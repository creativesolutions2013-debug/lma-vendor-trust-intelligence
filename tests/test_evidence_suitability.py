"""Requirement-specific review eligibility is metadata, never control assurance."""
from dataclasses import replace
from datetime import date

import pytest

from src.control_assurance import (
    ControlCase, ControlReviewState, CustomerThreshold, EvidenceExpectation,
    RequirementContext, bind_relevance, inspect_control, record_control_review,
)
from src.control_assurance_pilot import document, proposal, suitability_pilot_cases
from src.control_assurance_presentation import present_control
from src.evidence_source_validation import bind_evidence


AS_OF = date(2026, 10, 21)


def policy_case():
    scope = "the assessed production service and every supporting production team"
    requirement = RequirementContext(
        "GOV-SYNTH-42", "synthetic-security-governance", "2026.1",
        "Synthetic customer policy owner", date(2026, 10, 1),
        "Acme Analytics", "production", scope, 90,
        required_evidence=("current approved security policy covering the assessed service",),
        assurance_type="Documented governance, not operating effectiveness",
        evidence_expectation=EvidenceExpectation("2026.1", ("policy",)),
    )
    threshold = CustomerThreshold("Maintain a current approved security policy covering the assessed service.")
    source = document("approved-security-policy", (
        "SYNTHETIC approved information-security policy 2026.1 covers Acme Analytics production and all supporting teams; "
        "the policy owner approved this current edition on 2026-10-01."
    ), scope, kind="policy")
    p = proposal(source, "documented_security_policy", 1, True)
    relevance = bind_relevance(requirement, threshold, source,
                               rationale="The supplied policy addresses the documented governance requirement and assessed service.")
    return ControlCase("policy-documentation", "Current documented security governance", "Customer governance",
                       requirement, threshold, (source,), (p,), AS_OF, relevance=(relevance,))


def act(case, state, action, **kwargs):
    return record_control_review(
        case, state, action=action, expected_bundle=inspect_control(case).bundle_fingerprint,
        analyst="Synthetic suitability reviewer", reviewed_on=case.as_of,
        rationale="Checked the declared expectation, source relevance and exact source; specialist judgment is still required.",
        **kwargs,
    )


def reviewed(case):
    state = ControlReviewState()
    view = inspect_control(case)
    for row in view.facts:
        if not row.reasons and row.direction in {"review", "adverse"}:
            state = act(case, state, "exception" if row.direction == "adverse" else "meaning",
                        fact_ids=(row.proposal.fact_id,), presented_fingerprints=(row.fingerprint,), confirms=True)
    for signal in view.signals:
        state = act(case, state, "signal", signal_id=signal.signal_id, material=False)
    return act(case, state, "bundle", confirms=True)


def test_current_policy_is_pertinent_to_documented_governance_but_never_approval():
    case = policy_case()
    view = inspect_control(case)
    assert view.outcome == "Needs Review" and not view.specialist_available
    assert view.eligible_source_fingerprints == (bind_evidence(case.documents[0]).fingerprint,)
    assert view.facts[0].proposal.quote == case.proposals[0].quote
    assert view.facts[0].proposal.location == "Line 1"
    assert not view.facts[0].confirmed
    assert view.evidence[0].document.segments[0].text == case.proposals[0].quote
    presentation = present_control(case, view)
    assert not presentation.supporting
    assert any(c.quote == case.proposals[0].quote and c.location == "Line 1"
               for c in presentation.evidence_for_review)
    final = inspect_control(case, reviewed(case))
    assert final.outcome == "Needs Review" and final.bundle_review_valid
    assert final.facts[0].confirmed and final.provisional and final.review_required
    assert any("specialist" in x.casefold() for x in final.limitations)
    assert not any(check.status in {"supported", "failed"} for check in final.checks)


