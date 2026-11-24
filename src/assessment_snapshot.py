"""Unwired synthetic metadata round trip; no persistence or assessment restore.

An envelope is consistency data, never a credential, a source authenticity proof
or permission to reuse a review. Every operation needs a current server session
lease and the existing locked SQL membership/grant/ownership boundary. Do not
register this service in Streamlit, production auth, upload or storage routes.
"""
import hashlib
import json
import re
from contextlib import ExitStack
from datetime import datetime, timezone

from sqlalchemy import and_, select

from src.assessment_evidence_access import _positive_id
from src.authz import PERMISSION_ASSESSMENT_MANAGE
from src.db import Assessment, Engagement, Evidence, Vendor
from src.server_sessions import SessionManager
from src.session_identity_source import SessionIdentitySource
from src.tenant_read_scope import TenantReadService


MAX_METADATA_BYTES = 2048
MAX_SOURCE_ROWS = 200
_CONTEXT_VERSION = "linked-assessment-metadata-v1"
_SOURCE_VERSION = "evidence-inventory-metadata-v1"
_IDS = ("organization_id", "vendor_id", "engagement_id", "assessment_id")
_HASHES = ("context_fingerprint", "source_fingerprint")
_FIELDS = frozenset((*_IDS, *_HASHES, "schema_version", "synthetic",
                     "context_version", "source_version"))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field.")
        result[key] = value
    return result


def _parse(metadata):
    if type(metadata) is not bytes or not 1 <= len(metadata) <= MAX_METADATA_BYTES:
        raise ValueError("Invalid metadata.")
    packet = json.loads(metadata.decode("ascii"), object_pairs_hook=_unique_object)
    if (type(packet) is not dict or set(packet) != _FIELDS
            or type(packet["schema_version"]) is not int or packet["schema_version"] != 1
            or packet["synthetic"] is not True
            or packet["context_version"] != _CONTEXT_VERSION
            or packet["source_version"] != _SOURCE_VERSION
            or any(not _positive_id(packet[key]) or packet[key] > 2**63 - 1 for key in _IDS)
            or any(type(packet[key]) is not str
                   or re.fullmatch(r"[0-9a-f]{64}", packet[key]) is None for key in _HASHES)):
        raise ValueError("Invalid metadata.")
    return _canonical(packet)


def _cell(value):
    """Bound the selected SQL metadata; never traverse arbitrary ORM objects."""
    if value is None or type(value) is bool:
        return value
    if type(value) is int and 0 < value <= 2**63 - 1:
        return value
    if type(value) is str and len(value) <= 512:
        return value
    if type(value) is datetime:
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return aware.astimezone(timezone.utc).isoformat()
    raise ValueError("Invalid inventory metadata.")


def _fingerprint(value):
    encoded = _canonical(value)
    if len(encoded) > 262144:
        raise ValueError("Inventory metadata exceeds bound.")
    return hashlib.sha256(encoded).hexdigest()


class _MetadataReader(TenantReadService):
    """Private per-operation reader; carries no reusable authorization result."""

    def __init__(self, factory, source, assessment_id):
        super().__init__(factory, identity_source=source)
        self._assessment_id = assessment_id

    def _binding(self, session, scope, *, lock):
        a, e, v, d = Assessment, Engagement, Vendor, Evidence
        # Only selected database metadata is hashed. In particular no notes,
        # approval/risk fields, extracted facts, original bytes or storage keys.
        row = session.execute(select(
            v.organization_id, a.vendor_id, a.engagement_id, a.id,
            a.assessment_type, a.assessment_reason, a.status, a.created_at,
            e.service_name, e.business_criticality, e.data_classification,
            e.production_access, e.network_access, e.privileged_access, e.ai_enabled, e.status,
        ).select_from(a).join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id))
          .join(v, v.id == e.vendor_id).where(
              a.id == self._assessment_id, v.organization_id == scope.identity.organization_id,
              e.id.in_(scope.engagement_ids),
          )).one_or_none()
        if row is None or any(not _positive_id(value) for value in row[:4]):
            raise PermissionError("Snapshot metadata unavailable.")
        context = tuple(_cell(value) for value in row)
        # Include inconsistent linked inventory in the query and reject it;
        # silently filtering bad vendor links would pretend the binding is whole.
        query = select(
            d.id, d.vendor_id, d.assessment_id, d.document_type,
            d.document_date, d.coverage_start, d.coverage_end, d.expiration_date,
            d.file_hash, d.status, d.created_at,
        ).where(d.assessment_id == self._assessment_id).order_by(d.id).limit(MAX_SOURCE_ROWS + 1)
        if lock:
            query = query.with_for_update(of=d)
        inventory = session.execute(query).all()
        if (len(inventory) > MAX_SOURCE_ROWS
                or any(not _positive_id(item.id) or item.vendor_id != row.vendor_id
                       or item.assessment_id != row.id for item in inventory)):
            raise PermissionError("Snapshot metadata unavailable.")
        sources = tuple(tuple(_cell(value) for value in item) for item in inventory)
        packet = dict(zip(_IDS, context[:4]))
        packet.update(schema_version=1, synthetic=True,
                      context_version=_CONTEXT_VERSION, source_version=_SOURCE_VERSION,
                      context_fingerprint=_fingerprint((_CONTEXT_VERSION, context)),
                      source_fingerprint=_fingerprint((_SOURCE_VERSION, sources)))
        return _parse(_canonical(packet))

    def _relationships(self, session, scope, *, lock):
        # Parent locks and the membership identity guard stay owned by the
        # existing boundary. Include metadata in its final post-identity compare,
        # before that boundary's final cached-window/time validation.
        parents = super()._relationships(session, scope, lock=lock)
        return parents, self._binding(session, scope, lock=lock)


