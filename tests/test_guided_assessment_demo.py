"""Synthetic guided journey composition; no governed decisions or real data."""
from dataclasses import FrozenInstanceError
import json
import socket
import sqlite3

import pytest
import requests
import sqlalchemy

from src.guided_assessment_demo import (
    ACTIONS, RISK_PROFILES, SCENARIOS, active_actions, build_demo, record_action,
    report_bytes, report_payload, row_fingerprint,
)


def rows(model):
    return {row.control_id: row for row in model.worklist.rows}


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("received", [False, True])
@pytest.mark.parametrize("profile", RISK_PROFILES)
def test_every_walkthrough_retains_actual_customer_requirements_and_unreviewed_gates(scenario, received, profile):
    model = build_demo(scenario, received, profile)
    assert len(model.worklist.rows) == len(model.scenario.applicability.controls) == 4
    assert len({link.case.family for link in model.scenario.assurance_links}) == 4
    assert {row.specialist_available for row in model.worklist.rows} == {False, True}
    assert {row.requirement_id for row in model.worklist.rows} == {
        mapping.requirement.requirement_id for mapping in model.scenario.requirements
    }
    assert all(row.provisional and row.outcome not in {"Met", "Risk Identified"}
               for row in model.worklist.rows)
    for link in model.scenario.assurance_links:
        assert not link.state.fact_reviews and not link.state.events
        assert link.state.bundle_review is None and not link.need_reviews
    for row in model.worklist.rows:
        assert row.requirement.service == model.worklist.scope.service
        assert row.requirement.environment == model.worklist.scope.environment
        assert row.threshold and row.next_action and row.review.bundle_fingerprint


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_replaying_scoped_operating_evidence_removes_only_the_dr_request_not_review(scenario):
    first, replayed = build_demo(scenario), build_demo(scenario, True)
    assert first.worklist.baseline_questions == replayed.worklist.baseline_questions == 4
    assert len(first.worklist.requests) == 1 and len(replayed.worklist.requests) == 0
    assert first.worklist.requests[0].requirement_ids == ("BCP-01.DR",)
    a, b = rows(first), rows(replayed)
    assert a["BCP-01"].need_matches[0].status == "Missing or insufficient"
    assert b["BCP-01"].need_matches[0].status == "Analyst validation required"
    assert b["BCP-01"].outcome != "Met"
    assert all(a[key] == b[key] for key in a if key != "BCP-01")
    assert row_fingerprint(first, a["BCP-01"]) != row_fingerprint(replayed, b["BCP-01"])
    assert all(row_fingerprint(first, a[key]) == row_fingerprint(replayed, b[key])
               for key in a if key != "BCP-01")


def test_technical_exception_survives_gap_replay_and_every_simulated_action():
    model = build_demo("exception", True)
    tls = rows(model)["ENC-01"]
    assert tls.intent == "Review exception" and tls.priority <= 1
    assert any(fact.direction == "adverse" and "TLS 1.0" in fact.proposal.quote
               for fact in tls.review.facts)
    assert any(fact.direction == "support" for fact in tls.review.facts)
    history = ()
    for action in ACTIONS:
        history = record_action(model, history, tls.requirement_id, action, "Reviewed cited alternate-listener concern.")
        assert rows(model)["ENC-01"] == tls
        assert not any(fact.confirmed for fact in tls.review.facts)
        assert tls.outcome == "Needs Review"
    exported = report_payload(model, history)
    reported_tls = next(row for row in exported["requirements"] if row["control_id"] == "ENC-01")
    assert any("TLS 1.0" in citation["quote"] for citation in reported_tls["citations"])
    assert exported["findings"][0]["requirement_id"] == tls.requirement_id
    assert all(not action["semantic_confirmation"] and not action["governed_decision"]
               for action in exported["analyst_actions"])


