from dataclasses import dataclass
from typing import Tuple


TIER_POLICY_VERSION = "TP-2.0"


@dataclass(frozen=True)
class ControlRequirement:
    control_id: str
    domain: str
    requirement: str
    mandatory: bool = True
    rationale: str = ""


@dataclass(frozen=True)
class EvidenceRequirement:
    evidence_id: str
    evidence_type: str
    mandatory: bool = True
    freshness_months: int | None = None
    rationale: str = ""


@dataclass(frozen=True)
class TierProfile:
    tier: str
    name: str
    assessment_type: str
    required_controls: Tuple[ControlRequirement, ...]
    required_evidence: Tuple[EvidenceRequirement, ...]
    monitoring_rules: Tuple[str, ...]
    reassessment_rules: Tuple[str, ...]
    policy_version: str = TIER_POLICY_VERSION


CONTROL_LIBRARY = {
    "GOV-01": ControlRequirement(
        control_id="GOV-01",
        domain="Governance",
        requirement="Security governance and ownership",
        rationale="Establishes accountable ownership for the vendor security program.",
    ),
    "IAM-01": ControlRequirement(
        control_id="IAM-01",
        domain="Identity and Access Management",
        requirement="Identity and access management",
    ),
    "PAM-01": ControlRequirement(
        control_id="PAM-01",
        domain="Privileged Access Management",
        requirement="Privileged access management",
    ),
    "ENC-01": ControlRequirement(
        control_id="ENC-01",
        domain="Data Protection",
        requirement="Encryption and key management",
    ),
    "VM-01": ControlRequirement(
        control_id="VM-01",
        domain="Vulnerability Management",
        requirement="Vulnerability and patch management",
    ),
    "SDLC-01": ControlRequirement(
        control_id="SDLC-01",
        domain="Secure Development",
        requirement="Secure software development",
    ),
    "LOG-01": ControlRequirement(
        control_id="LOG-01",
        domain="Logging and Monitoring",
        requirement="Logging and security monitoring",
    ),
    "IR-01": ControlRequirement(
        control_id="IR-01",
        domain="Incident Response",
        requirement="Incident response capability",
    ),
    "BCP-01": ControlRequirement(
        control_id="BCP-01",
        domain="Business Continuity",
        requirement="Business continuity and disaster recovery",
    ),
    "TPRM-01": ControlRequirement(
        control_id="TPRM-01",
        domain="Fourth-Party Risk",
        requirement="Third- and fourth-party risk management",
    ),
    "DATA-01": ControlRequirement(
        control_id="DATA-01",
        domain="Data Protection",
        requirement="Data protection, retention, and secure disposal",
    ),
    "AI-01": ControlRequirement(
        control_id="AI-01",
        domain="AI Governance",
        requirement="AI governance and model accountability",
    ),
    "AI-02": ControlRequirement(
        control_id="AI-02",
        domain="AI Security",
        requirement="AI data handling and model access controls",
    ),
    "AI-03": ControlRequirement(
        control_id="AI-03",
        domain="AI Operations",
        requirement="AI change, evaluation, and incident management",
    ),
    "REG-01": ControlRequirement(
        control_id="REG-01",
        domain="Regulatory",
        requirement="Regulated data handling and minimization",
    ),
}


EVIDENCE_LIBRARY = {
    "EVID-SOC2": EvidenceRequirement(
        evidence_id="EVID-SOC2",
        evidence_type="SOC 2 Type II or equivalent assurance report",
        freshness_months=12,
    ),
    "EVID-PENTEST": EvidenceRequirement(
        evidence_id="EVID-PENTEST",
        evidence_type="Penetration Test",
        freshness_months=12,
    ),
    "EVID-BCP": EvidenceRequirement(
        evidence_id="EVID-BCP",
        evidence_type="BCP / DR Test",
        freshness_months=12,
    ),
    "EVID-IR": EvidenceRequirement(
        evidence_id="EVID-IR",
        evidence_type="Incident Response Plan",
        freshness_months=12,
    ),
    "EVID-POLICY": EvidenceRequirement(
        evidence_id="EVID-POLICY",
        evidence_type="Security Policy",
        freshness_months=12,
    ),
    "EVID-ARCH": EvidenceRequirement(
        evidence_id="EVID-ARCH",
        evidence_type="Architecture Diagram",
        freshness_months=12,
    ),
    "EVID-QUESTIONNAIRE": EvidenceRequirement(
        evidence_id="EVID-QUESTIONNAIRE",
        evidence_type="Security questionnaire or equivalent",
        freshness_months=12,
    ),
    "EVID-BASIC": EvidenceRequirement(
        evidence_id="EVID-BASIC",
        evidence_type="Basic security attestation",
        freshness_months=12,
    ),
    "EVID-AI-GOV": EvidenceRequirement(
        evidence_id="EVID-AI-GOV",
        evidence_type="AI governance / acceptable use documentation",
        freshness_months=12,
    ),
    "EVID-AI-ARCH": EvidenceRequirement(
        evidence_id="EVID-AI-ARCH",
        evidence_type="AI architecture or data-flow documentation",
        freshness_months=12,
    ),
    "EVID-REG": EvidenceRequirement(
        evidence_id="EVID-REG",
        evidence_type="Applicable regulatory assurance evidence",
        freshness_months=12,
    ),
}


