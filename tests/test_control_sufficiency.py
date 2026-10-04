from dataclasses import dataclass
from datetime import date

from src.control_sufficiency import (
    CONTROL_SUFFICIENCY_POLICY_VERSION,
    EvidenceControlClaim,
    evaluate_control_evidence,
    evaluate_control_set,
)


@dataclass
class EvidenceStub:
    id: int
    document_type: str = "SOC 2 Type II"
    document_name: str = "Vendor SOC 2"
    expiration_date: str | None = None
    status: str = "Received"
    exceptions_count: int = 0
    detected_exceptions: str = ""
    extraction_confidence: float = 0.95


TODAY = date(
    2026,
    10,
    3,
)


def test_current_tested_in_scope_evidence_is_supported():
    evidence = [
        EvidenceStub(
            id=1,
            expiration_date="2027-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=1,
            control_id="IAM-01",
            covered=True,
            tested=True,
            scope_matches=True,
            service_matches=True,
            extraction_confidence=0.95,
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "SUPPORTED"
    assert decision.supporting_evidence_ids == (1,)
    assert decision.analyst_review_required is False


def test_expired_evidence_is_not_sufficient():
    evidence = [
        EvidenceStub(
            id=2,
            expiration_date="2025-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=2,
            control_id="IAM-01",
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "UNSUPPORTED"


def test_scope_mismatch_requires_review():
    evidence = [
        EvidenceStub(
            id=3,
            expiration_date="2027-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=3,
            control_id="IAM-01",
            scope_matches=False,
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "REVIEW"
    assert decision.analyst_review_required is True


def test_service_mismatch_requires_review():
    evidence = [
        EvidenceStub(
            id=4,
            expiration_date="2027-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=4,
            control_id="IAM-01",
            service_matches=False,
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "REVIEW"


def test_control_not_tested_requires_review():
    evidence = [
        EvidenceStub(
            id=5,
            expiration_date="2027-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=5,
            control_id="IAM-01",
            tested=False,
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "REVIEW"


def test_low_confidence_claim_requires_review():
    evidence = [
        EvidenceStub(
            id=6,
            expiration_date="2027-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=6,
            control_id="IAM-01",
            extraction_confidence=0.40,
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "REVIEW"
    assert decision.analyst_review_required is True


def test_control_exception_results_in_partial():
    evidence = [
        EvidenceStub(
            id=7,
            expiration_date="2027-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=7,
            control_id="IAM-01",
            exception_present=True,
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "PARTIAL"
    assert decision.analyst_review_required is True


def test_document_level_exception_results_in_partial():
    evidence = [
        EvidenceStub(
            id=8,
            expiration_date="2027-01-01",
            exceptions_count=1,
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=8,
            control_id="IAM-01",
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "PARTIAL"


def test_expiring_soon_evidence_results_in_partial():
    evidence = [
        EvidenceStub(
            id=9,
            expiration_date="2026-10-20",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=9,
            control_id="IAM-01",
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "PARTIAL"


def test_no_claim_means_unsupported():
    decision = evaluate_control_evidence(
        "IAM-01",
        [],
        [],
        today=TODAY,
    )

    assert decision.status == "UNSUPPORTED"


def test_strong_evidence_can_support_control_despite_second_review_item():
    evidence = [
        EvidenceStub(
            id=10,
            expiration_date="2027-01-01",
        ),
        EvidenceStub(
            id=11,
            expiration_date="2027-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=10,
            control_id="IAM-01",
        ),
        EvidenceControlClaim(
            evidence_id=11,
            control_id="IAM-01",
            scope_matches=False,
        ),
    ]

    decision = evaluate_control_evidence(
        "IAM-01",
        evidence,
        claims,
        today=TODAY,
    )

    assert decision.status == "SUPPORTED"
    assert 10 in decision.supporting_evidence_ids
    assert 11 in decision.evidence_review_ids


def test_control_set_returns_one_decision_per_control():
    evidence = [
        EvidenceStub(
            id=20,
            expiration_date="2027-01-01",
        ),
    ]

    claims = [
        EvidenceControlClaim(
            evidence_id=20,
            control_id="IAM-01",
        ),
    ]

    decisions = evaluate_control_set(
        [
            "IAM-01",
            "VM-01",
        ],
        evidence,
        claims,
        today=TODAY,
    )

    assert len(decisions) == 2

    status_by_control = {
        decision.control_id:
            decision.status
        for decision in decisions
    }

    assert status_by_control["IAM-01"] == "SUPPORTED"
    assert status_by_control["VM-01"] == "UNSUPPORTED"


def test_policy_version_is_exposed():
    decision = evaluate_control_evidence(
        "IAM-01",
        [],
        [],
        today=TODAY,
    )

    assert (
        decision.policy_version
        == CONTROL_SUFFICIENCY_POLICY_VERSION
    )

    assert decision.policy_version == "CS-1.0"