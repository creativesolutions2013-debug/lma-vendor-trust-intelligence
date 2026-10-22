"""M4C-2B-2B: unwired, audited, engagement-bound analyst note changes.

Optional notes are *not* governed control acceptance, approval, risk scoring,
assessment status, evidence custody, or file operation. Never register this
with development principals, Streamlit selectors or an unverified browser
identity. Live production auth remains disabled.

A dedicated transaction locks authorization rows and the exact target during
the write (PostgreSQL FOR UPDATE). SQLite fixtures are synthetic only.
"""
from sqlalchemy import and_, select, update

from src.assessment_evidence_access import (
    AuthenticatedIdentity, _current, _positive_id, _text,
)
from src.authz import (
    Principal, VALID_ROLES, can, PERMISSION_ASSESSMENT_MANAGE,
    PERMISSION_EVIDENCE_ANALYZE,
)
from src.db import (
    Assessment, AuditLog, Engagement, EngagementAccessGrant, Evidence,
    Organization, OrganizationMembership, Vendor,
)
from src.tenant_read_scope import _db_time, _session_identity_key, _utc_now


def _valid_note(note):
    return (type(note) is str and 1 <= len(note) <= 1200
            and note == note.strip()
            and all(char in "\n\t" or ord(char) >= 32 for char in note)
            and not any(ord(char) == 127 for char in note))


def _valid_identity(value, now):
    return (type(value) is AuthenticatedIdentity
            and type(value.principal) is Principal
            and _positive_id(value.organization_id)
            and all(_text(x) for x in (
                value.issuer, value.principal.subject, value.audience,
                value.session_id,
            ))
            and _current(value.issued_at, value.expires_at, now))


class TenantAssessmentEvidenceOperations:
    """Write-only review notes with one transaction and authorization audit.

    No entity instance or audit detail is released to the caller: True/False
    means committed/not committed; a nonexistent and forbidden ID look alike.
    Upstream identity source and session factory are trusted server dependencies.
    """

    def __init__(self, session_factory, *, identity_source=None):
        self._sessions = session_factory
        self._source = identity_source

    def _target(self, session, kind, target_id, organization_id):
        a, e, v, d = Assessment, Engagement, Vendor, Evidence
        if kind == "assessment":
            query = select(a.id, a.vendor_id, a.engagement_id).select_from(a).join(
                e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id)
            ).join(v, v.id == e.vendor_id).where(
                a.id == target_id, v.organization_id == organization_id,
            ).with_for_update()
        else:
            query = select(d.id, a.vendor_id, a.engagement_id).select_from(d).join(
                a, and_(a.id == d.assessment_id, a.vendor_id == d.vendor_id)
            ).join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id)
            ).join(v, v.id == e.vendor_id).where(
                d.id == target_id, v.organization_id == organization_id,
            ).with_for_update()
        matches = session.execute(query).all()
        return matches[0] if len(matches) == 1 else None

    def _membership(self, session, identity, permission, now):
        m = OrganizationMembership
        matches = session.execute(
            select(m.id, m.organization_id, m.role, m.status,
                   m.valid_from, m.expires_at)
            .join(Organization, Organization.id == m.organization_id)
            .where(m.issuer == identity.issuer, m.subject == identity.principal.subject)
            .with_for_update()
        ).all()
        current = [x for x in matches if x.status == "active" and
                   _current(_db_time(x.valid_from), _db_time(x.expires_at), now)]
        if len(current) != 1:
            return None
        member = current[0]
        if (member.organization_id != identity.organization_id
                or member.role not in VALID_ROLES
                or not can(Principal(identity.principal.subject,
                                     identity.principal.display_name,
                                     identity.principal.email, member.role), permission)):
            return None
        return member

    def _grant(self, session, member_id, engagement_id, now):
        g = EngagementAccessGrant
        rows = session.execute(select(
            g.id, g.status, g.valid_from, g.expires_at,
        ).where(g.membership_id == member_id,
                g.engagement_id == engagement_id).with_for_update()).all()
        if len(rows) != 1 or rows[0].status != "active":
            return None
        row = rows[0]
        if not _current(_db_time(row.valid_from), _db_time(row.expires_at), now):
            return None
        return row

    def _record(self, kind, target_id, note):
        if (not _positive_id(target_id) or not _valid_note(note)
                or self._sessions is None or self._source is None):
            return False
        permission = (PERMISSION_ASSESSMENT_MANAGE if kind == "assessment"
                      else PERMISSION_EVIDENCE_ANALYZE)
        model = Assessment if kind == "assessment" else Evidence
        field = Assessment.notes if kind == "assessment" else Evidence.analyst_notes
        try:
            start = _utc_now()
            identity = self._source.authenticated_identity()
            if not _valid_identity(identity, start):
                return False
            # NEVER inherit a possibly dirty Streamlit/global ORM session.
            # PostgreSQL write locks prevent concurrent grant/membership/target
            # changes until commit. SQLite tests cannot prove that behavior.
            with self._sessions() as session:
                with session.begin(), session.no_autoflush:
                    member = self._membership(session, identity, permission, _utc_now())
                    if member is None:
                        return False
                    target = self._target(session, kind, target_id, identity.organization_id)
                    if target is None or not _positive_id(target.engagement_id):
                        return False
                    grant = self._grant(session, member.id, target.engagement_id, _utc_now())
                    if grant is None:
                        return False
                    end = _utc_now()
                    current = self._source.authenticated_identity()
                    if (not _valid_identity(current, end)
                            or _session_identity_key(identity) != _session_identity_key(current)
                            or not _current(_db_time(member.valid_from),
                                            _db_time(member.expires_at), end)
                            or not _current(_db_time(grant.valid_from),
                                            _db_time(grant.expires_at), end)):
                        return False

                    # These are the ONLY permitted source mutations. No status,
                    # scopes, approvals, scores, evidence paths or AI findings.
                    changed = session.execute(
                        update(model).where(model.id == target_id).values({field: note})
                    )
                    if changed.rowcount != 1:
                        return False
                    session.add(AuditLog(
                        actor_subject=identity.principal.subject,
                        actor_role=member.role,
                        action=kind + ".review_note_updated",
                        object_type=kind,
                        object_id=str(target_id),
                        vendor_id=target.vendor_id,
                        outcome="success",
                        # Avoid copying note contents/PII into broad audit logs.
                    ))
                    session.flush()
                    # These are fresh SQL reads inside the same locked
                    # transaction. Never rely only on pre-write snapshots.
                    final_member = self._membership(session, identity, permission, _utc_now())
                    final_target = self._target(
                        session, kind, target_id, identity.organization_id,
                    )
                    final_grant = self._grant(session, member.id, target.engagement_id, _utc_now())
                    final = _utc_now()
                    current = self._source.authenticated_identity()
                    if (final_member != member or final_target != target
                            or final_grant != grant
                            or not _valid_identity(current, final)
                            or _session_identity_key(current) != _session_identity_key(identity)
                            or not _current(_db_time(member.valid_from),
                                            _db_time(member.expires_at), final)
                            or not _current(_db_time(grant.valid_from),
                                            _db_time(grant.expires_at), final)):
                        # Returning from a managed transaction commits! Explicit
                        # rollback makes audit and review note atomic on denial.
                        session.rollback()
                        return False
                return True
        except Exception:
            # Session context rolls back on SQL errors. Hide existence and
            # backend/provider diagnostics from the untrusted caller.
            return False

    def record_assessment_review_note(self, assessment_id, note):
        return self._record("assessment", assessment_id, note)

    def record_evidence_review_note(self, evidence_id, note):
        return self._record("evidence", evidence_id, note)
