"""Add evidence request package table."""

from alembic import op
import sqlalchemy as sa


revision = "0007_evidence_request"
down_revision = "0006_targeted_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_request_packages",
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
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="Draft",
        ),
        sa.Column(
            "requested_items_json",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "validation_items_json",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "avoided_requests_json",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "analyst_notes",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "sent_by",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "closed_at",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table(
        "evidence_request_packages"
    )
