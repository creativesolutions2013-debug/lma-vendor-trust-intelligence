"""Validate M6 owner-quality addendum without rewriting sealed AI runs or source labels.

The addendum is a *proposed*, separately versioned interpretation overlay.
It does not execute a model, change a reference, or authorize risk decisions.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/executions/m6_ai_adjudication_20261116_v1/proposed_reference.json"
ADDENDUM = ROOT / "benchmarks/m6_owner_quality_proposal_v2.json"
SOURCE_SHA256 = "935a8e3170539ff71e6b2e256fb850e962bdffd77ba6e626faa0ea63eb8b073b"

def validate(source_path: Path = SOURCE, addendum_path: Path = ADDENDUM) -> dict:
    source_bytes = Path(source_path).read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Original sealed v1 reference differs from recorded source hash")
    source = json.loads(source_bytes)
    proposal = json.loads(Path(addendum_path).read_text(encoding="utf-8"))
    if source.get("reference_version") != "m6-ai-proposed-reference-v1":
        raise ValueError("Unexpected original reference version")
    if proposal.get("version") != "m6-ai-owner-quality-proposal-v2" or proposal.get("source_v1_sha256") != digest:
        raise ValueError("Incorrect source binding or owner proposal version")
    if (proposal.get("status") != "AI_only_provisional_owner_review"
            or proposal.get("human_validated") is not False
            or proposal.get("automatic_approval") is not False
            or proposal.get("authoritative_risk_mutation") is not False
            or proposal.get("measured_time_saved") is not None
            or proposal.get("measured_question_reduction") is not None):
        raise ValueError("Owner addendum cannot imply assurance or measured ROI")
    original_cases = {c["case_id"]: c for c in source["adjudication"]["cases"]}
    if set(original_cases) != {f"M6-{i:02d}" for i in range(1, 11)}:
        raise ValueError("Original 10-case record is incomplete")
    amendments = proposal.get("amendments")
    if not isinstance(amendments, list) or {a.get("case_id") for a in amendments if isinstance(a, dict)} != {"M6-02", "M6-04"} or len(amendments) != 2:
        raise ValueError("Owner correction must address exactly M6-02 and M6-04")
    for a in amendments:
        original = original_cases[a["case_id"]]["proposed_assessment"]
        if a.get("original_quote") not in [c["quote"] for c in original["citations"]]:
            raise ValueError("Amendment citation differs from source")
        if a.get("customer_requirement") != original_cases[a["case_id"]]["customer_requirement"]:
            raise ValueError("Customer requirement changed")
        if a.get("original_classifications") != original["classifications"]:
            raise ValueError("Original classifications were rewritten")
        if a.get("original_demonstrated_weakness") is not original["demonstrated_weakness"]:
            raise ValueError("Original weakness claim was rewritten")
        if a.get("scope_of_proposal") != "interpretation_only":
            raise ValueError("Amendment cannot alter product decisions")
        if not isinstance(a.get("residual_uncertainty"), str) or not a["residual_uncertainty"].strip():
            raise ValueError("Explicit residual uncertainty required")
        if not isinstance(a.get("next_action"), dict) or a["next_action"].get("kind") not in ("internal_verification", "analyst_review"):
            raise ValueError("Invalid smallest next action")
    mfa = next(a for a in amendments if a["case_id"] == "M6-02")
    if (mfa.get("method_phishing_resistant") is not False
            or mfa.get("complete_authentication_path_meets_threshold") != "not_established"
            or mfa.get("full_path_failure_confirmed") is not False
            or mfa["next_action"]["kind"] != "internal_verification"
            or not mfa["next_action"].get("fallback_if_absent")):
        raise ValueError("MFA must separate non-resistant method from unknown complete authentication path")
    tls = next(a for a in amendments if a["case_id"] == "M6-04")
    if (tls.get("listener_443_rejects_tls_1_0_1_1") is not True
            or tls.get("complete_production_endpoint_inventory") != "not_established"
            or tls.get("additional_weak_listener_demonstrated") is not False
            or tls["next_action"]["kind"] != "internal_verification"
            or not tls["next_action"].get("fallback_if_absent")
            or tls.get("do_not_repeat_confirmed_443_protocol_questions") is not True):
        raise ValueError("TLS follow-up must focus on unverified endpoints, not repeat 443")
    return proposal

def main():
    proposal = validate()
    print(f"Validated {proposal['version']} with {len(proposal['amendments'])} bounded corrections.")

if __name__ == "__main__":
    main()
