from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional, Sequence


@dataclass(frozen=True)
class EvidenceRequirementResult:
    requirement: str
    required: bool
    status: str
    evidence_id: Optional[int] = None
    document_type: Optional[str] = None
    document_name: Optional[str] = None
    expiration_date: Optional[str] = None


@dataclass(frozen=True)
class EvidenceCoverage:
    total_required: int
    satisfied_required: int
    completion_percent: int
    items: tuple[EvidenceRequirementResult, ...]


_REQUIREMENT_ALIASES = {
    "SOC 2 Type II or equivalent assurance report": (
        "SOC 2 Type II",
        "ISO 27001 Certificate",
    ),
    "Penetration Test": ("Penetration Test",),
    "BCP / DR Test": ("BCP / DR Test",),
    "Incident Response Plan": ("Incident Response Plan",),
    "Security Policy": ("Security Policy",),
    "Architecture Diagram": ("Architecture Diagram",),
    "Security questionnaire or equivalent": (
        "SIG Questionnaire",
        "CAIQ",
    ),
    "SOC 2 / ISO 27001 if available": (
        "SOC 2 Type II",
        "SOC 2 Type I",
        "ISO 27001 Certificate",
        "ISO 27001 Statement of Applicability",
    ),
    "Applicable regulatory assurance evidence": (
        "PCI AOC",
        "SOC 2 Type II",
        "ISO 27001 Certificate",
    ),
}


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def _is_optional(requirement: str) -> bool:
    lowered = requirement.lower()
    return "if available" in lowered or lowered.startswith("optional:")


def _document_matches(requirement: str, evidence) -> bool:
    allowed_types = _REQUIREMENT_ALIASES.get(requirement)

    if allowed_types:
        return (getattr(evidence, "document_type", "") or "") in allowed_types

    # For prototype-only requirements that do not yet have a dedicated
    # document type, allow a descriptive document name to satisfy them.
    haystack = " ".join(
        [
            getattr(evidence, "document_type", "") or "",
            getattr(evidence, "document_name", "") or "",
        ]
    ).lower()

    keywords = [
        word
        for word in requirement.lower().replace("/", " ").replace("-", " ").split()
        if len(word) >= 4
        and word
        not in {
            "documentation",
            "document",
            "evidence",
            "applicable",
            "assurance",
            "security",
        }
    ]

    return bool(keywords) and all(word in haystack for word in keywords[:3])


def _status_for_evidence(evidence, today: date) -> str:
    expiration = _parse_date(getattr(evidence, "expiration_date", None))

    if expiration:
        days_remaining = (expiration - today).days
        if days_remaining < 0:
            return "Expired"
        if days_remaining <= 60:
            return "Expiring Soon"

    status = (getattr(evidence, "status", "") or "").strip().lower()
    if status == "expired":
        return "Expired"
    if status == "expiring soon":
        return "Expiring Soon"

    return "Satisfied"


def evaluate_evidence_coverage(
    required_evidence: Sequence[str],
    evidence_records: Iterable,
    *,
    today: Optional[date] = None,
) -> EvidenceCoverage:
    today = today or date.today()
    evidence_records = list(evidence_records)

    results = []

    for requirement in required_evidence:
        optional = _is_optional(requirement)
        matches = [
            evidence
            for evidence in evidence_records
            if _document_matches(requirement, evidence)
        ]

        if not matches:
            results.append(
                EvidenceRequirementResult(
                    requirement=requirement,
                    required=not optional,
                    status="Missing",
                )
            )
            continue

        ranked = sorted(
            matches,
            key=lambda item: {
                "Satisfied": 3,
                "Expiring Soon": 2,
                "Expired": 1,
            }[_status_for_evidence(item, today)],
            reverse=True,
        )

        best = ranked[0]
        status = _status_for_evidence(best, today)

        results.append(
            EvidenceRequirementResult(
                requirement=requirement,
                required=not optional,
                status=status,
                evidence_id=getattr(best, "id", None),
                document_type=getattr(best, "document_type", None),
                document_name=getattr(best, "document_name", None),
                expiration_date=getattr(best, "expiration_date", None),
            )
        )

    required_items = [item for item in results if item.required]
    satisfied_items = [
        item
        for item in required_items
        if item.status in {"Satisfied", "Expiring Soon"}
    ]

    total_required = len(required_items)
    satisfied_required = len(satisfied_items)

    completion_percent = (
        round((satisfied_required / total_required) * 100)
        if total_required
        else 100
    )

    return EvidenceCoverage(
        total_required=total_required,
        satisfied_required=satisfied_required,
        completion_percent=completion_percent,
        items=tuple(results),
    )
