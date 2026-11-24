"""Add an empty, immutable synthetic SQL byte store; no legacy custody backfill."""
from alembic import context, op
import sqlalchemy as sa

from src.synthetic_custody_guards import (
    MAX_SYNTHETIC_EVIDENCE_BYTES, install_synthetic_custody_guards,
    synthetic_custody_guard_statements,
)


revision = "0014b_synthetic_custody"
down_revision = "0014a_membership_identity_guard"
branch_labels = None
depends_on = None


def upgrade():
    if context.is_offline_mode() and op.get_bind().dialect.name == "postgresql":
        # Guard functions fully qualify their application relations. An offline
        # script cannot verify the actual target schema; never assume public.
        raise RuntimeError("Synthetic custody PostgreSQL migration requires online schema verification; no custody DDL was emitted.")
    table = op.create_table(
        "synthetic_evidence_objects",
        sa.Column("evidence_id", sa.Integer(), sa.ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True),
        *(sa.Column(name, sa.Integer(), sa.ForeignKey(parent + ".id", ondelete="RESTRICT"), nullable=False)
          for name, parent in (("organization_id", "organizations"), ("vendor_id", "vendors"),
                               ("engagement_id", "engagements"), ("assessment_id", "assessments"))),
        sa.Column("generation", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("document_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(80), nullable=False),
        sa.Column("effective_role", sa.String(80), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("generation", name="uq_synthetic_custody_generation"),
        sa.UniqueConstraint("storage_key", name="uq_synthetic_custody_key"),
        sa.CheckConstraint("evidence_id > 0 AND organization_id > 0 AND vendor_id > 0 AND engagement_id > 0 AND assessment_id > 0 AND membership_id > 0", name="ck_synthetic_custody_positive_ids"),
        sa.CheckConstraint(f"byte_length BETWEEN 1 AND {MAX_SYNTHETIC_EVIDENCE_BYTES} AND length(payload) = byte_length", name="ck_synthetic_custody_bytes"),
        sa.CheckConstraint("length(generation) = 32 AND length(sha256) = 64", name="ck_synthetic_custody_hash_shape"),
        sa.CheckConstraint("length(storage_key) BETWEEN 1 AND 500 AND length(document_name) BETWEEN 1 AND 255", name="ck_synthetic_custody_names"),
        sa.CheckConstraint("length(trim(issuer)) BETWEEN 1 AND 500 AND length(trim(subject)) BETWEEN 1 AND 255 AND length(trim(session_id)) BETWEEN 1 AND 80", name="ck_synthetic_custody_provenance"),
        sa.CheckConstraint("effective_role IN ('Admin', 'Risk Manager', 'Analyst', 'Viewer')", name="ck_synthetic_custody_role"),
    )
    if context.is_offline_mode():
        for statement in synthetic_custody_guard_statements(op.get_bind().dialect):
            op.execute(statement)
    else:
        install_synthetic_custody_guards(table, op.get_bind())


def downgrade():
    raise RuntimeError("Synthetic custody downgrade requires an independently reviewed retention and rollback plan; no data was removed.")
