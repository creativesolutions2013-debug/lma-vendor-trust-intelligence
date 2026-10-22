"""Append-only note rationale history and immutable audit identity snapshots.

Adds an empty revision table and nullable audit columns. Existing annotations and
audit events remain untouched; no legacy author or tenant is guessed/backfilled.
"""
from alembic import context, op
import sqlalchemy as sa

from src.db import AnalystNoteRevision, install_note_revision_guards, note_revision_guard_statements


revision = "0015_analyst_note_revisions"
down_revision = "0014_organization_engagement_authorization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyst_note_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("engagement_id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("evidence_id", sa.Integer(), sa.ForeignKey("evidence.id", ondelete="RESTRICT")),
        sa.Column("object_type", sa.String(20), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("actor_issuer", sa.String(500)),
        sa.Column("actor_subject", sa.String(255)),
        sa.Column("actor_role", sa.String(80)),
        sa.Column("membership_id", sa.Integer()),
        sa.Column("session_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.CheckConstraint("organization_id > 0 AND vendor_id > 0 AND engagement_id > 0 AND assessment_id > 0 AND object_id > 0", name="ck_note_revision_positive_scope"),
        sa.CheckConstraint("(object_type = 'assessment' AND evidence_id IS NULL AND object_id = assessment_id) OR (object_type = 'evidence' AND evidence_id IS NOT NULL AND evidence_id > 0 AND object_id = evidence_id)", name="ck_note_revision_target"),
        sa.CheckConstraint("length(content) > 0", name="ck_note_revision_content"),
        sa.CheckConstraint("(origin = 'analyst' AND actor_issuer IS NOT NULL AND length(trim(actor_issuer)) > 0 AND actor_subject IS NOT NULL AND length(trim(actor_subject)) > 0 AND actor_role IS NOT NULL AND actor_role IN ('Admin', 'Risk Manager', 'Analyst', 'Viewer') AND membership_id IS NOT NULL AND membership_id > 0 AND session_id IS NOT NULL AND length(trim(session_id)) > 0) OR (origin = 'legacy_unknown' AND actor_issuer IS NULL AND actor_subject IS NULL AND actor_role IS NULL AND membership_id IS NULL AND session_id IS NULL)", name="ck_note_revision_attribution"),
    )
    op.create_index("ix_note_revision_scope_target", "analyst_note_revisions", ["organization_id", "object_type", "object_id", "id"])
    for name, data_type in (("actor_issuer", sa.String(500)), ("organization_id", sa.Integer()),
                            ("membership_id", sa.Integer()), ("session_id", sa.String(255))):
        op.add_column("audit_logs", sa.Column(name, data_type, nullable=True))
    if context.is_offline_mode():
        for statement in note_revision_guard_statements(op.get_bind().dialect):
            op.execute(statement)
    else:
        install_note_revision_guards(AnalystNoteRevision.__table__, op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Note history downgrade requires an independently reviewed data-retention and rollback plan; no history was removed.")
