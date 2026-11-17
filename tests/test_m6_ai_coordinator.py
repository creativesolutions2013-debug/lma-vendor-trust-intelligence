"""Synthetic contract regressions for the separate AI coordinator workflow.

All reviewer and coordinator messages below are constructed test fixtures. Mocked
CLI transports are not actual AI reviews or benchmark execution evidence.
"""

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from benchmarks import m6_ai_coordinator as coordinator
from benchmarks import m6_ai_review as review


REAL_RUN = subprocess.run


def constructed_review(packet, agent):
    cases = []
    for source in packet["cases"]:
        cases.append({
            "case_id": source["case_id"],
            "classifications": ["evidence_insufficient"],
            "demonstrated_weakness": False,
            "evidence_sufficiency": "insufficient" if source["evidence_provided"] else "missing",
            "citations": [{"source_id": source["source_id"], "quote": source["evidence"]}]
            if source["evidence_provided"] else [],
            "reasoning": "Constructed fixture: this excerpt alone does not establish the full requirement.",
            "scope_and_freshness": "Only the source's stated scope and dates are available.",
            "uncertainty": "Underlying operating artifacts were not supplied in this synthetic exercise.",
            "alternative_interpretation": "Additional relevant evidence may already exist internally.",
            "minimal_action": {"kind": "internal_verification",
                "text": "Check the existing package for scoped operating evidence.",
                "justification": "Assess available evidence before contacting the vendor."},
            "unnecessary_questions": [],
        })
    return {"schema_version": review.VERSION, "agent_id": agent,
        "input_boundary": {"status": "clean", "notes": "Constructed synthetic fixture only."},
        "cases": cases}


def mock_cli(monkeypatch, response, *, session="synthetic-coordinator-session",
             extra_events=(), events=None, raw_output=None, returncode=0, stderr="",
             on_exec=None):
    """Intercept only Codex; real git reads remain available for source anchors."""
    calls = []
    schemas = []
    transport = [{"type": "thread.started", "thread_id": session}, *extra_events]
    if response is not None:
        transport.append({"type": "item.completed", "item": {
            "type": "agent_message", "text": json.dumps(response)}})
    transport.append({"type": "turn.completed"})
    if events is not None:
        transport = events

    def fake_process(command, **kwargs):
        if command[0] != "/synthetic/bin/codex":
            return REAL_RUN(command, **kwargs)
        calls.append((list(command), kwargs))
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "codex synthetic-test-version\n", "")
        schema_path = Path(command[command.index("--output-schema") + 1])
        schemas.append(json.loads(schema_path.read_text(encoding="utf-8")))
        if on_exec is not None:
            on_exec(command, kwargs)
        output = raw_output if raw_output is not None else "\n".join(
            json.dumps(event) for event in transport)
        return subprocess.CompletedProcess(command, returncode, output, stderr)

    monkeypatch.setattr(review.shutil, "which", lambda name: "/synthetic/bin/codex")
    monkeypatch.setattr(review.subprocess, "run", fake_process)
    return calls, schemas


def reseal(path, value):
    path = Path(path)
    path.unlink()
    path.with_name(path.name + ".sha256").unlink()
    review.seal_json(path, value)


@pytest.fixture
def source(tmp_path, monkeypatch):
    source = tmp_path / "original-blind-reviews"
    review.prepare(source)
    packet = review.load_sealed(source / "inputs/packet.json")
    a = constructed_review(packet, "A")
    a["cases"][0]["minimal_action"] = {
        "kind": "vendor_question", "text": "Provide privileged authentication enforcement evidence.",
        "justification": "The supplied excerpt does not identify methods and recovery paths."}
    a["cases"][0]["unnecessary_questions"] = [{"text": "Is privileged MFA enabled?",
        "reason": "The excerpt already states that privileged MFA is enabled."}]
    b = deepcopy(a)
    b["agent_id"] = "B"
    b["cases"][0]["minimal_action"]["text"] = "Provide scoped method and fallback enforcement artifacts."
    b["cases"][1]["uncertainty"] = "A synthetic reviewer identifies unresolved service-population scope."
    b["cases"][2]["classifications"] = ["demonstrated_exception"]
    b["cases"][2]["demonstrated_weakness"] = True
    b["cases"][2]["reasoning"] = "The excerpt states a production TLS 1.1 listener below the threshold."
    for agent, response in (("A", a), ("B", b)):
        with monkeypatch.context() as isolated:
            mock_cli(isolated, response, session=f"synthetic-source-{agent}")
            result = review.run(source, agent, "configured-synthetic-model")
            assert result["status"] == "completed"
    return source


@pytest.fixture
def payload(source):
    return coordinator.verify_source(source)


