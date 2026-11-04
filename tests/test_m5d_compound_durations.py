"""M5D strict achieved compound-duration evidence; no partial-hours approvals."""
import pytest

from test_upload_evaluation import intake, upload, evaluation
from src.upload_assessment import build_assessment


@pytest.mark.parametrize("statement,values", [
    ("Measured RTO 3 hours 25 minutes.", {"achieved_rto_minutes": 205}),
    ("Observed RPO 1 hour and 15 minutes.", {"achieved_rpo_minutes": 75}),
    ("Achieved RTO 4 hours and 30 minutes; actual RPO 1 hour and 30 minutes.",
     {"achieved_rto_minutes": 270, "achieved_rpo_minutes": 90}),
])
def test_strict_compound_durations_are_complete_unconfirmed_metrics(intake, statement, values):
    bound = upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    facts = {fact["dimension"]: fact for fact in result["facts"]
             if fact["dimension"].startswith("achieved_")}
    assert {key: fact["value"] for key, fact in facts.items()} == values
    for fact in facts.values():
        assert fact["eligible_for_preview"]
        assert fact["confirmed"] is False
        assert fact["document_id"] == bound.evidence.source.document_id
        assert fact["source_fingerprint"] == bound.evidence.fingerprint
        assert any(fact["source_id"].endswith(":" + str(i)) and
                   fact["location"] == segment.location and fact["quote"] in segment.text
                   for i, segment in enumerate(bound.evidence.document.segments, 1))
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


@pytest.mark.parametrize("statement", [
    "Target RTO 4 hours 30 minutes.",
    "Planned RTO 4 hours 30 minutes.",
    "Measured RTO approximately 4 hours 30 minutes.",
    "Measured RTO 4 hours and 70 minutes.",
    "Measured RTO 4 hours 30 minutes, unless failover is slow.",
    "Measured RTO 4 hours 30 minutes and RPO 1 hour 20 minutes.",
    "RTO 4 hours 30 minutes was not measured.",
    "Observed RTO 4 hours plus 30 minutes.",
    "Measured RTO 4 hours (30 minutes extra).",
])
def test_ambiguous_compound_durations_never_partially_compare(intake, statement):
    result = evaluation(build_assessment(intake, (
        upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01"),
    )), "BCP-01")
    assert not any(f["dimension"].startswith("achieved_") for f in result["facts"])
    assert not any(f["eligible_for_preview"] and f["direction"] == "adverse"
                   for f in result["facts"])


def test_compound_duration_with_stale_date_cannot_be_current_exception(intake):
    result = evaluation(build_assessment(intake, (
        upload(intake, "Recovery exercise completed.\nMeasured RTO 4 hours 30 minutes.",
               "BCP-01", date="2024-01-01"),
    )), "BCP-01")
    assert any(f["dimension"] == "achieved_rto_minutes" and f["value"] == 270
               for f in result["facts"])
    assert not any(f["eligible_for_preview"] for f in result["facts"])


@pytest.mark.parametrize("statement", [
    "Measured RTO 4 hours 30 minutes but with an additional 45 minutes for restoration.",
    "Observed RPO 1 hour 10 minutes but another 20 minutes for replay.",
    "Measured RTO 3 hours 30 minutes; plus 40 minutes for dependent services.",
    "Measured RTO 4 hours 30 minutes; restoration required a further 45 minutes.",
    "Observed RPO 1 hour 10 minutes; 20 minutes extra for replay.",
    "Measured RTO 4 hours 30 minutes; an additional 45 minutes for restoration was required after the observed RPO.",
    "Measured RTO 4 hours 30 minutes; restoration required 45 more minutes.",
])
def test_split_duration_addendum_never_becomes_eligible_comparison(intake, statement):
    result = evaluation(build_assessment(intake, (
        upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01"),
    )), "BCP-01")
    assert not any(f["direction"] == "adverse" and f["eligible_for_preview"]
                   for f in result["facts"])
    assert result["preview"]["outcome_if_confirmed"] != "Risk Identified"


def test_independently_measured_rpo_after_but_does_not_suppress_adverse_rto(intake):
    result = evaluation(build_assessment(intake, (
        upload(intake, "Recovery exercise completed.\n"
               "Achieved RTO 300 minutes but achieved RPO 30 minutes.", "BCP-01"),
    )), "BCP-01")
    assert any(f["dimension"] == "achieved_rto_minutes" and f["value"] == 300
               and f["direction"] == "adverse" and f["eligible_for_preview"]
               for f in result["facts"])
    assert result["preview"]["outcome_if_confirmed"] == "Risk Identified"


