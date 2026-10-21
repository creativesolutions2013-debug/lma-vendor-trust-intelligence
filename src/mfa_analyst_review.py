"""M3C-1: an in-memory review adapter; M3B remains the validation gate.

Grouped confirmation records an explicit human interpretation of a displayed
fact set. It never infers meaning, triages exceptions, acknowledges sources or
approves a control implicitly. Reviewer identity is a caller input, not auth.
"""
from dataclasses import dataclass, replace
from datetime import date

from src.evidence_fact_validation import (
    BundleReview, EvidenceInput, FactReview, ProposedFact, SignalDisposition,
    ValidationResult, fact_fingerprint, validate_and_evaluate_mfa,
)
from src.evidence_intelligence_m3 import DIMENSIONS, KNOWN_METHODS, MfaRequirement


@dataclass(frozen=True)
class ReviewCase:
    case_id: str
    title: str
    requirement: MfaRequirement
    documents: tuple[EvidenceInput, ...]
    proposals: tuple[ProposedFact, ...]
    as_of: date
    supporting_fact_ids: tuple[str, ...]


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
class ReviewState:
    fact_reviews: tuple[FactReview, ...] = ()
    signal_dispositions: tuple[SignalDisposition, ...] = ()
    bundle_review: BundleReview | None = None
    events: tuple[ReviewEvent, ...] = ()
    bundle_fingerprint: str = ""


@dataclass(frozen=True)
class SourceExcerpt:
    source_id: str
    filename: str
    location: str
    quote: str


@dataclass(frozen=True)
class FactPresentation:
    fact_id: str
    fingerprint: str
    statement: str
    source_id: str
    filename: str
    location: str
    quote: str
    confirmed: bool


@dataclass(frozen=True)
class ReviewIssue:
    kind: str
    title: str
    detail: str
    priority: int
    fact_ids: tuple[str, ...] = ()
    signal_ids: tuple[str, ...] = ()
    citations: tuple[SourceExcerpt, ...] = ()


@dataclass(frozen=True)
class ReviewView:
    validation: ValidationResult
    supporting: tuple[FactPresentation, ...]
    issues: tuple[ReviewIssue, ...]
    next_action: str
    bundle_fingerprint: str
    supporting_fingerprints: tuple[str, ...]


def _base(case):
    if (not case.case_id or len(set(case.supporting_fact_ids)) != len(case.supporting_fact_ids)
            or not set(case.supporting_fact_ids) <= {p.fact_id for p in case.proposals}):
        raise ValueError("Supporting fact IDs must be unique members of the displayed case.")
    return validate_and_evaluate_mfa(case.requirement, case.documents, case.proposals, as_of=case.as_of)


def _evaluate(case, state):
    # A pre-fix session may contain a confirmed method with unknown activation.
    # Preserve that history, but never promote it to current assurance/failure.
    unknown_activation = {fact_fingerprint(p) for p in case.proposals
                          if p.fact.dimension == "method" and p.fact.active is None}
    return validate_and_evaluate_mfa(
        case.requirement, case.documents, case.proposals, as_of=case.as_of,
        fact_reviews=tuple(review for review in state.fact_reviews
                           if not (review.decision == "supported"
                                   and review.fact_fingerprint in unknown_activation)),
        bundle_review=state.bundle_review,
    )


def _excerpt(proposal, validation):
    filename = "Unmatched source"
    for owner in validation.evidence:
        if proposal.fact.citation.source_id.startswith(owner.source.document_id + ":"):
            filename = owner.document.filename
            break
    return SourceExcerpt(proposal.fact.citation.source_id, filename,
                         proposal.location, proposal.fact.citation.quote)


