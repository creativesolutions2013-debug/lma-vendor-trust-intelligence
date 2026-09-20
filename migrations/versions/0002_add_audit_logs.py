"""Add audit log table.

Revision ID: 0002_add_audit_logs
Revises: 0001_baseline
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_audit_logs"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("actor_name", sa.String(255)),
        sa.Column("actor_email", sa.String(255)),
        sa.Column("actor_role", sa.String(80)),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("object_type", sa.String(120), nullable=False),
        sa.Column("object_id", sa.String(120)),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id")),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("details_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_vendor_id", "audit_logs", ["vendor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_vendor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