def constructed_adjudication(payload):
    rows = []
    for case in payload["cases"]:
        case_id = case["case_id"]
        original = next(row for row in payload["reviews"]["A"]["cases"]
                        if row["case_id"] == case_id)
        packet_case = next(row for row in payload["packet"]["cases"]
                           if row["case_id"] == case_id)
        rows.append({"case_id": case_id, "customer_requirement": packet_case["requirement"],
            "original_case_sha256": deepcopy(case["original_case_sha256"]),
            "proposed_assessment": deepcopy(original),
            "field_reconciliations": [{"field": field, "decision": "prefer_A",
                "rationale": "Constructed test choice: preserve the cautious source-cited proposal.",
                "uncertainty": "This is a synthetic validation fixture, not an actual adjudication.",
                "unresolved": False} for field in case["differing_fields"]],
            "unresolved_fields": [],
            "internal_evidence_availability": "not_established_by_supplied_packet",
            "question_assessments": [{"source_id": question["source_id"],
                "verdict": "conditional", "rationale": "First check existing internal evidence.",
                "smallest_action": {"kind": "internal_verification",
                    "text": "Locate existing scoped operating artifacts before vendor follow-up.",
                    "justification": "Internal availability is unknown from the supplied packet."},
                "uncertainty": "The synthetic packet cannot establish internal availability."}
                for question in case["question_catalog"]]})
    return {"schema_version": coordinator.VERSION,
        "proposal_status": "ai_only_proposed_not_human_validated",
        "human_validated": False, "automatic_approval": False,
        "authoritative_risk_mutation": False,
        "input_boundary": {"status": "clean", "notes": "Constructed synthetic coordinator response."},
        "cases": rows}


@pytest.fixture
def response(payload):
    return constructed_adjudication(payload)


@pytest.fixture
def bundle(source, tmp_path):
    output = tmp_path / "coordinator"
    coordinator.prepare(source, output)
    return output


def test_verified_source_preserves_originals_and_question_identity(source, payload):
    for agent in ("A", "B"):
        original = review.load_sealed(source / f"runs/{agent}/response.json")
        assert payload["reviews"][agent] == original
        assert "review" not in payload["provenance"][agent]
        for case in payload["cases"]:
            row = next(row for row in original["cases"] if row["case_id"] == case["case_id"])
            assert case["original_case_sha256"][agent] == review.digest(review.encoded(row))
    assert payload["packet"] == review.parse_packet()
    assert len(payload["cases"]) == 10
    questions = payload["cases"][0]["question_catalog"]
    expected = {}
    for agent in ("A", "B"):
        row = payload["reviews"][agent]["cases"][0]
        expected[f"{agent}:minimal_action"] = ("vendor_question", row["minimal_action"])
        expected[f"{agent}:unnecessary_questions:0"] = ("unnecessary_question", row["unnecessary_questions"][0])
    assert {row["source_id"] for row in questions} == set(expected)
    for row in questions:
        kind, candidate = expected[row["source_id"]]
        assert row["kind"] == kind and row["text"] == candidate["text"]
        assert row["original_value_sha256"] == review.digest(review.encoded(candidate))


def test_local_preflight_reports_executed_local_checks_and_exact_source_hashes(source, payload):
    preflight = payload["local_preflight"]
    assert preflight["status"] == "passed"
    assert preflight["verification_scope"] == "local_wrapper_checks"
    assert preflight["checks"] == {
        "sealed_json_sidecar_digests_verified": True,
        "response_matches_record_review": True,
        "ten_case_completeness_and_exact_citations_verified": True,
        "completed_clean_distinct_reviewer_runs_verified": True,
        "packet_and_profiles_match_git_source_commit": True,
        "source_artifact_snapshot_recorded": True,
    }
    # Synthetic temporary source bundles are not tracked repository artifacts.
    assert preflight["git_artifact_anchor"] == {
        "applicable": False, "commit": None, "files_verified": []}
    expected = {str(path.relative_to(source)): review.digest(path.read_bytes())
                for path in source.rglob("*") if path.is_file()}
    assert payload["source_integrity"]["artifact_sha256"] == expected
    limitations = " ".join(preflight["limitations"]).lower()
    for concept in ("external signature", "worm", "host", "provider", "model", "statistical", "semantic"):
        assert concept in limitations
    for provenance in payload["provenance"].values():
        assert provenance["model_actual"] is None
        assert provenance["isolation"]["os_isolation_verified"] is False
        assert provenance["isolation"]["statistical_independence_established"] is False


