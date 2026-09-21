from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class TierProfile:
    tier: str
    name: str
    assessment_type: str
    required_controls: Tuple[str, ...]
    required_evidence: Tuple[str, ...]
    monitoring_rules: Tuple[str, ...]
    reassessment_rules: Tuple[str, ...]


_BASE_PROFILES = {
    "T1": TierProfile(
        tier="T1",
        name="Critical",
        assessment_type="Full Security Assessment",
        required_controls=(
            "Security governance and ownership",
            "Identity and access management",
            "Privileged access management",
            "Encryption and key management",
            "Vulnerability and patch management",
            "Secure software development",
            "Logging, monitoring, and incident response",
            "Business continuity and disaster recovery",
            "Third- and fourth-party risk management",
            "Data protection and retention",
        ),
        required_evidence=(
            "SOC 2 Type II or equivalent assurance report",
            "Penetration Test",
            "BCP / DR Test",
            "Incident Response Plan",
            "Security Policy",
            "Architecture Diagram",
        ),
        monitoring_rules=(
            "Continuous external security monitoring",
            "Evidence freshness monitoring",
            "Open critical/high finding monitoring",
            "Material change monitoring",
        ),
        reassessment_rules=(
            "At least annually",
            "Security incident or breach",
            "Material service or architecture change",
            "Critical evidence expiration",
            "Significant security rating deterioration",
        ),
    ),
    "T2": TierProfile(
        tier="T2",
        name="High",
        assessment_type="Enhanced Security Assessment",
        required_controls=(
            "Security governance and ownership",
            "Identity and access management",
            "Encryption and data protection",
            "Vulnerability management",
            "Incident response",
            "Business continuity",
            "Logging and monitoring",
        ),
        required_evidence=(
            "SOC 2 Type II or equivalent assurance report",
            "Penetration Test",
            "Incident Response Plan",
            "Security Policy",
        ),
        monitoring_rules=(
            "Continuous external security monitoring",
            "Evidence freshness monitoring",
            "Open high finding monitoring",
        ),
        reassessment_rules=(
            "Risk-based periodic review",
            "Security incident or breach",
            "Material service change",
            "Evidence expiration",
            "Significant security rating deterioration",
        ),
    ),
    "T3": TierProfile(
        tier="T3",
        name="Moderate",
        assessment_type="Targeted Security Review",
        required_controls=(
            "Security governance",
            "Access control",
            "Data protection",
            "Vulnerability management",
            "Incident response",
        ),
        required_evidence=(
            "Security questionnaire or equivalent",
            "Security Policy",
            "SOC 2 / ISO 27001 if available",
        ),
        monitoring_rules=(
            "Evidence freshness monitoring",
            "Material change monitoring",
        ),
        reassessment_rules=(
            "Event-triggered review",
            "Material service change",
            "Security incident",
            "Evidence expiration when relied upon",
        ),
    ),
    "T4": TierProfile(
        tier="T4",
        name="Low",
        assessment_type="Basic Security Screening",
        required_controls=(
            "Basic security ownership",
            "Access control",
            "Incident contact and escalation",
        ),
        required_evidence=("Basic security attestation",),
        monitoring_rules=("Exception-based monitoring",),
        reassessment_rules=(
            "Material scope change",
            "Security incident",
            "Increase in business criticality or data sensitivity",
        ),
    ),
}


def tier_code_from_score(score: int) -> str:
    score = max(0, min(100, int(score)))
    if score >= 75:
        return "T1"
    if score >= 50:
        return "T2"
    if score >= 25:
        return "T3"
    return "T4"


def get_tier_profile(
    score: int,
    *,
    ai_enabled: bool = False,
    regulated_data: bool = False,
) -> TierProfile:
    base = _BASE_PROFILES[tier_code_from_score(score)]

    controls = list(base.required_controls)
    evidence = list(base.required_evidence)
    monitoring = list(base.monitoring_rules)
    reassessment = list(base.reassessment_rules)

    if ai_enabled:
        controls += [
            "AI governance and model accountability",
            "AI data handling and model access controls",
            "AI change, evaluation, and incident management",
        ]
        evidence += [
            "AI governance / acceptable use documentation",
            "AI architecture or data-flow documentation",
        ]
        monitoring.append("Material AI model or capability change monitoring")
        reassessment.append("Material AI capability, model, or data-use change")

    if regulated_data:
        controls += [
            "Regulated data handling and minimization",
            "Data retention and secure disposal",
        ]
        evidence.append("Applicable regulatory assurance evidence")
        reassessment.append("Change in regulated data scope or processing purpose")

    return TierProfile(
        tier=base.tier,
        name=base.name,
        assessment_type=base.assessment_type,
        required_controls=tuple(dict.fromkeys(controls)),
        required_evidence=tuple(dict.fromkeys(evidence)),
        monitoring_rules=tuple(dict.fromkeys(monitoring)),
        reassessment_rules=tuple(dict.fromkeys(reassessment)),
    )


def tier_label(profile: TierProfile) -> str:
    return f"Tier {profile.tier[-1]} — {profile.name}"
