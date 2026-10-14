"""Add residual-risk revalidation case records."""

from alembic import op
import sqlalchemy as sa


revision = "0013_revalidation_case_records"
down_revision = "0012_control_disposition_claim_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revalidation_case_records",
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
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("assessments.id"),
            nullable=False,
        ),
        sa.Column(
            "activation_execution_id",
            sa.Integer(),
            sa.ForeignKey(
                "residual_risk_activation_executions.id"
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "status",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "trigger_status",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "trigger_reasons_json",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "activated_residual_risk",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "current_authoritative_risk",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "decision_coverage_percent",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "control_effectiveness_status",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "rav_policy_version",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "revalidation_policy_version",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "opened_by_subject",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "opened_by_name",
            sa.String(255),
        ),
        sa.Column(
            "opened_by_email",
            sa.String(255),
        ),
        sa.Column(
            "opened_by_role",
            sa.String(80),
        ),
        sa.Column(
            "opening_rationale",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_revalidation_case_vendor",
        "revalidation_case_records",
        ["vendor_id"],
    )

    op.create_index(
        "ix_revalidation_case_assessment",
        "revalidation_case_records",
        ["assessment_id"],
    )

    op.create_index(
        "ix_revalidation_case_status",
        "revalidation_case_records",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_revalidation_case_status",
        table_name="revalidation_case_records",
    )

    op.drop_index(
        "ix_revalidation_case_assessment",
        table_name="revalidation_case_records",
    )

    op.drop_index(
        "ix_revalidation_case_vendor",
        table_name="revalidation_case_records",
    )

    op.drop_table(
        "revalidation_case_records"
    )
