"""Actual UI regression paths for applicable requirements without specialist rules."""
from dataclasses import replace
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from src.control_assurance import CustomerThreshold, inspect_control
from src.control_assurance_pilot import control_pilot_cases, fallback_pilot_cases
from src.evidence_source_validation import bind_evidence


PILOT = (
    "from src.control_assurance_ui import render_control_assurance_pilot\n"
    "render_control_assurance_pilot(actor_label='Synthetic analyst')"
)
FAMILY = "Vulnerability remediation"
MEANING_LABEL = (
    "I checked this interpretation against its full source and confirm its meaning, "
    "without judging whether the requirement is met."
)
SPECIALIST_LIMIT = "Specialist evaluation unavailable; analyst review required."


def widget(items, label):
    return next(item for item in items if item.label == label)


def app(case_id="vm-present"):
    at = AppTest.from_string(PILOT, default_timeout=20).run()
    assert not at.exception
    widget(at.selectbox, "Control family").set_value(FAMILY).run()
    widget(at.selectbox, "Synthetic control package").set_value(case_id).run()
    assert not at.exception
    return at


def case(case_id="vm-present"):
    return next(c for c in fallback_pilot_cases() if c.case_id == case_id)


def assert_outcome(at, outcome):
    assert any("Provisional outcome: " + outcome in item.value for item in at.info)
    assert not any("Provisional outcome: " + value in item.value
                   for item in at.info for value in ("Met", "Risk Identified"))


def assert_specialist_limit(at):
    assert any(SPECIALIST_LIMIT in item.value for item in list(at.warning) + list(at.caption) + list(at.markdown))


def confirm_one_meaning(at):
    c = case()
    row = next(f for f in inspect_control(c).facts if f.direction == "review")
    widget(at.selectbox, "Interpretation to review").set_value(row.proposal.fact_id).run()
    widget(at.text_area, "Reason for this review").set_value(
        "Checked this quoted interpretation against the complete synthetic source; specialist judgment remains necessary."
    ).run()
    widget(at.checkbox, MEANING_LABEL).check().run()
    widget(at.button, "Confirm this interpretation's meaning").click().run()
    assert not at.exception
    return row


def test_fourth_unrelated_requirement_enters_common_read_only_review_without_rules(monkeypatch):
    from sqlalchemy.engine import Engine

    def forbidden(*args, **kwargs):
        raise AssertionError("The synthetic fallback must not access a database.")

    monkeypatch.setattr(Engine, "connect", forbidden)
    at = app()
    c = case()
    assert c.evaluator is None
    assert_outcome(at, "Needs Review")
    assert_specialist_limit(at)
    assert any("Customer requirement:" in item.value and c.requirement.customer_policy_id in item.value for item in at.markdown)
    assert any("Threshold:" in item.value and c.threshold.describe() in item.value for item in at.markdown)
    assert any("Recommended next action:" in item.value for item in at.markdown)
    assert "m3d_current_review" not in at.session_state
    assert not at.get("file_uploader")
    assert not any(item.label == "Confirm displayed supporting interpretations" for item in at.button)
    assert widget(at.button, "Confirm this interpretation's meaning").disabled
    for p in c.proposals:
        assert any(p.quote in item.value for item in at.code)
        assert any(p.location in item.value for item in at.caption)
    assert any("SHA-256" in item.value for item in at.caption)


def test_missing_evidence_stays_visible_and_missing_after_explicit_bundle_review():
    at = app("vm-missing")
    assert_outcome(at, "Evidence Missing")
    assert_specialist_limit(at)
    assert not any(item.label == "Confirm this interpretation's meaning" for item in at.button)
    assert not any(item.label == "Confirm displayed supporting interpretations" for item in at.button)
    widget(at.text_area, "Reason for this review").set_value(
        "No usable service evidence was supplied; request only the required remediation records."
    ).run()
    widget(at.checkbox, "I reviewed all supplied documents and their disagreements, scope, dates and technical coverage.").check().run()
    widget(at.button, "Record complete-bundle review").click().run()
    assert not at.exception
    state = at.session_state["m3d_current_review"][1]
    assert state.bundle_review is not None and not state.fact_reviews
    assert_outcome(at, "Evidence Missing")
    assert_specialist_limit(at)


def test_single_meaning_confirmation_never_confirms_requirement_or_triages_exception():
    at = app()
    row = confirm_one_meaning(at)
    state = at.session_state["m3d_current_review"][1]
    assert len(state.fact_reviews) == 1
    assert state.fact_reviews[0].fact_fingerprint == row.fingerprint
    assert state.events[-1].kind == "meaning"
    assert state.events[-1].fact_fingerprints == (row.fingerprint,)
    assert not state.signal_dispositions and state.bundle_review is None
    assert_outcome(at, "Needs Review")
    assert_specialist_limit(at)


def test_adverse_interpretation_and_signals_remain_separate_and_never_produce_pass_or_failure():
    at = app()
    confirmed = confirm_one_meaning(at)
    c = case()
    adverse = next(f for f in inspect_control(c).facts if f.direction == "adverse")
    assert any(adverse.proposal.quote in item.value for item in at.code)
    assert any("exception" in item.value.casefold() or "conflict" in item.value.casefold() for item in at.warning)
    widget(at.selectbox, "Exception interpretation").set_value(adverse.proposal.fact_id).run()
    widget(at.checkbox, "I checked this exception's meaning and affected scope in the full source context.").check().run()
    widget(at.button, "Confirm this exception's meaning").click().run()
    assert not at.exception
    state = at.session_state["m3d_current_review"][1]
    assert state.events[-1].kind == "exception"
    assert {r.fact_fingerprint for r in state.fact_reviews} == {confirmed.fingerprint, adverse.fingerprint}
    assert not state.signal_dispositions and state.bundle_review is None
    assert_outcome(at, "Needs Review")
    for s in inspect_control(c).signals:
        widget(at.selectbox, "Source signal").set_value(s.signal_id).run()
        widget(at.radio, "After checking the full context").set_value("Not material to this requirement").run()
        widget(at.button, "Record this signal triage").click().run()
        assert not at.exception
    widget(at.checkbox, "I reviewed all supplied documents and their disagreements, scope, dates and technical coverage.").check().run()
    widget(at.button, "Record complete-bundle review").click().run()
    state = at.session_state["m3d_current_review"][1]
    assert inspect_control(c, state).outcome == "Needs Review"
    assert any(adverse.proposal.quote in item.value for item in at.code)
    assert_specialist_limit(at)


