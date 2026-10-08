from dataclasses import dataclass

from src.control_claims import (
    ControlClaimCandidate,
    GeneratedControlClaim,
    generate_control_claim,
)


CONTROL_CLAIM_REVIEW_POLICY_VERSION = "CCR-1.0"


@dataclass(frozen=True)
class AnalystClaimConfirmation:
    """
    Analyst-confirmed assurance facts for one evidence-to-control
    candidate.

    Every required assurance fact must be explicitly supplied.
    None means the analyst has not established that fact yet.
    """

    covered: bool | None
    tested: bool | None
    scope_matches: bool | None
    service_matches: bool | None
    exception_present: bool | None

    confirmed_by: str
    analyst_rationale: str


@dataclass(frozen=True)
class ControlClaimReviewResult:
    evidence_id: int
    control_id: str

    result: GeneratedControlClaim

    analyst_rationale: str
    confirmed_by: str

    complete_confirmation: bool

    policy_version: str = (
        CONTROL_CLAIM_REVIEW_POLICY_VERSION
    )


def _normalize_text(
    value: str | None,
) -> str:
    return (
        value
        or ""
    ).strip()


def _confirmation_is_complete(
    confirmation: AnalystClaimConfirmation,
) -> bool:
    return all(
        value is not None
        for value in (
            confirmation.covered,
            confirmation.tested,
            confirmation.scope_matches,
            confirmation.service_matches,
            confirmation.exception_present,
        )
    )


def review_control_claim_candidate(
    evidence_id: int,
    candidate: ControlClaimCandidate,
    confirmation: AnalystClaimConfirmation,
    *,
    allowed_control_ids,
    minimum_confidence: float = 0.65,
) -> ControlClaimReviewResult:
    """
    Apply explicit analyst-confirmed assurance facts to one
    evidence-to-control candidate.

    The review process does not infer or default unknown facts.

    A candidate can become an authoritative EvidenceControlClaim
    only when:
    - all required assurance facts are explicitly confirmed,
    - reviewer identity is supplied,
    - rationale is supplied,
    - the underlying control-claim governance rules accept it.
    """

    confirmed_by = _normalize_text(
        confirmation.confirmed_by
    )

    rationale = _normalize_text(
        confirmation.analyst_rationale
    )

    if not confirmed_by:
        raise ValueError(
            "Analyst confirmation requires confirmed_by."
        )

    if not rationale:
        raise ValueError(
            "Analyst confirmation requires a rationale."
        )

    complete = (
        _confirmation_is_complete(
            confirmation
        )
    )

    # -------------------------------------------------
    # Preserve unknown facts when review is incomplete.
    # -------------------------------------------------

    reviewed_candidate = (
        ControlClaimCandidate(
            control_id=(
                candidate.control_id
            ),
            statement=(
                candidate.statement
            ),
            source_reference=(
                candidate.source_reference
            ),
            covered=(
                confirmation.covered
            ),
            tested=(
                confirmation.tested
            ),
            scope_matches=(
                confirmation.scope_matches
            ),
            service_matches=(
                confirmation.service_matches
            ),
            exception_present=(
                confirmation.exception_present
            ),
            confidence=(
                candidate.confidence
            ),
        )
    )

    result = generate_control_claim(
        evidence_id,
        reviewed_candidate,
        allowed_control_ids=(
            allowed_control_ids
        ),
        minimum_confidence=(
            minimum_confidence
        ),
        human_confirmed=complete,
        confirmed_by=(
            confirmed_by
            if complete
            else None
        ),
    )

    return ControlClaimReviewResult(
        evidence_id=evidence_id,
        control_id=(
            candidate.control_id
        ),
        result=result,
        analyst_rationale=rationale,
        confirmed_by=confirmed_by,
        complete_confirmation=complete,
    )