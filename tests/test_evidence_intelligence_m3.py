"""Synthetic structured interpretations; no vendor data, persistence or AI."""
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta

import pytest

from src.evidence_intelligence_m3 import (
    Citation, DIMENSIONS, MfaFact, MfaRequirement, SourceSegment,
    evaluate_privileged_mfa,
)

TODAY = date(2026, 10, 20)
SCOPE = dict(service="Synthetic SaaS", environment="production",
             account_scope="all interactive privileged accounts, including emergency/local")
POLICY = MfaRequirement("customer-mfa", "1", **SCOPE,
                        allowed_methods=("sms", "totp", "fido2", "webauthn"),
                        phishing_resistant=False, require_operating=True, max_age_days=90)
QUOTES = {
    "existence": "MFA is implemented for all scoped accounts.",
    "method": "All scoped authentication uses TOTP with a password; implementation was tested.",
    "enforcement": "All scoped accounts must authenticate with MFA; no exclusions exist.",
    "operating": "The test exercised all scoped authentication paths successfully.",
    "fallback_safe": "No weaker fallback path exists in the tested inventory.",
    "recovery_safe": "Recovery preserves the same authentication threshold for every scoped account.",
    "exceptions_absent": "The test found no exceptions across the scoped population.",
}


def package(**changes):
    facts = []
    sources = {}
    for dimension in DIMENSIONS:
        quote = QUOTES[dimension]
        sources[dimension] = SourceSegment("synthetic.txt", f"Section {dimension}", quote)
        facts.append(MfaFact(dimension, "totp" if dimension == "method" else True,
                             Citation(dimension, quote), **SCOPE,
                             observed_on=TODAY, evidence_kind="test",
                             implementation_evidenced=True, multifactor=True))
    return [replace(f, **changes) for f in facts], sources


def evaluate(facts=None, sources=None, policy=POLICY):
    if facts is None:
        facts, sources = package()
    return evaluate_privileged_mfa(policy, facts, sources or {}, as_of=TODAY)


def change(facts, dimension, **values):
    return [replace(f, **values) if f.dimension == dimension else f for f in facts]


def method_package(method, **properties):
    facts, sources = package()
    quote = f"Tested {method}: implementation and authentication properties are documented here."
    sources["method"] = SourceSegment("synthetic.txt", "Method test", quote)
    facts = change(facts, "method", value=method, citation=Citation("method", quote), **properties)
    return facts, sources


def test_basic_mfa_is_provisional_and_carries_policy_and_original_sources():
    result = evaluate()
    assert result.outcome == "Met"
    assert result.provisional and result.review_required
    assert result.requirement.requirement_id == "PAM-01.MFA"
    assert result.requirement.parent_control_id == "PAM-01"
    assert result.requirement == POLICY and result.as_of == TODAY
    assert result.evaluator_version == "MFA-1.0"
    assert dict(result.sources)["method"].text == QUOTES["method"]
    with pytest.raises(FrozenInstanceError):
        result.review_required = False


@pytest.mark.parametrize("method", ["sms", "totp"])
@pytest.mark.parametrize("resistant,outcome", [(False, "Met"), (True, "Risk Identified")])
def test_weak_methods_against_customer_thresholds(method, resistant, outcome):
    facts, sources = method_package(method)
    assert evaluate(facts, sources, replace(POLICY, phishing_resistant=resistant)).outcome == outcome


@pytest.mark.parametrize("method", ["fido2", "webauthn", "customer-equivalent"])
def test_qualifying_phishing_resistant_implementations(method):
    facts, sources = method_package(method, origin_bound=True, verifier_bound=True)
    policy = replace(POLICY, phishing_resistant=True,
                     allowed_methods=(method,),
                     approved_equivalents=(method,) if method == "customer-equivalent" else ())
    assert evaluate(facts, sources, policy).outcome == "Met"


@pytest.mark.parametrize("properties", [
    {"implementation_evidenced": None}, {"origin_bound": None},
    {"verifier_bound": None}, {"multifactor": None},
])
def test_brand_name_or_missing_properties_is_not_qualification(properties):
    facts, sources = method_package("fido2", origin_bound=True, verifier_bound=True)
    facts = change(facts, "method", **properties)
    assert evaluate(facts, sources, replace(POLICY, phishing_resistant=True)).outcome == "Partially Met"


