import json

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.authz import (
    Principal,
    ROLE_ANALYST,
    ROLE_VIEWER,
)
from src.control_disposition import (
    AnalystDisposition,
    DISPOSITION_COMPENSATING_CONTROL,
    DISPOSITION_NOT_SATISFIED,
    evaluate_control_disposition,
)
from src.control_disposition_service import (
    save_control_disposition,
)
from src.control_sufficiency import (
    ControlEvidenceDecision,
)
from src.db import (
    Assessment,
    AuditLog,
    Base,
    ControlDispositionRecord,
    Vendor,
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


def seed_vendor_and_assessment(
    session,
):
    vendor = Vendor(
        legal_name="Example Vendor LLC",
        display_name="Example Vendor",
    )

    session.add(
        vendor
    )

    session.flush()

    assessment = Assessment(
        vendor_id=vendor.id,
        assessment_type=(
            "Security Assessment"
        ),
    )

    session.add(
        assessment
    )

    session.flush()

    return (
        vendor,
        assessment,
    )


def make_sufficiency(
    *,
    status="UNSUPPORTED",
):
    return ControlEvidenceDecision(
        control_id="IAM-01",
        status=status,
        supporting_evidence_ids=(10,),
        evidence_review_ids=(11,),
        reasons=(
            "Evidence requires analyst review.",
        ),
        analyst_review_required=True,
    )


def make_human_decision():
    return evaluate_control_disposition(
        make_sufficiency(),
        AnalystDisposition(
            control_id="IAM-01",
            disposition=(
                DISPOSITION_NOT_SATISFIED
            ),
            rationale=(
                "Vendor confirmed that MFA "
                "is not enabled."
            ),
            decided_by="analyst@example.com",
        ),
    )


def test_save_control_disposition_persists_record():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    decision = make_human_decision()

    saved = save_control_disposition(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        sufficiency_status="UNSUPPORTED",
        decision=decision,
        principal=make_principal(),
        orchestrator_policy_version="AO-1.2",
    )

    session.commit()

    record = (
        session.query(
            ControlDispositionRecord
        )
        .filter_by(
            id=saved.id
        )
        .one()
    )

    assert (
        record.control_id
        == "IAM-01"
    )

    assert (
        record.sufficiency_status
        == "UNSUPPORTED"
    )

    assert (
        record.system_recommendation
        == "Analyst Review Required"
    )

    assert (
        record.final_disposition
        == "Not Satisfied"
    )

    assert (
        record.disposition_policy_version
        == "CD-1.0"
    )

    assert (
        record.orchestrator_policy_version
        == "AO-1.2"
    )

    assert (
        record.analyst_subject
        == "analyst-123"
    )

    session.close()


def test_save_control_disposition_serializes_evidence_ids():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    saved = save_control_disposition(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        sufficiency_status="UNSUPPORTED",
        decision=make_human_decision(),
        principal=make_principal(),
        orchestrator_policy_version="AO-1.2",
    )

    session.commit()

    assert (
        json.loads(
            saved.supporting_evidence_ids_json
        )
        == [10]
    )

    assert (
        json.loads(
            saved.review_evidence_ids_json
        )
        == [11]
    )

    reasons = json.loads(
        saved.system_reasons_json
    )

    assert reasons

    session.close()


def test_save_control_disposition_creates_audit_event():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    saved = save_control_disposition(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        sufficiency_status="UNSUPPORTED",
        decision=make_human_decision(),
        principal=make_principal(),
        orchestrator_policy_version="AO-1.2",
    )

    session.commit()

    event = (
        session.query(
            AuditLog
        )
        .filter_by(
            action=(
                "control_disposition.record"
            )
        )
        .one()
    )

    assert (
        event.object_type
        == "control_disposition"
    )

    assert (
        event.object_id
        == str(saved.id)
    )

    assert (
        event.vendor_id
        == vendor.id
    )

    details = json.loads(
        event.details_json
    )

    assert (
        details["control_id"]
        == "IAM-01"
    )

    assert (
        details["final_disposition"]
        == "Not Satisfied"
    )

    session.close()


def test_compensating_control_is_persisted():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    sufficiency = make_sufficiency(
        status="PARTIAL"
    )

    decision = evaluate_control_disposition(
        sufficiency,
        AnalystDisposition(
            control_id="IAM-01",
            disposition=(
                DISPOSITION_COMPENSATING_CONTROL
            ),
            rationale=(
                "Alternative privileged-access "
                "control accepted."
            ),
            decided_by="analyst@example.com",
            compensating_control=(
                "PAM approval is required and "
                "sessions are continuously monitored."
            ),
        ),
    )

    saved = save_control_disposition(
        session,
        vendor_id=vendor.id,
        assessment_id=assessment.id,
        sufficiency_status="PARTIAL",
        decision=decision,
        principal=make_principal(),
        orchestrator_policy_version="AO-1.2",
    )

    session.commit()

    assert (
        saved.final_disposition
        == "Compensating Control"
    )

    assert (
        "PAM approval"
        in saved.compensating_control
    )

    session.close()


def test_unconfirmed_system_recommendation_cannot_be_saved():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    system_only = (
        evaluate_control_disposition(
            make_sufficiency()
        )
    )

    with pytest.raises(
        ValueError,
        match="human-confirmed",
    ):
        save_control_disposition(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            sufficiency_status=(
                "UNSUPPORTED"
            ),
            decision=system_only,
            principal=make_principal(),
            orchestrator_policy_version=(
                "AO-1.2"
            ),
        )

    session.close()


def test_viewer_cannot_record_control_disposition():
    session = make_session()

    vendor, assessment = (
        seed_vendor_and_assessment(
            session
        )
    )

    viewer = Principal(
        subject="viewer-1",
        display_name="Viewer",
        email="viewer@example.com",
        role=ROLE_VIEWER,
    )

    with pytest.raises(
        PermissionError
    ):
        save_control_disposition(
            session,
            vendor_id=vendor.id,
            assessment_id=assessment.id,
            sufficiency_status=(
                "UNSUPPORTED"
            ),
            decision=make_human_decision(),
            principal=viewer,
            orchestrator_policy_version=(
                "AO-1.2"
            ),
        )

    session.close()