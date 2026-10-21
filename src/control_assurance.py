"""Small control-neutral, session-only evidence/review contract.

Domain rules are Python evaluators, not a policy DSL or a text-entailment engine.
Only explicit analyst dispositions can advance interpretations. Hashes bind the
entire policy/context/source bundle; they establish consistency, not authenticity
or production authorization. Nothing here persists or changes governed results.
"""
from dataclasses import asdict, dataclass, field, replace
from datetime import date
import re
from typing import Callable, Protocol

from src.evidence_source_validation import (
    BoundEvidence, BundleReview, EvidenceInput, ExceptionSignal, FactReview,
    SignalDisposition, _digest, _review_valid, bind_evidence, segment_id, source_issues,
)

CONTRACT_VERSION = "M3D-1.1"
SPECIALIST_LIMITATION = "Specialist evaluation unavailable; analyst review required."
# Triage only, not a domain rule, entailment engine or proof of failure.
GENERAL_SIGNALS = re.compile(r"\b(?:except\w*|fail\w*|excluded|overdue|untested|conflict\w*|unresolved)\b", re.I)


class ControlThreshold(Protocol):
    """A domain-owned typed record, with presentation derived from actual rules."""

    def describe(self) -> str: ...


@dataclass(frozen=True)
class CustomerThreshold:
    """Supplied acceptance criteria without executable specialist rules."""

    acceptance_criteria: str

    def __post_init__(self):
        if not isinstance(self.acceptance_criteria, str) or not self.acceptance_criteria.strip():
            raise ValueError("The customer must supply explicit acceptance criteria.")

    def describe(self):
        return self.acceptance_criteria


@dataclass(frozen=True)
class RequirementContext:
    requirement_id: str
    customer_policy_id: str
    policy_version: str
    approved_by: str
    approved_on: date
    service: str
    environment: str
    scope: str
    max_age_days: int
    standard_reference: str = ""
    business_use_case: str = ""
    required_evidence: tuple[str, ...] = ()
    assurance_type: str = ""
    standard_source: str = ""
    standard_edition: str = ""


@dataclass(frozen=True)
class Observation:
    fact_id: str
    dimension: str
    value: bool | int | str | None
    source_id: str
    source_fingerprint: str
    location: str
    quote: str
    subject: str = "complete scope"
    active: bool | None = True
    concern: str = ""  # supplied potential_exception/conflict; never inferred as failure


@dataclass(frozen=True)
class Check:
    dimension: str
    status: str  # supported, failed, reported, missing, conflict, uncertain
    rationale: str
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TechnicalResult:
    outcome: str
    checks: tuple[Check, ...]
    next_action: str


@dataclass(frozen=True)
class DomainEvaluator:
    """Small typed extension; domain logic is optional, not an applicability gate."""

    version: str
    evaluate: Callable[[ControlThreshold, tuple[tuple[Observation, EvidenceInput], ...], date], TechnicalResult]
    direction: Callable[[ControlThreshold, Observation, EvidenceInput], str]
    signal_pattern: re.Pattern[str] = GENERAL_SIGNALS


@dataclass(frozen=True)
class ControlCase:
    case_id: str
    title: str
    family: str
    requirement: RequirementContext
    threshold: ControlThreshold  # a frozen domain-specific record, never policy text
    documents: tuple[EvidenceInput, ...]
    proposals: tuple[Observation, ...]
    as_of: date
    evaluator: DomainEvaluator | None = field(default=None, repr=False)

    @property
    def threshold_summary(self):
        return self.threshold.describe() + f" Evidence no older than {self.requirement.max_age_days} days."


@dataclass(frozen=True)
class ReviewEvent:
    kind: str
    bundle_fingerprint: str
    fact_fingerprints: tuple[str, ...]
    target_ids: tuple[str, ...]
    analyst: str
    reviewed_on: date
    rationale: str


@dataclass(frozen=True)
class ControlReviewState:
    bundle_fingerprint: str = ""
    fact_reviews: tuple[FactReview, ...] = ()
    signal_dispositions: tuple[SignalDisposition, ...] = ()
    bundle_review: BundleReview | None = None
    events: tuple[ReviewEvent, ...] = ()


@dataclass(frozen=True)
class FactStatus:
    proposal: Observation
    fingerprint: str
    filename: str
    reasons: tuple[str, ...]
    confirmed: bool
    direction: str


