"""M5D focused port-acceptance regressions using synthetic, source-cited evidence.

Test nearby unsafe constructions to prevent a false positive from a word match.
These cases are deliberately different from the frozen M5C benchmark.
"""
import pytest

from test_upload_evaluation import intake, upload, evaluation
from src.upload_assessment import build_assessment


@pytest.mark.parametrize("statement,subject,version", [
    ("Connections through production port 8444 accept TLS 1.1 connections.", "production port 8444", 11),
    ("Traffic on gateway port 9444 currently allows TLS 1.0.", "gateway port 9444", 10),
    ("Client sessions on alternate port 8111 still accept TLS 1.2.", "alternate port 8111", 12),
])
def test_explicit_port_acceptance_is_only_an_unconfirmed_candidate(intake, statement, subject, version):
    bound = upload(intake, statement)
    model = build_assessment(intake, (bound,))
    result = evaluation(model)
    facts = [fact for fact in result["facts"]
             if fact["dimension"] == "enabled_version" and fact["value"] == version]
    assert len(facts) == 1
    fact = facts[0]
    assert fact["subject"] == subject
    assert fact["eligible_for_preview"]
    assert fact["direction"] == ("adverse" if version < 12 else "support")
    assert fact["confirmed"] is False
    assert fact["quote"] == statement
    assert fact["document_id"] == bound.evidence.source.document_id
    assert fact["source_fingerprint"] == bound.evidence.fingerprint
    segment = next(segment for index, segment in enumerate(bound.evidence.document.segments, 1)
                   if fact["source_id"].endswith(":" + str(index)))
    assert fact["location"] == segment.location and fact["quote"] in segment.text
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


@pytest.mark.parametrize("statement", [
    "Traffic on port 8444 may accept TLS 1.0 connections.",
    "Traffic on port 8444 could accept TLS 1.0 connections.",
    "Traffic on port 8444 should accept TLS 1.0 connections.",
    "Traffic on port 8444 did not accept TLS 1.0 connections.",
    "Traffic on port 8444 accepts TLS 1.0 connections if fallback is enabled.",
    "Traffic on port 8444 accepted TLS 1.0 connections previously.",
    "Traffic on port 8444 supports TLS 1.0 connections.",
    "Traffic on port 8444 accepts TLS 1.0 and may allow TLS 1.2.",
    "Traffic on port 99999 accepts TLS 1.0 connections.",
])
def test_port_wording_does_not_infer_current_adverse_activation(intake, statement):
    result = evaluation(build_assessment(intake, (upload(intake, statement),)))
    assert not any(f["eligible_for_preview"] and f["direction"] == "adverse"
                   for f in result["facts"])
    assert result["preview"]["outcome_if_confirmed"] != "Risk Identified"


def test_explicit_port_statement_in_stale_source_is_not_current_evidence(intake):
    result = evaluation(build_assessment(intake, (
        upload(intake, "Traffic on port 8444 still accepts TLS 1.0 connections.",
               date="2024-01-01"),
    )))
    assert any(f["dimension"] == "enabled_version" for f in result["facts"])
    assert not any(f["eligible_for_preview"] for f in result["facts"])
