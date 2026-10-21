"""Actual read-only worklist inspection, with explicit synthetic review inputs."""
from dataclasses import replace

import pytest
from streamlit.testing.v1 import AppTest

from src.assessment_worklist import EvidenceNeed, build_assessment_worklist, record_need_review
from src.assessment_worklist_pilot import worklist_scenarios
from src.control_assurance import inspect_control, record_control_review


PILOT = (
    "from src.assessment_worklist_ui import render_assessment_worklist_preview\n"
    "render_assessment_worklist_preview()"
)


def widget(items, label):
    return next(item for item in items if item.label == label)


def scenario(key="initial"):
    return next(s for s in worklist_scenarios() if s.scenario_id == key)


def built(s):
    return build_assessment_worklist(s.scope, s.applicability, s.requirements, s.assurance_links,
                                    legacy_evidence=s.legacy_evidence, control_claims=s.control_claims)


def app():
    at = AppTest.from_string(PILOT, default_timeout=25).run()
    assert not at.exception
    return at


def text(at):
    return "\n".join(item.value for collection in (at.markdown, at.caption, at.warning, at.info)
                     for item in collection)


def table(at):
    assert len(at.dataframe) == 1
    return at.dataframe[0].value


def select_detail(at, row):
    widget(at.selectbox, "Requirement detail").set_value(row.row_id).run()
    assert not at.exception


def test_initial_preview_keeps_every_applicable_requirement_and_separate_legacy_status():
    s = scenario()
    worklist = built(s)
    at = app()
    rows = table(at)
    assert len(rows) == len(worklist.rows) >= 4
    assert set(rows["Requirement"]) == {row.requirement_id for row in worklist.rows}
    assert set(rows["Control mapping"]) == {row.control_id for row in worklist.rows}
    assert list(rows["Requirement"]) == [row.requirement_id for row in worklist.rows]
    assert "Legacy evidence support means document sufficiency" in text(at)
    assert "not technical compliance" in text(at)
    assert "not sent" in text(at)
    assert widget(at.metric, "Draft vendor requests").value == "1"
    assert widget(at.metric, "Ask-everything baseline").value == str(worklist.baseline_questions)


def test_unknown_customer_control_without_specialist_keeps_sources_threshold_and_limitation():
    worklist = built(scenario())
    row = next(r for r in worklist.rows if r.control_id.startswith("CUSTOM-") and r.review and r.review.evidence)
    at = app()
    select_detail(at, row)
    shown = text(at)
    assert row.requirement_id in shown and row.control_id in shown
    assert row.requirement.customer_policy_id in shown and row.requirement.policy_version in shown
    assert row.requirement.service in shown and row.requirement.environment in shown
    assert row.threshold in shown
    assert "Specialist evaluation unavailable; analyst review required." in shown
    assert any("Provisional outcome: Needs Review" == i.value for i in at.info)
    for b in row.review.evidence:
        assert b.document.filename in shown
        assert b.content_sha256 in shown
        assert str(b.source.observed_on) in shown
        assert str(b.source.origin) in shown
        for part in b.document.segments:
            assert any(part.text in i.value for i in at.code)


def test_gap_closed_package_reduces_one_request_without_hiding_existing_exception():
    initial = built(scenario("initial"))
    closed = built(scenario("gap-closed"))
    at = app()
    assert widget(at.metric, "Draft vendor requests").value == "1"
    assert initial.requests[0].question in text(at)
    widget(at.selectbox, "Synthetic assessment package").set_value("gap-closed").run()
    assert not at.exception
    assert widget(at.metric, "Draft vendor requests").value == "0"
    assert len(table(at)) == len(initial.rows) == len(closed.rows)
    assert initial.requests[0].question not in text(at)
    adverse = next(r for r in closed.rows if r.review and any(f.direction == "adverse" for f in r.review.facts))
    select_detail(at, adverse)
    for f in adverse.review.facts:
        if f.direction == "adverse":
            assert any(f.proposal.quote in c.value for c in at.code)
    assert "not analyst time" in text(at)


