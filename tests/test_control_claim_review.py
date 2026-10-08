import pytest

from src.control_claim_review import (
    CONTROL_CLAIM_REVIEW_POLICY_VERSION,
    AnalystClaimConfirmation,
    review_control_claim_candidate,
)

from src.control_claims import (
    ControlClaimCandidate,
)


ALLOWED_CONTROLS = (
    "IAM-01",
    "PAM-01",
    "VM-01",
)


def candidate(
    *,
    control_id="IAM-01",
    confidence=0.90,
):
    return ControlClaimCandidate(
        control_id=control_id,
        statement=(
            "Evidence may support logical "
            "access management."
        ),
        source_reference=(
            "SOC2 Evidence ID 10"
        ),
        confidence=confidence,
    )


def complete_confirmation(
    **overrides,
):
    values = {
        "covered": True,
        "tested": True,
        "scope_matches": True,
        "service_matches": True,
        "exception_present": False,
        "confirmed_by": (
            "analyst@example.com"
        ),
        "analyst_rationale": (
            "Reviewed the control test and "
            "confirmed scope and service alignment."
        ),
    }

    values.update(
        overrides
    )

    return AnalystClaimConfirmation(
        **values
    )


def test_complete_confirmation_creates_accepted_claim():
    review = (
        review_control_claim_candidate(
            10,
            candidate(),
            complete_confirmation(),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )
    )

    assert (
        review.complete_confirmation
        is True
    )

    assert (
        review.result.claim
        is not None
    )

    assert (
        review.result.claim.control_id
        == "IAM-01"
    )

    assert (
        review.result.provenance
        .generation_status
        == "ACCEPTED"
    )

    assert (
        review.result.provenance
        .human_confirmed
        is True
    )


def test_missing_required_fact_does_not_create_claim():
    review = (
        review_control_claim_candidate(
            11,
            candidate(),
            complete_confirmation(
                tested=None
            ),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )
    )

    assert (
        review.complete_confirmation
        is False
    )

    assert (
        review.result.claim
        is None
    )

    assert (
        review.result.provenance
        .generation_status
        == "REVIEW"
    )


def test_confirmed_exception_is_preserved():
    review = (
        review_control_claim_candidate(
            12,
            candidate(),
            complete_confirmation(
                exception_present=True
            ),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )
    )

    assert (
        review.result.claim
        is not None
    )

    assert (
        review.result.claim
        .exception_present
        is True
    )

    assert (
        review.result.provenance
        .review_required
        is True
    )


def test_low_confidence_candidate_can_be_human_confirmed():
    review = (
        review_control_claim_candidate(
            13,
            candidate(
                confidence=0.40
            ),
            complete_confirmation(),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )
    )

    assert (
        review.result.claim
        is not None
    )

    assert (
        review.result.claim
        .extraction_confidence
        == 0.40
    )

    assert (
        review.result.provenance
        .human_confirmed
        is True
    )

    assert (
        review.result.provenance
        .review_required
        is True
    )


def test_out_of_scope_control_remains_rejected():
    review = (
        review_control_claim_candidate(
            14,
            candidate(
                control_id="ENC-01"
            ),
            complete_confirmation(),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )
    )

    assert (
        review.result.claim
        is None
    )

    assert (
        review.result.provenance
        .generation_status
        == "REJECTED"
    )


def test_reviewer_identity_is_preserved():
    review = (
        review_control_claim_candidate(
            15,
            candidate(),
            complete_confirmation(
                confirmed_by=(
                    "security-analyst-1"
                )
            ),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )
    )

    assert (
        review.confirmed_by
        == "security-analyst-1"
    )

    assert (
        review.result.provenance
        .confirmed_by
        == "security-analyst-1"
    )


def test_rationale_is_required():
    with pytest.raises(
        ValueError,
        match="rationale",
    ):
        review_control_claim_candidate(
            16,
            candidate(),
            complete_confirmation(
                analyst_rationale=""
            ),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )


def test_confirmed_by_is_required():
    with pytest.raises(
        ValueError,
        match="confirmed_by",
    ):
        review_control_claim_candidate(
            17,
            candidate(),
            complete_confirmation(
                confirmed_by=""
            ),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )


def test_policy_version_is_exposed():
    review = (
        review_control_claim_candidate(
            18,
            candidate(),
            complete_confirmation(),
            allowed_control_ids=(
                ALLOWED_CONTROLS
            ),
        )
    )

    assert (
        review.policy_version
        == CONTROL_CLAIM_REVIEW_POLICY_VERSION
    )

    assert (
        review.policy_version
        == "CCR-1.0"
    )