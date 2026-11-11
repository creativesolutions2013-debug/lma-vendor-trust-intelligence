"""M6 synthetic analyst-quality measurement. Independent of production evaluators.

This tool scores human-supplied observations against provisional, synthetic
reference annotations. No timings or ROI are inferred. No AI/network/database.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SCENARIOS = HERE / "benchmarks" / "m6_analyst_scenarios_v1.json"


def load_reference(path=SCENARIOS):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != "M6-provisional-v1":
        raise ValueError("Unsupported reference version")
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) < 8:
        raise ValueError("At least eight synthetic scenarios required")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate scenario ID")
    for case in cases:
        if not isinstance(case["reference_concerns"], list) or not isinstance(case["necessary_questions"], list):
            raise ValueError("Invalid reference annotations")
        if not case["evidence"] or not case["customer_requirement"]:
            raise ValueError("Incomplete scenario")
    return data


def _ids(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value) or len(value) != len(set(value)):
        raise ValueError(f"{name} must be a list of unique string IDs")
    return set(value)


def _metric(found, expected):
    return {"true_positive": len(found & expected), "missed": sorted(expected - found),
            "extra": sorted(found - expected),
            "recall": (len(found & expected) / len(expected)) if expected else None,
            "precision": (len(found & expected) / len(found)) if found else None}


def evaluate(reference, observations):
    """Score recorded actions only. Missing observations are missing, not failures."""
    cases = {case["id"]: case for case in reference["cases"]}
    if not isinstance(observations, dict) or not isinstance(observations.get("sessions"), list):
        raise ValueError("Expected a sessions array")
    rows, seen = [], set()
    for session in observations["sessions"]:
        if not isinstance(session, dict):
            raise ValueError("Session must be an object")
        case_id, mode = session.get("case_id"), session.get("mode")
        if case_id not in cases or mode not in ("manual", "lma"):
            raise ValueError("Unknown scenario or review mode")
        reviewer = session.get("reviewer_id")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("Use an anonymous, nonempty reviewer ID")
        key = (reviewer, case_id, mode)
        if key in seen:
            raise ValueError("Duplicate reviewer/case/mode session")
        seen.add(key)
        concerns = _ids(session.get("concern_ids"), "concern_ids")
        questions = _ids(session.get("question_ids"), "question_ids")
        citations = session.get("citations")
        if not isinstance(citations, list):
            raise ValueError("citations must be a list of evidence references")
        for citation in citations:
            if not isinstance(citation, dict) or not isinstance(citation.get("concern_id"), str) or not isinstance(citation.get("quote"), str) or not citation["quote"].strip():
                raise ValueError("Citation must have concern_id and quote")
        elapsed = session.get("elapsed_seconds")
        if elapsed is not None and (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not 0 <= elapsed <= 86400):
            raise ValueError("Invalid observed duration")
        case = cases[case_id]
        valid_quote = {c["id"]: c["quote"] for c in case["reference_concerns"]}
        supported_citations = {c["concern_id"] for c in citations
            if c["concern_id"] in concerns and c["concern_id"] in valid_quote
            and c["quote"] == valid_quote[c["concern_id"]] and c["quote"] in case["evidence"]}
        reference_concerns = set(valid_quote)
        necessary = {q["id"] for q in case["necessary_questions"]}
        # Unsupported citations are reported, never treated as source-verifiable.
        rows.append({"reviewer_id": reviewer, "case_id": case_id, "mode": mode,
            "concerns": _metric(concerns, reference_concerns),
            "questions": _metric(questions, necessary),
            "verified_citation_concern_ids": sorted(supported_citations),
            "uncited_or_unverified_concern_ids": sorted(concerns - supported_citations),
            "elapsed_seconds_observed": elapsed})
    return {"scope": "Synthetic pilot; provisional author annotations require independent human adjudication",
            "reference_version": reference["version"], "sessions_scored": len(rows),
            "manual_sessions": sum(r["mode"] == "manual" for r in rows),
            "lma_sessions": sum(r["mode"] == "lma" for r in rows),
            "observed_timing_sessions": sum(r["elapsed_seconds_observed"] is not None for r in rows),
            "measured_time_saved": None, "measured_question_reduction": None,
            "warning": "No cross-mode improvement or ROI claim without a controlled, counterbalanced study.",
            "results": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=SCENARIOS)
    parser.add_argument("--observations", type=Path, required=True, help="Anonymous analyst observations JSON")
    parser.add_argument("--output", type=Path, help="Optional output JSON file")
    args = parser.parse_args()
    result = evaluate(load_reference(args.reference), json.loads(args.observations.read_text(encoding="utf-8")))
    report = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