@pytest.mark.parametrize("mutation", [None, "changed_committed_bytes", "unavailable_committed_bytes"])
def test_git_artifact_anchor_requires_each_artifact_and_sidecar_to_match_committed_bytes(
        tmp_path, monkeypatch, mutation):
    """Exercise the local Git comparison with constructed Git command responses."""
    source = tmp_path / "synthetic/source"
    commit = "a" * 40
    raw = review.encoded({"synthetic_only": True})
    committed = {"manifest.json": raw,
                 "manifest.json.sha256": (review.digest(raw) + "\n").encode()}
    snapshot = {name: review.digest(value) for name, value in committed.items()}
    calls = []

    def fake_source_tip(command, **kwargs):
        expected_paths = ["synthetic/source/" + name for name in sorted(snapshot)]
        assert command == ["git", "log", "-1", "--format=%H", "--", *expected_paths]
        assert "synthetic/source" not in command[5:]
        assert "synthetic/source/EXECUTION_REPORT.md" not in command[5:]
        assert "synthetic/source/validation.json" not in command[5:]
        assert kwargs["cwd"] == tmp_path
        return commit + "\n"

    def fake_committed_bytes(requested_commit, path):
        assert requested_commit == commit and path.startswith("synthetic/source/")
        name = path.removeprefix("synthetic/source/")
        calls.append(name)
        if mutation == "unavailable_committed_bytes":
            raise ValueError("Synthetic committed artifact unavailable")
        if mutation == "changed_committed_bytes":
            return b"Different synthetic committed bytes"
        return committed[name]

    monkeypatch.setattr(coordinator, "ROOT", tmp_path)
    monkeypatch.setattr(coordinator.subprocess, "check_output", fake_source_tip)
    monkeypatch.setattr(coordinator, "_git_bytes", fake_committed_bytes)
    if mutation is not None:
        with pytest.raises(ValueError):
            coordinator._artifact_git_anchor(source, snapshot)
    else:
        anchor = coordinator._artifact_git_anchor(source, snapshot)
        assert anchor == {"applicable": True, "commit": commit,
                          "files_verified": sorted(committed)}
        assert calls == sorted(committed)


@pytest.mark.parametrize("mutation", ["missing_record", "tampered_seal", "response_mismatch",
    "shared_session", "shared_run", "failed_status", "unclean_context", "blank_model",
    "unsupported_os_claim", "unsupported_independence_claim", "started_response",
    "invalid_original_citation", "incomplete_original_review"])
def test_source_requires_sealed_matching_completed_distinct_reviews(source, mutation):
    path = source / "runs/B/record.json"
    record = review.load_sealed(path)
    if mutation == "missing_record":
        path.unlink()
    elif mutation == "tampered_seal":
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "response_mismatch":
        response_path = source / "runs/B/response.json"
        value = review.load_sealed(response_path)
        value["cases"][0]["reasoning"] += " Synthetic mismatch."
        reseal(response_path, value)
    elif mutation in {"invalid_original_citation", "incomplete_original_review"}:
        response_path = source / "runs/B/response.json"
        value = review.load_sealed(response_path)
        if mutation == "invalid_original_citation":
            value["cases"][0]["citations"][0]["quote"] = "Fabricated original-review operating evidence."
        else:
            value["cases"].pop()
        record["review"] = deepcopy(value)
        reseal(response_path, value)
        reseal(path, record)
    else:
        a = review.load_sealed(source / "runs/A/record.json")
        if mutation == "shared_session":
            record["session_ids"] = a["session_ids"]
        elif mutation == "shared_run":
            record["run_id"] = a["run_id"]
            started_path = source / "runs/B/started.json"
            started = review.load_sealed(started_path)
            started["run_id"] = a["run_id"]
            reseal(started_path, started)
        elif mutation == "failed_status":
            record["status"] = "blocked"
        elif mutation == "unclean_context":
            record["isolation"]["context_audit_passed"] = False
        elif mutation == "unsupported_os_claim":
            record["isolation"]["os_isolation_verified"] = True
        elif mutation == "unsupported_independence_claim":
            record["isolation"]["statistical_independence_established"] = True
        elif mutation == "started_response":
            started_path = source / "runs/B/started.json"
            started = review.load_sealed(started_path)
            started["review"] = deepcopy(record["review"])
            reseal(started_path, started)
        else:
            record["model_requested"] = " "
        reseal(path, record)
    with pytest.raises((ValueError, FileNotFoundError)):
        coordinator.verify_source(source)


@pytest.mark.parametrize("mutation", ["packet", "profile", "source_commit"])
def test_self_consistently_resealed_source_drift_is_rejected(source, mutation):
    manifest_path = source / "manifest.json"
    manifest = review.load_sealed(manifest_path)
    if mutation == "packet":
        path = source / "inputs/packet.json"
        value = review.load_sealed(path)
        value["input_version"] = "Altered synthetic packet metadata"
        reseal(path, value)
        manifest["input_sha256"] = review.digest(review.encoded(value))
        for agent in ("A", "B"):
            path = source / f"runs/{agent}/record.json"
            record = review.load_sealed(path)
            record["input_sha256"] = manifest["input_sha256"]
            reseal(path, record)
    elif mutation == "profile":
        path = source / "inputs/A.agent.json"
        value = review.load_sealed(path)
        value["instructions"] += "\nUnapproved synthetic instruction drift."
        reseal(path, value)
        manifest["config_sha256"]["A"] = review.digest(value["instructions"].encode())
        path = source / "runs/A/record.json"
        record = review.load_sealed(path)
        record["config_sha256"] = manifest["config_sha256"]["A"]
        reseal(path, record)
    else:
        manifest["source_commit"] = "0" * 40
    reseal(manifest_path, manifest)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        coordinator.verify_source(source)


