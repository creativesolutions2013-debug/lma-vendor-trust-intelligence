"""M3C-1 grouped human review regressions; no AI or confidential evidence.

Action counts are explicit decision submissions against a modeled M3B per-fact
baseline, not observed analyst time or an accuracy benchmark.
"""
from dataclasses import replace
from datetime import timedelta
import json

import pytest

from src.evidence_fact_validation import FactReview, ProposedFact, SignalDisposition, bind_evidence, fact_fingerprint
from src.evidence_intelligence_m3 import Citation
from src.mfa_analyst_review import (
    ReviewEvent, ReviewState, acknowledge_bundle, challenge_supporting, confirm_exception, confirm_supporting,
    inspect_review, triage_signal,
)
from src.mfa_review_pilot import pilot_cases


@pytest.fixture
def cases():
    return {case.case_id: case for case in pilot_cases()}


def actor(case, **changes):
    fields = dict(analyst="Synthetic pilot analyst", reviewed_on=case.as_of,
                  rationale="I checked the presented interpretations against the full synthetic source context.")
    fields.update(changes)
    return fields


def group(case, state=None, **changes):
    state = state or ReviewState()
    view = inspect_review(case, state)
    fields = dict(expected_bundle=view.bundle_fingerprint,
                  presented_fingerprints=view.supporting_fingerprints,
                  confirms_semantics=True, **actor(case))
    fields.update(changes)
    return confirm_supporting(case, state, **fields)


def ack(case, state, **changes):
    fields = dict(expected_bundle=inspect_review(case, state).bundle_fingerprint,
                  confirms_complete_bundle=True, **actor(case))
    fields.update(changes)
    return acknowledge_bundle(case, state, **fields)


def negative_proposals(case):
    return tuple(item for item in case.proposals if item.fact.value is False)


def triage(case, state, signal, material):
    return triage_signal(
        case, state, expected_bundle=inspect_review(case, state).bundle_fingerprint,
        signal_id=signal.signal_id, material=material,
        **actor(case, rationale=(
            "The cited source explicitly describes an active administrator exception requiring investigation."
            if material else
            "I checked this whole source; this marker occurs in an explicit statement of no exemptions or exceptions."
        )),
    )


def complete_known_case(case):
    """Explicit synthetic analyst oracle for strong, bypass and vendor-report cases."""
    state = ReviewState()
    if inspect_review(case).supporting_fingerprints:
        state = group(case, state)
    negative_source_ids = {item.fact.citation.source_id for item in negative_proposals(case)}
    for item in negative_proposals(case):
        state = confirm_exception(
            case, state, expected_bundle=inspect_review(case, state).bundle_fingerprint,
            fact_id=item.fact_id, confirms_semantics=True, **actor(case),
        )
    # Locations anchoring explicit negative proposals are independently known
    # material in these hand-authored cases; negated inventory statements are not.
    for signal in inspect_review(case, state).validation.signals:
        material = signal.source_id in negative_source_ids
        state = triage(case, state, signal, material)
    return ack(case, state)


def test_inspection_is_read_only_and_never_synthesizes_analyst_reviews(cases):
    case = cases["strong"]
    state = ReviewState()
    view = inspect_review(case, state)
    assert state == ReviewState()
    assert not view.validation.evaluation.facts
    assert not view.validation.bundle_review_valid
    assert view.validation.evaluation.outcome == "Needs Review"
    assert len(view.supporting) == len(view.supporting_fingerprints) == 7
    assert not any(item.confirmed for item in view.supporting)
    assert view.validation.provisional and view.validation.review_required
    assert view.next_action


def test_group_action_confirms_each_presented_fact_without_triaging_exceptions_or_bundle(cases):
    case = cases["strong"]
    before = inspect_review(case)
    state = group(case)
    assert len(state.fact_reviews) == 7
    assert {review.fact_fingerprint for review in state.fact_reviews} == set(before.supporting_fingerprints)
    assert all(review.decision == "supported" for review in state.fact_reviews)
    assert not state.signal_dispositions and state.bundle_review is None
    assert len(state.events) == 1
    assert set(state.events[0].fact_fingerprints) == set(before.supporting_fingerprints)
    assert dict(zip(state.events[0].target_ids, state.events[0].fact_fingerprints)) == {
        proposal.fact_id: fact_fingerprint(proposal) for proposal in case.proposals
    }
    assert state.events[0].analyst == "Synthetic pilot analyst"
    view = inspect_review(case, state)
    assert all(item.confirmed for item in view.supporting)
    assert view.validation.evaluation.outcome == "Needs Review"
    assert not view.validation.bundle_review_valid
    assert all(signal.status == "needs_review" for signal in view.validation.signals)


