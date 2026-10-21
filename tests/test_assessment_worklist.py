"""Synthetic integration boundaries for the read-only assessment adapter."""
from dataclasses import dataclass, replace
from datetime import date, timedelta

import pytest

from src.applicability import ApplicabilityResult
from src.assessment_worklist import (
    AssessmentScope, AssuranceLink, EvidenceNeed, RequirementMapping,
    ScopedLegacyEvidence, build_assessment_worklist,
)
from src.control_assurance import ControlReviewState, inspect_control, record_control_review
from src.control_assurance_pilot import control_pilot_cases, fallback_pilot_cases
from src.control_sufficiency import EvidenceControlClaim
from src.evidence_source_validation import bind_evidence
from src.tiering import ControlRequirement, EvidenceRequirement
from src.tls_assurance import TlsThreshold


CASES = {c.case_id: c for c in control_pilot_cases() + fallback_pilot_cases()}


def applicability(*control_ids):
    return ApplicabilityResult(
        controls=tuple(ControlRequirement(key, "Synthetic domain", "Explicit customer requirement " + key)
                       for key in control_ids),
        evidence=(EvidenceRequirement("SYNTH-SOC", "SOC 2 Type II or equivalent assurance report"),),
        decisions=(), review_required=True, review_reasons=("Synthetic assessment requires analyst review.",),
    )


def scope(case):
    return AssessmentScope("synthetic-engagement-1", case.requirement.service,
                           case.requirement.environment, case.as_of)


def mapping(case, control_id="ENC-01", needs=()):
    return RequirementMapping(control_id, case.requirement, case.threshold, needs=tuple(needs))


def link(case, control_id="ENC-01", state=ControlReviewState()):
    return AssuranceLink("synthetic-engagement-1", control_id, case, state)


def build(case=None, *, control_id="ENC-01", needs=(), state=ControlReviewState(), links=None,
          mappings=None, controls=None, legacy_evidence=(), control_claims=()):
    case = case or CASES["tls-strong"]
    return build_assessment_worklist(
        scope(case), applicability(*(controls or (control_id,))),
        tuple(mappings) if mappings is not None else (mapping(case, control_id, needs),),
        tuple(links) if links is not None else (link(case, control_id, state),),
        legacy_evidence=legacy_evidence, control_claims=control_claims,
    )


def current_review(case):
    """Test-only explicit decisions; the inspection adapter never generates these."""
    state = ControlReviewState()
    initial = inspect_control(case)

    def record(action, **kwargs):
        nonlocal state
        state = record_control_review(
            case, state, action=action, expected_bundle=initial.bundle_fingerprint,
            analyst="Synthetic independent analyst", reviewed_on=case.as_of,
            rationale="Checked exact source context and interpretation; governance remains separate.", **kwargs,
        )

    support = [f for f in initial.facts if f.direction == "support" and not f.reasons]
    if support:
        record("support", fact_ids=tuple(f.proposal.fact_id for f in support),
               presented_fingerprints=tuple(f.fingerprint for f in support), confirms=True)
    for row in initial.facts:
        if not row.reasons and row.direction in {"adverse", "review"}:
            record("exception" if row.direction == "adverse" else "meaning",
                   fact_ids=(row.proposal.fact_id,), presented_fingerprints=(row.fingerprint,), confirms=True)
    for signal in initial.signals:
        record("signal", signal_id=signal.signal_id, material=False)
    record("bundle", confirms=True)
    return state


def scan_need(**changes):
    need = EvidenceNeed(
        "dated-endpoint-scan", "Current operating protocol behavior on every assessed endpoint",
        "A dated complete-endpoint protocol-rejection scan",
        "Provide the dated protocol-rejection scan for all assessed production endpoints.",
        ("test",), dimensions=("minimum_version", "legacy_rejected", "scope_complete"), max_age_days=90,
    )
    return replace(need, **changes)


def test_unknown_customer_requirement_and_absent_mapping_are_never_dropped():
    case = CASES["vm-present"]
    result = build(case, control_id="CUSTOM-VM-42", controls=("CUSTOM-VM-42", "CUSTOM-UNKNOWN-99"))
    assert {r.control_id for r in result.rows} == {"CUSTOM-VM-42", "CUSTOM-UNKNOWN-99"}
    supplied = next(r for r in result.rows if r.control_id == "CUSTOM-VM-42")
    missing = next(r for r in result.rows if r.control_id == "CUSTOM-UNKNOWN-99")
    assert supplied.requirement_id == case.requirement.requirement_id
    assert supplied.specialist_available is False
    assert supplied.outcome == "Needs Review" and supplied.presentation is not None
    assert missing.outcome == "Needs Review" and missing.review is None
    assert missing.next_action and not missing.request_ids
    assert result.baseline_questions == 2