def test_annotations_invalidate_only_changed_context_and_history_remains_visible():
    model = build_demo()
    tls, dr = rows(model)["ENC-01"], rows(model)["BCP-01"]
    actions = record_action(model, (), tls.requirement_id, "Accept", "Accept this draft for later governance; not control approval.")
    actions = record_action(model, actions, dr.requirement_id, "Create Finding", "Completed recovery exercise missing.")
    replayed = build_demo(evidence_received=True)
    assert [action.requirement_id for action in active_actions(replayed, actions)] == [tls.requirement_id]
    payload = report_payload(replayed, actions)
    assert [action["active"] for action in payload["analyst_actions"]] == [True, False]
    assert payload["analyst_actions"][1]["status"] == "Stale context"
    assert payload["findings"][0]["context_status"] == "Stale context — re-review required"
    assert not payload["findings"][0]["resolved"]
    assert payload["findings"][0]["citations"] == [
        {"statement": citation.statement, "filename": citation.filename,
         "location": citation.location, "quote": citation.quote,
         "fingerprint": citation.fingerprint, "confirmed": citation.confirmed,
         "source_role": citation.source_role, "provenance": citation.provenance,
         "document_id": citation.document_id}
        for citation in actions[1].citations
    ]
    assert all(citation["filename"] != "dr-exercise.txt" for citation in payload["findings"][0]["citations"])
    revised = build_demo(evidence_received=True, risk_profile=RISK_PROFILES[1])
    assert active_actions(revised, actions) == ()
    assert len(report_payload(revised, actions)["analyst_actions"]) == 2
    assert active_actions(model, ()) == ()  # A new session receives no shared state.


def test_only_latest_current_annotation_is_active_without_discarding_prior_rationale():
    model = build_demo()
    requirement = model.worklist.rows[0].requirement_id
    history = record_action(model, (), requirement, "Create Finding", "Retain potential exception for investigation.")
    history = record_action(model, history, requirement, "Challenge", "Challenge the draft interpretation; issue remains unverified.")
    assert active_actions(model, history) == (history[-1],)
    payload = report_payload(model, history)
    assert len(payload["analyst_actions"]) == 2 and len(payload["findings"]) == 1
    assert payload["findings"][0]["context_status"] == "Current"
    assert not payload["findings"][0]["resolved"]
    assert payload["analyst_actions"][0]["status"] == "Superseded"
    assert model.worklist.rows[0].review.provisional


def test_later_accept_cannot_erase_a_draft_finding_or_replace_its_recorded_sources():
    model = build_demo("exception")
    target = rows(model)["ENC-01"]
    history = record_action(model, (), target.requirement_id, "Create Finding", "Investigate the active alternate TLS listener.")
    first = report_payload(model, history)["findings"][0]
    history = record_action(model, history, target.requirement_id, "Accept", "Accept draft wording for further review only.")
    later = report_payload(model, history)["findings"]
    assert later == [first]
    assert first["citations"] and "2026.1" in first["customer_context"]
    assert "90 days" in first["threshold"]
    assert any("TLS 1.0" in citation["quote"] for citation in first["citations"])
    assert first["resolved"] is False


