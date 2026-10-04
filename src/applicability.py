from dataclasses import dataclass
from typing import Tuple

from src.tiering import (
    CONTROL_LIBRARY,
    EVIDENCE_LIBRARY,
    ControlRequirement,
    EvidenceRequirement,
    TierProfile,
)


APPLICABILITY_POLICY_VERSION = "AP-1.0"


@dataclass(frozen=True)
class VendorRiskContext:
    """
    Facts about the vendor relationship used to determine
    which security requirements apply.

    The vendor supplies facts.
    The engine determines applicability.
    """

    sensitive_data: bool = False
    regulated_data: bool = False
    privileged_access: bool = False
    system_access: bool = False
    internet_facing: bool = False
    business_critical: bool = False
    ai_enabled: bool = False
    fourth_party_dependency: bool = False


@dataclass(frozen=True)
class ApplicabilityDecision:
    """
    Explainable result for one applicability rule.
    """

    rule_id: str
    applies: bool
    requirement_type: str
    requirement_id: str
    reason: str


@dataclass(frozen=True)
class ApplicabilityResult:
    """
    Final applicability result after tier baseline requirements
    and contextual requirements are combined.
    """

    controls: Tuple[ControlRequirement, ...]
    evidence: Tuple[EvidenceRequirement, ...]
    decisions: Tuple[ApplicabilityDecision, ...]
    review_required: bool
    review_reasons: Tuple[str, ...]
    policy_version: str = APPLICABILITY_POLICY_VERSION


def _decision(
    *,
    rule_id: str,
    applies: bool,
    requirement_type: str,
    requirement_id: str,
    reason: str,
) -> ApplicabilityDecision:
    return ApplicabilityDecision(
        rule_id=rule_id,
        applies=applies,
        requirement_type=requirement_type,
        requirement_id=requirement_id,
        reason=reason,
    )