def test_positive_case_requires_separate_signal_triage_and_complete_bundle_acknowledgment(cases):
    case = cases["strong"]
    state = group(case)
    for signal in inspect_review(case, state).validation.signals:
        state = triage(case, state, signal, False)
    assert state.bundle_review is None
    assert inspect_review(case, state).validation.evaluation.outcome == "Needs Review"
    state = ack(case, state)
    result = inspect_review(case, state).validation
    assert result.evaluation.outcome == "Met"
    assert result.bundle_review_valid
    assert all(item.status == "validated" for item in result.facts)
    assert result.provisional and result.review_required
    assert result.evaluation.provisional and result.evaluation.review_required


@pytest.mark.parametrize("presented", ["missing", "extra", "duplicate", "altered"])
def test_group_action_rejects_partial_extra_duplicate_or_altered_presented_set(cases, presented):
    case = cases["strong"]
    fingerprints = inspect_review(case).supporting_fingerprints
    changes = {
        "missing": fingerprints[:-1],
        "extra": fingerprints + ("f" * 64,),
        "duplicate": fingerprints + (fingerprints[0],),
        "altered": ("0" * 64,) + fingerprints[1:],
    }
    with pytest.raises(ValueError):
        group(case, presented_fingerprints=changes[presented])


@pytest.mark.parametrize("changes", [
    {"confirms_semantics": False}, {"confirms_semantics": "yes"},
    {"expected_bundle": "0" * 64}, {"analyst": ""}, {"rationale": " "},
])
def test_group_action_requires_explicit_current_semantic_confirmation_and_reviewer(cases, changes):
    with pytest.raises(ValueError):
        group(cases["strong"], **changes)


def test_group_review_date_cannot_be_future_or_predate_the_sources(cases):
    case = cases["strong"]
    for reviewed_on in (case.as_of + timedelta(days=1), min(item.captured_on for item in case.documents) - timedelta(days=1)):
        with pytest.raises(ValueError):
            group(case, reviewed_on=reviewed_on)


def test_group_confirmation_cannot_be_replayed_as_another_decision(cases):
    case = cases["strong"]
    state = group(case)
    with pytest.raises(ValueError):
        group(case, state)
    assert len(state.fact_reviews) == 7 and len(state.events) == 1


@pytest.mark.parametrize("classification,kind", [
    ("explicit_exception", "potential_exception"), ("conflicting_statement", "conflict"),
])
def test_positive_valued_reviewed_exception_or_conflict_is_retained_outside_supporting_group(cases, classification, kind):
    case = cases["strong"]
    proposal = case.proposals[0]
    fingerprint = fact_fingerprint(proposal)
    review = FactReview(fingerprint, "supported", classification, "Synthetic pilot analyst", case.as_of,
                        "The positive source account has a separately identified exception or disagreement.")
    state = ReviewState(fact_reviews=(review,), bundle_fingerprint=inspect_review(case).bundle_fingerprint)
    view = inspect_review(case, state)
    assert fingerprint not in view.supporting_fingerprints
    assert any(issue.kind == kind and proposal.fact_id in issue.fact_ids for issue in view.issues)
    # Even all remaining explicit reviews, signal decisions and bundle review
    # cannot turn a retained analyst-identified exception into positive assurance.
    state = group(case, state)
    for signal in inspect_review(case, state).validation.signals:
        state = triage(case, state, signal, False)
    state = ack(case, state)
    view = inspect_review(case, state)
    assert view.validation.bundle_review_valid
    assert view.validation.evaluation.outcome == "Needs Review"
    assert any(issue.kind == kind and proposal.fact_id in issue.fact_ids for issue in view.issues)