def test_export_uses_actual_thresholds_segments_gaps_and_counts_without_invented_assurance():
    model = build_demo("exception")
    payload = report_payload(model, ())
    assert payload == json.loads(report_bytes(model, ()).decode("utf-8"))
    assert payload["synthetic"] and payload["provisional"] and payload["session_only"]
    assert payload["authoritative"] is False
    assert len(payload["requirements"]) == 4
    actual = {row.requirement_id: row for row in model.worklist.rows}
    for row in payload["requirements"]:
        original = actual[row["requirement_id"]]
        assert row["outcome"] == original.outcome and row["threshold"] == original.threshold
        assert row["specialist_available"] == original.specialist_available
        assert row["max_age_days"] == original.requirement.max_age_days
        assert row["threshold_summary"] == original.review.threshold_summary
        assert row["presentation"]["uncertainty"] == original.presentation.uncertainty
        assert row["presentation"]["attention"]
        sources = {bound.fingerprint: bound for bound in original.review.evidence}
        for citation in row["citations"]:
            bound = sources[citation["source_fingerprint"]]
            assert citation["filename"] == bound.document.filename
            assert (citation["location"], citation["quote"]) in {
                (segment.location, segment.text) for segment in bound.document.segments
            }
            assert citation["service"] == bound.source.service
            assert citation["evidence_kind"] == bound.source.evidence_kind
    metrics = payload["question_metrics"]
    assert metrics["ask_everything_baseline"] == 4
    assert metrics["distinct_targeted_requests"] == 1
    assert metrics["reviewed_supporting_needs"] == 0
    assert metrics["awaiting_analyst_validation_needs"] == 4
    assert metrics["missing_or_insufficient_needs"] == 1
    assert payload["risk"]["residual_score"] is None and payload["risk"]["approved_risk"] is False
    assert "not" in metrics["limitation"] and "time savings" in metrics["limitation"]


def test_context_only_sources_are_actual_excerpts_and_never_satisfy_selected_requirements():
    model = build_demo()
    assert len(model.context_documents) == 2
    assert {bound.source.document_id for bound in model.context_documents} == {
        "synthetic-soc2-overview", "customer-access-policy"
    }
    actual = {bound.fingerprint for bound in model.documents}
    assert all(bound.fingerprint not in actual for bound in model.context_documents)
    for bound in model.context_documents:
        assert bound.document.segments and all("SYNTHETIC" in segment.text or segment.text
                                                for segment in bound.document.segments)
    payload = report_payload(model, ())
    assert all("Context only" in source["use"] for source in payload["context_only_sources"])


@pytest.mark.parametrize("scenario", ["gap", "exception"])
@pytest.mark.parametrize("received", [False, True])
def test_report_separates_customer_criteria_and_preserves_source_roles(scenario, received):
    from dataclasses import replace
    from src.guided_assessment_demo import SourceRole, source_role

    model = build_demo(scenario, received)
    target = rows(model)["ENC-01"]
    history = record_action(model, (), target.requirement_id, "Create Finding", "Retain exact source roles.")
    payload = report_payload(model, history)
    policies = payload["customer_policy_sources"]
    assert {s["document_id"] for s in policies} == {"tls-customer-policy", "customer-access-policy"}
    assert all(s["source_role"] == SourceRole.CUSTOMER_POLICY for s in policies)
    assert all(s["source_role"] != SourceRole.CUSTOMER_POLICY for s in payload["context_only_sources"])
    sources = {b.source.document_id: b for b in model.documents + model.context_documents}
    for source in policies:
        bound = sources[source["document_id"]]
        assert source["provenance"] == bound.source.origin
        assert source["source_fingerprint"] == bound.fingerprint
        assert source["segments"] == [{"location": s.location, "quote": s.text} for s in bound.document.segments]
        # Role comes from fixture provenance, never the display filename.
        renamed = replace(bound, document=replace(bound.document, filename="vendor-scan.txt"))
        assert source_role(renamed) == SourceRole.CUSTOMER_POLICY
    for row in payload["requirements"]:
        assert all(c["source_role"] != SourceRole.CUSTOMER_POLICY for c in row["citations"])
        assert all(c["source_role"] == SourceRole.CUSTOMER_POLICY for c in row["customer_policy_citations"])
        for citation in row["citations"] + row["customer_policy_citations"]:
            bound = sources[citation["document_id"]]
            assert citation["provenance"] == bound.source.origin
            assert (citation["location"], citation["quote"]) in {(s.location, s.text) for s in bound.document.segments}
    for entry in payload["analyst_actions"] + payload["findings"]:
        for citation in entry["citations"]:
            bound = sources[citation["document_id"]]
            assert citation["source_role"] == source_role(bound)
            assert citation["provenance"] == bound.source.origin
    assert all(row["requirement_id"] != "IAM-01" for row in payload["requirements"])


