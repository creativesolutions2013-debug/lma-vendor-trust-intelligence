"""Add finding escalation fields.

Revision ID: 0004_add_finding_escalation
Revises: 0003_add_approval_decisions
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_finding_escalation"
down_revision = "0003_add_approval_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("findings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "escalation_status",
                sa.String(50),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "escalation_note",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "escalated_by",
                sa.String(255),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "escalated_at",
                sa.DateTime(),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_column("escalated_at")
        batch_op.drop_column("escalated_by")
        batch_op.drop_column("escalation_note")
        batch_op.drop_column("escalation_status")
