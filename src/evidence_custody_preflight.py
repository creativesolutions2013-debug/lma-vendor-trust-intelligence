"""Unwired synthetic relationship/key preflight; never byte-access authority.

No storage operation, URL, key, file existence or hidden-scope metadata is
released. True means only that current SQL linkage and canonical key syntax
passed the leased check. It cannot prove historical ownership, source integrity,
storage confinement or reserve a key for subsequent I/O. Production stays closed.
"""
from sqlalchemy import and_, select

from src.assessment_evidence_access import EvidenceReadRequest, _positive_id
from src.authz import PERMISSION_EVIDENCE_READ
from src.db import Assessment, Engagement, Evidence, Vendor
from src.session_leased_read import _SessionLeasedRead
from src.storage import validate_evidence_key
from src.tenant_read_scope import TenantReadService


class _EvidenceLinkageReader(TenantReadService):
    """Private per-operation reader; its binding never leaves the service."""

    def __init__(self, factory, source, request):
        super().__init__(factory, identity_source=source)
        self._request = request

    def _binding(self, session, scope, *, lock):
        r = self._request
        d, a, e, v = Evidence, Assessment, Engagement, Vendor
        query = select(v.organization_id, d.vendor_id, a.engagement_id,
                       d.assessment_id, d.id, d.storage_path).select_from(d).join(
            a, and_(a.id == d.assessment_id, a.vendor_id == d.vendor_id)
        ).join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id))
        query = query.join(v, v.id == e.vendor_id).where(
            v.organization_id == scope.identity.organization_id,
            v.organization_id == r.organization_id, v.id == r.vendor_id,
            e.id == r.engagement_id, e.id.in_(scope.engagement_ids),
            a.id == r.assessment_id, d.id == r.evidence_id,
        )
        if lock:
            query = query.with_for_update(of=d)
        row = session.execute(query).one_or_none()
        if row is None:
            raise PermissionError("Evidence linkage unavailable.")
        key = validate_evidence_key(row.storage_path, vendor_id=r.vendor_id)
        # Inspect references even in hidden or inconsistent scopes, without
        # exposing their identity. No cross-scope row locks: an alias denies
        # immediately, and locking it cannot prevent a later phantom INSERT.
        references = session.execute(select(d.id).where(
            d.storage_path == key).order_by(d.id).limit(2)).scalars().all()
        if references != [r.evidence_id]:
            raise PermissionError("Evidence linkage unavailable.")
        return tuple(row)

    def _relationships(self, session, scope, *, lock):
        parents = super()._relationships(session, scope, lock=lock)
        return parents, self._binding(session, scope, lock=lock)


class SyntheticEvidenceCustodyPreflightService(_SessionLeasedRead):
    """Diagnostic boolean only, not a grant or permission for later storage use.

    Server wiring owns the session source/factory. Every call reauthenticates and
    checks effective evidence.read permission, fresh grants and exact parents.
    No public source, storage, key or identity DTO is accepted from the caller.
    """

    _reader_type = _EvidenceLinkageReader

    def preflight(self, request):
        if type(request) is not EvidenceReadRequest or any(
                not _positive_id(value) or value > 2**63 - 1 for value in (
                    request.organization_id, request.engagement_id, request.vendor_id,
                    request.assessment_id, request.evidence_id)):
            return False
        return self._leased_read(request, PERMISSION_EVIDENCE_READ) is not None