def test_risk_inputs_reuse_inherent_scoring_but_never_derive_effectiveness_from_demo_accept():
    normal, limited = build_demo(), build_demo(risk_profile=RISK_PROFILES[1])
    assert (normal.inherent_score, normal.inherent_rating) == (58, "High")
    assert (limited.inherent_score, limited.inherent_rating) == (36, "Moderate")
    assert len(normal.risk_drivers) == len(limited.risk_drivers) == 8
    for model in (normal, limited):
        assert "retain " + model.inherent_rating in model.residual_recommendation
        assert "non-authoritative" in model.residual_recommendation
        assert "No residual score" in model.residual_recommendation
    actions = tuple()
    for row in normal.worklist.rows:
        actions = record_action(normal, actions, row.requirement_id, "Accept", "Accept the draft proposal for independent review.")
    assert report_payload(normal, actions)["risk"] == report_payload(normal, ())["risk"]


def test_illustrative_residual_drivers_follow_actual_gaps_without_hiding_tls_exception():
    first, replayed = build_demo("exception"), build_demo("exception", True)
    assert "Missing or insufficient specific evidence needs: 1." in first.residual_drivers
    assert "Missing or insufficient specific evidence needs: 0." in replayed.residual_drivers
    assert "Specific evidence needs awaiting analyst validation: 5." in replayed.residual_drivers
    assert any("ENC-02.TLS" in driver and "needs review" in driver for driver in first.residual_drivers)
    assert any("ENC-02.TLS" in driver and "needs review" in driver for driver in replayed.residual_drivers)
    assert report_payload(replayed, ())["risk"]["residual_drivers"] == list(replayed.residual_drivers)
    assert not any(fact.confirmed for row in replayed.worklist.rows for fact in row.review.facts)


@pytest.mark.parametrize("arguments", [
    {"scenario_id": "unknown"}, {"scenario_id": None}, {"scenario_id": True},
    {"evidence_received": "yes"}, {"evidence_received": 1},
    {"risk_profile": "Unknown"}, {"risk_profile": None},
])
def test_unregistered_demo_inputs_are_rejected(arguments):
    with pytest.raises(ValueError):
        build_demo(**arguments)


@pytest.mark.parametrize("invalid", [None, 123, "", " ", "x" * 1201, " " * 1200 + "x", "bad\x00text", "bad\x7ftext"])
def test_action_requires_explicit_bounded_rationale(invalid):
    model = build_demo()
    with pytest.raises(ValueError):
        record_action(model, (), model.worklist.rows[0].requirement_id, "Accept", invalid)


@pytest.mark.parametrize("requirement,action", [("unknown", "Accept"), (True, "Accept"),
                                               ("ENC-02.TLS", "Approve"), ("ENC-02.TLS", None)])
def test_action_cannot_target_unknown_requirements_or_invent_approval_actions(requirement, action):
    with pytest.raises(ValueError):
        record_action(build_demo(), (), requirement, action, "Explicit reason")


def test_model_and_action_records_are_immutable():
    model = build_demo()
    action = record_action(model, (), model.worklist.rows[0].requirement_id, "Challenge", "Needs independent verification.")[0]
    with pytest.raises(FrozenInstanceError):
        model.evidence_received = True
    with pytest.raises(FrozenInstanceError):
        action.action = "Approve"


def test_pure_demo_composition_and_report_work_with_db_and_network_operations_blocked(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Synthetic guided demo must not perform database or network I/O")
    monkeypatch.setattr(sqlite3, "connect", blocked)
    monkeypatch.setattr(sqlalchemy, "create_engine", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    model = build_demo("exception", True)
    action = record_action(model, (), rows(model)["ENC-01"].requirement_id,
                           "Request Evidence", "Request focused alternate-listener verification in this simulation only.")
    assert report_bytes(model, action).startswith(b"{\n")