def test_inspection_has_no_review_or_vendor_controls_and_cannot_write_or_call_apis(monkeypatch):
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session
    import requests
    import src.control_assurance as review
    import src.evidence_intelligence_m2 as ai

    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only synthetic inspection may not write, use a database, AI or network.")

    monkeypatch.setattr(Engine, "connect", forbidden)
    for method in ("add", "add_all", "delete", "commit", "flush"):
        monkeypatch.setattr(Session, method, forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(review, "record_control_review", forbidden)
    monkeypatch.setattr(ai, "evaluate_ai_requirements", forbidden)
    before = worklist_scenarios()
    at = app()
    widget(at.selectbox, "Synthetic assessment package").set_value("gap-closed").run()
    assert not at.exception
    assert not at.button and not at.checkbox and not at.text_area and not at.text_input
    assert not at.get("form") and not at.get("file_uploader")
    assert "m3d_current_review" not in at.session_state
    assert "m3c1_current_review" not in at.session_state
    assert before == worklist_scenarios()
    assert all(not link.state.events and not link.state.fact_reviews for s in before for link in s.assurance_links)


def explicit_review(case, state, *, adverse_only=False):
    """Test only: actions happen before inspection, never in product fixtures/UI."""
    view = inspect_control(case, state)
    common = dict(expected_bundle=view.bundle_fingerprint, analyst="Synthetic independent reviewer",
                  reviewed_on=case.as_of, rationale="Checked the full synthetic source meaning and technical scope.")
    if adverse_only:
        f = next(f for f in view.facts if f.direction == "adverse" and not f.reasons)
        return record_control_review(case, state, action="exception", fact_ids=(f.proposal.fact_id,),
                                     presented_fingerprints=(f.fingerprint,), confirms=True, **common)
    support = tuple(f for f in view.facts if f.direction == "support" and not f.reasons)
    state = record_control_review(case, state, action="support", fact_ids=tuple(f.proposal.fact_id for f in support),
                                 presented_fingerprints=tuple(f.fingerprint for f in support), confirms=True, **common)
    for signal in view.signals:
        state = record_control_review(case, state, action="signal", signal_id=signal.signal_id, material=False, **common)
    return record_control_review(case, state, action="bundle", confirms=True, **common)


def test_previously_confirmed_current_failure_is_first_and_inspection_does_not_create_review(monkeypatch):
    import src.assessment_worklist_ui as ui

    s = scenario("adverse")
    link = next(link for link in s.assurance_links if link.control_id == "ENC-01")
    updated = replace(link, state=explicit_review(link.case, link.state, adverse_only=True))
    supplied = replace(s, assurance_links=tuple(updated if l is link else l for l in s.assurance_links))
    monkeypatch.setattr(ui, "worklist_scenarios", lambda: (supplied,))
    at = app()
    rows = table(at)
    assert rows.iloc[0]["Provisional assurance"] == "Risk Identified"
    assert rows.iloc[0]["Requirement"] == link.case.requirement.requirement_id
    assert any(i.value == "Provisional outcome: Risk Identified" for i in at.info)
    adverse = next(f for f in inspect_control(updated.case, updated.state).facts if f.direction == "adverse")
    assert any(adverse.proposal.quote in i.value for i in at.code)
    assert len(updated.state.events) == 1
    assert "m3d_current_review" not in at.session_state
    assert not at.button


def test_provisional_met_still_requires_governance_and_sorts_last(monkeypatch):
    import src.assessment_worklist_ui as ui

    s = scenario()
    link = next(link for link in s.assurance_links if link.control_id == "ENC-01")
    updated = replace(link, state=explicit_review(link.case, link.state))
    mapping = next(m for m in s.requirements if m.control_id == updated.control_id)
    view = inspect_control(updated.case, updated.state)
    reviews = []
    for need in mapping.needs:
        sources = tuple(b.fingerprint for b in view.evidence if b.source.evidence_kind in need.accepted_kinds)
        reviews.append(record_need_review(
            s.scope, mapping, updated.case, updated.state, need, decision="supported", confirms=True,
            source_fingerprints=sources,
            fact_fingerprints=tuple(f.fingerprint for f in view.facts if f.proposal.source_fingerprint in sources
                                    and f.proposal.dimension in need.dimensions),
            analyst="Synthetic independent reviewer", reviewed_on=updated.case.as_of,
            rationale="Checked these confirmed facts against this exact need and customer threshold.",
        ))
    updated = replace(updated, need_reviews=tuple(reviews))
    supplied = replace(s, assurance_links=tuple(updated if l is link else l for l in s.assurance_links))
    monkeypatch.setattr(ui, "worklist_scenarios", lambda: (supplied,))
    at = app()
    rows = table(at)
    assert rows.iloc[-1]["Requirement"] == link.case.requirement.requirement_id
    assert rows.iloc[-1]["Provisional assurance"] == "Met"
    row = next(r for r in built(supplied).rows if r.requirement_id == link.case.requirement.requirement_id)
    select_detail(at, row)
    assert "governance" in row.next_action.casefold()
    assert "not technical compliance" in text(at)
    assert "All assurance, workflow intents and next actions are provisional" in text(at)
    assert not at.button


def test_wrong_relationship_result_shows_linkage_gap_without_source_reuse(monkeypatch):
    import src.assessment_worklist_ui as ui

    s = scenario()
    link = next(link for link in s.assurance_links if link.control_id == "ENC-01")
    wrong = replace(link, engagement_id="different-synthetic-relationship")
    supplied = replace(s, assurance_links=tuple(wrong if l is link else l for l in s.assurance_links))
    monkeypatch.setattr(ui, "worklist_scenarios", lambda: (supplied,))
    at = app()
    row = next(r for r in built(supplied).rows if r.requirement_id == link.case.requirement.requirement_id)
    select_detail(at, row)
    assert any(i.value == "Provisional outcome: Needs Review" for i in at.info)
    assert row.review is None and row.presentation is None
    assert "No permitted source" in text(at)
    for proposal in link.case.proposals:
        assert not any(proposal.quote in i.value for i in at.code)


def test_empty_registered_package_is_explicit_without_creating_review(monkeypatch):
    import src.assessment_worklist_ui as ui

    monkeypatch.setattr(ui, "worklist_scenarios", lambda: ())
    at = app()
    assert "No synthetic assessment packages" in text(at)
    assert not at.selectbox and not at.button and not at.dataframe


def test_duplicate_package_is_rejected_visibly_before_any_assurance_is_presented(monkeypatch):
    import src.assessment_worklist_ui as ui

    s = scenario("adverse")
    link = next(l for l in s.assurance_links if l.control_id == "ENC-01")
    confirmed = replace(link, state=explicit_review(link.case, link.state, adverse_only=True))
    supplied = replace(s, assurance_links=s.assurance_links + (confirmed,))
    monkeypatch.setattr(ui, "worklist_scenarios", lambda: (supplied,))
    at = app()
    assert "Needs Review — assessment package rejected" in text(at)
    assert "Duplicate assurance linkages" in text(at)
    assert not at.dataframe and not at.metric and not at.button


def test_existing_assessments_page_renders_preview_before_inventory_queries():
    import ast
    from pathlib import Path

    module = ast.parse(Path("app.py").read_text())
    page = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "render_assessments")
    calls = [node for node in ast.walk(page) if isinstance(node, ast.Call)]
    preview = next(node for node in calls if isinstance(node.func, ast.Name)
                   and node.func.id == "render_assessment_worklist_preview")
    inventory = next(node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "query")
    assert preview.lineno < inventory.lineno