@dataclass(frozen=True)
class ControlReview:
    requirement: RequirementContext
    threshold_summary: str
    as_of: date
    outcome: str
    checks: tuple[Check, ...]
    facts: tuple[FactStatus, ...]
    evidence: tuple[BoundEvidence, ...]
    signals: tuple[ExceptionSignal, ...]
    limitations: tuple[str, ...]
    next_action: str
    bundle_fingerprint: str
    bundle_review_valid: bool
    specialist_available: bool = True
    provisional: bool = field(default=True, init=False)
    review_required: bool = field(default=True, init=False)


def observation_fingerprint(item: Observation) -> str:
    return _digest(asdict(item))


def inspect_control(case: ControlCase, state: ControlReviewState = ControlReviewState()) -> ControlReview:
    r = case.requirement
    if (type(case.as_of) is not date or type(r.approved_on) is not date
            or r.approved_on > case.as_of or type(r.max_age_days) is not int or r.max_age_days < 1
            or any(not isinstance(x, str) or not x.strip() for x in (
                r.requirement_id, r.customer_policy_id, r.policy_version, r.approved_by,
                r.service, r.environment, r.scope))):
        raise ValueError("A versioned, customer-approved requirement, scope and assessment date are required.")
    specialist = case.evaluator
    if specialist is not None and (not isinstance(specialist, DomainEvaluator)
            or not isinstance(specialist.version, str) or not specialist.version.strip()):
        raise ValueError("A versioned typed domain evaluator is required when specialist rules are supplied.")
    evidence = tuple(bind_evidence(d) for d in case.documents)
    if len({d.source.document_id for d in evidence}) != len(evidence):
        raise ValueError("Duplicate document IDs are not allowed.")
    if (len({p.fact_id for p in case.proposals}) != len(case.proposals)
            or any(not isinstance(p.fact_id, str) or not p.fact_id.strip() for p in case.proposals)):
        raise ValueError("Unique, nonempty fact IDs are required.")
    bundle = _digest({"contract": CONTRACT_VERSION, "evaluator": specialist.version if specialist else None,
                      "family": case.family, "requirement": asdict(r),
                      "threshold": asdict(case.threshold), "as_of": case.as_of,
                      "documents": sorted(d.fingerprint for d in evidence),
                      "facts": sorted(observation_fingerprint(p) for p in case.proposals)})
    # Policy, context, document and proposal changes invalidate *all* active review.
    # Prior events remain in the caller's state for inspection; never transfer approval.
    active = state if state.bundle_fingerprint == bundle else ControlReviewState()
    segments = {segment_id(b.source.document_id, i): (b, s)
                for b in evidence for i, s in enumerate(b.document.segments, 1)}
    limitations = []
    source_limits = {}
    for b in evidence:
        issues = source_issues(b.source, service=r.service, environment=r.environment,
                               scope=r.scope, max_age_days=r.max_age_days, as_of=case.as_of)
        source_limits[b.fingerprint] = tuple(issues)
        limitations.extend(f"{b.document.filename}: {x}" for x in issues)
    facts, accepted = [], []
    for p in case.proposals:
        owner = segments.get(p.source_id)
        reasons = []
        if not (owner and owner[0].fingerprint == p.source_fingerprint
                and owner[1].location == p.location and isinstance(p.quote, str)
                and p.quote.strip() and p.quote in owner[1].text):
            reasons.append("Source identity, version, exact quotation or location does not match.")
        if owner:
            reasons.extend(source_limits[owner[0].fingerprint])
        fingerprint = observation_fingerprint(p)
        reviews = [x for x in active.fact_reviews if x.fact_fingerprint == fingerprint]
        review = reviews[0] if len(reviews) == 1 else None
        kind = owner[0].source.evidence_kind if owner else ""
        expected_class = {"policy": "policy_assertion", "assertion": "policy_assertion",
                          "configuration": "implementation_evidence", "test": "operating_test"}.get(kind)
        confirmed = bool(review and review.decision == "supported"
                         and review.classification == expected_class
                         and _review_valid(review, case.as_of, owner[0].source.captured_on if owner else None))
        if review and review.decision in {"unsupported", "ambiguous"}:
            reasons.append(f"Analyst interpretation {review.decision}: {review.rationale}")
        if specialist:
            direction = specialist.direction(case.threshold, p, owner[0].source) if owner else "unknown"
        else:
            # A supplied concern keeps adverse/conflicting interpretations visible.
            # Neutral meaning review never implies threshold support or failure.
            direction = ("adverse" if p.concern in {"potential_exception", "conflict"}
                         else "review" if p.concern == "" else "unknown")
        if direction == "unknown":
            reasons.append("Domain fields, activation or technical interpretation are uncertain.")
        if confirmed and not reasons:
            accepted.append((p, owner[0].source))
        facts.append(FactStatus(p, fingerprint, owner[0].document.filename if owner else "Unmatched source",
                                tuple(reasons), confirmed and not reasons, direction))
    signals = []
    for sid, (b, segment) in segments.items():
        if not (specialist.signal_pattern if specialist else GENERAL_SIGNALS).search(segment.text):
            continue
        signal_id = _digest({"source": b.fingerprint, "segment": sid, "quote": segment.text})
        ds = [d for d in active.signal_dispositions if d.signal_id == signal_id]
        disposition = ds[0] if len(ds) == 1 else None
        valid = bool(disposition and type(disposition.material) is bool
                     and isinstance(disposition.rationale, str) and disposition.rationale.strip())
        signals.append(ExceptionSignal(signal_id, sid, b.document.filename, segment.location, segment.text,
                       ("material" if disposition.material else "dismissed_by_analyst") if valid else "needs_review",
                       disposition.rationale if valid else "Potential exception; inspect the full source context."))
    latest_capture = max((b.source.captured_on for b in evidence if b.source.captured_on), default=None)
    bundle_valid = bool(active.bundle_review and active.bundle_review.bundle_fingerprint == bundle
                        and _review_valid(active.bundle_review, case.as_of, latest_capture)
                        and active.bundle_review.signal_dispositions == active.signal_dispositions)
    if specialist:
        technical = specialist.evaluate(case.threshold, tuple(accepted), case.as_of)
    else:
        # Evidence inventory can remain useful even without candidate extraction.
        # Policy intent alone is not pertinent implementation/operating evidence.
        usable = any(not source_limits[b.fingerprint] and b.source.evidence_kind != "policy" for b in evidence)
        requested = "; ".join(r.required_evidence) or "current in-scope implementation or operating evidence"
        technical = TechnicalResult(
            "Needs Review" if usable else "Evidence Missing",
            (Check("specialist_evaluation", "uncertain", SPECIALIST_LIMITATION),),
            "Arrange specialist review of the cited evidence against the supplied customer acceptance criteria."
            if usable else "Request " + requested + "; then arrange specialist evaluation.",
        )
        limitations.append(SPECIALIST_LIMITATION)
    if any(not f.confirmed for f in facts):
        limitations.append("Confirm or challenge each interpretation; quotation matching does not establish meaning.")
    if any(s.status != "dismissed_by_analyst" for s in signals):
        limitations.append("Resolve retained potential or material source exceptions separately from supporting facts.")
    if not bundle_valid:
        limitations.append("Explicit review of the complete source bundle is still required.")
    outcome = technical.outcome
    if specialist and limitations and outcome != "Risk Identified":
        outcome = "Needs Review"
    next_action = technical.next_action
    if outcome not in {"Risk Identified", "Evidence Missing"} and not any(c.status == "conflict" for c in technical.checks):
        if any(source_limits.values()):
            next_action = limitations[0]
        elif any(not f.confirmed and not f.reasons and f.direction == "adverse" for f in facts):
            next_action = "Check the proposed exception's meaning and affected scope separately against its full source."
        elif any(not f.confirmed and not f.reasons and f.direction == "support" for f in facts):
            next_action = "Check the displayed supporting interpretations against their full sources before confirming meaning."
        elif any(not f.confirmed and not f.reasons and f.direction == "review" for f in facts):
            next_action = "Check the cited interpretation's meaning in its full source before specialist evaluation."
        elif any(s.status != "dismissed_by_analyst" for s in signals):
            next_action = "Investigate the retained source exception signals in full context."
        elif not bundle_valid:
            next_action = "Review the complete supplied bundle, including uncited documents and disagreements."
        elif limitations and specialist:
            next_action = limitations[0]
    return ControlReview(r, case.threshold_summary, case.as_of, outcome, technical.checks,
                         tuple(facts), evidence, tuple(signals), tuple(dict.fromkeys(limitations)),
                         next_action, bundle, bundle_valid, specialist is not None)


