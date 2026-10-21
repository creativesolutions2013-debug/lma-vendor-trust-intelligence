"""Independent synthetic bundle oracle, not an extraction accuracy benchmark.

Unreviewed proposals deliberately overclaim with exact quotes. Reviewed cases
use explicit manual semantic dispositions; no model or live API is involved.
"""
from dataclasses import replace
from datetime import date
import json
from pathlib import Path

import pytest

from src.evidence_fact_validation import (
    BundleReview, EvidenceInput, FactReview, ProposedFact, SignalDisposition,
    bind_evidence, fact_fingerprint, segment_id, validate_and_evaluate_mfa,
)
from src.evidence_intelligence_m3 import Citation, DIMENSIONS, MfaFact, MfaRequirement

CORPUS = json.loads((Path(__file__).parent / "fixtures/m3b_scenarios.json").read_text())
TODAY = date.fromisoformat(CORPUS["as_of"])
POLICY = MfaRequirement("synthetic-customer-mfa", "1", "Acme Analytics", "production",
                        "human administrators", ("fido2", "webauthn"), True, True,
                        CORPUS["max_age_days"])


def inputs(scenario):
    return tuple(EvidenceInput(
        row["id"], row["filename"], row["text"].encode(), "synthetic-v1",
        "synthetic analyst upload", TODAY, row["service"], row["environment"],
        row["account_scope"], date.fromisoformat(row["observed_on"]), row["evidence_kind"],
    ) for row in scenario["documents"])


def proposal(document, dimension, line, *, value=True, fact_id=None, quote=None, **changes):
    bound = bind_evidence(document)
    ordinal, part = next((i, part) for i, part in enumerate(bound.document.segments, 1)
                         if part.location == f"Line {line}")
    fields = dict(service=document.service, environment=document.environment,
                  account_scope=document.account_scope, observed_on=document.observed_on,
                  evidence_kind=document.evidence_kind)
    if dimension == "method":
        value = "fido2" if value is True else value
        fields.update(implementation_evidenced=True, origin_bound=True, verifier_bound=True,
                      multifactor=True, authentication_path="primary-admin", active=True)
    fields.update(changes)
    fact = MfaFact(dimension, value, Citation(segment_id(document.document_id, ordinal),
                                             quote or part.text), **fields)
    return ProposedFact(fact_id or dimension, fact, bound.fingerprint, part.location)


def strong_proposals(documents):
    by_id = {item.document_id: item for item in documents}
    config = by_id.get("configuration", by_id.get("operating-test"))
    test = by_id.get("operating-test", config)
    # The quotation is an anchor into the full source reviewed by the analyst.
    if config and config.filename == "production-idp-export.txt":
        return [proposal(config, "existence", 3), proposal(config, "method", 4),
                proposal(config, "enforcement", 3), proposal(test, "operating", 3),
                proposal(config, "fallback_safe", 6), proposal(config, "recovery_safe", 7),
                proposal(config, "exceptions_absent", 8)]
    return None


def overclaims(documents):
    """Adversarial extraction stub: perfect quotes, invented positive meanings."""
    source = next((item for item in documents if item.evidence_kind == "test"),
                  next((item for item in documents if item.evidence_kind == "configuration"), documents[-1]))
    return [proposal(source, dimension, 3) for dimension in DIMENSIONS]


def review(item, decision="supported", classification=None):
    if classification is None:
        classification = {"test": "operating_test", "configuration": "implementation_evidence",
                          "policy": "policy_assertion", "assertion": "policy_assertion"}[item.fact.evidence_kind]
    return FactReview(fact_fingerprint(item), decision, classification, "synthetic analyst",
                      TODAY, "Manual review of the full source and stated administrator/path inventory.")


def finalize(documents, proposals, reviews, scenario):
    initial = validate_and_evaluate_mfa(POLICY, documents, proposals, as_of=TODAY, fact_reviews=reviews)
    material = {(item["document_id"], item["location"]) for item in (
        scenario["material_exceptions"] + scenario.get("corroborating_material_locations", []))}
    dispositions = tuple(SignalDisposition(
        signal.signal_id, (signal.source_id.split(":")[0], signal.location) in material,
        "Manual synthetic oracle: explicit weakness." if
        (signal.source_id.split(":")[0], signal.location) in material else
        "Manual synthetic oracle: negated finding or another nonmaterial lexical match.",
    ) for signal in initial.signals)
    bundle = BundleReview(initial.bundle_fingerprint, "synthetic analyst", TODAY,
                          scenario["review_notes"], dispositions)
    return validate_and_evaluate_mfa(POLICY, documents, proposals, as_of=TODAY,
                                     fact_reviews=reviews, bundle_review=bundle)


