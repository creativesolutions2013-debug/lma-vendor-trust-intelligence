from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class AttentionReason:
    reason: str
    points: int
    category: str = "risk"


@dataclass(frozen=True)
class VendorAttention:
    score: int
    priority: str
    reasons: tuple[AttentionReason, ...]


_TIER_BONUS = {
    "T1": 15,
    "T2": 10,
    "T3": 5,
    "T4": 0,
}

_EVIDENCE_WEIGHTS = {
    "SOC 2 Type II or equivalent assurance report": 8,
    "Penetration Test": 12,
    "BCP / DR Test": 10,
    "Incident Response Plan": 8,
    "Security Policy": 5,
    "Architecture Diagram": 4,
    "AI governance / acceptable use documentation": 7,
    "AI architecture or data-flow documentation": 7,
    "Applicable regulatory assurance evidence": 8,
}

_FINDING_WEIGHTS = {
    "critical": 20,
    "high": 12,
    "moderate": 6,
    "medium": 6,
    "low": 2,
}

_EVENT_WEIGHTS = {
    "critical": 15,
    "high": 10,
    "moderate": 5,
    "medium": 5,
    "low": 2,
}

# Used only to rank what the analyst sees first.
# It does NOT change the attention score itself.
_REASON_CATEGORY_PRIORITY = {
    "finding": 4,
    "monitoring": 3,
    "evidence": 2,
    "residual": 1,
    "tier": 0,
}


def priority_from_score(score: int) -> str:
    if score >= 75:
        return "P1"
    if score >= 50:
        return "P2"
    if score >= 25:
        return "P3"
    return "P4"


def _evidence_gap_points(coverage) -> tuple[int, list[AttentionReason]]:
    points = 0
    reasons = []

    for item in coverage.items:
        if not item.required:
            continue

        if item.status not in {"Missing", "Expired", "Expiring Soon"}:
            continue

        base = _EVIDENCE_WEIGHTS.get(item.requirement, 4)

        if item.status == "Expiring Soon":
            contribution = max(2, round(base * 0.5))
        else:
            contribution = base

        points += contribution
        reasons.append(
            AttentionReason(
                reason=f"{item.requirement}: {item.status}",
                points=contribution,
                category="evidence",
            )
        )

    return min(points, 25), reasons


def _finding_points(findings: Iterable) -> tuple[int, list[AttentionReason]]:
    points = 0
    reasons = []

    for finding in findings:
        status = (getattr(finding, "status", "") or "").strip().lower()
        if status == "closed":
            continue

        severity = (getattr(finding, "severity", "") or "").strip().lower()
        contribution = _FINDING_WEIGHTS.get(severity, 4)

        points += contribution
        reasons.append(
            AttentionReason(
                reason=(
                    f"Open {severity or 'unrated'} finding: "
                    f"{getattr(finding, 'title', 'Finding')}"
                ),
                points=contribution,
                category="finding",
            )
        )

    return min(points, 25), reasons


def _event_points(events: Iterable) -> tuple[int, list[AttentionReason]]:
    points = 0
    reasons = []

    for event in events:
        status = (getattr(event, "status", "") or "").strip().lower()
        if status == "closed":
            continue

        if not bool(getattr(event, "requires_review", True)):
            continue

        severity = (getattr(event, "severity", "") or "").strip().lower()
        contribution = _EVENT_WEIGHTS.get(severity, 4)

        points += contribution
        reasons.append(
            AttentionReason(
                reason=(
                    f"Monitoring event: "
                    f"{getattr(event, 'event_type', 'Review required')}"
                ),
                points=contribution,
                category="monitoring",
            )
        )

    return min(points, 15), reasons


def calculate_vendor_attention(
    *,
    tier_code: str,
    residual_risk: float,
    evidence_coverage,
    findings: Sequence = (),
    monitoring_events: Sequence = (),
) -> VendorAttention:
    residual_points = round(max(0.0, min(100.0, float(residual_risk))) * 0.35)
    tier_points = _TIER_BONUS.get(tier_code, 0)

    evidence_points, evidence_reasons = _evidence_gap_points(evidence_coverage)
    finding_points, finding_reasons = _finding_points(findings)
    event_points, event_reasons = _event_points(monitoring_events)

    reasons = []

    if residual_points:
        reasons.append(
            AttentionReason(
                reason=f"Residual risk {round(float(residual_risk), 1)}",
                points=residual_points,
                category="residual",
            )
        )

    if tier_points:
        reasons.append(
            AttentionReason(
                reason=f"{tier_code} assurance criticality",
                points=tier_points,
                category="tier",
            )
        )

    reasons.extend(evidence_reasons)
    reasons.extend(finding_reasons)
    reasons.extend(event_reasons)

    total = min(
        100,
        residual_points
        + tier_points
        + evidence_points
        + finding_points
        + event_points,
    )

    # Rank what the analyst sees first by actionability, then contribution.
    # Findings > monitoring events > evidence gaps > residual risk > tier.
    ranked_reasons = tuple(
        sorted(
            reasons,
            key=lambda item: (
                _REASON_CATEGORY_PRIORITY.get(item.category, 0),
                item.points,
            ),
            reverse=True,
        )
    )

    return VendorAttention(
        score=total,
        priority=priority_from_score(total),
        reasons=ranked_reasons,
    )
