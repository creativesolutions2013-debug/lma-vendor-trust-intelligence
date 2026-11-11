"""M5C frozen holdout: measure baseline misses without tuning the extractor.

This is a repeatable, separately authored *synthetic* benchmark, not a field
accuracy claim or a statistically representative external blind study. The
gold text is read-only at scoring time; metrics never gate correctness unless
source integrity or human-confirmation invariants are broken.
"""
from datetime import date
from io import BytesIO
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from src.upload_assessment import Intake, build_assessment, read_upload
from src.evidence_source_validation import segment_id
from test_upload_assessment import pdf_bytes

CORPUS_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "m5c_holdout_v1.json"
TYPED = {
    "enabled_version", "disabled_version", "achieved_rto_minutes",
    "achieved_rpo_minutes", "scope_complete", "completed",
}


def _valid_docx(lines):
    """A minimally conforming WordprocessingML package, one paragraph per line."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paragraphs = "".join(
        '<w:p><w:r><w:t xml:space="preserve">' + escape(line) +
        '</w:t></w:r></w:p>' for line in lines
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{ns}"><w:body>{paragraphs}<w:sectPr/>'
        '</w:body></w:document>'
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '</Relationships>'
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
    with ZipFile(BytesIO(output.getvalue())) as archive:
        assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= set(archive.namelist())
    return output.getvalue()


def _case_bytes(case):
    text = case["source"]
    if case["format"] == "txt":
        return text.encode("utf-8")
    if case["format"] == "pdf":
        # Separate source lines into positioned PDF text operators, never OCR.
        assert not any(char in text for char in "()\\")
        return pdf_bytes(text.rstrip("\n").replace("\n", ") Tj 0 -14 Td ("))
    if case["format"] == "docx":
        return _valid_docx(text.rstrip("\n").splitlines())
    raise AssertionError("Unrecognized frozen format")


def _gold_match(gold, fact):
    return (
        gold["dimension"] == fact["dimension"]
        and gold["value"] == fact["value"]
        and gold["subject"].casefold() == fact["subject"].casefold()
        and gold["phrase"].casefold() in fact["quote"].casefold()
    )


def _score(case, intake):
    original = _case_bytes(case)
    bound = read_upload(
        intake, case["id"] + "." + case["format"], original, (case["family"],),
        kind=case["kind"], observed_on=date.fromisoformat(case["observed_on"]),
        service=case["service"], environment=case["environment"],
    )
    assessment = build_assessment(intake, (bound,))
    result = next(e for e in assessment.customer_context["evaluations"]
                  if e["requirement_id"] == case["family"])
    assert result["authoritative"] is False
    assert result["semantic_confirmation"] is False
    assert assessment.customer_context["criteria_basis"].startswith("Predefined synthetic")
    assert all(not f["confirmed"] for f in result["facts"])
    assert all(row.outcome not in ("Met", "Risk Identified") for row in assessment.worklist.rows)
    assert all(not f.confirmed for row in assessment.worklist.rows
               if row.review for f in row.review.facts)

    # A source line, segment identity, fingerprint and original document must
    # agree. A fabricated/shifted quotation is a blocking integrity failure.
    for fact in result["facts"]:
        assert fact["document_id"] == bound.evidence.source.document_id
        assert fact["source_fingerprint"] == bound.evidence.fingerprint
        matching = [
            segment for ordinal, segment in enumerate(bound.evidence.document.segments, 1)
            if fact["source_id"] == segment_id(bound.evidence.source.document_id, ordinal)
            and segment.location == fact["location"]
            and fact["quote"] in segment.text
        ]
        assert matching, (case["id"], fact["source_id"], fact["location"], fact["quote"])
    for source in result["sources"]:
        for citation in source["context_citations"]:
            assert citation["document_id"] == bound.evidence.source.document_id
            assert citation["source_fingerprint"] == bound.evidence.fingerprint
            assert any(
                citation["source_id"] == segment_id(bound.evidence.source.document_id, ordinal)
                and citation["location"] == segment.location
                and citation["quote"] in segment.text
                for ordinal, segment in enumerate(bound.evidence.document.segments, 1)
            ), (case["id"], citation)
    assert bound.evidence.source.content == original

    facts = [f for f in result["facts"] if f["dimension"] in TYPED]
    gold = case["gold"]
    used = set()
    matches = []
    misses = []
    for expected in gold:
        index = next((i for i, f in enumerate(facts)
                      if i not in used and _gold_match(expected, f)), None)
        if index is None:
            misses.append(expected)
        else:
            used.add(index)
            matches.append(expected)
    extra = [{k: f[k] for k in ("dimension", "value", "subject", "quote")}
             for i, f in enumerate(facts) if i not in used]
    eligible_adverse = any(f["direction"] == "adverse" and f["eligible_for_preview"]
                           for f in result["facts"])
    expected_attention = case["attention"]
    return {
        "id": case["id"], "family": case["family"], "format": case["format"],
        "expected_attention": expected_attention, "eligible_adverse": eligible_adverse,
        "status": result["status"],
        "preview": result["preview"]["outcome_if_confirmed"],
        "source_uncertainties": [
            issue for source in result["sources"] for issue in source["uncertainties"]
        ],
        "fact_matches": len(matches), "gold_facts": len(gold),
        "typed_predicted": len(facts), "fact_misses": misses,
        "extra_typed_facts": extra,
        "adverse_case_missed": expected_attention == "exception" and not eligible_adverse,
        "overclaimed_adverse": expected_attention != "exception" and eligible_adverse,
        "needs_human_interpretation": expected_attention == "abstain",
        "annotation": case["reason"],
    }


def _rate(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def benchmark():
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert corpus["version"] == "M5C-holdout-1.1"
    cases = corpus["cases"]
    assert len(cases) >= 12 and len({case["id"] for case in cases}) == len(cases)
    assert {c["format"] for c in cases} == {"txt", "pdf", "docx"}
    assert {c["family"] for c in cases} == {"ENC-01", "BCP-01"}
    assert {c["attention"] for c in cases} == {"exception", "no_exception", "abstain"}
    config = corpus["assessment"]
    intake = Intake(
        "m5c-benchmark-v1", config["vendor"], config["service"],
        "Synthetic independent holdout review",
        environment=config["environment"], as_of=date.fromisoformat(config["as_of"]),
    )
    details = [_score(case, intake) for case in cases]
    n_gold = sum(x["gold_facts"] for x in details)
    n_match = sum(x["fact_matches"] for x in details)
    n_predicted = sum(x["typed_predicted"] for x in details)
    positives = [x for x in details if x["expected_attention"] == "exception"]
    negatives = [x for x in details if x["expected_attention"] == "no_exception"]
    abstentions = [x for x in details if x["expected_attention"] == "abstain"]
    summary = {
        "version": corpus["version"], "scope": "Synthetic bounded TLS/DR only",
        "independence_limit": "Author reviewed product interfaces; this is not a truly external blind corpus or field accuracy estimate.",
        "as_of": config["as_of"], "case_count": len(details),
        "by_format": {fmt: sum(x["format"] == fmt for x in details) for fmt in ("txt", "pdf", "docx")},
        "by_family": {family: sum(x["family"] == family for x in details) for family in ("ENC-01", "BCP-01")},
        "typed_facts": {
            "gold_count": n_gold, "predicted_count": n_predicted,
            "matched_count": n_match, "missed_count": n_gold - n_match,
            "extra_count": n_predicted - n_match,
            "recall": _rate(n_match, n_gold), "precision_against_annotations": _rate(n_match, n_predicted),
        },
        "material_exception_triage": {
            "gold_cases": len(positives),
            "surfaced_eligible_cases": sum(x["eligible_adverse"] for x in positives),
            "missed_cases": sum(x["adverse_case_missed"] for x in positives),
            "case_recall": _rate(sum(x["eligible_adverse"] for x in positives), len(positives)),
            "non_exception_cases": len(negatives),
            "non_exception_false_alarms": sum(x["overclaimed_adverse"] for x in negatives),
            "abstain_expected_cases": len(abstentions),
            "abstain_overclaims": sum(x["overclaimed_adverse"] for x in abstentions),
        },
        "analyst_friction": {
            "observed_browser_minutes": None,
            "actual_human_clicks": None,
            "excess_vendor_questions": None,
            "note": "Not measured in automated corpus; requires an observed analyst walkthrough. Do not invent ROI.",
        },
    }
    return {"summary": summary, "cases": details}


def test_frozen_m5c_baseline_is_reproducible_and_source_verifiable():
    report = benchmark()
    # Benchmark quality is intentionally descriptive: record misses instead of
    # adding false gates or altering extractor logic to pass handpicked examples.
    assert report["summary"]["case_count"] == len(report["cases"])
    assert report["summary"]["typed_facts"]["missed_count"] >= 0
    # False positives and misses are reported, not hidden by a pass/fail target.
    output = json.dumps(report, sort_keys=True, indent=2)
    if os.environ.get("M5C_REPORT_PATH"):
        Path(os.environ["M5C_REPORT_PATH"]).write_text(output + "\n", encoding="utf-8")
    print("M5C_BENCHMARK_REPORT_BEGIN")
    print(output)
    print("M5C_BENCHMARK_REPORT_END")
