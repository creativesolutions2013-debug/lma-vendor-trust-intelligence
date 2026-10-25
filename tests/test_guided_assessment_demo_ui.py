"""Synthetic browser journeys over the real worklist, with live effects denied."""
import builtins
import json
from pathlib import Path

import pytest
from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PILOT = (
    "from src.guided_assessment_demo_ui import render_guided_assessment_demo\n"
    "render_guided_assessment_demo()"
)


def widget(items, label):
    return next(item for item in items if item.label == label)


def shown(at):
    return "\n".join(str(item.value) for collection in (
        at.title, at.header, at.subheader, at.markdown, at.caption, at.info,
        at.warning, at.success, at.error, at.text,
    ) for item in collection)


def run(at):
    at.run()
    assert not at.exception, [(item.message, item.stack_trace) for item in at.exception]
    return at


def app(*, actual=False):
    instance = (AppTest.from_file(str(ROOT / "app.py"), default_timeout=35) if actual
                else AppTest.from_string(PILOT, default_timeout=35))
    return run(instance)


def step(at, name):
    widget(at.radio, "Demo step").set_value(name)
    return run(at)


def model_for(at):
    from src.guided_assessment_demo import build_demo
    return build_demo(
        scenario_id=at.session_state["guided_demo:scenario"],
        evidence_received=at.session_state["guided_demo:received"],
        risk_profile=at.session_state["guided_demo:risk_profile"],
    )


def worklist_table(at):
    return next(item.value for item in at.dataframe
                if {"Requirement", "Provisional outcome", "Next action"} <= set(item.value.columns))


def review(at, requirement_id, action, rationale):
    step(at, "Analyst Review")
    widget(at.selectbox, "Review requirement").set_value(requirement_id)
    run(at)
    widget(at.radio, "Simulated analyst action").set_value(action)
    widget(at.text_area, "Review rationale").set_value(rationale)
    run(at)
    widget(at.button, "Record simulated review").click()
    return run(at)


