"""Adversarial synthetic need matching; artifact kind is never factual support."""
from dataclasses import replace
from datetime import timedelta

import pytest

from src.applicability import ApplicabilityResult
from src.assessment_worklist import (
    AssessmentScope, AssuranceLink, EvidenceNeed, RequirementMapping,
    build_assessment_worklist, record_need_review,
)
from src.control_assurance import ControlReviewState, inspect_control, record_control_review
from src.control_assurance_pilot import control_pilot_cases, document, proposal, suitability_pilot_cases
from src.dr_assurance import DrThreshold
from src.evidence_source_validation import bind_evidence
from src.tiering import ControlRequirement


CASES = {case.case_id: case for case in control_pilot_cases()}
SUPPORTED = "Supported by reviewed evidence"
VALIDATE = "Analyst validation required"
MISSING = "Missing or insufficient"


def need(dimension="achieved_rpo_minutes"):
    label = "RPO" if dimension == "achieved_rpo_minutes" else "RTO"
    return EvidenceNeed(
        "operating-" + label.lower(), f"Achieved {label} for the complete production recovery service",
        f"A dated complete-service exercise record documenting achieved {label}",
        f"Provide the dated complete-service achieved {label} record for Acme Analytics production.",
        ("test",), dimensions=(dimension,), max_age_days=365,
    )


def rto_only():
    full = CASES["dr-strong"]
    report = document(
        "dr-rto-only",
        "SYNTHETIC witnessed recovery exercise: achieved RTO was 120 minutes. This record addresses recovery time only.",
        full.requirement.scope,
    )
    fact = proposal(report, "achieved_rto_minutes", 1, 120)
    return replace(full, case_id="dr-rto-only", documents=(report,), proposals=(fact,))


def context(case):
    return AssessmentScope("synthetic-need-matching", case.requirement.service,
                           case.requirement.environment, case.as_of)


def mapping(case, needs):
    return RequirementMapping("BCP-01", case.requirement, case.threshold, tuple(needs))


def confirm(case, *, dimensions=None, adverse=False):
    """Explicit test decisions before inspection, never product-generated review."""
    state = ControlReviewState()
    initial = inspect_control(case)
    common = dict(expected_bundle=initial.bundle_fingerprint, analyst="Synthetic independent reviewer",
                  reviewed_on=case.as_of, rationale="Checked exact source meaning, technical value and complete affected context.")
    facts = tuple(f for f in initial.facts if not f.reasons and f.direction == "support"
                  and (dimensions is None or f.proposal.dimension in dimensions))
    if facts:
        state = record_control_review(
            case, state, action="support", fact_ids=tuple(f.proposal.fact_id for f in facts),
            presented_fingerprints=tuple(f.fingerprint for f in facts), confirms=True, **common,
        )
    if adverse:
        for fact in initial.facts:
            if fact.direction == "adverse" and not fact.reasons:
                state = record_control_review(
                    case, state, action="exception", fact_ids=(fact.proposal.fact_id,),
                    presented_fingerprints=(fact.fingerprint,), confirms=True, **common,
                )
    return state


def explicit_need_review(case, requirement, item, state, decision, *, facts=None):
    view = inspect_control(case, state)
    sources = tuple(b.fingerprint for b in view.evidence if b.source.evidence_kind in item.accepted_kinds)
    if facts is None:
        facts = tuple(f.fingerprint for f in view.facts
                      if f.proposal.dimension in item.dimensions and f.confirmed)
    return record_need_review(
        context(case), requirement, case, state, item, decision=decision,
        source_fingerprints=sources, fact_fingerprints=tuple(facts),
        confirms=True,
        analyst="Synthetic independent reviewer", reviewed_on=case.as_of,
        rationale=("The supplied time-only exercise record omits the required recovery point result."
                   if decision == "insufficient" else
                   "Verified this exact need against its cited confirmed facts and customer threshold."),
    )


