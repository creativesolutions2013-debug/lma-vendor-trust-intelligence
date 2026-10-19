from types import SimpleNamespace
import json
import pytest
from src.evidence_intelligence_mvp import EvidenceDocument, EvidenceSegment
from src.evidence_intelligence_m2 import (
    PILOT_REQUIREMENTS, ReviewRequirement, build_source_index,
    validate_drafts, evaluate_ai_requirements, MAX_SOURCE_CHARS,
)


def document(text="Administrative MFA is required and enforced for every privileged user."):
    return EvidenceDocument("soc2.txt", (EvidenceSegment("Line 1", text),))


def response_for(outcome="Met", quote="Administrative MFA is required and enforced for every privileged user."):
    return {"evaluations": [{"requirement_id": "IAM-01", "outcome": outcome,
        "reason": "The document asserts MFA is required.", "follow_up": "Verify scope and testing.",
        "citations": [{"source_id": "S00001", "quote": quote}]}]}


def reqs():
    return PILOT_REQUIREMENTS[:1]


def test_verified_quote_still_requires_analyst_confirmation():
    result = validate_drafts(response_for(), reqs(), build_source_index([document()]))[0]
    assert result.outcome == "Needs Review"
    assert result.citations[0].filename == "soc2.txt"
    assert result.citations[0].location == "Line 1"


def test_invented_quote_is_rejected_without_citations():
    result = validate_drafts(response_for("Risk Identified", "TLS 1.0 is enabled everywhere."),
                             reqs(), build_source_index([document()]))[0]
    assert result.outcome == "Needs Review"
    assert result.citations == ()
    assert "verifiable" in result.reason


def test_fake_source_id_cannot_be_cited():
    raw = response_for("Risk Identified")
    raw["evaluations"][0]["citations"][0]["source_id"] = "S99999"
    assert validate_drafts(raw, reqs(), build_source_index([document()]))[0].citations == ()


def test_missing_result_not_misclassified_as_evidence_missing():
    result = validate_drafts({"evaluations": []}, reqs(), build_source_index([document()]))[0]
    assert result.outcome == "Needs Review"


def test_source_budget_fails_not_truncates():
    with pytest.raises(ValueError, match="90,000"):
        build_source_index([document("A" * (MAX_SOURCE_CHARS + 1))])


def test_no_evidence_cannot_trigger_api_call():
    with pytest.raises(ValueError, match="No readable"):
        evaluate_ai_requirements([], api_key="fake", client=object(), requirements=reqs())


def test_custom_policy_requirements_are_supported():
    custom = (ReviewRequirement("ENC-CUSTOM", "Use approved encryption.", "Minimum AES-256."),)
    value = validate_drafts({"evaluations": [{"requirement_id": "ENC-CUSTOM", "outcome": "Evidence Missing",
        "reason": "Not established.", "follow_up": "Request configuration.", "citations": []}]},
        custom, build_source_index([document()]))[0]
    assert value.outcome == "Evidence Missing"


def test_api_output_is_always_validated():
    class FakeClient:
        class responses:
            @staticmethod
            def create(**kwargs):
                assert kwargs["store"] is False
                assert kwargs["text"]["format"]["strict"] is True
                return SimpleNamespace(output_text=json.dumps(response_for("Risk Identified")))
    result = evaluate_ai_requirements([document()], api_key="fake", client=FakeClient(),
                                      requirements=reqs())[0]
    assert result.outcome == "Risk Identified"
    assert result.review_required
    assert result.citations


def test_missing_api_key_is_not_silent():
    with pytest.raises(ValueError, match="API key"):
        evaluate_ai_requirements([document()], api_key="", requirements=reqs())


# ---------------------------------------------------------
# M2 evidence-judgment regression cases
# ---------------------------------------------------------

def _evaluate_synthetic_mfa(text, outcome, quote):
    from types import SimpleNamespace
    import json

    def create(**kwargs):
        assert kwargs["store"] is False
        payload = json.loads(kwargs["input"][1]["content"])
        assert text in payload["sources"][0]["text"]

        answer = {
            "evaluations": [{
                "requirement_id": "IAM-01",
                "outcome": outcome,
                "reason": (
                    "Evaluate privileged MFA against documented "
                    "auditor evidence and exceptions."
                ),
                "follow_up": "Confirm scope and current effectiveness.",
                "citations": [{
                    "source_id": "S00001",
                    "quote": quote,
                }],
            }]
        }

        return SimpleNamespace(output_text=json.dumps(answer))

    client = SimpleNamespace(
        responses=SimpleNamespace(create=create)
    )

    return evaluate_ai_requirements(
        [document(text)],
        api_key="synthetic-test-only",
        requirements=reqs(),
        client=client,
    )[0]


def test_m2_supported_auditor_tested_mfa_regression():
    quote = (
        "The independent auditor tested 25 privileged administrator "
        "records and confirmed MFA operated without exceptions."
    )

    text = (
        "SOC 2 Type II. Production SaaS service. "
        + quote
    )

    result = _evaluate_synthetic_mfa(
        text, "Met", quote
    )

    assert result.outcome == "Needs Review"
    assert result.review_required is True
    assert len(result.citations) == 1
    assert result.citations[0].filename == "soc2.txt"
    assert result.citations[0].location == "Line 1"
    assert result.citations[0].excerpt == quote


def test_m2_privileged_mfa_exception_regression():
    quote = (
        "Exception: Four production administrator accounts "
        "could authenticate using passwords without MFA."
    )

    text = (
        "SOC 2 Type II. "
        + quote
        + " Remediation remains incomplete."
    )

    result = _evaluate_synthetic_mfa(
        text, "Risk Identified", quote
    )

    assert result.outcome == "Risk Identified"
    assert result.review_required is True
    assert len(result.citations) == 1
    assert result.citations[0].excerpt == quote
    assert result.citations[0].location == "Line 1"