@pytest.mark.parametrize("change", ["source", "fact", "policy", "date"])
def test_old_review_state_cannot_survive_source_fact_policy_or_evaluation_date_changes(cases, change):
    case = cases["strong"]
    state = complete_known_case(case)
    assert inspect_review(case, state).validation.evaluation.outcome == "Met"
    if change == "source":
        changed = replace(case, documents=(replace(case.documents[0], version="synthetic-v2"),) + case.documents[1:])
    elif change == "fact":
        method = next(item for item in case.proposals if item.fact.dimension == "method")
        changed = replace(case, proposals=tuple(
            replace(item, fact=replace(item.fact, verifier_bound=False)) if item.fact_id == method.fact_id else item
            for item in case.proposals))
    elif change == "policy":
        changed = replace(case, requirement=replace(case.requirement, version="2"))
    else:
        changed = replace(case, as_of=case.as_of + timedelta(days=1))
    view = inspect_review(changed, state)
    assert view.validation.evaluation.outcome != "Met"
    assert not view.validation.bundle_review_valid
    assert not view.validation.evaluation.facts
    assert any(issue.kind == "review_changed" for issue in view.issues)
    with pytest.raises(ValueError):
        ack(changed, state)


@pytest.mark.parametrize("case_id,kind", [
    ("bypass", "potential_exception"), ("reported", "vendor_reported_exception"),
    ("conflict", "conflict"), ("stale", "stale_evidence"),
    ("coverage_gap", "scope_gap"), ("scope_mismatch", "scope_gap"),
    ("unknown", "incomplete_evidence"),
])
def test_exception_first_view_distinguishes_failure_uncertainty_currency_and_scope(cases, case_id, kind):
    view = inspect_review(cases[case_id])
    assert any(issue.kind == kind for issue in view.issues)
    assert view.validation.evaluation.outcome != "Met"
    assert [issue.priority for issue in view.issues] == sorted(issue.priority for issue in view.issues)
    assert view.next_action


def test_confirmed_configuration_failure_and_vendor_report_remain_distinct(cases):
    verified = inspect_review(cases["bypass"], complete_known_case(cases["bypass"]))
    reported = inspect_review(cases["reported"], complete_known_case(cases["reported"]))
    assert verified.validation.evaluation.outcome == "Risk Identified"
    assert any(item.status == "adverse" for item in verified.validation.evaluation.facts)
    assert any(issue.kind == "verified_failure" for issue in verified.issues)
    assert reported.validation.evaluation.outcome == "Needs Review"
    assert any(item.status == "reported_exception" for item in reported.validation.evaluation.facts)
    assert any(issue.kind == "vendor_reported_exception" for issue in reported.issues)
    assert not any(issue.kind == "verified_failure" for issue in reported.issues)


def test_dismissing_a_lexical_signal_cannot_hide_a_separately_proposed_exception(cases):
    case = cases["bypass"]
    state = group(case)
    for signal in inspect_review(case, state).validation.signals:
        # Deliberately mistaken triage must not erase the independent adverse fact.
        state = triage(case, state, signal, False)
    state = ack(case, state)
    view = inspect_review(case, state)
    assert view.validation.evaluation.outcome != "Met"
    assert any(issue.kind == "potential_exception" for issue in view.issues)
    assert all(any(item.fact_id in issue.fact_ids for issue in view.issues) for item in negative_proposals(case))
    for item in negative_proposals(case):
        state = confirm_exception(case, state, expected_bundle=view.bundle_fingerprint,
                                  fact_id=item.fact_id, confirms_semantics=True, **actor(case))
    view = inspect_review(case, state)
    assert any(issue.kind == "verified_failure" for issue in view.issues)
    assert view.validation.evaluation.outcome == "Risk Identified"


def test_exception_confirmation_is_separate_and_cannot_be_used_for_supporting_facts(cases):
    case = cases["bypass"]
    view = inspect_review(case)
    with pytest.raises(ValueError):
        confirm_exception(case, ReviewState(), expected_bundle=view.bundle_fingerprint,
                          fact_id=case.supporting_fact_ids[0], confirms_semantics=True, **actor(case))
    with pytest.raises(ValueError):
        confirm_exception(case, ReviewState(), expected_bundle=view.bundle_fingerprint,
                          fact_id=negative_proposals(case)[0].fact_id, confirms_semantics=False, **actor(case))