def describe_interpretation(proposal):
    fact = proposal.fact
    labels = {
        "existence": "MFA is implemented for the complete stated administrator population",
        "enforcement": "Every administrator in the stated population must complete MFA before access",
        "operating": "Actual operating tests cover the complete stated administrator and authentication-path inventory",
        "fallback_safe": "Every fallback path meets the same customer MFA threshold, or no fallback path exists",
        "recovery_safe": "Every recovery path preserves the same customer MFA threshold before administrative access",
        "exceptions_absent": "The complete stated administrator and authentication-path inventory has no exceptions",
    }
    if fact.dimension == "method":
        def shown(value):
            return "yes" if value is True else "no" if value is False else "unknown"
        statement = (
            f"Method {fact.value or 'unknown'} on path {fact.authentication_path or 'unspecified'}; "
            f"active: {shown(fact.active)}; deployed implementation: {shown(fact.implementation_evidenced)}; "
            f"multiple factors: {shown(fact.multifactor)}; origin binding: {shown(fact.origin_bound)}; "
            f"verifier binding: {shown(fact.verifier_bound)}"
        )
    else:
        statement = labels.get(fact.dimension, fact.dimension) + f": {fact.value}"
    if fact.uncertainty:
        statement += ". Uncertainty: " + fact.uncertainty
    return statement


def _positive_candidate(proposal, policy):
    fact = proposal.fact
    if fact.evidence_kind not in {"configuration", "test"} or fact.uncertainty:
        return False
    if fact.dimension != "method":
        return fact.value is True and (fact.dimension != "operating" or fact.evidence_kind == "test")
    return (fact.value in policy.allowed_methods and fact.implementation_evidenced is True
            and fact.multifactor is True and fact.active is True and bool(fact.authentication_path)
            and (not policy.phishing_resistant or (
                fact.value not in {"sms", "totp", "push"}
                and fact.origin_bound is True and fact.verifier_bound is True)))


def _adverse_candidate(proposal, policy):
    """Unknown implementation details are gaps, not affirmative exceptions."""
    fact = proposal.fact
    if fact.value is False:
        return True
    if (fact.dimension != "method" or fact.active is not True
            or fact.value not in KNOWN_METHODS | set(policy.approved_equivalents)
            or fact.implementation_evidenced is not True):
        return False
    return (fact.value not in policy.allowed_methods or fact.multifactor is False
            or (policy.phishing_resistant and (
                fact.value in {"sms", "totp", "push"}
                or fact.origin_bound is False or fact.verifier_bound is False)))


