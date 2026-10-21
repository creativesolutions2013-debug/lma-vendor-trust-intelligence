"""M3B: read-only source bindings and an explicit analyst semantic-review gate.

There is deliberately no automatic entailment engine. A matching quotation is
only citation integrity. Authorized callers supply analyst dispositions before
facts reach M3A; this module does not authenticate those callers. Hashes bind the
supplied bytes/metadata, not the authenticity or truth of a vendor document.
"""
from dataclasses import asdict, dataclass, field, replace
from datetime import date
import re
from typing import Iterable

from src.evidence_intelligence_m3 import (
    MfaEvaluation, MfaFact, MfaRequirement, SourceSegment, evaluate_privileged_mfa,
)
from src.evidence_source_validation import (
    BoundEvidence, BundleReview, CLASSIFICATIONS, EvidenceInput, ExceptionSignal,
    FactReview, SignalDisposition, _digest, _review_valid, bind_evidence, segment_id,
    source_issues,
)

VALIDATOR_VERSION = "M3B-1.0"
# Triage only: these expressions never establish a fact or a failed control.
# Negations also match and require an explicit, bundle-bound analyst disposition.
EXCEPTION_MARKERS = re.compile(
    r"\b(?:bypass\w*|exempt\w*|exceptions?|SMS|TOTP)\b|password[- ]only|"
    r"without\s+(?:MFA|multi.factor)|not\s+(?:enforced|required)|"
    r"(?:disable\w*|skip\w*)\s+(?:MFA|multi.factor)", re.I,
)


@dataclass(frozen=True)
class ProposedFact:
    fact_id: str
    fact: MfaFact
    source_fingerprint: str
    location: str


def fact_fingerprint(proposal: ProposedFact) -> str:
    """Bind every interpretation property, citation, location and source metadata."""
    return _digest(asdict(proposal))


@dataclass(frozen=True)
class FactValidation:
    proposal: ProposedFact
    citation_verified: bool
    status: str  # validated, needs_review, unsupported
    classification: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ValidationResult:
    evaluation: MfaEvaluation
    facts: tuple[FactValidation, ...]
    evidence: tuple[BoundEvidence, ...]
    signals: tuple[ExceptionSignal, ...]
    bundle_fingerprint: str
    bundle_review_valid: bool
    follow_up: tuple[str, ...]
    validator_version: str = field(default=VALIDATOR_VERSION, init=False)
    provisional: bool = field(default=True, init=False)
    review_required: bool = field(default=True, init=False)


def bundle_fingerprint(requirement, evidence, proposals, *, as_of):
    return _digest({
        "validator": VALIDATOR_VERSION, "requirement": asdict(requirement), "as_of": as_of,
        "documents": sorted(item.fingerprint for item in evidence),
        "proposals": sorted(fact_fingerprint(item) for item in proposals),
    })


def _source_issues(source, requirement, as_of):
    return source_issues(
        source, service=requirement.service, environment=requirement.environment,
        scope=requirement.account_scope, max_age_days=requirement.max_age_days,
        as_of=as_of,
    )


