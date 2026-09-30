"""Add material change decision/action fields.

Revision ID: 0005_add_material_change_action_fields
Revises: 0004_add_finding_escalation
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_material_change"
down_revision = "0004_add_finding_escalation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table(
        "monitoring_events"
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "materiality",
                sa.String(40),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "decision_impact",
                sa.String(80),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "recommended_action",
                sa.String(80),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "affected_domain",
                sa.String(120),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "recommendation_rationale",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "recommendation_confidence",
                sa.String(40),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "analyst_action",
                sa.String(80),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "analyst_rationale",
                sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "analyst_followed_recommendation",
                sa.Boolean(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "acted_by",
                sa.String(255),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "acted_at",
                sa.DateTime(),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "monitoring_events"
    ) as batch_op:
        batch_op.drop_column("acted_at")
        batch_op.drop_column("acted_by")
        batch_op.drop_column(
            "analyst_followed_recommendation"
        )
        batch_op.drop_column(
            "analyst_rationale"
        )
        batch_op.drop_column(
            "analyst_action"
        )
        batch_op.drop_column(
            "recommendation_confidence"
        )
        batch_op.drop_column(
            "recommendation_rationale"
        )
        batch_op.drop_column(
            "affected_domain"
        )
        batch_op.drop_column(
            "recommended_action"
        )
        batch_op.drop_column(
            "decision_impact"
        )
        batch_op.drop_column(
            "materiality"
        )
