"""Add approval decision table.

Revision ID: 0003_add_approval_decisions
Revises: 0002_add_audit_logs
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_approval_decisions"
down_revision = "0002_add_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_decisions",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column(
            "vendor_id",
            sa.Integer(),
            sa.ForeignKey("vendors.id"),
            nullable=False,
        ),
        sa.Column(
            "system_recommendation",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "system_reasons_json",
            sa.Text(),
        ),
        sa.Column(
            "evidence_completion_percent",
            sa.Float(),
        ),
        sa.Column(
            "residual_risk_score",
            sa.Float(),
        ),
        sa.Column(
            "decision",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "approver_subject",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "approver_name",
            sa.String(255),
        ),
        sa.Column(
            "approver_email",
            sa.String(255),
        ),
        sa.Column(
            "approver_role",
            sa.String(80),
        ),
        sa.Column(
            "rationale",
            sa.Text(),
        ),
        sa.Column(
            "conditions",
            sa.Text(),
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_approval_decisions_vendor_id",
        "approval_decisions",
        ["vendor_id"],
    )

    op.create_index(
        "ix_approval_decisions_decided_at",
        "approval_decisions",
        ["decided_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_approval_decisions_decided_at",
        table_name="approval_decisions",
    )

    op.drop_index(
        "ix_approval_decisions_vendor_id",
        table_name="approval_decisions",
    )

    op.drop_table("approval_decisions")