def inspect_review(case: ReviewCase, state: ReviewState = ReviewState()) -> ReviewView:
    """Present retained evidence first; no reviews are generated by inspection."""
    base = _base(case)
    has_decisions = bool(state.fact_reviews or state.signal_dispositions or state.bundle_review or state.events)
    changed = state.bundle_fingerprint != base.bundle_fingerprint and bool(state.bundle_fingerprint or has_decisions)
    if changed:
        state = ReviewState()
    validation = _evaluate(case, state)
    assessed = {fact_fingerprint(v.proposal): v for v in validation.facts}
    accepted = {fact_fingerprint(p): item for p in case.proposals
                for item in validation.evaluation.facts if item.fact == p.fact}
    reviews = {r.fact_fingerprint: r for r in state.fact_reviews}
    excerpts = {p.fact_id: _excerpt(p, validation) for p in case.proposals}
    supporting = []
    issues = []
    contested = {dimension for dimension in DIMENSIONS
                 if any(p.fact.dimension == dimension and p.fact.value is True for p in case.proposals)
                 and any(p.fact.dimension == dimension and p.fact.value is False for p in case.proposals)}
    if changed:
        issues.append(ReviewIssue("review_changed", "Evidence or requirement changed",
                                  "Earlier review decisions are invalid for this snapshot; review again.", 0))
    for proposal in case.proposals:
        fingerprint = fact_fingerprint(proposal)
        result = assessed[fingerprint]
        interpretation = accepted.get(fingerprint)
        excerpt = excerpts[proposal.fact_id]
        mechanical = tuple(reason for reason in result.reasons
                           if not reason.startswith("A unique, current analyst semantic disposition"))
        review = reviews.get(fingerprint)
        if (proposal.fact_id in case.supporting_fact_ids and _positive_candidate(proposal, case.requirement)
                and result.citation_verified and not mechanical and proposal.fact.dimension not in contested
                and (review is None or review.classification not in {"explicit_exception", "conflicting_statement"})):
            supporting.append(FactPresentation(
                proposal.fact_id, fingerprint, describe_interpretation(proposal), excerpt.source_id,
                excerpt.filename, excerpt.location, excerpt.quote,
                result.status == "validated" and interpretation is not None
                and interpretation.status == "supports",
            ))
        negative = _adverse_candidate(proposal, case.requirement)
        inactive_method = proposal.fact.dimension == "method" and proposal.fact.active is not True
        if inactive_method:
            issues.append(ReviewIssue(
                "method_activation_gap",
                "Method path activation is unverified" if proposal.fact.active is None else "Method path is disabled",
                "Verify whether this authentication path is enabled before judging current noncompliance."
                if proposal.fact.active is None else
                "A disabled method does not establish an active authentication path or a current control failure.",
                2, (proposal.fact_id,), citations=(excerpt,),
            ))
        if interpretation and interpretation.status == "adverse":
            issues.append(ReviewIssue("verified_failure", "Evidence-backed threshold failure — provisional",
                                      interpretation.reason, 0, (proposal.fact_id,), citations=(excerpt,)))
        elif negative and proposal.fact.evidence_kind == "assertion":
            issues.append(ReviewIssue("vendor_reported_exception", "Vendor-reported exception — unverified",
                                      "An assertion is not verified implementation evidence. Investigate affected accounts and paths.",
                                      1, (proposal.fact_id,), citations=(excerpt,)))
        elif negative and proposal.fact.evidence_kind in {"configuration", "test"}:
            issues.append(ReviewIssue("potential_exception", "Potential control exception",
                                      "Confirm the statement's meaning and scope separately from supporting facts.",
                                      2, (proposal.fact_id,), citations=(excerpt,)))
        if (review and proposal.fact_id in case.supporting_fact_ids
                and review.decision in {"unsupported", "ambiguous"}):
            issues.append(ReviewIssue("challenged_interpretation", "Supporting interpretation challenged",
                                      f"{review.decision}: {review.rationale}", 1,
                                      (proposal.fact_id,), citations=(excerpt,)))
        if review and (review.classification == "conflicting_statement"
                       or (review.classification == "explicit_exception" and not negative and not inactive_method)):
            issues.append(ReviewIssue("conflict" if review.classification == "conflicting_statement" else "potential_exception",
                                      "Retained analyst-identified exception or disagreement", review.rationale,
                                      1, (proposal.fact_id,), citations=(excerpt,)))
        if mechanical:
            issues.append(ReviewIssue("source_integrity" if not result.citation_verified else "incomplete_evidence",
                                      "Interpretation or source needs review", " ".join(mechanical),
                                      1 if not result.citation_verified else 4,
                                      (proposal.fact_id,), citations=(excerpt,)))
        if proposal.fact.uncertainty or proposal.fact.value is None:
            issues.append(ReviewIssue("incomplete_evidence", "Uncertain interpretation",
                                      proposal.fact.uncertainty or "The proposed fact is unknown.",
                                      4, (proposal.fact_id,), citations=(excerpt,)))
    # Conflicts are retained from proposals even before either account is accepted.
    for dimension in DIMENSIONS:
        rows = [p for p in case.proposals if p.fact.dimension == dimension]
        if any(a.fact.value is True and b.fact.value is False for a in rows for b in rows):
            issues.append(ReviewIssue("conflict", "Conflicting source statements",
                                      f"Sources disagree about {dimension}; positive evidence cannot resolve this silently.",
                                      1, tuple(p.fact_id for p in rows),
                                      citations=tuple(excerpts[p.fact_id] for p in rows)))
    disposition_rows = {}
    for item in state.signal_dispositions:
        disposition_rows.setdefault(item.signal_id, []).append(item)
    dispositions = {sid: rows[0] for sid, rows in disposition_rows.items()
                    if len(rows) == 1 and type(rows[0].material) is bool
                    and isinstance(rows[0].rationale, str) and rows[0].rationale.strip()}
    for signal in validation.signals:
        disposition = dispositions.get(signal.signal_id)
        # Nonmaterial dispositions remain accessible in source detail, rather
        # than hiding the underlying source or deleting its M3B signal.
        if disposition is None or disposition.material or signal.status == "material":
            material = signal.status == "material" or (disposition is not None and disposition.material)
            issues.append(ReviewIssue("potential_exception", "Material exception" if material else "Potential exception — triage needed",
                                      signal.rationale if signal.status == "material" else
                                      disposition.rationale if disposition else signal.rationale, 2,
                                      signal_ids=(signal.signal_id,), citations=(SourceExcerpt(
                                          signal.source_id, signal.filename, signal.location, signal.quote),)))
    policy = case.requirement
    for owner in validation.evidence:
        source = owner.source
        source_citations = tuple(SourceExcerpt(f"{source.document_id}:{i}", owner.document.filename,
                                               part.location, part.text)
                                 for i, part in enumerate(owner.document.segments, 1))
        if (any(not isinstance(value, str) or not value.strip() for value in (source.version, source.origin))
                or source.captured_on is None or source.captured_on > case.as_of
                or (source.observed_on is not None and source.captured_on is not None
                    and source.observed_on > source.captured_on)):
            issues.append(ReviewIssue("source_integrity", "Source provenance needs verification",
                                      f"{owner.document.filename}: version, origin or capture chronology is missing or inconsistent.",
                                      1, citations=source_citations[:1]))
        if source.observed_on is None or not 0 <= (case.as_of - source.observed_on).days <= policy.max_age_days:
            issues.append(ReviewIssue("stale_evidence", "Evidence date needs review",
                                      f"{owner.document.filename}: observation {source.observed_on}; maximum age {policy.max_age_days} days. Staleness is not control failure.",
                                      2, citations=source_citations[:1]))
        if (source.service, source.environment, source.account_scope) != (policy.service, policy.environment, policy.account_scope):
            issues.append(ReviewIssue("scope_gap", "Service or administrator scope gap",
                                      f"{owner.document.filename} declares {source.service} / {source.environment} / {source.account_scope}.",
                                      2, citations=source_citations[:1]))
    present = {p.fact.dimension for p in case.proposals if _positive_candidate(p, policy)}
    missing = [d for d in DIMENSIONS if d not in present and not (d == "operating" and not policy.require_operating)]
    if missing:
        issues.append(ReviewIssue("incomplete_evidence", "Incomplete administrator or authentication-path evidence",
                                  "Missing supported interpretations for: " + ", ".join(missing) +
                                  ". Account coverage, fallback and recovery must be established explicitly.", 4))
    coverage = [dimension for dimension in ("enforcement", "fallback_safe", "recovery_safe")
                if dimension not in present]
    if coverage:
        issues.append(ReviewIssue("scope_gap", "Administrator or recovery-path coverage is unverified",
                                  "Unverified complete-scope evidence for: " + ", ".join(coverage) + ".", 2))
    displayed_ids = {item.fact_id for item in supporting}
    pending = [p for p in case.proposals if p.fact_id not in displayed_ids
               and not _adverse_candidate(p, policy) and assessed[fact_fingerprint(p)].status != "validated"]
    if pending:
        issues.append(ReviewIssue("incomplete_evidence", "Remaining interpretations need review",
                                  "These proposals are not confirmed by the supporting group: " +
                                  ", ".join(p.fact_id for p in pending) + ".",
                                  4, tuple(p.fact_id for p in pending),
                                  citations=tuple(excerpts[p.fact_id] for p in pending)))
    issues.sort(key=lambda item: (item.priority, item.kind, item.title, item.fact_ids, item.signal_ids))
    supporting.sort(key=lambda item: ({"test": 0, "configuration": 1, "policy": 2, "assertion": 3}.get(
        next(p.fact.evidence_kind for p in case.proposals if p.fact_id == item.fact_id), 4), item.fact_id))
    if issues:
        next_action = {
            "verified_failure": "Escalate the evidenced threshold failure and request affected-account/path remediation evidence.",
            "vendor_reported_exception": "Verify the vendor-reported exception with current account/path configuration and operating tests.",
            "conflict": "Reconcile the conflicting source statements for the affected administrator and authentication paths.",
            "potential_exception": "Investigate the highest-priority exception in its full source context before drawing assurance.",
            "stale_evidence": "Request current in-scope operating evidence for the stated administrator and path inventory.",
            "scope_gap": "Request evidence covering this service and the complete administrator, fallback and recovery scope.",
            "method_activation_gap": "Verify which administrator authentication paths are enabled using current configuration and operating evidence.",
            "challenged_interpretation": "Resolve the challenged interpretation against its full source context or request the missing evidence.",
            "source_integrity": "Verify the original source identity, provenance and exact citation before relying on the interpretation.",
            "review_changed": "Review the changed evidence and interpretations again.",
        }.get(issues[0].kind, "Request the missing account/path implementation and operating evidence.")
    elif any(not item.confirmed for item in supporting):
        next_action = "Check the displayed supporting interpretations against full source context, then explicitly confirm their meaning."
    elif not validation.bundle_review_valid:
        next_action = "Acknowledge review of the complete source bundle after separate exception triage."
    elif validation.evaluation.outcome != "Met":
        next_action = "Resolve the remaining M3B evidence and interpretation limitations before drawing assurance."
    else:
        next_action = "Send the provisional result for independent governed review; no control or risk decision has been recorded."
    return ReviewView(validation, tuple(supporting), tuple(issues), next_action,
                      base.bundle_fingerprint, tuple(item.fingerprint for item in supporting))


