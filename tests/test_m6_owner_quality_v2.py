"""Focused regression checks for source-bound, non-authoritative M6 v2 addendum."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m6_owner_quality_v2", ROOT / "benchmarks" / "m6_owner_quality_v2.py")
m6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m6)


def _write(tmp_path, data):
    p = tmp_path / "proposal.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _base():
    return json.loads(m6.ADDENDUM.read_text(encoding="utf-8"))


def test_versioned_addendum_accepts_both_narrow_corrections():
    output = m6.validate()
    assert {row["case_id"] for row in output["amendments"]} == {"M6-02", "M6-04"}
    assert output["measured_time_saved"] is None
    assert output["measured_question_reduction"] is None


@pytest.mark.parametrize(("field", "value"), [
    ("human_validated", True), ("automatic_approval", True),
    ("authoritative_risk_mutation", True), ("measured_time_saved", 120),
    ("measured_question_reduction", 20)])
def test_forbidden_assurance_claims_rejected(tmp_path, field, value):
    data = _base()
    data[field] = value
    with pytest.raises(ValueError, match="assurance"):
        m6.validate(addendum_path=_write(tmp_path, data))


def test_original_reference_sha_must_match(tmp_path):
    source = json.loads(m6.SOURCE.read_text(encoding="utf-8"))
    source["reference_version"] = "modified"
    p = tmp_path / "source.json"
    p.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="source hash"):
        m6.validate(source_path=p)


def test_original_reference_binding_must_match(tmp_path):
    data = _base()
    data["source_v1_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source binding"):
        m6.validate(addendum_path=_write(tmp_path, data))


def test_only_two_allowed_case_changes(tmp_path):
    data = _base()
    data["amendments"][0]["case_id"] = "M6-03"
    with pytest.raises(ValueError, match="exactly"):
        m6.validate(addendum_path=_write(tmp_path, data))


@pytest.mark.parametrize(("field", "value"), [
    ("method_phishing_resistant", True),
    ("complete_authentication_path_meets_threshold", "failed"),
    ("full_path_failure_confirmed", True)])
def test_mfa_cannot_promote_method_to_full_path_failure(tmp_path, field, value):
    data = _base()
    data["amendments"][0][field] = value
    with pytest.raises(ValueError, match="MFA"):
        m6.validate(addendum_path=_write(tmp_path, data))


@pytest.mark.parametrize(("field", "value"), [
    ("listener_443_rejects_tls_1_0_1_1", False),
    ("complete_production_endpoint_inventory", "complete"),
    ("additional_weak_listener_demonstrated", True),
    ("do_not_repeat_confirmed_443_protocol_questions", False)])
def test_tls_cannot_erase_known_443_result_or_invent_endpoints(tmp_path, field, value):
    data = _base()
    data["amendments"][1][field] = value
    with pytest.raises(ValueError, match="TLS"):
        m6.validate(addendum_path=_write(tmp_path, data))


def test_reference_quote_cannot_be_substituted(tmp_path):
    data = _base()
    data["amendments"][0]["original_quote"] = "Invented evidence"
    with pytest.raises(ValueError, match="citation"):
        m6.validate(addendum_path=_write(tmp_path, data))


def test_customer_threshold_cannot_be_modified(tmp_path):
    data = _base()
    data["amendments"][1]["customer_requirement"] = "Only listener 443 must reject TLS 1.1."
    with pytest.raises(ValueError, match="Customer requirement"):
        m6.validate(addendum_path=_write(tmp_path, data))


def test_original_case_outcomes_are_immutable(tmp_path):
    data = _base()
    data["amendments"][0]["original_demonstrated_weakness"] = False
    with pytest.raises(ValueError, match="Original weakness"):
        m6.validate(addendum_path=_write(tmp_path, data))


def test_mfa_internal_first_fallback_required(tmp_path):
    data = _base()
    data["amendments"][0]["next_action"]["fallback_if_absent"] = ""
    with pytest.raises(ValueError, match="MFA"):
        m6.validate(addendum_path=_write(tmp_path, data))


def test_tls_internal_first_fallback_required(tmp_path):
    data = _base()
    data["amendments"][1]["next_action"]["kind"] = "vendor_question"
    with pytest.raises(ValueError, match="Invalid smallest next action|TLS"):
        m6.validate(addendum_path=_write(tmp_path, data))
