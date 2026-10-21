"""Read-only organization/engagement resolver behind the M4B preflight.

The upstream identity source is a server-owned trust dependency, not credentials
or a browser-selected implementation. No production source or app registration
is provided. Each decision reads fresh scalar database columns; no byte access,
membership/grant provisioning, audit mutation or governed decision lives here.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select

from src.assessment_evidence_access import (
    AssessmentLink, AuthenticatedIdentity, EngagementLink, EvidenceLink,
    EvidenceReadGrant, EvidenceReadRequest, _current, _positive_id, _text,
)
from src.authz import PERMISSION_EVIDENCE_READ, Principal, VALID_ROLES, can
from src.db import (
    Assessment, Engagement, EngagementAccessGrant, Evidence, Organization,
    OrganizationMembership, Vendor,
)
from src.storage import validate_evidence_key


class TrustedIdentitySource(Protocol):
    """Future external, validated session adapter; DTO construction is not login."""
    def authenticated_identity(self) -> AuthenticatedIdentity | None: ...


def _utc_now():
    return datetime.now(timezone.utc)


def _database_time(value):
    # SQLite loses timezone metadata. All authorization timestamps are stored in
    # UTC; PostgreSQL timestamptz also returns aware values normalized here.
    if type(value) is not datetime:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _identity_context(identity):
    return (identity.issuer, identity.principal.subject, identity.audience, identity.session_id,
            identity.organization_id, identity.issued_at, identity.expires_at)


class DatabaseEvidenceAccessAuthority:
    """Server-injected fresh-session factory and already-verified identity source.

    The factory must supply a dedicated session, never a request's pending ORM
    work. Queries disable autoflush and project columns rather than using cached
    entity state. Identity, membership and entitlement are rechecked every call.
    This returns short-lived metadata, not a reusable capability to read bytes.
    """

    def __init__(self, session_factory, *, identity_source: TrustedIdentitySource | None = None):
        self._sessions = session_factory
        self._identity_source = identity_source

    def _upstream_identity(self, now):
        if self._identity_source is None or self._sessions is None:
            return None
        identity = self._identity_source.authenticated_identity()
        if (type(identity) is not AuthenticatedIdentity or type(identity.principal) is not Principal
                or not _positive_id(identity.organization_id)
                or not all(_text(x) for x in (identity.issuer, identity.principal.subject, identity.audience, identity.session_id))
                or not _current(identity.issued_at, identity.expires_at, now)):
            return None
        return identity

    @staticmethod
    def _membership(session, identity):
        m = OrganizationMembership
        rows = session.execute(select(
            m.id, m.role, m.status, m.valid_from, m.expires_at,
        ).join(Organization, Organization.id == m.organization_id).where(
            m.organization_id == identity.organization_id, m.issuer == identity.issuer,
            m.subject == identity.principal.subject,
        ).limit(2)).all()
        return rows[0] if len(rows) == 1 else None

    @staticmethod
    def _member_current(member, now):
        return (member is not None and member.status == "active" and member.role in VALID_ROLES
                and _current(_database_time(member.valid_from), _database_time(member.expires_at), now))

    def authenticated_identity(self):
        try:
            now = _utc_now()
            identity = self._upstream_identity(now)
            if identity is None:
                return None
            with self._sessions() as session, session.no_autoflush:
                member = self._membership(session, identity)
            if not self._member_current(member, now):
                return None
            # Ignore the incoming global role. Organization membership alone
            # supplies the effective role; it still cannot substitute for a grant.
            return replace(identity, principal=replace(identity.principal, role=member.role))
        except Exception:
            return None  # No provider/SQL error text or hidden-tenant metadata.

    def authorize_evidence_read(self, identity, request):
        try:
            now = _utc_now()
            current = self._upstream_identity(now)
            if (current is None or type(identity) is not AuthenticatedIdentity
                    or type(identity.principal) is not Principal
                    or _identity_context(identity) != _identity_context(current)
                    or type(request) is not EvidenceReadRequest
                    or not all(_positive_id(x) for x in (request.organization_id, request.engagement_id,
                                                        request.vendor_id, request.assessment_id, request.evidence_id))
                    or request.organization_id != current.organization_id):
                return None
            m, g = OrganizationMembership, EngagementAccessGrant
            with self._sessions() as session, session.no_autoflush:
                member = self._membership(session, current)
                if (not self._member_current(member, now) or member.role != identity.principal.role
                        or not can(replace(current.principal, role=member.role), PERMISSION_EVIDENCE_READ)):
                    return None
                # Equality on every parent link is intentional: one vendor's
                # grant never authorizes its sibling engagement or another tenant.
                # Raw columns and cardinality checks retain ambiguity instead of
                # ORM identity-map deduplication or an arbitrary first match.
                rows = session.execute(select(
                    m.id.label("membership_id"), m.role, m.status.label("membership_status"),
                    m.valid_from.label("membership_start"), m.expires_at.label("membership_end"),
                    g.id.label("grant_id"), g.status.label("grant_status"),
                    g.valid_from.label("grant_start"), g.expires_at.label("grant_end"),
                    Evidence.storage_path,
                ).select_from(m).join(Organization, Organization.id == m.organization_id)
                    .join(g, g.membership_id == m.id)
                    .join(Engagement, Engagement.id == g.engagement_id)
                    .join(Vendor, Vendor.id == Engagement.vendor_id)
                    .join(Assessment, Assessment.engagement_id == Engagement.id)
                    .join(Evidence, Evidence.assessment_id == Assessment.id)
                    .where(
                        m.id == member.id, m.organization_id == request.organization_id,
                        m.issuer == current.issuer, m.subject == current.principal.subject,
                        Vendor.organization_id == Organization.id, Vendor.id == request.vendor_id,
                        Engagement.id == request.engagement_id, Assessment.id == request.assessment_id,
                        Evidence.id == request.evidence_id, Assessment.vendor_id == Vendor.id,
                        Evidence.vendor_id == Vendor.id,
                    ).limit(2)).all()
            if len(rows) != 1:
                return None
            row = rows[0]
            if (row.membership_status != "active" or row.grant_status != "active"
                    or row.role != identity.principal.role or row.role not in VALID_ROLES
                    or not can(replace(current.principal, role=row.role), PERMISSION_EVIDENCE_READ)
                    or not _current(_database_time(row.membership_start), _database_time(row.membership_end), now)
                    or not _current(_database_time(row.grant_start), _database_time(row.grant_end), now)):
                return None
            key = validate_evidence_key(row.storage_path, vendor_id=request.vendor_id)
            expiry = min(current.expires_at, _database_time(row.membership_end),
                         _database_time(row.grant_end), now + timedelta(minutes=1))
            return EvidenceReadGrant(
                "m4c-" + uuid4().hex, current.principal.subject, current.issuer, current.audience,
                current.session_id, request.organization_id, request.engagement_id, request.vendor_id,
                request.assessment_id, request.evidence_id, now, expiry,
                (EngagementLink(request.engagement_id, request.vendor_id, request.organization_id),),
                (AssessmentLink(request.assessment_id, request.vendor_id, request.engagement_id, request.organization_id),),
                (EvidenceLink(request.evidence_id, request.vendor_id, request.assessment_id, request.engagement_id,
                              request.organization_id, key),),
            )
        except Exception:
            return None