def test_conflict_keeps_both_source_accounts_after_exception_confirmation(cases):
    case = cases["conflict"]
    state = complete_known_case(case)
    view = inspect_review(case, state)
    issues = [issue for issue in view.issues if issue.kind == "conflict"]
    assert issues and view.validation.evaluation.outcome != "Met"
    involved = {item.fact_id for item in case.proposals if item.fact.dimension == "enforcement"}
    assert involved <= {fact_id for issue in issues for fact_id in issue.fact_ids}
    assert len({citation.source_id for issue in issues for citation in issue.citations}) >= 2


def test_unknown_method_is_uncertainty_rather_than_a_vendor_admission_of_failure(cases):
    view = inspect_review(cases["unknown"])
    assert any(issue.kind == "incomplete_evidence" for issue in view.issues)
    assert not any(issue.kind in {"verified_failure", "vendor_reported_exception"} for issue in view.issues)


def test_disabled_method_is_not_presented_as_an_active_control_exception(cases):
    case = cases["strong"]
    method = next(item for item in case.proposals if item.fact.dimension == "method")
    disabled = replace(method, fact=replace(method.fact, active=False))
    changed = replace(case, proposals=tuple(disabled if item.fact_id == method.fact_id else item for item in case.proposals))
    view = inspect_review(changed)
    assert any(issue.kind == "incomplete_evidence" for issue in view.issues)
    assert not any(method.fact_id in issue.fact_ids and issue.kind in {
        "verified_failure", "potential_exception", "vendor_reported_exception"} for issue in view.issues)


def test_active_weak_recovery_method_cannot_disappear_behind_fido2_support(cases):
    case = cases["strong"]
    source = replace(case.documents[1], document_id="sms-recovery", filename="sms-recovery.txt", content=(
        b"SYNTHETIC configuration: the enabled recovery path accepts an SMS code plus password and issues a production administrator session."
    ))
    bound = bind_evidence(source)
    primary = next(item for item in case.proposals if item.fact.dimension == "method")
    fact = replace(primary.fact, value="sms", citation=Citation("sms-recovery:1", source.content.decode()),
                   authentication_path="recovery-admin", origin_bound=False, verifier_bound=False)
    weak = ProposedFact("weak-recovery", fact, bound.fingerprint, "Line 1")
    changed = replace(case, documents=case.documents + (source,), proposals=case.proposals + (weak,))
    state = group(changed)
    view = inspect_review(changed, state)
    assert any(weak.fact_id in issue.fact_ids and issue.kind == "potential_exception" for issue in view.issues)
    state = confirm_exception(changed, state, expected_bundle=view.bundle_fingerprint,
                              fact_id=weak.fact_id, confirms_semantics=True, **actor(changed))
    view = inspect_review(changed, state)
    assert any(weak.fact_id in issue.fact_ids and issue.kind == "verified_failure" for issue in view.issues)
    assert view.validation.evaluation.outcome == "Risk Identified"


