"""Synthetic regressions for the M3B citation and human semantic-review boundary."""
from dataclasses import replace
from datetime import date, timedelta

import pytest

from src.evidence_fact_validation import (
    BundleReview, EvidenceInput, FactReview, ProposedFact, SignalDisposition,
    bind_evidence, fact_fingerprint, segment_id, validate_and_evaluate_mfa,
)
from src.evidence_intelligence_m3 import Citation, MfaFact, MfaRequirement


AS_OF = date(2026, 10, 20)
CAPTURED = date(2026, 10, 15)
POLICY = MfaRequirement(
    "synthetic-policy", "1", "Acme Analytics", "production", "human administrators",
    ("fido2", "webauthn"), True, True, 90,
)


def source(document_id, text, *, kind="configuration", observed_on=date(2026, 10, 12)):
    return EvidenceInput(
        document_id, f"{document_id}.txt", text.encode(), "synthetic-v1",
        "synthetic analyst-upload inventory", CAPTURED, POLICY.service,
        POLICY.environment, POLICY.account_scope, observed_on, kind,
    )


def strong_package():
    """The helper's typed facts are independently readable in the quoted text."""
    configuration = source("configuration", "\n".join((
        "MFA is implemented for the complete inventory of 24 human administrators in Acme Analytics production.",
        "The active primary-admin path uses deployed FIDO2 keys plus PIN, with client origin binding and server verifier binding checked before sessions issue.",
        "All 24 administrators, including emergency accounts, are prevented from obtaining a session unless the enforced MFA challenge succeeds.",
        "The complete administrator authentication-path inventory has fallback authentication disabled.",
        "Every recovery workflow requires a replacement FIDO2 key plus PIN and the same origin and verifier checks before any administrator session is issued.",
        "The complete administrator and authentication-path inventories contain no exemptions or exceptions.",
    )))
    operating_test = source("operating-test", (
        "On 2026-10-14 the tester exercised all 24 administrator accounts and every fallback and recovery workflow; "
        "all sessions required the deployed key plus PIN and origin and verifier checks, and unauthenticated attempts failed."
    ), kind="test", observed_on=date(2026, 10, 14))
    documents = (configuration, operating_test)
    bound = {item.document_id: bind_evidence(item) for item in documents}
    dimensions = (
        ("existence", True, "configuration", 1),
        ("method", "fido2", "configuration", 2),
        ("enforcement", True, "configuration", 3),
        ("fallback_safe", True, "configuration", 4),
        ("recovery_safe", True, "configuration", 5),
        ("exceptions_absent", True, "configuration", 6),
        ("operating", True, "operating-test", 1),
    )
    proposals = []
    for dimension, value, document_id, ordinal in dimensions:
        item = bound[document_id]
        part = item.document.segments[ordinal - 1]
        method_properties = dict(
            implementation_evidenced=True, origin_bound=True, verifier_bound=True,
            multifactor=True, authentication_path="primary-admin", active=True,
        ) if dimension == "method" else {}
        fact = MfaFact(
            dimension, value, Citation(segment_id(document_id, ordinal), part.text),
            item.source.service, item.source.environment, item.source.account_scope,
            item.source.observed_on, item.source.evidence_kind, **method_properties,
        )
        proposals.append(ProposedFact(dimension, fact, item.fingerprint, part.location))
    return documents, tuple(proposals)


def semantic_reviews(proposals):
    return tuple(FactReview(
        fact_fingerprint(proposal), "supported",
        "operating_test" if proposal.fact.evidence_kind == "test" else "implementation_evidence",
        "synthetic-analyst", AS_OF,
        "Independently checked this complete typed interpretation against the full supplied source context.",
    ) for proposal in proposals)