@pytest.mark.parametrize("case_id,outcome", [
    ("gov-policy", "Needs Review"), ("gov-missing", "Evidence Missing"),
    ("vm-policy-only", "Evidence Missing"), ("vm-unrelated", "Evidence Missing"),
])
def test_targeted_synthetic_suitability_scenarios(case_id, outcome):
    case = next(c for c in suitability_pilot_cases() if c.case_id == case_id)
    assert case.evaluator is None
    for state in (ControlReviewState(), reviewed(case)):
        view = inspect_control(case, state)
        assert view.outcome == outcome
        assert len(view.evidence) == len(case.documents)
        assert any("specialist" in x.casefold() for x in view.limitations)
        assert view.next_action
        assert bool(view.eligible_source_fingerprints) == (case_id == "gov-policy")


def test_operational_requirement_rejects_policy_even_with_explicit_relevance():
    base = policy_case()
    requirement = replace(base.requirement, assurance_type="Operating control effectiveness",
                          evidence_expectation=EvidenceExpectation("2026.2", ("configuration", "test")))
    threshold = CustomerThreshold("Demonstrate the control operated throughout the assessed period.")
    relevance = bind_relevance(requirement, threshold, base.documents[0],
                               rationale="The policy describes design and intent relevant to this control; it is not operating proof.")
    case = replace(base, requirement=requirement, threshold=threshold, relevance=(relevance,))
    final = inspect_control(case, reviewed(case))
    assert final.outcome == "Evidence Missing" and not final.eligible_source_fingerprints
    assert final.evidence[0].document.segments[0].text == case.proposals[0].quote
    assert final.facts[0].confirmed  # Meaning review cannot upgrade policy to operation.
    assert not any(c.status == "failed" for c in final.checks)


def test_current_configuration_kind_and_scope_do_not_establish_requirement_relevance():
    base = policy_case()
    source = document("unrelated-time-service-config", "SYNTHETIC configuration: production clocks use the approved network time service.",
                      base.requirement.scope, kind="configuration")
    requirement = replace(base.requirement, evidence_expectation=EvidenceExpectation("2026.1", ("configuration",)))
    case = replace(base, requirement=requirement, documents=(source,),
                   proposals=(proposal(source, "time_service_configured", 1, True),), relevance=())
    final = inspect_control(case, reviewed(case))
    assert final.outcome == "Evidence Missing" and not final.eligible_source_fingerprints
    assert any("relevan" in x.casefold() for x in final.limitations)
    assert final.evidence[0].source == source and final.facts[0].confirmed


@pytest.mark.parametrize("missing", ["expectation", "binding"])
def test_absence_of_explicit_suitability_metadata_is_a_visible_gap(missing):
    case = policy_case()
    if missing == "expectation":
        case = replace(case, requirement=replace(case.requirement, evidence_expectation=None))
    else:
        case = replace(case, relevance=())
    view = inspect_control(case, reviewed(case))
    assert view.outcome == "Evidence Missing" and not view.eligible_source_fingerprints
    assert view.limitations and view.evidence


@pytest.mark.parametrize("change", ["stale", "scope", "origin", "future"])
def test_explicit_relevance_cannot_override_source_quality_and_context(change):
    base = policy_case()
    attrs = {"stale": {"observed_on": date(2020, 1, 1)},
             "scope": {"service": "Another synthetic service"},
             "origin": {"origin": None},
             "future": {"observed_on": date(2026, 10, 22)}}[change]
    source = replace(base.documents[0], **attrs)
    p = replace(base.proposals[0], source_fingerprint=bind_evidence(source).fingerprint)
    relevance = bind_relevance(base.requirement, base.threshold, source,
                               rationale="Explicit supplied mapping cannot repair inventory limitations.")
    case = replace(base, documents=(source,), proposals=(p,), relevance=(relevance,))
    view = inspect_control(case, reviewed(case))
    assert view.outcome == "Evidence Missing" and not view.eligible_source_fingerprints
    assert view.evidence[0].source == source


