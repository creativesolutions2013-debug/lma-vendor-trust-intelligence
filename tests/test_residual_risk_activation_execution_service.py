import json

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.authz import (
    Principal,
    ROLE_ANALYST,
    ROLE_RISK_MANAGER,
)
from src.control_effectiveness_guardrail import (
    select_control_effectiveness_input,
)
from src.db import (
    Assessment,
    AuditLog,
    Base,
    ResidualRiskActivationExecution,
    Vendor,
)
from src.residual_risk_activation import (
    evaluate_residual_risk_activation,
)
from src.residual_risk_activation_execution_service import (
    execute_residual_risk_activation,
)
from src.residual_risk_activation_service import (
    save_residual_risk_activation_review,
)
from src.residual_risk_reconciliation import (
    reconcile_residual_risk,
)
from src.scoring import (
    evaluate_residual_risk,
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


def risk_manager():
    return Principal(
        subject="risk-manager-123",
        display_name="Risk Manager",
        email="risk@example.com",
        role=ROLE_RISK_MANAGER,
    )


def seed_vendor_and_assessment(
    session,
):
    vendor = Vendor(
        legal_name="Example Vendor LLC",
        display_name="Example Vendor",
        inherent_risk_score=80,
        residual_risk_score=66,
        external_risk_score=70,
        control_effectiveness=80,
        overall_risk_rating="High",
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

    return vendor, assessment


def create_review(
    session,
    *,
    vendor,
    assessment,
    coverage=100,
    approved=True,
):
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=coverage,
        )
    )

    reconciliation = (
        reconcile_residual_risk(
            inherent_risk=80,
            external_risk=70,
            stored_residual_risk=(
                vendor.residual_risk_score
            ),
            legacy_effectiveness=80,
            guarded_effectiveness=guarded,
        )
    )

    risk_decision = (
        evaluate_residual_risk(
            inherent_risk=80,
            control_effectiveness=(
                guarded.effective_control_input
            ),
            external_risk=70,
        )
    )

    activation = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                risk_decision
            ),
            analyst_approved=approved,
        )
    )

    return (
        save_residual_risk_activation_review(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            reconciliation=reconciliation,
            decision=activation,
            principal=analyst(),
            rationale=(
                "Reviewed governed residual risk "
                "and approved activation."
            ),
        )
    )


def test_execution_updates_authoritative_vendor_risk():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    review = create_review(
        session,
        vendor=vendor,
        assessment=assessment,
    )

    execution = (
        execute_residual_risk_activation(
            session,
            activation_review_id=review.id,
            principal=risk_manager(),
            rationale=(
                "Approved review passed all "
                "execution controls."
            ),
        )
    )

    session.commit()
    session.refresh(vendor)

    assert (
        vendor.residual_risk_score
        == 74.0
    )

    assert (
        vendor.overall_risk_rating
        == "High"
    )

    assert (
        execution.previous_residual_risk
        == 66.0
    )

    assert (
        execution.activated_residual_risk
        == 74.0
    )

    assert (
        execution.execution_policy_version
        == "RAE-1.0"
    )

    session.close()


def test_execution_creates_audit_event():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    review = create_review(
        session,
        vendor=vendor,
        assessment=assessment,
    )

    execution = (
        execute_residual_risk_activation(
            session,
            activation_review_id=review.id,
            principal=risk_manager(),
            rationale="Execute approved activation.",
        )
    )

    session.commit()

    event = (
        session.query(AuditLog)
        .filter_by(
            action=(
                "residual_risk_activation.execute"
            )
        )
        .one()
    )

    assert (
        event.object_id
        == str(execution.id)
    )

    details = json.loads(
        event.details_json
    )

    assert (
        details["activation_review_id"]
        == review.id
    )

    assert (
        details["previous_residual_risk"]
        == 66.0
    )

    assert (
        details["activated_residual_risk"]
        == 74.0
    )

    session.close()


def test_analyst_cannot_execute_authoritative_activation():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    review = create_review(
        session,
        vendor=vendor,
        assessment=assessment,
    )

    with pytest.raises(
        PermissionError
    ):
        execute_residual_risk_activation(
            session,
            activation_review_id=review.id,
            principal=analyst(),
            rationale="Attempted execution.",
        )

    session.close()


def test_ineligible_review_cannot_be_executed():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    review = create_review(
        session,
        vendor=vendor,
        assessment=assessment,
        coverage=14,
        approved=False,
    )

    with pytest.raises(
        ValueError,
        match="not system-ready",
    ):
        execute_residual_risk_activation(
            session,
            activation_review_id=review.id,
            principal=risk_manager(),
            rationale="Attempted blocked activation.",
        )

    session.close()


def test_stale_review_cannot_be_executed():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    review = create_review(
        session,
        vendor=vendor,
        assessment=assessment,
    )

    vendor.residual_risk_score = 67.0
    session.flush()

    with pytest.raises(
        ValueError,
        match="stale",
    ):
        execute_residual_risk_activation(
            session,
            activation_review_id=review.id,
            principal=risk_manager(),
            rationale="Attempted stale activation.",
        )

    assert (
        vendor.residual_risk_score
        == 67.0
    )

    session.close()


def test_same_review_cannot_be_executed_twice():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    review = create_review(
        session,
        vendor=vendor,
        assessment=assessment,
    )

    execute_residual_risk_activation(
        session,
        activation_review_id=review.id,
        principal=risk_manager(),
        rationale="First execution.",
    )

    with pytest.raises(
        ValueError,
        match="already been executed",
    ):
        execute_residual_risk_activation(
            session,
            activation_review_id=review.id,
            principal=risk_manager(),
            rationale="Second execution.",
        )

    session.close()


def test_outdated_policy_review_cannot_be_executed():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    review = create_review(
        session,
        vendor=vendor,
        assessment=assessment,
    )

    review.activation_policy_version = (
        "RRA-0.9"
    )

    session.flush()

    with pytest.raises(
        ValueError,
        match="outdated RRA policy",
    ):
        execute_residual_risk_activation(
            session,
            activation_review_id=review.id,
            principal=risk_manager(),
            rationale="Attempted old-policy activation.",
        )

    session.close()


def test_execution_rationale_is_required():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    review = create_review(
        session,
        vendor=vendor,
        assessment=assessment,
    )

    with pytest.raises(
        ValueError,
        match="rationale",
    ):
        execute_residual_risk_activation(
            session,
            activation_review_id=review.id,
            principal=risk_manager(),
            rationale="",
        )

    session.close()