def _context(case, state, expected_bundle, analyst, reviewed_on, rationale):
    base = _base(case)
    if (expected_bundle != base.bundle_fingerprint or
            state.bundle_fingerprint not in {"", base.bundle_fingerprint}):
        raise ValueError("Evidence, requirement or interpretation changed; refresh the displayed review.")
    if (not isinstance(analyst, str) or not analyst.strip() or not isinstance(rationale, str)
            or not rationale.strip() or type(reviewed_on) is not date or reviewed_on > case.as_of
            or any(s.captured_on is not None and reviewed_on < s.captured_on for s in case.documents)):
        raise ValueError("An explicit analyst identity, current review date and substantive rationale are required.")
    if not state.bundle_fingerprint and (state.fact_reviews or state.signal_dispositions or state.bundle_review or state.events):
        raise ValueError("Review state must be bound to its source bundle.")
    return base.bundle_fingerprint


def _event(state, bundle, kind, fingerprints, targets, analyst, reviewed_on, rationale, **changes):
    event = ReviewEvent(kind, bundle, tuple(fingerprints), tuple(targets), analyst.strip(), reviewed_on, rationale.strip())
    if state.events and state.events[-1] == event:
        raise ValueError("This review action was already recorded.")
    return replace(state, bundle_fingerprint=bundle, events=state.events + (event,), **changes)