@pytest.mark.parametrize("activation", [None, False, True])
@pytest.mark.parametrize("weakness", ["sms", "origin_binding", "verifier_binding"])
def test_current_method_failure_requires_affirmative_path_activation(cases, activation, weakness):
    case = cases["strong"]
    original = next(item for item in case.proposals if item.fact.dimension == "method")
    method = "sms" if weakness == "sms" else "fido2"
    activation_statement = {
        None: "The configuration does not establish whether this administrative path is enabled.",
        False: "The administrative authentication path is disabled and cannot issue sessions.",
        True: "The administrative authentication path is enabled and currently issues sessions.",
    }[activation]
    weakness_statement = {
        "sms": "The configured method requires SMS plus a password.",
        "origin_binding": "The deployed FIDO2 key plus PIN implementation does not validate origin binding.",
        "verifier_binding": "The deployed FIDO2 key plus PIN implementation does not validate verifier binding.",
    }[weakness]
    source = replace(case.documents[1], document_id="reviewed-method-path", filename="reviewed-method-path.txt",
                     content=f"SYNTHETIC configuration: {weakness_statement} {activation_statement}".encode())
    bound = bind_evidence(source)
    proposed = replace(original, source_fingerprint=bound.fingerprint, location="Line 1",
                       fact=replace(original.fact, value=method, active=activation,
                                    origin_bound=weakness not in {"sms", "origin_binding"},
                                    verifier_bound=weakness not in {"sms", "verifier_binding"},
                                    citation=Citation("reviewed-method-path:1", source.content.decode())))
    changed = replace(case, documents=case.documents + (source,),
                      proposals=tuple(proposed if row.fact_id == original.fact_id else row for row in case.proposals))
    state = group(changed)
    before = inspect_review(changed, state)
    assert before.validation.evaluation.outcome == "Needs Review"
    assert not any(issue.kind == "verified_failure" for issue in before.issues)
    assert any(proposed.fact_id in issue.fact_ids and
               any(citation.source_id == "reviewed-method-path:1" for citation in issue.citations)
               for issue in before.issues)
    if activation is True:
        state = confirm_exception(changed, state, expected_bundle=before.bundle_fingerprint,
                                  fact_id=proposed.fact_id, confirms_semantics=True, **actor(changed))
        result = inspect_review(changed, state)
        assert result.validation.evaluation.outcome == "Risk Identified"
        assert any(issue.kind == "verified_failure" and proposed.fact_id in issue.fact_ids for issue in result.issues)
    else:
        with pytest.raises(ValueError):
            confirm_exception(changed, state, expected_bundle=before.bundle_fingerprint,
                              fact_id=proposed.fact_id, confirms_semantics=True, **actor(changed))
        for signal in before.validation.signals:
            state = triage(changed, state, signal, False)
        result = inspect_review(changed, ack(changed, state))
        assert result.validation.evaluation.outcome == "Needs Review"
        assert not any(issue.kind == "verified_failure" for issue in result.issues)
        assert not any(item.status == "adverse" for item in result.validation.evaluation.facts)
        if activation is None:
            assert any(proposed.fact_id in issue.fact_ids and
                       "activ" in (issue.title + " " + issue.detail).lower()
                       for issue in result.issues)
    assert result.validation.provisional and result.validation.review_required


def test_restored_pre_fix_method_confirmation_with_unknown_activation_cannot_retain_verified_risk(cases):
    case = cases["strong"]
    original = next(item for item in case.proposals if item.fact.dimension == "method")
    source = replace(case.documents[1], document_id="legacy-method", filename="legacy-method.txt",
                     content=b"SYNTHETIC configuration lists SMS plus password; whether the administrator path is enabled is undocumented.")
    bound = bind_evidence(source)
    proposed = replace(original, source_fingerprint=bound.fingerprint, location="Line 1",
                       fact=replace(original.fact, value="sms", active=None, origin_bound=False,
                                    verifier_bound=False, citation=Citation("legacy-method:1", source.content.decode())))
    changed = replace(case, documents=case.documents + (source,),
                      proposals=tuple(proposed if row.fact_id == original.fact_id else row for row in case.proposals))
    state = group(changed)
    view = inspect_review(changed, state)
    for signal in view.validation.signals:
        state = triage(changed, state, signal, False)
    fingerprint = fact_fingerprint(proposed)
    previous_review = FactReview(fingerprint, "supported", "explicit_exception", "Synthetic pilot analyst",
                                case.as_of, "Pre-fix review accepted method noncompliance without checking activation.")
    previous_event = ReviewEvent("exception_confirmation", view.bundle_fingerprint, (fingerprint,),
                                 (proposed.fact_id,), previous_review.analyst, previous_review.reviewed_on,
                                 previous_review.rationale)
    state = replace(state, fact_reviews=state.fact_reviews + (previous_review,),
                    events=state.events + (previous_event,))
    state = ack(changed, state)
    previous_events = state.events
    result = inspect_review(changed, state)
    assert result.validation.evaluation.outcome == "Needs Review"
    assert not any(item.status == "adverse" for item in result.validation.evaluation.facts)
    assert not any(issue.kind == "verified_failure" for issue in result.issues)
    assert any(issue.kind == "method_activation_gap" and proposed.fact_id in issue.fact_ids
               and any(citation.source_id == "legacy-method:1" for citation in issue.citations)
               for issue in result.issues)
    assert previous_review in state.fact_reviews and state.events == previous_events
    assert previous_event in state.events
    with pytest.raises(ValueError):
        confirm_exception(changed, state, expected_bundle=view.bundle_fingerprint,
                          fact_id=proposed.fact_id, confirms_semantics=True, **actor(changed))


