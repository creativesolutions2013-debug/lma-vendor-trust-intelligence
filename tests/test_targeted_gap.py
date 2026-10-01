from dataclasses import dataclass
from datetime import date

from src.targeted_gap import (
    analyze_targeted_evidence_gaps,
)


@dataclass
class FakeEvidence:
    id: int
    document_type: str
    document_name: str
    expiration_date: str | None = None
    status: str = "Received"
    exceptions_count: int = 0
    detected_exceptions: str | None = None
    extraction_confidence: float | None = 0.90


TODAY = date(2026, 9, 30)


def test_current_evidence_is_reused():
    evidence = FakeEvidence(
        id=1,
        document_type="Penetration Test",
        document_name="2026 Pen Test",
        expiration_date="2027-06-01",
    )

    result = analyze_targeted_evidence_gaps(
        ["Penetration Test"],
        [evidence],
        today=TODAY,
    )

    assert result.items[0].workflow_action == "Reuse"
    assert result.items[0].evidence_state == "Current"


def test_missing_evidence_requests_vendor():
    result = analyze_targeted_evidence_gaps(
        ["Penetration Test"],
        [],
        today=TODAY,
    )

    assert (
        result.items[0].workflow_action
        == "Request Vendor"
    )
    assert result.items[0].evidence_state == "Missing"


def test_expired_evidence_requests_vendor():
    evidence = FakeEvidence(
        id=2,
        document_type="Penetration Test",
        document_name="Old Pen Test",
        expiration_date="2026-01-01",
    )

    result = analyze_targeted_evidence_gaps(
        ["Penetration Test"],
        [evidence],
        today=TODAY,
    )

    assert (
        result.items[0].workflow_action
        == "Request Vendor"
    )
    assert result.items[0].evidence_state == "Expired"


def test_expiring_evidence_requires_validation():
    evidence = FakeEvidence(
        id=3,
        document_type="Penetration Test",
        document_name="Current Pen Test",
        expiration_date="2026-10-20",
    )

    result = analyze_targeted_evidence_gaps(
        ["Penetration Test"],
        [evidence],
        today=TODAY,
    )

    assert (
        result.items[0].workflow_action
        == "Analyst Validate"
    )
    assert (
        result.items[0].evidence_state
        == "Expiring Soon"
    )


def test_current_evidence_with_exception_requires_validation():
    evidence = FakeEvidence(
        id=4,
        document_type="Penetration Test",
        document_name="Pen Test with Finding",
        expiration_date="2027-01-01",
        exceptions_count=1,
    )

    result = analyze_targeted_evidence_gaps(
        ["Penetration Test"],
        [evidence],
        today=TODAY,
    )

    assert (
        result.items[0].workflow_action
        == "Analyst Validate"
    )
    assert (
        result.items[0].evidence_state
        == "Current with Exceptions"
    )


def test_low_confidence_evidence_requires_validation():
    evidence = FakeEvidence(
        id=5,
        document_type="Security Policy",
        document_name="Security Policy",
        expiration_date="2027-01-01",
        extraction_confidence=0.50,
    )

    result = analyze_targeted_evidence_gaps(
        ["Security Policy"],
        [evidence],
        today=TODAY,
    )

    assert (
        result.items[0].workflow_action
        == "Analyst Validate"
    )
    assert (
        result.items[0].evidence_state
        == "Current / Low Confidence"
    )


def test_summary_counts_actions():
    records = [
        FakeEvidence(
            id=6,
            document_type="Security Policy",
            document_name="Security Policy",
            expiration_date="2027-01-01",
        ),
        FakeEvidence(
            id=7,
            document_type="Penetration Test",
            document_name="Old Pen Test",
            expiration_date="2026-01-01",
        ),
    ]

    result = analyze_targeted_evidence_gaps(
        [
            "Security Policy",
            "Penetration Test",
            "Incident Response Plan",
        ],
        records,
        today=TODAY,
    )

    assert result.total_requirements == 3
    assert result.reusable == 1
    assert result.vendor_requests == 2
    assert result.analyst_validation == 0


def test_scope_current_security_policy_matches_existing_policy():
    evidence = FakeEvidence(
        id=8,
        document_type="Security Policy",
        document_name="Enterprise Security Policy",
        expiration_date="2027-06-01",
    )

    result = analyze_targeted_evidence_gaps(
        ["Current Security Policy"],
        [evidence],
        today=TODAY,
    )

    assert result.items[0].workflow_action == "Reuse"
    assert result.items[0].requirement == "Current Security Policy"


def test_scope_latest_pen_test_matches_existing_pen_test():
    evidence = FakeEvidence(
        id=9,
        document_type="Penetration Test",
        document_name="2026 External Penetration Test",
        expiration_date="2027-06-01",
    )

    result = analyze_targeted_evidence_gaps(
        ["Latest penetration test status or report"],
        [evidence],
        today=TODAY,
    )

    assert result.items[0].workflow_action == "Reuse"
