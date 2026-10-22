"""Unwired, scoped analyst notes with append-only history and atomic audit.

These optional annotations never approve controls or change risk/status/source
fields. Reuse the read/export transaction's lock order and issuance boundary;
production authentication and legacy Streamlit routes remain disabled.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, select, update

from src.assessment_evidence_access import _current, _positive_id
from src.authz import PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_ANALYZE
from src.db import (
    AnalystNoteRevision, Assessment, AuditLog, Engagement, EngagementAccessGrant,
    Evidence, Vendor,
)
from src.tenant_read_scope import TenantReadService, _db_time, _utc_now


def _valid_note(note):
    return (type(note) is str and 1 <= len(note) <= 1200
            and note == note.strip()
            and all(char in "\n\t" or ord(char) >= 32 for char in note)
            and not any(ord(char) == 127 for char in note))


@dataclass(frozen=True)
class NoteRevisionSummary:
    id: int
    organization_id: int
    vendor_id: int
    engagement_id: int
    assessment_id: int
    evidence_id: int | None
    object_type: str
    object_id: int
    actor_issuer: str | None
    actor_subject: str | None
    actor_role: str | None
    membership_id: int | None
    session_id: str | None  # Correlation identifier, never a bearer handle.
    created_at: datetime
    content: str
    origin: str


class TenantAssessmentEvidenceOperations:
    """Server-only note writes and exact-target history reads.

    True/False means committed/not committed. History returns bounded immutable
    projections; nonexistent and forbidden targets look alike. Dependencies are
    trusted server wiring, never request-selected credentials or organizations.
    """

    def __init__(self, session_factory, *, identity_source=None):
        self._sessions, self._source = session_factory, identity_source
        self._reader = TenantReadService(session_factory, identity_source=identity_source)

    @staticmethod
    def _permission(kind):
        return PERMISSION_ASSESSMENT_MANAGE if kind == "assessment" else PERMISSION_EVIDENCE_ANALYZE

    def _target(self, session, kind, target_id, organization_id, *, engagement_ids):
        a, e, v, d = Assessment, Engagement, Vendor, Evidence
        if kind == "assessment":
            query = select(
                a.id.label("object_id"), a.vendor_id, a.engagement_id,
                a.id.label("assessment_id"), a.notes.label("note"),
            ).select_from(a).join(
                e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id)
            ).join(v, v.id == e.vendor_id).where(
                a.id == target_id, v.organization_id == organization_id,
                e.id.in_(engagement_ids),
            ).with_for_update(of=a)
        else:
            query = select(
                d.id.label("object_id"), a.vendor_id, a.engagement_id,
                a.id.label("assessment_id"), d.analyst_notes.label("note"),
            ).select_from(d).join(
                a, and_(a.id == d.assessment_id, a.vendor_id == d.vendor_id)
            ).join(e, and_(e.id == a.engagement_id, e.vendor_id == a.vendor_id)
            ).join(v, v.id == e.vendor_id).where(
                d.id == target_id, v.organization_id == organization_id,
                e.id.in_(engagement_ids),
            ).with_for_update(of=d)
        matches = session.execute(query).all()
        return matches[0] if len(matches) == 1 else None

    def _grant(self, session, member_id, engagement_id, now):
        # The shared transaction has already locked all membership grants before
        # any parent. This exact-target check never introduces another lock order.
        g = EngagementAccessGrant
        rows = session.execute(select(
            g.id, g.status, g.valid_from, g.expires_at,
        ).where(g.membership_id == member_id, g.engagement_id == engagement_id)).all()
        if (len(rows) != 1 or rows[0].status != "active"
                or not _current(_db_time(rows[0].valid_from), _db_time(rows[0].expires_at), now)):
            return None
        return rows[0]

    def _context(self, session, scope, kind, target_id):
        identity = scope.identity
        now = _utc_now()
        current_members = [row for row in scope.authority[0]
                           if row[1] == identity.organization_id and row[2] == scope.role
                           and row[3] == "active" and _current(_db_time(row[4]), _db_time(row[5]), now)]
        if len(current_members) != 1:
            raise PermissionError("Scoped access denied.")
        target = self._target(session, kind, target_id, identity.organization_id,
                              engagement_ids=scope.engagement_ids)
        member_id = current_members[0][0]
        if (target is None or target.engagement_id not in scope.engagement_ids
                or self._grant(session, member_id, target.engagement_id, _utc_now()) is None):
            raise PermissionError("Scoped access denied.")
        context = dict(
            organization_id=identity.organization_id, vendor_id=target.vendor_id,
            engagement_id=target.engagement_id, assessment_id=target.assessment_id,
            evidence_id=target_id if kind == "evidence" else None,
            object_type=kind, object_id=target_id,
        )
        return target, member_id, context

    @staticmethod
    def _preserve_legacy(session, target, context, now):
        if target.note is None or target.note == "":
            return
        if type(target.note) is not str:
            raise PermissionError("Scoped access denied.")
        r = AnalystNoteRevision
        latest = session.execute(select(r).where(
            r.object_type == context["object_type"], r.object_id == context["object_id"],
        ).order_by(r.id.desc()).limit(1)).scalar_one_or_none()
        if latest is not None and latest.content == target.note:
            return  # Already retained, including an earlier tenant's revision.
        if latest is not None and any(getattr(latest, key) != value for key, value in context.items()):
            # Never relabel untracked old text as the new tenant/engagement's
            # rationale after a relationship move. An owner must reconcile it.
            raise PermissionError("Scoped access denied.")
        session.add(r(**context, content=target.note, origin="legacy_unknown", created_at=now))

    def _record(self, kind, target_id, note):
        if kind not in ("assessment", "evidence") or not _positive_id(target_id) or not _valid_note(note):
            return False
        permission = self._permission(kind)
        model = Assessment if kind == "assessment" else Evidence
        field = Assessment.notes if kind == "assessment" else Evidence.analyst_notes
        try:
            with self._reader._authorized_transaction(permission) as (session, scope):
                target, member_id, context = self._context(session, scope, kind, target_id)
                identity, now = scope.identity, _utc_now()
                self._preserve_legacy(session, target, context, now)
                session.add(AnalystNoteRevision(
                    **context, content=note, origin="analyst", created_at=now,
                    actor_issuer=identity.issuer, actor_subject=identity.principal.subject,
                    actor_role=scope.role, membership_id=member_id, session_id=identity.session_id,
                ))
                changed = session.execute(update(model).where(model.id == target_id).values({field: note}))
                if changed.rowcount != 1:
                    raise PermissionError("Scoped access denied.")
                session.add(AuditLog(
                    actor_subject=identity.principal.subject, actor_role=scope.role,
                    actor_issuer=identity.issuer, organization_id=identity.organization_id,
                    membership_id=member_id, session_id=identity.session_id,
                    action=kind + ".review_note_updated", object_type=kind,
                    object_id=str(target_id), vendor_id=target.vendor_id,
                    outcome="success", created_at=now,
                    # Never copy note text or historical rationale into audit.
                ))
                session.flush()
                self._reader._finish_authorized(session, scope, permission)
            return True
        except Exception:
            # Exceptions roll back current note, revisions AND audit together.
            return False

    def _history(self, kind, target_id, *, limit=100, after_id=0):
        if (kind not in ("assessment", "evidence") or not _positive_id(target_id)
                or type(limit) is not int or not 1 <= limit <= 200
                or type(after_id) is not int or after_id < 0):
            return ()
        permission = self._permission(kind)
        try:
            with self._reader._authorized_transaction(permission) as (session, scope):
                _, _, context = self._context(session, scope, kind, target_id)
                r = AnalystNoteRevision
                query = select(r).where(r.id > after_id, *(getattr(r, key) == value for key, value in context.items()))
                records = session.execute(query.order_by(r.id).limit(limit)).scalars().all()
                result = tuple(NoteRevisionSummary(
                    **{name: (_db_time(row.created_at) if name == "created_at" else getattr(row, name))
                       for name in NoteRevisionSummary.__dataclass_fields__}
                ) for row in records)
                self._reader._finish_authorized(session, scope, permission)
            return result
        except Exception:
            return ()

    def record_assessment_review_note(self, assessment_id, note):
        return self._record("assessment", assessment_id, note)

    def record_evidence_review_note(self, evidence_id, note):
        return self._record("evidence", evidence_id, note)

    def list_assessment_note_revisions(self, assessment_id, *, limit=100, after_id=0):
        return self._history("assessment", assessment_id, limit=limit, after_id=after_id)

    def list_evidence_note_revisions(self, evidence_id, *, limit=100, after_id=0):
        return self._history("evidence", evidence_id, limit=limit, after_id=after_id)