def build(case, needs, *, state=ControlReviewState(), reviews=(), scope=None, extra_links=(), extra_requirements=()):
    requirement = mapping(case, needs)
    current_scope = scope or context(case)
    requirements = (requirement,) + tuple(extra_requirements)
    applicable = ApplicabilityResult(
        controls=tuple(ControlRequirement(item.control_id, "Synthetic test domain", "Explicit customer requirement")
                       for item in requirements),
        evidence=(), decisions=(), review_required=True, review_reasons=("Synthetic review only.",),
    )
    links = (AssuranceLink(current_scope.engagement_id, "BCP-01", case, state, tuple(reviews)),) + tuple(extra_links)
    return build_assessment_worklist(current_scope, applicable, requirements, links)


def matches(result):
    return {match.need_id: match for row in result.rows for match in row.need_matches}


def test_rto_only_operating_report_does_not_hide_reviewed_missing_rpo():
    case, item = rto_only(), need()
    state = confirm(case)
    requirement = mapping(case, (item,))
    review = explicit_need_review(case, requirement, item, state, "insufficient")
    result = build(case, (item,), state=state, reviews=(review,))
    assert matches(result)[item.need_id].status == MISSING
    assert len(result.requests) == 1 and result.requests[0].question == item.question
    assert result.rows[0].outcome not in {"Met", "Risk Identified"}
    assert item.missing_fact in result.rows[0].missing_fact
    assert result.rows[0].review.evidence[0].document.filename == "dr-rto-only.txt"


def test_same_kind_source_relevant_to_other_aspect_cannot_close_this_need():
    case, item = rto_only(), need()
    state = confirm(case)
    result = build(case, (item,), state=state)
    match = matches(result)[item.need_id]
    assert match.status == VALIDATE
    assert not result.requests
    assert result.rows[0].intent == "Analyst validate"
    wrong_dimension = tuple(f.fingerprint for f in inspect_control(case, state).facts if f.confirmed)
    with pytest.raises(ValueError):
        explicit_need_review(case, mapping(case, (item,)), item, state, "supported", facts=wrong_dimension)


def test_plausible_unreviewed_candidate_requires_validation_not_premature_follow_up():
    case, item = CASES["dr-strong"], need()
    result = build(case, (item,))
    assert matches(result)[item.need_id].status == VALIDATE
    assert result.rows[0].intent == "Analyst validate" and not result.requests
    assert not any(f.confirmed for f in result.rows[0].review.facts)
    view = inspect_control(case)
    proposed = tuple(f.fingerprint for f in view.facts if f.proposal.dimension in item.dimensions)
    with pytest.raises(ValueError):
        explicit_need_review(case, mapping(case, (item,)), item, ControlReviewState(), "supported", facts=proposed)


def test_reviewed_specific_match_suppresses_only_its_need_not_other_facts():
    case, rto, rpo = rto_only(), need("achieved_rto_minutes"), need()
    state = confirm(case)
    requirement = mapping(case, (rto, rpo))
    supported = explicit_need_review(case, requirement, rto, state, "supported")
    insufficient = explicit_need_review(case, requirement, rpo, state, "insufficient")
    result = build(case, (rto, rpo), state=state, reviews=(supported, insufficient))
    assert matches(result)[rto.need_id].status == SUPPORTED
    assert matches(result)[rpo.need_id].status == MISSING
    assert len(result.requests) == 1 and result.requests[0].question == rpo.question
    assert result.rows[0].missing_fact == rpo.missing_fact
    assert result.rows[0].outcome != "Met"