def partial_recovery_package(*, reviewed=False):
    """RTO-only source; explicit test review distinguishes support from absent RPO."""
    from src.control_assurance_pilot import document, proposal

    s = scenario("gap-closed")
    link = next(l for l in s.assurance_links if l.control_id == "BCP-01")
    report = document("ui-time-only-exercise", "SYNTHETIC witnessed production exercise: achieved RTO was 120 minutes. This record addresses recovery time only.",
                      link.case.requirement.scope)
    case = replace(link.case, documents=(report,), proposals=(proposal(report, "achieved_rto_minutes", 1, 120),))
    rto = EvidenceNeed("achieved-rto", "Achieved full-service RTO", "Dated complete-service recovery time record",
                       "Provide the dated complete-service achieved RTO record.", ("test",), ("achieved_rto_minutes",), 365)
    rpo = EvidenceNeed("achieved-rpo", "Achieved full-service RPO", "Dated complete-service recovery point record",
                       "Provide the dated complete-service achieved RPO record.", ("test",), ("achieved_rpo_minutes",), 365)
    mapping = replace(next(m for m in s.requirements if m.control_id == link.control_id), needs=(rto, rpo))
    updated = replace(link, case=case)
    if reviewed:
        state = explicit_review(case, updated.state)
        view = inspect_control(case, state)
        common = dict(source_fingerprints=(view.evidence[0].fingerprint,), confirms=True,
                      analyst="Synthetic independent reviewer", reviewed_on=case.as_of)
        support = record_need_review(
            s.scope, mapping, case, state, rto, decision="supported",
            fact_fingerprints=(view.facts[0].fingerprint,),
            rationale="Checked the confirmed recovery-time result against this specific need.", **common,
        )
        insufficient = record_need_review(
            s.scope, mapping, case, state, rpo, decision="insufficient",
            rationale="The time-only exercise record does not document the required recovery point result.", **common,
        )
        updated = replace(updated, state=state, need_reviews=(support, insufficient))
    return replace(s, requirements=tuple(mapping if m.control_id == updated.control_id else m for m in s.requirements),
                   assurance_links=tuple(updated if l.control_id == updated.control_id else l for l in s.assurance_links)), rto, rpo


