"""Unsupported domains stay in review; no claims of generic technical assurance."""
import ast
from dataclasses import replace
from datetime import date
from pathlib import Path
import re

import pytest

from src.control_assurance import (
    Check, ControlCase, ControlReviewState, CustomerThreshold, DomainEvaluator,
    EvidenceExpectation, RequirementContext, TechnicalResult, bind_relevance,
    inspect_control, record_control_review,
)
from src.control_assurance_pilot import (
    document, fallback_pilot_cases, proposal,
)
from src.control_assurance_presentation import present_control
from src.control_assurance_registry import ReviewFamily, registered_review_families
from src.evidence_source_validation import bind_evidence


AS_OF = date(2026, 10, 21)


def arbitrary_case(*, adverse=False):
    """An unrelated customer requirement needs no technical callback or enum."""
    scope = "all production processing activities and retention stores"
    requirement = RequirementContext(
        "customer-retention-42", "customer-retention-policy", "2026.1",
        "Synthetic customer policy owner", date(2026, 10, 1),
        "Acme Analytics", "production", scope, 90, "",
        business_use_case="Keep processing records only for the agreed business period",
        required_evidence=("Current retention inventory and executed deletion records",),
        assurance_type="Implemented retention and operating deletion proof",
        evidence_expectation=EvidenceExpectation("2026.1", ("configuration", "test", "assertion")),
    )
    policy = document("retention-policy", "SYNTHETIC customer policy: delete customer records within 30 days of the approved retention deadline.",
                      scope, kind="policy")
    inventory = document("retention-inventory", "SYNTHETIC inventory export: the vendor reports deletion after 28 days for the complete production store inventory.",
                         scope, kind="configuration")
    p = proposal(inventory, "reported_deletion_days", 1, 28)
    threshold = CustomerThreshold("Delete customer records within 30 days of the approved retention deadline.")
    relevance = (bind_relevance(requirement, threshold, inventory,
                               rationale="The inventory reports deletion timing for the customer records governed by this retention requirement."),)
    docs, ps = (policy, inventory), (p,)
    if adverse:
        exception = document("retention-exception", "SYNTHETIC vendor response: an exception leaves archived customer records overdue and excluded from deletion.",
                             scope, kind="assertion")
        ep = replace(proposal(exception, "archived_records_retained", 1, True), concern="potential_exception")
        docs, ps = docs + (exception,), ps + (ep,)
        relevance += (bind_relevance(requirement, threshold, exception,
                                     rationale="The response reports an archived-record exception to the same customer deletion criterion."),)
    return ControlCase(
        case_id="customer-retention-case", title="Unrelated retention requirement",
        family="Customer-defined retention", requirement=requirement,
        threshold=threshold, documents=docs, proposals=ps, as_of=AS_OF, relevance=relevance,
    )


def act(case, state, action, **kwargs):
    return record_control_review(
        case, state, action=action, expected_bundle=inspect_control(case).bundle_fingerprint,
        analyst="Synthetic specialist reviewer", reviewed_on=case.as_of,
        rationale="Checked the cited interpretation and complete synthetic context; technical sufficiency remains unassessed.",
        **kwargs,
    )


def confirm_one(case, state, row, *, action="meaning"):
    return act(case, state, action, fact_ids=(row.proposal.fact_id,),
               presented_fingerprints=(row.fingerprint,), confirms=True)


def reviewed(case, *, dismiss_signals=True):
    """Explicit test actions cannot manufacture a missing specialist evaluator."""
    state = ControlReviewState()
    view = inspect_control(case)
    for row in view.facts:
        if not row.reasons and row.direction in {"review", "adverse"}:
            state = confirm_one(case, state, row,
                                action="exception" if row.direction == "adverse" else "meaning")
    for signal in view.signals:
        state = act(case, state, "signal", signal_id=signal.signal_id,
                    material=not dismiss_signals)
    return act(case, state, "bundle", confirms=True)


def test_an_arbitrary_customer_requirement_exists_independently_of_evaluator():
    case = arbitrary_case()
    assert case.evaluator is None
    view = inspect_control(case)
    assert view.requirement == case.requirement
    assert case.threshold.acceptance_criteria in view.threshold_summary
    assert view.outcome == "Needs Review" and not view.specialist_available
    assert view.provisional and view.review_required
    assert any("specialist" in text.casefold() for text in view.limitations)
    assert view.next_action
    assert len(view.evidence) == 2 and len(view.facts) == 1
    row = view.facts[0]
    assert row.direction == "review" and not row.confirmed
    assert row.proposal.quote in case.documents[1].content.decode()
    assert row.proposal.location == "Line 1"
    assert row.proposal.source_fingerprint == bind_evidence(case.documents[1]).fingerprint


