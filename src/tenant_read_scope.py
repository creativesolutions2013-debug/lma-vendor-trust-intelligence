"""M4C-2B-1: unwired, read-only, engagement-scoped inventory projections.

This service accepts a *server-injected* trusted identity source and a dedicated
fresh database-session factory. Python DTOs, request selectors and dev roles
are not credentials. A production caller must first establish verified OIDC
identity, durable session validity and deployment-level isolation.

No application routes use this service yet. Do not connect it to development
Admin, streamlit.session_state or production startup. No file keys, bytes,
governed outcomes, or authorization tokens are returned.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select

from src.assessment_evidence_access import AuthenticatedIdentity, _current, _positive_id, _text
from src.authz import (
    PERMISSION_EVIDENCE_READ, PERMISSION_VENDOR_READ, Principal, VALID_ROLES, can,
)
from src.db import (
    Assessment, Engagement, EngagementAccessGrant, Evidence, Organization,
    OrganizationMembership, Vendor,
)


def _utc_now():
    return datetime.now(timezone.utc)


def _db_time(value):
    # Authorization timestamps are stored as UTC; SQLite returns naive values.
    if type(value) is not datetime:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class VendorSummary:
    id: int
    display_name: str
    criticality: str | None


@dataclass(frozen=True)
class EngagementSummary:
    id: int
    vendor_id: int
    service_name: str
    status: str | None


@dataclass(frozen=True)
class AssessmentSummary:
    id: int
    vendor_id: int
    engagement_id: int
    assessment_type: str
    status: str | None


@dataclass(frozen=True)
class EvidenceSummary:
    id: int
    vendor_id: int
    assessment_id: int
    engagement_id: int
    document_type: str
    document_name: str
    status: str | None


@dataclass(frozen=True)
class ScopedCounts:
    vendors: int
    engagements: int
    assessments: int
    evidence: int


@dataclass(frozen=True)
class _Scope:
    # Never returned to API/UI callers.
    identity: AuthenticatedIdentity
    role: str
    engagement_ids: frozenset[int]


def _session_identity_key(identity):
    return (identity.issuer, identity.principal.subject, identity.audience,
            identity.session_id, identity.organization_id,
            identity.issued_at, identity.expires_at)


class TenantReadService:
    """Projection-only repository; permission AND exact engagement scope required.

    The injected identity source must validate a real server-owned session
    independently of this service. No authentication is implemented here.
    The dedicated session factory must not share a request's pending ORM writes.
    Any failure yields an indistinguishable empty result.
    """

    def __init__(self, session_factory, *, identity_source=None):
        self._sessions = session_factory
        self._identity_source = identity_source

    def _scope(self, permission):
        try:
            if self._sessions is None or self._identity_source is None:
                return None
            identity = self._identity_source.authenticated_identity()
            now = _utc_now()
            if (type(identity) is not AuthenticatedIdentity
                    or type(identity.principal) is not Principal
                    or not _positive_id(identity.organization_id)
                    or not all(_text(value) for value in (
                        identity.issuer, identity.principal.subject,
                        identity.audience, identity.session_id,
                    ))
                    or not _current(identity.issued_at, identity.expires_at, now)):
                return None

            m, g = OrganizationMembership, EngagementAccessGrant
            with self._sessions() as session, session.no_autoflush:
                # Check *all* current memberships for this issuer+subject. Never
                # choose a tenant from a UI selector or first-match DB row.
                memberships = session.execute(select(
                    m.id, m.organization_id, m.role, m.status,
                    m.valid_from, m.expires_at,
                ).join(Organization, Organization.id == m.organization_id).where(
                    m.issuer == identity.issuer, m.subject == identity.principal.subject,
                )).all()
                current_members = [
                    member for member in memberships
                    if member.status == "active"
                    and _current(_db_time(member.valid_from), _db_time(member.expires_at), now)
                ]
                if len(current_members) != 1:
                    return None
                member = current_members[0]
                if (member.organization_id != identity.organization_id
                        or member.role not in VALID_ROLES
                        or not can(Principal(identity.principal.subject,
                                             identity.principal.display_name,
                                             identity.principal.email, member.role),
                                   permission)):
                    return None

                # Duplicate grant records, even if one is inactive, cannot be
                # used as an arbitrary first-match entitlement.
                grants = session.execute(select(
                    g.engagement_id, g.status, g.valid_from, g.expires_at,
                ).where(g.membership_id == member.id)).all()

            # Re-evaluate membership, grant and identity windows after I/O:
            # the initial authorization clock may have expired mid-query.
            end_now = _utc_now()
            if (not _current(_db_time(member.valid_from), _db_time(member.expires_at), end_now)
                    or not _current(identity.issued_at, identity.expires_at, end_now)):
                return None
            by_engagement = {}
            for grant in grants:
                by_engagement.setdefault(grant.engagement_id, []).append(grant)
            entitled = frozenset(
                engagement_id for engagement_id, rows in by_engagement.items()
                if _positive_id(engagement_id) and len(rows) == 1
                and rows[0].status == "active"
                and _current(_db_time(rows[0].valid_from), _db_time(rows[0].expires_at), end_now)
            )
            return _Scope(identity, member.role, entitled)
        except Exception:
            return None

    def _project(self, kind, scope, *, item_id=None, parent_id=None):
        v, e, a, d = Vendor, Engagement, Assessment, Evidence
        if kind == "vendor":
            columns = (v.id, v.display_name, v.criticality)
            stmt = select(*columns).select_from(v).join(e, e.vendor_id == v.id)
            key, parent_key, target = v.id, None, VendorSummary
        elif kind == "engagement":
            columns = (e.id, e.vendor_id, e.service_name, e.status)
            stmt = select(*columns).select_from(e).join(v, v.id == e.vendor_id)
            key, parent_key, target = e.id, e.vendor_id, EngagementSummary
        elif kind == "assessment":
            columns = (a.id, a.vendor_id, a.engagement_id, a.assessment_type, a.status)
            stmt = select(*columns).select_from(a).join(
                e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id)
            ).join(v, v.id == e.vendor_id)
            key, parent_key, target = a.id, a.engagement_id, AssessmentSummary
        elif kind == "evidence":
            columns = (d.id, d.vendor_id, d.assessment_id, a.engagement_id,
                       d.document_type, d.document_name, d.status)
            stmt = select(*columns).select_from(d).join(
                a, and_(a.id == d.assessment_id, a.vendor_id == d.vendor_id)
            ).join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id)
            ).join(v, v.id == e.vendor_id)
            key, parent_key, target = d.id, d.assessment_id, EvidenceSummary
        else:
            return ()
        stmt = stmt.where(
            v.organization_id == scope.identity.organization_id,
            e.id.in_(scope.engagement_ids),
        )
        if item_id is not None:
            stmt = stmt.where(key == item_id)
        if parent_id is not None and parent_key is not None:
            stmt = stmt.where(parent_key == parent_id)
        stmt = stmt.distinct().order_by(key)
        with self._sessions() as session, session.no_autoflush:
            return tuple(target(*row) for row in session.execute(stmt).all())

    def _read(self, kind, *, item_id=None, parent_id=None):
        if ((item_id is not None and not _positive_id(item_id))
                or (parent_id is not None and not _positive_id(parent_id))):
            return ()
        permission = PERMISSION_EVIDENCE_READ if kind == "evidence" else PERMISSION_VENDOR_READ
        first = self._scope(permission)
        if first is None or not first.engagement_ids:
            return ()
        try:
            rows = self._project(kind, first, item_id=item_id, parent_id=parent_id)
            # Revoked grants and changed/expired sessions during I/O must not
            # release already-collected projections. Re-read DB entitlements.
            second = self._scope(permission)
            if (second is None or _session_identity_key(first.identity) != _session_identity_key(second.identity)
                    or first.role != second.role or first.engagement_ids != second.engagement_ids):
                return ()
            # Also recheck relationships after the second entitlement snapshot
            # so parent-link changes cannot release stale projections.
            if rows != self._project(kind, second, item_id=item_id, parent_id=parent_id):
                return ()
            # Verify entitlements again after the final row query: a concurrent
            # revocation there must not leak the rows selected earlier.
            final = self._scope(permission)
            if (final is None or _session_identity_key(first.identity) != _session_identity_key(final.identity)
                    or first.role != final.role or first.engagement_ids != final.engagement_ids):
                return ()
            last = self._identity_source.authenticated_identity()
            if (type(last) is not AuthenticatedIdentity or type(last.principal) is not Principal
                    or _session_identity_key(last) != _session_identity_key(final.identity)
                    or not _current(last.issued_at, last.expires_at, _utc_now())):
                return ()
            return rows
        except Exception:
            return ()

    def list_vendors(self):
        return self._read("vendor")

    def get_vendor(self, vendor_id):
        rows = self._read("vendor", item_id=vendor_id)
        return rows[0] if len(rows) == 1 else None

    def list_engagements(self, *, vendor_id=None):
        return self._read("engagement", parent_id=vendor_id)

    def get_engagement(self, engagement_id):
        rows = self._read("engagement", item_id=engagement_id)
        return rows[0] if len(rows) == 1 else None

    def list_assessments(self, *, engagement_id=None):
        return self._read("assessment", parent_id=engagement_id)

    def get_assessment(self, assessment_id):
        rows = self._read("assessment", item_id=assessment_id)
        return rows[0] if len(rows) == 1 else None

    def list_evidence(self, *, assessment_id=None):
        return self._read("evidence", parent_id=assessment_id)

    def get_evidence(self, evidence_id):
        rows = self._read("evidence", item_id=evidence_id)
        return rows[0] if len(rows) == 1 else None

    def visible_counts(self):
        # Counts inherit the same access protections as each read. These are
        # explicitly *not* global customer/vendor totals.
        return ScopedCounts(
            len(self.list_vendors()), len(self.list_engagements()),
            len(self.list_assessments()), len(self.list_evidence()),
        )
