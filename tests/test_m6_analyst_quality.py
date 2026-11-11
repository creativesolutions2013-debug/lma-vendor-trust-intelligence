"""M6 scorer contract tests; no product evaluator or external APIs."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "benchmarks" / "m6_analyst_quality.py"
spec = importlib.util.spec_from_file_location("m6_quality", MODULE_PATH)
m6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m6)


def session(case, *, concern_ids=None, question_ids=None, citations=None, elapsed=None, mode="lma"):
    return {"reviewer_id": "analyst-A", "case_id": case["id"], "mode": mode,
            "concern_ids": concern_ids if concern_ids is not None else [],
            "question_ids": question_ids if question_ids is not None else [],
            "citations": citations if citations is not None else [],
            "elapsed_seconds": elapsed}


def test_reference_is_provisional_and_cross_control():
    ref = m6.load_reference()
    assert len(ref["cases"]) == 10
    assert {c["family"] for c in ref["cases"]} >= {"PAM-01", "ENC-01", "BCP-01", "IR-01"}
    assert "provisional" in ref["authoring_note"].lower()


def test_complete_source_cited_observation_scores_without_inventing_roi():
    ref = m6.load_reference()
    case = ref["cases"][0]
    concern = case["reference_concerns"][0]
    question = case["necessary_questions"][0]
    obs = {"sessions": [session(case, concern_ids=[concern["id"]],
        question_ids=[question["id"]],
        citations=[{"concern_id": concern["id"], "quote": concern["quote"]}],
        elapsed=180)]}
    report = m6.evaluate(ref, obs)
    row = report["results"][0]
    assert row["concerns"]["true_positive"] == 1
    assert row["questions"]["true_positive"] == 1
    assert row["verified_citation_concern_ids"] == [concern["id"]]
    assert report["observed_timing_sessions"] == 1
    assert report["measured_time_saved"] is None
    assert report["measured_question_reduction"] is None


def test_fake_quote_and_extra_vendor_questions_are_exposed():
    ref = m6.load_reference()
    case = ref["cases"][0]
    concern = case["reference_concerns"][0]
    report = m6.evaluate(ref, {"sessions": [session(case,
        concern_ids=[concern["id"]], question_ids=["Q-unnecessary"],
        citations=[{"concern_id": concern["id"], "quote": "fabricated"}])]})
    row = report["results"][0]
    assert row["uncited_or_unverified_concern_ids"] == [concern["id"]]
    assert row["questions"]["extra"] == ["Q-unnecessary"]
    assert row["elapsed_seconds_observed"] is None


def test_missing_evidence_is_not_failed_control():
    ref = m6.load_reference()
    case = next(c for c in ref["cases"] if c["id"] == "no-evidence")
    report = m6.evaluate(ref, {"sessions": [session(case, question_ids=["ir-proof"])]})
    assert report["results"][0]["concerns"]["missed"] == []
    assert report["results"][0]["questions"]["missed"] == []


@pytest.mark.parametrize("elapsed", [-1, True, 86401, "12"])
def test_duration_must_be_real_observation(elapsed):
    ref = m6.load_reference()
    with pytest.raises(ValueError, match="duration"):
        m6.evaluate(ref, {"sessions": [session(ref["cases"][0], elapsed=elapsed)]})


def test_invalid_sessions_and_duplicates_rejected():
    ref = m6.load_reference()
    one = session(ref["cases"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        m6.evaluate(ref, {"sessions": [one, one]})
    with pytest.raises(ValueError, match="Unknown"):
        m6.evaluate(ref, {"sessions": [{**one, "mode": "unknown"}]})
    with pytest.raises(ValueError, match="unique"):
        m6.evaluate(ref, {"sessions": [{**one, "question_ids": ["x", "x"]}]})


def test_no_observations_has_no_made_up_measurements():
    report = m6.evaluate(m6.load_reference(), {"sessions": []})
    assert report["sessions_scored"] == 0
    assert report["observed_timing_sessions"] == 0
    assert report["measured_time_saved"] is None


def test_reference_is_json_serializable_and_quotes_are_present():
    ref = m6.load_reference()
    assert json.loads(json.dumps(ref)) == ref
    for case in ref["cases"]:
        for concern in case["reference_concerns"]:
            assert concern["quote"] in case["evidence"]