def bundle_acknowledgment(documents, proposals, *, requirement=POLICY):
    preliminary = validate_and_evaluate_mfa(requirement, documents, proposals, as_of=AS_OF)
    return BundleReview(
        preliminary.bundle_fingerprint, "synthetic-analyst", AS_OF,
        "Reviewed every supplied document and reconciled the complete population and authentication-path inventory.",
        tuple(SignalDisposition(signal.signal_id, False,
                                "This source explicitly reports no exemptions or exceptions in its complete inventory.")
              for signal in preliminary.signals),
    )


def evaluate(documents, proposals, *, fact_reviews=(), bundle_review=None, requirement=POLICY, as_of=AS_OF):
    return validate_and_evaluate_mfa(requirement, documents, proposals, as_of=as_of,
                                   fact_reviews=fact_reviews, bundle_review=bundle_review)


def reviewed(documents, proposals):
    return evaluate(documents, proposals, fact_reviews=semantic_reviews(proposals),
                    bundle_review=bundle_acknowledgment(documents, proposals))


def test_complete_independently_reviewed_package_reaches_provisional_m3a_met():
    documents, proposals = strong_package()
    result = reviewed(documents, proposals)
    assert result.evaluation.outcome == "Met"
    assert result.bundle_review_valid
    assert all(item.citation_verified and item.status == "validated" for item in result.facts)
    assert len(result.evaluation.facts) == 7
    assert result.provisional and result.review_required
    assert result.evaluation.provisional and result.evaluation.review_required


def test_exact_supported_quotations_without_semantic_reviews_require_review():
    documents, proposals = strong_package()
    result = evaluate(documents, proposals)
    assert result.evaluation.outcome == "Needs Review"
    assert all(item.citation_verified and item.status == "needs_review" for item in result.facts)
    assert not result.evaluation.facts
    assert not result.bundle_review_valid


def test_exact_fido2_quotation_does_not_entail_supplied_implementation_properties():
    text = "Acme Analytics supports FIDO2 and MFA as optional product features; this overview does not document deployment."
    document = source("overview", text, kind="assertion")
    item = bind_evidence(document)
    fabricated_interpretation = MfaFact(
        "method", "fido2", Citation("overview:1", text), POLICY.service,
        POLICY.environment, POLICY.account_scope, document.observed_on, "assertion",
        implementation_evidenced=True, origin_bound=True, verifier_bound=True,
        multifactor=True, authentication_path="primary-admin", active=True,
    )
    proposal = ProposedFact("overclaim", fabricated_interpretation, item.fingerprint, "Line 1")
    result = evaluate((document,), (proposal,))
    assert result.facts[0].citation_verified
    assert result.facts[0].classification == "unsupported_interpretation"
    assert result.facts[0].status == "needs_review"
    assert not result.evaluation.facts
    assert result.evaluation.outcome == "Needs Review"


@pytest.mark.parametrize("change", [
    {"location": "Line 99"},
    {"source_fingerprint": "0" * 64},
    {"citation": Citation("missing:1", "MFA is implemented")},
    {"citation": Citation("configuration:1", "MFA IS implemented")},
    {"citation": Citation("configuration:2", "MFA is implemented")},
])
def test_wrong_identity_location_or_changed_exact_quote_cannot_be_reviewed_into_support(change):
    documents, proposals = strong_package()
    original = proposals[0]
    citation = change.get("citation")
    changed = replace(original, fact=replace(original.fact, citation=citation)) if citation else replace(original, **change)
    candidates = (changed,) + proposals[1:]
    result = reviewed(documents, candidates)
    assert not result.facts[0].citation_verified
    assert result.facts[0].status == "needs_review"
    assert result.evaluation.outcome == "Needs Review"


@pytest.mark.parametrize("changes", [
    {"version": "synthetic-v2"},
    {"origin": "a different uploaded source"},
    {"content": b"Replacement source text with different meaning."},
    {"filename": "another-export.txt"},
])
def test_document_identity_changes_invalidate_old_source_and_bundle_bindings(changes):
    documents, proposals = strong_package()
    reviews = semantic_reviews(proposals)
    bundle = bundle_acknowledgment(documents, proposals)
    changed = (replace(documents[0], **changes), documents[1])
    result = evaluate(changed, proposals, fact_reviews=reviews, bundle_review=bundle)
    assert not result.bundle_review_valid
    assert not result.facts[0].citation_verified
    assert result.evaluation.outcome == "Needs Review"


