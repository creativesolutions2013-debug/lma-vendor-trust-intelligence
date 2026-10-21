"""Requirement-specific evidence eligibility through the actual shared UI."""
from dataclasses import replace

import pytest
from streamlit.testing.v1 import AppTest

from src.control_assurance import inspect_control
from src.control_assurance_pilot import suitability_pilot_cases


PILOT = (
    "from src.control_assurance_ui import render_control_assurance_pilot\n"
    "render_control_assurance_pilot(actor_label='Synthetic suitability reviewer')"
)
MEANING_LABEL = (
    "I checked this interpretation against its full source and confirm its meaning, "
    "without judging whether the requirement is met."
)
SPECIALIST_LIMIT = "Specialist evaluation unavailable; analyst review required."


def widget(items, label):
    return next(item for item in items if item.label == label)


def fixture(case_id):
    return next(c for c in suitability_pilot_cases() if c.case_id == case_id)


def app(case_id="gov-policy"):
    c = fixture(case_id)
    at = AppTest.from_string(PILOT, default_timeout=20).run()
    assert not at.exception
    widget(at.selectbox, "Control family").set_value(c.family).run()
    widget(at.selectbox, "Synthetic control package").set_value(case_id).run()
    assert not at.exception
    return at


def displayed_text(at):
    return "\n".join(item.value for collection in (at.markdown, at.caption, at.warning, at.info)
                     for item in collection)


def assert_provisional(at, expected):
    assert any(item.value == "Provisional outcome: " + expected for item in at.info)
    assert not any(item.value == "Provisional outcome: " + outcome
                   for item in at.info for outcome in ("Met", "Partially Met", "Risk Identified"))
    assert SPECIALIST_LIMIT in displayed_text(at)


def confirm_meaning(at, c):
    row = next(f for f in inspect_control(c).facts if f.direction == "review")
    widget(at.selectbox, "Interpretation to review").set_value(row.proposal.fact_id).run()
    widget(at.text_area, "Reason for this review").set_value(
        "Checked the quoted policy meaning and its source; suitability is not technical approval."
    ).run()
    widget(at.checkbox, MEANING_LABEL).check().run()
    widget(at.button, "Confirm this interpretation's meaning").click().run()
    assert not at.exception
    return row


def acknowledge_bundle(at):
    widget(at.text_area, "Reason for this review").set_value(
        "Reviewed the entire synthetic evidence package; specialist review is still required."
    ).run()
    widget(at.checkbox, "I reviewed all supplied documents and their disagreements, scope, dates and technical coverage.").check().run()
    widget(at.button, "Record complete-bundle review").click().run()
    assert not at.exception


def test_current_policy_is_cited_for_documentation_requirement_without_approval(monkeypatch):
    from sqlalchemy.engine import Engine

    def forbidden(*args, **kwargs):
        raise AssertionError("The synthetic suitability pilot cannot access a database.")

    monkeypatch.setattr(Engine, "connect", forbidden)
    c = fixture("gov-policy")
    at = app()
    assert c.evaluator is None and {d.evidence_kind for d in c.documents} == {"policy"}
    assert_provisional(at, "Needs Review")
    assert "m3d_current_review" not in at.session_state
    assert not any(i.label == "Confirm displayed supporting interpretations" for i in at.button)
    assert not at.get("file_uploader")
    assert widget(at.button, "Confirm this interpretation's meaning").disabled
    text = displayed_text(at)
    assert c.requirement.evidence_expectation.version in text
    assert "policy" in text and "sufficiency not evaluated" in text
    for p in c.proposals:
        assert any(p.quote in i.value for i in at.code)
        assert any(p.location in i.value for i in at.caption)


@pytest.mark.parametrize("case_id,gap", [("vm-policy-only", "kind"), ("vm-unrelated", "relevance")])
def test_operational_or_unrelated_evidence_retains_quotes_but_does_not_become_pertinent(case_id, gap):
    c = fixture(case_id)
    at = app(case_id)
    assert_provisional(at, "Evidence Missing")
    assert not inspect_control(c).eligible_source_fingerprints
    assert any(gap in item.value.casefold() for item in at.warning)
    assert not any(item.label == "Confirm displayed supporting interpretations" for item in at.button)
    for d in c.documents:
        assert any(d.content.decode() in i.value for i in at.code) or any(
            line in i.value for line in d.content.decode().splitlines() for i in at.code
        )
    acknowledge_bundle(at)
    assert_provisional(at, "Evidence Missing")


