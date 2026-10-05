from src.control_claims import (
    CONTROL_CLAIM_POLICY_VERSION,
    ControlClaimCandidate,
    generate_control_claim,
    generate_control_claims,
)


ALLOWED_CONTROLS = (
    "GOV-01",
    "IAM-01",
    "PAM-01",
    "ENC-01",
    "VM-01",
)


def valid_candidate(
    *,
    control_id="IAM-01",
    confidence=0.94,
    **overrides,
):
    values = {
        "control_id": control_id,
        "statement": (
            "Logical access is approved and "
            "periodically reviewed."
        ),
        "source_reference": (
            "SOC2 p.42 CC6.1"
        ),
        "covered": True,
        "tested": True,
        "scope_matches": True,
        "service_matches": True,
        "exception_present": False,
        "confidence": confidence,
    }

    values.update(
        overrides
    )

    return ControlClaimCandidate(
        **values
    )


def test_valid_candidate_generates_control_claim():
    result = generate_control_claim(
        100,
        valid_candidate(),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is not None
    assert result.claim.control_id == "IAM-01"
    assert result.claim.evidence_id == 100

    assert (
        result.provenance.generation_status
        == "ACCEPTED"
    )

    assert (
        result.provenance.review_required
        is False
    )


def test_control_id_is_normalized():
    result = generate_control_claim(
        101,
        valid_candidate(
            control_id=" iam-01 "
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is not None
    assert result.claim.control_id == "IAM-01"


def test_unknown_control_is_rejected():
    result = generate_control_claim(
        102,
        valid_candidate(
            control_id="UNKNOWN-99"
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REJECTED"
    )


def test_missing_control_is_rejected():
    result = generate_control_claim(
        103,
        valid_candidate(
            control_id=""
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REJECTED"
    )


def test_candidate_defaults_are_conservative():
    candidate = ControlClaimCandidate(
        control_id="IAM-01",
        statement="Possible IAM control.",
        source_reference="SOC2 p.10",
    )

    assert candidate.covered is None
    assert candidate.tested is None
    assert candidate.scope_matches is None
    assert candidate.service_matches is None
    assert candidate.exception_present is None
    assert candidate.confidence == 0.0


def test_unknown_assurance_facts_require_review():
    result = generate_control_claim(
        104,
        ControlClaimCandidate(
            control_id="IAM-01",
            statement=(
                "Possible IAM evidence."
            ),
            source_reference=(
                "SOC2 p.18"
            ),
            confidence=0.95,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )

    assert (
        result.provenance.review_required
        is True
    )


def test_missing_statement_requires_review():
    result = generate_control_claim(
        105,
        valid_candidate(
            statement=""
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )


def test_missing_source_reference_requires_review():
    result = generate_control_claim(
        106,
        valid_candidate(
            source_reference=""
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )

    assert (
        result.provenance.review_required
        is True
    )


def test_low_confidence_machine_candidate_requires_review():
    result = generate_control_claim(
        107,
        valid_candidate(
            confidence=0.40
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )

    assert (
        result.provenance.confidence
        == 0.40
    )


def test_scope_mismatch_machine_candidate_requires_review():
    result = generate_control_claim(
        108,
        valid_candidate(
            scope_matches=False
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )


def test_untested_machine_candidate_requires_review():
    result = generate_control_claim(
        109,
        valid_candidate(
            tested=False
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )


def test_exception_machine_candidate_requires_review():
    result = generate_control_claim(
        110,
        valid_candidate(
            exception_present=True
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )


def test_human_confirmation_can_promote_explicit_review_candidate():
    result = generate_control_claim(
        111,
        valid_candidate(
            exception_present=True
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
        human_confirmed=True,
        confirmed_by="Security Analyst",
    )

    assert result.claim is not None

    assert (
        result.claim.exception_present
        is True
    )

    assert (
        result.provenance.generation_status
        == "ACCEPTED"
    )

    assert (
        result.provenance.human_confirmed
        is True
    )

    assert (
        result.provenance.confirmed_by
        == "Security Analyst"
    )

    # The underlying exception still requires
    # downstream consideration by CS-1.0.
    assert (
        result.provenance.review_required
        is True
    )


def test_human_confirmation_does_not_invent_unknown_facts():
    result = generate_control_claim(
        112,
        ControlClaimCandidate(
            control_id="IAM-01",
            statement=(
                "Possible IAM control."
            ),
            source_reference=(
                "SOC2 p.22"
            ),
            confidence=0.95,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
        human_confirmed=True,
        confirmed_by="Security Analyst",
    )

    assert result.claim is None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )


def test_batch_generation_returns_only_accepted_claims():
    result = generate_control_claims(
        200,
        [
            valid_candidate(
                control_id="IAM-01",
            ),
            valid_candidate(
                control_id="VM-01",
                confidence=0.40,
            ),
            valid_candidate(
                control_id="INVALID-01",
            ),
        ],
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.accepted == 1
    assert result.review_required == 1
    assert result.rejected == 1

    # Only the accepted machine claim may enter
    # downstream control-sufficiency evaluation.
    assert len(
        result.generated_claims
    ) == 1

    assert len(
        result.provenance
    ) == 3

    assert (
        result.generated_claims[0]
        .control_id
        == "IAM-01"
    )


def test_policy_version_is_cg_1_1():
    result = generate_control_claims(
        300,
        [
            valid_candidate(),
        ],
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert (
        CONTROL_CLAIM_POLICY_VERSION
        == "CG-1.1"
    )

    assert (
        result.policy_version
        == "CG-1.1"
    )

    assert all(
        item.policy_version
        == "CG-1.1"
        for item in result.provenance
    )