def validate_and_evaluate_mfa(
    requirement: MfaRequirement,
    documents: Iterable[EvidenceInput],
    proposals: Iterable[ProposedFact],
    *,
    as_of: date,
    fact_reviews: Iterable[FactReview] = (),
    bundle_review: BundleReview | None = None,
) -> ValidationResult:
    """Validate a supplied bundle and call unchanged M3A with reviewed facts only.

    Semantic support is an explicit analyst input, never inferred from lexical
    overlap. Review does not upgrade policy intent, broaden scope, refresh stale
    evidence, or manufacture authentication properties. All inputs and signals
    remain visible. Invalid/ambiguous proposals cannot create positive assurance.
    """
    if type(as_of) is not date:
        raise ValueError("An explicit evaluation date is required.")
    evidence = tuple(bind_evidence(item) for item in documents)
    proposals = tuple(proposals)
    if len({item.source.document_id for item in evidence}) != len(evidence):
        raise ValueError("Duplicate document IDs are not allowed.")
    if (any(not isinstance(item.fact_id, str) or not item.fact_id.strip() for item in proposals)
            or len({item.fact_id for item in proposals}) != len(proposals)):
        raise ValueError("Unique nonempty proposed fact IDs are required.")
    sources, owners, signals = {}, {}, []
    for item in evidence:
        for ordinal, part in enumerate(item.document.segments, 1):
            sid = segment_id(item.source.document_id, ordinal)
            sources[sid] = SourceSegment(item.document.filename, part.location, part.text)
            owners[sid] = item
            if EXCEPTION_MARKERS.search(part.text):
                signals.append(ExceptionSignal(
                    _digest({"source": item.fingerprint, "segment": sid, "quote": part.text}),
                    sid, item.document.filename, part.location, part.text,
                ))
    bundle_hash = bundle_fingerprint(requirement, evidence, proposals, as_of=as_of)
    capture_dates = [item.source.captured_on for item in evidence if item.source.captured_on]
    bundle_valid = (bundle_review is not None
                    and bundle_review.bundle_fingerprint == bundle_hash
                    and _review_valid(bundle_review, as_of, max(capture_dates, default=None)))
    reviews = {}
    for review in fact_reviews:
        reviews.setdefault(review.fact_fingerprint, []).append(review)
    validations, accepted = [], []
    for proposal in proposals:
        fact = proposal.fact
        source = sources.get(fact.citation.source_id)
        owner = owners.get(fact.citation.source_id)
        citation_ok = bool(source and owner.fingerprint == proposal.source_fingerprint
                           and proposal.location == source.location
                           and isinstance(fact.citation.quote, str) and fact.citation.quote.strip()
                           and fact.citation.quote in source.text)
        reasons = [] if citation_ok else ["Source identity, version, location or exact quotation did not match."]
        if owner:
            reasons.extend(_source_issues(owner.source, requirement, as_of))
            if (fact.service, fact.environment, fact.account_scope, fact.observed_on, fact.evidence_kind) != (
                    owner.source.service, owner.source.environment, owner.source.account_scope,
                    owner.source.observed_on, owner.source.evidence_kind):
                reasons.append("Proposed scope, observation date or evidence kind differs from source inventory.")
        if citation_ok:
            try:
                evaluate_privileged_mfa(requirement, (fact,), sources, as_of=as_of)
            except ValueError:
                reasons.append("Proposed fact has invalid MFA fields.")
        candidates = reviews.get(fact_fingerprint(proposal), [])
        review = candidates[0] if len(candidates) == 1 else None
        classification = "unsupported_interpretation"
        status = "needs_review"
        if review is None or not _review_valid(review, as_of, owner.source.captured_on if owner else None):
            reasons.append("A unique, current analyst semantic disposition is required; quotation matching is insufficient.")
        elif review.classification not in CLASSIFICATIONS or review.decision not in {"supported", "unsupported", "ambiguous"}:
            reasons.append("Unknown analyst disposition or evidence classification.")
        else:
            classification = review.classification
            if review.decision != "supported" or classification == "unsupported_interpretation":
                status = "unsupported" if review.decision == "unsupported" else "needs_review"
                reasons.append("Analyst marked the interpretation unsupported or ambiguous: " + review.rationale)
            else:
                expected_kind = {"policy_assertion": {"policy", "assertion"},
                                 "implementation_evidence": {"configuration"},
                                 "operating_test": {"test"},
                                 "explicit_exception": {"assertion", "configuration", "test"},
                                 "conflicting_statement": {"policy", "assertion", "configuration", "test"}}
                if fact.evidence_kind not in expected_kind[classification]:
                    reasons.append("Analyst classification does not match the evidence kind.")
                if not reasons:
                    status = "validated"
                    accepted.append(fact)
        validations.append(FactValidation(proposal, citation_ok, status, classification, tuple(reasons)))
    dispositions = {}
    if bundle_valid:
        for disposition in bundle_review.signal_dispositions:
            dispositions.setdefault(disposition.signal_id, []).append(disposition)
    triaged = []
    for signal in signals:
        items = dispositions.get(signal.signal_id, [])
        if (len(items) == 1 and type(items[0].material) is bool
                and isinstance(items[0].rationale, str) and items[0].rationale.strip()):
            signal = replace(signal, status="material" if items[0].material else "dismissed_by_analyst",
                             rationale=items[0].rationale)
        triaged.append(signal)
    evaluation = evaluate_privileged_mfa(requirement, accepted, sources, as_of=as_of)
    follow_up = []
    if not bundle_valid:
        follow_up.append("Analyst must review the complete supplied bundle, including uncited documents, scope and provenance.")
    if any(item.status != "validated" for item in validations):
        follow_up.append("Resolve unsupported, ambiguous or invalid fact interpretations against full source context.")
    if any(item.classification in {"explicit_exception", "conflicting_statement"}
           for item in validations):
        follow_up.append("Priority: resolve analyst-identified exceptions and conflicting statements; retain both source accounts.")
    if any(item.status != "dismissed_by_analyst" for item in triaged):
        follow_up.append("Priority: investigate retained potential/material exceptions; these are not verified control failures.")
    # Uncited stale/out-of-scope/provenance-deficient documents cannot disappear
    # behind a positive fact from another source, even after a bundle acknowledgment.
    if any(_source_issues(item.source, requirement, as_of) for item in evidence):
        follow_up.append("Resolve source provenance, freshness and scope limitations in the supplied bundle.")
    if follow_up and evaluation.outcome in {"Met", "Partially Met", "Evidence Missing"}:
        evaluation = replace(evaluation, outcome="Needs Review")
    if follow_up:
        evaluation = replace(evaluation, follow_up=tuple(follow_up) + evaluation.follow_up)
    return ValidationResult(evaluation, tuple(validations), evidence, tuple(triaged),
                            bundle_hash, bool(bundle_valid), tuple(follow_up))