def test_individual_challenge_retains_original_source_and_human_event_history():
    at = app()
    row = confirm_one_meaning(at)
    widget(at.selectbox, "Interpretation to challenge").set_value(row.proposal.fact_id).run()
    widget(at.text_area, "Reason for this review").set_value("The original interpretation overstates what the source establishes.").run()
    widget(at.button, "Record interpretation challenge").click().run()
    assert not at.exception
    state = at.session_state["m3d_current_review"][1]
    assert [e.kind for e in state.events] == ["meaning", "challenge_unsupported"]
    assert state.fact_reviews[0].decision == "unsupported"
    assert not state.bundle_review
    assert any(row.proposal.quote in item.value for item in at.code)
    assert_outcome(at, "Needs Review")


@pytest.mark.parametrize("mutation", ["policy", "threshold", "date", "source"])
def test_fallback_policy_threshold_date_or_source_change_invalidates_active_ui_review(monkeypatch, mutation):
    import src.control_assurance_ui as ui

    cases = fallback_pilot_cases()
    monkeypatch.setattr(ui, "fallback_pilot_cases", lambda: cases)
    at = app()
    confirm_one_meaning(at)
    assert "m3d_current_review" in at.session_state
    changed = next(c for c in cases if c.case_id == "vm-present")
    if mutation == "policy":
        changed = replace(changed, requirement=replace(changed.requirement, policy_version="2026.2"))
    elif mutation == "threshold":
        changed = replace(changed, threshold=CustomerThreshold("Customer critical remediation deadline is 14 days; specialist review remains required."))
    elif mutation == "date":
        changed = replace(changed, as_of=date(2026, 10, 22))
    else:
        source = replace(changed.documents[-1], content=changed.documents[-1].content + b"\nSYNTHETIC corrected source context.")
        changed = replace(changed, documents=changed.documents[:-1] + (source,))
    cases = tuple(changed if c.case_id == changed.case_id else c for c in cases)
    at.run()
    assert not at.exception and "m3d_current_review" not in at.session_state
    assert widget(at.button, "Confirm this interpretation's meaning").disabled
    assert_specialist_limit(at)


@pytest.mark.parametrize("change", ["stale", "other_service"])
def test_unusable_fallback_evidence_is_missing_but_source_context_remains_available(monkeypatch, change):
    import src.control_assurance_ui as ui

    current = case()
    docs = tuple(replace(d, observed_on=date(2020, 1, 1)) if change == "stale"
                 else replace(d, service="Different synthetic service") for d in current.documents)
    owners = {d.document_id: d for d in docs}
    ps = tuple(replace(p, source_fingerprint=bind_evidence(owners[p.source_id.split(":")[0]]).fingerprint)
               for p in current.proposals)
    changed = replace(current, documents=docs, proposals=ps)
    monkeypatch.setattr(ui, "fallback_pilot_cases", lambda: (changed,))
    at = app()
    assert_outcome(at, "Evidence Missing")
    assert_specialist_limit(at)
    assert any("stale" in item.value.casefold() if change == "stale" else "scope" in item.value.casefold() for item in at.warning)
    assert any(current.proposals[0].quote in item.value for item in at.code)


def test_arbitrary_subsequent_family_is_registered_without_editing_common_renderer(monkeypatch):
    import src.control_assurance_ui as ui

    original = case("vm-missing")
    fifth = replace(original, case_id="logging-unavailable", family="Security event retention",
                    title="Customer event-retention requirement without specialist rules",
                    requirement=replace(original.requirement, requirement_id="CUSTOM-LOG-99", customer_policy_id="synthetic-event-retention"),
                    threshold=CustomerThreshold("Retain service security events for at least 90 days."))
    monkeypatch.setattr(ui, "control_pilot_cases", lambda: control_pilot_cases() + (fifth,))
    at = AppTest.from_string(PILOT, default_timeout=20).run()
    assert not at.exception
    assert fifth.family in widget(at.selectbox, "Control family").options
    widget(at.selectbox, "Control family").set_value(fifth.family).run()
    assert not at.exception
    assert_outcome(at, "Evidence Missing")
    assert_specialist_limit(at)
    assert any("CUSTOM-LOG-99" in item.value for item in at.markdown)
    assert any(fifth.threshold.describe() in item.value for item in at.markdown)


def test_package_and_family_switch_discard_fallback_confirmation():
    at = app()
    confirm_one_meaning(at)
    widget(at.selectbox, "Synthetic control package").set_value("vm-missing").run()
    assert "m3d_current_review" not in at.session_state
    assert_outcome(at, "Evidence Missing")
    widget(at.selectbox, "Control family").set_value("Transport encryption (TLS)").run()
    widget(at.selectbox, "Control family").set_value(FAMILY).run()
    widget(at.selectbox, "Synthetic control package").set_value("vm-present").run()
    assert not at.exception and "m3d_current_review" not in at.session_state
    assert widget(at.button, "Confirm this interpretation's meaning").disabled