def test_constructed_adjudication_is_complete_but_has_no_governance_authority(payload, response):
    coordinator.validate_adjudication(payload, response)
    assert response["human_validated"] is False
    assert response["automatic_approval"] is False
    assert response["authoritative_risk_mutation"] is False
    missing = response["cases"][8]["proposed_assessment"]
    assert missing["evidence_sufficiency"] == "missing" and missing["citations"] == []


@pytest.mark.parametrize("status", ["contaminated", "unknown"])
def test_declared_C_context_contamination_is_rejected(payload, response, status):
    response["input_boundary"]["status"] = status
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


@pytest.mark.parametrize("mutation", ["failure", "adequate", "fabricated_citation"])
def test_C_cannot_turn_missing_evidence_into_failure_or_adequate_support(payload, response, mutation):
    row = response["cases"][8]
    assessment = row["proposed_assessment"]
    if mutation == "failure":
        assessment["demonstrated_weakness"] = True
        assessment["classifications"] = ["demonstrated_exception"]
    elif mutation == "adequate":
        assessment["evidence_sufficiency"] = "adequate"
        assessment["classifications"] = ["supported_with_limits"]
    else:
        assessment["citations"] = [{"source_id": "M6-09", "quote": "A fabricated incident exercise passed."}]
    # Supply reconciliations so rejection cannot be explained by omitted coverage.
    changed = [key for key in assessment if assessment[key] != payload["reviews"]["A"]["cases"][8][key]]
    row["field_reconciliations"] = [{"field": field, "decision": "synthesize",
        "rationale": "Constructed invalid proposed evidence interpretation.",
        "uncertainty": "The packet contains no incident evidence.", "unresolved": False}
        for field in changed]
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "wrong_threshold",
    "wrong_original_hash", "wrong_nested_case", "foreign_source", "absent_quote"])
def test_cases_thresholds_original_identity_and_citations_are_bound(payload, response, mutation):
    row = response["cases"][0]
    if mutation == "missing":
        response["cases"].pop()
    elif mutation == "duplicate":
        response["cases"][-1] = deepcopy(row)
    elif mutation == "unknown":
        row["case_id"] = "M6-11"
    elif mutation == "wrong_threshold":
        response["cases"][2]["customer_requirement"] = "TLS 1.0 is sufficient for production traffic."
    elif mutation == "wrong_original_hash":
        row["original_case_sha256"]["A"] = "0" * 64
    elif mutation == "wrong_nested_case":
        row["proposed_assessment"]["case_id"] = "M6-02"
    elif mutation == "foreign_source":
        row["proposed_assessment"]["citations"][0]["source_id"] = "M6-03"
    else:
        row["proposed_assessment"]["citations"][0]["quote"] = "Invented synthetic operational assurance."
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


@pytest.mark.parametrize("mutation", ["omitted", "duplicate", "unchanged_field", "prefer_B_mismatch", "prefer_A_mismatch"])
def test_every_original_disagreement_is_accounted_for_and_preferences_match(payload, response, mutation):
    row = response["cases"][0]
    reconciliations = row["field_reconciliations"]
    assert reconciliations and reconciliations[0]["field"] == "minimal_action"
    if mutation == "omitted":
        reconciliations.clear()
    elif mutation == "duplicate":
        reconciliations.append(deepcopy(reconciliations[0]))
    elif mutation == "unchanged_field":
        extra = deepcopy(reconciliations[0])
        extra["field"] = "case_id"
        reconciliations.append(extra)
    elif mutation == "prefer_B_mismatch":
        reconciliations[0]["decision"] = "prefer_B"
    else:
        row["proposed_assessment"]["minimal_action"] = deepcopy(
            payload["reviews"]["B"]["cases"][0]["minimal_action"])
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


def test_matching_prefer_B_and_explicitly_unresolved_retain_both_are_allowed(payload, response):
    row = response["cases"][0]
    row["field_reconciliations"][0]["decision"] = "prefer_B"
    row["proposed_assessment"]["minimal_action"] = deepcopy(
        payload["reviews"]["B"]["cases"][0]["minimal_action"])
    coordinator.validate_adjudication(payload, response)
    row["field_reconciliations"][0].update(decision="retain_both", unresolved=True)
    row["unresolved_fields"] = ["minimal_action"]
    coordinator.validate_adjudication(payload, response)