@pytest.mark.parametrize("bad_control", ["IAM-01", "PAM-01", "ENC-02.TLS"])
def test_parent_or_similarly_named_control_ids_do_not_silently_join(bad_control):
    case = CASES["tls-strong"]
    result = build(case, links=(link(case, bad_control),))
    row = result.rows[0]
    assert row.control_id == "ENC-01" and row.requirement_id == "ENC-02.TLS"
    assert row.outcome == "Needs Review" and row.review is None and row.presentation is None
    assert not result.requests and (row.limitations or result.diagnostics)


@pytest.mark.parametrize("mutation", ["engagement", "service", "environment", "policy", "version", "id", "date", "threshold"])
def test_explicit_linkage_rejects_wrong_relationship_or_requirement_metadata(mutation):
    case = CASES["tls-strong"]
    changed, wrong_engagement = case, False
    if mutation == "engagement":
        wrong_engagement = True
    elif mutation == "threshold":
        changed = replace(case, threshold=TlsThreshold(13))
    elif mutation == "date":
        changed = replace(case, as_of=date(2026, 10, 22))
    else:
        attrs = {"service": {"service": "Other synthetic relationship"},
                 "environment": {"environment": "staging"},
                 "policy": {"customer_policy_id": "other-customer-policy"},
                 "version": {"policy_version": "2026.2"},
                 "id": {"requirement_id": "ENC-01"}}[mutation]
        changed = replace(case, requirement=replace(case.requirement, **attrs))
    supplied = link(changed)
    if wrong_engagement:
        supplied = replace(supplied, engagement_id="synthetic-engagement-2")
    result = build(case, links=(supplied,))
    row = result.rows[0]
    assert row.outcome == "Needs Review" and row.review is None and row.presentation is None
    assert not result.requests and (row.limitations or result.diagnostics)
    assert case.proposals[0].quote not in repr(result)


def test_duplicate_assurance_links_do_not_choose_a_positive_result():
    case = CASES["tls-strong"]
    good = link(case, state=current_review(case))
    adverse = CASES["tls-exception"]
    bad = link(adverse, state=current_review(adverse))
    assert inspect_control(adverse, bad.state).outcome == "Risk Identified"
    for links in ((good, good), (good, bad), (bad, good)):
        with pytest.raises(ValueError, match="Duplicate assurance linkages"):
            build(case, links=links)


def test_unlinked_extra_result_cannot_add_requirement_or_leak_its_source():
    case, extra = CASES["tls-strong"], CASES["dr-strong"]
    result = build(case, links=(link(case), link(extra, "NOT-APPLICABLE")))
    assert len(result.rows) == 1 and result.rows[0].requirement_id == case.requirement.requirement_id
    assert result.diagnostics
    assert extra.proposals[0].quote not in repr(result)


def test_legacy_supported_is_informational_and_cannot_become_customer_met():
    @dataclass(frozen=True)
    class LegacyRecord:
        id: int = 1
        document_type: str = "SOC 2 Type II"
        document_name: str = "synthetic-legacy-report.txt"
        status: str = "Current"
        expiration_date: str | None = None
        extraction_confidence: float = 1.0

    case = replace(CASES["tls-strong"], documents=(), proposals=())
    evidence = ScopedLegacyEvidence("synthetic-engagement-1", case.requirement.service,
                                    case.requirement.environment, LegacyRecord())
    result = build(case, legacy_evidence=(evidence,), control_claims=(EvidenceControlClaim(1, "ENC-01"),))
    assert result.legacy_plan.items[0].sufficiency_status == "SUPPORTED"
    row = result.rows[0]
    assert row.outcome != "Met" and "reuse" not in row.intent.casefold()
    assert "support" in row.legacy_status.casefold()


def test_legacy_evidence_from_another_engagement_is_not_reused():
    @dataclass(frozen=True)
    class LegacyRecord:
        id: int = 7
        document_type: str = "SOC 2 Type II"
        document_name: str = "synthetic-wrong-relationship.txt"

    case = CASES["tls-strong"]
    evidence = ScopedLegacyEvidence("synthetic-engagement-2", case.requirement.service,
                                    case.requirement.environment, LegacyRecord())
    result = build(case, legacy_evidence=(evidence,), control_claims=(EvidenceControlClaim(7, "ENC-01"),))
    assert result.legacy_plan.items[0].sufficiency_status != "SUPPORTED"
    assert result.diagnostics and result.rows[0].outcome != "Met"