def test_policy_documentation_missing_source_stays_missing_after_acknowledgment():
    at = app("gov-missing")
    assert_provisional(at, "Evidence Missing")
    assert not any(i.label == "Confirm this interpretation's meaning" for i in at.button)
    acknowledge_bundle(at)
    assert_provisional(at, "Evidence Missing")
    assert not at.session_state["m3d_current_review"][1].fact_reviews


def test_policy_meaning_confirmation_and_bundle_review_cannot_approve_documentation_control():
    c = fixture("gov-policy")
    at = app()
    row = confirm_meaning(at, c)
    state = at.session_state["m3d_current_review"][1]
    assert len(state.fact_reviews) == 1 and state.fact_reviews[0].fact_fingerprint == row.fingerprint
    assert state.events[-1].kind == "meaning"
    assert state.bundle_review is None and not state.signal_dispositions
    assert_provisional(at, "Needs Review")
    acknowledge_bundle(at)
    assert_provisional(at, "Needs Review")
    assert any(row.proposal.quote in i.value for i in at.code)


@pytest.mark.parametrize("mutation", ["accepted_kinds", "expectation_version", "relevance_reason", "policy"])
def test_suitability_metadata_change_invalidates_active_review_and_checkbox(monkeypatch, mutation):
    import src.control_assurance_ui as ui

    cases = suitability_pilot_cases()
    monkeypatch.setattr(ui, "suitability_pilot_cases", lambda: cases)
    original = fixture("gov-policy")
    at = app()
    confirm_meaning(at, original)
    assert "m3d_current_review" in at.session_state
    changed = original
    if mutation == "accepted_kinds":
        expectation = replace(original.requirement.evidence_expectation, accepted_kinds=("configuration", "test"))
        changed = replace(original, requirement=replace(original.requirement, evidence_expectation=expectation))
    elif mutation == "expectation_version":
        expectation = replace(original.requirement.evidence_expectation, version="2026.2")
        changed = replace(original, requirement=replace(original.requirement, evidence_expectation=expectation))
    elif mutation == "relevance_reason":
        binding = replace(original.relevance[0], rationale="A revised declared relevance reason requires fresh analyst review.")
        changed = replace(original, relevance=(binding,) + original.relevance[1:])
    else:
        changed = replace(original, requirement=replace(original.requirement, policy_version="2026.2"))
    cases = tuple(changed if c.case_id == changed.case_id else c for c in cases)
    at.run()
    assert not at.exception and "m3d_current_review" not in at.session_state
    assert not widget(at.checkbox, MEANING_LABEL).value
    assert widget(at.button, "Confirm this interpretation's meaning").disabled
    assert SPECIALIST_LIMIT in displayed_text(at)
    assert any(item.value in ("Provisional outcome: Needs Review", "Provisional outcome: Evidence Missing") for item in at.info)


@pytest.mark.parametrize("missing", ["expectation", "relevance"])
def test_missing_explicit_suitability_metadata_is_a_visible_gap(monkeypatch, missing):
    import src.control_assurance_ui as ui

    c = fixture("gov-policy")
    changed = (replace(c, requirement=replace(c.requirement, evidence_expectation=None))
               if missing == "expectation" else replace(c, relevance=()))
    monkeypatch.setattr(ui, "suitability_pilot_cases", lambda: (changed,))
    at = app()
    assert_provisional(at, "Evidence Missing")
    assert any(missing in item.value.casefold() for item in at.warning)
    assert any(c.proposals[0].quote in item.value for item in at.code)


def test_case_switch_discards_policy_documentation_meaning_review():
    at = app()
    confirm_meaning(at, fixture("gov-policy"))
    widget(at.selectbox, "Synthetic control package").set_value("gov-missing").run()
    assert not at.exception and "m3d_current_review" not in at.session_state
    assert_provisional(at, "Evidence Missing")
    widget(at.selectbox, "Synthetic control package").set_value("gov-policy").run()
    assert not at.exception and "m3d_current_review" not in at.session_state
    assert widget(at.button, "Confirm this interpretation's meaning").disabled


def test_malformed_relevance_reason_remains_a_visible_gap_without_crashing(monkeypatch):
    import src.control_assurance_ui as ui

    c = fixture("gov-policy")
    changed = replace(c, relevance=(replace(c.relevance[0], rationale=None),))
    monkeypatch.setattr(ui, "suitability_pilot_cases", lambda: (changed,))
    at = app()
    assert_provisional(at, "Evidence Missing")
    assert any("relevance" in item.value.casefold() for item in at.warning)
    assert any("not supplied" in item.value for item in at.caption)
    assert any(c.proposals[0].quote in item.value for item in at.code)
