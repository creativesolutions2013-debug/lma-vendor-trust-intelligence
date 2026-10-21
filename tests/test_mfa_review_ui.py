"""Exercise the actual synthetic Streamlit surface without importing app DB setup."""
from pathlib import Path
import ast
from dataclasses import replace

import pytest
from streamlit.testing.v1 import AppTest

from src.mfa_analyst_review import inspect_review
from src.evidence_fact_validation import bind_evidence, fact_fingerprint
from src.evidence_intelligence_m3 import Citation
from src.mfa_review_pilot import pilot_cases


PILOT = "from src.mfa_review_ui import render_mfa_review_pilot\nrender_mfa_review_pilot(actor_label='Synthetic analyst')"


def widget(items, label):
    return next(item for item in items if item.label == label)


def app():
    result = AppTest.from_string(PILOT, default_timeout=15).run()
    assert not result.exception
    return result


def reviewed_support(at):
    at.text_area[0].set_value("Checked every displayed interpretation against the full synthetic source context.")
    widget(at.checkbox, "I checked every displayed interpretation against its full sources and confirm its meaning, not just its quotation.").check().run()
    widget(at.button, "Confirm displayed supporting interpretations").click().run()
    assert not at.exception
    return at


def test_default_is_read_only_and_confirmation_has_no_implicit_reviews(monkeypatch):
    from sqlalchemy.engine import Engine

    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic review cannot access a database.")

    monkeypatch.setattr(Engine, "connect", forbidden)
    at = app()
    assert any("Provisional outcome: Needs Review" in item.value for item in at.info)
    assert any("Customer requirement:" in item.value for item in at.markdown)
    assert any("Threshold:" in item.value for item in at.markdown)
    assert any("Recommended next action:" in item.value for item in at.markdown)
    assert "m3c1_current_review" not in at.session_state
    assert widget(at.button, "Confirm displayed supporting interpretations").disabled
    assert not at.get("file_uploader")


def test_explicit_group_confirmation_creates_seven_bound_reviews_but_no_exception_or_bundle_ack():
    at = reviewed_support(app())
    state = at.session_state["m3c1_current_review"][1]
    case = next(case for case in pilot_cases() if case.case_id == "strong")
    assert len(state.fact_reviews) == 7
    assert not state.signal_dispositions and state.bundle_review is None
    assert len(state.events) == 1 and len(state.events[0].fact_fingerprints) == 7
    assert inspect_review(case, state).validation.evaluation.outcome == "Needs Review"
    assert widget(at.button, "Confirm displayed supporting interpretations").disabled


def test_positive_ui_keeps_signal_triage_and_complete_source_review_separate():
    at = reviewed_support(app())
    case = next(case for case in pilot_cases() if case.case_id == "strong")
    signals = inspect_review(case).validation.signals
    for signal in signals:
        widget(at.selectbox, "Source signal").set_value(signal.signal_id).run()
        widget(at.radio, "After checking the full context").set_value("Not material to this requirement")
        at.text_area[0].set_value("The full source expressly found no exceptions in the complete tested inventory.")
        widget(at.button, "Record this signal triage").click().run()
        assert not at.exception
        assert any("Provisional outcome: Needs Review" in item.value for item in at.info)
    widget(at.checkbox, "I reviewed all supplied documents and their disagreements, scope, dates, account and recovery paths.").check().run()
    widget(at.button, "Record complete-bundle review").click().run()
    assert not at.exception
    state = at.session_state["m3c1_current_review"][1]
    result = inspect_review(case, state).validation
    assert result.evaluation.outcome == "Met"
    assert result.provisional and result.review_required and result.evaluation.provisional
    assert len(state.events) == 4  # One group + two separate triages + one bundle acknowledgment.
    assert any("Provisional outcome: Met" in item.value for item in at.info)