def test_other_metric_addendum_must_not_hide_independent_rto_breach(intake):
    line = ("Recovery exercise completed.\nMeasured RTO 4 hours 30 minutes; "
            "achieved RPO 30 minutes plus an additional 5 minutes.")
    bound = upload(intake, line, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    rto = [f for f in result["facts"] if f["dimension"] == "achieved_rto_minutes"
           and f["value"] == 270]
    assert len(rto) == 1 and rto[0]["eligible_for_preview"]
    assert rto[0]["direction"] == "adverse" and not rto[0]["confirmed"]
    assert result["preview"]["outcome_if_confirmed"] == "Risk Identified"
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


@pytest.mark.parametrize("statement", [
    "Measured RTO 4 hours 30 minutes; achieved RPO 30 minutes; an additional 5 minutes for RPO replay.",
    "Measured RTO 4 hours 30 minutes; achieved RPO 30 minutes but an additional 5 minutes for replay.",
])
def test_detached_other_metric_addendum_does_not_hide_rto_breach(intake, statement):
    bound = upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    assert any(f["dimension"] == "achieved_rto_minutes" and f["value"] == 270
               and f["direction"] == "adverse" and f["eligible_for_preview"]
               and not f["confirmed"] for f in result["facts"])
    assert result["preview"]["outcome_if_confirmed"] == "Risk Identified"
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


@pytest.mark.parametrize("statement,eligible", [
    ("Measured RTO 3 hours 30 minutes; achieved RPO 30 minutes; an additional 60 minutes for RTO restoration.", False),
    ("Measured RTO 4 hours 30 minutes; we achieved RPO 30 minutes; an additional 5 minutes for RPO replay.", True),
    ("Measured RTO 4 hours 30 minutes; RPO 30 minutes was achieved; an additional 5 minutes for RPO replay.", True),
])
def test_explicit_and_inherited_metric_ownership(intake, statement, eligible):
    bound = upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    rto = [f for f in result["facts"] if f["dimension"] == "achieved_rto_minutes"]
    assert len(rto) == 1
    assert rto[0]["eligible_for_preview"] is eligible
    assert rto[0]["confirmed"] is False
    assert rto[0]["quote"] == statement
    assert rto[0]["document_id"] == bound.evidence.source.document_id
    assert (result["preview"]["outcome_if_confirmed"] == "Risk Identified") is eligible
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


@pytest.mark.parametrize("statement", [
    "Measured RTO 3 hours 30 minutes; achieved RPO 30 minutes; RTO required an additional 60 minutes for restoration.",
    "Measured RTO 3 hours 30 minutes; restoration required 60 minutes in addition.",
])
def test_explicit_rto_and_in_addition_continuations_block_truncated_comparison(intake, statement):
    bound = upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    rto = [f for f in result["facts"] if f["dimension"] == "achieved_rto_minutes"]
    assert len(rto) == 1
    assert rto[0]["value"] == 210
    assert not rto[0]["eligible_for_preview"]
    assert not rto[0]["confirmed"]
    assert rto[0]["document_id"] == bound.evidence.source.document_id
    assert result["preview"]["outcome_if_confirmed"] != "Met"
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


def test_additive_fragment_explicitly_names_both_recovery_metrics(intake):
    statement = ("Measured RTO 3 hours 30 minutes; observed RPO 0 hours 30 minutes; "
                 "an additional 60 minutes for RTO restoration and 45 minutes for RPO replay.")
    bound = upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    facts = {f["dimension"]: f for f in result["facts"] if f["dimension"].startswith("achieved_")}
    assert facts["achieved_rto_minutes"]["value"] == 210
    assert facts["achieved_rpo_minutes"]["value"] == 30
    assert not facts["achieved_rto_minutes"]["eligible_for_preview"]
    assert not facts["achieved_rpo_minutes"]["eligible_for_preview"]
    assert all(not f["confirmed"] for f in facts.values())
    assert result["preview"]["outcome_if_confirmed"] != "Met"


def test_completed_exercise_rpo_assertion_owns_following_addendum(intake):
    statement = ("Measured RTO 4 hours 30 minutes; "
                 "the completed DR exercise achieved RPO 30 minutes; "
                 "an additional 5 minutes for replay.")
    bound = upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    assert any(f["dimension"] == "achieved_rto_minutes" and f["value"] == 270
               and f["eligible_for_preview"] and f["direction"] == "adverse"
               and not f["confirmed"] for f in result["facts"])
    assert result["preview"]["outcome_if_confirmed"] == "Risk Identified"
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


@pytest.mark.parametrize("labels", ["RTO and RPO", "RPO and RTO"])
def test_shared_preposition_additive_time_qualifies_both_metrics(intake, labels):
    statement = (
        "Measured RTO 3 hours 30 minutes; observed RPO 0 hours 30 minutes; "
        f"an additional 60 minutes for {labels}."
    )
    bound = upload(intake, "Recovery exercise completed.\n" + statement, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    values = {fact["dimension"]: fact for fact in result["facts"]
              if fact["dimension"] in ("achieved_rto_minutes", "achieved_rpo_minutes")}
    assert values["achieved_rto_minutes"]["value"] == 210
    assert values["achieved_rpo_minutes"]["value"] == 30
    for fact in values.values():
        assert not fact["eligible_for_preview"]
        assert not fact["confirmed"]
        assert fact["document_id"] == bound.evidence.source.document_id
        assert fact["quote"] == statement
    assert result["preview"]["outcome_if_confirmed"] != "Met"
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)