@pytest.mark.parametrize("mutation", ["source", "threshold", "scope", "assessment_date", "need"])
def test_prior_need_match_cannot_survive_changed_source_threshold_scope_or_definition(mutation):
    case, item = rto_only(), need("achieved_rto_minutes")
    state = confirm(case)
    review = explicit_need_review(case, mapping(case, (item,)), item, state, "supported")
    assert matches(build(case, (item,), state=state, reviews=(review,)))[item.need_id].status == SUPPORTED
    changed = case
    if mutation == "source":
        original = case.documents[0]
        source = replace(original, content=original.content + b"\nSYNTHETIC report revised.")
        changed = replace(case, documents=(source,))
    elif mutation == "threshold":
        changed = replace(case, threshold=DrThreshold(365, 60, 60))
    elif mutation == "scope":
        changed = replace(case, requirement=replace(case.requirement, scope="different complete recovery scope"))
    elif mutation == "assessment_date":
        changed = replace(case, as_of=case.as_of + timedelta(days=1))
    else:
        item = replace(item, missing_fact="Achieved RTO including another required dependency")
    result = build(changed, (item,), state=state, reviews=(review,))
    assert matches(result)[item.need_id].status != SUPPORTED
    assert result.rows[0].outcome != "Met"


def test_absent_artifact_creates_precise_missing_need_without_declaring_failure():
    case, item = replace(CASES["dr-strong"], documents=(), proposals=()), need()
    result = build(case, (item,))
    assert matches(result)[item.need_id].status == MISSING
    assert len(result.requests) == 1 and result.requests[0].question == item.question
    assert result.rows[0].outcome != "Risk Identified"


def test_confirmed_exception_remains_first_while_other_need_request_stays_visible():
    case, item = rto_only(), need()
    state = confirm(case)
    review = explicit_need_review(case, mapping(case, (item,)), item, state, "insufficient")
    adverse = CASES["tls-exception"]
    adverse_state = confirm(adverse, adverse=True)
    extra = RequirementMapping("ENC-01", adverse.requirement, adverse.threshold)
    result = build(case, (item,), state=state, reviews=(review,),
                   extra_requirements=(extra,),
                   extra_links=(AssuranceLink(context(case).engagement_id, "ENC-01", adverse, adverse_state),))
    assert result.rows[0].control_id == "ENC-01" and result.rows[0].outcome == "Risk Identified"
    assert result.rows[0].priority == 0
    assert len(result.requests) == 1 and result.requests[0].question == item.question
    assert result.rows[0].review.provisional and result.rows[0].review.review_required


@pytest.mark.parametrize("decision", ["supported", "insufficient"])
def test_need_review_requires_explicit_confirmation_for_both_decisions(decision):
    case, item = rto_only(), need("achieved_rto_minutes")
    state = confirm(case)
    view = inspect_control(case, state)
    with pytest.raises(ValueError):
        record_need_review(
            context(case), mapping(case, (item,)), case, state, item, decision=decision,
            source_fingerprints=tuple(b.fingerprint for b in view.evidence),
            fact_fingerprints=tuple(f.fingerprint for f in view.facts) if decision == "supported" else (),
            analyst="Synthetic independent reviewer", reviewed_on=case.as_of,
            rationale="Review text alone is not an explicit confirmation action.",
        )


def test_duplicate_need_reviews_require_reconciliation_instead_of_reusing_support():
    case, item = rto_only(), need("achieved_rto_minutes")
    state = confirm(case)
    review = explicit_need_review(case, mapping(case, (item,)), item, state, "supported")
    result = build(case, (item,), state=state, reviews=(review, review))
    assert matches(result)[item.need_id].status == VALIDATE
    assert result.rows[0].intent == "Analyst validate" and not result.requests


def test_challenging_a_previously_confirmed_fact_invalidates_need_support():
    case, item = rto_only(), need("achieved_rto_minutes")
    state = confirm(case)
    review = explicit_need_review(case, mapping(case, (item,)), item, state, "supported")
    view = inspect_control(case, state)
    fact = view.facts[0]
    changed = record_control_review(
        case, state, action="challenge", fact_ids=(fact.proposal.fact_id,),
        presented_fingerprints=(fact.fingerprint,), expected_bundle=view.bundle_fingerprint,
        decision="unsupported", analyst="Synthetic independent reviewer", reviewed_on=case.as_of,
        rationale="On second source review, the interpretation does not establish the required service recovery time.",
    )
    result = build(case, (item,), state=changed, reviews=(review,))
    assert matches(result)[item.need_id].status == VALIDATE
    assert result.rows[0].outcome != "Met"


