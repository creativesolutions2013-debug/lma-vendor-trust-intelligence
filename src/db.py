import os
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    declarative_base,
    relationship,
    sessionmaker,
)

from src.membership_identity_guard import install_membership_identity_guard


DATA_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
    / "data"
)

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DEFAULT_DATABASE_PATH = (
    DATA_DIR
    / "vendor_trust.db"
)

DEFAULT_DATABASE_URL = (
    f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    DEFAULT_DATABASE_URL,
)


def build_engine(
    database_url: str,
):
    engine_kwargs = {}

    if database_url.startswith(
        "sqlite"
    ):
        engine_kwargs[
            "connect_args"
        ] = {
            "check_same_thread": False,
        }

    return create_engine(
        database_url,
        **engine_kwargs,
    )


engine = build_engine(
    DATABASE_URL
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


def utc_now():
    """
    Return current UTC as a naive datetime for
    current database compatibility.
    """

    return datetime.now(
        timezone.utc
    ).replace(
        tzinfo=None
    )


class Organization(Base):
    """Server-managed organization identity; names never authorize access."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("external_key", name="uq_organization_external_key"),
        CheckConstraint("length(trim(external_key)) > 0", name="ck_organization_key_nonempty"),
        CheckConstraint("length(trim(name)) > 0", name="ck_organization_name_nonempty"),
    )

    id = Column(Integer, primary_key=True)
    external_key = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)


class OrganizationMembership(Base):
    """Explicit issuer/subject membership; never inferred from email or role."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "issuer", "subject", name="uq_membership_identity"),
        CheckConstraint("length(trim(issuer)) > 0", name="ck_membership_issuer_nonempty"),
        CheckConstraint("length(trim(subject)) > 0", name="ck_membership_subject_nonempty"),
        CheckConstraint("role IN ('Admin', 'Risk Manager', 'Analyst', 'Viewer')", name="ck_membership_role"),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_membership_status"),
        CheckConstraint("expires_at > valid_from", name="ck_membership_window"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    issuer = Column(String(500), nullable=False)
    subject = Column(String(255), nullable=False)
    role = Column(String(80), nullable=False)
    status = Column(String(20), nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


event.listen(OrganizationMembership.__table__, "after_create", install_membership_identity_guard)


class EngagementAccessGrant(Base):
    """Revocable membership entitlement to one explicit service engagement."""

    __tablename__ = "engagement_access_grants"
    __table_args__ = (
        UniqueConstraint("membership_id", "engagement_id", name="uq_membership_engagement_grant"),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_engagement_grant_status"),
        CheckConstraint("expires_at > valid_from", name="ck_engagement_grant_window"),
    )

    id = Column(Integer, primary_key=True)
    membership_id = Column(Integer, ForeignKey("organization_memberships.id", ondelete="RESTRICT"), nullable=False)
    engagement_id = Column(Integer, ForeignKey("engagements.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(
        Integer,
        primary_key=True,
    )

    # Legacy rows remain unassigned; null is never secure authorization.
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True)

    legal_name = Column(
        String(255),
        nullable=False,
    )

    display_name = Column(
        String(255),
        nullable=False,
    )

    website = Column(
        String(255)
    )

    primary_domain = Column(
        String(255)
    )

    industry = Column(
        String(120)
    )

    headquarters_country = Column(
        String(120)
    )

    relationship_status = Column(
        String(50),
        default="Prospective",
    )

    criticality = Column(
        String(50),
        default="Moderate",
    )

    inherent_risk_score = Column(
        Float,
        default=0,
    )

    residual_risk_score = Column(
        Float,
        default=0,
    )

    external_risk_score = Column(
        Float,
        default=0,
    )

    control_effectiveness = Column(
        Float,
        default=50,
    )

    overall_risk_rating = Column(
        String(50),
        default="Moderate",
    )

    security_rating = Column(
        Float,
        default=0,
    )

    created_at = Column(
        DateTime,
        default=utc_now,
    )

    engagements = relationship(
        "Engagement",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    findings = relationship(
        "Finding",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    events = relationship(
        "MonitoringEvent",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    assessments = relationship(
        "Assessment",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    evidence = relationship(
        "Evidence",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    approval_decisions = relationship(
        "ApprovalDecision",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    control_dispositions = relationship(
        "ControlDispositionRecord",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    control_claims = relationship(
        "ControlClaimRecord",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    residual_risk_activation_records = relationship(
        "ResidualRiskActivationRecord",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    residual_risk_activation_executions = relationship(
        "ResidualRiskActivationExecution",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    revalidation_cases = relationship(
        "RevalidationCaseRecord",
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

class Engagement(Base):
    __tablename__ = "engagements"

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
        nullable=False,
    )

    service_name = Column(
        String(255),
        nullable=False,
    )

    service_description = Column(
        Text
    )

    business_owner = Column(
        String(255)
    )

    department = Column(
        String(120)
    )

    business_criticality = Column(
        String(50)
    )

    data_classification = Column(
        String(80)
    )

    production_access = Column(
        Boolean,
        default=False,
    )

    network_access = Column(
        Boolean,
        default=False,
    )

    privileged_access = Column(
        Boolean,
        default=False,
    )

    ai_enabled = Column(
        Boolean,
        default=False,
    )

    status = Column(
        String(50),
        default="Active",
    )

    vendor = relationship(
        "Vendor",
        back_populates="engagements",
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(
        Integer,
        primary_key=True,
    )

    # Explicit service scope is additive; no vendor-based engagement inference.
    engagement_id = Column(Integer, ForeignKey("engagements.id", ondelete="RESTRICT"), nullable=True, index=True)

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
        nullable=False,
    )

    assessment_type = Column(
        String(120),
        nullable=False,
    )

    assessment_reason = Column(
        String(120),
        default="New vendor",
    )

    status = Column(
        String(50),
        default="Not Started",
    )

    assigned_to = Column(
        String(255)
    )

    due_date = Column(
        String(40)
    )

    started_at = Column(
        DateTime
    )

    completed_at = Column(
        DateTime
    )

    risk_score = Column(
        Float,
        default=0,
    )

    approval_status = Column(
        String(80),
        default="Pending",
    )

    notes = Column(
        Text
    )

    proposed_scope_json = Column(
        Text
    )

    approved_scope_json = Column(
        Text
    )

    scope_override_rationale = Column(
        Text
    )

    scope_confirmed_by = Column(
        String(255)
    )

    scope_confirmed_at = Column(
        DateTime
    )

    created_at = Column(
        DateTime,
        default=utc_now,
    )

    vendor = relationship(
        "Vendor",
        back_populates="assessments",
    )

    evidence = relationship(
        "Evidence",
        back_populates="assessment",
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
        nullable=False,
    )

    assessment_id = Column(
        Integer,
        ForeignKey(
            "assessments.id"
        ),
    )

    document_type = Column(
        String(120),
        nullable=False,
    )

    document_name = Column(
        String(255),
        nullable=False,
    )

    document_date = Column(
        String(40)
    )

    coverage_start = Column(
        String(40)
    )

    coverage_end = Column(
        String(40)
    )

    expiration_date = Column(
        String(40)
    )

    issuer = Column(
        String(255)
    )

    opinion = Column(
        String(120)
    )

    exceptions_count = Column(
        Integer,
        default=0,
    )

    status = Column(
        String(80),
        default="Received",
    )

    storage_path = Column(
        String(500)
    )

    analyst_notes = Column(
        Text
    )

    analyst_actions = Column(
        Text
    )

    file_hash = Column(
        String(64)
    )

    extraction_method = Column(
        String(120)
    )

    extraction_confidence = Column(
        Float
    )

    analyzed_at = Column(
        DateTime
    )

    confidence_reasons = Column(
        Text
    )

    confidence_gaps = Column(
        Text
    )

    detected_exceptions = Column(
        Text
    )

    created_at = Column(
        DateTime,
        default=utc_now,
    )

    vendor = relationship(
        "Vendor",
        back_populates="evidence",
    )

    assessment = relationship(
        "Assessment",
        back_populates="evidence",
    )

    findings = relationship(
        "Finding",
        back_populates="evidence",
    )


class EvidenceRequestPackage(Base):
    __tablename__ = (
        "evidence_request_packages"
    )

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
        nullable=False,
    )

    assessment_id = Column(
        Integer,
        ForeignKey(
            "assessments.id"
        ),
        nullable=False,
    )

    status = Column(
        String(40),
        default="Draft",
        nullable=False,
    )

    requested_items_json = Column(
        Text,
        nullable=False,
    )

    validation_items_json = Column(
        Text
    )

    avoided_requests_json = Column(
        Text
    )

    analyst_notes = Column(
        Text
    )

    created_by = Column(
        String(255),
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    sent_by = Column(
        String(255)
    )

    sent_at = Column(
        DateTime
    )

    received_at = Column(
        DateTime
    )

    closed_at = Column(
        DateTime
    )


class Finding(Base):
    __tablename__ = "findings"

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
        nullable=False,
    )

    evidence_id = Column(
        Integer,
        ForeignKey(
            "evidence.id"
        ),
    )

    source_exception_index = Column(
        Integer
    )

    source_control_id = Column(
        String(80)
    )

    title = Column(
        String(255),
        nullable=False,
    )

    description = Column(
        Text
    )

    source = Column(
        String(80),
        default="Assessment",
    )

    severity = Column(
        String(40),
        default="Moderate",
    )

    status = Column(
        String(50),
        default="Open",
    )

    owner = Column(
        String(255)
    )

    target_date = Column(
        String(40)
    )

    escalation_status = Column(
        String(50),
        default="Not Escalated",
    )

    escalation_note = Column(
        Text
    )

    escalated_by = Column(
        String(255)
    )

    escalated_at = Column(
        DateTime
    )

    created_at = Column(
        DateTime,
        default=utc_now,
    )

    vendor = relationship(
        "Vendor",
        back_populates="findings",
    )

    evidence = relationship(
        "Evidence",
        back_populates="findings",
    )


class ApprovalDecision(Base):
    __tablename__ = (
        "approval_decisions"
    )

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
        nullable=False,
    )

    system_recommendation = Column(
        String(80),
        nullable=False,
    )

    system_reasons_json = Column(
        Text
    )

    evidence_completion_percent = Column(
        Float
    )

    residual_risk_score = Column(
        Float
    )

    decision = Column(
        String(80),
        nullable=False,
    )

    approver_subject = Column(
        String(255),
        nullable=False,
    )

    approver_name = Column(
        String(255)
    )

    approver_email = Column(
        String(255)
    )

    approver_role = Column(
        String(80)
    )

    rationale = Column(
        Text
    )

    conditions = Column(
        Text
    )

    decided_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    vendor = relationship(
        "Vendor",
        back_populates="approval_decisions",
    )


class ControlDispositionRecord(Base):
    __tablename__ = (
        "control_disposition_records"
    )

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
        nullable=False,
    )

    assessment_id = Column(
        Integer,
        ForeignKey(
            "assessments.id"
        ),
        nullable=False,
    )

    control_id = Column(
        String(80),
        nullable=False,
    )

    sufficiency_status = Column(
        String(40),
        nullable=False,
    )

    system_recommendation = Column(
        String(80),
        nullable=False,
    )

    final_disposition = Column(
        String(80),
        nullable=False,
    )

    supporting_evidence_ids_json = Column(
        Text
    )

    review_evidence_ids_json = Column(
        Text
    )

    system_reasons_json = Column(
        Text
    )

    analyst_subject = Column(
        String(255),
        nullable=False,
    )

    analyst_name = Column(
        String(255)
    )

    analyst_email = Column(
        String(255)
    )

    analyst_role = Column(
        String(80)
    )

    rationale = Column(
        Text,
        nullable=False,
    )

    compensating_control = Column(
        Text
    )

    disposition_policy_version = Column(
        String(40),
        nullable=False,
    )

    orchestrator_policy_version = Column(
        String(40)
    )

    claim_basis_verified = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    claim_basis_mode = Column(
        String(40),
        default="LEGACY_UNVERIFIED",
        nullable=False,
    )

    claim_basis_record_ids_json = Column(
        Text
    )

    claim_basis_evidence_ids_json = Column(
        Text
    )

    claim_basis_override_reason = Column(
        Text
    )

    claim_basis_policy_version = Column(
        String(40)
    )

    decided_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    vendor = relationship(
        "Vendor",
        back_populates="control_dispositions",
    )

class ControlClaimRecord(Base):
    __tablename__ = "control_claim_records"

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey("vendors.id"),
        nullable=False,
    )

    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id"),
        nullable=False,
    )

    evidence_id = Column(
        Integer,
        ForeignKey("evidence.id"),
        nullable=False,
    )

    control_id = Column(
        String(80),
        nullable=False,
    )

    statement = Column(
        Text,
        nullable=False,
    )

    source_reference = Column(
        Text,
        nullable=False,
    )

    covered = Column(
        Boolean,
        nullable=False,
    )

    tested = Column(
        Boolean,
        nullable=False,
    )

    scope_matches = Column(
        Boolean,
        nullable=False,
    )

    service_matches = Column(
        Boolean,
        nullable=False,
    )

    exception_present = Column(
        Boolean,
        nullable=False,
    )

    confidence = Column(
        Float,
        nullable=False,
    )

    generation_status = Column(
        String(40),
        nullable=False,
    )

    human_confirmed = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    confirmed_by = Column(
        String(255),
    )

    analyst_rationale = Column(
        Text,
    )

    claim_policy_version = Column(
        String(40),
        nullable=False,
    )

    review_policy_version = Column(
        String(40),
    )

    created_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    vendor = relationship(
        "Vendor",
        back_populates="control_claims",
    )

class ResidualRiskActivationRecord(Base):
    __tablename__ = "residual_risk_activation_records"

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey("vendors.id"),
        nullable=False,
    )

    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id"),
        nullable=False,
    )

    stored_residual_risk = Column(
        Float,
        nullable=False,
    )

    fresh_baseline_risk = Column(
        Float,
        nullable=False,
    )

    proposed_residual_risk = Column(
        Float,
        nullable=False,
    )

    stored_to_baseline_delta = Column(
        Float,
        nullable=False,
    )

    governed_contribution_delta = Column(
        Float,
        nullable=False,
    )

    stored_to_governed_delta = Column(
        Float,
        nullable=False,
    )

    governed_rating = Column(
        String(40),
        nullable=False,
    )

    control_input_mode = Column(
        String(80),
        nullable=False,
    )

    decision_status = Column(
        String(80),
        nullable=False,
    )

    system_ready = Column(
        Boolean,
        nullable=False,
    )

    analyst_approved = Column(
        Boolean,
        nullable=False,
    )

    activation_eligible = Column(
        Boolean,
        nullable=False,
    )

    blocking_reasons_json = Column(
        Text
    )

    analyst_subject = Column(
        String(255),
        nullable=False,
    )

    analyst_name = Column(
        String(255)
    )

    analyst_email = Column(
        String(255)
    )

    analyst_role = Column(
        String(80)
    )

    rationale = Column(
        Text,
        nullable=False,
    )

    activation_policy_version = Column(
        String(40),
        nullable=False,
    )

    reconciliation_policy_version = Column(
        String(40),
        nullable=False,
    )

    residual_risk_policy_version = Column(
        String(40),
        nullable=False,
    )

    reviewed_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    vendor = relationship(
        "Vendor",
        back_populates="residual_risk_activation_records",
    )


class ResidualRiskActivationExecution(Base):
    __tablename__ = "residual_risk_activation_executions"

    id = Column(
        Integer,
        primary_key=True,
    )

    activation_review_id = Column(
        Integer,
        ForeignKey(
            "residual_risk_activation_records.id"
        ),
        nullable=False,
        unique=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey("vendors.id"),
        nullable=False,
    )

    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id"),
        nullable=False,
    )

    previous_residual_risk = Column(
        Float,
        nullable=False,
    )

    activated_residual_risk = Column(
        Float,
        nullable=False,
    )

    previous_risk_rating = Column(
        String(40)
    )

    activated_risk_rating = Column(
        String(40),
        nullable=False,
    )

    executor_subject = Column(
        String(255),
        nullable=False,
    )

    executor_name = Column(
        String(255)
    )

    executor_email = Column(
        String(255)
    )

    executor_role = Column(
        String(80)
    )

    execution_rationale = Column(
        Text,
        nullable=False,
    )

    execution_policy_version = Column(
        String(40),
        nullable=False,
    )

    activation_policy_version = Column(
        String(40),
        nullable=False,
    )

    reconciliation_policy_version = Column(
        String(40),
        nullable=False,
    )

    residual_risk_policy_version = Column(
        String(40),
        nullable=False,
    )

    activated_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    vendor = relationship(
        "Vendor",
        back_populates="residual_risk_activation_executions",
    )

    review = relationship(
        "ResidualRiskActivationRecord"
    )


class RevalidationCaseRecord(Base):
    __tablename__ = "revalidation_case_records"

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey("vendors.id"),
        nullable=False,
    )

    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id"),
        nullable=False,
    )

    activation_execution_id = Column(
        Integer,
        ForeignKey(
            "residual_risk_activation_executions.id"
        ),
        nullable=False,
        unique=True,
    )

    status = Column(
        String(40),
        nullable=False,
    )

    trigger_status = Column(
        String(80),
        nullable=False,
    )

    trigger_reasons_json = Column(
        Text,
        nullable=False,
    )

    activated_residual_risk = Column(
        Float,
        nullable=False,
    )

    current_authoritative_risk = Column(
        Float,
        nullable=False,
    )

    decision_coverage_percent = Column(
        Integer,
        nullable=False,
    )

    control_effectiveness_status = Column(
        String(80),
        nullable=False,
    )

    rav_policy_version = Column(
        String(40),
        nullable=False,
    )

    revalidation_policy_version = Column(
        String(40),
        nullable=False,
    )

    opened_by_subject = Column(
        String(255),
        nullable=False,
    )

    opened_by_name = Column(
        String(255),
    )

    opened_by_email = Column(
        String(255),
    )

    opened_by_role = Column(
        String(80),
    )

    opening_rationale = Column(
        Text,
        nullable=False,
    )

    opened_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    vendor = relationship(
        "Vendor",
        back_populates="revalidation_cases",
    )

    activation_execution = relationship(
        "ResidualRiskActivationExecution"
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(
        Integer,
        primary_key=True,
    )

    actor_subject = Column(
        String(255),
        nullable=False,
    )

    actor_name = Column(
        String(255)
    )

    actor_email = Column(
        String(255)
    )

    actor_role = Column(
        String(80)
    )

    action = Column(
        String(120),
        nullable=False,
    )

    object_type = Column(
        String(120),
        nullable=False,
    )

    object_id = Column(
        String(120)
    )

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
    )

    outcome = Column(
        String(40),
        nullable=False,
        default="success",
    )

    details_json = Column(
        Text
    )

    created_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )


class MonitoringEvent(Base):
    __tablename__ = (
        "monitoring_events"
    )

    id = Column(
        Integer,
        primary_key=True,
    )

    vendor_id = Column(
        Integer,
        ForeignKey(
            "vendors.id"
        ),
        nullable=False,
    )

    event_type = Column(
        String(120),
        nullable=False,
    )

    severity = Column(
        String(40),
        default="Moderate",
    )

    description = Column(
        Text
    )

    previous_value = Column(
        String(120)
    )

    new_value = Column(
        String(120)
    )

    requires_review = Column(
        Boolean,
        default=True,
    )

    status = Column(
        String(50),
        default="Open",
    )

    materiality = Column(
        String(40)
    )

    decision_impact = Column(
        String(80)
    )

    recommended_action = Column(
        String(80)
    )

    affected_domain = Column(
        String(120)
    )

    recommendation_rationale = Column(
        Text
    )

    recommendation_confidence = Column(
        String(40)
    )

    analyst_action = Column(
        String(80)
    )

    analyst_rationale = Column(
        Text
    )

    analyst_followed_recommendation = Column(
        Boolean
    )

    acted_by = Column(
        String(255)
    )

    acted_at = Column(
        DateTime
    )

    event_date = Column(
        DateTime,
        default=utc_now,
    )

    vendor = relationship(
        "Vendor",
        back_populates="events",
    )


def init_db():
    """
    Application startup hook.

    Alembic owns schema creation and evolution.
    """

    return None


def get_session():
    return SessionLocal()
