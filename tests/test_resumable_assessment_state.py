"""Pure bounded state reconstruction; receipt DTOs here grant no byte access."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

import src.guided_assessment_demo as guided
import src.resumable_assessment_state as state
import src.upload_assessment as uploaded
from src.guided_assessment_demo import active_actions, complete_review, package_bytes, report_payload
from src.organization_methodology import OrganizationMethodology, default_definition
from src.synthetic_evidence_custody import SyntheticEvidenceReceipt, SyntheticEvidenceResult
from src.upload_assessment import Intake, build_assessment, read_upload, record_upload_review


DAY = date(2026, 11, 20)
CONTENT = (
    b"Synthetic recovery plan\nService: Synthetic analytics\nEnvironment: production\n"
    b"Target RTO 120 minutes and RPO 30 minutes. No completed recovery test supplied."
)


@pytest.fixture
def original():
    policy = OrganizationMethodology.from_dict(default_definition("synthetic-a"))
    intake = Intake("1001", "Synthetic vendor", "Synthetic analytics", "Synthetic reporting",
                    as_of=DAY, organization_id="synthetic-a", methodology=policy)
    upload = read_upload(intake, "dr-policy.txt", CONTENT, ("BCP-01",), kind="policy", observed_on=DAY)
    receipt = SyntheticEvidenceReceipt(1, 11, 101, 1001, 9001, "a" * 32,
        sha256(CONTENT).hexdigest(), len(CONTENT), "dr-policy.txt",
        datetime(2026, 11, 20, 12, tzinfo=timezone.utc), "https://synthetic.invalid", "reader",
        "sid_synthetic", "Analyst", 501)
    packet = state.parse_state(state.encode_draft(intake, (upload,), (receipt,)))
    return intake, upload, receipt, packet


def results(original):
    return (SyntheticEvidenceResult(original[2], CONTENT),)


def reviewed(original):
    intake, upload, _, packet = original
    model = build_assessment(intake, (upload,))
    model, actions = record_upload_review(model, (), "BCP-01", "Request Evidence",
        "Provide completed recovery results and dependency coverage.", confirms_insufficiency=True)
    model, actions = record_upload_review(model, actions, "BCP-01", "Create Finding",
        "Operating proof remains unavailable; this is a draft finding.")
    completion = complete_review(model, actions)
    return model, actions, completion, state.with_review_state(packet, model, actions, completion)


def test_canonical_draft_round_trip_rebuilds_same_model_and_original(original):
    intake, upload, _, packet = original
    restored = state.restore_state(packet, results(original), as_of=DAY)
    assert restored.intake == intake and restored.uploads == (upload,)
    assert restored.model == build_assessment(intake, (upload,))
    assert restored.actions == () and restored.completion is None and restored.completion_stale is False
    encoded = state.encode_state(packet)
    assert state.encode_state(state.parse_state(encoded)) == encoded
    assert len(encoded) <= state.MAX_STATE_BYTES
    assert packet["methodology"] == intake.methodology.json_text
    assert packet["methodology_sha256"] == intake.methodology.fingerprint
    detached = state.parse_state(encoded)
    detached["intake"]["vendor"] = "Changed detached value"
    assert packet["intake"]["vendor"] == intake.vendor
    for forbidden in ("worklist", "risk", "facts", "report", "st.session_state", "pickle"):
        assert forbidden not in packet


def test_native_review_history_completion_citations_and_zip_survive_reconstruction(original, monkeypatch):
    model, actions, completion, packet = reviewed(original)
    def blocked(*args, **kwargs):
        pytest.fail("resume replayed a past review as a new analyst command")
    monkeypatch.setattr(uploaded, "record_upload_review", blocked)
    monkeypatch.setattr(guided, "record_action", blocked)
    restored = state.restore_state(packet, results(original), as_of=DAY)
    assert restored.actions == actions and restored.completion == completion
    assert restored.completion_stale is False
    assert report_payload(restored.model, restored.actions, restored.completion) == report_payload(model, actions, completion)
    report = report_payload(restored.model, restored.actions, restored.completion)
    assert report["evidence_gap_reviews"][0]["status"] == "Current"
    assert report["findings"][0]["context_status"] == "Current"
    assert report["risk"]["residual_score"] is None and report["review_completion"]["vendor_approved"] is False
    with ZipFile(BytesIO(package_bytes(restored.model, restored.actions, restored.completion))) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        artifact, = manifest["artifacts"]
        assert archive.read(artifact["archive_path"]) == CONTENT
        assert artifact["sha256"] == sha256(CONTENT).hexdigest()
        report_json = json.loads(archive.read("report.json"))
        assert report_json["findings"][0]["citations"][0]["archive_path"] == artifact["archive_path"]


@pytest.mark.parametrize("change", ["date", "intake", "methodology"])
def test_changed_current_context_stales_reviews_and_completion_without_recapturing_originals(original, change):
    _, actions, _, packet = reviewed(original)
    current_day = DAY
    if change == "date":
        current_day += timedelta(days=1)
    elif change == "intake":
        packet["intake"]["use_case"] = "Changed declared use case"
    else:
        definition = json.loads(packet["methodology"])
        definition["version"] = "2"
        definition["assurance"]["rto_minutes"] = 60
        policy = OrganizationMethodology.from_dict(definition)
        packet["methodology"], packet["methodology_sha256"] = policy.json_text, policy.fingerprint
    restored = state.restore_state(packet, results(original), as_of=current_day)
    assert restored.intake.as_of == current_day
    assert restored.uploads[0].evidence == original[1].evidence
    assert restored.uploads[0].evidence.source.captured_on == DAY
    assert restored.actions == actions and active_actions(restored.model, restored.actions) == ()
    assert restored.completion is None and restored.completion_stale is True
    report = report_payload(restored.model, restored.actions)
    assert report["evidence_gap_reviews"][0]["status"] == "Stale context"
    assert all(action["status"] == "Stale context" for action in report["analyst_actions"])


def test_source_declarations_stay_original_when_intake_scope_changes(original):
    packet = original[3]
    packet["intake"]["service"] = "Changed assessment service"
    packet["intake"]["environment"] = "Changed environment"
    restored = state.restore_state(packet, results(original), as_of=DAY)
    assert restored.uploads[0].evidence.source.service == original[0].service
    assert restored.uploads[0].evidence.source.environment == original[0].environment
    assert restored.model.worklist.scope.service == "Changed assessment service"


@pytest.mark.parametrize("change", ["bytes", "routing"])
def test_changed_original_or_routing_retains_but_stales_historical_review(original, change):
    _, actions, _, historical = reviewed(original)
    intake, _, receipt, _ = original
    content = CONTENT + b"\nAdditional synthetic policy context." if change == "bytes" else CONTENT
    routing = () if change == "routing" else ("BCP-01",)
    upload = read_upload(intake, "dr-policy.txt", content, routing, kind="policy", observed_on=DAY)
    if change == "bytes":
        receipt = replace(receipt, evidence_id=9002, generation="b" * 32,
                          sha256=sha256(content).hexdigest(), byte_length=len(content))
    packet = state.parse_state(state.encode_draft(intake, (upload,), (receipt,)))
    for field in ("actions", "need_reviews", "completion"):
        packet[field] = historical[field]  # The server carries durable history.
    restored = state.restore_state(packet, (SyntheticEvidenceResult(receipt, content),), as_of=DAY)
    assert restored.actions == actions and active_actions(restored.model, restored.actions) == ()
    assert restored.completion is None and restored.completion_stale is True
    assert report_payload(restored.model, restored.actions)["evidence_gap_reviews"][0]["status"] == "Stale context"


def test_unlinked_historical_need_review_survives_new_completion_without_becoming_current(original):
    _, _, _, packet = reviewed(original)
    historical = dict(packet["need_reviews"][0], need_id="evidence-removed-custom-requirement",
                      rationale="Historical insufficiency for a removed requirement.")
    packet["need_reviews"].append(historical)
    restored = state.restore_state(packet, results(original), as_of=DAY)
    assert all(review.need_id != historical["need_id"] for link in restored.model.scenario.assurance_links
               for review in link.need_reviews)
    updated = state.with_review_state(packet, restored.model, restored.actions, restored.completion)
    assert historical in updated["need_reviews"]
    rebuilt = state.restore_state(updated, results(original), as_of=DAY)
    report = report_payload(rebuilt.model, rebuilt.actions, rebuilt.completion)
    assert all(review["need_id"] != historical["need_id"] for review in report["evidence_gap_reviews"])


@pytest.mark.parametrize("payload", [None, "{}", bytearray(b"{}"), b"", b"[]", b"null", b"pickle-looking-data",
    b"\xff", b"{" + b" " * state.MAX_STATE_BYTES, b'{"schema_version":NaN}', b'{"schema_version":Infinity}'])
def test_only_bounded_well_formed_json_bytes_are_parsed(payload):
    with pytest.raises(ValueError):
        state.parse_state(payload)


def test_duplicate_json_fields_at_all_nesting_levels_deny(original):
    encoded = state.encode_state(original[3])
    for payload in (encoded[:-1] + b',"schema_version":1}',
                    encoded.replace(b'"vendor":"Synthetic vendor"', b'"vendor":"Synthetic vendor","vendor":"Synthetic vendor"')):
        with pytest.raises(ValueError):
            state.parse_state(payload)


@pytest.mark.parametrize("field,value", [("schema_version", True), ("schema_version", 2),
    ("engine_version", "future-engine"), ("methodology_sha256", "0" * 64),
    ("methodology", {}), ("sources", []), ("actions", {}), ("need_reviews", {}),
    ("completion", {"vendor_approved": True})])
def test_invalid_contract_versions_types_and_state_fields_deny(original, field, value):
    packet = original[3]
    packet[field] = value
    with pytest.raises(ValueError):
        state.encode_state(packet)


@pytest.mark.parametrize("field", ["model", "worklist", "risk", "facts", "report", "session_state", "pickle"])
def test_unknown_executable_or_derived_state_fields_deny(original, field):
    packet = original[3]
    packet[field] = "untrusted"
    with pytest.raises(ValueError):
        state.encode_state(packet)


@pytest.mark.parametrize("field,value", [("organization_id", True), ("vendor_id", 0), ("engagement_id", -1),
    ("assessment_id", "1001"), ("evidence_id", 2**64), ("generation", "../unsafe"), ("generation", "A" * 32),
    ("sha256", "g" * 64), ("byte_length", True), ("byte_length", 65537), ("filename", "../a.txt"),
    ("filename", "a.exe"), ("requirements", ["BCP-01", "BCP-01"]), ("kind", "verified control"),
    ("captured_on", "2026-11-21"), ("observed_on", "invalid-date"), ("service", "bad\x00scope"),
    ("source_fingerprint", "bad")])
def test_malformed_source_references_and_declarations_deny(original, field, value):
    packet = original[3]
    packet["sources"][0][field] = value
    with pytest.raises(ValueError):
        state.encode_state(packet)


@pytest.mark.parametrize("mutation", ["bytes", "hash", "size", "filename", "generation", "assessment", "capture_date", "binding"])
def test_exact_receipts_original_bytes_and_source_fingerprints_are_required(original, mutation):
    packet = original[3]
    receipt = original[2]
    content = CONTENT
    if mutation == "bytes":
        content = b"X" + CONTENT[1:]
    elif mutation == "binding":
        packet["sources"][0]["source_fingerprint"] = "0" * 64
    else:
        changes = {"hash": {"sha256": "0" * 64}, "size": {"byte_length": len(CONTENT) + 1},
            "filename": {"document_name": "other.txt"}, "generation": {"generation": "b" * 32},
            "assessment": {"assessment_id": 1002},
            "capture_date": {"created_at": receipt.created_at + timedelta(days=1)}}
        receipt = replace(receipt, **changes[mutation])
    with pytest.raises(ValueError):
        state.restore_state(packet, (SyntheticEvidenceResult(receipt, content),), as_of=DAY)


def test_four_original_limit_duplicate_names_and_mismatched_assessment_deny(original):
    packet = original[3]
    packet["sources"] = packet["sources"] * 5
    with pytest.raises(ValueError):
        state.encode_state(packet)
    packet["sources"] = packet["sources"][:2]
    with pytest.raises(ValueError):
        state.encode_state(packet)
    packet["sources"] = packet["sources"][:1]
    packet["intake"]["assessment_id"] = "1002"
    with pytest.raises(ValueError):
        state.encode_state(packet)


@pytest.mark.parametrize("mutation", ["confirmed_citation", "supported_review", "review_facts", "missing_confirmation",
    "naive_time", "unknown_action", "unknown_field"])
def test_history_cannot_gain_fact_confirmation_or_governed_meaning(original, mutation):
    _, _, _, packet = reviewed(original)
    if mutation == "confirmed_citation":
        packet["actions"][0]["citations"][0]["confirmed"] = True
    elif mutation == "supported_review":
        packet["need_reviews"][0]["decision"] = "supported"
    elif mutation == "review_facts":
        packet["need_reviews"][0]["fact_fingerprints"] = ["a" * 64]
    elif mutation == "missing_confirmation":
        packet["need_reviews"][0]["confirms"] = False
    elif mutation == "naive_time":
        packet["actions"][0]["recorded_at"] = "2026-11-20T12:00:00"
    elif mutation == "unknown_action":
        packet["actions"][0]["action"] = "Approve vendor"
    else:
        packet["actions"][0]["risk_accepted"] = True
    with pytest.raises(ValueError):
        state.encode_state(packet)


def test_state_and_history_caps_deny_without_truncation(original):
    _, _, _, packet = reviewed(original)
    packet["actions"] = packet["actions"][:1] * (state.MAX_ACTIONS + 1)
    with pytest.raises(ValueError):
        state.encode_state(packet)
    _, _, _, packet = reviewed(original)
    packet["actions"] = packet["actions"][:1] * state.MAX_ACTIONS
    for action in packet["actions"]:
        action["citations"][0]["quote"] = "x" * 12000
    with pytest.raises(ValueError):
        state.encode_state(packet)


def test_current_date_cannot_roll_back_and_results_cannot_be_missing_or_untyped(original):
    for as_of, supplied in ((DAY - timedelta(days=1), results(original)), (DAY, ()),
                            (DAY, (CONTENT,)), (datetime(2026, 11, 20), results(original))):
        with pytest.raises(ValueError):
            state.restore_state(original[3], supplied, as_of=as_of)


def test_encode_draft_requires_matching_native_original_capture_and_methodology(original):
    intake, upload, receipt, _ = original
    for supplied_intake, supplied_uploads, supplied_receipts in (
        (replace(intake, methodology=None), (upload,), (receipt,)),
        (intake, [upload], (receipt,)), (intake, (upload,), ()),
        (intake, (upload,), (replace(receipt, created_at=receipt.created_at + timedelta(days=1)),)),
    ):
        with pytest.raises(ValueError):
            state.encode_draft(supplied_intake, supplied_uploads, supplied_receipts)
