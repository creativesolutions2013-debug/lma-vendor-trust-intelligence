"""Synthetic analyst end-to-end journey: evidence, question, response, review and ZIP.

The real Streamlit app is exercised with zero live DB, AI, network or governed
decision effects. This is NOT an authenticated vendor portal or production E2E.
"""
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

from test_guided_assessment_demo_ui import no_live_effects, packages, run, widget
from test_upload_assessment_ui import start, stage
from test_upload_evaluation import source_text
from test_upload_evaluation_ui import suggestions


def _export(packages):
    assert packages
    with ZipFile(BytesIO(packages[-1])) as archive:
        report = json.loads(archive.read("report.json"))
        manifest = json.loads(archive.read("manifest.json"))
        sources = {item["filename"]: archive.read(item["archive_path"])
                   for item in manifest["artifacts"]}
        for item in manifest["artifacts"]:
            assert sha256(sources[item["filename"]]).hexdigest() == item["sha256"]
        return report, sources


def _review(at, requirement, action, reason):
    stage(at, "Review gaps")
    widget(at.selectbox, "Review requirement").set_value(requirement)
    run(at)
    widget(at.radio, "Draft action").set_value(action)
    widget(at.text_area, "Rationale").set_value(reason)
    run(at)
    widget(at.button, "Record draft review").click()
    run(at)
    assert not at.error


def _replay_empty_native_picker_callback(at, monkeypatch):
    """Replay the real callback on a snapshot of the observed AppTest state.

    AppTest.set_value([]) on an already-empty picker is a no-op, while
    AppTest's session proxy lacks the runtime mapping's .pop method. A plain
    mapping snapshot faithfully exposes callback mutations without changing
    the AppTest's live objects. Restoring the old handler fails this assertion:
    it clears pending originals, dirties the snapshot and loses completion.
    """
    import src.upload_assessment_ui as upload_ui

    state = {
        "customer_assessment:pending_files":
            at.session_state.get("customer_assessment:pending_files"),
        "customer_assessment:completion":
            at.session_state.get("customer_assessment:completion"),
        "customer_assessment:uploads_dirty":
            at.session_state.get("customer_assessment:uploads_dirty", False),
    }
    expected = dict(state)
    key = "customer_assessment:files:" + str(
        at.session_state.get("customer_assessment:upload_epoch", 0)
    )
    with monkeypatch.context() as patch:
        patch.setattr(upload_ui.st, "session_state", state)
        upload_ui._capture_files(key)
    assert state == expected, "Empty native picker callback mutated retained state."


def test_browser_empty_picker_replay_does_not_invalidate_completed_review(no_live_effects, packages, monkeypatch):
    at = start()
    at.get("file_uploader")[0].upload(
        "context.txt", b"Synthetic metadata for a test; no control approval."
    )
    run(at)
    widget(at.button, "Evaluate attached evidence").click()
    run(at)
    stage(at, "Report")
    widget(at.button, "Finish assessment review").click()
    run(at)
    completion = at.session_state["customer_assessment:completion"]
    exported, originals = _export(packages)
    assert originals["context.txt"].startswith(b"Synthetic metadata")
    assert exported["review_completion"]["vendor_approved"] is False

    stage(at, "Upload evidence")
    # A normal native picker remount can yield an empty value even though the
    # evidence is already retained: neither completion nor exports are dirty.
    _replay_empty_native_picker_callback(at, monkeypatch)
    assert at.session_state["customer_assessment:completion"] == completion
    assert not at.session_state.get("customer_assessment:uploads_dirty", False)
    stage(at, "Report")
    assert [b for b in at.get("download_button")
            if b.label == "Download assessment package (.zip)"]


