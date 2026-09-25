from dataclasses import dataclass


@dataclass(frozen=True)
class ReassessmentDecision:
    triggered: bool
    assessment_type: str | None
    assessment_reason: str | None
    priority: str | None
    rationale: str


_SEVERITY_RANK = {
    "low": 1,
    "moderate": 2,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _severity_at_least(severity: str, minimum: str) -> bool:
    return _SEVERITY_RANK.get((severity or "").strip().lower(), 0) >= _SEVERITY_RANK[minimum]


def evaluate_reassessment_trigger(
    *,
    event_type: str,
    severity: str,
    tier_code: str,
) -> ReassessmentDecision:
    event = (event_type or "").strip()
    severity_value = (severity or "").strip()

    if event in {
        "Breach disclosure",
        "Ransomware event",
        "Credential exposure",
        "Critical KEV exposure",
    }:
        if _severity_at_least(severity_value, "high"):
            return ReassessmentDecision(
                triggered=True,
                assessment_type="Incident-Triggered Reassessment",
                assessment_reason=event,
                priority="P1" if severity_value.lower() == "critical" else "P2",
                rationale=(
                    f"{event} at {severity_value} severity materially changes "
                    "the vendor's current security risk."
                ),
            )

    if event == "Material vendor change":
        if _severity_at_least(severity_value, "moderate"):
            return ReassessmentDecision(
                triggered=True,
                assessment_type="Material Change Reassessment",
                assessment_reason=event,
                priority="P2" if _severity_at_least(severity_value, "high") else "P3",
                rationale=(
                    "A material service, architecture, ownership, data-use, "
                    "or delivery change requires the prior assurance decision "
                    "to be reconsidered."
                ),
            )

    if event == "Expired assurance evidence":
        if tier_code in {"T1", "T2"}:
            return ReassessmentDecision(
                triggered=True,
                assessment_type="Evidence-Triggered Reassessment",
                assessment_reason=event,
                priority="P2" if tier_code == "T1" else "P3",
                rationale=(
                    f"{tier_code} vendor assurance depends on current evidence; "
                    "critical evidence expiration requires renewed validation."
                ),
            )

    if event == "Security rating deterioration":
        if _severity_at_least(severity_value, "high"):
            return ReassessmentDecision(
                triggered=True,
                assessment_type="Risk-Triggered Reassessment",
                assessment_reason=event,
                priority="P2" if tier_code in {"T1", "T2"} else "P3",
                rationale=(
                    "A significant deterioration in external security posture "
                    "requires targeted reassessment of the changed risk."
                ),
            )

    return ReassessmentDecision(
        triggered=False,
        assessment_type=None,
        assessment_reason=None,
        priority=None,
        rationale="The event does not meet the configured reassessment threshold.",
    )
