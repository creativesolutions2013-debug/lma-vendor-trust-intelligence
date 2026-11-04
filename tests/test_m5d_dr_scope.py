"""M5D scoped DR exclusion candidates with explicit evidence and negative controls."""
import pytest

from test_upload_evaluation import intake, upload, evaluation
from src.upload_assessment import build_assessment


@pytest.mark.parametrize("line", [
    "Identity federation was not tested in this exercise.",
    "Message queue was not tested in the recovery exercise.",
    "Identity service was excluded from this DR test.",
])
def test_explicit_uncovered_dependency_is_source_cited_and_unconfirmed(intake, line):
    bound = upload(intake, "Recovery exercise completed.\n" + line, "BCP-01")
    model = build_assessment(intake, (bound,))
    result = evaluation(model, "BCP-01")
    candidates = [fact for fact in result["facts"]
                  if fact["dimension"] == "scope_complete" and fact["value"] is False]
    assert len(candidates) == 1
    fact = candidates[0]
    assert fact["eligible_for_preview"]
    assert fact["direction"] == "adverse"
    assert not fact["confirmed"]
    assert fact["quote"] == line
    assert fact["document_id"] == bound.evidence.source.document_id
    assert fact["source_fingerprint"] == bound.evidence.fingerprint
    assert any(fact["source_id"].endswith(":" + str(index))
               and fact["location"] == segment.location and fact["quote"] in segment.text
               for index, segment in enumerate(bound.evidence.document.segments, 1))
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


@pytest.mark.parametrize("line", [
    "Identity federation was not tested in a hypothetical exercise.",
    "Identity federation was not tested in this exercise?",
    "The report says identity federation was not tested in this exercise.",
    "Management says identity federation was not tested in this exercise.",
    "It is false that identity federation was not tested in this exercise.",
    "It was reported that identity federation was not tested in this exercise.",
    "Identity federation will not be tested in this exercise.",
    "Identity federation was not tested in this exercise in 2024.",
    "No identity federation was excluded from this exercise.",
])
def test_ambiguous_or_reported_omission_is_not_confirmed_current_failure(intake, line):
    result = evaluation(build_assessment(intake, (
        upload(intake, "Recovery exercise completed.\n" + line, "BCP-01"),
    )), "BCP-01")
    assert not any(f["dimension"] == "scope_complete" and f["eligible_for_preview"]
                   and f["direction"] == "adverse" for f in result["facts"])
    assert result["preview"]["outcome_if_confirmed"] != "Risk Identified"
