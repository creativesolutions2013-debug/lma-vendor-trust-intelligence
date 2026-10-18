"""Conservative document-to-requirement screening for the LMA pilot.

This is a deterministic, read-only preview, not verified assurance or a
replacement for an analyst-approved control disposition.
"""
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from src.evidence_ai import local_soc2_extraction

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_DOCUMENT_PAGES = 300


@dataclass(frozen=True)
class EvidenceSegment:
    location: str
    text: str


@dataclass(frozen=True)
class EvidenceDocument:
    filename: str
    segments: tuple[EvidenceSegment, ...]


@dataclass(frozen=True)
class EvidenceCitation:
    filename: str
    location: str
    excerpt: str


@dataclass(frozen=True)
class RequirementEvaluation:
    requirement_id: str
    requirement: str
    outcome: str
    reason: str
    follow_up: str
    citations: tuple[EvidenceCitation, ...] = ()


def read_evidence_document(filename: str, content: bytes) -> EvidenceDocument:
    """Read PDF, DOCX, or text into separately citable source locations."""
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("Evidence file is empty or exceeds the 15 MB pilot limit.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(content))
            if len(reader.pages) > MAX_DOCUMENT_PAGES:
                raise ValueError("PDF exceeds the 300-page pilot limit.")
            segments = tuple(
                EvidenceSegment(f"Page {i}", page.extract_text() or "")
                for i, page in enumerate(reader.pages, 1)
            )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Unable to read PDF text; check the file.") from exc
    elif suffix == ".docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paras = [
                "".join(t.text or "" for t in p.iter(f"{ns}t"))
                for p in root.iter(f"{ns}p")
            ]
            segments = tuple(
                EvidenceSegment(f"Paragraph {i}", p)
                for i, p in enumerate(paras, 1) if p.strip()
            )
        except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise ValueError("Unable to read DOCX document text.") from exc
    elif suffix == ".txt":
        segments = tuple(
            EvidenceSegment(f"Line {i}", line)
            for i, line in enumerate(content.decode("utf-8-sig", errors="replace").splitlines(), 1)
            if line.strip()
        )
    else:
        raise ValueError("Pilot analysis supports PDF, DOCX and TXT evidence only.")
    if not any(part.text.strip() for part in segments):
        raise ValueError("No readable text found; scanned evidence needs human review/OCR.")
    return EvidenceDocument(filename=Path(filename).name, segments=segments)


def _lines(documents):
    for doc in documents:
        for part in doc.segments:
            for line in part.text.splitlines():
                line = line.strip()
                if line:
                    yield doc, part.location, line


def _citation(doc, location, line):
    return EvidenceCitation(doc.filename, location, line[:280])


def _tls(documents):
    evidence = [
        (doc, location, line)
        for doc, location, line in _lines(documents)
        if re.search(r"\bTLS\s*(?:v\s*)?1\.[0-3]\b", line, re.I)
    ]
    requirement = "Production endpoints must use TLS 1.2 or newer."
    if not evidence:
        return RequirementEvaluation("ENC-01", requirement, "Evidence Missing",
            "No readable statement identified the TLS versions used by the assessed service.",
            "Request production TLS configuration or a verified endpoint scan.")
    legacy = []
    ambiguous = []
    for row in evidence:
        line = row[2]
        if not re.search(r"\bTLS\s*(?:v\s*)?1\.[01]\b", line, re.I):
            continue
        negated = re.search(r"\b(disabled|blocked|prohibited|deprecated|rejected|removed|disallowed|not supported|not enabled)\b", line, re.I)
        positive = re.search(r"\b(supported|enabled|allowed|accepted|permitted|used|configured)\b", line, re.I)
        if positive and not negated:
            legacy.append(row)
        else:
            ambiguous.append(row)
    if legacy:
        row = legacy[0]
        return RequirementEvaluation("ENC-01", requirement, "Risk Identified",
            "A source affirmatively describes support/use of TLS 1.0 or 1.1, below the minimum. Confirm the exposed production endpoints and whether the statement is current.",
            "Request a current production TLS scan and remediation or exception details.",
            (_citation(*row),))
    row = (ambiguous or evidence)[0]
    return RequirementEvaluation("ENC-01", requirement, "Needs Review",
        "The source mentions TLS versions, but text alone does not establish that production endpoints enforce the required minimum.",
        "Confirm actual production configuration with a current endpoint scan.",
        (_citation(*row),))


