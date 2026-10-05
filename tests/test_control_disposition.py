from src.control_disposition import (
    CONTROL_DISPOSITION_POLICY_VERSION,
    AnalystDisposition,
    DISPOSITION_ANALYST_REVIEW,
    DISPOSITION_COMPENSATING_CONTROL,
    DISPOSITION_NOT_APPLICABLE,
    DISPOSITION_NOT_SATISFIED,
    DISPOSITION_PARTIALLY_SATISFIED,
    DISPOSITION_SATISFIED,
    evaluate_control_disposition,
)

from src.control_sufficiency import (
    ControlEvidenceDecision,
)


def sufficiency(
    *,
    status: str,
    review_required: bool = False,
) -> ControlEvidenceDecision:
    return ControlEvidenceDecision(
        control_id="IAM-01",
        status=status,
        supporting_evidence_ids=(10,),
        evidence_review_ids=(
            (11,)
            if review_required
            else ()
        ),
        reasons=(
            "Evidence evaluation reason.",
        ),
        analyst_review_required=review_required,
    )


def test_supported_evidence_recommends_satisfied():
    result = evaluate_control_disposition(
        sufficiency(
            status="SUPPORTED",
        )
    )

    assert (
        result.recommended_disposition
        == DISPOSITION_SATISFIED
    )

    assert (
        result.final_disposition
        == DISPOSITION_SATISFIED
    )

    assert result.human_confirmed is False
    assert result.analyst_review_required is False


def test_supported_with_secondary_review_preserves_review_flag():
    result = evaluate_control_disposition(
        sufficiency(
            status="SUPPORTED",
            review_required=True,
        )
    )

    assert (
        result.recommended_disposition
        == DISPOSITION_SATISFIED
    )

    assert result.analyst_review_required is True
    assert result.review_evidence_ids == (11,)


def test_partial_recommends_partially_satisfied():
    result = evaluate_control_disposition(
        sufficiency(
            status="PARTIAL",
            review_required=True,
        )
    )

    assert (
        result.recommended_disposition
        == DISPOSITION_PARTIALLY_SATISFIED
    )

    assert result.analyst_review_required is True


def test_review_status_requires_analyst_review():
    result = evaluate_control_disposition(
        sufficiency(
            status="REVIEW",
            review_required=True,
        )
    )

    assert (
        result.final_disposition
        == DISPOSITION_ANALYST_REVIEW
    )

    assert result.analyst_review_required is True


def test_unsupported_does_not_auto_fail_control():
    result = evaluate_control_disposition(
        sufficiency(
            status="UNSUPPORTED",
        )
    )

    assert (
        result.final_disposition
        == DISPOSITION_ANALYST_REVIEW
    )

    assert (
        result.final_disposition
        != DISPOSITION_NOT_SATISFIED
    )

    assert result.analyst_review_required is True

    assert any(
        "not treated as proof"
        in reason
        for reason in result.reasons
    )


def test_analyst_can_confirm_not_satisfied():
    result = evaluate_control_disposition(
        sufficiency(
            status="UNSUPPORTED",
        ),
        AnalystDisposition(
            control_id="IAM-01",
            disposition=(
                DISPOSITION_NOT_SATISFIED
            ),
            rationale=(
                "Vendor confirmed MFA is not enabled."
            ),
            decided_by="analyst@example.com",
        ),
    )

    assert (
        result.final_disposition
        == DISPOSITION_NOT_SATISFIED
    )

    assert result.human_confirmed is True
    assert result.analyst_review_required is False
    assert result.decided_by == "analyst@example.com"


def test_analyst_can_mark_not_applicable():
    result = evaluate_control_disposition(
        sufficiency(
            status="REVIEW",
            review_required=True,
        ),
        AnalystDisposition(
            control_id="IAM-01",
            disposition=(
                DISPOSITION_NOT_APPLICABLE
            ),
            rationale=(
                "Service does not provide interactive "
                "user authentication."
            ),
            decided_by="analyst@example.com",
        ),
    )

    assert (
        result.final_disposition
        == DISPOSITION_NOT_APPLICABLE
    )

    assert result.human_confirmed is True


def test_compensating_control_requires_description():
    try:
        evaluate_control_disposition(
            sufficiency(
                status="PARTIAL",
                review_required=True,
            ),
            AnalystDisposition(
                control_id="IAM-01",
                disposition=(
                    DISPOSITION_COMPENSATING_CONTROL
                ),
                rationale=(
                    "Alternative control accepted."
                ),
                decided_by="analyst@example.com",
            ),
        )

    except ValueError as exc:
        assert (
            "compensating control description"
            in str(exc).lower()
        )

    else:
        raise AssertionError(
            "Expected ValueError."
        )


def test_compensating_control_can_be_recorded():
    result = evaluate_control_disposition(
        sufficiency(
            status="PARTIAL",
            review_required=True,
        ),
        AnalystDisposition(
            control_id="IAM-01",
            disposition=(
                DISPOSITION_COMPENSATING_CONTROL
            ),
            rationale=(
                "Primary mechanism is unavailable."
            ),
            decided_by="analyst@example.com",
            compensating_control=(
                "Privileged sessions require PAM approval "
                "and are continuously monitored."
            ),
        ),
    )

    assert (
        result.final_disposition
        == DISPOSITION_COMPENSATING_CONTROL
    )

    assert result.compensating_control is not None
    assert result.human_confirmed is True


def test_analyst_rationale_is_required():
    try:
        evaluate_control_disposition(
            sufficiency(
                status="REVIEW",
                review_required=True,
            ),
            AnalystDisposition(
                control_id="IAM-01",
                disposition=(
                    DISPOSITION_SATISFIED
                ),
                rationale="",
                decided_by="analyst@example.com",
            ),
        )

    except ValueError as exc:
        assert "rationale" in str(exc).lower()

    else:
        raise AssertionError(
            "Expected ValueError."
        )


def test_analyst_identity_is_required():
    try:
        evaluate_control_disposition(
            sufficiency(
                status="REVIEW",
                review_required=True,
            ),
            AnalystDisposition(
                control_id="IAM-01",
                disposition=(
                    DISPOSITION_SATISFIED
                ),
                rationale=(
                    "Evidence manually validated."
                ),
                decided_by="",
            ),
        )

    except ValueError as exc:
        assert "decided_by" in str(exc)

    else:
        raise AssertionError(
            "Expected ValueError."
        )


def test_control_id_must_match():
    try:
        evaluate_control_disposition(
            sufficiency(
                status="REVIEW",
                review_required=True,
            ),
            AnalystDisposition(
                control_id="VM-01",
                disposition=(
                    DISPOSITION_SATISFIED
                ),
                rationale=(
                    "Validated by analyst."
                ),
                decided_by="analyst@example.com",
            ),
        )

    except ValueError as exc:
        assert "control_id" in str(exc)

    else:
        raise AssertionError(
            "Expected ValueError."
        )


def test_policy_version_is_exposed():
    result = evaluate_control_disposition(
        sufficiency(
            status="SUPPORTED",
        )
    )

    assert (
        result.policy_version
        == CONTROL_DISPOSITION_POLICY_VERSION
    )

    assert result.policy_version == "CD-1.0"