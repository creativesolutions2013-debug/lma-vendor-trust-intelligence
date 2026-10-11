import json

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.authz import (
    Principal,
    ROLE_ANALYST,
    ROLE_VIEWER,
)
from src.control_effectiveness_guardrail import (
    select_control_effectiveness_input,
)
from src.db import (
    Assessment,
    AuditLog,
    Base,
    ResidualRiskActivationRecord,
    Vendor,
)
from src.residual_risk_activation import (
    evaluate_residual_risk_activation,
)
from src.residual_risk_activation_service import (
    save_residual_risk_activation_review,
)
from src.residual_risk_reconciliation import (
    reconcile_residual_risk,
)
from src.scoring import (
    ResidualRiskContext,
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


def make_principal():
    return Principal(
        subject="analyst-123",
        display_name="Test Analyst",
        email="analyst@example.com",
        role=ROLE_ANALYST,
    )


def seed_context(session):
    vendor = Vendor(
        legal_name="Example Vendor LLC",
        display_name="Example Vendor",
        inherent_risk_score=80,
        residual_risk_score=66,
        external_risk_score=70,
        control_effectiveness=80,
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


def make_review(
    *,
    coverage=100,
    analyst_approved=False,
    context=None,
):
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=coverage,
        )
    )

    reconciliation = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=66,
        legacy_effectiveness=80,
        guarded_effectiveness=guarded,
    )

    risk_decision = evaluate_residual_risk(
        inherent_risk=80,
        control_effectiveness=(
            guarded.effective_control_input
        ),
        external_risk=70,
        context=context,
    )

    activation = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                risk_decision
            ),
            analyst_approved=(
                analyst_approved
            ),
        )
    )

    return reconciliation, activation


def test_persists_activation_review():
    session = make_session()

    vendor, assessment = seed_context(
        session
    )

    reconciliation, decision = make_review()

    saved = (
        save_residual_risk_activation_review(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            reconciliation=reconciliation,
            decision=decision,
            principal=make_principal(),
            rationale=(
                "Reviewed activation readiness "
                "and policy lineage."
            ),
        )
    )

    session.commit()

    record = (
        session.query(
            ResidualRiskActivationRecord
        )
        .filter_by(id=saved.id)
        .one()
    )

    assert record.vendor_id == vendor.id
    assert record.assessment_id == assessment.id
    assert record.stored_residual_risk == 66.0
    assert record.proposed_residual_risk == 74.0

    assert (
        record.activation_policy_version
        == "RRA-1.0"
    )

    assert (
        record.reconciliation_policy_version
        == "RRR-1.0"
    )

    assert (
        record.residual_risk_policy_version
        == "RR-2.0"
    )

    session.close()


def test_blocking_reasons_are_persisted():
    session = make_session()

    vendor, assessment = seed_context(
        session
    )

    reconciliation, decision = make_review(
        coverage=14,
        context=ResidualRiskContext(
            assessment_complete=False,
        ),
    )

    saved = (
        save_residual_risk_activation_review(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            reconciliation=reconciliation,
            decision=decision,
            principal=make_principal(),
            rationale="Activation remains blocked.",
        )
    )

    session.commit()

    reasons = json.loads(
        saved.blocking_reasons_json
    )

    assert (
        "GOVERNED_COVERAGE_INSUFFICIENT"
        in reasons
    )

    assert (
        "RR2_APPROVAL_BLOCKED"
        in reasons
    )

    assert (
        "RR2_GUARDRAIL:ASSESSMENT_INCOMPLETE"
        in reasons
    )

    session.close()


def test_creates_audit_event():
    session = make_session()

    vendor, assessment = seed_context(
        session
    )

    reconciliation, decision = make_review()

    saved = (
        save_residual_risk_activation_review(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            reconciliation=reconciliation,
            decision=decision,
            principal=make_principal(),
            rationale="Reviewed activation decision.",
        )
    )

    session.commit()

    event = (
        session.query(AuditLog)
        .filter_by(
            action=(
                "residual_risk_activation.review"
            )
        )
        .one()
    )

    assert (
        event.object_type
        == "residual_risk_activation"
    )

    assert (
        event.object_id
        == str(saved.id)
    )

    assert event.vendor_id == vendor.id

    session.close()


def test_rationale_is_required():
    session = make_session()

    vendor, assessment = seed_context(
        session
    )

    reconciliation, decision = make_review()

    with pytest.raises(
        ValueError,
        match="rationale",
    ):
        save_residual_risk_activation_review(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            reconciliation=reconciliation,
            decision=decision,
            principal=make_principal(),
            rationale="",
        )

    session.close()


def test_viewer_cannot_record_review():
    session = make_session()

    vendor, assessment = seed_context(
        session
    )

    reconciliation, decision = make_review()

    viewer = Principal(
        subject="viewer-1",
        display_name="Viewer",
        email="viewer@example.com",
        role=ROLE_VIEWER,
    )

    with pytest.raises(
        PermissionError
    ):
        save_residual_risk_activation_review(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            reconciliation=reconciliation,
            decision=decision,
            principal=viewer,
            rationale="Attempted review.",
        )

    session.close()


def test_eligible_approval_can_be_recorded():
    session = make_session()

    vendor, assessment = seed_context(
        session
    )

    reconciliation, decision = make_review(
        analyst_approved=True,
    )

    saved = (
        save_residual_risk_activation_review(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            reconciliation=reconciliation,
            decision=decision,
            principal=make_principal(),
            rationale=(
                "Governed coverage and guardrails "
                "support activation."
            ),
        )
    )

    session.commit()

    assert saved.system_ready is True
    assert saved.analyst_approved is True
    assert saved.activation_eligible is True

    session.close()


def test_service_does_not_mutate_vendor_risk():
    session = make_session()

    vendor, assessment = seed_context(
        session
    )

    original_score = (
        vendor.residual_risk_score
    )

    reconciliation, decision = make_review(
        analyst_approved=True,
    )

    save_residual_risk_activation_review(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        reconciliation=reconciliation,
        decision=decision,
        principal=make_principal(),
        rationale="Approval review recorded.",
    )

    session.commit()
    session.refresh(vendor)

    assert (
        vendor.residual_risk_score
        == original_score
    )

    session.close()