@pytest.mark.parametrize("decision", ["unsupported", "ambiguous"])
def test_challenge_before_grouping_withholds_one_fact_and_preserves_other_review_work(cases, decision):
    case = cases["strong"]
    target = next(item for item in case.proposals if item.fact.dimension == "enforcement")
    fingerprint = fact_fingerprint(target)
    initial = inspect_review(case)
    state = challenge_supporting(
        case, ReviewState(), expected_bundle=initial.bundle_fingerprint,
        fact_id=target.fact_id, decision=decision,
        **actor(case, rationale="The source does not establish complete emergency-account enforcement coverage."),
    )
    assert len(state.events) == 1
    assert state.events[0].target_ids == (target.fact_id,)
    assert state.events[0].fact_fingerprints == (fingerprint,)
    assert state.fact_reviews[0].decision == decision
    assert state.fact_reviews[0].classification == "unsupported_interpretation"
    assert not state.signal_dispositions and state.bundle_review is None
    challenged = inspect_review(case, state)
    assert fingerprint not in challenged.supporting_fingerprints
    assert any(target.fact_id in issue.fact_ids and
               any(citation.source_id == target.fact.citation.source_id for citation in issue.citations)
               for issue in challenged.issues)
    state = group(case, state)
    assert len(state.fact_reviews) == 7
    assert sum(review.decision == "supported" for review in state.fact_reviews) == 6
    for signal in inspect_review(case, state).validation.signals:
        state = triage(case, state, signal, False)
    result = inspect_review(case, ack(case, state))
    assert result.validation.evaluation.outcome == "Needs Review"
    assert not any(item.fact == target.fact for item in result.validation.evaluation.facts)
    assert any(row.proposal == target and row.status != "validated" for row in result.validation.facts)


@pytest.mark.parametrize("decision", ["unsupported", "ambiguous"])
def test_challenge_supersedes_grouped_confirmation_after_met_without_erasing_history(cases, decision):
    case = cases["strong"]
    state = complete_known_case(case)
    assert inspect_review(case, state).validation.evaluation.outcome == "Met"
    target = next(item for item in case.proposals if item.fact.dimension == "enforcement")
    fingerprint = fact_fingerprint(target)
    original_events = state.events
    original_signals = state.signal_dispositions
    original_others = tuple(review for review in state.fact_reviews if review.fact_fingerprint != fingerprint)
    corrected = challenge_supporting(
        case, state, expected_bundle=inspect_review(case, state).bundle_fingerprint,
        fact_id=target.fact_id, decision=decision,
        **actor(case, rationale="On re-reading, emergency-account coverage is not established by this export."),
    )
    assert corrected.events[:-1] == original_events
    assert corrected.events[-1].target_ids == (target.fact_id,)
    assert corrected.events[-1].fact_fingerprints == (fingerprint,)
    assert corrected.signal_dispositions == original_signals
    assert corrected.bundle_review is None
    assert tuple(review for review in corrected.fact_reviews if review.fact_fingerprint != fingerprint) == original_others
    current = [review for review in corrected.fact_reviews if review.fact_fingerprint == fingerprint]
    assert len(current) == 1 and current[0].decision == decision
    result = inspect_review(case, corrected)
    assert result.validation.evaluation.outcome == "Needs Review"
    assert not result.validation.bundle_review_valid
    assert fingerprint not in result.supporting_fingerprints
    reacknowledged = ack(case, corrected)
    assert inspect_review(case, reacknowledged).validation.evaluation.outcome == "Needs Review"
    assert reacknowledged.events[:len(original_events)] == original_events


