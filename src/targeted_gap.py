from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Sequence

from src.assurance import evaluate_evidence_coverage


@dataclass(frozen=True)
class TargetedEvidenceGap:
    requirement: str
    evidence_state: str
    workflow_action: str
    reason: str
    evidence_id: Optional[int] = None
    document_type: Optional[str] = None
    document_name: Optional[str] = None
    expiration_date: Optional[str] = None


@dataclass(frozen=True)
class TargetedGapAnalysis:
    total_requirements: int
    reusable: int
    analyst_validation: int
    vendor_requests: int
    items: tuple[TargetedEvidenceGap, ...]


def _normalize_requirement(requirement: str) -> str:
    """Translate targeted-scope wording into assurance requirements."""
    value = (requirement or "").strip()

    aliases = {
        "Current SOC 2 Type II or equivalent assurance report":
            "SOC 2 Type II or equivalent assurance report",
        "Current Security Policy":
            "Security Policy",
        "Latest penetration test status or report":
            "Penetration Test",
        "Current Incident Response Plan":
            "Incident Response Plan",
        "Updated architecture diagram":
            "Architecture Diagram",
    }

    return aliases.get(value, value)


def _has_detected_exception(evidence) -> bool:
    if (
        getattr(evidence, "exceptions_count", 0)
        or 0
    ) > 0:
        return True

    detected = (
        getattr(
            evidence,
            "detected_exceptions",
            None,
        )
        or ""
    ).strip()

    return bool(detected)


def _needs_confidence_review(evidence) -> bool:
    confidence = getattr(
        evidence,
        "extraction_confidence",
        None,
    )

    return (
        confidence is not None
        and confidence < 0.65
    )


def analyze_targeted_evidence_gaps(
    required_evidence: Sequence[str],
    evidence_records: Iterable,
    *,
    today: Optional[date] = None,
) -> TargetedGapAnalysis:

    evidence_records = list(evidence_records)

    normalized_requirements = [
        _normalize_requirement(requirement)
        for requirement in required_evidence
    ]

    coverage = evaluate_evidence_coverage(
        normalized_requirements,
        evidence_records,
        today=today,
    )

    original_by_normalized = {
        _normalize_requirement(requirement): requirement
        for requirement in required_evidence
    }

    evidence_by_id = {
        getattr(record, "id", None): record
        for record in evidence_records
        if getattr(record, "id", None)
        is not None
    }

    results = []

    for item in coverage.items:
        display_requirement = original_by_normalized.get(
            item.requirement,
            item.requirement,
        )

        # -------------------------------------------------
        # Nothing matched the requirement.
        # -------------------------------------------------

        if item.status == "Missing":
            results.append(
                TargetedEvidenceGap(
                    requirement=display_requirement,
                    evidence_state="Missing",
                    workflow_action="Request Vendor",
                    reason=(
                        "No evidence currently on file "
                        "matches this approved review "
                        "requirement."
                    ),
                )
            )
            continue

        evidence = evidence_by_id.get(
            item.evidence_id
        )

        # -------------------------------------------------
        # A matching artifact exists but is stale.
        # -------------------------------------------------

        if item.status == "Expired":
            results.append(
                TargetedEvidenceGap(
                    requirement=display_requirement,
                    evidence_state="Expired",
                    workflow_action="Request Vendor",
                    reason=(
                        "Matching evidence exists but "
                        "has expired and should not be "
                        "relied on for the current review."
                    ),
                    evidence_id=item.evidence_id,
                    document_type=item.document_type,
                    document_name=item.document_name,
                    expiration_date=item.expiration_date,
                )
            )
            continue

        # -------------------------------------------------
        # Evidence is approaching expiration.
        # Do not automatically bother the vendor yet.
        # -------------------------------------------------

        if item.status == "Expiring Soon":
            results.append(
                TargetedEvidenceGap(
                    requirement=display_requirement,
                    evidence_state="Expiring Soon",
                    workflow_action="Analyst Validate",
                    reason=(
                        "Evidence is still current but "
                        "approaching expiration. Validate "
                        "whether it remains sufficient "
                        "for this targeted decision."
                    ),
                    evidence_id=item.evidence_id,
                    document_type=item.document_type,
                    document_name=item.document_name,
                    expiration_date=item.expiration_date,
                )
            )
            continue

        # -------------------------------------------------
        # Current evidence with known exceptions should
        # not be automatically reused.
        # -------------------------------------------------

        if (
            evidence is not None
            and _has_detected_exception(
                evidence
            )
        ):
            results.append(
                TargetedEvidenceGap(
                    requirement=display_requirement,
                    evidence_state=(
                        "Current with Exceptions"
                    ),
                    workflow_action=(
                        "Analyst Validate"
                    ),
                    reason=(
                        "Current evidence matches the "
                        "requirement, but documented "
                        "exceptions require analyst "
                        "review before reuse."
                    ),
                    evidence_id=item.evidence_id,
                    document_type=item.document_type,
                    document_name=item.document_name,
                    expiration_date=item.expiration_date,
                )
            )
            continue

        # -------------------------------------------------
        # Low extraction confidence means the document
        # should not be treated as automatically reliable.
        # -------------------------------------------------

        if (
            evidence is not None
            and _needs_confidence_review(
                evidence
            )
        ):
            results.append(
                TargetedEvidenceGap(
                    requirement=display_requirement,
                    evidence_state=(
                        "Current / Low Confidence"
                    ),
                    workflow_action=(
                        "Analyst Validate"
                    ),
                    reason=(
                        "Evidence is current, but the "
                        "extracted metadata has low "
                        "confidence and should be "
                        "validated before reuse."
                    ),
                    evidence_id=item.evidence_id,
                    document_type=item.document_type,
                    document_name=item.document_name,
                    expiration_date=item.expiration_date,
                )
            )
            continue

        # -------------------------------------------------
        # Current, matched, no material validation flag.
        # -------------------------------------------------

        results.append(
            TargetedEvidenceGap(
                requirement=display_requirement,
                evidence_state="Current",
                workflow_action="Reuse",
                reason=(
                    "Current evidence on file matches "
                    "the approved targeted-review "
                    "requirement and has no identified "
                    "reuse blocker."
                ),
                evidence_id=item.evidence_id,
                document_type=item.document_type,
                document_name=item.document_name,
                expiration_date=item.expiration_date,
            )
        )

    reusable = sum(
        1
        for item in results
        if item.workflow_action == "Reuse"
    )

    analyst_validation = sum(
        1
        for item in results
        if item.workflow_action
        == "Analyst Validate"
    )

    vendor_requests = sum(
        1
        for item in results
        if item.workflow_action
        == "Request Vendor"
    )

    return TargetedGapAnalysis(
        total_requirements=len(results),
        reusable=reusable,
        analyst_validation=analyst_validation,
        vendor_requests=vendor_requests,
        items=tuple(results),
    )
