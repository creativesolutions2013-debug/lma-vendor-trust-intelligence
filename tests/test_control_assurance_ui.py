"""Drive actual widgets and count scripted interactions, not analyst time."""
from dataclasses import replace

import pytest
from streamlit.testing.v1 import AppTest

from src.control_assurance import inspect_control
from src.control_assurance_pilot import control_pilot_cases

PILOT = "from src.control_assurance_ui import render_control_assurance_pilot\nrender_control_assurance_pilot(actor_label='Synthetic analyst')"


def widget(items, label):
    return next(i for i in items if i.label == label)


def app():
    at = AppTest.from_string(PILOT, default_timeout=20).run()
    assert not at.exception
    return at


class InteractionCounter:
    def __init__(self, at):
        self.at, self.actions = at, []

    def set(self, kind, label, value):
        widget(getattr(self.at, kind), label).set_value(value).run()
        self.actions.append((kind, label))
        assert not self.at.exception

    def click(self, label):
        widget(self.at.button, label).click().run()
        self.actions.append(("button", label))
        assert not self.at.exception


def family(at, name):
    widget(at.selectbox, "Control family").set_value(name).run()
    assert not at.exception
    return at


@pytest.mark.parametrize("name", ["Privileged MFA", "Transport encryption (TLS)", "Disaster-recovery testing"])
def test_all_three_families_share_read_only_exception_first_summary(name, monkeypatch):
    from sqlalchemy.engine import Engine

    def forbidden(*args, **kwargs):
        raise AssertionError("The synthetic review must not access a database.")

    monkeypatch.setattr(Engine, "connect", forbidden)
    at = family(app(), name)
    assert any("Evidence-Based Control Assurance" in i.value for i in at.subheader)
    assert any("Customer requirement:" in i.value for i in at.markdown)
    assert any("Threshold:" in i.value for i in at.markdown)
    assert any("Provisional outcome: Needs Review" in i.value for i in at.info)
    assert widget(at.button, "Confirm displayed supporting interpretations").disabled
    assert not at.get("file_uploader") and "m3d_current_review" not in at.session_state


@pytest.mark.parametrize("name,key,expected_widgets,expected_submissions,baseline", [
    ("Privileged MFA", "strong", 12, 4, 10),
    ("Transport encryption (TLS)", "tls-strong", 12, 4, 9),
    ("Disaster-recovery testing", "dr-strong", 6, 2, 5),
])
def test_actual_positive_widget_paths_and_modeled_per_fact_baseline(name, key, expected_widgets, expected_submissions, baseline):
    at = app()
    c = InteractionCounter(at)
    c.set("selectbox", "Control family", name)
    c.set("text_area", "Reason for this review", "Checked all presented meanings and the complete synthetic source inventory.")
    c.set("checkbox", "I checked every displayed interpretation against its full sources and confirm its meaning, not just its quotation.", True)
    c.click("Confirm displayed supporting interpretations")
    assert any("Provisional outcome: Needs Review" in i.value for i in at.info)
    if name == "Privileged MFA":
        from src.mfa_analyst_review import inspect_review
        from src.mfa_review_pilot import pilot_cases
        case = next(c for c in pilot_cases() if c.case_id == key)
        signals = inspect_review(case).validation.signals
        bundle_label = "I reviewed all supplied documents and their disagreements, scope, dates, account and recovery paths."
        state_key = "m3c1_current_review"
    else:
        case = next(c for c in control_pilot_cases() if c.case_id == key)
        signals = inspect_control(case).signals
        bundle_label = "I reviewed all supplied documents and their disagreements, scope, dates and technical coverage."
        state_key = "m3d_current_review"
    for s in signals:
        c.set("selectbox", "Source signal", s.signal_id)
        c.set("radio", "After checking the full context", "Not material to this requirement")
        c.click("Record this signal triage")
    c.set("checkbox", bundle_label, True)
    c.click("Record complete-bundle review")
    assert any("Provisional outcome: Met" in i.value for i in at.info)
    state = at.session_state[state_key][1]
    assert len(state.events) == expected_submissions
    assert len(c.actions) == expected_widgets
    assert baseline == len(case.proposals) + len(signals) + 1
    print(f"{key}: {len(c.actions)} widget interactions; {len(state.events)} decisions; modeled M3B per-fact baseline {baseline}")


