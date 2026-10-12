from dataclasses import dataclass
from typing import Tuple

from src.control_effectiveness import (
    ControlEffectivenessResult,
)
from src.residual_risk_activation_execution_service import (
    RESIDUAL_RISK_ACTIVATION_EXECUTION_POLICY_VERSION,
)
from src.residual_risk_activation import (
    RESIDUAL_RISK_ACTIVATION_POLICY_VERSION,
)
from src.residual_risk_reconciliation import (
    RESIDUAL_RISK_RECONCILIATION_POLICY_VERSION,
)
from src.scoring import (
    RESIDUAL_RISK_POLICY_VERSION,
)


RESIDUAL_RISK_ACTIVATION_VALIDITY_POLICY_VERSION = "RAV-1.0"

STATUS_VALID = "Valid"
STATUS_REVALIDATION_REQUIRED = "Revalidation Required"
STATUS_CHALLENGED = "Challenged"
STATUS_NOT_ACTIVATED = "Not Activated"


@dataclass(frozen=True)
class ResidualRiskActivationValidity:
    status: str
    valid: bool
    revalidation_required: bool
    challenged: bool

    reasons: Tuple[str, ...]

    activated_residual_risk: float | None
    current_authoritative_risk: float

    decision_coverage_percent: int
    control_effectiveness_status: str

    policy_version: str = (
        RESIDUAL_RISK_ACTIVATION_VALIDITY_POLICY_VERSION
    )


def evaluate_residual_risk_activation_validity(
    *,
    latest_execution,
    current_authoritative_risk: float,
    control_effectiveness: ControlEffectivenessResult,
    assessment_complete: bool,
) -> ResidualRiskActivationValidity:
    """
    Evaluate whether a previously activated authoritative
    residual-risk value remains supported by the current
    governed assurance state.

    RAV-1.0 never silently changes the authoritative score.
    It only determines whether that score remains trustworthy
    or requires revalidation.
    """

    current_risk = round(
        max(
            0.0,
            min(
                100.0,
                float(
                    current_authoritative_risk
                    or 0
                ),
            ),
        ),
        1,
    )

    if latest_execution is None:
        return ResidualRiskActivationValidity(
            status=STATUS_NOT_ACTIVATED,
            valid=False,
            revalidation_required=False,
            challenged=False,
            reasons=(
                "No controlled residual-risk activation "
                "has been executed for this assessment.",
            ),
            activated_residual_risk=None,
            current_authoritative_risk=current_risk,
            decision_coverage_percent=(
                control_effectiveness
                .decision_coverage_percent
            ),
            control_effectiveness_status=(
                control_effectiveness.status
            ),
        )

    reasons = []
    challenged = False

    activated_risk = round(
        float(
            latest_execution
            .activated_residual_risk
        ),
        1,
    )

    # -----------------------------------------------------
    # Authoritative score changed outside this activation
    # -----------------------------------------------------

    if abs(
        current_risk
        - activated_risk
    ) > 0.01:
        challenged = True

        reasons.append(
            "AUTHORITATIVE_RISK_CHANGED_AFTER_ACTIVATION"
        )

    # -----------------------------------------------------
    # Governed control basis has deteriorated
    # -----------------------------------------------------

    if (
        control_effectiveness
        .effectiveness_score
        is None
    ):
        reasons.append(
            "GOVERNED_EFFECTIVENESS_UNAVAILABLE"
        )

    if (
        control_effectiveness
        .decision_coverage_percent
        < 80
    ):
        reasons.append(
            "GOVERNED_DECISION_COVERAGE_BELOW_THRESHOLD"
        )

    if (
        control_effectiveness.status
        != "Governed"
    ):
        reasons.append(
            "CONTROL_EFFECTIVENESS_NOT_GOVERNED"
        )

    # -----------------------------------------------------
    # Assessment state changed / no longer complete
    # -----------------------------------------------------

    if not assessment_complete:
        reasons.append(
            "ASSESSMENT_NOT_COMPLETE"
        )

    # -----------------------------------------------------
    # Policy lineage is no longer current
    # -----------------------------------------------------

    if (
        latest_execution
        .execution_policy_version
        != RESIDUAL_RISK_ACTIVATION_EXECUTION_POLICY_VERSION
    ):
        reasons.append(
            "EXECUTION_POLICY_VERSION_OUTDATED"
        )

    if (
        latest_execution
        .activation_policy_version
        != RESIDUAL_RISK_ACTIVATION_POLICY_VERSION
    ):
        reasons.append(
            "ACTIVATION_POLICY_VERSION_OUTDATED"
        )

    if (
        latest_execution
        .reconciliation_policy_version
        != RESIDUAL_RISK_RECONCILIATION_POLICY_VERSION
    ):
        reasons.append(
            "RECONCILIATION_POLICY_VERSION_OUTDATED"
        )

    if (
        latest_execution
        .residual_risk_policy_version
        != RESIDUAL_RISK_POLICY_VERSION
    ):
        reasons.append(
            "RESIDUAL_RISK_POLICY_VERSION_OUTDATED"
        )

    reasons = tuple(
        dict.fromkeys(
            reasons
        )
    )

    if challenged:
        status = STATUS_CHALLENGED
        valid = False
        revalidation_required = True

    elif reasons:
        status = STATUS_REVALIDATION_REQUIRED
        valid = False
        revalidation_required = True

    else:
        status = STATUS_VALID
        valid = True
        revalidation_required = False

    return ResidualRiskActivationValidity(
        status=status,
        valid=valid,
        revalidation_required=(
            revalidation_required
        ),
        challenged=challenged,
        reasons=reasons,
        activated_residual_risk=(
            activated_risk
        ),
        current_authoritative_risk=(
            current_risk
        ),
        decision_coverage_percent=(
            control_effectiveness
            .decision_coverage_percent
        ),
        control_effectiveness_status=(
            control_effectiveness.status
        ),
    )
