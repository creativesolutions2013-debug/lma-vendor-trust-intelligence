"""Durable synthetic analyst revisions; no Streamlit or production integration.

The state is a strict declarative contract, not serialized session state or
trusted analysis. Every command freshly owns SQL/session authority and verifies
originals through the merged custody implementation before rebuilding analysis.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest
import re
import json

from sqlalchemy import and_, func, insert, select

from src.assessment_evidence_access import EvidenceReadRequest, _positive_id
from src.authz import PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_READ
from src.db import Assessment, Engagement, Organization, SyntheticAssessmentRevision, SyntheticEvidenceObject, Vendor
from src.guided_assessment_demo import complete_review, report_payload, source_role
from src.guided_assessment_package import assessment_package
from src.resumable_assessment_state import (
    MAX_STATE_BYTES, encode_draft, encode_state, parse_state, restore_state, with_review_state,
)
from src.session_leased_read import _SessionLeasedRead
from src.synthetic_custody_guards import require_synthetic_custody_guards
from src.synthetic_evidence_custody import SyntheticEvidenceReceipt, _retrieve_in_authorized_transaction
from src.synthetic_handoff_provenance import (
    encode_handoff_metadata, handoff_in_transaction, record_handoff_in_transaction,
)
from src.synthetic_revision_guards import require_synthetic_revision_guards
from src.tenant_read_scope import TenantReadService
from src.upload_assessment import read_upload, record_upload_review, risk_and_applicability


_PERMISSIONS = (PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_READ)


def _id(value):
    return _positive_id(value) and value <= 2**63 - 1


def _counter(value):
    return type(value) is int and 0 <= value < 2**31 - 1


@dataclass(frozen=True)
class SavedAssessmentRevision:
    assessment_id: int
    revision: int
    state_sha256: str


@dataclass(frozen=True)
class ResumedAssessment:
    assessment_id: int
    revision: int
    state_sha256: str
    intake: object
    uploads: tuple
    model: object
    actions: tuple
    completion: object
    completion_stale: bool
    report: dict
    package: bytes


@dataclass(frozen=True)
class _Command:
    assessment_id: int
    operation: str
    expected_revision: int = 0
    draft: bytes | None = None
    requirement_id: str = ""
    action: str = ""
    rationale: str = ""
    confirms_insufficiency: bool = False
    receipt: SyntheticEvidenceReceipt | None = None
    handoff_metadata: bytes | None = None


class _RevisionReader(TenantReadService):
    def __init__(self, factory, source, command):
        super().__init__(factory, identity_source=source)
        self._command = command
        self._before = None
        self._created = None
        self._originals = ()

    def _head(self, session):
        r = SyntheticAssessmentRevision
        row = session.execute(select(
            r.revision, func.substr(r.state_sha256, 1, 65), r.anchor_evidence_id,
            r.organization_id, r.vendor_id, r.engagement_id, r.assessment_id,
        ).where(r.assessment_id == self._command.assessment_id)
            .order_by(r.revision.desc()).limit(1)).one_or_none()
        if row is not None and (not all(_id(value) for value in (row[0], *row[2:]))
                or type(row[1]) is not str or re.fullmatch(r"[0-9a-f]{64}", row[1]) is None):
            raise PermissionError("Synthetic assessment unavailable.")
        return tuple(row) if row is not None else None

    def _binding(self, session, scope):
        require_synthetic_custody_guards(session.connection(), SyntheticEvidenceObject.__table__)
        require_synthetic_revision_guards(session.connection(), SyntheticAssessmentRevision.__table__)
        a, e, v, o = Assessment, Engagement, Vendor, Organization
        row = session.execute(select(o.id, v.id, e.id, a.id,
                                     func.substr(o.external_key, 1, 256),
                                     func.substr(v.display_name, 1, 256),
                                     func.substr(e.service_name, 1, 256))
            .select_from(a).join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id))
            .join(v, v.id == e.vendor_id).join(o, o.id == v.organization_id).where(
                a.id == self._command.assessment_id, o.id == scope.identity.organization_id,
                e.id.in_(scope.engagement_ids))).one_or_none()
        if row is None or any(not _id(value) for value in row[:4]):
            raise PermissionError("Synthetic assessment unavailable.")
        relation = tuple(row)
        head = self._head(session)
        if head is not None and head[3:] != relation[:4]:
            raise PermissionError("Synthetic assessment unavailable.")
        if self._created is not None:
            if head != self._created or relation != self._before[0]:
                raise PermissionError("Synthetic assessment unavailable.")
            return self._before
        binding = relation, head
        if self._before is None:
            self._before = binding
        return binding

    def _relationships(self, session, scope, *, lock):
        parents = super()._relationships(session, scope, lock=lock)
        return parents, self._binding(session, scope)

    def _read_state(self, session, head):
        if head is None:
            return None
        r = SyntheticAssessmentRevision
        payload = session.execute(select(func.substr(r.state_payload, 1, MAX_STATE_BYTES + 1))
            .where(r.assessment_id == self._command.assessment_id, r.revision == head[0])).scalar_one()
        if (type(payload) is not bytes or not 1 <= len(payload) <= MAX_STATE_BYTES
                or not compare_digest(sha256(payload).hexdigest(), head[1])):
            raise PermissionError("Synthetic assessment unavailable.")
        packet = parse_state(payload)
        if packet["sources"][0]["evidence_id"] != head[2]:
            raise PermissionError("Synthetic assessment unavailable.")
        return packet

    @staticmethod
    def _now(scope):
        now = scope.identity_source._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise PermissionError("Synthetic assessment unavailable.")
        return now.astimezone(timezone.utc)

    def _restore(self, session, scope, packet, relation, now):
        org, vendor, engagement, assessment, external_key, vendor_name, service_name = relation
        intake = packet["intake"]
        if (intake["assessment_id"] != str(assessment) or intake["organization_id"] != external_key
                or intake["vendor"] != vendor_name or intake["service"] != service_name):
            raise PermissionError("Synthetic assessment unavailable.")
        results = []
        for source in packet["sources"]:
            if tuple(source[key] for key in ("organization_id", "vendor_id", "engagement_id", "assessment_id")) != relation[:4]:
                raise PermissionError("Synthetic assessment unavailable.")
            request = EvidenceReadRequest(org, engagement, vendor, assessment, source["evidence_id"])
            results.append(_retrieve_in_authorized_transaction(session, scope, request, source["generation"]))
        self._originals = tuple(results)
        return restore_state(packet, self._originals, as_of=now.date())

    def _append_vendor_source(self, session, scope, packet, relation, now):
        """Append one explicitly captured delivery; never replace prior originals."""
        command = self._command
        restored = self._restore(session, scope, packet, relation, now)
        receipt = command.receipt
        if type(receipt) is not SyntheticEvidenceReceipt or len(packet["sources"]) >= 4:
            raise PermissionError("Synthetic assessment unavailable.")
        if any(source["filename"] == receipt.document_name or source["sha256"] == receipt.sha256
               or source["evidence_id"] == receipt.evidence_id for source in packet["sources"]):
            raise PermissionError("Synthetic source already present or capacity exceeded.")
        request = EvidenceReadRequest(relation[0], relation[2], relation[1], relation[3], receipt.evidence_id)
        original = _retrieve_in_authorized_transaction(session, scope, request, receipt.generation)
        if original.receipt != receipt:
            raise PermissionError("Synthetic original differs from capture acknowledgment.")
        metadata = json.loads(command.handoff_metadata.decode("ascii"))
        if encode_handoff_metadata(metadata) != command.handoff_metadata:
            raise PermissionError("Synthetic delivery metadata differs.")
        target = metadata["requirement_id"]
        if target not in {control.control_id for control in risk_and_applicability(restored.intake)[2].controls}:
            raise PermissionError("Synthetic delivery requirement is no longer applicable.")
        captured = receipt.created_at.astimezone(timezone.utc).date()
        intake = replace(restored.intake, as_of=now.date())
        upload = read_upload(replace(intake, as_of=captured), receipt.document_name, original.content,
            (target,), kind=metadata["kind"],
            observed_on=datetime.fromisoformat(metadata["observed_on"]).date() if metadata["observed_on"] else None,
            service=intake.service, environment=intake.environment)
        source = parse_state(encode_draft(intake, (upload,), (receipt,)))["sources"][0]
        packet["intake"]["as_of"] = now.date().isoformat()
        packet["sources"].append(source)
        # Provenance and source revision either commit together or remain absent.
        record_handoff_in_transaction(session, scope, receipt, metadata)
        return packet

    def materialize(self, session, scope):
        command = self._command
        relation, head = scope.relationships[1]
        latest = head[0] if head else 0
        if command.operation != "resume" and command.expected_revision != latest:
            raise PermissionError("Synthetic assessment unavailable.")
        previous = self._read_state(session, head)
        now = self._now(scope)
        if command.operation == "save":
            packet = parse_state(command.draft)
            if packet["actions"] or packet["need_reviews"] or packet["completion"] is not None:
                raise PermissionError("Synthetic assessment unavailable.")
            if previous is not None:
                packet.update({key: previous[key] for key in ("actions", "need_reviews", "completion")})
        else:
            if previous is None:
                raise PermissionError("Synthetic assessment unavailable.")
            packet = previous
        if command.operation == "append_vendor_source":
            packet = self._append_vendor_source(session, scope, packet, relation, now)
        restored = self._restore(session, scope, packet, relation, now)
        if command.operation == "resume":
            payload = report_payload(restored.model, restored.actions, restored.completion)
            payload["session_only"] = False
            payload["limitations"] = [
                "Server-authenticated synthetic service only; production identity, confidential evidence, vendor messages and authoritative risk updates remain disabled."
                if text == "No vendor messages, confidential evidence, real authentication or authoritative risk updates are enabled."
                else text for text in payload["limitations"]
            ]
            payload["persistence"] = {
                "mode": "Server-internal synthetic durable revision", "assessment_id": command.assessment_id,
                "revision": latest, "state_sha256": head[1], "completion_stale": restored.completion_stale,
                "historical_completion": packet["completion"],
                "insufficiency_history": packet["need_reviews"],
                "freshness_date": now.date().isoformat(),
                "policy_authority": "Latest saved assessment methodology; external active-policy changes are not detected.",
                "source_custody": [{
                    "evidence_id": original.receipt.evidence_id,
                    "generation": original.receipt.generation,
                    "filename": original.receipt.document_name,
                    "sha256": original.receipt.sha256,
                    "byte_length": original.receipt.byte_length,
                    "captured_at": original.receipt.created_at.isoformat(),
                    "capture_actor": {"issuer": original.receipt.issuer,
                                      "subject": original.receipt.subject,
                                      "role": original.receipt.effective_role},
                    "vendor_delivery": handoff_in_transaction(session, scope, original.receipt),
                } for original in self._originals],
            }
            package = assessment_package(payload, [(u.evidence, source_role(u.evidence).value) for u in restored.uploads])
            return ResumedAssessment(command.assessment_id, latest, head[1], restored.intake, restored.uploads,
                                     restored.model, restored.actions, restored.completion,
                                     restored.completion_stale, payload, package)
        if command.operation == "review":
            model, actions = record_upload_review(
                restored.model, restored.actions, command.requirement_id, command.action, command.rationale,
                confirms_insufficiency=command.confirms_insufficiency,
                analyst="Server-authorized synthetic reviewer",
            )
            actions = (*actions[:-1], replace(actions[-1], recorded_at=now.isoformat()))
            # Keep the old completion marker as history. The rebuild will mark
            # it stale; only an explicit finish may create a new completion.
            updated = with_review_state(packet, model, actions, None)
            updated["completion"] = packet["completion"]
            packet = updated
        elif command.operation == "finish":
            completion = replace(complete_review(restored.model, restored.actions), completed_at=now.isoformat())
            packet = with_review_state(packet, restored.model, restored.actions, completion)
        elif command.operation not in ("save", "append_vendor_source"):
            raise PermissionError("Synthetic assessment unavailable.")
        encoded = encode_state(packet)
        digest = sha256(encoded).hexdigest()
        org, vendor, engagement, assessment = relation[:4]
        members = [row for row in scope.authority[0] if row[1] == org]
        if len(members) != 1:
            raise PermissionError("Synthetic assessment unavailable.")
        anchor = packet["sources"][0]["evidence_id"]
        session.execute(insert(SyntheticAssessmentRevision).values(
            assessment_id=assessment, revision=latest + 1, organization_id=org, vendor_id=vendor,
            engagement_id=engagement, anchor_evidence_id=anchor, state_payload=encoded, state_sha256=digest,
            created_at=now, issuer=scope.identity.issuer, subject=scope.identity.principal.subject,
            session_id=scope.identity.session_id, effective_role=scope.role, membership_id=members[0][0],
        ))
        self._created = (latest + 1, digest, anchor, org, vendor, engagement, assessment)
        return SavedAssessmentRevision(assessment, latest + 1, digest)


class SyntheticResumableAssessmentService(_SessionLeasedRead):
    """Fixed analyst commands; every output is freshly authorized, provisional data."""
    _reader_type = _RevisionReader

    def _materialize(self, reader, session, scope):
        return reader.materialize(session, scope)

    def _command(self, command):
        if not _id(command.assessment_id) or not _counter(command.expected_revision):
            return None
        return self._leased_read(command, _PERMISSIONS)

    def save(self, assessment_id, *, expected_revision, draft):
        if type(draft) is not bytes or not 1 <= len(draft) <= MAX_STATE_BYTES:
            return None
        return self._command(_Command(assessment_id, "save", expected_revision, draft))

    def record_review(self, assessment_id, *, expected_revision, requirement_id, action, rationale,
                      confirms_insufficiency=False):
        if (type(requirement_id) is not str or not 1 <= len(requirement_id) <= 120
                or type(action) is not str or type(rationale) is not str or not 1 <= len(rationale) <= 2000
                or type(confirms_insufficiency) is not bool):
            return None
        return self._command(_Command(assessment_id, "review", expected_revision,
            requirement_id=requirement_id, action=action, rationale=rationale,
            confirms_insufficiency=confirms_insufficiency))

    def finish(self, assessment_id, *, expected_revision):
        return self._command(_Command(assessment_id, "finish", expected_revision))

    def append_vendor_source(self, assessment_id, *, expected_revision, receipt, metadata):
        """Server composition after an authenticated pending delivery is captured.

        The HTTP adapter never accepts a receipt or provenance DTO from a browser.
        This command freshly authorizes and verifies the exact immutable original.
        """
        try:
            if type(receipt) is not SyntheticEvidenceReceipt:
                return None
            encoded = encode_handoff_metadata(metadata)
            return self._command(_Command(assessment_id, "append_vendor_source", expected_revision,
                receipt=receipt, handoff_metadata=encoded))
        except Exception:
            return None

    def resume(self, assessment_id):
        return self._command(_Command(assessment_id, "resume"))