_TIER_CONTROL_IDS = {
    "T1": (
        "GOV-01",
        "IAM-01",
        "PAM-01",
        "ENC-01",
        "VM-01",
        "SDLC-01",
        "LOG-01",
        "IR-01",
        "BCP-01",
        "TPRM-01",
        "DATA-01",
    ),
    "T2": (
        "GOV-01",
        "IAM-01",
        "ENC-01",
        "VM-01",
        "LOG-01",
        "IR-01",
        "BCP-01",
        "DATA-01",
    ),
    "T3": (
        "GOV-01",
        "IAM-01",
        "ENC-01",
        "VM-01",
        "IR-01",
    ),
    "T4": (
        "GOV-01",
        "IAM-01",
        "IR-01",
    ),
}


_TIER_EVIDENCE_IDS = {
    "T1": (
        "EVID-SOC2",
        "EVID-PENTEST",
        "EVID-BCP",
        "EVID-IR",
        "EVID-POLICY",
        "EVID-ARCH",
    ),
    "T2": (
        "EVID-SOC2",
        "EVID-PENTEST",
        "EVID-IR",
        "EVID-POLICY",
    ),
    "T3": (
        "EVID-QUESTIONNAIRE",
        "EVID-POLICY",
    ),
    "T4": (
        "EVID-BASIC",
    ),
}


_ASSESSMENT_TYPES = {
    "T1": "Full Security Assessment",
    "T2": "Enhanced Security Assessment",
    "T3": "Targeted Security Review",
    "T4": "Basic Security Screening",
}


_MONITORING_RULES = {
    "T1": (
        "Continuous external security monitoring",
        "Evidence freshness monitoring",
        "Open critical/high finding monitoring",
        "Material change monitoring",
    ),
    "T2": (
        "Continuous external security monitoring",
        "Evidence freshness monitoring",
        "Open high finding monitoring",
    ),
    "T3": (
        "Evidence freshness monitoring",
        "Material change monitoring",
    ),
    "T4": (
        "Exception-based monitoring",
    ),
}


_REASSESSMENT_RULES = {
    "T1": (
        "At least annually",
        "Security incident or breach",
        "Material service or architecture change",
        "Critical evidence expiration",
        "Significant security rating deterioration",
    ),
    "T2": (
        "Risk-based periodic review",
        "Security incident or breach",
        "Material service change",
        "Evidence expiration",
        "Significant security rating deterioration",
    ),
    "T3": (
        "Event-triggered review",
        "Material service change",
        "Security incident",
        "Evidence expiration when relied upon",
    ),
    "T4": (
        "Material scope change",
        "Security incident",
        "Increase in business criticality or data sensitivity",
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
    privileged_access: bool = False,
) -> TierProfile:
    tier = tier_code_from_score(score)

    control_ids = list(_TIER_CONTROL_IDS[tier])
    evidence_ids = list(_TIER_EVIDENCE_IDS[tier])

    monitoring = list(_MONITORING_RULES[tier])
    reassessment = list(_REASSESSMENT_RULES[tier])

    if ai_enabled:
        control_ids.extend(
            [
                "AI-01",
                "AI-02",
                "AI-03",
            ]
        )

        evidence_ids.extend(
            [
                "EVID-AI-GOV",
                "EVID-AI-ARCH",
            ]
        )

        monitoring.append(
            "Material AI model or capability change monitoring"
        )

        reassessment.append(
            "Material AI capability, model, or data-use change"
        )

    if regulated_data:
        control_ids.append("REG-01")
        control_ids.append("DATA-01")

        evidence_ids.append("EVID-REG")

        reassessment.append(
            "Change in regulated data scope or processing purpose"
        )

    if privileged_access:
        control_ids.append("PAM-01")
        control_ids.append("IAM-01")

        if tier in ("T3", "T4"):
            evidence_ids.append("EVID-POLICY")

        monitoring.append(
            "Privileged access material-change monitoring"
        )

    control_ids = tuple(dict.fromkeys(control_ids))
    evidence_ids = tuple(dict.fromkeys(evidence_ids))

    controls = tuple(
        CONTROL_LIBRARY[control_id]
        for control_id in control_ids
    )

    evidence = tuple(
        EVIDENCE_LIBRARY[evidence_id]
        for evidence_id in evidence_ids
    )

    return TierProfile(
        tier=tier,
        name={
            "T1": "Critical",
            "T2": "High",
            "T3": "Moderate",
            "T4": "Low",
        }[tier],
        assessment_type=_ASSESSMENT_TYPES[tier],
        required_controls=controls,
        required_evidence=evidence,
        monitoring_rules=tuple(dict.fromkeys(monitoring)),
        reassessment_rules=tuple(dict.fromkeys(reassessment)),
    )


def tier_label(profile: TierProfile) -> str:
    return f"Tier {profile.tier[-1]} — {profile.name}"