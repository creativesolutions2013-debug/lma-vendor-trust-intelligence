"""Add empty append-only synthetic assessment revisions; no legacy state import."""
from alembic import context, op
import sqlalchemy as sa

from src.synthetic_revision_guards import (
    MAX_SYNTHETIC_ASSESSMENT_STATE_BYTES, install_synthetic_revision_guards,
    synthetic_revision_guard_statements,
)


revision = "0014c_assessment_revisions"
down_revision = "0014b_synthetic_custody"
branch_labels = None
depends_on = None


def upgrade():
    if context.is_offline_mode() and op.get_bind().dialect.name == "postgresql":
        raise RuntimeError("Synthetic revision PostgreSQL migration requires online schema verification; no revision DDL was emitted.")
    table = op.create_table(
        "synthetic_assessment_revisions",
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        *(sa.Column(name, sa.Integer(), sa.ForeignKey(parent + ".id", ondelete="RESTRICT"), nullable=False)
          for name, parent in (("organization_id", "organizations"), ("vendor_id", "vendors"),
                               ("engagement_id", "engagements"))),
        sa.Column("anchor_evidence_id", sa.Integer(), sa.ForeignKey("synthetic_evidence_objects.evidence_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("state_payload", sa.LargeBinary(), nullable=False),
        sa.Column("state_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(80), nullable=False),
        sa.Column("effective_role", sa.String(80), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("assessment_id > 0 AND revision > 0 AND organization_id > 0 AND vendor_id > 0 AND engagement_id > 0 AND anchor_evidence_id > 0 AND membership_id > 0", name="ck_synthetic_revision_positive_ids"),
        sa.CheckConstraint(f"length(state_payload) BETWEEN 1 AND {MAX_SYNTHETIC_ASSESSMENT_STATE_BYTES}", name="ck_synthetic_revision_size"),
        sa.CheckConstraint("length(state_sha256) = 64", name="ck_synthetic_revision_hash_shape"),
        sa.CheckConstraint("length(trim(issuer)) BETWEEN 1 AND 500 AND length(trim(subject)) BETWEEN 1 AND 255 AND length(trim(session_id)) BETWEEN 1 AND 80", name="ck_synthetic_revision_provenance"),
        sa.CheckConstraint("effective_role IN ('Admin', 'Risk Manager', 'Analyst', 'Viewer')", name="ck_synthetic_revision_role"),
        sqlite_with_rowid=False,
    )
    if context.is_offline_mode():
        for statement in synthetic_revision_guard_statements(op.get_bind().dialect):
            op.execute(statement)
    else:
        install_synthetic_revision_guards(table, op.get_bind())


def downgrade():
    raise RuntimeError("Synthetic revision downgrade requires an independently reviewed retention and rollback plan; no data was removed.")
