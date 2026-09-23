from dataclasses import dataclass
from datetime import date

from src.assurance import evaluate_evidence_coverage


@dataclass
class FakeEvidence:
    id: int
    document_type: str
    document_name: str
    expiration_date: str | None = None
    status: str = "Received"


def test_complete_required_evidence_reports_100_percent():
    required = (
        "Penetration Test",
        "Security Policy",
    )
    evidence = [
        FakeEvidence(1, "Penetration Test", "2026 penetration test"),
        FakeEvidence(2, "Security Policy", "Information Security Policy"),
    ]

    coverage = evaluate_evidence_coverage(
        required,
        evidence,
        today=date(2026, 9, 21),
    )

    assert coverage.total_required == 2
    assert coverage.satisfied_required == 2
    assert coverage.completion_percent == 100


def test_missing_evidence_reduces_completion():
    coverage = evaluate_evidence_coverage(
        ("Penetration Test", "Security Policy"),
        [FakeEvidence(1, "Security Policy", "Security Policy")],
        today=date(2026, 9, 21),
    )

    assert coverage.completion_percent == 50
    assert coverage.items[0].status == "Missing"


def test_expired_evidence_does_not_count_as_satisfied():
    coverage = evaluate_evidence_coverage(
        ("Penetration Test",),
        [
            FakeEvidence(
                1,
                "Penetration Test",
                "Old penetration test",
                expiration_date="2026-09-01",
            )
        ],
        today=date(2026, 9, 21),
    )

    assert coverage.completion_percent == 0
    assert coverage.items[0].status == "Expired"


def test_expiring_soon_evidence_counts_but_is_flagged():
    coverage = evaluate_evidence_coverage(
        ("Penetration Test",),
        [
            FakeEvidence(
                1,
                "Penetration Test",
                "Current penetration test",
                expiration_date="2026-10-15",
            )
        ],
        today=date(2026, 9, 21),
    )

    assert coverage.completion_percent == 100
    assert coverage.items[0].status == "Expiring Soon"


def test_if_available_requirement_is_optional():
    coverage = evaluate_evidence_coverage(
        (
            "Security Policy",
            "SOC 2 / ISO 27001 if available",
        ),
        [FakeEvidence(1, "Security Policy", "Security Policy")],
        today=date(2026, 9, 21),
    )

    assert coverage.total_required == 1
    assert coverage.satisfied_required == 1
    assert coverage.completion_percent == 100
    assert coverage.items[1].required is False
