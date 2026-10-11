from dataclasses import dataclass
from typing import Tuple

from src.residual_risk_reconciliation import (
    ResidualRiskReconciliation,
)
from src.scoring import (
    ResidualRiskDecision,
)


RESIDUAL_RISK_ACTIVATION_POLICY_VERSION = "RRA-1.0"


STATUS_BLOCKED = "Blocked"
STATUS_AWAITING_APPROVAL = "Awaiting Analyst Approval"
STATUS_ELIGIBLE = "Eligible for Activation"


@dataclass(frozen=True)
class ResidualRiskActivationDecision:
    system_ready: bool
    analyst_approval_required: bool
    analyst_approved: bool
    activation_eligible: bool

    status: str
    blocking_reasons: Tuple[str, ...]

    governed_residual_risk: float
    governed_rating: str
    control_input_mode: str

    reconciliation_policy_version: str
    residual_risk_policy_version: str

    policy_version: str = (
        RESIDUAL_RISK_ACTIVATION_POLICY_VERSION
    )


def evaluate_residual_risk_activation(
    *,
    reconciliation: ResidualRiskReconciliation,
    residual_risk_decision: ResidualRiskDecision,
    inputs_traceable: bool = True,
    analyst_approved: bool = False,
) -> ResidualRiskActivationDecision:
    """
    Determine whether a governed residual-risk result is eligible
    to become authoritative.

    RRA-1.0 is intentionally conservative.

    Activation requires:

    1. Governed control-effectiveness mode.
    2. Complete input / policy lineage.
    3. No RR-2.0 approval-blocking guardrail.
    4. No RR-2.0 escalation condition.
    5. Explicit analyst approval.

    This function does not persist or mutate any risk value.
    """

    blocking_reasons = []

    if (
        reconciliation.control_input_mode
        != "Governed"
    ):
        blocking_reasons.append(
            "GOVERNED_COVERAGE_INSUFFICIENT"
        )

    if not inputs_traceable:
        blocking_reasons.append(
            "INPUT_LINEAGE_INCOMPLETE"
        )

    if residual_risk_decision.approval_blocked:
        blocking_reasons.append(
            "RR2_APPROVAL_BLOCKED"
        )

    if residual_risk_decision.escalation_required:
        blocking_reasons.append(
            "RR2_ESCALATION_REQUIRED"
        )

    for guardrail in (
        residual_risk_decision
        .triggered_guardrails
    ):
        reason = (
            f"RR2_GUARDRAIL:{guardrail}"
        )

        if reason not in blocking_reasons:
            blocking_reasons.append(
                reason
            )

    system_ready = (
        len(blocking_reasons) == 0
    )

    analyst_approval_required = True

    activation_eligible = (
        system_ready
        and analyst_approved
    )

    if activation_eligible:
        status = STATUS_ELIGIBLE

    elif system_ready:
        status = STATUS_AWAITING_APPROVAL

    else:
        status = STATUS_BLOCKED

    return ResidualRiskActivationDecision(
        system_ready=system_ready,
        analyst_approval_required=(
            analyst_approval_required
        ),
        analyst_approved=analyst_approved,
        activation_eligible=(
            activation_eligible
        ),
        status=status,
        blocking_reasons=tuple(
            blocking_reasons
        ),
        governed_residual_risk=(
            reconciliation
            .governed_preview_risk
        ),
        governed_rating=(
            residual_risk_decision
            .final_rating
        ),
        control_input_mode=(
            reconciliation
            .control_input_mode
        ),
        reconciliation_policy_version=(
            reconciliation
            .policy_version
        ),
        residual_risk_policy_version=(
            residual_risk_decision
            .policy_version
        ),
    )
