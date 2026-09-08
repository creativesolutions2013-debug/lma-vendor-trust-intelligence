import io
import json
import os
import re
from datetime import datetime
from typing import Any, Dict

from pypdf import PdfReader


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _find(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else default

def _find_first(patterns, text: str, default: str = "") -> str:
    for pattern in patterns:
        value = _find(pattern, text)
        if value:
            return value
    return default

def normalize_date(value: str) -> str:
    if not value:
        return ""

    formats = [
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return value.strip()


def local_soc2_extraction(text: str) -> Dict[str, Any]:
    """Deterministic fallback for demo/testing when no API key is configured."""
    issuer = _find_first(
        [
            r"Independent Auditor\s+([^\n]+)",
            r"Independent service auditor\s+([^\n]+)",
            r"Service auditor\s+([^\n]+)",
            r"Auditor\s+([^\n]+)",
        ],
        text,
    )
    report_date = _find_first(
        [
            r"Report Date\s+([^\n]+)",
            r"Report issued\s+([^\n]+)",
            r"Report issue date\s+([^\n]+)",
            r"Date of report\s+([^\n]+)",
        ],
        text,
    )
    period = re.search(
        r"(?:Examination Period|Period under examination)\s+"
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})"
        r"\s*(?:[-–]|through|to)\s*"
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    opinion = _find_first(
        [
            r"Auditor Opinion\s+([^\n]+)",
            r"Conclusion\s+([^\n]+)",
            r"Service Auditor Conclusion\s+([^\n]+)",
        ],
        text,
    )
    exception_mentions = re.findall(r"\bException\b", text, flags=re.IGNORECASE)

    # For the synthetic report and similar reports, identify explicit exception rows.
    control_blocks = re.findall(
        r"(?ms)^(CC\d+(?:\.\d+)?|A\d+(?:\.\d+)?)\s*\n"
        r"(.*?)(?=^(?:CC\d+(?:\.\d+)?|A\d+(?:\.\d+)?)\s*$|\Z)",
        text,
    )

    explicit_exception_rows = []

    for control, block in control_blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]

        for index, line in enumerate(lines):
            if re.fullmatch(
                r"Exception(?:\s+noted)?",
                line,
                flags=re.IGNORECASE,
            ):
                description = " ".join(lines[index + 1 :]).strip()

                if description:
                    explicit_exception_rows.append(
                        (control, description)
                    )
                break
    cuec_section = ""
    cuec_match = re.search(
        r"Complementary User Entity Controls.*?(?=\n(?:\d+\.\s+)?Subservice Organizations|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if cuec_match:
        cuec_section = cuec_match.group(0).strip()

    subservice_section = ""
    sub_match = re.search(
        r"Subservice Organizations.*?(?=\n(?:\d+\.\s+)?Analyst Test Notes|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if sub_match:
        subservice_section = sub_match.group(0).strip()

    exceptions = [
        {"control_id": control, "description": desc.strip(), "severity": "Moderate"}
        for control, desc in explicit_exception_rows
    ]

    return {
        "document_type": "SOC 2 Type II" if re.search(r"SOC\s*2\s*TYPE\s*II", text, re.I) else "SOC 2",
        "issuer": issuer.replace("(Fictional)", "").strip(),
        "document_date": normalize_date(report_date),
        "coverage_start": normalize_date(period.group(1)) if period else "",
        "coverage_end": normalize_date(period.group(2)) if period else "",
        "opinion": (
            "Unmodified"
            if re.search(r"\bunmodified\b", opinion, re.IGNORECASE)
            else "Unqualified"
            if re.search(r"\bunqualified\b", opinion, re.IGNORECASE)
            else opinion.split(",")[0].strip()
            if opinion
            else ""
        ),
        "exceptions_count": len(exceptions),
        "exceptions": exceptions,
        "cuecs_summary": cuec_section[:1800],
        "subservice_organizations_summary": subservice_section[:1800],
        "confidence": 0.72,
        "extraction_method": "Local parser",
        "review_notes": "Fallback parser used. Analyst review is required before accepting metadata.",
    }


def ai_soc2_extraction(text: str, api_key: str, model: str = "gpt-5.6-luna") -> Dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = f"""
You are a third-party security assurance analyst. Extract structured metadata from the SOC 2 report text below.

Return ONLY valid JSON with these keys:
document_type, issuer, document_date, coverage_start, coverage_end, opinion,
exceptions_count, exceptions, cuecs_summary, subservice_organizations_summary,
confidence, extraction_method, review_notes.

Rules:
- Use ISO YYYY-MM-DD dates when the date is unambiguous.
- exceptions must be an array of objects with control_id, description, severity.
- Do not invent missing facts. Use empty strings or [].
- confidence is a number from 0 to 1.
- extraction_method must be "OpenAI".
- Flag ambiguity or potential issues in review_notes.

REPORT TEXT:
{text[:60000]}
"""
    response = client.responses.create(
        model=model,
        input=prompt,
    )
    raw = response.output_text.strip()
    raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    result = json.loads(raw)
    result["extraction_method"] = "OpenAI"
    return result


def extract_soc2_metadata(file_bytes: bytes, api_key: str | None = None) -> Dict[str, Any]:
    text = extract_pdf_text(file_bytes)
    if not text.strip():
        raise ValueError("No readable text was found in the PDF.")

    if api_key:
        try:
            return ai_soc2_extraction(text, api_key)
        except Exception as exc:
            fallback = local_soc2_extraction(text)
            fallback["review_notes"] = f"OpenAI extraction failed; local parser used instead. Error: {exc}"
            return fallback

    return local_soc2_extraction(text)
