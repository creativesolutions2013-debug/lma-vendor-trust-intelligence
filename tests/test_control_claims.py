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


def test_valid_candidate_generates_control_claim():
    result = generate_control_claim(
        100,
        ControlClaimCandidate(
            control_id="IAM-01",
            statement=(
                "Logical access is approved and "
                "periodically reviewed."
            ),
            source_reference="SOC2 p.42 CC6.1",
            confidence=0.94,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is not None
    assert result.claim.control_id == "IAM-01"
    assert result.claim.evidence_id == 100

    assert (
        result.provenance.generation_status
        == "ACCEPTED"
    )

    assert result.provenance.review_required is False


def test_control_id_is_normalized():
    result = generate_control_claim(
        101,
        ControlClaimCandidate(
            control_id=" iam-01 ",
            statement="Access control tested.",
            source_reference="SOC2 p.12",
            confidence=0.90,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is not None
    assert result.claim.control_id == "IAM-01"


def test_unknown_control_is_rejected():
    result = generate_control_claim(
        102,
        ControlClaimCandidate(
            control_id="UNKNOWN-99",
            statement="Unknown mapping.",
            source_reference="SOC2 p.10",
            confidence=0.99,
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
        ControlClaimCandidate(
            control_id="",
            statement="No control identifier.",
            source_reference="SOC2 p.15",
            confidence=0.90,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is None
    assert result.provenance.generation_status == "REJECTED"


def test_missing_source_reference_requires_review():
    result = generate_control_claim(
        104,
        ControlClaimCandidate(
            control_id="IAM-01",
            statement="Access control appears present.",
            source_reference="",
            confidence=0.95,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is not None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )

    assert result.provenance.review_required is True

    assert (
        result.claim.extraction_confidence
        == 0.0
    )


def test_low_confidence_requires_review():
    result = generate_control_claim(
        105,
        ControlClaimCandidate(
            control_id="IAM-01",
            statement="Possible IAM evidence.",
            source_reference="SOC2 p.18",
            confidence=0.40,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is not None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )

    assert result.provenance.review_required is True

    assert (
        result.claim.extraction_confidence
        == 0.40
    )


def test_scope_mismatch_requires_review():
    result = generate_control_claim(
        106,
        ControlClaimCandidate(
            control_id="IAM-01",
            statement="IAM control tested.",
            source_reference="SOC2 p.22",
            scope_matches=False,
            confidence=0.95,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is not None

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )

    assert result.claim.scope_matches is False


def test_untested_control_requires_review():
    result = generate_control_claim(
        107,
        ControlClaimCandidate(
            control_id="IAM-01",
            statement=(
                "Control described but operating "
                "effectiveness was not tested."
            ),
            source_reference="SOC2 p.31",
            tested=False,
            confidence=0.91,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert (
        result.provenance.generation_status
        == "REVIEW"
    )

    assert result.claim is not None
    assert result.claim.tested is False


def test_exception_is_preserved_in_generated_claim():
    result = generate_control_claim(
        108,
        ControlClaimCandidate(
            control_id="IAM-01",
            statement=(
                "Access review control had one exception."
            ),
            source_reference="SOC2 p.55 CC6.1",
            exception_present=True,
            confidence=0.97,
        ),
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.claim is not None
    assert result.claim.exception_present is True


def test_batch_generation_exposes_provenance_counts():
    result = generate_control_claims(
        200,
        [
            ControlClaimCandidate(
                control_id="IAM-01",
                statement="IAM control tested.",
                source_reference="SOC2 p.10",
                confidence=0.95,
            ),
            ControlClaimCandidate(
                control_id="VM-01",
                statement="Possible VM mapping.",
                source_reference="SOC2 p.20",
                confidence=0.40,
            ),
            ControlClaimCandidate(
                control_id="INVALID-01",
                statement="Unsupported control.",
                source_reference="SOC2 p.30",
                confidence=0.99,
            ),
        ],
        allowed_control_ids=ALLOWED_CONTROLS,
    )

    assert result.accepted == 1
    assert result.review_required == 1
    assert result.rejected == 1

    assert len(result.generated_claims) == 2
    assert len(result.provenance) == 3

    assert (
        result.policy_version
        == CONTROL_CLAIM_POLICY_VERSION
    )

    assert result.policy_version == "CG-1.0"