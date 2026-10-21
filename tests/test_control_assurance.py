"""Adversarial synthetic proof, not a measure of vendor extraction accuracy."""
import ast
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from src.control_assurance import (
    ControlReviewState, inspect_control, observation_fingerprint, record_control_review,
)
from src.control_assurance_pilot import control_pilot_cases, document, proposal
from src.evidence_source_validation import bind_evidence
from src.tls_assurance import TlsThreshold
from src.dr_assurance import DrThreshold


CASES = {c.case_id: c for c in control_pilot_cases()}


def act(case, state, action, **kwargs):
    return record_control_review(case, state, action=action,
        expected_bundle=inspect_control(case).bundle_fingerprint, analyst="Synthetic reviewer",
        reviewed_on=case.as_of, rationale="Checked the complete synthetic source and meaning.", **kwargs)


def confirm(case, state, rows, action="support"):
    return act(case, state, action, fact_ids=tuple(f.proposal.fact_id for f in rows),
               presented_fingerprints=tuple(f.fingerprint for f in rows), confirms=True)


def review_all(case):
    """Test-only explicit actions; production fixtures seed no dispositions."""
    state = ControlReviewState()
    view = inspect_control(case)
    support = [f for f in view.facts if f.direction == "support" and not f.reasons]
    if support:
        state = confirm(case, state, support)
    for f in view.facts:
        if f.direction == "adverse" and not f.reasons:
            state = confirm(case, state, [f], "exception")
    for s in view.signals:
        state = act(case, state, "signal", signal_id=s.signal_id, material=False)
    return act(case, state, "bundle", confirms=True)


@pytest.mark.parametrize("family", ["tls", "dr"])
def test_positive_needs_individual_semantics_and_separate_bundle(family):
    case = CASES[family + "-strong"]
    view = inspect_control(case)
    assert view.outcome == "Needs Review" and not any(f.confirmed for f in view.facts)
    assert not view.bundle_review_valid and all(not f.reasons for f in view.facts)
    state = confirm(case, ControlReviewState(), view.facts)
    grouped = inspect_control(case, state)
    assert grouped.outcome == "Needs Review" and not state.bundle_review
    assert len(state.fact_reviews) == len(case.proposals) and len(state.events) == 1
    assert all(f.confirmed for f in grouped.facts)
    final = inspect_control(case, review_all(case))
    assert final.outcome == "Met" and final.bundle_review_valid
    assert final.provisional and final.review_required


@pytest.mark.parametrize("case_id,expected", [
    ("tls-exception", "Risk Identified"), ("dr-exception", "Risk Identified"),
    ("tls-reported", "Needs Review"), ("dr-reported", "Needs Review"),
    ("tls-conflict", "Needs Review"), ("dr-conflict", "Needs Review"),
    ("tls-stale", "Needs Review"), ("dr-stale", "Needs Review"),
    ("tls-scope", "Needs Review"), ("dr-scope", "Needs Review"),
    ("tls-statement", "Evidence Missing"), ("dr-statement", "Evidence Missing"),
    ("tls-strict", "Risk Identified"), ("dr-strict", "Risk Identified"),
])
def test_adversarial_multi_document_corpus(case_id, expected):
    case = CASES[case_id]
    assert len(case.documents) >= 2
    view = inspect_control(case, review_all(case))
    assert view.outcome == expected
    assert view.outcome != "Met"
    if "conflict" in case_id:
        assert any(c.status == "conflict" and len(c.fact_ids) >= 2 for c in view.checks)
    if "reported" in case_id:
        assert any(c.status == "reported" for c in view.checks)
        assert not any(c.status == "failed" for c in view.checks)


@pytest.mark.parametrize("family", ["tls", "dr"])
def test_material_candidate_cannot_hide_behind_group_and_dismissed_signals(family):
    case = CASES[family + "-exception"]
    view = inspect_control(case)
    support = [f for f in view.facts if f.direction == "support"]
    state = confirm(case, ControlReviewState(), support)
    for s in view.signals:
        state = act(case, state, "signal", signal_id=s.signal_id, material=False)
    state = act(case, state, "bundle", confirms=True)
    assert inspect_control(case, state).outcome == "Needs Review"
    adverse = next(f for f in view.facts if f.direction == "adverse")
    with pytest.raises(ValueError, match="Adverse"):
        confirm(case, state, [adverse])
    state = confirm(case, state, [adverse], "exception")
    assert inspect_control(case, state).outcome == "Risk Identified"
    assert state.bundle_review is None