@pytest.mark.parametrize("properties", [{"origin_bound": False}, {"verifier_bound": False}, {"multifactor": False}])
def test_nonqualifying_implementation(properties):
    facts, sources = method_package("webauthn", origin_bound=True, verifier_bound=True)
    facts = change(facts, "method", **properties)
    assert evaluate(facts, sources, replace(POLICY, phishing_resistant=True)).outcome == "Risk Identified"


def test_unknown_method_is_uncertainty_not_failure():
    facts, sources = method_package("unknown-brand")
    assert evaluate(facts, sources).outcome == "Partially Met"


def test_known_disallowed_method_is_adverse():
    facts, sources = method_package("sms")
    assert evaluate(facts, sources, replace(POLICY, allowed_methods=("totp",))).outcome == "Risk Identified"


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_missing_dimension_prevents_met(dimension):
    facts, sources = package()
    assert evaluate([f for f in facts if f.dimension != dimension], sources).outcome == "Partially Met"


@pytest.mark.parametrize("dimension", ["existence", "enforcement", "fallback_safe", "recovery_safe", "exceptions_absent", "operating"])
def test_explicit_adverse_facts_are_preserved(dimension):
    facts, sources = package()
    quote = f"Testing found the {dimension} threshold was NOT met for scoped accounts."
    sources["adverse"] = SourceSegment("exception.txt", "Line 1", quote)
    facts = change(facts, dimension, value=False, citation=Citation("adverse", quote))
    result = evaluate(facts, sources)
    assert result.outcome == "Risk Identified"
    assert any(a.fact.citation.quote == quote and a.status == "adverse" for a in result.facts)


def test_conflicts_survive_supporting_evidence_and_input_order():
    facts, sources = package()
    quote = "Contrary test: MFA enforcement is disabled for local administrators."
    sources["contrary"] = SourceSegment("same-name.txt", "Line 1", quote)
    facts.append(replace(facts[2], value=False, citation=Citation("contrary", quote)))
    for ordered in (facts, list(reversed(facts))):
        result = evaluate(ordered, sources)
        assert result.outcome == "Needs Review"
        assert dict((d.dimension, d.status) for d in result.dimensions)["enforcement"] == "conflict"
        assert len(result.facts) == len(facts)


@pytest.mark.parametrize("kind", ["policy", "assertion", "configuration"])
def test_intent_and_configuration_are_not_operating_proof(kind):
    facts, sources = package()
    assert evaluate(change(facts, "operating", evidence_kind=kind), sources).outcome == "Partially Met"


def test_customer_can_explicitly_omit_operating_requirement():
    facts, sources = package()
    facts = [f for f in facts if f.dimension != "operating"]
    assert evaluate(facts, sources, replace(POLICY, require_operating=False)).outcome == "Met"


@pytest.mark.parametrize("age,outcome", [(90, "Met"), (91, "Needs Review"), (-1, "Needs Review")])
def test_freshness_boundaries(age, outcome):
    facts, sources = package(observed_on=TODAY - timedelta(days=age))
    assert evaluate(facts, sources).outcome == outcome


def test_unknown_date_and_stale_adverse_fact_are_retained_without_current_failure():
    facts, sources = package(observed_on=None, value=False)
    facts = [f for f in facts if f.dimension != "method"]
    result = evaluate(facts, sources)
    assert result.outcome == "Needs Review"
    assert len(result.facts) == len(facts)
    assert all(a.status == "unknown" for a in result.facts)


@pytest.mark.parametrize("scope", [dict(service="other"), dict(environment="dev"),
                                   dict(account_scope="machine accounts")])
def test_scope_mismatch_never_supports_or_fails_target(scope):
    facts, sources = package(**scope)
    result = evaluate(facts, sources)
    assert result.outcome == "Evidence Missing"
    assert all(a.status == "excluded" for a in result.facts)


@pytest.mark.parametrize("changes", [{"service": None}, {"uncertainty": "Scope ambiguous"}, {"value": None}])
def test_unknowns_do_not_become_failures(changes):
    facts, sources = package(**changes)
    assert evaluate(facts, sources).outcome == "Needs Review"


