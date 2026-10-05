from dataclasses import dataclass
from typing import Iterable, Tuple

from src.control_sufficiency import EvidenceControlClaim


CONTROL_CLAIM_POLICY_VERSION = "CG-1.1"

STATUS_ACCEPTED = "ACCEPTED"
STATUS_REVIEW = "REVIEW"
STATUS_REJECTED = "REJECTED"


@dataclass(frozen=True)
class ControlClaimCandidate:
    """
    Machine- or analyst-generated candidate mapping between
    evidence and a security control.

    Important:
    Unknown assurance facts remain None.

    The generator must not assume that evidence:
    - covers the control
    - was tested
    - matches scope
    - matches the assessed service
    - has no exception

    Those facts must be explicitly established before a
    machine-generated candidate can become an authoritative
    EvidenceControlClaim.
    """

    control_id: str
    statement: str
    source_reference: str

    covered: bool | None = None
    tested: bool | None = None

    scope_matches: bool | None = None
    service_matches: bool | None = None

    exception_present: bool | None = None

    confidence: float = 0.0


@dataclass(frozen=True)
class ControlClaimProvenance:
    evidence_id: int
    control_id: str

    statement: str
    source_reference: str

    confidence: float

    generation_status: str
    review_required: bool

    reason: str

    human_confirmed: bool = False
    confirmed_by: str | None = None

    policy_version: str = CONTROL_CLAIM_POLICY_VERSION


@dataclass(frozen=True)
class GeneratedControlClaim:
    claim: EvidenceControlClaim | None
    provenance: ControlClaimProvenance


@dataclass(frozen=True)
class ControlClaimGenerationResult:
    evidence_id: int

    generated_claims: Tuple[EvidenceControlClaim, ...]
    provenance: Tuple[ControlClaimProvenance, ...]

    accepted: int
    review_required: int
    rejected: int

    policy_version: str = CONTROL_CLAIM_POLICY_VERSION


def _normalize_control_id(
    control_id: str,
) -> str:
    return (
        control_id
        or ""
    ).strip().upper()


def _normalize_text(
    value: str,
) -> str:
    return (
        value
        or ""
    ).strip()


def _clamp_confidence(
    confidence: float,
) -> float:
    try:
        normalized = float(
            confidence
        )
    except (TypeError, ValueError):
        normalized = 0.0

    return max(
        0.0,
        min(
            1.0,
            normalized,
        ),
    )


def _required_facts_known(
    candidate: ControlClaimCandidate,
) -> bool:
    """
    Return True only when every assurance fact required by
    CS-1.0 has been explicitly established.
    """

    return all(
        value is not None
        for value in (
            candidate.covered,
            candidate.tested,
            candidate.scope_matches,
            candidate.service_matches,
            candidate.exception_present,
        )
    )


def _build_claim(
    evidence_id: int,
    control_id: str,
    candidate: ControlClaimCandidate,
    confidence: float,
    statement: str,
) -> EvidenceControlClaim:
    """
    Build a CS-1.0 claim only after the caller has established
    that all required candidate facts are explicit.
    """

    return EvidenceControlClaim(
        evidence_id=evidence_id,
        control_id=control_id,
        covered=bool(
            candidate.covered
        ),
        tested=bool(
            candidate.tested
        ),
        scope_matches=bool(
            candidate.scope_matches
        ),
        service_matches=bool(
            candidate.service_matches
        ),
        exception_present=bool(
            candidate.exception_present
        ),
        extraction_confidence=confidence,
        rationale=statement,
    )


def _review_result(
    *,
    evidence_id: int,
    control_id: str,
    statement: str,
    source_reference: str,
    confidence: float,
    reason: str,
    human_confirmed: bool,
    confirmed_by: str | None,
) -> GeneratedControlClaim:
    """
    Preserve a candidate and its provenance without allowing it
    to enter the control-sufficiency engine as an authoritative
    claim.
    """

    provenance = ControlClaimProvenance(
        evidence_id=evidence_id,
        control_id=control_id,
        statement=statement,
        source_reference=source_reference,
        confidence=confidence,
        generation_status=STATUS_REVIEW,
        review_required=True,
        reason=reason,
        human_confirmed=human_confirmed,
        confirmed_by=confirmed_by,
    )

    return GeneratedControlClaim(
        claim=None,
        provenance=provenance,
    )


