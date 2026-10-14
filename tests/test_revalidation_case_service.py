import json

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.authz import (
    Principal,
    ROLE_ANALYST,
    ROLE_VIEWER,
)
from src.db import (
    Assessment,
    AuditLog,
    Base,
    RevalidationCaseRecord,
    ResidualRiskActivationExecution,
    Vendor,
)
from src.revalidation_case import (
    build_revalidation_case_snapshot,
)
from src.revalidation_case_service import (
    open_revalidation_case,
)
from src.residual_risk_activation_validity import (
    ResidualRiskActivationValidity,
)


def make_session():
    engine = create_engine(
        "sqlite:///:memory:"
    )

    Base.metadata.create_all(
        engine
    )

    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )()


def analyst():
    return Principal(
        subject="analyst-123",
        display_name="Test Analyst",
        email="analyst@example.com",
        role=ROLE_ANALYST,
    )


def viewer():
    return Principal(
        subject="viewer-123",
        display_name="Viewer",
        email="viewer@example.com",
        role=ROLE_VIEWER,
    )


def seed_context(session):
    vendor = Vendor(
        legal_name="Example Vendor LLC",
        display_name="Example Vendor",
        residual_risk_score=5.8,
        overall_risk_rating="Low",
    )

    session.add(vendor)
    session.flush()

    assessment = Assessment(
        vendor_id=vendor.id,
        assessment_type="Security Assessment",
        status="Completed",
    )

    session.add(assessment)
    session.flush()

    execution = ResidualRiskActivationExecution(
        activation_review_id=999,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        previous_residual_risk=25.8,
        activated_residual_risk=5.8,
        previous_risk_rating="Moderate",
        activated_risk_rating="Low",
        executor_subject="risk-manager-1",
        executor_name="Risk Manager",
        executor_email="risk@example.com",
        executor_role="Risk Manager",
        execution_rationale="Synthetic activation.",
        execution_policy_version="RAE-1.0",
        activation_policy_version="RRA-1.0",
        reconciliation_policy_version="RRR-1.0",
        residual_risk_policy_version="RR-2.0",
    )

    session.add(execution)
    session.flush()

    return vendor, assessment, execution


def make_snapshot(execution):
    validity = ResidualRiskActivationValidity(
        status="Revalidation Required",
        valid=False,
        revalidation_required=True,
        challenged=False,
        reasons=(
            "GOVERNED_EFFECTIVENESS_UNAVAILABLE",
            "GOVERNED_DECISION_COVERAGE_BELOW_THRESHOLD",
            "CONTROL_EFFECTIVENESS_NOT_GOVERNED",
        ),
        activated_residual_risk=5.8,
        current_authoritative_risk=5.8,
        decision_coverage_percent=0,
        control_effectiveness_status=(
            "Insufficient Decisions"
        ),
    )

    return build_revalidation_case_snapshot(
        validity=validity,
        latest_execution=execution,
    )


def test_persists_revalidation_case():
    session = make_session()

    vendor, assessment, execution = (
        seed_context(session)
    )

    snapshot = make_snapshot(execution)

    saved = open_revalidation_case(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        snapshot=snapshot,
        principal=analyst(),
        rationale=(
            "Governed assurance basis deteriorated "
            "after activation."
        ),
    )

    session.commit()

    record = (
        session.query(RevalidationCaseRecord)
        .filter_by(id=saved.id)
        .one()
    )

    assert record.vendor_id == vendor.id
    assert record.assessment_id == assessment.id
    assert (
        record.activation_execution_id
        == execution.id
    )
    assert record.status == "Open"
    assert record.trigger_status == (
        "Revalidation Required"
    )
    assert record.activated_residual_risk == 5.8
    assert record.current_authoritative_risk == 5.8
    assert record.decision_coverage_percent == 0
    assert record.rav_policy_version == "RAV-1.0"
    assert (
        record.revalidation_policy_version
        == "RVC-1.0"
    )

    session.close()


def test_trigger_reasons_are_persisted():
    session = make_session()

    vendor, assessment, execution = (
        seed_context(session)
    )

    saved = open_revalidation_case(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        snapshot=make_snapshot(execution),
        principal=analyst(),
        rationale="Open governed revalidation.",
    )

    session.commit()

    reasons = json.loads(
        saved.trigger_reasons_json
    )

    assert reasons == [
        "GOVERNED_EFFECTIVENESS_UNAVAILABLE",
        "GOVERNED_DECISION_COVERAGE_BELOW_THRESHOLD",
        "CONTROL_EFFECTIVENESS_NOT_GOVERNED",
    ]

    session.close()


def test_creates_audit_event():
    session = make_session()

    vendor, assessment, execution = (
        seed_context(session)
    )

    saved = open_revalidation_case(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        snapshot=make_snapshot(execution),
        principal=analyst(),
        rationale="Open governed revalidation.",
    )

    session.commit()

    event = (
        session.query(AuditLog)
        .filter_by(
            action="residual_risk_revalidation.open"
        )
        .one()
    )

    assert event.object_type == "revalidation_case"
    assert event.object_id == str(saved.id)
    assert event.vendor_id == vendor.id

    details = json.loads(
        event.details_json
    )

    assert (
        details["activation_execution_id"]
        == execution.id
    )

    session.close()


def test_opening_rationale_is_required():
    session = make_session()

    vendor, assessment, execution = (
        seed_context(session)
    )

    with pytest.raises(
        ValueError,
        match="rationale",
    ):
        open_revalidation_case(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            snapshot=make_snapshot(execution),
            principal=analyst(),
            rationale="",
        )

    session.close()


def test_viewer_cannot_open_case():
    session = make_session()

    vendor, assessment, execution = (
        seed_context(session)
    )

    with pytest.raises(
        PermissionError
    ):
        open_revalidation_case(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            snapshot=make_snapshot(execution),
            principal=viewer(),
            rationale="Attempted revalidation.",
        )

    session.close()


def test_duplicate_case_is_blocked():
    session = make_session()

    vendor, assessment, execution = (
        seed_context(session)
    )

    snapshot = make_snapshot(execution)

    open_revalidation_case(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        snapshot=snapshot,
        principal=analyst(),
        rationale="First case.",
    )

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        open_revalidation_case(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            snapshot=snapshot,
            principal=analyst(),
            rationale="Duplicate case.",
        )

    session.close()


def test_execution_must_match_vendor_and_assessment():
    session = make_session()

    vendor, assessment, execution = (
        seed_context(session)
    )

    other_vendor = Vendor(
        legal_name="Other LLC",
        display_name="Other",
    )

    session.add(other_vendor)
    session.flush()

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        open_revalidation_case(
            session,
            vendor_id=other_vendor.id,
            assessment_id=assessment.id,
            snapshot=make_snapshot(execution),
            principal=analyst(),
            rationale="Invalid linkage.",
        )

    session.close()


def test_service_does_not_mutate_authoritative_risk():
    session = make_session()

    vendor, assessment, execution = (
        seed_context(session)
    )

    original_score = vendor.residual_risk_score
    original_rating = vendor.overall_risk_rating

    open_revalidation_case(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        snapshot=make_snapshot(execution),
        principal=analyst(),
        rationale="Open case only.",
    )

    session.commit()
    session.refresh(vendor)

    assert (
        vendor.residual_risk_score
        == original_score
    )
    assert (
        vendor.overall_risk_rating
        == original_rating
    )

    session.close()