@pytest.mark.parametrize("changes", [
    {"version": None}, {"origin": None}, {"captured_on": None},
    {"captured_on": AS_OF + timedelta(days=1)},
    {"observed_on": AS_OF + timedelta(days=1)},
    {"observed_on": AS_OF - timedelta(days=91)},
    {"service": "Acme Analytics Labs"}, {"environment": "development"},
    {"account_scope": "three sampled human administrators"},
])
def test_missing_provenance_staleness_and_scope_limitations_survive_fresh_reviews(changes):
    documents, proposals = strong_package()
    limited_source = replace(documents[0], **changes)
    item = bind_evidence(limited_source)
    changed_proposals = tuple(
        replace(proposal, source_fingerprint=item.fingerprint,
                fact=replace(proposal.fact, service=limited_source.service,
                             environment=limited_source.environment,
                             account_scope=limited_source.account_scope,
                             observed_on=limited_source.observed_on))
        if proposal.fact.citation.source_id.startswith("configuration:") else proposal
        for proposal in proposals
    )
    result = reviewed((limited_source, documents[1]), changed_proposals)
    assert result.facts[0].citation_verified
    assert result.facts[0].status == "needs_review"
    assert result.evaluation.outcome == "Needs Review"
    assert any("provenance, freshness and scope" in item for item in result.follow_up)


@pytest.mark.parametrize("changes", [
    {"service": "Acme Analytics Labs"}, {"environment": "development"},
    {"account_scope": "human and machine administrators"},
    {"observed_on": date(2026, 10, 13)}, {"evidence_kind": "test"},
])
def test_extractor_metadata_cannot_override_declared_source_inventory(changes):
    documents, proposals = strong_package()
    changed = (replace(proposals[0], fact=replace(proposals[0].fact, **changes)),) + proposals[1:]
    result = reviewed(documents, changed)
    assert result.facts[0].citation_verified
    assert result.facts[0].status == "needs_review"
    assert any("differs from source inventory" in reason for reason in result.facts[0].reasons)
    assert result.evaluation.outcome == "Needs Review"


@pytest.mark.parametrize("changes", [
    {"value": "webauthn"}, {"origin_bound": False}, {"verifier_bound": None},
    {"multifactor": False}, {"implementation_evidenced": None},
    {"authentication_path": "recovery-admin"}, {"active": False},
])
def test_altered_interpretation_properties_invalidate_existing_fact_review(changes):
    documents, proposals = strong_package()
    reviews = semantic_reviews(proposals)
    original = proposals[1]
    changed = replace(original, fact=replace(original.fact, **changes))
    candidates = (proposals[0], changed) + proposals[2:]
    assert fact_fingerprint(changed) != fact_fingerprint(original)
    # Even a fresh acknowledgment of the bundle does not substitute for a fact review.
    result = evaluate(documents, candidates, fact_reviews=reviews,
                      bundle_review=bundle_acknowledgment(documents, candidates))
    assert result.facts[1].status == "needs_review"
    assert len(result.evaluation.facts) == 6
    assert result.evaluation.outcome == "Needs Review"


