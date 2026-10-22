"""Unwired M4C-1 adapter: current server session plus unambiguous DB membership.

No browser organization selector is accepted. This bounded slice denies accounts
with multiple current memberships pending a separately reviewed server selection
flow. The database evidence authority still supplies effective roles and grants.
"""
from sqlalchemy import select

from src.assessment_evidence_access import AuthenticatedIdentity, _current, _positive_id
from src.authz import Principal, ROLE_VIEWER, VALID_ROLES
from src.database_evidence_authority import _database_time
from src.db import Organization, OrganizationMembership
from src.server_sessions import SessionManager, ServerSession, utc_now


class SessionIdentitySource:
    """Server-injected session handle and dedicated session factory, never DTO authority."""
    def __init__(self, sessions: SessionManager, handle: str, session_factory, *, clock=utc_now):
        self._sessions, self._handle = sessions, handle
        self._database_sessions, self._clock = session_factory, clock

    def authenticated_identity(self):
        try:
            session = self._sessions.authenticate(self._handle)
            if type(session) is not ServerSession or self._database_sessions is None:
                return None
            now = self._clock()
            m = OrganizationMembership
            with self._database_sessions() as database, database.no_autoflush:
                rows = database.execute(select(
                    m.organization_id, m.role, m.valid_from, m.expires_at,
                ).join(Organization, Organization.id == m.organization_id).where(
                    m.issuer == session.issuer, m.subject == session.subject, m.status == "active",
                    m.valid_from <= now, m.expires_at > now,
                ).limit(2)).all()
            # Re-read the server session after DB work, preserving its stable
            # absolute timestamps while independently enforcing idle expiry.
            current = self._sessions.authenticate(self._handle)
            now = self._clock()
            if len(rows) != 1 or current != session:
                return None
            row = rows[0]
            if (not _positive_id(row.organization_id) or row.role not in VALID_ROLES
                    or not _current(_database_time(row.valid_from), _database_time(row.expires_at), now)
                    or not _current(session.issued_at, session.expires_at, now)):
                return None
            return AuthenticatedIdentity(
                Principal(session.subject, "Verified account", "", ROLE_VIEWER),
                session.issuer, session.audience, session.session_id, row.organization_id,
                session.issued_at, session.expires_at,
            )
        except Exception:
            return None  # No handles, provider errors or hidden membership metadata.