@pytest.mark.parametrize("quote", ["Invented quotation", "", "  ", QUOTES["existence"].lower(),
                                   QUOTES["existence"].replace(" ", "  ")])
def test_invalid_or_altered_citation_rejects_entire_evaluation(quote):
    facts, sources = package()
    facts = change(facts, "existence", citation=Citation("existence", quote))
    with pytest.raises(ValueError, match="exactly"):
        evaluate(facts, sources)


def test_wrong_segment_cannot_support_a_fact():
    facts, sources = package()
    facts = change(facts, "existence", citation=Citation("method", QUOTES["existence"]))
    with pytest.raises(ValueError, match="exactly"):
        evaluate(facts, sources)


def test_empty_evidence_and_replay():
    assert evaluate([], {}).outcome == "Evidence Missing"
    facts, sources = package()
    assert evaluate(facts, sources) == evaluate(iter(facts), sources)


@pytest.mark.parametrize("changes", [dict(version=""), dict(max_age_days=-1),
    dict(max_age_days=True), dict(allowed_methods=()), dict(allowed_methods=("brand",)),
    dict(approved_equivalents=("sms",)), dict(phishing_resistant="yes")])
def test_invalid_policy_never_uses_implicit_defaults(changes):
    with pytest.raises(ValueError):
        replace(POLICY, **changes)


@pytest.mark.parametrize("changes", [dict(dimension="approval"), dict(value="true", dimension="existence"),
    dict(evidence_kind="AI conclusion"), dict(observed_on="2026-10-20"), dict(origin_bound="yes")])
def test_invalid_structured_facts_fail_closed(changes):
    facts, sources = package()
    facts[0] = replace(facts[0], **changes)
    with pytest.raises(ValueError):
        evaluate(facts, sources)


def test_legacy_control_meanings_and_m2_are_unchanged():
    from src.tiering import CONTROL_LIBRARY
    from src.evidence_intelligence_m2 import PILOT_REQUIREMENTS
    assert CONTROL_LIBRARY["IAM-01"].requirement == "Identity and access management"
    assert CONTROL_LIBRARY["PAM-01"].requirement == "Privileged access management"
    assert PILOT_REQUIREMENTS[0].requirement_id == "IAM-01"  # Historical M2 only.
    assert evaluate().requirement.requirement_id != PILOT_REQUIREMENTS[0].requirement_id


def test_stale_exception_cannot_be_erased_by_current_support():
    facts, sources = package()
    quote = "Historical test: password-only recovery bypassed MFA."
    sources["old"] = SourceSegment("history.txt", "Line 2", quote)
    facts.append(replace(facts[5], value=False, observed_on=TODAY-timedelta(days=91),
                         citation=Citation("old", quote)))
    result = evaluate(facts, sources)
    assert result.outcome == "Partially Met"
    assert result.facts[-1].status == "unknown"
    assert result.facts[-1].fact.value is False


def test_same_filename_and_location_have_distinct_source_identity():
    facts, sources = package()
    sources = {key: replace(source, filename="same.txt", location="Page 1")
               for key, source in sources.items()}
    result = evaluate(facts, sources)
    assert result.outcome == "Met"
    assert len(result.sources) == len(DIMENSIONS)


def test_unapproved_equivalent_is_unknown_even_with_implementation_properties():
    facts, sources = method_package("unapproved", origin_bound=True, verifier_bound=True)
    assert evaluate(facts, sources, replace(POLICY, phishing_resistant=True)).outcome == "Partially Met"


def test_basic_fido_requires_multiple_factors_too():
    facts, sources = method_package("fido2", multifactor=False)
    assert evaluate(facts, sources).outcome == "Risk Identified"


def test_source_metadata_and_evaluation_date_are_required():
    facts, sources = package()
    sources["method"] = replace(sources["method"], location="")
    with pytest.raises(ValueError, match="exactly"):
        evaluate(facts, sources)
    with pytest.raises(ValueError, match="date"):
        evaluate_privileged_mfa(POLICY, [], {}, as_of=None)


def test_m3_has_no_governed_or_network_dependencies():
    import ast
    from pathlib import Path
    tree = ast.parse(Path("src/evidence_intelligence_m3.py").read_text())
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"dataclasses", "datetime", "typing"}
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