def test_fourth_unrelated_pilot_requirement_has_present_and_missing_packages():
    cases = {case.case_id: case for case in fallback_pilot_cases()}
    assert {"vm-present", "vm-missing"} <= cases.keys()
    present, missing = cases["vm-present"], cases["vm-missing"]
    assert present.requirement.requirement_id == missing.requirement.requirement_id
    assert present.evaluator is None and missing.evaluator is None
    assert inspect_control(present).outcome == "Needs Review"
    assert inspect_control(missing).outcome == "Evidence Missing"
    assert inspect_control(present, reviewed(present)).outcome == "Needs Review"
    assert inspect_control(missing, reviewed(missing)).outcome == "Evidence Missing"
    assert present.proposals and any(p.quote for p in present.proposals)


def test_fallback_semantics_confirmation_is_explicit_individual_and_never_technical_approval():
    case = arbitrary_case()
    initial = inspect_control(case)
    row = initial.facts[0]
    assert not any(f.confirmed for f in initial.facts)
    with pytest.raises(ValueError):
        act(case, ControlReviewState(), "meaning", fact_ids=(row.proposal.fact_id,),
            presented_fingerprints=(row.fingerprint,), confirms=False)
    with pytest.raises(ValueError):
        confirm_one(case, ControlReviewState(), row, action="support")
    state = confirm_one(case, ControlReviewState(), row)
    assert len(state.fact_reviews) == 1 and len(state.events) == 1
    assert state.events[0].kind == "meaning"
    assert not state.bundle_review
    view = inspect_control(case, state)
    assert view.facts[0].confirmed and view.outcome == "Needs Review"
    state = act(case, state, "bundle", confirms=True)
    final = inspect_control(case, state)
    assert final.bundle_review_valid and final.outcome == "Needs Review"
    assert not final.specialist_available
    assert any("specialist" in text.casefold() for text in final.limitations)


@pytest.mark.parametrize("claimed_value", [True, False, 1, 100000, "fully compliant", None])
def test_generic_claim_values_are_never_interpreted_as_threshold_pass_or_failure(claimed_value):
    base = arbitrary_case()
    case = replace(base, proposals=(replace(base.proposals[0], value=claimed_value),))
    view = inspect_control(case)
    assert view.facts[0].direction == "review"
    assert view.outcome == "Needs Review"
    final = inspect_control(case, reviewed(case))
    assert final.outcome == "Needs Review"
    assert not any(c.status in {"supported", "failed"} for c in final.checks)


@pytest.mark.parametrize("change", ["none", "policy_only", "stale", "scope", "origin", "future"])
def test_no_usable_evidence_is_missing_and_never_silent_pass_or_failure(change):
    base = arbitrary_case()
    doc = base.documents[1]
    if change == "none":
        case = replace(base, documents=(), proposals=())
    elif change == "policy_only":
        doc = replace(doc, evidence_kind="policy")
        p = replace(base.proposals[0], source_fingerprint=bind_evidence(doc).fingerprint)
        case = replace(base, documents=(base.documents[0], doc), proposals=(p,))
    else:
        attrs = {
            "stale": {"observed_on": date(2025, 1, 1)},
            "scope": {"service": "Unrelated synthetic service"},
            "origin": {"origin": None},
            "future": {"observed_on": date(2026, 10, 22)},
        }[change]
        doc = replace(doc, **attrs)
        p = replace(base.proposals[0], source_fingerprint=bind_evidence(doc).fingerprint)
        case = replace(base, documents=(base.documents[0], doc), proposals=(p,))
    for state in (ControlReviewState(), reviewed(case)):
        view = inspect_control(case, state)
        assert view.outcome == "Evidence Missing"
        assert not view.specialist_available and view.review_required
        assert any("specialist" in text.casefold() for text in view.limitations)
        assert view.next_action
        assert len(view.evidence) == len(case.documents)