@pytest.mark.parametrize("name,key,expected", [
    ("Transport encryption (TLS)", "tls-exception", "Risk Identified"),
    ("Transport encryption (TLS)", "tls-reported", "Needs Review"),
    ("Disaster-recovery testing", "dr-exception", "Risk Identified"),
    ("Disaster-recovery testing", "dr-reported", "Needs Review"),
])
def test_exception_paths_remain_visible_and_require_separate_meaning(name, key, expected):
    at = app()
    c = InteractionCounter(at)
    c.set("selectbox", "Control family", name)
    c.set("selectbox", "Synthetic control package", key)
    assert any("exception" in i.value.casefold() for i in at.warning)
    c.set("text_area", "Reason for this review", "Checked the complete synthetic source and the separate technical exception.")
    c.set("checkbox", "I checked every displayed interpretation against its full sources and confirm its meaning, not just its quotation.", True)
    c.click("Confirm displayed supporting interpretations")
    assert any("Provisional outcome: Needs Review" in i.value for i in at.info)
    c.set("checkbox", "I checked this exception's meaning and affected scope in the full source context.", True)
    c.click("Confirm this exception's meaning")
    assert any("Provisional outcome: " + expected in i.value for i in at.info)
    case = next(c for c in control_pilot_cases() if c.case_id == key)
    signals = inspect_control(case).signals
    for s in signals:
        c.set("selectbox", "Source signal", s.signal_id)
        # Deliberately wrong dismissal cannot erase the distinct adverse fact.
        c.set("radio", "After checking the full context", "Not material to this requirement")
        c.click("Record this signal triage")
    c.set("checkbox", "I reviewed all supplied documents and their disagreements, scope, dates and technical coverage.", True)
    c.click("Record complete-bundle review")
    state = at.session_state["m3d_current_review"][1]
    assert inspect_control(case, state).outcome == expected
    assert len(state.events) == 3 + len(signals)
    assert len(c.actions) == 9 + 3 * len(signals)
    print(f"{key}: {len(c.actions)} widget interactions; {len(state.events)} decisions; "
          f"modeled per-fact baseline {len(case.proposals) + len(signals) + 1}")


def test_case_and_family_switch_require_fresh_confirmation():
    at = family(app(), "Transport encryption (TLS)")
    at.text_area[0].set_value("Source checked.")
    widget(at.checkbox, "I checked every displayed interpretation against its full sources and confirm its meaning, not just its quotation.").check().run()
    widget(at.button, "Confirm displayed supporting interpretations").click().run()
    assert "m3d_current_review" in at.session_state
    widget(at.selectbox, "Synthetic control package").set_value("tls-exception").run()
    assert "m3d_current_review" not in at.session_state
    family(at, "Disaster-recovery testing")
    assert "m3d_current_review" not in at.session_state
    assert widget(at.button, "Confirm displayed supporting interpretations").disabled


def test_challenge_after_met_preserves_history_and_blocks_positive_again():
    from tests.test_control_assurance import CASES, review_all
    at = family(app(), "Disaster-recovery testing")
    case = CASES["dr-strong"]
    # Seed via explicit backend actions to focus this UI regression on correction.
    prefix = f"m3d:Synthetic analyst:dr-strong:{inspect_control(case).bundle_fingerprint}"
    at.session_state["m3d_current_review"] = (prefix, review_all(case))
    at.run()
    assert any("Provisional outcome: Met" in i.value for i in at.info)
    at.text_area[0].set_value("The quoted record does not establish this interpretation.").run()
    widget(at.button, "Record interpretation challenge").click().run()
    assert not at.exception
    state = at.session_state["m3d_current_review"][1]
    assert state.events[-1].kind == "challenge_unsupported"
    assert not state.bundle_review and inspect_control(case, state).outcome != "Met"
    assert len(state.events) == 3


def test_each_grouped_meaning_has_its_own_exact_quote_and_source_location():
    at = family(app(), "Transport encryption (TLS)")
    case = next(c for c in control_pilot_cases() if c.case_id == "tls-strong")
    for p in case.proposals:
        assert any(p.quote == i.value for i in at.code)
        assert any(p.location in i.value for i in at.caption)


def test_changed_policy_invalidates_saved_ui_session(monkeypatch):
    import src.control_assurance_ui as ui
    cases = control_pilot_cases()
    monkeypatch.setattr(ui, "control_pilot_cases", lambda: cases)
    at = family(app(), "Disaster-recovery testing")
    at.text_area[0].set_value("Source checked.")
    widget(at.checkbox, "I checked every displayed interpretation against its full sources and confirm its meaning, not just its quotation.").check().run()
    widget(at.button, "Confirm displayed supporting interpretations").click().run()
    cases = tuple(replace(c, requirement=replace(c.requirement, policy_version="2026.2")) for c in cases)
    at.run()
    assert not at.exception and "m3d_current_review" not in at.session_state
    assert widget(at.button, "Confirm displayed supporting interpretations").disabled
