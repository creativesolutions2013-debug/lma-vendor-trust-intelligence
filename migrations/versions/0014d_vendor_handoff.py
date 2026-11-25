"""Add empty immutable synthetic vendor-delivery provenance; no custody rewrite."""
from alembic import context, op
import sqlalchemy as sa

from src.synthetic_handoff_provenance import (
    MAX_HANDOFF_METADATA_BYTES, install_synthetic_handoff_guards,
    synthetic_handoff_guard_statements,
)

revision = "0014d_vendor_handoff"
down_revision = "0014c_assessment_revisions"
branch_labels = None
depends_on = None


def upgrade():
    if context.is_offline_mode() and op.get_bind().dialect.name == "postgresql":
        raise RuntimeError("Synthetic handoff PostgreSQL migration requires online schema verification; no handoff DDL was emitted.")
    table = op.create_table(
        "synthetic_vendor_handoffs",
        sa.Column("evidence_id", sa.Integer(), sa.ForeignKey("synthetic_evidence_objects.evidence_id", ondelete="RESTRICT"), primary_key=True, autoincrement=False),
        *(sa.Column(name, sa.Integer(), nullable=False) for name in ("organization_id", "vendor_id", "engagement_id", "assessment_id")),
        sa.Column("generation", sa.String(32), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata_payload", sa.LargeBinary(), nullable=False),
        sa.Column("metadata_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("evidence_id > 0 AND organization_id > 0 AND vendor_id > 0 AND engagement_id > 0 AND assessment_id > 0", name="ck_synthetic_handoff_positive_ids"),
        sa.CheckConstraint(f"length(metadata_payload) BETWEEN 1 AND {MAX_HANDOFF_METADATA_BYTES}", name="ck_synthetic_handoff_size"),
        sa.CheckConstraint("length(generation) = 32 AND length(sha256) = 64 AND length(metadata_sha256) = 64", name="ck_synthetic_handoff_hash_shape"),
        sqlite_with_rowid=False,
    )
    if context.is_offline_mode():
        for statement in synthetic_handoff_guard_statements(op.get_bind().dialect):
            op.execute(statement)
    else:
        install_synthetic_handoff_guards(table, op.get_bind())


def downgrade():
    raise RuntimeError("Synthetic handoff downgrade requires an independently reviewed retention and rollback plan; no data was removed.")