@pytest.mark.parametrize("change", ["requirement", "date", "uncited_document", "proposal"])
def test_bundle_review_is_bound_to_requirement_date_every_document_and_every_proposal(change):
    documents, proposals = strong_package()
    bundle = bundle_acknowledgment(documents, proposals)
    requirement, as_of = POLICY, AS_OF
    if change == "requirement":
        requirement = replace(POLICY, version="2")
    elif change == "date":
        as_of += timedelta(days=1)
    elif change == "uncited_document":
        documents += (source("appendix", "The current account inventory is attached for reconciliation."),)
    else:
        proposals = (replace(proposals[0], fact_id="renamed-proposal"),) + proposals[1:]
    result = evaluate(documents, proposals, fact_reviews=semantic_reviews(proposals),
                      bundle_review=bundle, requirement=requirement, as_of=as_of)
    assert not result.bundle_review_valid
    assert result.evaluation.outcome == "Needs Review"


def test_duplicate_source_and_fact_ids_raise_instead_of_overwriting():
    documents, proposals = strong_package()
    with pytest.raises(ValueError, match="Duplicate document IDs"):
        evaluate(documents + (documents[0],), proposals)
    with pytest.raises(ValueError, match="Unique nonempty proposed fact IDs"):
        evaluate(documents, proposals + (proposals[0],))


def test_duplicate_semantic_reviews_do_not_choose_one_to_accept():
    documents, proposals = strong_package()
    reviews = semantic_reviews(proposals)
    result = evaluate(documents, proposals, fact_reviews=reviews + (reviews[0],),
                      bundle_review=bundle_acknowledgment(documents, proposals))
    assert result.facts[0].status == "needs_review"
    assert result.evaluation.outcome == "Needs Review"


@pytest.mark.parametrize("changes", [
    {"analyst": ""}, {"rationale": ""},
    {"reviewed_on": CAPTURED - timedelta(days=1)},
    {"reviewed_on": AS_OF + timedelta(days=1)},
    {"decision": "approved"}, {"classification": "verified_by_model"},
])
def test_invalid_or_outdated_semantic_review_cannot_validate_a_fact(changes):
    documents, proposals = strong_package()
    reviews = semantic_reviews(proposals)
    result = evaluate(documents, proposals, fact_reviews=(replace(reviews[0], **changes),) + reviews[1:],
                      bundle_review=bundle_acknowledgment(documents, proposals))
    assert result.facts[0].status == "needs_review"
    assert result.evaluation.outcome == "Needs Review"


@pytest.mark.parametrize("decision,status", [("unsupported", "unsupported"), ("ambiguous", "needs_review")])
def test_explicit_semantic_rejection_or_ambiguity_retains_proposal_and_quotation(decision, status):
    documents, proposals = strong_package()
    reviews = semantic_reviews(proposals)
    review = replace(reviews[0], decision=decision, classification="unsupported_interpretation",
                     rationale="The cited text does not establish the proposed complete-population interpretation.")
    result = evaluate(documents, proposals, fact_reviews=(review,) + reviews[1:],
                      bundle_review=bundle_acknowledgment(documents, proposals))
    assert result.facts[0].proposal == proposals[0]
    assert result.facts[0].status == status
    assert result.evaluation.outcome == "Needs Review"


def test_policy_intent_cannot_be_upgraded_by_caller_or_review_classification():
    document = source("policy", "All human administrators must use MFA in Acme Analytics production.", kind="policy")
    bound = bind_evidence(document)
    fact = MfaFact("enforcement", True, Citation("policy:1", bound.document.segments[0].text),
                   document.service, document.environment, document.account_scope, document.observed_on, "policy")
    proposal = ProposedFact("policy-enforcement", fact, bound.fingerprint, "Line 1")
    review = FactReview(fact_fingerprint(proposal), "supported", "implementation_evidence",
                        "synthetic-analyst", AS_OF, "Policy cannot prove operation.")
    result = evaluate((document,), (proposal,), fact_reviews=(review,),
                      bundle_review=bundle_acknowledgment((document,), (proposal,)))
    assert result.facts[0].status == "needs_review"
    assert not result.evaluation.facts
    policy_review = replace(review, classification="policy_assertion")
    result = evaluate((document,), (proposal,), fact_reviews=(policy_review,),
                      bundle_review=bundle_acknowledgment((document,), (proposal,)))
    assert result.facts[0].status == "validated"
    assert result.evaluation.facts[0].status == "unknown"
    assert result.evaluation.outcome != "Met"