def record_control_review(case, state, *, action, expected_bundle, analyst, reviewed_on,
                          rationale, fact_ids=(), presented_fingerprints=(), confirms=False,
                          decision="supported", signal_id="", material=True):
    """Explicit session actions; grouping never includes adverse facts or triage.

    The caller supplies an authorized identity in deployment. This synthetic API
    deliberately makes no claim to authenticate that identity.
    """
    view = inspect_control(case, state)
    if expected_bundle != view.bundle_fingerprint:
        raise ValueError("The source/policy bundle changed; inspect it again.")
    metadata = BundleReview(expected_bundle, analyst, reviewed_on, rationale)
    latest = max((b.source.captured_on for b in view.evidence if b.source.captured_on), default=None)
    if not _review_valid(metadata, case.as_of, latest):
        raise ValueError("A current named analyst and nonempty rationale are required.")
    active = state if state.bundle_fingerprint == expected_bundle else ControlReviewState(events=state.events)
    fingerprints = ()
    targets = ()
    if action in {"support", "meaning", "exception", "challenge"}:
        rows = {f.proposal.fact_id: f for f in view.facts}
        targets = tuple(fact_ids)
        if not targets or len(set(targets)) != len(targets) or any(x not in rows for x in targets):
            raise ValueError("Select current, unique interpretations.")
        selected = tuple(rows[x] for x in targets)
        fingerprints = tuple(f.fingerprint for f in selected)
        if tuple(presented_fingerprints) != fingerprints:
            raise ValueError("The displayed interpretation fingerprints changed.")
        if action == "challenge":
            if len(targets) != 1 or decision not in {"unsupported", "ambiguous"}:
                raise ValueError("Challenge one interpretation as unsupported or ambiguous.")
        else:
            if confirms is not True or decision != "supported" or any(f.reasons for f in selected):
                raise ValueError("Explicit semantic confirmation of valid source context is required.")
            if action == "support" and any(f.direction != "support" for f in selected):
                raise ValueError("Adverse or unknown interpretations require separate review.")
            if action == "meaning" and (view.specialist_available
                    or len(targets) != 1 or selected[0].direction != "review"):
                raise ValueError("Confirm one fallback interpretation's meaning separately from threshold evaluation.")
            if action == "exception" and (len(targets) != 1 or selected[0].direction != "adverse"):
                raise ValueError("Confirm each exception interpretation separately.")
        reviews = tuple(x for x in active.fact_reviews if x.fact_fingerprint not in fingerprints)
        by_source = {segment_id(b.source.document_id, i): b.source
                     for b in view.evidence for i, _ in enumerate(b.document.segments, 1)}
        for f in selected:
            classification = "unsupported_interpretation"
            if action != "challenge":
                kind = by_source[f.proposal.source_id].evidence_kind
                classification = {"policy": "policy_assertion", "assertion": "policy_assertion",
                                  "configuration": "implementation_evidence", "test": "operating_test"}[kind]
            reviews += (FactReview(f.fingerprint, decision, classification, analyst, reviewed_on, rationale),)
        active = replace(active, fact_reviews=reviews, bundle_review=None)
    elif action == "signal":
        if signal_id not in {s.signal_id for s in view.signals} or type(material) is not bool:
            raise ValueError("Triage a current source signal explicitly.")
        targets = (signal_id,)
        ds = tuple(d for d in active.signal_dispositions if d.signal_id != signal_id)
        active = replace(active, signal_dispositions=ds + (SignalDisposition(signal_id, material, rationale),),
                         bundle_review=None)
    elif action == "bundle":
        if confirms is not True:
            raise ValueError("Explicit complete-bundle acknowledgment is required.")
        active = replace(active, bundle_review=replace(metadata, signal_dispositions=active.signal_dispositions))
    else:
        raise ValueError("Unknown review action.")
    event = ReviewEvent(action if action != "challenge" else "challenge_" + decision,
                        expected_bundle, fingerprints, targets, analyst, reviewed_on, rationale)
    return replace(active, bundle_fingerprint=expected_bundle, events=active.events + (event,))
