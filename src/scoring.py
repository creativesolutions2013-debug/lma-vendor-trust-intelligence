from dataclasses import dataclass

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

def calculate_residual_risk(
    inherent_risk: float,
    control_effectiveness: float,
    external_risk: float
) -> float:
    control_deficiency = 100 - max(0, min(100, control_effectiveness))
    residual = (
        inherent_risk * 0.40
        + control_deficiency * 0.35
        + external_risk * 0.25
    )
    return round(max(0, min(100, residual)), 1)

def rating_from_score(score: float) -> str:
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Moderate"
    return "Low"