def test_C_can_challenge_an_agreed_original_judgment_with_explicit_synthesis(payload, response):
    original = deepcopy(payload)
    row = response["cases"][3]
    assert payload["cases"][3]["differing_fields"] == []
    row["proposed_assessment"]["classifications"].append("unresolved_ambiguity")
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)
    row["field_reconciliations"] = [{"field": "classifications", "decision": "synthesize",
        "rationale": "Constructed independent C challenge to a judgment both fixtures shared.",
        "uncertainty": "This tests reconciliation coverage, not substantive benchmark correctness.",
        "unresolved": True}]
    row["unresolved_fields"] = ["classifications"]
    coordinator.validate_adjudication(payload, response)
    assert payload == original
    row["field_reconciliations"][0]["decision"] = "prefer_A"
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


@pytest.mark.parametrize("mutation", ["retain_without_unresolved", "unlisted_unresolved", "unflagged_list", "duplicate_list"])
def test_unresolved_flags_and_retained_disagreements_must_match(payload, response, mutation):
    row = response["cases"][0]
    reconciliation = row["field_reconciliations"][0]
    if mutation == "retain_without_unresolved":
        reconciliation["decision"] = "retain_both"
    elif mutation == "unlisted_unresolved":
        reconciliation["unresolved"] = True
    elif mutation == "unflagged_list":
        row["unresolved_fields"] = ["minimal_action"]
    else:
        reconciliation["unresolved"] = True
        row["unresolved_fields"] = ["minimal_action", "minimal_action"]
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown_id", "rewritten_text", "claimed_internal_availability"])
def test_question_catalog_requires_exact_coverage_without_inventing_internal_availability(payload, response, mutation):
    row = response["cases"][0]
    questions = row["question_assessments"]
    assert len(questions) == 4
    if mutation == "missing":
        questions.pop()
    elif mutation == "duplicate":
        questions[-1] = deepcopy(questions[0])
    elif mutation == "unknown_id":
        questions[0]["source_id"] = "A:unnecessary_questions:99"
    elif mutation == "rewritten_text":
        questions[0]["text"] = "An invented replacement for the original question."
    else:
        row["internal_evidence_availability"] = "all_internal_evidence_checked"
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


def test_necessary_question_cannot_reconcile_to_no_action(payload, response):
    question = response["cases"][0]["question_assessments"][0]
    question["verdict"] = "necessary"
    coordinator.validate_adjudication(payload, response)
    question["smallest_action"] = {"kind": "no_action", "text": "Take no action.",
        "justification": "Constructed contradictory action for a necessary question."}
    with pytest.raises(ValueError, match="necessary question cannot propose no action"):
        coordinator.validate_adjudication(payload, response)


@pytest.mark.parametrize("field", ["human_validated", "automatic_approval", "authoritative_risk_mutation"])
@pytest.mark.parametrize("invalid", [True, 0, "false"])
def test_governance_booleans_are_explicitly_false_not_truthy_or_numeric(payload, response, field, invalid):
    response[field] = invalid
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


@pytest.mark.parametrize("location", ["root", "case", "assessment", "action", "reconciliation", "question", "smallest_action"])
def test_unauthorized_approval_and_risk_fields_are_rejected_at_nested_levels(payload, response, location):
    row = response["cases"][0]
    objects = {"root": response, "case": row, "assessment": row["proposed_assessment"],
        "action": row["proposed_assessment"]["minimal_action"],
        "reconciliation": row["field_reconciliations"][0],
        "question": row["question_assessments"][0],
        "smallest_action": row["question_assessments"][0]["smallest_action"]}
    objects[location]["authoritative_risk_approved"] = True
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, response)


def test_coordinator_prompt_has_only_explicit_C_instructions_and_verified_source(payload, source):
    prompt = coordinator.coordinator_prompt(payload, "PRIVATE_C_INSTRUCTION_SENTINEL")
    assert "PRIVATE_C_INSTRUCTION_SENTINEL" in prompt
    assert "No tools" in prompt
    for case in payload["packet"]["cases"]:
        assert case["requirement"] in prompt and case["evidence"] in prompt
    for agent in ("A", "B"):
        private_instructions = review.load_sealed(source / f"inputs/{agent}.agent.json")["instructions"]
        assert private_instructions not in prompt
    for forbidden in ('"reference_concerns"', '"necessary_questions"', '"sessions_scored"',
                      "m6_analyst_quality.py", "m6_ai_review_simulation.json"):
        assert forbidden not in prompt


def test_prompt_defines_truthful_input_use_boundary_separately_from_external_assurance(payload):
    prompt = coordinator.coordinator_prompt(payload, "Synthetic coordinator instructions.")
    normalized = " ".join(prompt.split())
    for clause in (
        "input_boundary is your self-report about substantive materials actually used",
        "clean means you used only the supplied allowed materials",
        "contaminated means you used additional substantive materials",
        "unknown means you cannot tell which substantive materials you used",
        "Report the status truthfully",
        "does not by itself establish input contamination",
        "Unknown and contaminated declarations will still be rejected",
        "without claiming you personally inspected the filesystem or recomputed SHA values",
        "Do not run tools or recompute hashes",
    ):
        assert clause in normalized