def test_dimensionless_need_cannot_be_supported_by_generic_source_presence():
    case, item = rto_only(), replace(need("achieved_rto_minutes"), dimensions=())
    state = confirm(case)
    with pytest.raises(ValueError):
        explicit_need_review(case, mapping(case, (item,)), item, state, "supported")


@pytest.mark.parametrize("kind,subject", [("policy", "complete scope"), ("assertion", "complete scope"),
                                         ("test", "database only")])
def test_domain_excluded_operating_fact_cannot_gain_need_support(kind, subject):
    case = rto_only()
    source = replace(case.documents[0], evidence_kind=kind)
    fact = proposal(source, "achieved_rto_minutes", 1, 120, subject=subject)
    changed = replace(case, documents=(source,), proposals=(fact,))
    # Broad candidate kinds permit analyst inspection; they cannot weaken the
    # existing domain evaluator's operating-proof and full-scope restrictions.
    item = replace(need("achieved_rto_minutes"), accepted_kinds=("test", "policy", "assertion"))
    state = confirm(changed)
    assert inspect_control(changed, state).facts[0].confirmed
    assert not any(c.status == "supported" for c in inspect_control(changed, state).checks)
    with pytest.raises(ValueError):
        explicit_need_review(changed, mapping(changed, (item,)), item, state, "supported")


def test_source_from_another_report_cannot_be_paired_with_a_confirmed_fact():
    case, item = rto_only(), need("achieved_rto_minutes")
    unrelated = document("dr-other-test", "SYNTHETIC recovery exercise inventory timestamp record.",
                         case.requirement.scope)
    case = replace(case, documents=case.documents + (unrelated,))
    state = confirm(case)
    view = inspect_control(case, state)
    with pytest.raises(ValueError):
        record_need_review(
            context(case), mapping(case, (item,)), case, state, item, decision="supported", confirms=True,
            source_fingerprints=(bind_evidence(unrelated).fingerprint,),
            fact_fingerprints=(view.facts[0].fingerprint,),
            analyst="Synthetic independent reviewer", reviewed_on=case.as_of,
            rationale="A different report fingerprint cannot carry this confirmed fact.",
        )


@pytest.mark.parametrize("change", ["analyst", "rationale", "future_date", "before_capture"])
def test_need_review_requires_current_named_analyst_and_review_metadata(change):
    case, item = rto_only(), need("achieved_rto_minutes")
    state = confirm(case)
    view = inspect_control(case, state)
    metadata = dict(analyst="Synthetic independent reviewer", reviewed_on=case.as_of,
                    rationale="Checked the specific fact and complete source context.")
    if change in {"analyst", "rationale"}:
        metadata[change] = " "
    elif change == "future_date":
        metadata["reviewed_on"] = case.as_of + timedelta(days=1)
    else:
        metadata["reviewed_on"] = case.documents[0].captured_on - timedelta(days=1)
    with pytest.raises(ValueError):
        record_need_review(
            context(case), mapping(case, (item,)), case, state, item, decision="supported", confirms=True,
            source_fingerprints=(view.evidence[0].fingerprint,),
            fact_fingerprints=(view.facts[0].fingerprint,), **metadata,
        )