def confirm_supporting(case, state, *, expected_bundle, presented_fingerprints,
                       confirms_semantics, analyst, reviewed_on, rationale):
    bundle = _context(case, state, expected_bundle, analyst, reviewed_on, rationale)
    if confirms_semantics is not True:
        raise ValueError("Explicit confirmation of the displayed interpretations is required.")
    view = inspect_review(case, state)
    expected = view.supporting_fingerprints
    supplied = tuple(presented_fingerprints)
    if not expected or len(set(supplied)) != len(supplied) or set(supplied) != set(expected):
        raise ValueError("Confirm the complete exact displayed supporting fact set; partial, duplicate or extra facts are not accepted.")
    proposals = [p for p in case.proposals if fact_fingerprint(p) in expected]
    if any(not _positive_candidate(p, case.requirement) for p in proposals):
        raise ValueError("Unsupported, uncertain or adverse interpretations require separate review.")
    if any(r.fact_fingerprint in expected for r in state.fact_reviews):
        raise ValueError("Supporting interpretations were already reviewed; refresh rather than replaying confirmation.")
    reviews = tuple(FactReview(fact_fingerprint(p), "supported", "operating_test" if p.fact.evidence_kind == "test"
                               else "implementation_evidence", analyst.strip(), reviewed_on, rationale.strip()) for p in proposals)
    updated = _event(state, bundle, "group_confirmation", tuple(fact_fingerprint(p) for p in proposals),
                     tuple(p.fact_id for p in proposals),
                     analyst, reviewed_on, rationale, fact_reviews=state.fact_reviews + reviews, bundle_review=None)
    checked = _evaluate(case, updated)
    targets = {fact_fingerprint(p) for p in proposals}
    if any(row.status != "validated" for row in checked.facts if fact_fingerprint(row.proposal) in targets):
        raise ValueError("M3B rejected one or more supporting fact bindings, scope, provenance or dates; no confirmation was recorded.")
    return updated