def test_prepared_manifest_binds_local_preflight_to_input_prompt_and_schema_audits(bundle, payload):
    prepared = review.load_sealed(bundle / "inputs/payload.json")
    manifest = review.load_sealed(bundle / "manifest.json")
    instructions = review.load_sealed(bundle / "inputs/coordinator.agent.json")["instructions"]
    schema = review.load_sealed(bundle / "inputs/coordinator.schema.json")
    provider = review.load_sealed(bundle / "inputs/provider.schema.json")
    assert prepared == payload and prepared["local_preflight"]["status"] == "passed"
    prompt = coordinator.coordinator_prompt(prepared, instructions)
    assert '"local_preflight"' in prompt
    assert prompt.endswith(json.dumps(prepared, indent=2, sort_keys=True))
    assert manifest["input_sha256"] == review.digest(review.encoded(prepared))
    assert manifest["prompt_sha256"] == review.digest(prompt.encode())
    assert manifest["source_snapshot_sha256"] == review.digest(review.encoded(prepared["source_integrity"]))
    assert schema == coordinator.coordinator_schema()
    assert manifest["schema_sha256"] == review.digest(review.encoded(schema))
    assert provider == coordinator.provider_schema()
    assert manifest["provider_schema_sha256"] == review.digest(review.encoded(provider))
    assert "local_preflight" not in schema["properties"]


def test_self_consistently_resealed_preflight_claim_cannot_replace_verified_provenance(bundle, monkeypatch):
    path = bundle / "inputs/payload.json"
    value = review.load_sealed(path)
    value["local_preflight"]["checks"]["response_matches_record_review"] = False
    reseal(path, value)
    manifest_path = bundle / "manifest.json"
    manifest = review.load_sealed(manifest_path)
    instructions = review.load_sealed(bundle / "inputs/coordinator.agent.json")["instructions"]
    manifest["input_sha256"] = review.digest(review.encoded(value))
    manifest["prompt_sha256"] = review.digest(coordinator.coordinator_prompt(value, instructions).encode())
    reseal(manifest_path, manifest)
    monkeypatch.setattr(coordinator.shutil, "which", lambda name: pytest.fail("Must reject before C launch"))
    with pytest.raises(ValueError):
        coordinator.run(bundle, "configured-synthetic-model")
    assert not (bundle / "proposed_reference.json").exists()


def test_provider_projection_is_actual_exec_schema_while_canonical_uniqueness_remains(
        bundle, payload, response, monkeypatch):
    canonical = coordinator.coordinator_schema()
    canonical_before = deepcopy(canonical)
    calls, schemas = mock_cli(monkeypatch, response)
    result = coordinator.run(bundle, "configured-synthetic-model")
    assert result["status"] == "completed"
    assert result["model_requested"] == "configured-synthetic-model"
    assert result["model_actual"] is None
    assert len(schemas) == 1 and schemas[0] == coordinator.provider_schema()
    assert '"uniqueItems"' not in json.dumps(schemas[0])
    assert '"uniqueItems"' in json.dumps(canonical)
    assert coordinator.coordinator_schema() == canonical_before
    assert review.load_sealed(bundle / "inputs/coordinator.schema.json") == canonical_before
    assert review.load_sealed(bundle / "inputs/provider.schema.json") == schemas[0]
    duplicate = deepcopy(response)
    duplicate["cases"][0]["proposed_assessment"]["classifications"] *= 2
    with pytest.raises(ValueError):
        coordinator.validate_adjudication(payload, duplicate)
    command, options = calls[-1]
    assert command[1] == "exec" and "resume" not in command and "fork" not in command
    assert {"--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check"} <= set(command)
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--model") + 1] == "configured-synthetic-model"
    assert "project_doc_max_bytes=0" in command and 'web_search="disabled"' in command
    assert all(feature in command for feature in review.DISABLED_FEATURES)
    assert Path(command[command.index("-C") + 1]) != review.ROOT
    assert options["timeout"] == 600


def test_fresh_C_exec_drops_inherited_thread_and_github_tokens(bundle, source, response, monkeypatch, tmp_path):
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CAAS_SESSION_ID", "CODEX_TOOL_CALL_ID"):
        monkeypatch.setenv(name, "synthetic-inherited-marker")
    calls, _ = mock_cli(monkeypatch, response)
    codex_home = tmp_path / "synthetic-authorized-home"
    result = coordinator.run(bundle, "configured-synthetic-model", codex_home=codex_home)
    assert result["status"] == "completed" and result["adjudication"] == response
    _, options = calls[-1]
    assert options["env"]["CODEX_HOME"] == str(codex_home.resolve())
    assert "synthetic-inherited-marker" not in options["input"]
    assert all(name not in options["env"] for name in (
        "GH_TOKEN", "GITHUB_TOKEN", "CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CAAS_SESSION_ID", "CODEX_TOOL_CALL_ID"))
    assert result["isolation"]["context_audit_passed"] is True
    assert result["isolation"]["os_isolation_verified"] is False
    assert result["isolation"]["statistical_independence_established"] is False
    proposal = review.load_sealed(bundle / "proposed_reference.json")
    assert proposal["adjudication"] == response
    assert proposal["original_reviews"] == coordinator.verify_source(source)["reviews"]
    assert proposal["local_preflight"] == coordinator.verify_source(source)["local_preflight"]