@pytest.mark.parametrize("attribute,value", [
    ("source_id", "missing:1"), ("source_fingerprint", "incorrect"),
    ("location", "Page 999"), ("quote", "An invented quotation"),
])
def test_broken_fallback_citations_remain_visible_and_challengeable(attribute, value):
    base = arbitrary_case()
    p = replace(base.proposals[0], **{attribute: value})
    case = replace(base, proposals=(p,))
    view = inspect_control(case)
    row = view.facts[0]
    assert row.reasons and not row.confirmed
    assert view.outcome not in {"Met", "Risk Identified"}
    with pytest.raises(ValueError):
        confirm_one(case, ControlReviewState(), row)
    state = act(case, ControlReviewState(), "challenge", fact_ids=(p.fact_id,),
                presented_fingerprints=(row.fingerprint,), decision="unsupported")
    assert state.events[-1].kind == "challenge_unsupported"
    assert inspect_control(case, state).evidence == view.evidence


@pytest.mark.parametrize("dismiss_signals", [False, True])
def test_adverse_claim_survives_meaning_review_and_signal_triage_without_becoming_verified_failure(dismiss_signals):
    case = arbitrary_case(adverse=True)
    initial = inspect_control(case)
    row = next(f for f in initial.facts if f.direction == "adverse")
    assert initial.signals
    with pytest.raises(ValueError):
        confirm_one(case, ControlReviewState(), row)
    state = reviewed(case, dismiss_signals=dismiss_signals)
    final = inspect_control(case, state)
    assert final.outcome == "Needs Review" and final.bundle_review_valid
    assert any(f.proposal.fact_id == row.proposal.fact_id for f in final.facts)
    assert all(f.confirmed for f in final.facts)
    assert not any(c.status == "failed" for c in final.checks)
    presentation = present_control(case, final)
    assert any(row.proposal.quote == citation.quote
               for attention in presentation.attention for citation in attention.citations)
    assert any("exception" in attention.title.casefold() for attention in presentation.attention)


def test_fallback_challenge_preserves_citations_history_and_other_reviews():
    case = arbitrary_case(adverse=True)
    state = reviewed(case)
    before = inspect_control(case, state)
    row = before.facts[0]
    count = len(state.events)
    state = act(case, state, "challenge", fact_ids=(row.proposal.fact_id,),
                presented_fingerprints=(row.fingerprint,), decision="ambiguous")
    final = inspect_control(case, state)
    assert final.outcome == "Needs Review" and not final.bundle_review_valid
    assert not final.facts[0].confirmed and final.facts[1].confirmed
    assert final.evidence == before.evidence
    assert len(state.events) == count + 1
    assert state.events[0].kind == "meaning" and state.events[-1].kind == "challenge_ambiguous"
    assert final.facts[0].proposal.quote == row.proposal.quote


def test_declared_conflict_remains_visible_without_matching_lexical_signals():
    base = arbitrary_case()
    # A supplied interpretation can carry concern without a known scanner word.
    p = replace(base.proposals[0], concern="conflict")
    case = replace(base, proposals=(p,))
    initial = inspect_control(case)
    assert not initial.signals and initial.facts[0].direction == "adverse"
    result = inspect_control(case, reviewed(case))
    presentation = present_control(case, result)
    assert result.outcome == "Needs Review"
    assert any("conflicting" in item.title and any(c.quote == p.quote for c in item.citations)
               for item in presentation.attention)


@pytest.mark.parametrize("mutation", ["policy", "threshold", "date", "source", "scope", "standard", "assurance_type"])
def test_fallback_review_binding_invalidates_for_material_requirement_and_source_changes(mutation):
    case = arbitrary_case()
    state = reviewed(case)
    if mutation == "policy":
        changed = replace(case, requirement=replace(case.requirement, policy_version="2026.2"))
    elif mutation == "threshold":
        changed = replace(case, threshold=CustomerThreshold("Delete within 7 days of the retention deadline."))
    elif mutation == "date":
        changed = replace(case, as_of=date(2026, 10, 22))
    elif mutation == "source":
        d = replace(case.documents[1], content=case.documents[1].content + b" Additional synthetic source context.")
        changed = replace(case, documents=(case.documents[0], d))
    else:
        attrs = {"scope": {"scope": "a different processing population"},
                 "standard": {"standard_reference": "Customer-supplied mapping", "standard_edition": "2026"},
                 "assurance_type": {"assurance_type": "Different required operating evidence"}}[mutation]
        changed = replace(case, requirement=replace(case.requirement, **attrs))
    result = inspect_control(changed, state)
    assert result.bundle_fingerprint != state.bundle_fingerprint
    assert not result.bundle_review_valid and not any(f.confirmed for f in result.facts)
    assert result.outcome in {"Needs Review", "Evidence Missing"}
    with pytest.raises(ValueError, match="bundle changed"):
        record_control_review(changed, state, action="bundle", expected_bundle=state.bundle_fingerprint,
                              analyst="Reviewer", reviewed_on=changed.as_of, rationale="old review", confirms=True)


