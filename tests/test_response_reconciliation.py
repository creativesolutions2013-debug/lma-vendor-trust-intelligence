from dataclasses import dataclass

from src.response_reconciliation import (
    reconcile_evidence_response,
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


def test_missing_request_remains_outstanding():
    result = reconcile_evidence_response(
        ["Penetration Test"],
        [],
    )

    assert result.outstanding == 1
    assert result.satisfied == 0
    assert (
        result.items[0].status
        == "Outstanding"
    )


def test_current_evidence_satisfies_request():
    evidence = FakeEvidence(
        id=1,
        document_type="Penetration Test",
        document_name="2026 Pen Test",
        expiration_date="2027-06-01",
    )

    result = reconcile_evidence_response(
        ["Penetration Test"],
        [evidence],
    )

    assert result.satisfied == 1
    assert result.outstanding == 0
    assert (
        result.items[0].status
        == "Satisfied"
    )


def test_exception_requires_validation():
    evidence = FakeEvidence(
        id=2,
        document_type="Security Policy",
        document_name="Security Policy",
        expiration_date="2027-06-01",
        exceptions_count=1,
    )

    result = reconcile_evidence_response(
        ["Security Policy"],
        [evidence],
    )

    assert (
        result.validation_required == 1
    )
    assert (
        result.items[0].status
        == "Validate"
    )


def test_expired_response_remains_outstanding():
    evidence = FakeEvidence(
        id=3,
        document_type="Penetration Test",
        document_name="Old Pen Test",
        expiration_date="2025-01-01",
    )

    result = reconcile_evidence_response(
        ["Penetration Test"],
        [evidence],
    )

    assert result.outstanding == 1


def test_completion_percentage():
    evidence = FakeEvidence(
        id=4,
        document_type="Security Policy",
        document_name="Security Policy",
        expiration_date="2027-06-01",
    )

    result = reconcile_evidence_response(
        [
            "Security Policy",
            "Incident Response Plan",
        ],
        [evidence],
    )

    assert result.total_requested == 2
    assert result.satisfied == 1
    assert result.outstanding == 1
    assert result.completion_percent == 50


def test_no_requested_items_is_complete():
    result = reconcile_evidence_response(
        [],
        [],
    )

    assert result.total_requested == 0
    assert result.outstanding == 0
    assert result.completion_percent == 100