@pytest.mark.parametrize("reviewed", [False, True])
def test_ui_distinguishes_exact_need_support_validation_and_reviewed_insufficiency(monkeypatch, reviewed):
    import src.assessment_worklist_ui as ui

    s, rto, rpo = partial_recovery_package(reviewed=reviewed)
    monkeypatch.setattr(ui, "worklist_scenarios", lambda: (s,))
    at = app()
    row = next(r for r in built(s).rows if r.control_id == "BCP-01")
    select_detail(at, row)
    shown = text(at)
    assert rto.missing_fact in shown and rpo.missing_fact in shown
    assert "A request deferred for analyst review is not a resolved evidence need" in shown
    if reviewed:
        assert rto.need_id + " · Supported by reviewed evidence" in shown
        assert rpo.need_id + " · Missing or insufficient" in shown
        assert rpo.question in shown and rto.question not in shown
        assert widget(at.metric, "Draft vendor requests").value == "1"
        assert "1 reviewed support" in shown
        assert row.outcome != "Met"
        assert any("achieved RTO was 120 minutes" in item.value for item in at.code)
    else:
        assert rto.need_id + " · Analyst validation required" in shown
        assert rpo.need_id + " · Analyst validation required" in shown
        assert "Supported by reviewed evidence" not in shown
        assert rpo.question not in shown
        assert widget(at.metric, "Draft vendor requests").value == "0"
        assert row.intent == "Analyst validate"
    assert not at.button and not at.checkbox and not at.text_input


@pytest.mark.parametrize("change", ["source", "threshold", "scope"])
def test_ui_cannot_reuse_need_review_after_source_threshold_or_scope_changes(monkeypatch, change):
    import src.assessment_worklist_ui as ui
    from src.dr_assurance import DrThreshold

    s, _, _ = partial_recovery_package(reviewed=True)
    original = next(l for l in s.assurance_links if l.control_id == "BCP-01")
    if change == "source":
        case = replace(original.case, documents=(replace(original.case.documents[0], content=b"SYNTHETIC revised recovery exercise record; interpretation requires review."),))
    elif change == "threshold":
        case = replace(original.case, threshold=DrThreshold(365, 60, 60))
    else:
        case = replace(original.case, requirement=replace(original.case.requirement, scope="additional production recovery dependencies"))
    changed = replace(original, case=case)
    supplied = replace(s, assurance_links=tuple(changed if l is original else l for l in s.assurance_links),
                       requirements=tuple(replace(m, requirement=case.requirement, threshold=case.threshold)
                                          if m.control_id == "BCP-01" else m for m in s.requirements))
    monkeypatch.setattr(ui, "worklist_scenarios", lambda: (supplied,))
    at = app()
    row = next(r for r in built(supplied).rows if r.control_id == "BCP-01")
    select_detail(at, row)
    assert "Supported by reviewed evidence" not in text(at)
    assert all(m.status != "Supported by reviewed evidence" for m in row.need_matches)
    assert row.outcome != "Met" and not any(f.confirmed for f in row.review.facts)
    assert original.need_reviews == changed.need_reviews  # Inspection never replaces decisions.