@pytest.mark.parametrize("changes", [
    {"decision": "supported"}, {"decision": "approved"}, {"fact_id": "missing-fact"},
    {"expected_bundle": "0" * 64}, {"analyst": ""}, {"rationale": " "},
])
def test_challenge_requires_current_fact_binding_negative_disposition_and_reason(cases, changes):
    case = cases["strong"]
    fields = dict(expected_bundle=inspect_review(case).bundle_fingerprint,
                  fact_id="enforcement", decision="unsupported", **actor(case))
    fields.update(changes)
    with pytest.raises(ValueError):
        challenge_supporting(case, ReviewState(), **fields)


def test_challenge_cannot_reuse_a_stale_state_or_invalid_review_date(cases):
    case = cases["strong"]
    old_state = complete_known_case(case)
    changed = replace(case, requirement=replace(case.requirement, version="new-version"))
    with pytest.raises(ValueError):
        challenge_supporting(changed, old_state,
                             expected_bundle=inspect_review(changed).bundle_fingerprint,
                             fact_id="enforcement", decision="unsupported", **actor(changed))
    for invalid_date in (case.as_of + timedelta(days=1), min(source.captured_on for source in case.documents) - timedelta(days=1)):
        with pytest.raises(ValueError):
            challenge_supporting(case, ReviewState(), expected_bundle=inspect_review(case).bundle_fingerprint,
                                 fact_id="enforcement", decision="ambiguous",
                                 **actor(case, reviewed_on=invalid_date))


def test_uncited_source_provenance_gap_stays_in_the_exception_first_queue(cases):
    case = cases["strong"]
    appendix = replace(case.documents[1], document_id="unverified-appendix", filename="unverified-appendix.txt",
                       content=b"SYNTHETIC supplementary administrator inventory note.",
                       version=None, origin=None, captured_on=None)
    changed = replace(case, documents=case.documents + (appendix,))
    state = complete_known_case(changed)
    view = inspect_review(changed, state)
    assert view.validation.evaluation.outcome == "Needs Review"
    assert any("unverified-appendix" in issue.detail and issue.kind in {
        "source_integrity", "incomplete_evidence"} for issue in view.issues)
    assert not view.next_action.startswith("Send the provisional result")


def test_ungrouped_positive_proposal_cannot_disappear_from_remaining_review_work(cases):
    case = cases["strong"]
    omitted = next(item for item in case.proposals if item.fact.dimension == "enforcement")
    changed = replace(case, supporting_fact_ids=tuple(
        fact_id for fact_id in case.supporting_fact_ids if fact_id != omitted.fact_id))
    state = complete_known_case(changed)
    view = inspect_review(changed, state)
    assert view.validation.evaluation.outcome == "Needs Review"
    assert any(omitted.fact_id in issue.fact_ids for issue in view.issues)
    assert not view.next_action.startswith("Send the provisional result")


def test_restored_duplicate_signal_disposition_cannot_hide_material_m3b_result(cases):
    case = cases["strong"]
    source = replace(case.documents[1], document_id="uncited-emergency", filename="uncited-emergency.txt", content=(
        b"SYNTHETIC emergency administrator accounts bypass MFA using a password-only local login."
    ))
    changed = replace(case, documents=case.documents + (source,))
    state = group(changed)
    material_id = None
    for signal in inspect_review(changed, state).validation.signals:
        material = signal.source_id == "uncited-emergency:1"
        if material:
            material_id = signal.signal_id
        state = triage(changed, state, signal, material)
    assert material_id is not None
    state = ack(changed, state)
    inconsistent = replace(state, signal_dispositions=state.signal_dispositions + (
        SignalDisposition(material_id, False, "Incorrect nonmaterial entry in restored transient state."),))
    view = inspect_review(changed, inconsistent)
    assert any(signal.signal_id == material_id and signal.status == "material" for signal in view.validation.signals)
    assert any(material_id in issue.signal_ids for issue in view.issues)
    assert view.validation.evaluation.outcome == "Needs Review"