@pytest.mark.parametrize("family", ["tls", "dr"])
@pytest.mark.parametrize("mutation", ["policy", "threshold", "source", "origin", "scope", "date", "interpretation"])
def test_every_material_change_invalidates_all_active_review(family, mutation):
    case = CASES[family + "-strong"]
    state = review_all(case)
    assert inspect_control(case, state).outcome == "Met"
    if mutation == "policy":
        changed = replace(case, requirement=replace(case.requirement, policy_version="2026.2"))
    elif mutation == "threshold":
        threshold = TlsThreshold(13) if family == "tls" else DrThreshold(90, 60, 5)
        changed = replace(case, threshold=threshold)
    elif mutation in {"source", "origin"}:
        d = case.documents[-1]
        d = replace(d, content=d.content + b"\nSYNTHETIC additional source context.") if mutation == "source" else replace(d, origin="Different synthetic custody")
        changed = replace(case, documents=case.documents[:-1] + (d,))
    elif mutation == "scope":
        changed = replace(case, requirement=replace(case.requirement, scope="another recovery/endpoint population"))
    elif mutation == "date":
        changed = replace(case, as_of=date(2026, 10, 22))
    else:
        changed = replace(case, proposals=(replace(case.proposals[0], quote="Changed interpretation"),) + case.proposals[1:])
    result = inspect_control(changed, state)
    assert result.outcome != "Met" and not result.bundle_review_valid
    assert not any(f.confirmed for f in result.facts)
    with pytest.raises(ValueError, match="bundle changed"):
        record_control_review(changed, state, action="bundle", expected_bundle=state.bundle_fingerprint,
            analyst="Reviewer", reviewed_on=case.as_of, rationale="old action", confirms=True)


@pytest.mark.parametrize("property,value", [("source_id", "missing:1"), ("source_fingerprint", "bad"),
                                            ("location", "Page 500"), ("quote", "Invented exact quotation")])
def test_source_identity_location_and_exact_quote_fail_closed(property, value):
    case = CASES["tls-strong"]
    case = replace(case, proposals=(replace(case.proposals[0], **{property: value}),) + case.proposals[1:])
    view = inspect_control(case)
    assert view.facts[0].reasons and not view.facts[0].confirmed
    with pytest.raises(ValueError):
        confirm(case, ControlReviewState(), [view.facts[0]])
    # A broken citation must remain individually challengeable, not crash review.
    f = view.facts[0]
    state = act(case, ControlReviewState(), "challenge", fact_ids=(f.proposal.fact_id,),
                presented_fingerprints=(f.fingerprint,), decision="unsupported")
    assert state.events[-1].kind == "challenge_unsupported"
    assert not inspect_control(case, state).facts[0].confirmed


def test_matching_quote_with_unreviewed_invented_interpretation_never_means_met():
    case = CASES["tls-strong"]
    p = replace(case.proposals[0], value=13)  # actual quote says 1.2
    case = replace(case, proposals=(p,) + case.proposals[1:])
    state = act(case, ControlReviewState(), "bundle", confirms=True)
    assert inspect_control(case, state).outcome != "Met"
    assert not any(f.confirmed for f in inspect_control(case, state).facts)


@pytest.mark.parametrize("family", ["tls", "dr"])
def test_challenge_retains_other_confirmations_sources_and_history(family):
    case = CASES[family + "-strong"]
    state = review_all(case)
    f = inspect_control(case, state).facts[0]
    state = act(case, state, "challenge", fact_ids=(f.proposal.fact_id,),
                presented_fingerprints=(f.fingerprint,), decision="unsupported")
    result = inspect_control(case, state)
    assert result.outcome != "Met" and not result.bundle_review_valid
    assert sum(f.confirmed for f in result.facts) == len(case.proposals) - 1
    assert len(result.evidence) == len(case.documents)
    assert state.events[0].kind == "support" and state.events[-1].kind == "challenge_unsupported"
    state = act(case, state, "bundle", confirms=True)
    assert inspect_control(case, state).outcome != "Met"


@pytest.mark.parametrize("family", ["tls", "dr"])
def test_unknown_active_state_and_wrong_boolean_types_cannot_support_met(family):
    case = CASES[family + "-strong"]
    for change in ({"active": None}, {"value": "true"}):
        changed = replace(case, proposals=(replace(case.proposals[0], **change),) + case.proposals[1:])
        assert inspect_control(changed, review_all(changed)).outcome != "Met"


def test_tls_configuration_without_scans_and_scans_without_configuration_are_partial():
    case = CASES["tls-strong"]
    for kind in ("configuration", "test"):
        keep = tuple(d for d in case.documents if d.evidence_kind != kind)
        ids = {d.document_id for d in keep}
        changed = replace(case, documents=keep, proposals=tuple(p for p in case.proposals if p.source_id.split(":")[0] in ids))
        assert inspect_control(changed, review_all(changed)).outcome == "Partially Met"


def test_dr_test_cadence_differs_from_document_freshness_and_plan_targets():
    case = CASES["dr-strong"]
    d = replace(case.documents[-1], observed_on=date(2026, 1, 1))
    ps = tuple(replace(p, source_fingerprint=bind_evidence(d).fingerprint) for p in case.proposals)
    old = replace(case, documents=(case.documents[0], d), proposals=ps)
    assert inspect_control(old, review_all(old)).outcome == "Met"  # annual
    quarterly = replace(old, threshold=DrThreshold(90, 240, 60))
    assert inspect_control(quarterly, review_all(quarterly)).outcome != "Met"
    plan = replace(d, evidence_kind="policy")
    planned = replace(case, documents=(case.documents[0], plan), proposals=tuple(
        replace(p, source_fingerprint=bind_evidence(plan).fingerprint) for p in ps))
    assert inspect_control(planned, review_all(planned)).outcome == "Evidence Missing"