@pytest.mark.parametrize("case_id,phrase", [
    ("bypass", "Potential control exception"),
    ("reported", "Vendor-reported exception"),
    ("conflict", "Conflicting source statements"),
    ("stale", "Evidence date needs review"),
    ("coverage_gap", "scope"),
    ("scope_mismatch", "scope"),
])
def test_case_switch_drops_prior_confirmation_and_retains_important_issue(case_id, phrase):
    at = reviewed_support(app())
    widget(at.selectbox, "Synthetic evidence package").set_value(case_id).run()
    assert not at.exception
    assert any("Provisional outcome: Needs Review" in item.value for item in at.info)
    assert any(phrase.casefold() in item.value.casefold() for item in at.warning)
    if any(item.label == "Confirm displayed supporting interpretations" for item in at.button):
        assert widget(at.button, "Confirm displayed supporting interpretations").disabled


def test_uncertain_method_is_a_gap_and_does_not_offer_exception_confirmation():
    at = app()
    widget(at.selectbox, "Synthetic evidence package").set_value("unknown").run()
    assert not at.exception
    assert not any("Vendor-reported exception" in item.value for item in at.warning)
    assert not any(item.label == "Confirm this exception's meaning" for item in at.button)
    assert not any(item.label == "Confirm displayed supporting interpretations" for item in at.button)


def test_switching_away_and_back_requires_fresh_confirmation_instead_of_restoring_an_old_session():
    at = reviewed_support(app())
    widget(at.selectbox, "Synthetic evidence package").set_value("bypass").run()
    assert "m3c1_current_review" not in at.session_state
    widget(at.selectbox, "Synthetic evidence package").set_value("strong").run()
    assert not at.exception
    assert "m3c1_current_review" not in at.session_state
    assert widget(at.button, "Confirm displayed supporting interpretations").disabled


@pytest.mark.parametrize("case_id,outcome,title", [
    ("bypass", "Risk Identified", "Evidence-backed threshold failure"),
    ("reported", "Needs Review", "Vendor-reported exception"),
])
def test_explicit_exception_meaning_keeps_configuration_and_vendor_assertion_distinct(case_id, outcome, title):
    at = app()
    widget(at.selectbox, "Synthetic evidence package").set_value(case_id).run()
    at.text_area[0].set_value("I checked the source and its explicit emergency-administrator exception.")
    widget(at.checkbox, "I checked this exception's meaning and affected population in the full source context.").check().run()
    widget(at.button, "Confirm this exception's meaning").click().run()
    assert not at.exception
    assert any(f"Provisional outcome: {outcome}" in item.value for item in at.info)
    assert any(title in item.value for item in at.warning)
    state = at.session_state["m3c1_current_review"][1]
    assert len(state.fact_reviews) == 1 and state.bundle_review is None
    assert widget(at.button, "Confirm this exception's meaning").disabled


def test_selecting_a_new_signal_defaults_to_retaining_potential_materiality():
    at = app()
    case = next(case for case in pilot_cases() if case.case_id == "strong")
    signals = inspect_review(case).validation.signals
    widget(at.radio, "After checking the full context").set_value("Not material to this requirement").run()
    widget(at.selectbox, "Source signal").set_value(signals[1].signal_id).run()
    assert not at.exception
    assert widget(at.radio, "After checking the full context").value == "Retain as material or potentially material"


def test_a_method_that_ceases_to_be_supporting_remains_available_for_separate_exception_review(monkeypatch):
    import src.mfa_review_ui as ui

    case = next(case for case in pilot_cases() if case.case_id == "strong")
    method = next(item for item in case.proposals if item.fact.dimension == "method")
    source = replace(case.documents[1], document_id="weak-active-path", filename="weak-active-path.txt",
                     content=b"SYNTHETIC active administrator path requires an SMS code plus password and issues a production session.")
    bound = bind_evidence(source)
    weak = replace(method, source_fingerprint=bound.fingerprint, location="Line 1",
                   fact=replace(method.fact, value="sms", citation=Citation("weak-active-path:1", source.content.decode()),
                                origin_bound=False, verifier_bound=False))
    changed = replace(case, documents=case.documents + (source,),
                      proposals=tuple(weak if item.fact_id == method.fact_id else item for item in case.proposals))
    monkeypatch.setattr(ui, "pilot_cases", lambda: (changed,))
    at = app()
    assert method.fact_id in widget(at.selectbox, "Exception interpretation").options
    assert any(item.label == "Confirm this exception's meaning" for item in at.button)