class SyntheticAssessmentSnapshotService:
    """Server-internal synthetic metadata only; default-deny, no save/list API.

    ``validate_resume`` proves a round trip still matches selected current SQL
    metadata. It restores nothing and authorizes no later operation. Unsigned
    client data cannot confer tenant authority, approval or source authenticity.
    """

    def __init__(self, session_factory=None, *, identity_source=None):
        self._sessions = session_factory
        self._identity_source = identity_source

    def _check(self, source, factory):
        if (type(source) is not SessionIdentitySource or factory is None
                or self._identity_source is not source or self._sessions is not factory
                or source._database_sessions is not factory):
            raise PermissionError("Snapshot metadata unavailable.")

    def _operation(self, assessment_id, expected):
        if not _positive_id(assessment_id) or assessment_id > 2**63 - 1:
            return None
        try:
            source, factory = self._identity_source, self._sessions
            self._check(source, factory)
            manager, handle, source_clock = source._sessions, source._handle, source._clock
            if type(manager) is not SessionManager:
                raise PermissionError("Snapshot metadata unavailable.")
            store, clock, idle, absolute = manager._store, manager._clock, manager._idle, manager._absolute

            def pinned():
                # Pin inner dependencies before the initial SQL/source work as
                # well as during the later lease. Replacing one with an object
                # that returns identical identity fields cannot preserve scope.
                self._check(source, factory)
                if (source._sessions is not manager or source._handle != handle
                        or source._clock is not source_clock or manager._store is not store
                        or manager._clock is not clock or type(manager._idle) is not int
                        or manager._idle != idle or type(manager._absolute) is not int
                        or manager._absolute != absolute):
                    raise PermissionError("Snapshot metadata unavailable.")

            pinned()
            reader = _MetadataReader(factory, source, assessment_id)
            # Existing tenant reads acquire SQL locks before their final session
            # lookup. Keep that order: acquire SQL authority first, then lease
            # the session and complete SQL while the lease is still held.
            with ExitStack() as database:
                session, scope = database.enter_context(
                    reader._authorized_transaction(PERMISSION_ASSESSMENT_MANAGE))
                pinned()
                with source.session_operation():
                    pinned()
                    packet = scope.relationships[1]
                    if expected is not None and expected != packet:
                        raise PermissionError("Snapshot metadata unavailable.")
                    reader._finish_authorized(session, scope, PERMISSION_ASSESSMENT_MANAGE)
                    pinned()
                    database.close()  # Commit/close SQL before releasing the lease.
                pinned()
            pinned()
            reader._finish_cached_windows(scope, PERMISSION_ASSESSMENT_MANAGE)
            return packet  # Only after SQL completion and successful lease cleanup.
        except Exception:
            return None  # Uniform denial; no tokens, hidden metadata or provider errors.

    def capture(self, assessment_id):
        return self._operation(assessment_id, None)

    def validate_resume(self, assessment_id, metadata):
        try:
            expected = _parse(metadata)
        except Exception:
            return None
        return self._operation(assessment_id, expected)
