"""Add residual risk activation review records."""

from alembic import op
import sqlalchemy as sa


revision = "0010_residual_risk_activation_records"
down_revision = "0009_control_claim_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic defaults version_num to VARCHAR(32). Revision IDs from
    # 0010 onward exceed that length, so widen the column on PostgreSQL
    # before Alembic records this revision.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(255)"
        )

    op.create_table(
        "residual_risk_activation_records",
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
            "stored_residual_risk",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "fresh_baseline_risk",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "proposed_residual_risk",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "stored_to_baseline_delta",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "governed_contribution_delta",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "stored_to_governed_delta",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "governed_rating",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "control_input_mode",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "decision_status",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "system_ready",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "analyst_approved",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "activation_eligible",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "blocking_reasons_json",
            sa.Text(),
        ),
        sa.Column(
            "analyst_subject",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "analyst_name",
            sa.String(255),
        ),
        sa.Column(
            "analyst_email",
            sa.String(255),
        ),
        sa.Column(
            "analyst_role",
            sa.String(80),
        ),
        sa.Column(
            "rationale",
            sa.Text(),
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
            "reviewed_at",
            sa.DateTime(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_residual_activation_vendor",
        "residual_risk_activation_records",
        ["vendor_id"],
    )

    op.create_index(
        "ix_residual_activation_assessment",
        "residual_risk_activation_records",
        ["assessment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_residual_activation_assessment",
        table_name="residual_risk_activation_records",
    )

    op.drop_index(
        "ix_residual_activation_vendor",
        table_name="residual_risk_activation_records",
    )

    op.drop_table(
        "residual_risk_activation_records"
    )
