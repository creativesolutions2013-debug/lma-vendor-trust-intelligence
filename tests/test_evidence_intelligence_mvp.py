from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest

from src.evidence_intelligence_mvp import (
    evaluate_pilot_requirements,
    read_evidence_document,
)


def analyze(filename, content, **kwargs):
    doc = read_evidence_document(filename, content.encode())
    return {x.requirement_id: x for x in evaluate_pilot_requirements(
        [doc], today=date(2026, 10, 17), **kwargs)}


def test_tls_deprecated_supported_is_flagged_with_real_line():
    out = analyze("architecture.txt", "Production:\nTLS 1.0 and TLS 1.2 are supported.")
    finding = out["ENC-01"]
    assert finding.outcome == "Risk Identified"
    assert finding.citations[0].location == "Line 2"
    assert "TLS 1.0" in finding.citations[0].excerpt


def test_disabled_tls_does_not_create_false_positive():
    out = analyze("architecture.txt", "TLS 1.0 is disabled. TLS 1.2 is enabled.")
    assert out["ENC-01"].outcome == "Needs Review"


def test_no_evidence_is_not_control_failure():
    out = evaluate_pilot_requirements([], today=date(2026, 10, 17))
    assert all(x.outcome == "Evidence Missing" for x in out)
    assert all(not x.citations for x in out)


def test_old_soc2_is_stale_not_control_failure():
    out = analyze("soc2.txt", "SOC 2 Type II\nPeriod under examination\n02/01/2024 through 07/31/2024")
    result = out["SOC2-FRESHNESS"]
    assert result.outcome == "Needs Review"
    assert "outside the 365-day" in result.reason
    assert result.citations[0].filename == "soc2.txt"


def test_recent_soc2_still_requires_scope_validation():
    out = analyze("soc2.txt", "SOC 2 Type II\nPeriod under examination\n02/01/2026 through 07/31/2026")
    assert "within 365 days" in out["SOC2-FRESHNESS"].reason
    assert out["SOC2-FRESHNESS"].outcome == "Needs Review"


def test_privileged_context_flags_low_pentest_for_review():
    out = analyze("pentest.txt", "Penetration Test\nFinding 4: Severity: Low - weak admin session timeout", privileged_access=True)
    result = out["VM-01"]
    assert result.outcome == "Needs Review"
    assert "privileged production" in result.reason
    assert result.citations[0].location == "Line 2"


def test_textless_file_not_silently_accepted():
    with pytest.raises(ValueError, match="No readable text"):
        read_evidence_document("empty.txt", b"   ")


def test_docx_paragraphs_preserve_location():
    out = BytesIO()
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body><w:p><w:r><w:t>TLS 1.0 is supported.</w:t></w:r></w:p></w:body></w:document>')
    with ZipFile(out, "w") as z:
        z.writestr("word/document.xml", xml)
    doc = read_evidence_document("architecture.docx", out.getvalue())
    result = evaluate_pilot_requirements([doc], today=date(2026, 10, 17))[0]
    assert result.outcome == "Risk Identified"
    assert result.citations[0].location == "Paragraph 1"
