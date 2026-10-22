"""M4C-2B-1: unwired, read-only, engagement-scoped inventory projections.

This service accepts a *server-injected* trusted identity source and a dedicated
fresh database-session factory. Python DTOs, request selectors and dev roles
are not credentials. A production caller must first establish verified OIDC
identity, durable session validity and deployment-level isolation.

No application routes use this service yet. Do not connect it to development
Admin, streamlit.session_state or production startup. No file keys, bytes,
governed outcomes, or authorization tokens are returned.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from sqlalchemy import and_, func, select

from src.assessment_evidence_access import AuthenticatedIdentity, _current, _positive_id, _text
from src.authz import (
    PERMISSION_EVIDENCE_READ, PERMISSION_VENDOR_READ, Principal, VALID_ROLES, can,
)
from src.db import (
    Assessment, Engagement, EngagementAccessGrant, Evidence, Organization,
    OrganizationMembership, Vendor,
)
from src.membership_identity_guard import acquire_membership_identity_guard


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
    authority: tuple = ()
    relationships: tuple = ()
    identity_source: object = field(default=None, repr=False, compare=False)
    session_factory: object = field(default=None, repr=False, compare=False)


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

    def _check_dependencies(self, source, factory):
        if (source is None or factory is None or self._identity_source is not source
                or self._sessions is not factory):
            raise PermissionError("Scoped access denied.")

    @staticmethod
    def _valid_identity(identity, now):
        return (type(identity) is AuthenticatedIdentity
                and type(identity.principal) is Principal
                and _positive_id(identity.organization_id)
                and all(_text(value) for value in (identity.issuer, identity.principal.subject,
                                                   identity.audience, identity.session_id))
                and _current(identity.issued_at, identity.expires_at, now))

    @staticmethod
    def _permitted(identity, role, permission):
        permissions = permission if type(permission) is tuple else (permission,)
        return role in VALID_ROLES and all(can(Principal(
            identity.principal.subject, identity.principal.display_name,
            identity.principal.email, role), value) for value in permissions)

    def _scope(self, permission, *, session=None, identity=None, lock=False):
        """Internal authority snapshot; public reads use the locked transaction.

        The optional independent snapshot remains for compatibility with unwired
        callers, but is not an authorization capability and cannot release data.
        """
        try:
            if self._sessions is None or self._identity_source is None:
                return None
            if identity is None:
                identity = self._identity_source.authenticated_identity()
            if not self._valid_identity(identity, _utc_now()):
                return None
            if session is None:
                with self._sessions() as database, database.no_autoflush:
                    return self._scope(permission, session=database, identity=identity)
            m, g = OrganizationMembership, EngagementAccessGrant
            memberships_query = select(
                m.id, m.organization_id, m.role, m.status, m.valid_from, m.expires_at,
            ).join(Organization, Organization.id == m.organization_id).where(
                m.issuer == identity.issuer, m.subject == identity.principal.subject,
            ).order_by(m.id)
            if lock:
                memberships_query = memberships_query.with_for_update(of=m)
            memberships = session.execute(memberships_query).all()
            now = _utc_now()
            current_members = [member for member in memberships
                               if member.status == "active"
                               and _current(_db_time(member.valid_from), _db_time(member.expires_at), now)]
            if len(current_members) != 1:
                return None
            member = current_members[0]
            if (member.organization_id != identity.organization_id
                    or not self._permitted(identity, member.role, permission)):
                return None
            grants_query = select(
                g.id, g.engagement_id, g.status, g.valid_from, g.expires_at,
            ).where(g.membership_id == member.id).order_by(g.id)
            if lock:
                grants_query = grants_query.with_for_update(of=g)
            grants = session.execute(grants_query).all()
            end_now = _utc_now()
            if (not _current(_db_time(member.valid_from), _db_time(member.expires_at), end_now)
                    or not self._valid_identity(identity, end_now)):
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
            # Include all authority columns: role/window/status changes and newly
            # ambiguous membership/grant rows invalidate the complete response.
            authority = (tuple(tuple(row) for row in memberships), tuple(tuple(row) for row in grants))
            return _Scope(identity, member.role, entitled, authority)
        except Exception:
            return None

    def _relationships(self, session, scope, *, lock):
        """Lock canonical existing parents without DISTINCT/aggregate FOR UPDATE.

        Deterministic table/ID ordering is shared by read and export. New inserts
        are outside the issued snapshot; no new entitlement is inferred from them.
        """
        v, e, a, d = Vendor, Engagement, Assessment, Evidence
        org = scope.identity.organization_id
        queries = [
            (Organization, select(Organization.id).where(Organization.id == org)),
            # Lock engagements before deriving their vendor parents; otherwise
            # a reassignment between vendor/engagement locks could leave the new
            # vendor row unprotected at issuance.
            (e, select(e.id, e.vendor_id, e.service_name, e.status).where(e.id.in_(scope.engagement_ids))),
            (v, select(v.id, v.organization_id, v.display_name, v.criticality).where(
                v.organization_id == org,
                v.id.in_(select(e.vendor_id).where(e.id.in_(scope.engagement_ids))))),
            (a, select(a.id, a.vendor_id, a.engagement_id, a.assessment_type, a.status).join(
                e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id)
            ).join(v, v.id == e.vendor_id).where(v.organization_id == org, e.id.in_(scope.engagement_ids))),
            (d, select(d.id, d.vendor_id, d.assessment_id, d.document_type, d.document_name, d.status).join(
                a, and_(a.id == d.assessment_id, a.vendor_id == d.vendor_id)
            ).join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id)
            ).join(v, v.id == e.vendor_id).where(v.organization_id == org, e.id.in_(scope.engagement_ids))),
        ]
        result = []
        for model, query in queries:
            query = query.order_by(model.id)
            if lock:
                query = query.with_for_update(of=model)
            result.append(tuple(tuple(row) for row in session.execute(query).all()))
        return tuple(result)

    @contextmanager
    def _authorized_transaction(self, permission):
        """Server-internal transaction; hold SQL authority until issuance.

        PostgreSQL row locks serialize revocation/reparenting of existing rows.
        SQLite reserves its writer before reading. No endpoint is wired here.
        """
        source, factory = self._identity_source, self._sessions
        self._check_dependencies(source, factory)
        identity = source.authenticated_identity()
        self._check_dependencies(source, factory)
        if not self._valid_identity(identity, _utc_now()):
            raise PermissionError("Scoped access denied.")
        with factory() as session, session.no_autoflush, session.begin():
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            elif session.get_bind().dialect.name == "postgresql":
                session.connection().exec_driver_sql("SET LOCAL lock_timeout = '3s'")
                session.connection().exec_driver_sql("SET LOCAL statement_timeout = '10s'")
                acquire_membership_identity_guard(session.connection(), OrganizationMembership.__table__,
                                                   identity.issuer, identity.principal.subject)
            else:
                raise PermissionError("Scoped access denied.")
            scope = self._scope(permission, session=session, identity=identity, lock=True)
            if scope is None or not scope.engagement_ids:
                raise PermissionError("Scoped access denied.")
            scope = replace(scope, relationships=self._relationships(session, scope, lock=True),
                            identity_source=source, session_factory=factory)
            yield session, scope
            # A dedicated read transaction must never flush unrelated pending
            # ORM changes at commit. The factory contract is server-owned.
            if session.new or session.dirty or session.deleted:
                raise PermissionError("Scoped access denied.")
            self._check_dependencies(source, factory)

    def _finish_authorized(self, session, scope, permission):
        """Last remote session check, then SQL/time checks while locks remain held.

        There is no remote lookup after the final DB validation. Session changes
        after issuance require a future coordinated session lease to retract data.
        """
        self._check_dependencies(scope.identity_source, scope.session_factory)
        last = scope.identity_source.authenticated_identity()
        self._check_dependencies(scope.identity_source, scope.session_factory)
        if (not self._valid_identity(last, _utc_now())
                or _session_identity_key(last) != _session_identity_key(scope.identity)):
            raise PermissionError("Scoped access denied.")
        final = self._scope(permission, session=session, identity=last)
        if (final is None or final.role != scope.role or final.engagement_ids != scope.engagement_ids
                or final.authority != scope.authority
                or self._relationships(session, final, lock=False) != scope.relationships):
            raise PermissionError("Scoped access denied.")
        # SQL reads can block too. Re-evaluate the cached locked windows after
        # all I/O, immediately before issuance; no identity/SQL call follows.
        now = _utc_now()
        if not self._valid_identity(last, now):
            raise PermissionError("Scoped access denied.")
        members, grants = final.authority
        active = [row for row in members if row[3] == "active"
                  and _current(_db_time(row[4]), _db_time(row[5]), now)]
        current_grants = frozenset(row[1] for row in grants if row[2] == "active"
                                  and _current(_db_time(row[3]), _db_time(row[4]), now))
        if (len(active) != 1 or active[0][1] != last.organization_id
                or not self._permitted(last, active[0][2], permission)
                or current_grants != scope.engagement_ids):
            raise PermissionError("Scoped access denied.")
        self._check_dependencies(scope.identity_source, scope.session_factory)

    def _project(self, kind, scope, *, session=None, item_id=None, parent_id=None,
                 limit=100, after_id=0, count=False):
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
            raise PermissionError("Scoped access denied.")
        stmt = stmt.where(v.organization_id == scope.identity.organization_id, e.id.in_(scope.engagement_ids))
        if item_id is not None:
            stmt = stmt.where(key == item_id)
        if parent_id is not None and parent_key is not None:
            stmt = stmt.where(parent_key == parent_id)
        if count:
            stmt = stmt.with_only_columns(func.count(key.distinct()))
        else:
            stmt = stmt.where(key > after_id).distinct().order_by(key).limit(limit)
        if session is None:
            with self._sessions() as database, database.no_autoflush:
                return self._project(kind, scope, session=database, item_id=item_id,
                                     parent_id=parent_id, limit=limit, after_id=after_id, count=count)
        result = session.execute(stmt)
        return result.scalar_one() if count else tuple(target(*row) for row in result.all())

    def _read(self, kind, *, item_id=None, parent_id=None, limit=100, after_id=0):
        if ((item_id is not None and not _positive_id(item_id))
                or (parent_id is not None and not _positive_id(parent_id))
                or type(limit) is not int or not 1 <= limit <= 200
                or type(after_id) is not int or after_id < 0):
            return ()
        permission = PERMISSION_EVIDENCE_READ if kind == "evidence" else PERMISSION_VENDOR_READ
        try:
            with self._authorized_transaction(permission) as (session, scope):
                rows = self._project(kind, scope, session=session, item_id=item_id,
                                     parent_id=parent_id, limit=limit, after_id=after_id)
                if rows != self._project(kind, scope, session=session, item_id=item_id,
                                         parent_id=parent_id, limit=limit, after_id=after_id):
                    raise PermissionError("Scoped access denied.")
                self._finish_authorized(session, scope, permission)
            return rows
        except Exception:
            return ()

    def list_vendors(self, *, limit=100, after_id=0):
        return self._read("vendor", limit=limit, after_id=after_id)

    def get_vendor(self, vendor_id):
        if not _positive_id(vendor_id):
            return None
        rows = self._read("vendor", item_id=vendor_id)
        return rows[0] if len(rows) == 1 else None

    def list_engagements(self, *, vendor_id=None, limit=100, after_id=0):
        return self._read("engagement", parent_id=vendor_id, limit=limit, after_id=after_id)

    def get_engagement(self, engagement_id):
        if not _positive_id(engagement_id):
            return None
        rows = self._read("engagement", item_id=engagement_id)
        return rows[0] if len(rows) == 1 else None

    def list_assessments(self, *, engagement_id=None, limit=100, after_id=0):
        return self._read("assessment", parent_id=engagement_id, limit=limit, after_id=after_id)

    def get_assessment(self, assessment_id):
        if not _positive_id(assessment_id):
            return None
        rows = self._read("assessment", item_id=assessment_id)
        return rows[0] if len(rows) == 1 else None

    def list_evidence(self, *, assessment_id=None, limit=100, after_id=0):
        return self._read("evidence", parent_id=assessment_id, limit=limit, after_id=after_id)

    def get_evidence(self, evidence_id):
        if not _positive_id(evidence_id):
            return None
        rows = self._read("evidence", item_id=evidence_id)
        return rows[0] if len(rows) == 1 else None

    def visible_counts(self):
        try:
            permissions = (PERMISSION_VENDOR_READ, PERMISSION_EVIDENCE_READ)
            with self._authorized_transaction(permissions) as (session, scope):
                counts = ScopedCounts(*(self._project(kind, scope, session=session, count=True)
                                        for kind in ("vendor", "engagement", "assessment", "evidence")))
                self._finish_authorized(session, scope, permissions)
            return counts
        except Exception:
            return ScopedCounts(0, 0, 0, 0)
