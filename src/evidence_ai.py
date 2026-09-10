import io
import json
import re
from datetime import datetime
from typing import Any, Dict

from pypdf import PdfReader


# ---------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------

def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []

    for page in reader.pages:
        pages.append(page.extract_text() or "")

    return "\n".join(pages)


# ---------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------

def _find(
    pattern: str,
    text: str,
    default: str = "",
) -> str:
    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    return (
        match.group(1).strip()
        if match
        else default
    )


def _find_first(
    patterns,
    text: str,
    default: str = "",
) -> str:
    for pattern in patterns:
        value = _find(
            pattern,
            text,
        )

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
            return datetime.strptime(
                value.strip(),
                fmt,
            ).strftime(
                "%Y-%m-%d"
            )

        except ValueError:
            continue

    return value.strip()


# ---------------------------------------------------------
# Local SOC 2 parser
# ---------------------------------------------------------

def local_soc2_extraction(
    text: str,
) -> Dict[str, Any]:
    """
    Deterministic SOC 2 parser used for the public demo
    and as a fallback when no AI API key is configured.

    The parser extracts common SOC 2 metadata,
    control exceptions, CUECs, subservice organizations,
    and produces an explainable extraction-confidence score.
    """

    # -----------------------------------------------------
    # Auditor / issuer
    # -----------------------------------------------------

    issuer = _find_first(
        [
            r"Independent Auditor\s+([^\n]+)",
            r"Independent service auditor\s+([^\n]+)",
            r"Service auditor\s+([^\n]+)",
            r"Auditor\s+([^\n]+)",
        ],
        text,
    )

    # -----------------------------------------------------
    # Report date
    # -----------------------------------------------------

    report_date = _find_first(
        [
            r"Report Date\s+([^\n]+)",
            r"Report issued\s+([^\n]+)",
            r"Report issue date\s+([^\n]+)",
            r"Date of report\s+([^\n]+)",
        ],
        text,
    )

    # -----------------------------------------------------
    # Examination / coverage period
    # -----------------------------------------------------

    period = re.search(
        r"(?:Examination Period|Period under examination)\s+"
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4}"
        r"|\d{1,2}/\d{1,2}/\d{4})"
        r"\s*(?:[-–]|through|to)\s*"
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4}"
        r"|\d{1,2}/\d{1,2}/\d{4})",
        text,
        flags=re.IGNORECASE,
    )

    # -----------------------------------------------------
    # Auditor opinion
    # -----------------------------------------------------

    opinion = _find_first(
        [
            r"Auditor Opinion\s+([^\n]+)",
            r"Conclusion\s+([^\n]+)",
            r"Service Auditor Conclusion\s+([^\n]+)",
        ],
        text,
    )

    # -----------------------------------------------------
    # Control exception extraction
    # -----------------------------------------------------

    control_blocks = re.findall(
        r"(?ms)^"
        r"(CC\d+(?:\.\d+)?|A\d+(?:\.\d+)?)"
        r"\s*\n"
        r"(.*?)"
        r"(?=^"
        r"(?:CC\d+(?:\.\d+)?|A\d+(?:\.\d+)?)"
        r"\s*$|\Z)",
        text,
    )

    explicit_exception_rows = []

    for control, block in control_blocks:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        for index, line in enumerate(
            lines
        ):
            if re.fullmatch(
                r"Exception(?:\s+noted)?",
                line,
                flags=re.IGNORECASE,
            ):
                description = " ".join(
                    lines[
                        index + 1 :
                    ]
                ).strip()

                if description:
                    explicit_exception_rows.append(
                        (
                            control,
                            description,
                        )
                    )

                break

    exceptions = [
        {
            "control_id": control,
            "description": (
                description.strip()
            ),
            "severity": "Moderate",
        }
        for (
            control,
            description,
        ) in explicit_exception_rows
    ]

    # -----------------------------------------------------
    # Complementary User Entity Controls
    # -----------------------------------------------------

    cuec_section = ""

    cuec_match = re.search(
        r"Complementary User Entity Controls"
        r".*?"
        r"(?="
        r"\n(?:\d+\.\s+)?"
        r"Subservice Organizations"
        r"|\Z)",
        text,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    if cuec_match:
        cuec_section = (
            cuec_match
            .group(0)
            .strip()
        )

    # -----------------------------------------------------
    # Subservice organizations
    # -----------------------------------------------------

    subservice_section = ""

    sub_match = re.search(
        r"Subservice Organizations"
        r".*?"
        r"(?="
        r"\n(?:\d+\.\s+)?"
        r"Analyst Test Notes"
        r"|\Z)",
        text,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    if sub_match:
        subservice_section = (
            sub_match
            .group(0)
            .strip()
        )

    # -----------------------------------------------------
    # Dynamic extraction-confidence scoring
    # -----------------------------------------------------

    confidence_score = 0.20

    if issuer:
        confidence_score += 0.15

    if report_date:
        confidence_score += 0.15

    if period:
        confidence_score += 0.20

    if opinion:
        confidence_score += 0.15

    if cuec_section:
        confidence_score += 0.075

    if subservice_section:
        confidence_score += 0.075

    confidence_score = round(
        min(
            confidence_score,
            0.95,
        ),
        2,
    )

    # -----------------------------------------------------
    # Explain what supported the confidence score
    # -----------------------------------------------------

    confidence_reasons = []

    if issuer:
        confidence_reasons.append(
            "Issuer / auditor identified"
        )

    if report_date:
        confidence_reasons.append(
            "Report date identified"
        )

    if period:
        confidence_reasons.append(
            "Coverage period identified"
        )

    if opinion:
        confidence_reasons.append(
            "Auditor opinion identified"
        )

    if cuec_section:
        confidence_reasons.append(
            "Complementary User Entity Controls identified"
        )

    if subservice_section:
        confidence_reasons.append(
            "Subservice organizations identified"
        )

    # -----------------------------------------------------
    # Explain what was not identified
    # -----------------------------------------------------

    confidence_gaps = []

    if not issuer:
        confidence_gaps.append(
            "Issuer / auditor not identified"
        )

    if not report_date:
        confidence_gaps.append(
            "Report date not identified"
        )

    if not period:
        confidence_gaps.append(
            "Coverage period not identified"
        )

    if not opinion:
        confidence_gaps.append(
            "Auditor opinion not identified"
        )

    if not cuec_section:
        confidence_gaps.append(
            "Complementary User Entity Controls not identified"
        )

    if not subservice_section:
        confidence_gaps.append(
            "Subservice organizations not identified"
        )

    # -----------------------------------------------------
    # Recommended analyst actions for missing metadata
    # -----------------------------------------------------

    confidence_actions = []

    if not issuer:
        confidence_actions.append(
            {
                "gap": "Issuer / auditor not identified",
                "action": (
                    "Review the report cover page, independent "
                    "service auditor section, or signature page "
                    "to confirm the audit firm."
                ),
            }
        )

    if not report_date:
        confidence_actions.append(
            {
                "gap": "Report date not identified",
                "action": (
                    "Review the report cover page, auditor opinion, "
                    "or signature section to confirm the report "
                    "issuance date."
                ),
            }
        )

    if not period:
        confidence_actions.append(
            {
                "gap": "Coverage period not identified",
                "action": (
                    "Locate the examination period or system "
                    "description and confirm the start and end "
                    "dates covered by the SOC 2 report."
                ),
            }
        )

    if not opinion:
        confidence_actions.append(
            {
                "gap": "Auditor opinion not identified",
                "action": (
                    "Review the independent service auditor's "
                    "opinion and determine whether the report "
                    "is unmodified, qualified, adverse, or "
                    "contains other limitations."
                ),
            }
        )

    if not cuec_section:
        confidence_actions.append(
            {
                "gap": (
                    "Complementary User Entity Controls "
                    "not identified"
                ),
                "action": (
                    "Review or request the CUEC section to identify "
                    "customer responsibilities that must be met "
                    "for the vendor's controls to operate effectively."
                ),
            }
        )

    if not subservice_section:
        confidence_actions.append(
            {
                "gap": "Subservice organizations not identified",
                "action": (
                    "Confirm whether the vendor relies on "
                    "subservice organizations and determine whether "
                    "they are addressed using the carve-out or "
                    "inclusive method."
                ),
            }
        )

    # -----------------------------------------------------
    # Normalize auditor opinion
    # -----------------------------------------------------

    normalized_opinion = ""

    if opinion:
        if re.search(
            r"\bunmodified\b",
            opinion,
            flags=re.IGNORECASE,
        ):
            normalized_opinion = (
                "Unmodified"
            )

        elif re.search(
            r"\bunqualified\b",
            opinion,
            flags=re.IGNORECASE,
        ):
            normalized_opinion = (
                "Unqualified"
            )

        else:
            normalized_opinion = (
                opinion
                .split(",")[0]
                .strip()
            )

    # -----------------------------------------------------
    # Return structured extraction result
    # -----------------------------------------------------

    return {
        "document_type": (
            "SOC 2 Type II"
            if re.search(
                r"SOC\s*2\s*TYPE\s*II",
                text,
                flags=re.IGNORECASE,
            )
            else "SOC 2"
        ),

        "issuer": (
            issuer.replace(
                "(Fictional)",
                "",
            ).strip()
        ),

        "document_date": (
            normalize_date(
                report_date
            )
        ),

        "coverage_start": (
            normalize_date(
                period.group(1)
            )
            if period
            else ""
        ),

        "coverage_end": (
            normalize_date(
                period.group(2)
            )
            if period
            else ""
        ),

        "opinion": (
            normalized_opinion
        ),

        "exceptions_count": (
            len(exceptions)
        ),

        "exceptions": (
            exceptions
        ),

        "cuecs_summary": (
            cuec_section[:1800]
        ),

        "subservice_organizations_summary": (
            subservice_section[:1800]
        ),

        "confidence": (
            confidence_score
        ),

        "confidence_reasons": (
            confidence_reasons
        ),

        "confidence_gaps": (
            confidence_gaps
        ),

        "confidence_actions": (
            confidence_actions
        ),

        "extraction_method": (
            "Local parser"
        ),

        "review_notes": (
            "Fallback parser used. "
            "Analyst review is required "
            "before accepting metadata."
        ),
    }


# ---------------------------------------------------------
# Optional OpenAI extraction
# ---------------------------------------------------------

def ai_soc2_extraction(
    text: str,
    api_key: str,
    model: str = "gpt-5.6-luna",
) -> Dict[str, Any]:

    from openai import OpenAI

    client = OpenAI(
        api_key=api_key
    )

    prompt = f"""
You are a third-party security assurance analyst.

Extract structured metadata from the SOC 2 report text below.

Return ONLY valid JSON with these keys:

document_type,
issuer,
document_date,
coverage_start,
coverage_end,
opinion,
exceptions_count,
exceptions,
cuecs_summary,
subservice_organizations_summary,
confidence,
confidence_reasons,
confidence_gaps,
confidence_actions,
extraction_method,
review_notes.

Rules:

- Use ISO YYYY-MM-DD dates when the date is unambiguous.

- exceptions must be an array of objects containing:
  control_id,
  description,
  severity.

- confidence must be a number between 0 and 1.

- confidence represents confidence in extraction completeness,
  not the trustworthiness of the report or effectiveness
  of the vendor's controls.

- confidence_reasons must be an array of short statements
  explaining which expected SOC 2 elements were identified.

- confidence_gaps must be an array of short statements
  identifying expected SOC 2 metadata that could not
  be reliably identified.

- confidence_actions must be an array of objects containing:
  gap,
  action.

- Each confidence_actions entry should give the analyst
  a practical next step for validating or obtaining the
  missing metadata.

- Do not invent missing facts.

- Use empty strings or [] when information is unavailable.

- extraction_method must be "OpenAI".

- Flag ambiguity or potential issues in review_notes.

REPORT TEXT:

{text[:60000]}
"""

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    raw = (
        response
        .output_text
        .strip()
    )

    raw = re.sub(
        r"^```json\s*|\s*```$",
        "",
        raw,
        flags=re.IGNORECASE,
    )

    result = json.loads(
        raw
    )

    result[
        "extraction_method"
    ] = "OpenAI"

    return result


# ---------------------------------------------------------
# Main evidence extraction function
# ---------------------------------------------------------

def extract_soc2_metadata(
    file_bytes: bytes,
    api_key: str | None = None,
) -> Dict[str, Any]:

    text = extract_pdf_text(
        file_bytes
    )

    if not text.strip():
        raise ValueError(
            "No readable text was found in the PDF."
        )

    if api_key:
        try:
            return ai_soc2_extraction(
                text,
                api_key,
            )

        except Exception:
            fallback = (
                local_soc2_extraction(
                    text
                )
            )

            fallback[
                "review_notes"
            ] = (
                "AI extraction failed; "
                "local parser used instead. "
                "Analyst review is required "
                "before accepting metadata."
            )

            return fallback

    return local_soc2_extraction(
        text
    )