def test_integration_is_in_evidence_center_and_available_without_real_vendor_data():
    tree = ast.parse((Path(__file__).parents[1] / "app.py").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_evidence")
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
    pilot = next(node for node in calls if isinstance(node.func, ast.Name) and node.func.id == "render_control_assurance_pilot")
    vendor_gate = next(node for node in function.body if isinstance(node, ast.If)
                       and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.operand, ast.Name)
                       and node.test.operand.id == "vendors")
    assert pilot.lineno < vendor_gate.lineno
    assert not pilot.args  # It accepts no vendor, uploaded evidence, session or governed assessment.


@pytest.mark.parametrize("active", [None, False, True], ids=["unknown", "disabled", "enabled"])
def test_configuration_method_requires_affirmative_active_use_before_ui_can_confirm_failure(monkeypatch, active):
    import src.mfa_review_ui as ui

    strong = next(case for case in pilot_cases() if case.case_id == "strong")
    method = next(item for item in strong.proposals if item.fact.dimension == "method")
    activation = {None: "The configuration does not establish whether this path is enabled.",
                  False: "The path is disabled and cannot issue a session.",
                  True: "The path is enabled and can issue an administrator session."}[active]
    source = replace(strong.documents[1], document_id="activation-review", filename="activation-review.txt",
                     content=("SYNTHETIC configuration records an implemented SMS-code-plus-password administrator path. "
                              + activation).encode())
    bound = bind_evidence(source)
    candidate = replace(method, source_fingerprint=bound.fingerprint, location="Line 1",
                        fact=replace(method.fact, value="sms", active=active,
                                     citation=Citation("activation-review:1", source.content.decode()),
                                     origin_bound=False, verifier_bound=False))
    case = replace(strong, documents=(source,), proposals=(candidate,), supporting_fact_ids=())
    monkeypatch.setattr(ui, "pilot_cases", lambda: (case,))
    at = app()
    assert any("Provisional outcome: Needs Review" in item.value for item in at.info)
    assert any(item.value == source.content.decode() for item in at.code)
    if active is True:
        at.text_area[0].set_value("I checked the cited configuration and its explicitly enabled administrator path.")
        widget(at.checkbox, "I checked this exception's meaning and affected population in the full source context.").check().run()
        widget(at.button, "Confirm this exception's meaning").click().run()
        assert not at.exception
        assert any("Provisional outcome: Risk Identified" in item.value for item in at.info)
        assert any("Evidence-backed threshold failure" in item.value for item in at.warning)
        state = at.session_state["m3c1_current_review"][1]
        assert inspect_review(case, state).validation.evaluation.provisional
    else:
        assert not any(item.label == "Confirm this exception's meaning" for item in at.button)
        assert not any("Evidence-backed threshold failure" in item.value for item in at.warning)
        expected_word = "activation" if active is None else "disabled"
        assert any(expected_word in item.value.casefold() for item in at.warning)
        at.text_area[0].set_value("The source leaves activation unresolved or explicitly disables the path; no current failure is verified.")
        widget(at.checkbox, "I reviewed all supplied documents and their disagreements, scope, dates, account and recovery paths.").check().run()
        widget(at.button, "Record complete-bundle review").click().run()
        assert not at.exception
        assert any("Provisional outcome: Needs Review" in item.value for item in at.info)
        state = at.session_state["m3c1_current_review"][1]
        assert not state.fact_reviews
        assert not any(item.status == "adverse" for item in inspect_review(case, state).validation.evaluation.facts)


def challenge(at, fact_id, decision):
    at.text_area[0].set_value("The source does not establish complete emergency-administrator coverage; do not accept this interpretation.")
    widget(at.selectbox, "Supporting interpretation to challenge").set_value(fact_id).run()
    widget(at.radio, "Challenge disposition").set_value(decision).run()
    widget(at.button, "Record supporting interpretation challenge").click().run()
    assert not at.exception
    return at