def generate_control_claim(
    evidence_id: int,
    candidate: ControlClaimCandidate,
    *,
    allowed_control_ids: Iterable[str],
    minimum_confidence: float = 0.65,
    human_confirmed: bool = False,
    confirmed_by: str | None = None,
) -> GeneratedControlClaim:
    """
    Govern creation of a control-level evidence claim.

    Machine-generated candidates are automatically usable only
    when:

    - the control is approved for the assessment scope
    - a statement exists
    - source provenance exists
    - all assurance facts are explicitly known
    - confidence meets the automatic-use threshold
    - no fact requires analyst interpretation

    Candidates that do not meet those conditions remain
    provenance records requiring analyst review.

    Human confirmation does not invent missing facts.
    """

    control_id = _normalize_control_id(
        candidate.control_id
    )

    allowed = {
        _normalize_control_id(
            item
        )
        for item in allowed_control_ids
    }

    statement = _normalize_text(
        candidate.statement
    )

    source_reference = _normalize_text(
        candidate.source_reference
    )

    confidence = _clamp_confidence(
        candidate.confidence
    )

    confirmed_by = (
        _normalize_text(
            confirmed_by
        )
        or None
    )

    # =====================================================
    # Hard validation
    # =====================================================

    if not control_id:
        provenance = ControlClaimProvenance(
            evidence_id=evidence_id,
            control_id="",
            statement=statement,
            source_reference=source_reference,
            confidence=confidence,
            generation_status=STATUS_REJECTED,
            review_required=False,
            reason=(
                "Candidate does not identify a control."
            ),
            human_confirmed=human_confirmed,
            confirmed_by=confirmed_by,
        )

        return GeneratedControlClaim(
            claim=None,
            provenance=provenance,
        )

    if control_id not in allowed:
        provenance = ControlClaimProvenance(
            evidence_id=evidence_id,
            control_id=control_id,
            statement=statement,
            source_reference=source_reference,
            confidence=confidence,
            generation_status=STATUS_REJECTED,
            review_required=False,
            reason=(
                "Candidate references a control that is not "
                "part of the approved control scope."
            ),
            human_confirmed=human_confirmed,
            confirmed_by=confirmed_by,
        )

        return GeneratedControlClaim(
            claim=None,
            provenance=provenance,
        )

    # =====================================================
    # Provenance requirements
    # =====================================================

    if not statement:
        return _review_result(
            evidence_id=evidence_id,
            control_id=control_id,
            statement="",
            source_reference=source_reference,
            confidence=confidence,
            reason=(
                "A control mapping was identified, but no "
                "supporting claim statement was provided. "
                "Analyst validation is required."
            ),
            human_confirmed=human_confirmed,
            confirmed_by=confirmed_by,
        )

    if not source_reference:
        return _review_result(
            evidence_id=evidence_id,
            control_id=control_id,
            statement=statement,
            source_reference="",
            confidence=confidence,
            reason=(
                "A potential control mapping was identified, "
                "but no source reference was provided. "
                "Analyst validation is required."
            ),
            human_confirmed=human_confirmed,
            confirmed_by=confirmed_by,
        )

    # =====================================================
    # Unknown facts must never become True by default
    # =====================================================

    if not _required_facts_known(
        candidate
    ):
        return _review_result(
            evidence_id=evidence_id,
            control_id=control_id,
            statement=statement,
            source_reference=source_reference,
            confidence=confidence,
            reason=(
                "The control mapping does not explicitly establish "
                "coverage, testing, scope alignment, service "
                "alignment, and exception status. Analyst "
                "validation is required."
            ),
            human_confirmed=human_confirmed,
            confirmed_by=confirmed_by,
        )

    # =====================================================
    # Low-confidence machine mappings require review.
    #
    # Human confirmation may promote the mapping into an
    # authoritative claim, but the original confidence is
    # preserved. CS-1.0 can still require review based on it.
    # =====================================================

    if (
        confidence < minimum_confidence
        and not human_confirmed
    ):
        return _review_result(
            evidence_id=evidence_id,
            control_id=control_id,
            statement=statement,
            source_reference=source_reference,
            confidence=confidence,
            reason=(
                "Control mapping has source provenance but its "
                "confidence is below the automatic-use threshold."
            ),
            human_confirmed=False,
            confirmed_by=None,
        )

    # =====================================================
    # Facts requiring interpretation remain review-only
    # unless a human explicitly confirms the mapping.
    # =====================================================

    material_review_condition = (
        candidate.covered is False
        or candidate.tested is False
        or candidate.scope_matches is False
        or candidate.service_matches is False
        or candidate.exception_present is True
    )

    if (
        material_review_condition
        and not human_confirmed
    ):
        return _review_result(
            evidence_id=evidence_id,
            control_id=control_id,
            statement=statement,
            source_reference=source_reference,
            confidence=confidence,
            reason=(
                "The evidence mapping contains a coverage, "
                "testing, scope, service-alignment, or exception "
                "condition that requires analyst confirmation."
            ),
            human_confirmed=False,
            confirmed_by=None,
        )

    # =====================================================
    # Accepted authoritative claim
    # =====================================================

    claim = _build_claim(
        evidence_id,
        control_id,
        candidate,
        confidence,
        statement,
    )

    review_required = (
        confidence < minimum_confidence
        or material_review_condition
    )

    if human_confirmed:
        reason = (
            "An analyst confirmed this evidence-to-control "
            "mapping with explicit assurance facts. Underlying "
            "limitations are preserved for CS-1.0 evaluation."
        )

    else:
        reason = (
            "Control mapping has an approved control ID, "
            "source provenance, explicit assurance facts, and "
            "sufficient confidence for automatic use."
        )

    provenance = ControlClaimProvenance(
        evidence_id=evidence_id,
        control_id=control_id,
        statement=statement,
        source_reference=source_reference,
        confidence=confidence,
        generation_status=STATUS_ACCEPTED,
        review_required=review_required,
        reason=reason,
        human_confirmed=human_confirmed,
        confirmed_by=confirmed_by,
    )

    return GeneratedControlClaim(
        claim=claim,
        provenance=provenance,
    )


