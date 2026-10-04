from dataclasses import dataclass, field
from typing import List


RESIDUAL_RISK_POLICY_VERSION = "RR-2.0"


@dataclass
class InherentRiskInput:
    data_sensitivity: int
    system_access: int
    business_criticality: int
    data_volume: int
    regulatory_exposure: int
    fourth_party_dependency: int
    geographic_risk: int
    ai_autonomy: int


@dataclass
class ResidualRiskContext:
    """
    Context used to apply policy guardrails after the numeric
    residual-risk score is calculated.
    """

    active_critical_incident: bool = False
    unresolved_critical_finding: bool = False
    privileged_access_without_mfa: bool = False
    required_evidence_expired: bool = False
    assessment_complete: bool = True
    risk_acceptance_expired: bool = False


@dataclass
class ResidualRiskDecision:
    score: float
    calculated_rating: str
    final_rating: str
    external_adjustment: int

    triggered_guardrails: List[str] = field(default_factory=list)

    escalation_required: bool = False
    approval_blocked: bool = False

    policy_version: str = RESIDUAL_RISK_POLICY_VERSION


def calculate_inherent_risk(inp: InherentRiskInput) -> int:
    score = (
        inp.data_sensitivity
        + inp.system_access
        + inp.business_criticality
        + inp.data_volume
        + inp.regulatory_exposure
        + inp.fourth_party_dependency
        + inp.geographic_risk
        + inp.ai_autonomy
    )

    return max(0, min(100, int(score)))


def tier_from_score(score: int) -> str:
    if score >= 75:
        return "Tier 1 — Critical"

    if score >= 50:
        return "Tier 2 — High"

    if score >= 25:
        return "Tier 3 — Moderate"

    return "Tier 4 — Low"


def external_risk_adjustment(external_risk: float) -> int:
    """
    Convert a 0-100 external-risk signal into a bounded adjustment.

    External risk acts as a modifier rather than a third independent
    weighted component.

    0-19   = -5
    20-49  = 0
    50-64  = +5
    65-79  = +10
    80-100 = +20
    """

    score = max(0, min(100, external_risk))

    if score >= 80:
        return 20

    if score >= 65:
        return 10

    if score >= 50:
        return 5

    if score >= 20:
        return 0

    return -5


def calculate_residual_risk(
    inherent_risk: float,
    control_effectiveness: float,
    external_risk: float,
) -> float:
    """
    Residual Risk Model RR-2.0

    Base Residual Risk =
        (Inherent Risk × 0.60)
        +
        (Control Deficiency × 0.40)

    Control Deficiency =
        100 - Control Effectiveness

    Final Numeric Risk =
        Base Residual Risk
        +
        External Risk Adjustment

    Guardrails are applied separately so the mathematical score
    remains transparent.
    """

    inherent = max(0, min(100, inherent_risk))

    effectiveness = max(
        0,
        min(100, control_effectiveness),
    )

    control_deficiency = 100 - effectiveness

    base_residual = (
        inherent * 0.60
        + control_deficiency * 0.40
    )

    residual = (
        base_residual
        + external_risk_adjustment(external_risk)
    )

    return round(
        max(0, min(100, residual)),
        1,
    )


def rating_from_score(score: float) -> str:
    if score >= 75:
        return "Critical"

    if score >= 50:
        return "High"

    if score >= 25:
        return "Moderate"

    return "Low"


def _rating_rank(rating: str) -> int:
    return {
        "Low": 0,
        "Moderate": 1,
        "High": 2,
        "Critical": 3,
    }[rating]


def _max_rating(
    current: str,
    minimum: str,
) -> str:
    if _rating_rank(minimum) > _rating_rank(current):
        return minimum

    return current


def evaluate_residual_risk(
    inherent_risk: float,
    control_effectiveness: float,
    external_risk: float,
    context: ResidualRiskContext | None = None,
) -> ResidualRiskDecision:
    """
    Calculate residual risk and apply policy guardrails.

    Important:
    The calculated numeric score is preserved.

    Guardrails may raise the final rating or block approval
    without manipulating the underlying calculated score.
    """

    context = context or ResidualRiskContext()

    score = calculate_residual_risk(
        inherent_risk,
        control_effectiveness,
        external_risk,
    )

    calculated_rating = rating_from_score(score)
    final_rating = calculated_rating

    guardrails: List[str] = []

    escalation_required = False
    approval_blocked = False

    # Hard Stop:
    # Active critical security incident
    if context.active_critical_incident:
        final_rating = "Critical"

        escalation_required = True
        approval_blocked = True

        guardrails.append(
            "ACTIVE_CRITICAL_SECURITY_INCIDENT"
        )

    # Minimum High:
    # Critical finding remains unresolved
    if context.unresolved_critical_finding:
        final_rating = _max_rating(
            final_rating,
            "High",
        )

        escalation_required = True
        approval_blocked = True

        guardrails.append(
            "UNRESOLVED_CRITICAL_FINDING"
        )

    # Minimum High:
    # Privileged access without MFA
    if context.privileged_access_without_mfa:
        final_rating = _max_rating(
            final_rating,
            "High",
        )

        escalation_required = True
        approval_blocked = True

        guardrails.append(
            "PRIVILEGED_ACCESS_WITHOUT_MFA"
        )

    # Approval Block:
    # Required evidence is no longer current
    if context.required_evidence_expired:
        approval_blocked = True

        guardrails.append(
            "REQUIRED_EVIDENCE_EXPIRED"
        )

    # Approval Block:
    # Assessment not complete
    if not context.assessment_complete:
        approval_blocked = True

        guardrails.append(
            "ASSESSMENT_INCOMPLETE"
        )

    # Escalation:
    # Previously accepted risk has expired
    if context.risk_acceptance_expired:
        approval_blocked = True
        escalation_required = True

        guardrails.append(
            "RISK_ACCEPTANCE_EXPIRED"
        )

    return ResidualRiskDecision(
        score=score,
        calculated_rating=calculated_rating,
        final_rating=final_rating,
        external_adjustment=external_risk_adjustment(
            external_risk
        ),
        triggered_guardrails=guardrails,
        escalation_required=escalation_required,
        approval_blocked=approval_blocked,
    )