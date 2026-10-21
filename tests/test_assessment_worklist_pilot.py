"""Synthetic integration proof; no real timing, vendor data or approvals."""
from dataclasses import replace

from src.assessment_orchestrator import QUESTION_LIBRARY
from src.assessment_worklist import build_assessment_worklist
from src.assessment_worklist_pilot import worklist_scenarios
from src.control_assurance import inspect_control, record_control_review


def scenario(key):
    return next(item for item in worklist_scenarios() if item.scenario_id == key)


def build(item):
    return build_assessment_worklist(
        item.scope, item.applicability, item.requirements, item.assurance_links,
        legacy_evidence=item.legacy_evidence, control_claims=item.control_claims,
    )


def rows_by_control(worklist):
    return {row.control_id: row for row in worklist.rows}


def test_one_assessment_retains_all_four_explicit_customer_requirements():
    item = scenario("initial")
    result = build(item)
    assert len(result.rows) == len(item.applicability.controls) == 4
    assert len({link.case.family for link in item.assurance_links}) >= 3
    expected = {mapping.control_id: mapping.requirement.requirement_id for mapping in item.requirements}
    assert {row.control_id: row.requirement_id for row in result.rows} == expected
    assert "CUSTOM-GOV-42" not in QUESTION_LIBRARY and "CUSTOM-VM-42" not in QUESTION_LIBRARY
    assert expected["ENC-01"] == "ENC-02.TLS"
    assert expected["BCP-01"] == "BCP-01.DR"
    assert expected["CUSTOM-GOV-42"] == "GOV-01.POLICY"
    assert expected["CUSTOM-VM-42"] == "VM-01.REMEDIATION"
    assert all(row.next_action for row in result.rows)
    assert not any(row.outcome == "Risk Identified" for row in result.rows)


def test_added_recovery_evidence_removes_only_its_targeted_request():
    initial = build(scenario("initial"))
    closed = build(scenario("gap-closed"))
    assert initial.baseline_questions == closed.baseline_questions == 4
    assert len(initial.requests) == 1 and len(closed.requests) == 0
    first, second = rows_by_control(initial), rows_by_control(closed)
    assert first["BCP-01"] != second["BCP-01"]
    assert all(first[key] == second[key] for key in first if key != "BCP-01")
    assert "completed" in str(initial.requests[0]).casefold()
    assert "RTO" in str(initial.requests[0]) and "RPO" in str(initial.requests[0])
    # The newly supplied test is useful for analyst review, never automatically Met.
    assert second["BCP-01"].outcome != "Met"


def test_inspecting_scenarios_never_creates_semantic_or_bundle_reviews():
    for item in worklist_scenarios():
        before = item.assurance_links
        result = build(item)
        assert item.assurance_links == before
        for link in item.assurance_links:
            assert not link.state.fact_reviews and not link.state.events
            assert not link.state.signal_dispositions and link.state.bundle_review is None
        assert all(row.outcome != "Met" for row in result.rows)


def test_explicit_id_conflict_never_creates_or_guesses_an_extra_requirement():
    initial = build(scenario("initial"))
    conflict = build(scenario("mapping-conflict"))
    assert {row.requirement_id for row in conflict.rows} == {row.requirement_id for row in initial.rows}
    assert len(conflict.rows) == 4
    row = rows_by_control(conflict)["ENC-01"]
    assert row.outcome == "Needs Review"
    assert conflict.diagnostics
    assert row.outcome != "Met"


def _review(case, state, action, **kwargs):
    return record_control_review(
        case, state, action=action, expected_bundle=inspect_control(case).bundle_fingerprint,
        analyst="Synthetic integration test reviewer", reviewed_on=case.as_of,
        rationale="Explicit test action after checking the exact synthetic source and affected scope.",
        **kwargs,
    )


def test_confirmed_current_exception_takes_precedence_over_supporting_evidence():
    item = scenario("adverse")
    link = next(link for link in item.assurance_links if link.control_id == "ENC-01")
    view = inspect_control(link.case)
    adverse = next(row for row in view.facts if row.direction == "adverse")
    state = _review(link.case, link.state, "exception", fact_ids=(adverse.proposal.fact_id,),
                    presented_fingerprints=(adverse.fingerprint,), confirms=True)
    changed = replace(item, assurance_links=tuple(replace(row, state=state) if row.control_id == "ENC-01" else row
                                                 for row in item.assurance_links))
    result = build(changed)
    assert result.rows[0].control_id == "ENC-01"
    assert result.rows[0].outcome == "Risk Identified"
    assert len(result.rows[0].review.evidence) > 1
    assert any(f.direction == "support" for f in result.rows[0].review.facts)
    assert not result.rows[0].review.bundle_review_valid
    assert state.events[-1].kind == "exception"
    # The source-reviewed failure is still provisional; nothing is approved.
    assert result.rows[0].review.provisional and result.rows[0].review.review_required


def test_explicit_existing_review_can_reuse_evidence_without_approving_risk():
    item = scenario("initial")
    link = next(link for link in item.assurance_links if link.control_id == "ENC-01")
    view = inspect_control(link.case)
    support = tuple(row for row in view.facts if row.direction == "support" and not row.reasons)
    state = _review(link.case, link.state, "support", fact_ids=tuple(row.proposal.fact_id for row in support),
                    presented_fingerprints=tuple(row.fingerprint for row in support), confirms=True)
    for signal in view.signals:
        state = _review(link.case, state, "signal", signal_id=signal.signal_id, material=False)
    state = _review(link.case, state, "bundle", confirms=True)
    assert inspect_control(link.case, state).outcome == "Met"
    changed = replace(item, assurance_links=tuple(replace(row, state=state) if row.control_id == "ENC-01" else row
                                                 for row in item.assurance_links))
    result = build(changed)
    row = rows_by_control(result)["ENC-01"]
    assert row.outcome == "Met" and row.review.provisional and row.review.review_required
    assert "governance" in row.next_action.casefold() or "governed" in row.next_action.casefold()
    assert len(result.requests) == 1  # The unrelated missing DR exercise remains.


def test_synthetic_request_counts_are_reproducible_and_not_cycle_time_claims():
    counts = [(item.scenario_id, len(build(item).requests), build(item).baseline_questions)
              for item in worklist_scenarios()]
    assert counts[:3] == [("initial", 1, 4), ("gap-closed", 0, 4), ("adverse", 1, 4)]
    print("M4A synthetic distinct vendor-request previews / ask-everything baseline:", counts)