def test_evidence_first_question_followup_and_reassessment_journey(no_live_effects, packages, monkeypatch):
    at = start()
    intake = at.session_state["customer_assessment:intake"]
    observed = intake.as_of - timedelta(days=7)
    tls = source_text(
        intake,
        "Primary listener 443: TLS 1.2 is enabled.\n"
        "Alternate production listener 9443: TLS 1.0 is enabled.",
        date=observed.isoformat(),
    ).encode()
    dr_plan = (
        "Recovery plan objectives\n"
        f"Service: {intake.service}\n"
        f"Environment: {intake.environment}\n"
        f"Observation date: {observed.isoformat()}\n"
        "Target RTO 120 minutes and RPO 30 minutes.\n"
        "Next recovery exercise is scheduled; no completed test result supplied.\n"
    ).encode()
    originals = {"tls-config.txt": tls, "dr-plan.txt": dr_plan}

    # An analyst starts with two sources, then navigates before evaluation.
    uploader = at.get("file_uploader")[0]
    uploader.upload("tls-config.txt", tls).upload("dr-plan.txt", dr_plan)
    run(at)
    assert len(at.multiselect) == 2
    pending = at.session_state["customer_assessment:pending_files"]
    stage(at, "Report")
    assert at.warning and not [button for button in at.get("download_button")
                              if button.label == "Download assessment package (.zip)"]
    stage(at, "Upload evidence")
    _replay_empty_native_picker_callback(at, monkeypatch)
    assert at.session_state["customer_assessment:pending_files"] == pending

    # Use source-stated fields by direct analyst action; not verified facts.
    assert len(suggestions(at)) == 2
    suggestions(at)[0].click()
    run(at)
    suggestions(at)[1].click()
    run(at)
    kinds = [x.value for x in at.selectbox if x.label == "Document kind (your declaration)"]
    assert kinds == ["configuration", "policy"]
    assert all(d.value == observed for d in at.date_input)
    widget(at.button, "Evaluate attached evidence").click()
    run(at)

    initial = at.session_state["customer_assessment:model"]
    cases = {e["requirement_id"]: e for e in initial.customer_context["evaluations"]}
    assert any(f["dimension"] == "enabled_version" and f["value"] == 10
               and f["eligible_for_preview"] and not f["confirmed"]
               for f in cases["ENC-01"]["facts"])
    assert cases["ENC-01"]["preview"]["outcome_if_confirmed"] == "Risk Identified"
    assert cases["BCP-01"]["preview"]["outcome_if_confirmed"] != "Risk Identified"
    assert not any(f["eligible_for_preview"] and f["direction"] == "adverse"
                   for f in cases["BCP-01"]["facts"])
    assert all(r.outcome not in ("Met", "Risk Identified") for r in initial.worklist.rows)
    assert not any("BCP-01" in request.requirement_ids for request in initial.worklist.requests)

    # A missing executed DR test warrants an evidence request, not an invented
    # failed control. Weak TLS is a separate provisional draft finding.
    _review(at, "BCP-01", "Request Evidence",
            "Check existing records for a completed production recovery test with achieved objectives and dependency scope; request only the missing proof.")
    reviewed = at.session_state["customer_assessment:model"]
    bcp_request, = [request for request in reviewed.worklist.requests if "BCP-01" in request.requirement_ids]
    assert bcp_request.question == at.session_state["customer_assessment:actions"][-1].rationale
    assert any(bcp_request.question == text.value for text in at.text)
    _review(at, "ENC-01", "Create Finding",
            "Validate the cited TLS 1.0 alternate production listener and its current remediation status.")
    stage(at, "Report")
    widget(at.button, "Finish assessment review").click()
    run(at)
    report, evidence = _export(packages)
    assert evidence == originals
    assert len(report["findings"]) == 1
    assert {a["action"] for a in report["analyst_actions"]} == {"Request Evidence", "Create Finding"}
    gap_review, = report["evidence_gap_reviews"]
    assert gap_review["status"] == "Current" and gap_review["decision"] == "insufficient"
    assert gap_review["semantic_confirmation"] is False
    assert any("BCP-01" in request["requirement_ids"] and request["question"] == bcp_request.question
               for request in report["targeted_requests"])
    assert report["risk"]["residual_score"] is None
    assert report["review_completion"]["vendor_approved"] is False

    # The synthetic follow-up is selected by the analyst, not delivered to a
    # vendor. Reevaluate the new original rather than inheriting old conclusions.
    dr_test = source_text(
        intake,
        "Recovery exercise completed.\n"
        "Achieved RTO 210 minutes and RPO 45 minutes.\n"
        "Identity provider was excluded from the exercise.",
        "BCP-01", date=observed.isoformat(),
    ).encode()
    originals["dr-exercise.txt"] = dr_test
    stage(at, "Upload evidence")
    at.get("file_uploader")[0].upload("dr-exercise.txt", dr_test)
    run(at)
    stage(at, "Report")
    assert at.warning and not [button for button in at.get("download_button")
                              if button.label == "Download assessment package (.zip)"]  # Old export invalid.
    stage(at, "Upload evidence")
    assert len(suggestions(at)) == 3
    suggestions(at)[2].click()
    run(at)
    widget(at.button, "Evaluate attached evidence").click()
    run(at)
    revised = at.session_state["customer_assessment:model"]
    assert len(revised.documents) == 3
    dr = next(e for e in revised.customer_context["evaluations"]
              if e["requirement_id"] == "BCP-01")
    assert {(f["dimension"], f["value"]) for f in dr["facts"]
            if f["dimension"] in ("achieved_rto_minutes", "achieved_rpo_minutes")} >= {
        ("achieved_rto_minutes", 210), ("achieved_rpo_minutes", 45)
    }
    assert any(f["dimension"] == "scope_complete" and f["value"] is False
               for f in dr["facts"])
    assert all(not f["confirmed"] for f in dr["facts"])
    stage(at, "Report")
    widget(at.button, "Finish assessment review").click()
    run(at)
    latest, evidence = _export(packages)
    assert evidence == originals
    assert any(a["requirement_id"] == "BCP-01" and a["status"] == "Stale context"
               for a in latest["analyst_actions"])
    assert latest["evidence_gap_reviews"][0]["status"] == "Stale context"
    assert not any("BCP-01" in request["requirement_ids"] for request in latest["targeted_requests"])
    tls_action = next(a for a in latest["analyst_actions"] if a["requirement_id"] == "ENC-01")
    assert tls_action["status"] == "Current"
    assert tls_action["citations"] == next(a for a in report["analyst_actions"]
                                           if a["requirement_id"] == "ENC-01")["citations"]
    assert next(f for f in latest["findings"] if f["requirement_id"] == "ENC-01")["context_status"] == "Current"
    # DR-only follow-up must not let an unchanged TLS finding be duplicated.
    stage(at, "Review gaps")
    widget(at.selectbox, "Review requirement").set_value("ENC-01")
    run(at)
    widget(at.radio, "Draft action").set_value("Create Finding")
    widget(at.text_area, "Rationale").set_value(tls_action["rationale"])
    run(at)
    widget(at.button, "Record draft review").click()
    run(at)
    assert any("identical draft finding" in e.value for e in at.error)
    assert len(at.session_state["customer_assessment:actions"]) == 2
    assert all(not f["confirmed"]
               for e in latest["assessment_context"]["evaluations"] for f in e["facts"])
    assert latest["risk"]["residual_score"] is None
    assert latest["review_completion"]["vendor_approved"] is False

    # Read the added source, then explicitly request only the remaining scope proof.
    # The old request is retained in history; it is not silently reused or closed.
    focused_question = "Provide current exercise evidence for the excluded identity provider and its recovery dependency scope."
    _review(at, "BCP-01", "Request Evidence", focused_question)
    stage(at, "Report")
    widget(at.button, "Finish assessment review").click()
    run(at)
    final, evidence = _export(packages)
    assert evidence == originals
    final_request, = [request for request in final["targeted_requests"] if "BCP-01" in request["requirement_ids"]]
    assert final_request["question"] == focused_question
    assert final["evidence_gap_reviews"][0]["status"] == "Current"
    bcp_actions = [action for action in final["analyst_actions"] if action["requirement_id"] == "BCP-01"]
    assert [action["status"] for action in bcp_actions] == ["Stale context", "Current"]
    assert final["risk"]["residual_score"] is None
    assert final["review_completion"]["vendor_approved"] is False