@pytest.mark.parametrize("classification", ["explicit_exception", "conflicting_statement"])
def test_analyst_identified_exception_or_conflict_blocks_positive_even_without_lexical_marker(classification):
    documents, proposals = strong_package()
    reviews = semantic_reviews(proposals)
    # The first source sentence contains none of the lexical triage markers.
    review = replace(reviews[0], classification=classification,
                     rationale="The asserted inventory conflicts with a separate source account.")
    result = evaluate(documents, proposals, fact_reviews=(review,) + reviews[1:],
                      bundle_review=bundle_acknowledgment(documents, proposals))
    assert result.facts[0].classification == classification
    assert result.evaluation.outcome == "Needs Review"
    assert any("analyst-identified exceptions" in item for item in result.follow_up)


@pytest.mark.parametrize("rejected_positive", [False, True])
def test_uncited_bypass_document_is_retained_even_when_positive_interpretation_is_rejected(rejected_positive):
    documents, proposals = strong_package()
    bypass = source("emergency", (
        "Two emergency administrators bypass MFA and obtain production administrator sessions with a password-only local login."
    ))
    documents += (bypass,)
    reviews = semantic_reviews(proposals)
    if rejected_positive:
        reviews = (replace(reviews[0], decision="unsupported", classification="unsupported_interpretation"),) + reviews[1:]
    # The bundle is acknowledged, but the bypass signal is deliberately unresolved.
    preliminary = evaluate(documents, proposals)
    bundle = BundleReview(preliminary.bundle_fingerprint, "synthetic-analyst", AS_OF,
                          "Reviewed supplied sources; emergency-access scope requires investigation.")
    result = evaluate(documents, proposals, fact_reviews=reviews, bundle_review=bundle)
    signal = next(item for item in result.signals if item.source_id == "emergency:1")
    assert signal.quote == bypass.content.decode()
    assert signal.location == "Line 1"
    assert signal.status == "needs_review"
    assert any(item.source.document_id == "emergency" for item in result.evidence)
    assert result.evaluation.outcome == "Needs Review"
    assert any(item.startswith("Priority:") for item in result.follow_up)


@pytest.mark.parametrize("disposition_kind", ["material", "duplicate", "empty_rationale"])
def test_material_or_invalid_exception_disposition_cannot_clear_a_signal(disposition_kind):
    documents, proposals = strong_package()
    bundle = bundle_acknowledgment(documents, proposals)
    original = bundle.signal_dispositions[0]
    if disposition_kind == "material":
        dispositions = (replace(original, material=True, rationale="A material exception requires investigation."),)
    elif disposition_kind == "duplicate":
        dispositions = (original, original)
    else:
        dispositions = (replace(original, rationale=""),)
    result = evaluate(documents, proposals, fact_reviews=semantic_reviews(proposals),
                      bundle_review=replace(bundle, signal_dispositions=dispositions))
    assert result.signals[0].status != "dismissed_by_analyst"
    assert result.evaluation.outcome == "Needs Review"


def test_validation_uses_supplied_bytes_without_file_database_or_network_access(monkeypatch):
    documents, proposals = strong_package()
    reviews = semantic_reviews(proposals)
    bundle = bundle_acknowledgment(documents, proposals)

    def external_access_forbidden(*args, **kwargs):
        raise AssertionError("Validation must remain in memory and must not perform external access.")

    import builtins
    import socket
    from sqlalchemy.engine import Engine

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", external_access_forbidden)
        patch.setattr(socket, "socket", external_access_forbidden)
        patch.setattr(Engine, "connect", external_access_forbidden)
        result = evaluate(documents, proposals, fact_reviews=reviews, bundle_review=bundle)
    assert result.evaluation.outcome == "Met"
