from dataclasses import dataclass

from src.assurance import EvidenceCoverage, EvidenceRequirementResult
from src.attention import calculate_vendor_attention, priority_from_score


@dataclass
class Finding:
    title: str
    severity: str
    status: str = "Open"


@dataclass
class Event:
    event_type: str
    severity: str
    status: str = "Open"
    requires_review: bool = True


def coverage(*items):
    return EvidenceCoverage(
        total_required=len([item for item in items if item.required]),
        satisfied_required=len(
            [
                item
                for item in items
                if item.required
                and item.status in {"Satisfied", "Expiring Soon"}
            ]
        ),
        completion_percent=0,
        items=tuple(items),
    )


def item(requirement, status, required=True):
    return EvidenceRequirementResult(
        requirement=requirement,
        required=required,
        status=status,
    )


def test_priority_thresholds():
    assert priority_from_score(75) == "P1"
    assert priority_from_score(50) == "P2"
    assert priority_from_score(25) == "P3"
    assert priority_from_score(24) == "P4"


def test_tier1_missing_critical_evidence_surfaces_high_priority():
    result = calculate_vendor_attention(
        tier_code="T1",
        residual_risk=56,
        evidence_coverage=coverage(
            item("Penetration Test", "Missing"),
            item("BCP / DR Test", "Missing"),
            item("Security Policy", "Satisfied"),
        ),
    )

    assert result.score >= 50
    assert result.priority in {"P1", "P2"}
    assert any("Penetration Test" in reason.reason for reason in result.reasons)


def test_high_finding_increases_attention():
    baseline = calculate_vendor_attention(
        tier_code="T2",
        residual_risk=40,
        evidence_coverage=coverage(
            item("Security Policy", "Satisfied"),
        ),
    )

    with_finding = calculate_vendor_attention(
        tier_code="T2",
        residual_risk=40,
        evidence_coverage=coverage(
            item("Security Policy", "Satisfied"),
        ),
        findings=[Finding("MFA gap", "High")],
    )

    assert with_finding.score > baseline.score
    assert any("MFA gap" in reason.reason for reason in with_finding.reasons)


def test_closed_findings_and_events_do_not_increase_attention():
    result = calculate_vendor_attention(
        tier_code="T3",
        residual_risk=20,
        evidence_coverage=coverage(),
        findings=[Finding("Old issue", "Critical", status="Closed")],
        monitoring_events=[
            Event(
                "Old rating event",
                "Critical",
                status="Closed",
            )
        ],
    )

    assert result.score == 12
    assert result.priority == "P4"


def test_monitoring_event_contributes_explainable_reason():
    result = calculate_vendor_attention(
        tier_code="T2",
        residual_risk=45,
        evidence_coverage=coverage(),
        monitoring_events=[
            Event(
                "Security rating deterioration",
                "High",
            )
        ],
    )

    assert any(
        "Security rating deterioration" in reason.reason
        for reason in result.reasons
    )


def test_evidence_gap_is_displayed_before_generic_residual_risk():
    result = calculate_vendor_attention(
        tier_code="T1",
        residual_risk=80,
        evidence_coverage=coverage(
            item("Penetration Test", "Missing"),
        ),
    )

    assert result.reasons[0].reason == "Penetration Test: Missing"
    assert result.reasons[0].category == "evidence"


def test_open_finding_is_displayed_before_evidence_gap():
    result = calculate_vendor_attention(
        tier_code="T1",
        residual_risk=80,
        evidence_coverage=coverage(
            item("Penetration Test", "Missing"),
        ),
        findings=[Finding("MFA not enforced", "High")],
    )

    assert "MFA not enforced" in result.reasons[0].reason
    assert result.reasons[0].category == "finding"
