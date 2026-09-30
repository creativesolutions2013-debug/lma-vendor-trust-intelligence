"""Add targeted review scope snapshot fields.

Revision ID: 0006_add_targeted_scope_snapshot
Revises: 0005_add_material_change_action_fields
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_targeted_scope_snapshot"
down_revision = "0005_add_material_change_action_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table(
        "assessments"
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "proposed_scope_json",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "approved_scope_json",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "scope_override_rationale",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "scope_confirmed_by",
                sa.String(255),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "scope_confirmed_at",
                sa.DateTime(),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "assessments"
    ) as batch_op:
        batch_op.drop_column(
            "scope_confirmed_at"
        )
        batch_op.drop_column(
            "scope_confirmed_by"
        )
        batch_op.drop_column(
            "scope_override_rationale"
        )
        batch_op.drop_column(
            "approved_scope_json"
        )
        batch_op.drop_column(
            "proposed_scope_json"
        )
