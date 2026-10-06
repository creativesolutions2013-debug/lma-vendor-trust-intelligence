"""Add persistent control dispositions."""

from alembic import op
import sqlalchemy as sa


revision = "0008_control_dispositions"
down_revision = "0007_evidence_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "control_disposition_records",
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
            "control_id",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "sufficiency_status",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "system_recommendation",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "final_disposition",
            sa.String(80),
            nullable=False,
        ),
        sa.Column(
            "supporting_evidence_ids_json",
            sa.Text(),
        ),
        sa.Column(
            "review_evidence_ids_json",
            sa.Text(),
        ),
        sa.Column(
            "system_reasons_json",
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
            "compensating_control",
            sa.Text(),
        ),
        sa.Column(
            "disposition_policy_version",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "orchestrator_policy_version",
            sa.String(40),
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_control_disposition_vendor",
        "control_disposition_records",
        ["vendor_id"],
    )

    op.create_index(
        "ix_control_disposition_assessment",
        "control_disposition_records",
        ["assessment_id"],
    )

    op.create_index(
        "ix_control_disposition_control",
        "control_disposition_records",
        ["control_id"],
    )

    op.create_index(
        "ix_control_disposition_decided_at",
        "control_disposition_records",
        ["decided_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_control_disposition_decided_at",
        table_name="control_disposition_records",
    )

    op.drop_index(
        "ix_control_disposition_control",
        table_name="control_disposition_records",
    )

    op.drop_index(
        "ix_control_disposition_assessment",
        table_name="control_disposition_records",
    )

    op.drop_index(
        "ix_control_disposition_vendor",
        table_name="control_disposition_records",
    )

    op.drop_table(
        "control_disposition_records"
    )