def test_unconfirmed_source_bound_candidates_require_analyst_validation_not_more_questions():
    case = CASES["tls-strong"]
    result = build(case, needs=(scan_need(),))
    row = result.rows[0]
    assert row.outcome == "Needs Review" and not result.requests
    # Raw source exception markers require separate triage, even when an
    # interpretation claims the quotation describes disabled legacy protocols.
    assert row.priority == 1 and row.intent == "Review exception"
    assert row.review.signals
    assert not any(f.confirmed for f in row.review.facts)


def test_explicitly_missing_artifact_creates_one_precise_preview_not_generic_questionnaire():
    full = CASES["tls-strong"]
    keep = tuple(d for d in full.documents if d.evidence_kind != "test")
    ids = {d.document_id for d in keep}
    case = replace(full, documents=keep,
                   proposals=tuple(p for p in full.proposals if p.source_id.split(":")[0] in ids))
    need = scan_need()
    state = ControlReviewState()
    for signal in inspect_control(case).signals:
        state = record_control_review(
            case, state, action="signal", signal_id=signal.signal_id, material=False,
            expected_bundle=inspect_control(case).bundle_fingerprint,
            analyst="Synthetic independent analyst", reviewed_on=case.as_of,
            rationale="Verified that this source marker describes rejected legacy protocols.",
        )
    present_configuration = scan_need(need_id="config", missing_fact="Enabled protocol configuration",
                                      accepted_kinds=("configuration",))
    result = build(case, needs=(present_configuration, need, need), state=state)
    assert len(result.requests) == 1
    request = result.requests[0]
    assert request.question == need.question and request.missing_fact == need.missing_fact
    assert request.acceptable_evidence == need.acceptable_evidence
    assert case.requirement.requirement_id in request.requirement_ids
    assert result.rows[0].outcome != "Risk Identified"
    assert result.rows[0].request_ids == (request.request_id,)
    assert result.rows[0].missing_fact == need.missing_fact


def test_same_filename_or_artifact_label_does_not_merge_different_customer_threshold_questions():
    first = replace(CASES["tls-strong"], documents=(), proposals=())
    second = replace(first, requirement=replace(first.requirement, requirement_id="CUSTOM-TRANSPORT-STRICT"),
                     threshold=TlsThreshold(13))
    need = scan_need()
    result = build(first, mappings=(mapping(first, needs=(need,)), mapping(second, needs=(need,))),
                   links=(link(first), link(second)))
    assert len(result.rows) == 2 and len(result.requests) == 2
    assert len({request.request_id for request in result.requests}) == 2
    assert {r.requirement_id for r in result.rows} == {first.requirement.requirement_id, second.requirement.requirement_id}


def test_fully_reviewed_met_reuses_evidence_but_preserves_governance_boundary():
    case = CASES["tls-strong"]
    state = current_review(case)
    before = state
    result = build(case, state=state, needs=(scan_need(),))
    row = result.rows[0]
    assert row.outcome == "Met" and not result.requests
    assert row.priority == 4 and "reuse" in row.intent.casefold()
    assert "govern" in (row.intent + row.next_action).casefold()
    assert row.review.provisional and row.review.review_required
    assert state == before  # Inspection does not create review records.


def test_confirmed_current_exception_is_first_beside_other_supported_requirements():
    bad, good = CASES["tls-exception"], CASES["dr-strong"]
    result = build(bad, controls=("ENC-01", "BCP-01"),
                   mappings=(mapping(bad), mapping(good, "BCP-01")),
                   links=(link(bad, state=current_review(bad)), link(good, "BCP-01", current_review(good))))
    first = result.rows[0]
    assert first.requirement_id == bad.requirement.requirement_id
    assert first.outcome == "Risk Identified" and first.priority == 0
    assert "exception" in first.intent.casefold()
    assert any(f.direction == "adverse" and f.confirmed for f in first.review.facts)
    assert any(c.status == "failed" for c in first.review.checks)
    assert result.rows[-1].outcome == "Met"


def test_contradictory_or_unverified_exceptions_stay_visible_without_becoming_verified_failure():
    for key in ("tls-conflict", "tls-reported"):
        case = CASES[key]
        result = build(case, state=current_review(case))
        row = result.rows[0]
        assert row.outcome == "Needs Review" and row.priority <= 1
        assert row.presentation.attention and not result.requests


def test_source_replacement_with_old_review_cannot_keep_met_or_old_verified_citations():
    full = CASES["tls-strong"]
    state = current_review(full)
    changed_doc = replace(full.documents[-1], content=full.documents[-1].content + b"\nSYNTHETIC revised report.")
    changed = replace(full, documents=full.documents[:-1] + (changed_doc,))
    result = build(changed, state=state, needs=(scan_need(),))
    row = result.rows[0]
    assert row.outcome != "Met" and not row.review.bundle_review_valid
    assert not any(f.confirmed for f in row.review.facts)
    assert row.limitations or row.review.limitations


