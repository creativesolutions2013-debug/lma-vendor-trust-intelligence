"""Synthetic safety regressions for the separate M6 AI-review workflow.

These constructed responses test the workflow contract. They are not completed
agent reviews, customer control approvals, or adjudicated benchmark labels.
"""

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from benchmarks import m6_ai_review as review


@pytest.fixture
def packet():
    return review.parse_packet()


def constructed_review(packet, agent="A"):
    """An intentionally cautious, source-cited response used only by tests."""
    cases = []
    for source in packet["cases"]:
        available = source["evidence_provided"]
        cases.append({
            "case_id": source["case_id"],
            "classifications": ["evidence_insufficient"],
            "demonstrated_weakness": False,
            "evidence_sufficiency": "insufficient" if available else "missing",
            "citations": [{"source_id": source["source_id"],
                           "quote": source["evidence"]}] if available else [],
            "reasoning": "This synthetic excerpt alone does not establish the full requirement.",
            "scope_and_freshness": "Only the scope and dates stated in the excerpt are available.",
            "uncertainty": "Original operational artifacts are unavailable in this exercise.",
            "alternative_interpretation": "Relevant additional evidence may already exist internally.",
            "minimal_action": {
                "kind": "internal_verification",
                "text": "Check the existing package for requirement-specific operational evidence.",
                "justification": "Existing evidence should be assessed before vendor contact.",
            },
            "unnecessary_questions": [],
        })
    return {"schema_version": "m6-ai-review-v1", "agent_id": agent,
            "input_boundary": {"status": "clean", "notes": "Constructed test response; no peer or reference context."},
            "cases": cases}


def test_blind_packet_preserves_all_ten_cases_without_reference_labels(packet):
    assert packet["synthetic_only"] is True
    assert len(packet["packet_sha256"]) == 64
    assert [case["case_id"] for case in packet["cases"]] == [
        f"M6-{number:02d}" for number in range(1, 11)
    ]
    assert all(case["source_id"] and case["source_location"] for case in packet["cases"])
    assert not packet["cases"][8]["evidence_provided"]
    assert all(case["evidence_provided"] for case in packet["cases"] if case["case_id"] != "M6-09")
    assert all("reference_concerns" not in case and "necessary_questions" not in case
               for case in packet["cases"])


def test_prompts_contain_only_blind_data_and_each_roles_own_instructions(packet):
    a_prompt = review.review_prompt(packet, "A", "PRIVATE_A_INSTRUCTION_SENTINEL")
    b_prompt = review.review_prompt(packet, "B", "PRIVATE_B_INSTRUCTION_SENTINEL")
    assert "PRIVATE_A_INSTRUCTION_SENTINEL" in a_prompt
    assert "PRIVATE_A_INSTRUCTION_SENTINEL" not in b_prompt
    assert "PRIVATE_B_INSTRUCTION_SENTINEL" in b_prompt
    assert "PRIVATE_B_INSTRUCTION_SENTINEL" not in a_prompt
    for source in packet["cases"]:
        assert source["evidence"] in a_prompt
        assert source["evidence"] in b_prompt
        assert source["requirement"] in a_prompt
        assert source["requirement"] in b_prompt
    assert a_prompt.index("M6-01") < a_prompt.index("M6-10")
    assert b_prompt.index("M6-10") < b_prompt.index("M6-01")
    for forbidden_field in ('"reference_concerns"', '"necessary_questions"', '"reviewer_a"',
                            '"reviewer_b"', '"sessions_scored"'):
        assert forbidden_field not in a_prompt
        assert forbidden_field not in b_prompt


def test_sealed_artifact_refuses_overwrite_and_detects_tampering(tmp_path):
    output = tmp_path / "review.json"
    review.seal_json(output, {"synthetic": True, "case": "M6-09"})
    assert review.load_sealed(output) == {"synthetic": True, "case": "M6-09"}
    with pytest.raises((FileExistsError, ValueError)):
        review.seal_json(output, {"synthetic": True, "case": "M6-01"})
    output.chmod(0o600)
    output.write_text('{"synthetic": true, "case": "M6-01"}', encoding="utf-8")
    with pytest.raises(ValueError):
        review.load_sealed(output)


def test_constructed_complete_source_cited_submission_is_valid(packet):
    review.validate_review(packet, constructed_review(packet))