def test_new_domain_evaluator_is_a_typed_extension_without_changing_review_contract():
    """A test-only retention rule proves attachment, not production coverage."""
    case = arbitrary_case()
    assert inspect_control(case, reviewed(case)).outcome == "Needs Review"

    def direction(threshold, fact, source):
        return "support" if fact.dimension == "reported_deletion_days" and type(fact.value) is int else "unknown"

    def evaluate(threshold, observations, as_of):
        supported = any(f.dimension == "reported_deletion_days" for f, _ in observations)
        return TechnicalResult("Met" if supported else "Evidence Missing",
                               (Check("test-only-retention-rule", "supported" if supported else "missing",
                                      "Synthetic typed extension exercised."),),
                               "Seek independent governed review of the synthetic extension.")

    evaluator = DomainEvaluator("TEST-ONLY-RETENTION-1.0", evaluate, direction, re.compile(r"\bexception\b", re.I))
    extended = replace(case, evaluator=evaluator)
    initial = inspect_control(extended, reviewed(case))
    assert initial.specialist_available and initial.outcome != "Met"
    assert not initial.bundle_review_valid and not any(f.confirmed for f in initial.facts)
    row = initial.facts[0]
    state = confirm_one(extended, ControlReviewState(), row, action="support")
    state = act(extended, state, "bundle", confirms=True)
    view = inspect_control(extended, state)
    assert view.specialist_available and view.outcome == "Met"
    assert view.provisional and view.review_required
    assert present_control(extended, view).requirement_id == case.requirement.requirement_id


def test_registered_arbitrary_family_retains_every_applicable_case():
    first = arbitrary_case()
    missing = replace(first, case_id="retention-without-evidence", documents=(), proposals=())
    unrelated = fallback_pilot_cases()
    registrations = registered_review_families(unrelated + (first, missing))
    family = registrations[first.family]
    assert family.name == first.family and family.renderer is None
    assert family.cases == (first, missing)
    assert sum(len(registration.cases) for registration in registrations.values()) == len(unrelated) + 2
    assert inspect_control(family.cases[0]).outcome == "Needs Review"
    assert inspect_control(family.cases[1]).outcome == "Evidence Missing"


def test_duplicate_adapter_names_raise_instead_of_replacing_applicable_cases():
    first = arbitrary_case()
    second = replace(first, case_id="different-applicable-requirement")
    adapters = (ReviewFamily("Legacy compatible family", (first,)),
                ReviewFamily("Legacy compatible family", (second,)))
    with pytest.raises(ValueError, match="Duplicate review adapters"):
        registered_review_families((), adapters=adapters)


def test_adapter_and_common_cases_cannot_silently_hide_each_other():
    common = arbitrary_case()
    adapted = replace(common, case_id="legacy-adapted-requirement")
    adapter = ReviewFamily(common.family, (adapted,))
    with pytest.raises(ValueError, match="cannot mix"):
        registered_review_families((common,), adapters=(adapter,))


def test_common_ui_family_selection_is_registration_driven_without_domain_label_branch():
    tree = ast.parse(Path("src/control_assurance_ui.py").read_text())
    selector = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "selectbox" and node.args
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value == "Control family")
    assert not isinstance(selector.args[1], (ast.Tuple, ast.List, ast.Set))
    assert any(isinstance(node, ast.Name) and node.id == "registrations" for node in ast.walk(selector.args[1]))
    for comparison in (node for node in ast.walk(tree) if isinstance(node, ast.Compare)):
        values = (comparison.left, *comparison.comparators)
        assert not (any(isinstance(value, ast.Name) and value.id == "family" for value in values)
                    and any(isinstance(value, ast.Constant) and isinstance(value.value, str) for value in values))