@pytest.mark.parametrize("mutation", ["tool", "unknown_event", "malformed_item", "malformed_item_type", "primitive", "raw_non_json",
    "source_session", "second_source_session", "two_sessions", "no_session", "blank_session", "two_messages", "no_completion"])
def test_contaminated_or_malformed_transports_cannot_publish(bundle, response, monkeypatch, mutation):
    kwargs = {}
    if mutation == "tool":
        kwargs["extra_events"] = [{"type": "item.completed", "item": {"type": "mcp_tool_call"}}]
    elif mutation == "unknown_event":
        kwargs["extra_events"] = [{"type": "context.loaded"}]
    elif mutation == "malformed_item":
        kwargs["extra_events"] = [{"type": "item.completed", "item": None}]
    elif mutation == "malformed_item_type":
        kwargs["extra_events"] = [{"type": "item.completed", "item": {
            "type": {"private_raw_field": "SYNTHETIC_MALFORMED_TRANSPORT_MARKER"}}}]
    elif mutation == "primitive":
        kwargs["extra_events"] = [42]
    elif mutation == "raw_non_json":
        kwargs["raw_output"] = "transport-marker: not JSON"
    elif mutation == "source_session":
        kwargs["session"] = "synthetic-source-A"
    elif mutation == "second_source_session":
        kwargs["session"] = "synthetic-source-B"
    elif mutation == "two_sessions":
        kwargs["extra_events"] = [{"type": "thread.started", "thread_id": "another-synthetic-C"}]
    elif mutation == "blank_session":
        kwargs["session"] = " "
    else:
        events = [{"type": "thread.started", "thread_id": "synthetic-C"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}},
            {"type": "turn.completed"}]
        if mutation == "no_session":
            events.pop(0)
        elif mutation == "two_messages":
            events.insert(2, deepcopy(events[1]))
        else:
            events.pop()
        kwargs["events"] = events
    mock_cli(monkeypatch, response, **kwargs)
    result = coordinator.run(bundle, "configured-synthetic-model")
    assert result["status"] == "rejected" and result["adjudication"] is None
    assert result["isolation"]["context_audit_passed"] is False
    assert not (bundle / "proposed_reference.json").exists()
    assert review.load_sealed(bundle / "runs/coordinator/record.json") == result
    assert "SYNTHETIC_MALFORMED_TRANSPORT_MARKER" not in json.dumps(result)


@pytest.mark.parametrize("mutation", ["auth", "error_item", "turn_failed", "timeout", "invalid_response"])
def test_failed_or_invalid_C_execution_never_publishes_or_persists_transport_details(
        bundle, response, monkeypatch, mutation):
    marker = "SYNTHETIC_PRIVATE_TRANSPORT_MARKER"
    if mutation == "auth":
        mock_cli(monkeypatch, None, returncode=1, stderr="401 Unauthorized " + marker)
    elif mutation == "error_item":
        mock_cli(monkeypatch, response, extra_events=[{"type": "item.completed", "item": {
            "type": "error", "message": marker}}])
    elif mutation == "turn_failed":
        mock_cli(monkeypatch, response, extra_events=[{"type": "turn.failed", "error": {"message": marker}}])
    elif mutation == "timeout":
        def timeout(command, options):
            raise subprocess.TimeoutExpired(command, options["timeout"], stderr=marker)
        mock_cli(monkeypatch, response, on_exec=timeout)
    else:
        response["cases"][0]["customer_requirement"] = "Invented lower customer threshold."
        mock_cli(monkeypatch, response)
    result = coordinator.run(bundle, "configured-synthetic-model", timeout=7)
    assert result["status"] in {"blocked", "rejected"}
    assert result["adjudication"] is None
    assert marker not in json.dumps(result)
    assert not (bundle / "proposed_reference.json").exists()


