"""Small SQL-backed synthetic byte custody proof; no app or production wiring.

Fresh Evidence + immutable original bytes commit together. No legacy location,
preflight result, key or URL is ever accepted as byte authority. A failed
acknowledgement after commit can leave an immutable unacknowledged record; None
does not promise rollback. See the Phase 4 design for exact lifecycle limits.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
import re
from uuid import uuid4

from sqlalchemy import and_, func, insert, select

from src.assessment_evidence_access import EvidenceReadRequest, _positive_id
from src.authz import PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_READ, PERMISSION_EVIDENCE_UPLOAD
from src.database_evidence_authority import _database_time
from src.db import Assessment, Engagement, Evidence, SyntheticEvidenceObject, Vendor
from src.session_leased_read import _SessionLeasedRead
from src.storage import validate_evidence_key
from src.synthetic_custody_guards import MAX_SYNTHETIC_EVIDENCE_BYTES, require_synthetic_custody_guards
from src import tenant_read_scope as scoped


def _id(value):
    return _positive_id(value) and value <= 2**63 - 1


def _generation(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _name(value):
    return (type(value) is str and value == value.strip()
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}", value) is not None)


@dataclass(frozen=True)
class SyntheticEvidenceReceipt:
    organization_id: int
    vendor_id: int
    engagement_id: int
    assessment_id: int
    evidence_id: int
    generation: str
    sha256: str
    byte_length: int
    document_name: str
    created_at: datetime
    issuer: str
    subject: str
    session_id: str  # Non-bearer correlation ID only.
    effective_role: str
    membership_id: int


@dataclass(frozen=True)
class SyntheticEvidenceResult:
    receipt: SyntheticEvidenceReceipt
    content: bytes


@dataclass(frozen=True)
class _Operation:
    assessment_id: int
    content: bytes | None = None
    document_name: str | None = None
    request: EvidenceReadRequest | None = None
    generation: str | None = None


class _CustodyReader(scoped.TenantReadService):
    def __init__(self, factory, source, target):
        super().__init__(factory, identity_source=source)
        self._target = target
        self._created_evidence_id = None
        self._saved = None

    def _load_receipt(self, session, scope, request, generation):
        o, d, a, e, v = SyntheticEvidenceObject, Evidence, Assessment, Engagement, Vendor
        # Bound text projections too, including on SQLite where VARCHAR lengths
        # alone are not enforced. Never select the payload in a metadata query.
        text_bounds = {"generation": 32, "storage_key": 500, "sha256": 64,
                       "document_name": 120, "issuer": 500, "subject": 255,
                       "session_id": 80, "effective_role": 80}
        columns = [getattr(o, field) for field in (
            "organization_id", "vendor_id", "engagement_id", "assessment_id",
            "evidence_id", "byte_length", "created_at", "membership_id")]
        columns += [func.substr(getattr(o, field), 1, bound + 1).label(field)
                    for field, bound in text_bounds.items()]
        columns.append(func.length(o.payload).label("actual_length"))
        row = session.execute(select(*columns).select_from(o).join(d, d.id == o.evidence_id)
            .join(a, and_(a.id == d.assessment_id, a.vendor_id == d.vendor_id))
            .join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id))
            .join(v, v.id == e.vendor_id).where(
                d.id == request.evidence_id, a.id == request.assessment_id,
                e.id == request.engagement_id, v.id == request.vendor_id,
                v.organization_id == request.organization_id,
                v.organization_id == scope.identity.organization_id,
                e.id.in_(scope.engagement_ids), o.organization_id == v.organization_id,
                o.vendor_id == v.id, o.engagement_id == e.id, o.assessment_id == a.id,
                o.generation == generation, d.storage_path == o.storage_key,
                d.file_hash == o.sha256,
            )).mappings().one_or_none()
        if (row is None or any(not _id(row[field]) for field in (
                "organization_id", "vendor_id", "engagement_id", "assessment_id", "evidence_id", "membership_id"))
                or any(type(row[field]) is not str or len(row[field]) > bound
                       for field, bound in text_bounds.items())
                or not _generation(row["generation"]) or not _name(row["document_name"])
                or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None
                or type(row["byte_length"]) is not int
                or not 1 <= row["byte_length"] <= MAX_SYNTHETIC_EVIDENCE_BYTES
                or row["actual_length"] != row["byte_length"]):
            raise PermissionError("Synthetic custody unavailable.")
        key = validate_evidence_key(row["storage_key"], vendor_id=request.vendor_id)
        if key != f"vendors/{request.vendor_id}/evidence/m7_{generation}.bin":
            raise PermissionError("Synthetic custody unavailable.")
        captured = _database_time(row["created_at"])
        if captured is None:
            raise PermissionError("Synthetic custody unavailable.")
        fields = {field: row[field] for field in SyntheticEvidenceReceipt.__dataclass_fields__}
        fields["created_at"] = captured
        return SyntheticEvidenceReceipt(**fields)

    def _binding(self, session, scope):
        require_synthetic_custody_guards(session.connection(), SyntheticEvidenceObject.__table__)
        target = self._target
        if target.request is not None:
            return self._load_receipt(session, scope, target.request, target.generation)
        a, e, v = Assessment, Engagement, Vendor
        row = session.execute(select(v.organization_id, a.vendor_id, a.engagement_id, a.id)
            .select_from(a).join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id))
            .join(v, v.id == e.vendor_id).where(
                a.id == target.assessment_id, v.organization_id == scope.identity.organization_id,
                e.id.in_(scope.engagement_ids))).one_or_none()
        if row is None or any(not _id(value) for value in row):
            raise PermissionError("Synthetic custody unavailable.")
        if self._saved is not None:
            request = EvidenceReadRequest(row[0], row[2], row[1], row[3], self._created_evidence_id)
            if self._load_receipt(session, scope, request, self._saved.generation) != self._saved:
                raise PermissionError("Synthetic custody unavailable.")
        return tuple(row)

    def _relationships(self, session, scope, *, lock):
        parents = super()._relationships(session, scope, lock=lock)
        if self._created_evidence_id is not None:
            # Only this operation's freshly inserted Evidence is an intended
            # inventory change. All prior rows/authority retain exact equality.
            parents = (*parents[:-1], tuple(row for row in parents[-1]
                                           if row[0] != self._created_evidence_id))
        return parents, self._binding(session, scope)

    def materialize(self, session, scope):
        target = self._target
        if target.request is not None:
            receipt = scope.relationships[1]
            o = SyntheticEvidenceObject
            payload = session.execute(select(func.substr(o.payload, 1, MAX_SYNTHETIC_EVIDENCE_BYTES + 1))
                .where(o.evidence_id == receipt.evidence_id, o.generation == receipt.generation)).scalar_one()
            if (type(payload) is not bytes or len(payload) != receipt.byte_length
                    or len(payload) > MAX_SYNTHETIC_EVIDENCE_BYTES
                    or not compare_digest(sha256(payload).hexdigest(), receipt.sha256)):
                raise PermissionError("Synthetic custody unavailable.")
            return SyntheticEvidenceResult(receipt, payload)

        org, vendor, engagement, assessment = scope.relationships[1]
        generation = uuid4().hex
        if not _generation(generation):
            raise PermissionError("Synthetic custody unavailable.")
        key = validate_evidence_key(f"vendors/{vendor}/evidence/m7_{generation}.bin", vendor_id=vendor)
        digest = sha256(target.content).hexdigest()
        captured = scoped._utc_now()
        evidence_id = session.execute(insert(Evidence).values(
            vendor_id=vendor, assessment_id=assessment, document_type="Synthetic fixture",
            document_name=target.document_name, storage_path=key, file_hash=digest,
            status="Synthetic stored", created_at=captured,
        ).returning(Evidence.id)).scalar_one()
        self._created_evidence_id = evidence_id
        member = [row for row in scope.authority[0] if row[1] == org]
        if len(member) != 1 or not _id(evidence_id):
            raise PermissionError("Synthetic custody unavailable.")
        session.execute(insert(SyntheticEvidenceObject).values(
            evidence_id=evidence_id, organization_id=org, vendor_id=vendor,
            engagement_id=engagement, assessment_id=assessment, generation=generation,
            storage_key=key, byte_length=len(target.content), payload=target.content, sha256=digest,
            document_name=target.document_name, created_at=captured, issuer=scope.identity.issuer,
            subject=scope.identity.principal.subject, session_id=scope.identity.session_id,
            effective_role=scope.role, membership_id=member[0][0],
        ))
        request = EvidenceReadRequest(org, engagement, vendor, assessment, evidence_id)
        self._saved = self._load_receipt(session, scope, request, generation)
        return self._saved


class SyntheticEvidenceCustodyService(_SessionLeasedRead):
    """Fixed save/retrieve only; all failures release no receipt or bytes.

    No delete, list, URL/key read, overwrite, legacy adoption or production
    configuration. A receipt is data; each retrieval reauthenticates. A denied
    acknowledgement may follow a committed write: callers must not auto-retry.
    """
    _reader_type = _CustodyReader

    def _materialize(self, reader, session, scope):
        return reader.materialize(session, scope)

    def save(self, assessment_id, content, *, document_name):
        if (not _id(assessment_id) or type(content) is not bytes
                or not 1 <= len(content) <= MAX_SYNTHETIC_EVIDENCE_BYTES or not _name(document_name)):
            return None
        target = _Operation(assessment_id, content, document_name)
        return self._leased_read(target, (PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_UPLOAD))

    def retrieve(self, request, *, generation):
        if (type(request) is not EvidenceReadRequest or any(not _id(value) for value in (
                request.organization_id, request.engagement_id, request.vendor_id,
                request.assessment_id, request.evidence_id)) or not _generation(generation)):
            return None
        target = _Operation(request.assessment_id, request=request, generation=generation)
        return self._leased_read(target, PERMISSION_EVIDENCE_READ)