def reviewed_case(scenario):
    documents = inputs(scenario)
    sid = scenario["id"]
    by_id = {item.document_id: item for item in documents}
    if sid == "strong_fido2_full_population":
        proposed = strong_proposals(documents)
        reviews = [review(item) for item in proposed]
    elif sid in {"sms_active_administrative_path", "totp_active_administrative_path"}:
        method = "sms" if sid.startswith("sms") else "totp"
        proposed = [proposal(by_id["configuration"], "method", 3, value=method,
                             origin_bound=False, verifier_bound=False)]
        reviews = [review(proposed[0], classification="explicit_exception")]
    elif sid == "contradictory_policy_configuration_and_test":
        test = by_id["operating-test"]
        proposed = [proposal(test, "enforcement", 3),
                    proposal(by_id["configuration"], "enforcement", 3, value=False,
                             fact_id="local-account-exclusion")]
        reviews = [review(proposed[0]), review(proposed[1], classification="conflicting_statement")]
    elif sid == "outdated_operating_evidence":
        proposed = strong_proposals(documents)
        reviews = [review(item) for item in proposed]
    elif sid == "similarly_named_service_scope_mismatch":
        proposed = overclaims(documents)
        # Adversarial target-service relabeling cannot replace declared scope.
        proposed = [replace(item, fact=replace(item.fact, service=POLICY.service)) for item in proposed]
        reviews = [review(item) for item in proposed]
    elif sid in {"omitted_break_glass_bypass", "sms_recovery_bypasses_primary_method"}:
        # Extraction omits the adverse runbook entirely; scanner still sees it.
        proposed = [proposal(by_id["configuration"], "method", 4)]
        reviews = [review(proposed[0])]
    elif sid == "policy_and_assertion_only":
        proposed = overclaims(documents)
        # Even a supported policy assertion cannot establish implementation.
        reviews = [review(item) for item in proposed]
    elif sid == "unknown_method":
        proposed = [proposal(by_id["vendor-response"], "method", 2, value="secure-challenge",
                             implementation_evidenced=None, origin_bound=None,
                             verifier_bound=None, multifactor=None)]
        reviews = [review(proposed[0])]
    else:
        proposed = overclaims(documents)
        reviews = [review(item, "ambiguous", "unsupported_interpretation") for item in proposed]
    return finalize(documents, proposed, reviews, scenario)


@pytest.mark.parametrize("scenario", CORPUS["scenarios"], ids=lambda s: s["id"])
def test_unreviewed_exact_quote_overclaims_never_establish_positive_assurance(scenario):
    documents = inputs(scenario)
    proposed = overclaims(documents)
    result = validate_and_evaluate_mfa(POLICY, documents, proposed, as_of=TODAY)
    assert all(item.citation_verified for item in result.facts)
    assert not any(item.status == "validated" for item in result.facts)
    assert result.evaluation.outcome == "Needs Review"
    assert result.provisional and result.review_required
    for exception in scenario["material_exceptions"] + scenario.get("corroborating_material_locations", []):
        assert any(signal.source_id.startswith(exception["document_id"] + ":")
                   and signal.location == exception["location"] and signal.status == "needs_review"
                   for signal in result.signals)


@pytest.mark.parametrize("scenario", CORPUS["scenarios"], ids=lambda s: s["id"])
def test_reviewed_scenarios_preserve_thresholds_conflicts_scope_and_currency(scenario):
    result = reviewed_case(scenario)
    assert result.bundle_review_valid
    assert (result.evaluation.outcome == "Met") is scenario["expected_positive"]
    if scenario["id"] in {"unknown_method", "fido2_mention_only", "sampled_test_not_complete_coverage",
                           "outdated_operating_evidence", "similarly_named_service_scope_mismatch",
                           "policy_and_assertion_only"}:
        assert result.evaluation.outcome != "Risk Identified"
    if scenario["id"] == "contradictory_policy_configuration_and_test":
        assert next(d for d in result.evaluation.dimensions if d.dimension == "enforcement").status == "conflict"
    for exception in scenario["material_exceptions"] + scenario.get("corroborating_material_locations", []):
        assert any(signal.source_id.startswith(exception["document_id"] + ":")
                   and signal.location == exception["location"] and signal.status == "material"
                   for signal in result.signals)


def test_regression_metrics(capsys):
    results = [reviewed_case(scenario) for scenario in CORPUS["scenarios"]]
    negatives = sum(not scenario["expected_positive"] for scenario in CORPUS["scenarios"])
    incorrect = sum(result.evaluation.outcome == "Met" and not scenario["expected_positive"]
                    for scenario, result in zip(CORPUS["scenarios"], results))
    exceptions = sum(len(scenario["material_exceptions"]) for scenario in CORPUS["scenarios"])
    missed = sum(not any(signal.source_id.startswith(exception["document_id"] + ":")
                         and signal.location == exception["location"] and signal.status == "material"
                         for signal in result.signals)
                 for scenario, result in zip(CORPUS["scenarios"], results)
                 for exception in scenario["material_exceptions"])
    retained = sum(item.status == "validated" for item in results[0].facts)
    metrics = {"scenarios": len(results), "documents": sum(len(s["documents"]) for s in CORPUS["scenarios"]),
               "incorrect_positive_recommendations": incorrect, "negative_scenarios": negatives,
               "missed_material_exceptions": missed, "material_exceptions": exceptions,
               "reviewed_strong_facts_retained": retained, "strong_facts": len(results[0].facts),
               "reviewed_positive_controls": sum(r.evaluation.outcome == "Met" for r in results),
               "material_signals_including_corroboration": sum(s.status == "material" for r in results for s in r.signals),
               "nonmaterial_lexical_signals": sum(s.status == "dismissed_by_analyst" for r in results for s in r.signals)}
    assert incorrect == missed == 0
    assert retained == 7
    assert metrics["reviewed_positive_controls"] == 1
    with capsys.disabled():
        print("\nM3B synthetic regression metrics: " + json.dumps(metrics, sort_keys=True))


def test_scanner_is_triage_and_has_known_language_blind_spots():
    """A lexical miss remains reviewable via the mandatory complete-bundle gate."""
    source = EvidenceInput("euphemism", "memo.txt", b"The emergency route grants access after a single secret.",
                           "1", "synthetic upload", TODAY, POLICY.service, POLICY.environment,
                           POLICY.account_scope, TODAY, "assertion")
    result = validate_and_evaluate_mfa(POLICY, (source,), (), as_of=TODAY)
    assert not result.signals  # Deliberately records a known scanner limitation.
    assert not result.bundle_review_valid and result.evaluation.outcome == "Needs Review"