@pytest.mark.parametrize("mutation", ["payload", "provider_schema", "coordinator_profile", "source_after_prepare"])
def test_prepared_input_or_source_drift_is_rejected_before_C_launch(bundle, source, monkeypatch, mutation):
    if mutation == "source_after_prepare":
        path = source / "runs/A/response.json"
        value = review.load_sealed(path)
        value["cases"][0]["reasoning"] += " Altered original after C preparation."
    else:
        names = {"payload": "inputs/payload.json", "provider_schema": "inputs/provider.schema.json",
                 "coordinator_profile": "inputs/coordinator.agent.json"}
        path = bundle / names[mutation]
        value = review.load_sealed(path)
        if mutation == "payload":
            value["cases"][0]["question_catalog"][0]["text"] = "Rewritten original question."
        elif mutation == "provider_schema":
            value["additionalProperties"] = True
        else:
            value["instructions"] += "\nUnapproved instruction drift."
    reseal(path, value)
    monkeypatch.setattr(coordinator.shutil, "which", lambda name: pytest.fail("Must reject before launch"))
    with pytest.raises(ValueError):
        coordinator.run(bundle, "configured-synthetic-model")
    assert not (bundle / "proposed_reference.json").exists()


def test_original_source_mutation_during_C_execution_prevents_publication(bundle, source, response, monkeypatch):
    def mutate_original(command, options):
        path = source / "runs/A/response.json"
        value = review.load_sealed(path)
        value["cases"][0]["reasoning"] += " Original changed while the synthetic C process ran."
        reseal(path, value)
    mock_cli(monkeypatch, response, on_exec=mutate_original)
    result = coordinator.run(bundle, "configured-synthetic-model")
    assert result["status"] == "rejected" and result["adjudication"] is None
    assert not (bundle / "proposed_reference.json").exists()


def test_successful_publication_retains_originals_and_refuses_overwrite(bundle, source, response, monkeypatch):
    originals = {str(path.relative_to(source)): path.read_bytes()
                 for path in source.rglob("*") if path.is_file()}
    mock_cli(monkeypatch, response)
    result = coordinator.run(bundle, "configured-synthetic-model")
    assert result["status"] == "completed"
    proposal = review.load_sealed(bundle / "proposed_reference.json")
    assert proposal["reference_version"] == coordinator.REFERENCE_VERSION
    assert proposal["reference_id"] == "m6-ai-reference:" + result["run_id"]
    for flag in ("human_validated", "automatic_approval", "authoritative_risk_mutation"):
        assert proposal[flag] is False
    assert proposal["adjudication"] == response
    assert proposal["original_reviews"] == coordinator.verify_source(source)["reviews"]
    assert {str(path.relative_to(source)): path.read_bytes()
            for path in source.rglob("*") if path.is_file()} == originals
    with pytest.raises((FileExistsError, ValueError)):
        coordinator.run(bundle, "configured-synthetic-model")
    assert review.load_sealed(bundle / "proposed_reference.json") == proposal


def test_prepare_refuses_existing_destination_without_overwriting(bundle, source):
    before = {str(path.relative_to(bundle)): path.read_bytes()
              for path in bundle.rglob("*") if path.is_file()}
    with pytest.raises((FileExistsError, ValueError)):
        coordinator.prepare(source, bundle)
    assert {str(path.relative_to(bundle)): path.read_bytes()
            for path in bundle.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("name", ["proposed_reference.json", "proposed_reference.json.sha256"])
def test_preexisting_reference_or_digest_blocks_execution_before_model_launch(bundle, monkeypatch, name):
    path = bundle / name
    path.write_text("Synthetic preexisting artifact must be preserved.", encoding="utf-8")
    monkeypatch.setattr(coordinator.shutil, "which", lambda name: pytest.fail("No model launch permitted"))
    with pytest.raises((FileExistsError, ValueError)):
        coordinator.run(bundle, "configured-synthetic-model")
    assert path.read_text(encoding="utf-8") == "Synthetic preexisting artifact must be preserved."
    assert not (bundle / "runs/coordinator").exists()


def test_C_run_identifier_cannot_reuse_an_original_run(bundle, source, monkeypatch):
    original_id = review.load_sealed(source / "runs/A/record.json")["run_id"]
    monkeypatch.setattr(coordinator.uuid, "uuid4", lambda: original_id)
    monkeypatch.setattr(coordinator.shutil, "which", lambda name: pytest.fail("No model launch permitted"))
    with pytest.raises(ValueError):
        coordinator.run(bundle, "configured-synthetic-model")
    assert not (bundle / "runs/coordinator/started.json").exists()
    assert not (bundle / "proposed_reference.json").exists()


@pytest.mark.parametrize("model,timeout", [("", 600), (" ", 600), (None, 600),
    ("configured-synthetic-model", 0), ("configured-synthetic-model", -1),
    ("configured-synthetic-model", True)])
def test_invalid_execution_configuration_is_rejected_without_model_launch(bundle, monkeypatch, model, timeout):
    monkeypatch.setattr(coordinator.shutil, "which", lambda name: pytest.fail("No model launch permitted"))
    with pytest.raises(ValueError):
        coordinator.run(bundle, model, timeout=timeout)
    assert not (bundle / "runs/coordinator").exists()
