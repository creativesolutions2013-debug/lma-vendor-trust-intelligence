from dataclasses import dataclass

from src.applicability import (
    VendorRiskContext,
    evaluate_applicability,
)

from src.assessment_orchestrator import (
    ORCHESTRATOR_POLICY_VERSION,
    build_assessment_work_plan,
)

from src.tiering import get_tier_profile


@dataclass
class EvidenceStub:
    id: int
    document_type: str
    document_name: str = ""
    expiration_date: str | None = None
    status: str = "Current"
    exceptions_count: int = 0
    detected_exceptions: str = ""
    extraction_confidence: float = 0.95


def build_contextual_profile():
    profile = get_tier_profile(30)

    return evaluate_applicability(
        profile,
        VendorRiskContext(
            sensitive_data=True,
            system_access=True,
            internet_facing=True,
        ),
    )


def test_missing_evidence_generates_targeted_questions():
    applicability = build_contextual_profile()

    work_plan = build_assessment_work_plan(
        applicability,
        [],
    )

    assert work_plan.vendor_input_controls > 0
    assert work_plan.questions_generated > 0

    assert any(
        item.workflow_action == "Ask Vendor"
        for item in work_plan.items
    )


def test_current_evidence_suppresses_questions():
    applicability = evaluate_applicability(
        get_tier_profile(80),
        VendorRiskContext(),
    )

    evidence = [
        EvidenceStub(
            id=1,
            document_type="SOC 2 Type II",
        ),
        EvidenceStub(
            id=2,
            document_type="Penetration Test",
        ),
        EvidenceStub(
            id=3,
            document_type="BCP / DR Test",
        ),
        EvidenceStub(
            id=4,
            document_type="Incident Response Plan",
        ),
        EvidenceStub(
            id=5,
            document_type="Security Policy",
        ),
        EvidenceStub(
            id=6,
            document_type="Architecture Diagram",
        ),
    ]

    work_plan = build_assessment_work_plan(
        applicability,
        evidence,
    )

    assert work_plan.evidence_satisfied_controls > 0
    assert work_plan.questions_suppressed > 0
    assert work_plan.questionnaire_reduction_percent > 0


def test_expired_evidence_generates_vendor_gap():
    applicability = evaluate_applicability(
        get_tier_profile(30),
        VendorRiskContext(
            internet_facing=True,
        ),
    )

    evidence = [
        EvidenceStub(
            id=10,
            document_type="Penetration Test",
            expiration_date="2020-01-01",
        ),
    ]

    work_plan = build_assessment_work_plan(
        applicability,
        evidence,
    )

    assert any(
        item.workflow_action == "Ask Vendor"
        and "Penetration Test"
        in item.evidence_requirements
        for item in work_plan.items
    )


def test_low_confidence_evidence_routes_to_analyst():
    applicability = evaluate_applicability(
        get_tier_profile(30),
        VendorRiskContext(),
    )

    evidence = [
        EvidenceStub(
            id=20,
            document_type="Security Policy",
            extraction_confidence=0.40,
        ),
    ]

    work_plan = build_assessment_work_plan(
        applicability,
        evidence,
    )

    assert any(
        item.workflow_action == "Analyst Validate"
        for item in work_plan.items
    )


def test_evidence_with_exception_routes_to_analyst():
    applicability = evaluate_applicability(
        get_tier_profile(80),
        VendorRiskContext(),
    )

    evidence = [
        EvidenceStub(
            id=30,
            document_type="SOC 2 Type II",
            exceptions_count=2,
        ),
    ]

    work_plan = build_assessment_work_plan(
        applicability,
        evidence,
    )

    assert any(
        item.workflow_action == "Analyst Validate"
        for item in work_plan.items
    )


def test_question_traceability_exists():
    applicability = build_contextual_profile()

    work_plan = build_assessment_work_plan(
        applicability,
        [],
    )

    vendor_questions = [
        item
        for item in work_plan.items
        if item.workflow_action == "Ask Vendor"
    ]

    assert vendor_questions

    assert all(
        item.control_id
        for item in vendor_questions
    )

    assert all(
        item.question_id
        for item in vendor_questions
    )

    assert all(
        item.question
        for item in vendor_questions
    )


def test_policy_version_is_exposed():
    applicability = build_contextual_profile()

    work_plan = build_assessment_work_plan(
        applicability,
        [],
    )

    assert (
        work_plan.policy_version
        == ORCHESTRATOR_POLICY_VERSION
    )

    assert work_plan.policy_version == "AO-1.0"