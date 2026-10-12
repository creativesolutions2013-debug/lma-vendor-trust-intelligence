"""Add claim-backed control disposition enforcement metadata."""

from alembic import op
import sqlalchemy as sa


revision = "0012_control_disposition_claim_basis"
down_revision = "0011_residual_risk_activation_executions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "control_disposition_records",
        sa.Column(
            "claim_basis_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "control_disposition_records",
        sa.Column(
            "claim_basis_mode",
            sa.String(40),
            nullable=False,
            server_default="LEGACY_UNVERIFIED",
        ),
    )

    op.add_column(
        "control_disposition_records",
        sa.Column(
            "claim_basis_record_ids_json",
            sa.Text(),
        ),
    )

    op.add_column(
        "control_disposition_records",
        sa.Column(
            "claim_basis_evidence_ids_json",
            sa.Text(),
        ),
    )

    op.add_column(
        "control_disposition_records",
        sa.Column(
            "claim_basis_override_reason",
            sa.Text(),
        ),
    )

    op.add_column(
        "control_disposition_records",
        sa.Column(
            "claim_basis_policy_version",
            sa.String(40),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "control_disposition_records",
        "claim_basis_policy_version",
    )

    op.drop_column(
        "control_disposition_records",
        "claim_basis_override_reason",
    )

    op.drop_column(
        "control_disposition_records",
        "claim_basis_evidence_ids_json",
    )

    op.drop_column(
        "control_disposition_records",
        "claim_basis_record_ids_json",
    )

    op.drop_column(
        "control_disposition_records",
        "claim_basis_mode",
    )

    op.drop_column(
        "control_disposition_records",
        "claim_basis_verified",
    )