@pytest.mark.parametrize("boundary_status", ["contaminated", "unknown"])
def test_declared_contamination_or_unknown_boundary_cannot_be_accepted(packet, boundary_status):
    response = constructed_review(packet)
    response["input_boundary"]["status"] = boundary_status
    with pytest.raises(ValueError):
        review.validate_review(packet, response)


@pytest.mark.parametrize("mutation", [
    "foreign_source", "absent_quote", "requirement_quote", "empty_citations",
])
def test_citations_must_quote_the_correct_original_case_evidence(packet, mutation):
    response = constructed_review(packet)
    case = response["cases"][0]
    if mutation == "foreign_source":
        case["citations"][0]["source_id"] = packet["cases"][2]["source_id"]
    elif mutation == "absent_quote":
        case["citations"][0]["quote"] = "A security engineer verified FIDO2 enforcement."
    elif mutation == "requirement_quote":
        case["citations"][0]["quote"] = packet["cases"][0]["requirement"]
    else:
        case["citations"] = []
    with pytest.raises(ValueError):
        review.validate_review(packet, response)


def test_no_ir_evidence_is_explicitly_missing_without_fabricated_citation(packet):
    response = constructed_review(packet)
    missing = response["cases"][8]
    assert missing["evidence_sufficiency"] == "missing"
    assert missing["citations"] == []
    review.validate_review(packet, response)


@pytest.mark.parametrize("mutation", ["weakness", "adequate", "supported", "mixed_support", "fabricated_source"])
def test_missing_evidence_cannot_become_control_failure_or_assurance(packet, mutation):
    response = constructed_review(packet)
    missing = response["cases"][8]
    if mutation == "weakness":
        missing["demonstrated_weakness"] = True
        missing["classifications"] = ["demonstrated_exception"]
    elif mutation == "adequate":
        missing["evidence_sufficiency"] = "adequate"
    elif mutation == "supported":
        missing["classifications"] = ["supported_with_limits"]
    elif mutation == "mixed_support":
        missing["classifications"] = ["evidence_insufficient", "supported_with_limits"]
    else:
        missing["citations"] = [{"source_id": "invented-ir-report", "quote": "Tabletop passed."}]
    with pytest.raises(ValueError):
        review.validate_review(packet, response)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "unknown"])
def test_each_original_case_must_have_exactly_one_response(packet, mutation):
    response = constructed_review(packet)
    if mutation == "duplicate":
        response["cases"][-1] = deepcopy(response["cases"][0])
    elif mutation == "missing":
        response["cases"].pop()
    else:
        response["cases"][-1]["case_id"] = "M6-11"
    with pytest.raises(ValueError):
        review.validate_review(packet, response)


@pytest.mark.parametrize("field", ["scope_and_freshness", "uncertainty", "alternative_interpretation"])
def test_uncertainty_and_scope_are_required_not_silently_omitted(packet, field):
    response = constructed_review(packet)
    del response["cases"][0][field]
    with pytest.raises(ValueError):
        review.validate_review(packet, response)


@pytest.mark.parametrize("location", ["review", "case", "action"])
def test_automatic_approval_fields_are_rejected_at_every_structured_level(packet, location):
    response = constructed_review(packet)
    if location == "review":
        response["approved"] = True
    elif location == "case":
        response["cases"][0]["control_approved"] = True
    else:
        response["cases"][0]["minimal_action"]["approve_vendor"] = True
    with pytest.raises(ValueError):
        review.validate_review(packet, response)


def test_demonstrated_weakness_requires_explicit_exception_classification(packet):
    response = constructed_review(packet)
    response["cases"][2]["demonstrated_weakness"] = True
    with pytest.raises(ValueError):
        review.validate_review(packet, response)


def test_coordinator_preserves_disagreement_instead_of_averaging(packet):
    a = constructed_review(packet, "A")
    b = constructed_review(packet, "B")
    b["cases"][2]["classifications"] = ["demonstrated_exception"]
    b["cases"][2]["demonstrated_weakness"] = True
    b["cases"][2]["reasoning"] = "The stated production listener accepts TLS 1.1 below the threshold."
    a_before, b_before = deepcopy(a), deepcopy(b)
    result = review.compare_reviews(packet, a, b)
    assert a == a_before and b == b_before
    disputed = result["cases"][2]
    assert disputed["agreement"] is False
    assert disputed["unresolved_disagreement"] is True
    assert disputed["proposed_classifications"] is None
    assert disputed["reviewer_a"] == a["cases"][2]
    assert disputed["reviewer_b"] == b["cases"][2]


