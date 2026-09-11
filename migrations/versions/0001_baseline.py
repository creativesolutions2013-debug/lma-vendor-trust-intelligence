"""Baseline current vendor trust schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("vendors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("website", sa.String(255)), sa.Column("primary_domain", sa.String(255)),
        sa.Column("industry", sa.String(120)), sa.Column("headquarters_country", sa.String(120)),
        sa.Column("relationship_status", sa.String(50)), sa.Column("criticality", sa.String(50)),
        sa.Column("inherent_risk_score", sa.Float()), sa.Column("residual_risk_score", sa.Float()),
        sa.Column("external_risk_score", sa.Float()), sa.Column("control_effectiveness", sa.Float()),
        sa.Column("overall_risk_rating", sa.String(50)), sa.Column("security_rating", sa.Float()),
        sa.Column("created_at", sa.DateTime()))
    op.create_table("engagements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False), sa.Column("service_description", sa.Text()),
        sa.Column("business_owner", sa.String(255)), sa.Column("department", sa.String(120)),
        sa.Column("business_criticality", sa.String(50)), sa.Column("data_classification", sa.String(80)),
        sa.Column("production_access", sa.Boolean()), sa.Column("network_access", sa.Boolean()),
        sa.Column("privileged_access", sa.Boolean()), sa.Column("ai_enabled", sa.Boolean()),
        sa.Column("status", sa.String(50)))
    op.create_table("assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("assessment_type", sa.String(120), nullable=False), sa.Column("assessment_reason", sa.String(120)),
        sa.Column("status", sa.String(50)), sa.Column("assigned_to", sa.String(255)),
        sa.Column("due_date", sa.String(40)), sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()), sa.Column("risk_score", sa.Float()),
        sa.Column("approval_status", sa.String(80)), sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime()))
    op.create_table("evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id")),
        sa.Column("document_type", sa.String(120), nullable=False), sa.Column("document_name", sa.String(255), nullable=False),
        sa.Column("document_date", sa.String(40)), sa.Column("coverage_start", sa.String(40)),
        sa.Column("coverage_end", sa.String(40)), sa.Column("expiration_date", sa.String(40)),
        sa.Column("issuer", sa.String(255)), sa.Column("opinion", sa.String(120)),
        sa.Column("exceptions_count", sa.Integer()), sa.Column("status", sa.String(80)),
        sa.Column("storage_path", sa.String(500)), sa.Column("analyst_notes", sa.Text()),
        sa.Column("analyst_actions", sa.Text()), sa.Column("file_hash", sa.String(64)),
        sa.Column("extraction_method", sa.String(120)), sa.Column("extraction_confidence", sa.Float()),
        sa.Column("analyzed_at", sa.DateTime()), sa.Column("confidence_reasons", sa.Text()),
        sa.Column("confidence_gaps", sa.Text()), sa.Column("detected_exceptions", sa.Text()),
        sa.Column("created_at", sa.DateTime()))
    op.create_table("findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("evidence_id", sa.Integer(), sa.ForeignKey("evidence.id")),
        sa.Column("source_exception_index", sa.Integer()), sa.Column("source_control_id", sa.String(80)),
        sa.Column("title", sa.String(255), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("source", sa.String(80)), sa.Column("severity", sa.String(40)),
        sa.Column("status", sa.String(50)), sa.Column("owner", sa.String(255)),
        sa.Column("target_date", sa.String(40)), sa.Column("created_at", sa.DateTime()))
    op.create_table("monitoring_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False), sa.Column("severity", sa.String(40)),
        sa.Column("description", sa.Text()), sa.Column("previous_value", sa.String(120)),
        sa.Column("new_value", sa.String(120)), sa.Column("requires_review", sa.Boolean()),
        sa.Column("status", sa.String(50)), sa.Column("event_date", sa.DateTime()))

def downgrade() -> None:
    op.drop_table("monitoring_events")
    op.drop_table("findings")
    op.drop_table("evidence")
    op.drop_table("assessments")
    op.drop_table("engagements")
    op.drop_table("vendors")