@pytest.mark.parametrize("problem", ["duplicate", "stale_requirement", "wrong_source", "empty_rationale"])
def test_ambiguous_stale_or_incomplete_relevance_cannot_establish_eligibility(problem):
    base = policy_case()
    relevance = base.relevance[0]
    if problem == "duplicate":
        bindings = (relevance, replace(relevance, rationale="Another supplied account of relevance."))
    elif problem == "stale_requirement":
        bindings = (replace(relevance, requirement_fingerprint="old-requirement"),)
    elif problem == "wrong_source":
        bindings = (replace(relevance, source_fingerprint="unrelated-source"),)
    else:
        bindings = (replace(relevance, rationale=""),)
    case = replace(base, relevance=bindings)
    view = inspect_control(case, reviewed(case))
    assert view.outcome == "Evidence Missing" and not view.eligible_source_fingerprints
    assert any("relevan" in x.casefold() for x in view.limitations)


def test_exact_matching_quote_and_confirmed_meaning_do_not_create_relevance():
    base = policy_case()
    case = replace(base, relevance=())
    state = reviewed(case)
    view = inspect_control(case, state)
    assert view.facts[0].confirmed and view.bundle_review_valid
    assert view.facts[0].proposal.quote in view.evidence[0].document.segments[0].text
    assert view.outcome == "Evidence Missing" and not view.eligible_source_fingerprints


@pytest.mark.parametrize("version,kinds", [("", ("policy",)), ("2026.1", ()),
                                            ("2026.1", ("unknown",)), ("2026.1", ("policy", "policy"))])
def test_evidence_expectations_are_explicit_versioned_known_kinds(version, kinds):
    with pytest.raises(ValueError):
        EvidenceExpectation(version, kinds)


@pytest.mark.parametrize("change", ["policy", "threshold", "expectation_version", "accepted_kinds", "relevance", "source", "date"])
def test_suitability_changes_invalidate_all_active_review(change):
    case = policy_case()
    state = reviewed(case)
    assert inspect_control(case, state).bundle_review_valid
    if change == "policy":
        changed = replace(case, requirement=replace(case.requirement, policy_version="2026.2"))
    elif change == "threshold":
        changed = replace(case, threshold=CustomerThreshold("Require policy approval and quarterly review by the customer owner."))
    elif change == "expectation_version":
        changed = replace(case, requirement=replace(case.requirement,
                          evidence_expectation=EvidenceExpectation("2026.2", ("policy",))))
    elif change == "accepted_kinds":
        changed = replace(case, requirement=replace(case.requirement,
                          evidence_expectation=EvidenceExpectation("2026.1", ("policy", "assertion"))))
    elif change == "relevance":
        changed = replace(case, relevance=(replace(case.relevance[0], rationale="Corrected source-to-requirement explanation."),))
    elif change == "date":
        changed = replace(case, as_of=date(2026, 10, 22))
    else:
        changed = replace(case, documents=(replace(case.documents[0], content=case.documents[0].content + b" Additional synthetic context."),))
    view = inspect_control(changed, state)
    assert view.bundle_fingerprint != state.bundle_fingerprint
    assert not view.bundle_review_valid and not any(row.confirmed for row in view.facts)
    assert view.outcome in {"Evidence Missing", "Needs Review"}
    with pytest.raises(ValueError, match="bundle changed"):
        record_control_review(changed, state, action="bundle", expected_bundle=state.bundle_fingerprint,
                              analyst="Reviewer", reviewed_on=changed.as_of, rationale="Old review", confirms=True)


def test_adding_relevance_requires_fresh_review_and_preserves_prior_event_history():
    base = policy_case()
    unbound = replace(base, relevance=())
    old = reviewed(unbound)
    assert inspect_control(unbound, old).outcome == "Evidence Missing"
    initial = inspect_control(base, old)
    assert initial.outcome == "Needs Review" and not initial.bundle_review_valid
    assert not initial.facts[0].confirmed
    row = initial.facts[0]
    new = act(base, old, "meaning", fact_ids=(row.proposal.fact_id,),
              presented_fingerprints=(row.fingerprint,), confirms=True)
    assert len(new.events) == len(old.events) + 1
    assert new.events[:len(old.events)] == old.events
    assert not new.bundle_review
    assert inspect_control(base, new).outcome == "Needs Review"