def confirm_exception(case, state, *, expected_bundle, fact_id, confirms_semantics,
                      analyst, reviewed_on, rationale):
    bundle = _context(case, state, expected_bundle, analyst, reviewed_on, rationale)
    rows = [p for p in case.proposals if p.fact_id == fact_id]
    if (confirms_semantics is not True or len(rows) != 1
            or fact_id in {p.fact_id for p in inspect_review(case, state).supporting}):
        raise ValueError("Explicit separate confirmation of a displayed adverse interpretation is required.")
    proposal = rows[0]
    if not _adverse_candidate(proposal, case.requirement):
        raise ValueError("This interpretation is not an explicit adverse statement.")
    fingerprint = fact_fingerprint(proposal)
    if any(r.fact_fingerprint == fingerprint for r in state.fact_reviews):
        raise ValueError("This exception interpretation was already reviewed.")
    review = FactReview(fingerprint, "supported", "explicit_exception", analyst.strip(), reviewed_on, rationale.strip())
    updated = _event(state, bundle, "exception_confirmation", (fingerprint,), (fact_id,),
                     analyst, reviewed_on, rationale, fact_reviews=state.fact_reviews + (review,), bundle_review=None)
    if next(v for v in _evaluate(case, updated).facts if v.proposal.fact_id == fact_id).status != "validated":
        raise ValueError("M3B rejected the exception's source binding, scope, provenance or date; retain it for investigation.")
    return updated


def challenge_supporting(case, state, *, expected_bundle, fact_id, decision,
                         analyst, reviewed_on, rationale):
    """Supersede one positive interpretation without erasing earlier decisions."""
    bundle = _context(case, state, expected_bundle, analyst, reviewed_on, rationale)
    rows = [p for p in case.proposals if p.fact_id == fact_id]
    if (decision not in ("unsupported", "ambiguous") or len(rows) != 1
            or fact_id not in case.supporting_fact_ids):
        raise ValueError("Select a supporting interpretation and an unsupported/ambiguous disposition.")
    fingerprint = fact_fingerprint(rows[0])
    review = FactReview(fingerprint, decision, "unsupported_interpretation",
                        analyst.strip(), reviewed_on, rationale.strip())
    reviews = tuple(item for item in state.fact_reviews if item.fact_fingerprint != fingerprint) + (review,)
    return _event(state, bundle, "challenge_" + decision, (fingerprint,), (fact_id,),
                  analyst, reviewed_on, rationale, fact_reviews=reviews, bundle_review=None)


def triage_signal(case, state, *, expected_bundle, signal_id, material,
                  analyst, reviewed_on, rationale):
    bundle = _context(case, state, expected_bundle, analyst, reviewed_on, rationale)
    if type(material) is not bool or signal_id not in {s.signal_id for s in _base(case).signals}:
        raise ValueError("A separate explicit material/nonmaterial decision for a current signal is required.")
    disposition = SignalDisposition(signal_id, material, rationale.strip())
    if disposition in state.signal_dispositions:
        raise ValueError("This signal disposition was already recorded.")
    dispositions = tuple(s for s in state.signal_dispositions if s.signal_id != signal_id) + (disposition,)
    return _event(state, bundle, "signal_triage", (), (signal_id,), analyst, reviewed_on, rationale,
                  signal_dispositions=dispositions, bundle_review=None)


def acknowledge_bundle(case, state, *, expected_bundle, confirms_complete_bundle,
                        analyst, reviewed_on, rationale):
    bundle = _context(case, state, expected_bundle, analyst, reviewed_on, rationale)
    if confirms_complete_bundle is not True:
        raise ValueError("Explicit review of the entire supplied source bundle is required.")
    if state.bundle_review is not None:
        raise ValueError("This bundle was already acknowledged.")
    acknowledgment = BundleReview(bundle, analyst.strip(), reviewed_on, rationale.strip(), state.signal_dispositions)
    return _event(state, bundle, "bundle_acknowledgment", tuple(fact_fingerprint(p) for p in case.proposals),
                  tuple(d.document_id for d in case.documents), analyst, reviewed_on, rationale,
                  bundle_review=acknowledgment)