@pytest.fixture
def no_live_effects(monkeypatch):
    """Fail on actual entry-point imports as well as effects hidden in services."""
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session
    import requests
    import src.assessment_worklist as worklist
    import src.control_assurance as assurance
    import src.evidence_ai as ai
    import src.evidence_intelligence_m2 as ai_requirements
    import src.scoring as scoring

    def forbidden(*args, **kwargs):
        raise AssertionError("The guided synthetic demo must not access live services or governed state.")

    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("DEV_USER_ROLE", "Admin")
    monkeypatch.setattr(Engine, "connect", forbidden)
    for method in ("add", "add_all", "delete", "commit", "flush"):
        monkeypatch.setattr(Session, method, forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(ai, "extract_soc2_metadata", forbidden)
    monkeypatch.setattr(ai_requirements, "evaluate_ai_requirements", forbidden)
    monkeypatch.setattr(assurance, "record_control_review", forbidden)
    monkeypatch.setattr(worklist, "record_need_review", forbidden)
    monkeypatch.setattr(scoring, "calculate_residual_risk", forbidden)
    monkeypatch.setattr(scoring, "evaluate_residual_risk", forbidden)

    original_import = builtins.__import__
    blocked = {
        "src.db", "src.db_health", "src.storage", "src.seed", "src.audit",
        "src.control_claim_service", "src.control_disposition_service",
        "src.residual_risk_activation_service", "src.residual_risk_activation_execution_service",
        "src.revalidation_case_service",
    }

    def import_without_live_services(name, *args, **kwargs):
        if name in blocked:
            raise AssertionError("Live service imported in guided demo: " + name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_live_services)


@pytest.fixture
def downloads(monkeypatch):
    """Capture Streamlit's real download bytes in memory; never fetch a URL."""
    captured = []
    original = MemoryMediaFileStorage.load_and_get_id

    def load(self, path_or_data, mimetype, kind, filename=None):
        if mimetype == "application/json":
            assert isinstance(path_or_data, bytes)
            captured.append((path_or_data, filename))
        return original(self, path_or_data, mimetype, kind, filename)

    monkeypatch.setattr(MemoryMediaFileStorage, "load_and_get_id", load)
    return captured


def test_actual_app_walkthrough_uses_no_live_services_and_downloads_current_report(no_live_effects, downloads):
    from src.guided_assessment_demo import report_bytes

    at = app(actual=True)
    assert widget(at.sidebar.radio, "Navigation").value == "Guided Assessment Demo"
    assert "synthetic" in shown(at).lower()
    assert "provisional" in shown(at).lower()
    assert "Acme" in shown(at)
    assert not at.get("file_uploader")

    widget(at.button, "Continue").click()
    run(at)
    assert widget(at.radio, "Demo step").value == "Evidence"
    initial = model_for(at)
    assert len(initial.worklist.rows) >= 4
    for document in initial.documents + initial.context_documents:
        assert document.document.filename in shown(at)
        assert all(any(part.text in block.value for block in at.code)
                   for part in document.document.segments)

    step(at, "Assess")
    rows = worklist_table(at)
    assert list(rows["Requirement"]) == [row.requirement_id for row in initial.worklist.rows]
    assert list(rows["Provisional outcome"]) == [row.outcome for row in initial.worklist.rows]

    step(at, "Questions")
    assert len(initial.worklist.requests) == 1
    assert widget(at.metric, "Draft vendor requests").value == "1"
    assert widget(at.metric, "Ask-everything baseline").value == "4"
    assert widget(at.metric, "Needs awaiting analyst validation").value == "4"
    assert initial.worklist.requests[0].question in shown(at)
    widget(at.button, "Replay new evidence received").click()
    run(at)
    received = model_for(at)
    assert at.session_state["guided_demo:received"] is True
    assert received.worklist.requests == ()
    assert widget(at.metric, "Draft vendor requests").value == "0"
    assert widget(at.metric, "Ask-everything baseline").value == "4"
    assert widget(at.metric, "Needs awaiting analyst validation").value == "5"
    assert "not resolved evidence or measured real-world time savings" in shown(at)
    assert initial.worklist.requests[0].question not in shown(at)
    assert all(match.status != "Supported by reviewed evidence"
               for row in received.worklist.rows for match in row.need_matches)

    requirement_id = received.worklist.rows[0].requirement_id
    review(at, requirement_id, "Create Finding", "Source scope remains unresolved; retain a simulated finding.")
    assert len(at.session_state["guided_demo:actions"]) == 1
    step(at, "Results")
    assert len(at.get("download_button")) == 1
    assert at.get("download_button")[0].proto.label == "Download synthetic assessment report"
    assert downloads
    assert downloads[-1][0] == report_bytes(received, at.session_state["guided_demo:actions"])
    payload = json.loads(downloads[-1][0])
    assert payload["synthetic"] is True and payload["provisional"] is True
    assert payload["authoritative"] is False
    assert "Source scope remains unresolved" in downloads[-1][0].decode()
    for row in received.worklist.rows:
        assert row.requirement_id in downloads[-1][0].decode()
    assert "illustrative" in shown(at).lower()


def test_customer_thresholds_exact_sources_and_no_specialist_requirement_remain_visible(no_live_effects):
    at = app()
    model = model_for(at)
    step(at, "Assess")
    fallback = next(row for row in model.worklist.rows if row.specialist_available is False)
    widget(at.selectbox, "Requirement detail").set_value(fallback.requirement_id)
    run(at)
    assert fallback.threshold in shown(at)
    assert fallback.requirement.customer_policy_id in shown(at)
    assert fallback.requirement.policy_version in shown(at)
    assert "Specialist evaluation unavailable" in shown(at)
    assert fallback.outcome == "Needs Review"
    for bound in fallback.review.evidence:
        assert bound.document.filename in shown(at)
        assert all(any(part.text in block.value for block in at.code)
                   for part in bound.document.segments)


def test_policy_presence_does_not_turn_missing_operating_proof_into_failure_or_support(no_live_effects):
    at = app()
    model = model_for(at)
    dr = next(row for row in model.worklist.rows if row.control_id == "BCP-01")
    assert dr.review.evidence and all(bound.source.evidence_kind == "policy" for bound in dr.review.evidence)
    step(at, "Assess")
    widget(at.selectbox, "Requirement detail").set_value(dr.requirement_id)
    run(at)
    # The real evaluator retains a plan's policy evidence as Needs Review;
    # its missing operating fact is a separate evidence need, not a failure.
    assert dr.outcome == "Needs Review"
    assert "Provisional outcome: " + dr.outcome in shown(at)
    assert [match.status for match in dr.need_matches] == ["Missing or insufficient"]
    assert "Missing or insufficient" in shown(at)
    assert "Evidence Missing for this specific need" in shown(at)
    assert dr.threshold in shown(at)
    assert "gap" in shown(at).lower()
    assert not dr.review.bundle_review_valid


def test_tls_exception_survives_replay_and_accept_annotation(no_live_effects):
    at = app()
    widget(at.selectbox, "Demo scenario").set_value("exception")
    run(at)
    before = model_for(at)
    tls = next(row for row in before.worklist.rows if row.control_id == "ENC-01")
    assert tls.priority <= 1
    adverse = [fact for fact in tls.review.facts if fact.direction == "adverse"]
    assert adverse
    step(at, "Assess")
    widget(at.selectbox, "Requirement detail").set_value(tls.requirement_id)
    run(at)
    for fact in adverse:
        assert any(fact.proposal.quote in block.value for block in at.code)
    review(at, tls.requirement_id, "Accept", "Accept the provisional concern for discussion; no final approval.")
    step(at, "Questions")
    widget(at.button, "Replay new evidence received").click()
    run(at)
    current = model_for(at)
    current_tls = next(row for row in current.worklist.rows if row.control_id == "ENC-01")
    assert current_tls.outcome == tls.outcome != "Met"
    assert current_tls.priority == tls.priority
    assert [fact.fingerprint for fact in current_tls.review.facts if fact.direction == "adverse"] == [
        fact.fingerprint for fact in adverse]
    assert not any(fact.confirmed for fact in current_tls.review.facts)
    step(at, "Assess")
    widget(at.selectbox, "Requirement detail").set_value(tls.requirement_id)
    run(at)
    assert all(any(fact.proposal.quote in block.value for block in at.code) for fact in adverse)


@pytest.mark.parametrize("action", ["Accept", "Challenge", "Request Evidence", "Create Finding"])
def test_simulated_actions_require_reason_and_leave_actual_assurance_unchanged(no_live_effects, action):
    at = app()
    before = model_for(at)
    target = before.worklist.rows[0]
    step(at, "Analyst Review")
    assert "does not confirm facts, satisfy an evidence need or approve a control" in shown(at)
    assert "next actions describe work outside this demo" in shown(at)
    assert widget(at.button, "Record simulated review").disabled
    review(at, target.requirement_id, action, "Explicit synthetic reviewer reasoning for " + action)
    actions = at.session_state["guided_demo:actions"]
    assert len(actions) == 1 and actions[0].action == action
    after = model_for(at)
    assert [(row.requirement_id, row.outcome) for row in after.worklist.rows] == [
        (row.requirement_id, row.outcome) for row in before.worklist.rows]
    assert all(not link.state.events and not link.state.fact_reviews for link in after.scenario.assurance_links)
    if action == "Accept":
        assert any("does not confirm facts" in item.value for item in at.info)
        assert "does not verify or approve control" in widget(at.radio, "Simulated analyst action").options[0]
        for name in ("Assess", "Results"):
            step(at, name)
            table = worklist_table(at).set_index("Requirement")
            assert table.loc[target.requirement_id, "Provisional outcome"] == "Needs Review"
            assert table.loc[target.requirement_id, "Simulated review"] == (
                "Accept draft for discussion — does not verify or approve control")
            assert "does not confirm facts, satisfy an evidence need or approve a control" in shown(at)


@pytest.mark.parametrize("scenario", ["gap", "exception"])
def test_evidence_inventory_distinguishes_customer_criteria_from_vendor_sources(no_live_effects, scenario):
    at = app()
    widget(at.selectbox, "Demo scenario").set_value(scenario)
    run(at)
    step(at, "Evidence")
    inventories = [item.value for item in at.dataframe if "Source role" in item.value.columns]
    assert len(inventories) == 2
    roles = {name: role for inventory in inventories
             for name, role in inventory.set_index("Document")["Source role"].items()}
    assert set(inventories[1]["Document"]) == {"tls-customer-policy.txt", "customer-access-policy.txt"}
    assert not set(inventories[0]["Document"]) & set(inventories[1]["Document"])
    assert f"Simulated vendor artifacts: {len(roles) - 2} · Customer policy sources: 2" in shown(at)
    for name in ("tls-customer-policy.txt", "customer-access-policy.txt"):
        assert roles[name] == "Customer requirement / policy context"
    for name in ("tls-config.txt", "tls-scan.txt", "dr-plan.txt", "approved-security-policy.txt"):
        assert roles[name] == "Simulated vendor evidence"
    assert "not vendor-supplied proof of implementation or operation" in shown(at)
    for bound in model_for(at).documents + model_for(at).context_documents:
        assert bound.document.filename in roles
        assert all(any(part.text in block.value for block in at.code)
                   for part in bound.document.segments)


def test_replay_invalidates_only_changed_requirement_review_and_preserves_history(no_live_effects):
    from src.guided_assessment_demo import active_actions

    at = app()
    model = model_for(at)
    dr = next(row for row in model.worklist.rows if row.control_id == "BCP-01")
    tls = next(row for row in model.worklist.rows if row.control_id == "ENC-01")
    review(at, dr.requirement_id, "Challenge", "Exercise proof is missing from this exact source bundle.")
    review(at, tls.requirement_id, "Accept", "Retain the draft TLS interpretation for discussion.")
    history = at.session_state["guided_demo:actions"]
    assert len(history) == 2
    step(at, "Questions")
    widget(at.button, "Replay new evidence received").click()
    run(at)
    current = model_for(at)
    assert at.session_state["guided_demo:actions"] == history
    assert [action.requirement_id for action in active_actions(current, history)] == [tls.requirement_id]
    step(at, "Analyst Review")
    ledger = next(item.value for item in at.dataframe if "Review context" in item.value.columns)
    assert list(ledger["Review context"]) == ["Stale — source or context changed", "Current"]


def test_accepting_a_draft_never_removes_a_previously_created_material_finding(no_live_effects):
    from src.guided_assessment_demo import report_payload

    at = app()
    widget(at.selectbox, "Demo scenario").set_value("exception")
    run(at)
    initial = model_for(at)
    tls = next(row for row in initial.worklist.rows if row.control_id == "ENC-01")
    rationale = "The alternate production listener exception remains open and needs evidence-backed remediation."
    review(at, tls.requirement_id, "Create Finding", rationale)
    review(at, tls.requirement_id, "Accept", "Accept the draft concern for discussion; the finding is still open.")
    current = model_for(at)
    payload = report_payload(current, at.session_state["guided_demo:actions"])
    assert len(payload["findings"]) == 1
    finding = payload["findings"][0]
    assert finding["requirement_id"] == tls.requirement_id
    assert finding["rationale"] == rationale
    assert finding["context_status"] == "Current"
    assert finding["resolved"] is False and finding["draft"] is True
    assert finding["citations"]
    assert next(row for row in current.worklist.rows if row.control_id == "ENC-01").outcome == tls.outcome
    step(at, "Results")
    assert rationale in shown(at)


def test_replayed_finding_keeps_its_original_sources_and_requires_new_review(no_live_effects):
    from src.guided_assessment_demo import report_payload

    at = app()
    initial = model_for(at)
    dr = next(row for row in initial.worklist.rows if row.control_id == "BCP-01")
    original_sources = {(bound.document.filename, part.location, part.text)
                        for bound in dr.review.evidence for part in bound.document.segments}
    rationale = "Retain the missing recovery-exercise concern from this original plan-only bundle."
    review(at, dr.requirement_id, "Create Finding", rationale)
    step(at, "Questions")
    widget(at.button, "Replay new evidence received").click()
    run(at)
    current = model_for(at)
    finding = report_payload(current, at.session_state["guided_demo:actions"])["findings"][0]
    assert finding["context_status"] == "Stale context — re-review required"
    assert finding["resolved"] is False
    assert finding["rationale"] == rationale
    assert finding["threshold"] == dr.review.threshold_summary
    citations = {(item["filename"], item["location"], item["quote"]) for item in finding["citations"]}
    assert citations and citations <= original_sources
    new_dr = next(row for row in current.worklist.rows if row.control_id == "BCP-01")
    new_only = {(bound.document.filename, part.location, part.text)
                for bound in new_dr.review.evidence for part in bound.document.segments} - original_sources
    assert new_only and not citations.intersection(new_only)
    step(at, "Results")
    assert rationale in shown(at)
    assert "Stale context — re-review required" in shown(at)


def test_freeform_finding_rationale_renders_as_literal_text_and_exports_verbatim(no_live_effects, downloads):
    at = app()
    target = model_for(at).worklist.rows[0]
    rationale = (
        "![tracking image](https://tracker.synthetic.invalid/pixel.png)\n"
        "<script>window.location='https://tracker.synthetic.invalid/script'</script>\n"
        "Keep this as literal analyst rationale, with no browser resource request."
    )
    review(at, target.requirement_id, "Create Finding", rationale)
    step(at, "Results")
    assert any(rationale in item.value for item in at.text)
    assert all("tracker.synthetic.invalid" not in item.value for item in at.markdown)
    assert downloads
    payload = json.loads(downloads[-1][0])
    assert payload["findings"][0]["rationale"] == rationale
    assert payload["analyst_actions"][0]["rationale"] == rationale


def test_reset_and_other_browser_session_have_no_shared_review_state(no_live_effects):
    first = app()
    target = model_for(first).worklist.rows[0]
    review(first, target.requirement_id, "Create Finding", "Private synthetic session A observation.")
    step(first, "Questions")
    widget(first.button, "Replay new evidence received").click()
    run(first)

    second = app()
    assert second.session_state["guided_demo:actions"] == ()
    assert second.session_state["guided_demo:received"] is False
    assert widget(second.radio, "Demo step").value == "Start"
    assert len(model_for(second).worklist.requests) == 1
    assert len(first.session_state["guided_demo:actions"]) == 1

    widget(first.button, "Reset demo").click()
    run(first)
    assert first.session_state["guided_demo:actions"] == ()
    assert first.session_state["guided_demo:received"] is False
    assert widget(first.radio, "Demo step").value == "Start"
    assert "Private synthetic session A observation" not in shown(first)


def test_scenario_change_clears_annotations_and_returns_to_start(no_live_effects):
    at = app()
    target = model_for(at).worklist.rows[0]
    review(at, target.requirement_id, "Challenge", "This reasoning belongs only to the initial scenario.")
    widget(at.selectbox, "Demo scenario").set_value("exception")
    run(at)
    assert at.session_state["guided_demo:actions"] == ()
    assert at.session_state["guided_demo:received"] is False
    assert widget(at.radio, "Demo step").value == "Start"
    assert "initial scenario" not in shown(at)


def test_actual_app_production_mode_still_fails_closed(no_live_effects, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "production")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert at.exception
    assert any("Production authentication is not configured" in item.message for item in at.exception)
    assert not at.title and not at.dataframe
