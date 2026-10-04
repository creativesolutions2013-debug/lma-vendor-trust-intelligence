from dataclasses import dataclass
from typing import Iterable, Tuple

from src.control_sufficiency import EvidenceControlClaim


CONTROL_CLAIM_POLICY_VERSION = "CG-1.0"


@dataclass(frozen=True)
class ControlClaimCandidate:
    """
    Candidate control mapping produced from evidence analysis.

    A candidate is not yet an assurance conclusion.
    It must pass provenance and confidence checks before
    becoming a usable EvidenceControlClaim.
    """

    control_id: str
    statement: str
    source_reference: str

    covered: bool = True
    tested: bool = True

    scope_matches: bool = True
    service_matches: bool = True

    exception_present: bool = False

    confidence: float = 1.0


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
    return max(
        0.0,
        min(
            1.0,
            float(confidence),
        ),
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

    # -------------------------------------------------
    # Hard validation:
    # Unknown controls cannot silently enter the engine.
    # -------------------------------------------------

    if not control_id:
        provenance = ControlClaimProvenance(
            evidence_id=evidence_id,
            control_id="",
            statement=statement,
            source_reference=source_reference,
            confidence=confidence,
            generation_status="REJECTED",
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
            generation_status="REJECTED",
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

    # -------------------------------------------------
    # Provenance guardrail:
    # A claim without a source reference must never be
    # treated as automatically trustworthy.
    # -------------------------------------------------

    if not source_reference:
        claim = EvidenceControlClaim(
            evidence_id=evidence_id,
            control_id=control_id,
            covered=candidate.covered,
            tested=candidate.tested,
            scope_matches=candidate.scope_matches,
            service_matches=candidate.service_matches,
            exception_present=candidate.exception_present,
            extraction_confidence=0.0,
            rationale=statement,
        )

        provenance = ControlClaimProvenance(
            evidence_id=evidence_id,
            control_id=control_id,
            statement=statement,
            source_reference="",
            confidence=0.0,
            generation_status="REVIEW",
            review_required=True,
            reason=(
                "A potential control mapping was identified, "
                "but no evidence source reference was provided. "
                "Analyst validation is required."
            ),
            human_confirmed=human_confirmed,
            confirmed_by=confirmed_by,
        )

        return GeneratedControlClaim(
            claim=claim,
            provenance=provenance,
        )

    # -------------------------------------------------
    # Low-confidence mappings remain usable as potential
    # claims but must route through analyst review.
    # CS-1.0 will independently enforce its confidence
    # threshold as well.
    # -------------------------------------------------

    if confidence < minimum_confidence:
        claim = EvidenceControlClaim(
            evidence_id=evidence_id,
            control_id=control_id,
            covered=candidate.covered,
            tested=candidate.tested,
            scope_matches=candidate.scope_matches,
            service_matches=candidate.service_matches,
            exception_present=candidate.exception_present,
            extraction_confidence=confidence,
            rationale=statement,
        )

        provenance = ControlClaimProvenance(
            evidence_id=evidence_id,
            control_id=control_id,
            statement=statement,
            source_reference=source_reference,
            confidence=confidence,
            generation_status="REVIEW",
            review_required=True,
            reason=(
                "Control mapping has source provenance but "
                "its confidence is below the automatic-use "
                "threshold."
            ),
            human_confirmed=human_confirmed,
            confirmed_by=confirmed_by,
        )

        return GeneratedControlClaim(
            claim=claim,
            provenance=provenance,
        )

    # -------------------------------------------------
    # Human confirmation may allow a low-ambiguity
    # generated mapping to carry explicit review history,
    # but it does not change the underlying facts.
    # -------------------------------------------------

    review_required = (
        not candidate.scope_matches
        or not candidate.service_matches
        or not candidate.tested
    )

    if review_required:
        status = "REVIEW"

        reason = (
            "Control mapping has valid provenance, but "
            "scope, service alignment, or testing status "
            "requires analyst validation."
        )
    else:
        status = "ACCEPTED"

        reason = (
            "Control mapping has an approved control ID, "
            "source provenance, and sufficient mapping "
            "confidence."
        )

    claim = EvidenceControlClaim(
        evidence_id=evidence_id,
        control_id=control_id,
        covered=candidate.covered,
        tested=candidate.tested,
        scope_matches=candidate.scope_matches,
        service_matches=candidate.service_matches,
        exception_present=candidate.exception_present,
        extraction_confidence=confidence,
        rationale=statement,
    )

    provenance = ControlClaimProvenance(
        evidence_id=evidence_id,
        control_id=control_id,
        statement=statement,
        source_reference=source_reference,
        confidence=confidence,
        generation_status=status,
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
        if result.claim is not None
    )

    provenance = tuple(
        result.provenance
        for result in results
    )

    accepted = sum(
        1
        for item in provenance
        if item.generation_status
        == "ACCEPTED"
    )

    review_required = sum(
        1
        for item in provenance
        if item.generation_status
        == "REVIEW"
    )

    rejected = sum(
        1
        for item in provenance
        if item.generation_status
        == "REJECTED"
    )

    return ControlClaimGenerationResult(
        evidence_id=evidence_id,
        generated_claims=claims,
        provenance=provenance,
        accepted=accepted,
        review_required=review_required,
        rejected=rejected,
    )