def test_question_necessity_disagreement_is_preserved_even_when_labels_agree(packet):
    a = constructed_review(packet, "A")
    b = constructed_review(packet, "B")
    b["cases"][0]["minimal_action"] = {
        "kind": "vendor_question",
        "text": "Provide privileged authentication method and fallback enforcement evidence.",
        "justification": "The currently supplied excerpt does not identify methods or recovery paths.",
    }
    b["cases"][0]["unnecessary_questions"] = [{
        "text": "Is MFA enabled?",
        "reason": "The supplied statement already says privileged MFA is enabled.",
    }]
    result = review.compare_reviews(packet, a, b)
    disputed = result["cases"][0]
    assert disputed["unresolved_disagreement"] is True
    assert disputed["proposed_classifications"] is None
    assert disputed["reviewer_a"]["minimal_action"]["kind"] == "internal_verification"
    assert disputed["reviewer_b"]["minimal_action"]["kind"] == "vendor_question"
    assert disputed["reviewer_b"]["unnecessary_questions"] == b["cases"][0]["unnecessary_questions"]


def test_ai_agreement_is_only_a_proposed_reference_without_human_assurance(packet):
    a = constructed_review(packet, "A")
    b = constructed_review(packet, "B")
    result = review.compare_reviews(packet, a, b)
    assert result["proposal_status"] == "ai_only_proposed_not_human_validated"
    assert all(case["agreement"] is True for case in result["cases"])
    assert all(case["unresolved_disagreement"] is False for case in result["cases"])
    assert all(case["proposed_classifications"] == ["evidence_insufficient"] for case in result["cases"])
    assert "approved" not in result and "authoritative_risk" not in result


def test_coordinator_refuses_to_run_before_both_sealed_reviews_exist(tmp_path):
    bundle = tmp_path / "bundle"
    review.prepare(bundle)
    with pytest.raises((ValueError, FileNotFoundError)):
        review.coordinate(bundle)
    assert not (bundle / "proposed_reference.json").exists()


@pytest.fixture
def bundle(tmp_path):
    output = tmp_path / "bundle"
    review.prepare(output)
    return output


def mock_codex(monkeypatch, response, *, session="fresh-test-session", extra_events=None,
               returncode=0, stderr="", schema_check=None):
    """Substitute the CLI process; no model service or real credential is used."""
    calls = []
    events = [{"type": "thread.started", "thread_id": session}]
    events.extend(extra_events or [])
    if response is not None:
        events.append({"type": "item.completed", "item": {
            "type": "agent_message", "text": json.dumps(response)}})
    events.append({"type": "turn.completed"})

    def fake_process(command, **kwargs):
        calls.append((command, kwargs))
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "codex synthetic-test-version\n", "")
        if schema_check is not None:
            schema_check(json.loads(Path(command[command.index("--output-schema") + 1]).read_text()))
        return subprocess.CompletedProcess(command, returncode,
                                           "\n".join(json.dumps(event) for event in events), stderr)

    monkeypatch.setattr(review.shutil, "which", lambda name: "/synthetic/bin/codex")
    monkeypatch.setattr(review.subprocess, "run", fake_process)
    return calls


def test_runner_adapts_provider_schema_without_changing_canonical_contract(packet, bundle, monkeypatch):
    canonical = review.review_schema()
    manifest = review.load_sealed(bundle / "manifest.json")
    expected_provider = deepcopy(canonical)
    del expected_provider["properties"]["cases"]["items"]["properties"]["classifications"]["uniqueItems"]
    observed = []

    def check_provider_schema(schema):
        observed.append(schema)
        assert schema == expected_provider
        assert '"uniqueItems"' not in json.dumps(schema)

    mock_codex(monkeypatch, constructed_review(packet), schema_check=check_provider_schema)
    result = review.run(bundle, "A", "configured-test-model")
    assert result["status"] == "completed"
    assert len(observed) == 1
    assert review.review_schema() == canonical
    assert review.load_sealed(bundle / "inputs/review.schema.json") == canonical
    assert manifest["schema_sha256"] == review.digest(review.encoded(canonical))
    assert review.load_sealed(bundle / "manifest.json") == manifest


