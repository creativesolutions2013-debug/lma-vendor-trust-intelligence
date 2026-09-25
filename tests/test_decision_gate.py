
from dataclasses import dataclass
from src.decision_gate import evaluate_vendor_decision


@dataclass
class Finding:
    title: str
    severity: str
    status: str


@dataclass
class Assessment:
    assessment_type: str
    status: str


def test_clean_vendor_can_be_approved():
    result = evaluate_vendor_decision(
        evidence_completion_percent=100,
        findings=[],
        assessments=[],
        residual_risk=22,
    )

    assert result.outcome == "Approve"
    assert result.reasons == ()


def test_incomplete_required_evidence_blocks_approval():
    result = evaluate_vendor_decision(
        evidence_completion_percent=75,
        findings=[],
        assessments=[],
        residual_risk=20,
    )

    assert result.outcome == "Further Review Required"
    assert any(r.code == "evidence_incomplete" for r in result.reasons)


def test_open_high_finding_blocks_approval():
    result = evaluate_vendor_decision(
        evidence_completion_percent=100,
        findings=[
            Finding(
                title="MFA gap",
                severity="High",
                status="In Remediation",
            )
        ],
        assessments=[],
        residual_risk=30,
    )

    assert result.outcome == "Further Review Required"
    assert any(r.code == "high_risk_finding" for r in result.reasons)


def test_risk_accepted_high_finding_does_not_block():
    result = evaluate_vendor_decision(
        evidence_completion_percent=100,
        findings=[
            Finding(
                title="MFA gap",
                severity="High",
                status="Risk Accepted",
            )
        ],
        assessments=[],
        residual_risk=30,
    )

    assert result.outcome == "Approve"


def test_open_triggered_reassessment_blocks_approval():
    result = evaluate_vendor_decision(
        evidence_completion_percent=100,
        findings=[],
        assessments=[
            Assessment(
                assessment_type="Incident-Triggered Reassessment",
                status="Not Started",
            )
        ],
        residual_risk=35,
    )

    assert result.outcome == "Further Review Required"
    assert any(r.code == "open_reassessment" for r in result.reasons)


def test_high_residual_risk_requires_conditions_when_no_blockers():
    result = evaluate_vendor_decision(
        evidence_completion_percent=100,
        findings=[],
        assessments=[],
        residual_risk=58,
    )

    assert result.outcome == "Approve with Conditions"
    assert any(r.code == "high_residual_risk" for r in result.reasons)


def test_critical_residual_risk_blocks_approval():
    result = evaluate_vendor_decision(
        evidence_completion_percent=100,
        findings=[],
        assessments=[],
        residual_risk=81,
    )

    assert result.outcome == "Further Review Required"
    assert any(r.code == "critical_residual_risk" for r in result.reasons)
