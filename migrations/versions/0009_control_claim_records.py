"""Add persistent governed control claims."""

from alembic import op
import sqlalchemy as sa


revision = "0009_control_claim_records"
down_revision = "0008_control_dispositions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "control_claim_records",
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
            "evidence_id",
            sa.Integer(),
            sa.ForeignKey("evidence.id"),
            nullable=False,
        ),
        sa.Column(
            "control_id",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "statement",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "source_reference",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "covered",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "tested",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "scope_matches",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "service_matches",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "exception_present",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "generation_status",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "human_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "confirmed_by",
            sa.String(255),
        ),
        sa.Column(
            "analyst_rationale",
            sa.Text(),
        ),
        sa.Column(
            "claim_policy_version",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "review_policy_version",
            sa.String(40),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_control_claim_vendor",
        "control_claim_records",
        ["vendor_id"],
    )

    op.create_index(
        "ix_control_claim_assessment",
        "control_claim_records",
        ["assessment_id"],
    )

    op.create_index(
        "ix_control_claim_evidence",
        "control_claim_records",
        ["evidence_id"],
    )

    op.create_index(
        "ix_control_claim_control",
        "control_claim_records",
        ["control_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_control_claim_control",
        table_name="control_claim_records",
    )

    op.drop_index(
        "ix_control_claim_evidence",
        table_name="control_claim_records",
    )

    op.drop_index(
        "ix_control_claim_assessment",
        table_name="control_claim_records",
    )

    op.drop_index(
        "ix_control_claim_vendor",
        table_name="control_claim_records",
    )

    op.drop_table(
        "control_claim_records"
    )