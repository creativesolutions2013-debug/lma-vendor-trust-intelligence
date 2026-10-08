import json
from dataclasses import dataclass

from src.evidence_control_claim_adapter import (
    ADAPTER_POLICY_VERSION,
    build_evidence_control_candidates,
)


@dataclass
class EvidenceStub:
    id: int
    document_type: str
    document_name: str = "Vendor Evidence"
    extraction_confidence: float = 0.90
    detected_exceptions: str = ""


ALLOWED = (
    "GOV-01",
    "IAM-01",
    "PAM-01",
    "ENC-01",
    "VM-01",
    "SDLC-01",
    "LOG-01",
    "IR-01",
    "BCP-01",
    "TPRM-01",
    "DATA-01",
)


def test_soc2_creates_possible_control_candidates():
    result = (
        build_evidence_control_candidates(
            EvidenceStub(
                id=1,
                document_type=(
                    "SOC 2 Type II"
                ),
            ),
            allowed_control_ids=ALLOWED,
        )
    )

    control_ids = {
        candidate.control_id
        for candidate
        in result.candidates
    }

    assert "IAM-01" in control_ids
    assert "GOV-01" in control_ids
    assert "LOG-01" in control_ids


def test_document_mapping_does_not_invent_assurance_facts():
    result = (
        build_evidence_control_candidates(
            EvidenceStub(
                id=2,
                document_type=(
                    "SOC 2 Type II"
                ),
            ),
            allowed_control_ids=ALLOWED,
        )
    )

    candidate = next(
        item
        for item in result.candidates
        if item.control_id
        == "IAM-01"
    )

    assert candidate.covered is None
    assert candidate.tested is None
    assert candidate.scope_matches is None
    assert candidate.service_matches is None
    assert (
        candidate.exception_present
        is None
    )


def test_detected_exception_creates_exception_candidate():
    exceptions = json.dumps(
        [
            {
                "control_id": (
                    "IAM-01"
                ),
                "description": (
                    "One terminated account "
                    "remained active."
                ),
                "severity": "Moderate",
            }
        ]
    )

    result = (
        build_evidence_control_candidates(
            EvidenceStub(
                id=3,
                document_type=(
                    "SOC 2 Type II"
                ),
                detected_exceptions=(
                    exceptions
                ),
            ),
            allowed_control_ids=ALLOWED,
        )
    )

    iam = next(
        item
        for item in result.candidates
        if item.control_id
        == "IAM-01"
    )

    assert (
        iam.exception_present
        is True
    )

    assert (
        "terminated account"
        in iam.statement
    )


def test_exception_candidate_replaces_generic_candidate():
    exceptions = json.dumps(
        [
            {
                "control_id": (
                    "IAM-01"
                ),
                "description": (
                    "Exception found."
                ),
            }
        ]
    )

    result = (
        build_evidence_control_candidates(
            EvidenceStub(
                id=4,
                document_type=(
                    "SOC 2 Type II"
                ),
                detected_exceptions=(
                    exceptions
                ),
            ),
            allowed_control_ids=ALLOWED,
        )
    )

    iam_candidates = [
        item
        for item in result.candidates
        if item.control_id
        == "IAM-01"
    ]

    assert len(
        iam_candidates
    ) == 1

    assert (
        iam_candidates[0]
        .exception_present
        is True
    )


def test_unapproved_controls_are_not_created():
    result = (
        build_evidence_control_candidates(
            EvidenceStub(
                id=5,
                document_type=(
                    "SOC 2 Type II"
                ),
            ),
            allowed_control_ids=(
                "IAM-01",
            ),
        )
    )

    assert {
        item.control_id
        for item
        in result.candidates
    } == {
        "IAM-01"
    }


def test_penetration_test_maps_to_vm_and_sdlc():
    result = (
        build_evidence_control_candidates(
            EvidenceStub(
                id=6,
                document_type=(
                    "Penetration Test"
                ),
            ),
            allowed_control_ids=ALLOWED,
        )
    )

    ids = {
        item.control_id
        for item
        in result.candidates
    }

    assert ids == {
        "VM-01",
        "SDLC-01",
    }


def test_confidence_is_preserved():
    result = (
        build_evidence_control_candidates(
            EvidenceStub(
                id=7,
                document_type=(
                    "Incident Response Plan"
                ),
                extraction_confidence=0.73,
            ),
            allowed_control_ids=ALLOWED,
        )
    )

    candidate = (
        result.candidates[0]
    )

    assert (
        candidate.confidence
        == 0.73
    )


def test_policy_version_is_exposed():
    result = (
        build_evidence_control_candidates(
            EvidenceStub(
                id=8,
                document_type=(
                    "Security Policy"
                ),
            ),
            allowed_control_ids=ALLOWED,
        )
    )

    assert (
        result.policy_version
        == ADAPTER_POLICY_VERSION
    )

    assert (
        result.policy_version
        == "ECA-1.0"
    )