def test_provider_schema_adaptation_does_not_accept_duplicate_classifications(packet, bundle, monkeypatch):
    response = constructed_review(packet)
    response["cases"][0]["classifications"] = ["evidence_insufficient", "evidence_insufficient"]
    with pytest.raises(ValueError, match="Duplicate array member"):
        review.validate_review(packet, response)
    mock_codex(monkeypatch, response)
    result = review.run(bundle, "A", "configured-test-model")
    assert result["status"] == "rejected"
    assert result["failure_category"] == "invalid_response_or_event_stream"
    assert result["review"] is None
    assert result["isolation"]["context_audit_passed"] is False
    assert not (bundle / "proposed_reference.json").exists()


def test_runner_starts_fresh_context_without_peer_output_or_inherited_thread_identity(
        packet, bundle, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "synthetic-test-placeholder")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-test-placeholder")
    monkeypatch.setenv("CODEX_THREAD_ID", "parent-thread-that-must-not-be-inherited")
    calls = mock_codex(monkeypatch, constructed_review(packet, "B"))
    result = review.run(bundle, "B", "configured-test-model")
    assert result["status"] == "completed"
    assert result["model_requested"] == "configured-test-model"
    assert result["model_actual"] is None
    assert result["session_ids"] == ["fresh-test-session"]
    assert result["isolation"]["context_audit_passed"] is True
    assert result["isolation"]["os_isolation_verified"] is False
    assert result["isolation"]["statistical_independence_established"] is False
    command, options = calls[-1]
    assert command[1] == "exec" and "resume" not in command and "fork" not in command
    assert {"--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check"} <= set(command)
    assert "project_doc_max_bytes=0" in command and 'web_search="disabled"' in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert all(feature in command for feature in review.DISABLED_FEATURES)
    assert "GH_TOKEN" not in options["env"] and "GITHUB_TOKEN" not in options["env"]
    assert "CODEX_THREAD_ID" not in options["env"]
    assert "reviewer_a" not in options["input"]
    assert '"reference_concerns"' not in options["input"]
    assert "Agent B" in options["input"] and "You are Agent A" not in options["input"]
    assert review.load_sealed(bundle / "runs/B/record.json") == result


@pytest.mark.parametrize("tool_type", ["command_execution", "mcp_tool_call", "future_unknown_tool"])
def test_tool_activity_rejects_review_even_with_otherwise_valid_output(
        packet, bundle, monkeypatch, tool_type):
    mock_codex(monkeypatch, constructed_review(packet), extra_events=[{
        "type": "item.completed", "item": {"type": tool_type, "id": "synthetic-tool-id"}}])
    result = review.run(bundle, "A", "configured-test-model")
    assert result["status"] == "rejected"
    assert result["failure_category"] == "context_audit_failed"
    assert result["review"] is None
    assert result["isolation"]["context_audit_passed"] is False
    assert tool_type in result["isolation"]["tool_events_observed"]


@pytest.mark.parametrize("event_type", ["thread.resumed", "context.loaded", "future_unknown_event"])
def test_unknown_top_level_context_events_fail_closed(packet, bundle, monkeypatch, event_type):
    mock_codex(monkeypatch, constructed_review(packet), extra_events=[{"type": event_type}])
    result = review.run(bundle, "A", "configured-test-model")
    assert result["status"] == "rejected"
    assert result["failure_category"] == "context_audit_failed"
    assert result["review"] is None
    assert result["isolation"]["context_audit_passed"] is False


@pytest.mark.parametrize("malformed_event", [None, 42, "not-an-event-object", [],
    {"type": "item.completed", "item": None}])
def test_malformed_json_event_shapes_are_sealed_as_rejected_without_review(
        packet, bundle, monkeypatch, malformed_event):
    mock_codex(monkeypatch, constructed_review(packet), extra_events=[malformed_event])
    result = review.run(bundle, "A", "configured-test-model")
    assert result["status"] == "rejected"
    assert result["failure_category"] == "invalid_response_or_event_stream"
    assert result["review"] is None
    assert result["isolation"]["context_audit_passed"] is False
    assert review.load_sealed(bundle / "runs/A/record.json") == result