def governance_case_and_meaning(*, relevance="current"):
    case = next(c for c in suitability_pilot_cases() if c.case_id == "gov-policy")
    if relevance == "missing":
        case = replace(case, relevance=())
    elif relevance == "stale":
        case = replace(case, relevance=(replace(case.relevance[0], requirement_fingerprint="superseded-policy-binding"),))
    view = inspect_control(case)
    fact = view.facts[0]
    state = record_control_review(
        case, ControlReviewState(), action="meaning", fact_ids=(fact.proposal.fact_id,),
        presented_fingerprints=(fact.fingerprint,), expected_bundle=view.bundle_fingerprint, confirms=True,
        analyst="Synthetic independent reviewer", reviewed_on=case.as_of,
        rationale="Checked the policy's service-specific documented approval, owner and review dates; no operating effectiveness asserted.",
    )
    item = EvidenceNeed("documented-policy", "Current approved service policy with owner and review date",
                        "Approved service-specific governance policy", "Provide the current approved service policy.",
                        ("policy",), dimensions=("documented_policy",))
    return case, item, state


def test_confirmed_governance_need_support_never_becomes_specialist_assurance():
    case, item, state = governance_case_and_meaning()
    review = explicit_need_review(case, mapping(case, (item,)), item, state, "supported")
    result = build(case, (item,), state=state, reviews=(review,))
    assert matches(result)[item.need_id].status == SUPPORTED and not result.requests
    assert result.rows[0].outcome == "Needs Review"
    assert result.rows[0].specialist_available is False
    assert result.rows[0].review.provisional and result.rows[0].review.review_required


@pytest.mark.parametrize("relevance", ["missing", "stale"])
def test_confirmed_fallback_meaning_requires_current_requirement_specific_relevance(relevance):
    case, item, state = governance_case_and_meaning(relevance=relevance)
    view = inspect_control(case, state)
    assert view.facts[0].confirmed and not view.eligible_source_fingerprints
    with pytest.raises(ValueError):
        explicit_need_review(case, mapping(case, (item,)), item, state, "supported")


def test_insufficient_review_cannot_ignore_an_uninspected_same_kind_candidate():
    case, item = rto_only(), need()
    complete = next(d for d in CASES["dr-strong"].documents if d.evidence_kind == "test")
    case = replace(case, documents=case.documents + (complete,))
    state = confirm(case)
    with pytest.raises(ValueError):
        record_need_review(
            context(case), mapping(case, (item,)), case, state, item, decision="insufficient", confirms=True,
            source_fingerprints=(bind_evidence(case.documents[0]).fingerprint,),
            analyst="Synthetic independent reviewer", reviewed_on=case.as_of,
            rationale="Reviewed only the time-only report; the additional exercise candidate has not yet been inspected.",
        )


def test_same_row_keeps_confirmed_failure_first_and_independent_missing_fact_request():
    case, item = rto_only(), need()
    report = replace(case.documents[0], content=b"SYNTHETIC witnessed full-service recovery exercise: achieved RTO was 480 minutes.")
    case = replace(case, documents=(report,), proposals=(proposal(report, "achieved_rto_minutes", 1, 480),))
    state = confirm(case, adverse=True)
    review = explicit_need_review(case, mapping(case, (item,)), item, state, "insufficient")
    result = build(case, (item,), state=state, reviews=(review,))
    assert result.rows[0].priority == 0 and result.rows[0].outcome == "Risk Identified"
    assert result.rows[0].intent == "Review exception"
    assert result.rows[0].request_ids == (result.requests[0].request_id,)
    assert result.requests[0].question == item.question
    assert matches(result)[item.need_id].status == MISSING


@pytest.mark.parametrize("change", ["confirmation", "source", "fact"])
def test_replayed_modified_need_records_are_revalidated_during_inspection(change):
    case, item = rto_only(), need("achieved_rto_minutes")
    state = confirm(case)
    review = explicit_need_review(case, mapping(case, (item,)), item, state, "supported")
    attributes = {"confirmation": {"confirms": False}, "source": {"source_fingerprints": ("other-source",)},
                  "fact": {"fact_fingerprints": ("invented-fact",)}}[change]
    replay = replace(review, **attributes)
    result = build(case, (item,), state=state, reviews=(replay,))
    assert matches(result)[item.need_id].status == VALIDATE
    assert result.rows[0].outcome != "Met" and not result.requests
