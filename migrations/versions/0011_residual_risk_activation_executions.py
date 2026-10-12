"""Add residual risk activation executions."""

from alembic import op
import sqlalchemy as sa


revision = "0011_residual_risk_activation_executions"
down_revision = "0010_residual_risk_activation_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "residual_risk_activation_executions",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column(
            "activation_review_id",
            sa.Integer(),
            sa.ForeignKey(
                "residual_risk_activation_records.id"
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "vendor_id",
            sa.Integer(),
            sa.ForeignKey("vendors.id"),
            nullable=False,
        ),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("assessments.id"),
            nullable=False,
        ),
        sa.Column(
            "previous_residual_risk",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "activated_residual_risk",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "previous_risk_rating",
            sa.String(40),
        ),
        sa.Column(
            "activated_risk_rating",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "executor_subject",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "executor_name",
            sa.String(255),
        ),
        sa.Column(
            "executor_email",
            sa.String(255),
        ),
        sa.Column(
            "executor_role",
            sa.String(80),
        ),
        sa.Column(
            "execution_rationale",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "execution_policy_version",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "activation_policy_version",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "reconciliation_policy_version",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "residual_risk_policy_version",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_residual_execution_vendor",
        "residual_risk_activation_executions",
        ["vendor_id"],
    )

    op.create_index(
        "ix_residual_execution_assessment",
        "residual_risk_activation_executions",
        ["assessment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_residual_execution_assessment",
        table_name=(
            "residual_risk_activation_executions"
        ),
    )

    op.drop_index(
        "ix_residual_execution_vendor",
        table_name=(
            "residual_risk_activation_executions"
        ),
    )

    op.drop_table(
        "residual_risk_activation_executions"
    )