def test_error_item_blocks_completion_even_when_a_valid_final_response_exists(packet, bundle, monkeypatch):
    mock_codex(monkeypatch, constructed_review(packet), extra_events=[{
        "type": "item.completed", "item": {"type": "error", "message": "Synthetic execution failure."}}])
    result = review.run(bundle, "A", "configured-test-model")
    assert result["status"] == "blocked"
    assert result["failure_category"] == "codex_execution_failed"
    assert result["review"] is None
    assert result["isolation"]["context_audit_passed"] is False
    assert review.load_sealed(bundle / "runs/A/record.json") == result


def test_authentication_failure_is_recorded_without_fabricated_review_or_raw_transport_data(
        bundle, monkeypatch):
    transport_marker = "transport-detail-that-must-not-be-persisted"
    mock_codex(monkeypatch, None, returncode=1, stderr="401 Unauthorized " + transport_marker)
    result = review.run(bundle, "A", "configured-test-model")
    assert result["status"] == "blocked"
    assert result["failure_category"] == "authentication_unavailable"
    assert result["review"] is None and result["finished_at"] is not None
    assert result["isolation"]["context_audit_passed"] is False
    assert transport_marker not in json.dumps(result)
    with pytest.raises((FileNotFoundError, ValueError)):
        review.coordinate(bundle)


def test_invalid_or_wrong_reviewer_response_never_becomes_completed(packet, bundle, monkeypatch):
    mock_codex(monkeypatch, constructed_review(packet, "B"))
    result = review.run(bundle, "A", "configured-test-model")
    assert result["status"] == "rejected"
    assert result["review"] is None


def test_timed_out_execution_keeps_only_blocked_metadata(bundle, monkeypatch):
    monkeypatch.setattr(review.shutil, "which", lambda name: "/synthetic/bin/codex")

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(review.subprocess, "run", timeout)
    result = review.run(bundle, "A", "configured-test-model", timeout=5)
    assert result["status"] == "blocked" and result["failure_category"] == "execution_timeout"
    assert result["review"] is None


@pytest.mark.parametrize("changed_input", ["packet", "configuration"])
def test_manifest_prevents_resealed_input_or_instruction_drift(bundle, monkeypatch, changed_input):
    target = bundle / ("inputs/packet.json" if changed_input == "packet" else "inputs/A.agent.json")
    value = review.load_sealed(target)
    if changed_input == "packet":
        value["cases"][0]["evidence"] = "Changed synthetic input after preparation."
    else:
        value["instructions"] += "\nChanged instructions after preparation."
    target.unlink()
    target.with_name(target.name + ".sha256").unlink()
    review.seal_json(target, value)
    monkeypatch.setattr(review.shutil, "which", lambda name: pytest.fail("Must reject before CLI launch"))
    with pytest.raises(ValueError):
        review.run(bundle, "A", "configured-test-model")


def test_coordinator_rejects_shared_model_session_even_with_separate_run_ids(packet, bundle, monkeypatch):
    mock_codex(monkeypatch, constructed_review(packet, "A"), session="reused-context")
    a = review.run(bundle, "A", "configured-test-model")
    mock_codex(monkeypatch, constructed_review(packet, "B"), session="reused-context")
    b = review.run(bundle, "B", "configured-test-model")
    assert a["run_id"] != b["run_id"]
    assert a["status"] == b["status"] == "completed"
    with pytest.raises(ValueError):
        review.coordinate(bundle)
    assert not (bundle / "proposed_reference.json").exists()


def test_completed_distinct_mocked_sessions_produce_only_a_provisional_dataset(packet, bundle, monkeypatch):
    mock_codex(monkeypatch, constructed_review(packet, "A"), session="context-a")
    review.run(bundle, "A", "configured-test-model")
    mock_codex(monkeypatch, constructed_review(packet, "B"), session="context-b")
    review.run(bundle, "B", "configured-test-model")
    proposal = review.coordinate(bundle)
    assert proposal["proposal_status"] == "ai_only_proposed_not_human_validated"
    assert proposal["human_validated"] is False
    assert proposal["authoritative_decision"] is None
    assert proposal["semantic_ai_adjudication_executed"] is False
    assert proposal["measured_time_saved"] is None and proposal["measured_question_reduction"] is None
    assert set(proposal["review_record_sha256"]) == {"A", "B"}
    assert review.load_sealed(bundle / "proposed_reference.json") == proposal
    with pytest.raises((FileExistsError, ValueError)):
        review.coordinate(bundle)
