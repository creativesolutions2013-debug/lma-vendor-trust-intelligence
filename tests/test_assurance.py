from dataclasses import dataclass
from datetime import date

from src.assurance import (
    evaluate_evidence_coverage,
)
from src.tiering import (
    EvidenceRequirement,
    get_tier_profile,
)


@dataclass
class FakeEvidence:
    id: int
    document_type: str
    document_name: str
    expiration_date: str | None = None
    status: str = "Received"


TODAY = date(
    2026,
    9,
    21,
)


def test_complete_required_evidence_reports_100_percent():
    required = (
        "Penetration Test",
        "Security Policy",
    )

    evidence = [
        FakeEvidence(
            1,
            "Penetration Test",
            "2026 penetration test",
        ),
        FakeEvidence(
            2,
            "Security Policy",
            "Information Security Policy",
        ),
    ]

    coverage = evaluate_evidence_coverage(
        required,
        evidence,
        today=TODAY,
    )

    assert coverage.total_required == 2
    assert coverage.satisfied_required == 2
    assert coverage.completion_percent == 100


def test_missing_evidence_reduces_completion():
    coverage = evaluate_evidence_coverage(
        (
            "Penetration Test",
            "Security Policy",
        ),
        [
            FakeEvidence(
                1,
                "Security Policy",
                "Security Policy",
            )
        ],
        today=TODAY,
    )

    assert coverage.completion_percent == 50
    assert coverage.items[0].status == "Missing"


def test_expired_evidence_does_not_count_as_satisfied():
    coverage = evaluate_evidence_coverage(
        (
            "Penetration Test",
        ),
        [
            FakeEvidence(
                1,
                "Penetration Test",
                "Old penetration test",
                expiration_date="2026-09-01",
            )
        ],
        today=TODAY,
    )

    assert coverage.completion_percent == 0
    assert coverage.items[0].status == "Expired"


def test_expiring_soon_evidence_counts_but_is_flagged():
    coverage = evaluate_evidence_coverage(
        (
            "Penetration Test",
        ),
        [
            FakeEvidence(
                1,
                "Penetration Test",
                "Current penetration test",
                expiration_date="2026-10-15",
            )
        ],
        today=TODAY,
    )

    assert coverage.completion_percent == 100

    assert (
        coverage.items[0].status
        == "Expiring Soon"
    )


def test_if_available_requirement_is_optional():
    coverage = evaluate_evidence_coverage(
        (
            "Security Policy",
            "SOC 2 / ISO 27001 if available",
        ),
        [
            FakeEvidence(
                1,
                "Security Policy",
                "Security Policy",
            )
        ],
        today=TODAY,
    )

    assert coverage.total_required == 1
    assert coverage.satisfied_required == 1
    assert coverage.completion_percent == 100
    assert coverage.items[1].required is False


def test_structured_evidence_requirement_is_supported():
    requirement = EvidenceRequirement(
        evidence_id="EVID-PENTEST",
        evidence_type="Penetration Test",
        mandatory=True,
        freshness_months=12,
    )

    coverage = evaluate_evidence_coverage(
        (
            requirement,
        ),
        [
            FakeEvidence(
                10,
                "Penetration Test",
                "Current penetration test",
            )
        ],
        today=TODAY,
    )

    assert coverage.total_required == 1
    assert coverage.satisfied_required == 1
    assert coverage.completion_percent == 100

    assert (
        coverage.items[0].requirement
        == "Penetration Test"
    )

    assert coverage.items[0].required is True


def test_structured_optional_requirement_respects_mandatory_flag():
    requirement = EvidenceRequirement(
        evidence_id="EVID-OPTIONAL",
        evidence_type="Optional evidence package",
        mandatory=False,
    )

    coverage = evaluate_evidence_coverage(
        (
            requirement,
        ),
        [],
        today=TODAY,
    )

    assert coverage.total_required == 0
    assert coverage.satisfied_required == 0
    assert coverage.completion_percent == 100

    assert coverage.items[0].status == "Missing"
    assert coverage.items[0].required is False


def test_tier_profile_required_evidence_can_be_evaluated_directly():
    profile = get_tier_profile(
        80,
    )

    evidence = [
        FakeEvidence(
            20,
            "SOC 2 Type II",
            "Vendor SOC 2 Type II",
        ),
        FakeEvidence(
            21,
            "Penetration Test",
            "2026 Penetration Test",
        ),
        FakeEvidence(
            22,
            "BCP / DR Test",
            "2026 BCP DR Test",
        ),
        FakeEvidence(
            23,
            "Incident Response Plan",
            "Incident Response Plan",
        ),
        FakeEvidence(
            24,
            "Security Policy",
            "Information Security Policy",
        ),
        FakeEvidence(
            25,
            "Architecture Diagram",
            "Production Architecture Diagram",
        ),
    ]

    coverage = evaluate_evidence_coverage(
        profile.required_evidence,
        evidence,
        today=TODAY,
    )

    assert coverage.total_required == 6
    assert coverage.satisfied_required == 6
    assert coverage.completion_percent == 100

    assert all(
        isinstance(
            item.requirement,
            str,
        )
        for item in coverage.items
    )