def generate_control_claims(
    evidence_id: int,
    candidates: Iterable[ControlClaimCandidate],
    *,
    allowed_control_ids: Iterable[str],
    minimum_confidence: float = 0.65,
) -> ControlClaimGenerationResult:
    """
    Batch machine-generated candidates.

    Only ACCEPTED claims are returned in generated_claims.
    REVIEW and REJECTED candidates remain visible through
    provenance so they can be routed to human review without
    silently affecting control-sufficiency conclusions.
    """

    allowed_control_ids = tuple(
        allowed_control_ids
    )

    results = [
        generate_control_claim(
            evidence_id,
            candidate,
            allowed_control_ids=allowed_control_ids,
            minimum_confidence=minimum_confidence,
        )
        for candidate in candidates
    ]

    claims = tuple(
        result.claim
        for result in results
        if (
            result.claim is not None
            and result.provenance.generation_status
            == STATUS_ACCEPTED
        )
    )

    provenance = tuple(
        result.provenance
        for result in results
    )

    accepted = sum(
        1
        for item in provenance
        if item.generation_status
        == STATUS_ACCEPTED
    )

    review_required = sum(
        1
        for item in provenance
        if item.generation_status
        == STATUS_REVIEW
    )

    rejected = sum(
        1
        for item in provenance
        if item.generation_status
        == STATUS_REJECTED
    )

    return ControlClaimGenerationResult(
        evidence_id=evidence_id,
        generated_claims=claims,
        provenance=provenance,
        accepted=accepted,
        review_required=review_required,
        rejected=rejected,
    )