def _soc(documents, today):
    soc_documents = [
        doc for doc in documents
        if re.search(r"\bSOC\s*2\s*Type\s*II\b", "\n".join(p.text for p in doc.segments), re.I)
    ]
    requirement = "Provide an in-scope SOC 2 Type II report with a coverage period ending within the past 365 days."
    if not soc_documents:
        return RequirementEvaluation("SOC2-FRESHNESS", requirement, "Evidence Missing",
            "No readable SOC 2 Type II report was identified.",
            "Provide the relevant report or approved alternative assurance.")
    doc = soc_documents[0]
    extracted = local_soc2_extraction("\n".join(p.text for p in doc.segments))
    end_value = extracted.get("coverage_end") or ""
    period_parts = [
        part for part in doc.segments
        if re.search(r"examination period|period under examination", part.text, re.I)
    ]
    location = (period_parts or doc.segments)[0]
    excerpt = " ".join(location.text.split())[:280]
    citation = EvidenceCitation(doc.filename, location.location, excerpt)
    try:
        coverage_end = date.fromisoformat(end_value)
    except ValueError:
        coverage_end = None
    if coverage_end is None:
        return RequirementEvaluation("SOC2-FRESHNESS", requirement, "Needs Review",
            "A SOC 2 Type II report was identified but its coverage-end date could not be reliably extracted.",
            "Verify the auditor's report period and relevant service scope.", (citation,))
    age = (today - coverage_end).days
    if age > 365:
        return RequirementEvaluation("SOC2-FRESHNESS", requirement, "Needs Review",
            f"SOC 2 coverage ended {coverage_end.isoformat()} ({age} days ago), outside the 365-day pilot threshold; this is stale assurance, not proof of a control failure.",
            "Request the current SOC 2 Type II report and review coverage or a suitable interim assurance.", (citation,))
    if age < 0:
        return RequirementEvaluation("SOC2-FRESHNESS", requirement, "Needs Review",
            "The extracted coverage period ends in the future; verify the date before relying on this report.",
            "Confirm the report period and document authenticity.", (citation,))
    return RequirementEvaluation("SOC2-FRESHNESS", requirement, "Needs Review",
        f"The SOC 2 coverage period ended {coverage_end.isoformat()} and is within 365 days; audit opinion, exceptions, service scope and currency still require analyst validation.",
        "Confirm service scope, auditor opinion, exceptions and applicable bridge evidence.", (citation,))


def _pentest(documents, privileged_access):
    matched = [
        doc for doc in documents
        if re.search(r"penetration\s+test|pentest", doc.filename + "\n" + "\n".join(s.text for s in doc.segments), re.I)
    ]
    requirement = "Review the penetration test and assess findings for the vendor's service and access context."
    if not matched:
        return RequirementEvaluation("VM-01", requirement, "Evidence Missing",
            "No readable penetration-test report was identified.",
            "Request the latest in-scope penetration-test summary or report.")
    findings = [
        (doc, location, line)
        for doc, location, line in _lines(matched)
        if re.search(r"\b(low severity|severity\s*[:=]\s*low|risk\s*[:=]\s*low|low risk)\b", line, re.I)
        and re.search(r"session|privileg|admin|authentication|access", line, re.I)
    ]
    if findings:
        row = findings[0]
        reason = (
            "A finding marked Low concerns access/session security. Because the vendor has privileged production access, its business impact needs heightened analyst review; the tester's original severity remains Low."
            if privileged_access else
            "A Low-rated access/session finding was found. The testing firm's rating alone is not sufficient to determine its importance for this service."
        )
        return RequirementEvaluation("VM-01", requirement, "Needs Review", reason,
            "Review affected components, exploitability, service scope and remediation evidence.",
            (_citation(*row),))
    return RequirementEvaluation("VM-01", requirement, "Needs Review",
        "A penetration-test document was found; findings, timing, scope and remediation have not been independently validated.",
        "Review the report scope, test date, findings and remediation status.",
        (EvidenceCitation(matched[0].filename, matched[0].segments[0].location,
                          " ".join(matched[0].segments[0].text.split())[:280]),))


def evaluate_pilot_requirements(documents, *, privileged_access=False, today=None):
    documents = tuple(documents)
    today = today or date.today()
    return (
        _tls(documents),
        _soc(documents, today),
        _pentest(documents, privileged_access),
    )
