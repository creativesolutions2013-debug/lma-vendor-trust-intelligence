"""Add explicit organization ownership and service-engagement entitlements.

No legacy ownership/linkage is inferred or backfilled. SQLite uses native nullable
ADD COLUMN REFERENCES, avoiding reconstruction of populated legacy tables.
"""
from alembic import op
import sqlalchemy as sa


revision = "0014_organization_engagement_authorization"
down_revision = "0013_revalidation_case_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_key", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.UniqueConstraint("external_key", name="uq_organization_external_key"),
        sa.CheckConstraint("length(trim(external_key)) > 0", name="ck_organization_key_nonempty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_organization_name_nonempty"),
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "issuer", "subject", name="uq_membership_identity"),
        sa.CheckConstraint("length(trim(issuer)) > 0", name="ck_membership_issuer_nonempty"),
        sa.CheckConstraint("length(trim(subject)) > 0", name="ck_membership_subject_nonempty"),
        sa.CheckConstraint("role IN ('Admin', 'Risk Manager', 'Analyst', 'Viewer')", name="ck_membership_role"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_membership_status"),
        sa.CheckConstraint("expires_at > valid_from", name="ck_membership_window"),
    )
    op.create_table(
        "engagement_access_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("membership_id", sa.Integer(), sa.ForeignKey("organization_memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("engagements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("membership_id", "engagement_id", name="uq_membership_engagement_grant"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_engagement_grant_status"),
        sa.CheckConstraint("expires_at > valid_from", name="ck_engagement_grant_window"),
    )
    op.create_index("ix_engagement_access_grants_engagement_id", "engagement_access_grants", ["engagement_id"])

    if op.get_bind().dialect.name == "sqlite":
        # SQLite permits an ADD COLUMN REFERENCES with NULL default. Alembic's
        # generic add_column(ForeignKey) would separately ADD CONSTRAINT and need
        # a table rebuild; keep the existing rows/tables in place instead.
        op.execute("ALTER TABLE vendors ADD COLUMN organization_id INTEGER REFERENCES organizations(id) ON DELETE RESTRICT")
        op.execute("ALTER TABLE assessments ADD COLUMN engagement_id INTEGER REFERENCES engagements(id) ON DELETE RESTRICT")
    else:
        op.add_column("vendors", sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True))
        op.add_column("assessments", sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("engagements.id", ondelete="RESTRICT"), nullable=True))
    op.create_index("ix_vendors_organization_id", "vendors", ["organization_id"])
    op.create_index("ix_assessments_engagement_id", "assessments", ["engagement_id"])


def downgrade() -> None:
    # Dropping ownership/grants silently discards security history and cannot be
    # represented as a safe rollback. An owner-reviewed backup/retention and
    # rollback plan must precede any separate destructive migration.
    raise RuntimeError("Authorization downgrade requires an independently reviewed data-retention and rollback plan; no data was removed.")