def test_citations_and_source_limits_are_retained_without_semantic_promotion():
    case = CASES["tls-strong"]
    row = build(case).rows[0]
    assert row.review is not None and row.presentation.supporting
    source_quotes = {part.text for b in row.review.evidence for part in b.document.segments}
    for citation in row.presentation.supporting:
        assert citation.quote in source_quotes and citation.location.startswith("Line ")
        assert not citation.confirmed
    assert all(b.source.service == case.requirement.service for b in row.review.evidence)
    assert all(b.content_sha256 and b.source.origin and b.source.version for b in row.review.evidence)


def test_same_requirement_id_on_distinct_controls_never_cross_attaches_requests():
    full = CASES["tls-strong"]
    empty = replace(full, documents=(), proposals=())
    result = build(full, controls=("CUSTOM-A", "CUSTOM-B"),
                   mappings=(mapping(empty, "CUSTOM-A", (scan_need(),)), mapping(full, "CUSTOM-B")),
                   links=(link(empty, "CUSTOM-A"), link(full, "CUSTOM-B")))
    rows = {r.control_id: r for r in result.rows}
    assert len(result.requests) == 1
    assert rows["CUSTOM-A"].request_ids == (result.requests[0].request_id,)
    assert rows["CUSTOM-B"].request_ids == ()
    assert rows["CUSTOM-B"].missing_fact == ""


def test_duplicate_artifact_request_labels_do_not_create_duplicate_vendor_questions():
    case = replace(CASES["tls-strong"], documents=(), proposals=())
    need = scan_need()
    result = build(case, needs=(need, replace(need, need_id="another-label-for-same-request")))
    assert len(result.requests) == 1 and len(result.rows[0].request_ids) == 1


@pytest.mark.parametrize("change", ["stale", "scope", "citation"])
def test_bad_source_context_cannot_establish_pass_or_verified_citation(change):
    full = CASES["tls-strong"]
    state = current_review(full)
    if change == "citation":
        wrong = replace(full.proposals[0], quote="SYNTHETIC invented supporting quotation")
        changed = replace(full, proposals=(wrong,) + full.proposals[1:])
    else:
        attributes = ({"observed_on": full.as_of - timedelta(days=400)} if change == "stale"
                      else {"service": "Other synthetic service"})
        changed = replace(full, documents=tuple(replace(d, **attributes) for d in full.documents))
    row = build(changed, state=state, needs=(scan_need(),)).rows[0]
    assert row.outcome != "Met" and not row.review.bundle_review_valid
    assert not any(f.confirmed for f in row.review.facts)
    assert row.limitations
    assert "invented supporting quotation" not in repr(row.presentation)


def test_no_specialist_and_no_evidence_keeps_customer_requirement_and_focused_gap():
    case = CASES["vm-missing"]
    need = EvidenceNeed("remediation-records", "Dated critical-vulnerability remediation records",
                        "Scoped remediation and closure records", "Provide the dated scoped remediation records.",
                        ("configuration", "test"))
    result = build(case, control_id="CUSTOM-VM-42", needs=(need,))
    row = result.rows[0]
    assert row.outcome == "Evidence Missing" and row.specialist_available is False
    assert row.presentation and "specialist" in " ".join(row.limitations).lower()
    assert row.missing_fact == need.missing_fact and len(result.requests) == 1


@pytest.mark.parametrize("case_id", ["dr-stale", "dr-scope", "dr-statement"])
def test_stale_wrong_scope_or_asserted_recovery_results_need_exact_operating_record(case_id):
    case = CASES[case_id]
    need = EvidenceNeed("completed-exercise", "Current completed full-service recovery exercise results",
                        "Dated completed exercise with achieved RTO/RPO", "Provide the current in-scope completed recovery exercise.",
                        ("test",), max_age_days=365)
    result = build(case, control_id="BCP-01", needs=(need,))
    assert len(result.requests) == 1 and result.requests[0].question == need.question
    assert result.rows[0].outcome not in {"Met", "Risk Identified"}
    assert result.rows[0].priority == 2


def test_request_hint_cannot_relax_customer_requirement_freshness():
    case = CASES["dr-stale"]
    need = EvidenceNeed("completed-exercise", "Current completed full-service recovery exercise results",
                        "Dated completed exercise", "Provide the current completed recovery exercise.",
                        ("test",), max_age_days=999)
    result = build(case, control_id="BCP-01", needs=(need,))
    assert len(result.requests) == 1
    assert result.rows[0].outcome != "Met"