def evaluate_applicability(
    profile: TierProfile,
    context: VendorRiskContext,
) -> ApplicabilityResult:
    """
    Apply contextual rules on top of the tier baseline.

    Important design principle:

    Tier establishes minimum due diligence.
    Applicability rules may ADD requirements.

    Applicability rules do not silently remove mandatory
    tier requirements.
    """

    control_ids = [
        control.control_id
        for control in profile.required_controls
    ]

    evidence_ids = [
        evidence.evidence_id
        for evidence in profile.required_evidence
    ]

    decisions = []
    review_reasons = []

    # ---------------------------------------------------------
    # AP-001 — Sensitive data
    # ---------------------------------------------------------

    if context.sensitive_data:
        control_ids.extend(
            [
                "ENC-01",
                "DATA-01",
            ]
        )

        decisions.append(
            _decision(
                rule_id="AP-001",
                applies=True,
                requirement_type="control",
                requirement_id="ENC-01",
                reason=(
                    "Vendor handles sensitive data; "
                    "encryption requirements apply."
                ),
            )
        )

        decisions.append(
            _decision(
                rule_id="AP-001",
                applies=True,
                requirement_type="control",
                requirement_id="DATA-01",
                reason=(
                    "Vendor handles sensitive data; "
                    "data protection, retention, and "
                    "secure disposal requirements apply."
                ),
            )
        )

    # ---------------------------------------------------------
    # AP-002 — Regulated data
    # ---------------------------------------------------------

    if context.regulated_data:
        control_ids.extend(
            [
                "REG-01",
                "DATA-01",
            ]
        )

        evidence_ids.append("EVID-REG")

        decisions.append(
            _decision(
                rule_id="AP-002",
                applies=True,
                requirement_type="control",
                requirement_id="REG-01",
                reason=(
                    "Vendor processes regulated data; "
                    "regulatory handling requirements apply."
                ),
            )
        )

        decisions.append(
            _decision(
                rule_id="AP-002",
                applies=True,
                requirement_type="evidence",
                requirement_id="EVID-REG",
                reason=(
                    "Regulated-data processing requires "
                    "applicable regulatory assurance evidence."
                ),
            )
        )

    # ---------------------------------------------------------
    # AP-003 — System access
    # ---------------------------------------------------------

    if context.system_access:
        control_ids.append("IAM-01")

        decisions.append(
            _decision(
                rule_id="AP-003",
                applies=True,
                requirement_type="control",
                requirement_id="IAM-01",
                reason=(
                    "Vendor has system access; "
                    "identity and access management applies."
                ),
            )
        )

    # ---------------------------------------------------------
    # AP-004 — Privileged access
    # ---------------------------------------------------------

    if context.privileged_access:
        control_ids.extend(
            [
                "IAM-01",
                "PAM-01",
            ]
        )

        decisions.append(
            _decision(
                rule_id="AP-004",
                applies=True,
                requirement_type="control",
                requirement_id="PAM-01",
                reason=(
                    "Vendor has privileged access; "
                    "privileged access management is mandatory."
                ),
            )
        )

        # Privileged access should always require analyst review.
        review_reasons.append(
            "Privileged vendor access requires analyst validation."
        )

    # ---------------------------------------------------------
    # AP-005 — Internet-facing service
    # ---------------------------------------------------------

    if context.internet_facing:
        control_ids.append("VM-01")
        evidence_ids.append("EVID-PENTEST")

        decisions.append(
            _decision(
                rule_id="AP-005",
                applies=True,
                requirement_type="control",
                requirement_id="VM-01",
                reason=(
                    "Internet-facing exposure increases attack "
                    "surface; vulnerability management applies."
                ),
            )
        )

        decisions.append(
            _decision(
                rule_id="AP-005",
                applies=True,
                requirement_type="evidence",
                requirement_id="EVID-PENTEST",
                reason=(
                    "Internet-facing service requires current "
                    "penetration-testing evidence."
                ),
            )
        )

    # ---------------------------------------------------------
    # AP-006 — Business-critical service
    # ---------------------------------------------------------

    if context.business_critical:
        control_ids.append("BCP-01")
        evidence_ids.append("EVID-BCP")

        decisions.append(
            _decision(
                rule_id="AP-006",
                applies=True,
                requirement_type="control",
                requirement_id="BCP-01",
                reason=(
                    "Vendor supports a business-critical process; "
                    "resilience requirements apply."
                ),
            )
        )

        decisions.append(
            _decision(
                rule_id="AP-006",
                applies=True,
                requirement_type="evidence",
                requirement_id="EVID-BCP",
                reason=(
                    "Business-critical dependency requires "
                    "BCP/DR testing evidence."
                ),
            )
        )

    # ---------------------------------------------------------
    # AP-007 — AI capability
    # ---------------------------------------------------------

    if context.ai_enabled:
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

        decisions.append(
            _decision(
                rule_id="AP-007",
                applies=True,
                requirement_type="control",
                requirement_id="AI-01",
                reason=(
                    "Vendor provides AI capability; "
                    "AI governance requirements apply."
                ),
            )
        )

        decisions.append(
            _decision(
                rule_id="AP-007",
                applies=True,
                requirement_type="evidence",
                requirement_id="EVID-AI-ARCH",
                reason=(
                    "AI capability requires architecture or "
                    "data-flow evidence."
                ),
            )
        )

    # ---------------------------------------------------------
    # AP-008 — Fourth-party dependency
    # ---------------------------------------------------------

    if context.fourth_party_dependency:
        control_ids.append("TPRM-01")

        decisions.append(
            _decision(
                rule_id="AP-008",
                applies=True,
                requirement_type="control",
                requirement_id="TPRM-01",
                reason=(
                    "Material fourth-party dependency exists; "
                    "supplier-risk governance applies."
                ),
            )
        )

    # ---------------------------------------------------------
    # Cross-factor consistency / analyst-review checks
    # ---------------------------------------------------------

    if (
        context.privileged_access
        and not context.system_access
    ):
        review_reasons.append(
            "Privileged access is marked true while system "
            "access is false; intake answers require review."
        )

    if (
        context.regulated_data
        and not context.sensitive_data
    ):
        review_reasons.append(
            "Regulated data is marked true while sensitive "
            "data is false; data classification requires review."
        )

    # Preserve order while removing duplicates.
    control_ids = tuple(
        dict.fromkeys(control_ids)
    )

    evidence_ids = tuple(
        dict.fromkeys(evidence_ids)
    )

    controls = tuple(
        CONTROL_LIBRARY[control_id]
        for control_id in control_ids
    )

    evidence = tuple(
        EVIDENCE_LIBRARY[evidence_id]
        for evidence_id in evidence_ids
    )

    return ApplicabilityResult(
        controls=controls,
        evidence=evidence,
        decisions=tuple(decisions),
        review_required=bool(review_reasons),
        review_reasons=tuple(
            dict.fromkeys(review_reasons)
        ),
    )