@pytest.mark.parametrize("change", ["quote", "method_properties", "uncertainty", "scope"])
def test_forged_positive_interpretation_cannot_enter_grouped_confirmation(cases, change):
    case = cases["strong"]
    proposal = next(item for item in case.proposals if item.fact.dimension == "method")
    if change == "quote":
        altered = replace(proposal, fact=replace(proposal.fact, citation=Citation(
            proposal.fact.citation.source_id, "A fabricated quotation that does not exist.")))
    elif change == "method_properties":
        altered = replace(proposal, fact=replace(proposal.fact, verifier_bound=None))
    elif change == "uncertainty":
        altered = replace(proposal, fact=replace(proposal.fact, uncertainty="Coverage has not been established."))
    else:
        altered = replace(proposal, fact=replace(proposal.fact, account_scope="three sampled administrators"))
    changed = replace(case, proposals=tuple(altered if item.fact_id == proposal.fact_id else item for item in case.proposals))
    view = inspect_review(changed)
    assert fact_fingerprint(altered) not in view.supporting_fingerprints
    with pytest.raises(ValueError):
        group(changed, presented_fingerprints=view.supporting_fingerprints + (fact_fingerprint(altered),))
    assert view.validation.evaluation.outcome != "Met"
    if view.supporting_fingerprints:
        state = group(changed)
        assert not any(review.fact_fingerprint == fact_fingerprint(altered) for review in state.fact_reviews)
        assert {review.fact_fingerprint for review in state.fact_reviews} == set(view.supporting_fingerprints)
        assert inspect_review(changed, state).validation.evaluation.outcome != "Met"


def test_policy_metadata_cannot_be_grouped_into_implementation_or_operating_proof(cases):
    case = cases["strong"]
    sources = tuple(replace(item, evidence_kind="policy") for item in case.documents)
    by_id = {item.document_id: bind_evidence(item) for item in sources}
    proposals = tuple(replace(item, source_fingerprint=by_id[item.fact.citation.source_id.split(":")[0]].fingerprint,
                              fact=replace(item.fact, evidence_kind="policy")) for item in case.proposals)
    changed = replace(case, documents=sources, proposals=proposals)
    view = inspect_review(changed)
    assert not view.supporting_fingerprints
    with pytest.raises(ValueError):
        group(changed)
    assert not view.validation.evaluation.facts


def test_empty_proposals_never_count_as_a_complete_group(cases):
    case = replace(cases["strong"], proposals=(), supporting_fact_ids=())
    assert not inspect_review(case).supporting_fingerprints
    with pytest.raises(ValueError):
        group(case)
    assert inspect_review(case).validation.evaluation.outcome != "Met"


def test_modeled_action_counts_record_group_savings_without_erasing_exception_work(cases, capsys):
    rows = []
    for case_id in ("strong", "bypass", "reported"):
        case = cases[case_id]
        initial = inspect_review(case)
        state = complete_known_case(case)
        view = inspect_review(case, state)
        baseline = len(initial.supporting) + len(negative_proposals(case)) + len(initial.validation.signals) + 1
        expected = bool(initial.supporting) + len(negative_proposals(case)) + len(initial.validation.signals) + 1
        assert len(state.events) == expected
        assert baseline - len(state.events) == max(0, len(initial.supporting) - 1)
        if case_id != "strong":
            assert any(issue.kind in {"verified_failure", "vendor_reported_exception"} for issue in view.issues)
            assert view.validation.evaluation.outcome != "Met"
        rows.append({"case": case_id, "supporting_facts": len(initial.supporting),
                     "exception_facts": len(negative_proposals(case)), "signal_decisions": len(initial.validation.signals),
                     "m3b_per_fact_baseline_decisions": baseline, "m3c_recorded_decisions": len(state.events)})
    assert rows[0]["supporting_facts"] == 7
    with capsys.disabled():
        print("\nM3C modeled analyst decision submissions: " + json.dumps(rows, sort_keys=True))


def test_review_actions_remain_in_memory_and_do_not_write_to_external_systems(cases, monkeypatch):
    import builtins
    import socket
    from sqlalchemy.engine import Engine

    case = cases["strong"]

    def forbidden(*args, **kwargs):
        raise AssertionError("The M3C pilot must not access files, databases or the network during review.")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(Engine, "connect", forbidden)
        state = complete_known_case(case)
    assert inspect_review(case, state).validation.evaluation.outcome == "Met"
