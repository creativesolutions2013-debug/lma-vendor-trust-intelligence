from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialChangeDecision:
    materiality: str
    decision_impact: str
    recommended_action: str
    affected_domain: str
    rationale: str
    confidence: str


_SEVERITY = {
    "low": 1,
    "moderate": 2,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _severity_rank(value: str | None) -> int:
    return _SEVERITY.get(
        _norm(value),
        0,
    )


def _context_score(
    *,
    tier_code: str,
    business_criticality: str | None,
    data_classification: str | None,
    production_access: bool,
    privileged_access: bool,
    ai_enabled: bool,
) -> int:
    score = 0

    if tier_code == "T1":
        score += 3
    elif tier_code == "T2":
        score += 2
    elif tier_code == "T3":
        score += 1

    if _norm(business_criticality) == "critical":
        score += 2
    elif _norm(business_criticality) == "high":
        score += 1

    data_value = _norm(data_classification)

    if data_value in {
        "restricted",
        "regulated",
        "confidential",
        "sensitive",
    }:
        score += 2

    if production_access:
        score += 1

    if privileged_access:
        score += 2

    if ai_enabled:
        score += 1

    return score


def evaluate_material_change(
    *,
    event_type: str,
    severity: str,
    tier_code: str,
    business_criticality: str | None = None,
    data_classification: str | None = None,
    production_access: bool = False,
    privileged_access: bool = False,
    ai_enabled: bool = False,
    has_current_approval: bool = False,
) -> MaterialChangeDecision:

    event = _norm(event_type)
    severity_rank = _severity_rank(severity)

    context_score = _context_score(
        tier_code=tier_code,
        business_criticality=business_criticality,
        data_classification=data_classification,
        production_access=production_access,
        privileged_access=privileged_access,
        ai_enabled=ai_enabled,
    )

    # -----------------------------------------------------
    # Evidence freshness changes
    # -----------------------------------------------------

    if event == "expired assurance evidence":
        if tier_code in {"T1", "T2"}:
            return MaterialChangeDecision(
                materiality="High",
                decision_impact=(
                    "Decision Review Required"
                    if has_current_approval
                    else "Monitor"
                ),
                recommended_action="Request Evidence",
                affected_domain="Assurance Evidence",
                rationale=(
                    "A high-tier vendor is relying on expired "
                    "assurance evidence. The smallest appropriate "
                    "response is to renew the missing evidence rather "
                    "than automatically launch a full reassessment."
                ),
                confidence="High",
            )

        return MaterialChangeDecision(
            materiality="Moderate",
            decision_impact="Monitor",
            recommended_action="Request Evidence",
            affected_domain="Assurance Evidence",
            rationale=(
                "Assurance evidence has expired, but the vendor's "
                "current context does not justify a broader reassessment."
            ),
            confidence="High",
        )

    # -----------------------------------------------------
    # Incident / breach
    # -----------------------------------------------------

    if event in {
        "breach disclosure",
        "ransomware event",
        "credential exposure",
        "critical kev exposure",
    }:
        if severity_rank >= 3 and context_score >= 4:
            return MaterialChangeDecision(
                materiality="Critical",
                decision_impact="Decision Challenged",
                recommended_action="Escalate",
                affected_domain="Security Incident",
                rationale=(
                    "A significant security event affects a vendor "
                    "with material business, data, or access exposure. "
                    "The existing decision should not be assumed valid "
                    "until the affected risk is reviewed."
                ),
                confidence="High",
            )

        if severity_rank >= 3:
            return MaterialChangeDecision(
                materiality="High",
                decision_impact="Decision Review Required",
                recommended_action="Targeted Review",
                affected_domain="Security Incident",
                rationale=(
                    "The event is significant, but the current vendor "
                    "context supports a targeted incident review rather "
                    "than a full reassessment."
                ),
                confidence="High",
            )

    # -----------------------------------------------------
    # Material service / architecture change
    # -----------------------------------------------------

    if event == "material vendor change":
        if ai_enabled:
            return MaterialChangeDecision(
                materiality="High",
                decision_impact=(
                    "Decision Challenged"
                    if has_current_approval
                    else "Decision Review Required"
                ),
                recommended_action="Targeted Review",
                affected_domain="AI / Service Change",
                rationale=(
                    "The vendor has a material service change involving "
                    "AI capability. Review should focus on AI data use, "
                    "model access, retention, subprocessors, governance, "
                    "and architecture rather than repeating the full "
                    "vendor assessment."
                ),
                confidence="High",
            )

        if context_score >= 4:
            return MaterialChangeDecision(
                materiality="High",
                decision_impact="Decision Review Required",
                recommended_action="Targeted Review",
                affected_domain="Service / Architecture",
                rationale=(
                    "The vendor's service or architecture changed in a "
                    "relationship with meaningful business, data, or "
                    "access exposure. Review only the affected domains."
                ),
                confidence="High",
            )

        return MaterialChangeDecision(
            materiality="Moderate",
            decision_impact="Monitor",
            recommended_action="Monitor",
            affected_domain="Service / Architecture",
            rationale=(
                "The change is notable but the current relationship "
                "context does not justify reassessment."
            ),
            confidence="Medium",
        )

    # -----------------------------------------------------
    # Security rating deterioration
    # -----------------------------------------------------

    if event == "security rating deterioration":
        if severity_rank >= 3 and context_score >= 4:
            return MaterialChangeDecision(
                materiality="High",
                decision_impact="Decision Review Required",
                recommended_action="Targeted Review",
                affected_domain="External Security Posture",
                rationale=(
                    "The vendor's external posture deteriorated and the "
                    "relationship has meaningful exposure. Validate the "
                    "specific changed controls before expanding scope."
                ),
                confidence="Medium",
            )

        return MaterialChangeDecision(
            materiality="Moderate",
            decision_impact="Monitor",
            recommended_action="Monitor",
            affected_domain="External Security Posture",
            rationale=(
                "The external signal changed, but it does not yet "
                "justify analyst-intensive reassessment."
            ),
            confidence="Medium",
        )

    # -----------------------------------------------------
    # Default
    # -----------------------------------------------------

    if severity_rank <= 1:
        return MaterialChangeDecision(
            materiality="Low",
            decision_impact="No Impact",
            recommended_action="No Action",
            affected_domain="General",
            rationale=(
                "The event is low severity and does not materially "
                "change the current third-party risk decision."
            ),
            confidence="Medium",
        )

    return MaterialChangeDecision(
        materiality="Moderate",
        decision_impact="Monitor",
        recommended_action="Monitor",
        affected_domain="General",
        rationale=(
            "The event warrants monitoring but does not currently "
            "justify additional analyst workflow."
        ),
        confidence="Medium",
    )