def test_dr_cannot_assemble_one_success_from_unrelated_exercises():
    case = CASES["dr-strong"]
    d = replace(case.documents[-1], document_id="different-exercise", filename="different-exercise.txt")
    rpo = proposal(d, "achieved_rpo_minutes", 4, 15)
    changed = replace(case, documents=case.documents + (d,), proposals=case.proposals[:-1] + (rpo,))
    result = inspect_control(changed, review_all(changed))
    assert result.outcome != "Met" and any(c.dimension == "exercise_binding" for c in result.checks)


def test_shared_contract_and_non_mfa_domains_have_no_mfa_import_dependency():
    for name in ("control_assurance", "control_assurance_presentation", "evidence_source_validation", "tls_assurance", "dr_assurance"):
        tree = ast.parse(Path("src", name + ".py").read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any("mfa" in module or "intelligence_m3" in module for module in imports)


@pytest.mark.parametrize("family", ["tls", "dr"])
def test_uncited_provenance_limits_and_material_signal_still_block_positive(family):
    base = CASES[family + "-strong"]
    d = document("uncited-adverse", "SYNTHETIC exception: an alternate endpoint or recovery dependency remains excluded.",
                 base.requirement.scope, kind="assertion")
    case = replace(base, documents=base.documents + (d,))
    state = review_all(case)
    signal = next(s for s in inspect_control(case).signals if s.filename == d.filename)
    state = act(case, state, "signal", signal_id=signal.signal_id, material=True)
    state = act(case, state, "bundle", confirms=True)
    result = inspect_control(case, state)
    assert result.outcome == "Needs Review" and any(s.status == "material" for s in result.signals)
    bad = replace(d, origin=None)
    case = replace(base, documents=base.documents + (bad,))
    result = inspect_control(case, review_all(case))
    assert result.outcome == "Needs Review" and any("origin" in x for x in result.limitations)


def test_threshold_display_is_derived_from_rules_and_handles_not_applicable_objectives():
    tls = replace(CASES["tls-strong"], threshold=TlsThreshold(13))
    assert "TLS 1.3" in inspect_control(tls).threshold_summary
    dr = replace(CASES["dr-strong"], threshold=DrThreshold(90, None, 0))
    assert "RTO not applicable" in inspect_control(dr).threshold_summary
    assert "RPO ≤ 0 minutes" in inspect_control(dr).threshold_summary
    assert "90 days" in inspect_control(dr).threshold_summary


@pytest.mark.parametrize("family", ["tls", "dr"])
def test_explicit_boolean_confirmation_and_presented_fingerprints_are_required(family):
    case = CASES[family + "-strong"]
    rows = inspect_control(case).facts
    for changes in ({"confirms": False}, {"confirms": "yes"}, {"presented_fingerprints": ("old",)}):
        kwargs = dict(fact_ids=tuple(f.proposal.fact_id for f in rows),
                      presented_fingerprints=tuple(f.fingerprint for f in rows), confirms=True)
        kwargs.update(changes)
        with pytest.raises(ValueError):
            act(case, ControlReviewState(), "support", **kwargs)
    with pytest.raises(ValueError):
        act(case, ControlReviewState(), "bundle", confirms="yes")


def test_old_failed_dr_report_is_stale_uncertainty_not_current_verified_failure():
    case = CASES["dr-exception"]
    docs = tuple(replace(d, observed_on=date(2026, 1, 1)) if d.evidence_kind == "test" else d for d in case.documents)
    by_id = {d.document_id: d for d in docs}
    ps = tuple(replace(p, source_fingerprint=bind_evidence(by_id[p.source_id.split(":")[0]]).fingerprint) for p in case.proposals)
    case = replace(case, threshold=DrThreshold(90, 240, 60), documents=docs, proposals=ps)
    result = inspect_control(case, review_all(case))
    assert result.outcome == "Needs Review"
    assert any(c.dimension == "test_cadence" for c in result.checks)
    assert not any(c.status == "failed" for c in result.checks)


def test_no_false_met_or_missed_current_material_exception_in_bounded_corpus():
    results = {key: inspect_control(case, review_all(case)) for key, case in CASES.items()}
    incorrect_positive = [key for key, result in results.items() if result.outcome == "Met" and not key.endswith("-strong")]
    missed_exceptions = [key for key in ("tls-exception", "dr-exception", "tls-strict", "dr-strict")
                         if results[key].outcome != "Risk Identified"]
    assert not incorrect_positive and not missed_exceptions
    assert sum(r.outcome == "Met" for r in results.values()) == 2