def finish_strong_signal_and_bundle_reviews(at, case):
    # Explicit fixture-specific human dispositions, not automatic semantic triage.
    for signal in inspect_review(case).validation.signals:
        widget(at.selectbox, "Source signal").set_value(signal.signal_id).run()
        widget(at.radio, "After checking the full context").set_value("Not material to this requirement")
        at.text_area[0].set_value("The cited source expressly reports no exemptions or exceptions in its complete tested inventory.")
        widget(at.button, "Record this signal triage").click().run()
        assert not at.exception
    widget(at.checkbox, "I reviewed all supplied documents and their disagreements, scope, dates, account and recovery paths.").check().run()
    widget(at.button, "Record complete-bundle review").click().run()
    assert not at.exception
    return at


@pytest.mark.parametrize("decision", ["Unsupported", "Ambiguous"])
def test_challenge_before_grouping_excludes_one_fact_without_accepting_it_with_the_remaining_group(decision):
    case = next(case for case in pilot_cases() if case.case_id == "strong")
    target = next(item for item in case.proposals if item.fact.dimension == "enforcement")
    at = challenge(app(), target.fact_id, decision)
    state = at.session_state["m3c1_current_review"][1]
    assert len(state.fact_reviews) == len(state.events) == 1
    assert state.fact_reviews[0].fact_fingerprint == fact_fingerprint(target)
    assert state.fact_reviews[0].decision == decision.casefold()
    assert any("challeng" in item.value.casefold() for item in at.warning)
    assert any(item.value == target.fact.citation.quote for item in at.code)
    assert fact_fingerprint(target) not in inspect_review(case, state).supporting_fingerprints
    at = reviewed_support(at)
    state = at.session_state["m3c1_current_review"][1]
    assert len(state.fact_reviews) == 7
    assert len(state.events[-1].fact_fingerprints) == 6
    assert fact_fingerprint(target) not in state.events[-1].fact_fingerprints
    at = finish_strong_signal_and_bundle_reviews(at, case)
    state = at.session_state["m3c1_current_review"][1]
    assert inspect_review(case, state).validation.evaluation.outcome == "Needs Review"
    assert any("Provisional outcome: Needs Review" in item.value for item in at.info)
    assert next(review for review in state.fact_reviews if review.fact_fingerprint == fact_fingerprint(target)).decision == decision.casefold()


@pytest.mark.parametrize("decision", ["Unsupported", "Ambiguous"])
def test_challenge_after_provisional_met_supersedes_the_group_without_erasing_history(decision):
    case = next(case for case in pilot_cases() if case.case_id == "strong")
    target = next(item for item in case.proposals if item.fact.dimension == "enforcement")
    at = finish_strong_signal_and_bundle_reviews(reviewed_support(app()), case)
    before = at.session_state["m3c1_current_review"][1]
    assert inspect_review(case, before).validation.evaluation.outcome == "Met"
    assert len(before.events) == 4
    at = challenge(at, target.fact_id, decision)
    state = at.session_state["m3c1_current_review"][1]
    assert state.events[:-1] == before.events
    assert len(state.events) == 5
    assert state.bundle_review is None
    assert state.signal_dispositions == before.signal_dispositions
    assert len(state.fact_reviews) == 7
    assert next(review for review in state.fact_reviews if review.fact_fingerprint == fact_fingerprint(target)).decision == decision.casefold()
    assert inspect_review(case, state).validation.evaluation.outcome == "Needs Review"
    assert any("Provisional outcome: Needs Review" in item.value for item in at.info)
    assert any("challeng" in item.value.casefold() for item in at.warning)
    widget(at.checkbox, "I reviewed all supplied documents and their disagreements, scope, dates, account and recovery paths.").check().run()
    widget(at.button, "Record complete-bundle review").click().run()
    assert not at.exception
    state = at.session_state["m3c1_current_review"][1]
    assert inspect_review(case, state).validation.evaluation.outcome == "Needs Review"
    assert any("Provisional outcome: Needs Review" in item.value for item in at.info)


def test_every_grouped_interpretation_exposes_its_exact_quote_alongside_its_source():
    case = next(case for case in pilot_cases() if case.case_id == "strong")
    at = app()
    codes = {item.value for item in at.code}
    captions = [item.value for item in at.caption]
    for interpretation in inspect_review(case).supporting:
        assert interpretation.quote in codes
        assert any(interpretation.filename in caption and interpretation.location in caption for caption in captions)
