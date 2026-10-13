from dataclasses import dataclass
from typing import Tuple

from src.residual_risk_activation_validity import (
    ResidualRiskActivationValidity,
)


REVALIDATION_CASE_POLICY_VERSION = "RVC-1.0"

STATUS_OPEN = "Open"
STATUS_IN_PROGRESS = "In Progress"
STATUS_READY_FOR_REVIEW = "Ready for Review"
STATUS_RESOLVED = "Resolved"


@dataclass(frozen=True)
class RevalidationCaseSnapshot:
    """
    Immutable policy snapshot representing the assurance state
    that caused a residual-risk activation to require revalidation.

    RVC-1.0 does not modify risk, assurance, evidence, or assessment
    records. Persistence and workflow transitions are handled
    separately.
    """

    status: str

    trigger_status: str
    trigger_reasons: Tuple[str, ...]

    activation_execution_id: int

    activated_residual_risk: float
    current_authoritative_risk: float

    decision_coverage_percent: int
    control_effectiveness_status: str

    rav_policy_version: str
    policy_version: str = REVALIDATION_CASE_POLICY_VERSION


def build_revalidation_case_snapshot(
    *,
    validity: ResidualRiskActivationValidity,
    latest_execution,
) -> RevalidationCaseSnapshot:
    """
    Build a governed revalidation-case snapshot from RAV output.

    A case may be opened only when:
    - a controlled activation execution exists; and
    - RAV explicitly requires revalidation.

    This prevents ordinary incomplete assessments or vendors that
    were never activated from creating misleading revalidation cases.
    """

    if latest_execution is None:
        raise ValueError(
            "A revalidation case requires a prior controlled "
            "residual-risk activation execution."
        )

    if not validity.revalidation_required:
        raise ValueError(
            "A revalidation case may be opened only when "
            "RAV requires revalidation."
        )

    if validity.activated_residual_risk is None:
        raise ValueError(
            "RAV did not provide an activated residual-risk value."
        )

    reasons = tuple(
        dict.fromkeys(
            reason
            for reason in validity.reasons
            if reason
        )
    )

    if not reasons:
        raise ValueError(
            "A revalidation case requires at least one "
            "governed trigger reason."
        )

    execution_id = getattr(
        latest_execution,
        "id",
        None,
    )

    if execution_id is None:
        raise ValueError(
            "The prior activation execution must have a "
            "persistent execution identifier."
        )

    return RevalidationCaseSnapshot(
        status=STATUS_OPEN,
        trigger_status=validity.status,
        trigger_reasons=reasons,
        activation_execution_id=int(execution_id),
        activated_residual_risk=round(
            float(validity.activated_residual_risk),
            1,
        ),
        current_authoritative_risk=round(
            float(validity.current_authoritative_risk),
            1,
        ),
        decision_coverage_percent=int(
            validity.decision_coverage_percent
        ),
        control_effectiveness_status=(
            validity.control_effectiveness_status
        ),
        rav_policy_version=validity.policy_version,
    )
