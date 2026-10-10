from dataclasses import dataclass

from src.control_effectiveness_guardrail import (
    GuardedControlEffectiveness,
)
from src.scoring import (
    calculate_residual_risk,
    rating_from_score,
)


RESIDUAL_RISK_RECONCILIATION_POLICY_VERSION = "RRR-1.0"


@dataclass(frozen=True)
class ResidualRiskReconciliation:
    stored_residual_risk: float
    fresh_baseline_risk: float
    governed_preview_risk: float

    stored_rating: str
    baseline_rating: str
    governed_rating: str

    stored_to_baseline_delta: float
    governed_contribution_delta: float
    stored_to_governed_delta: float

    drift_detected: bool

    legacy_control_input: float
    effective_control_input: float
    control_input_mode: str

    activation_ready: bool

    policy_version: str = (
        RESIDUAL_RISK_RECONCILIATION_POLICY_VERSION
    )


def _bounded_score(
    value: float,
) -> float:
    return round(
        max(
            0.0,
            min(
                100.0,
                float(value),
            ),
        ),
        1,
    )


def reconcile_residual_risk(
    *,
    inherent_risk: float,
    external_risk: float,
    stored_residual_risk: float,
    legacy_effectiveness: float,
    guarded_effectiveness: GuardedControlEffectiveness,
) -> ResidualRiskReconciliation:
    """
    Separate residual-risk drift from the effect of governed
    control effectiveness.

    Fresh baseline:
        RR-2.0 calculated using the existing / legacy
        control-effectiveness input.

    Governed preview:
        RR-2.0 calculated using the CEG-1.0 guarded input.

    This allows analysts to distinguish:

        stored score drift
            from
        governed assurance impact.
    """

    stored = _bounded_score(
        stored_residual_risk
    )

    legacy_input = _bounded_score(
        legacy_effectiveness
    )

    effective_input = _bounded_score(
        guarded_effectiveness
        .effective_control_input
    )

    baseline = calculate_residual_risk(
        inherent_risk=inherent_risk,
        control_effectiveness=(
            legacy_input
        ),
        external_risk=external_risk,
    )

    governed = calculate_residual_risk(
        inherent_risk=inherent_risk,
        control_effectiveness=(
            effective_input
        ),
        external_risk=external_risk,
    )

    stored_to_baseline = round(
        baseline - stored,
        1,
    )

    governed_contribution = round(
        governed - baseline,
        1,
    )

    stored_to_governed = round(
        governed - stored,
        1,
    )

    return ResidualRiskReconciliation(
        stored_residual_risk=stored,
        fresh_baseline_risk=baseline,
        governed_preview_risk=governed,
        stored_rating=rating_from_score(
            stored
        ),
        baseline_rating=rating_from_score(
            baseline
        ),
        governed_rating=rating_from_score(
            governed
        ),
        stored_to_baseline_delta=(
            stored_to_baseline
        ),
        governed_contribution_delta=(
            governed_contribution
        ),
        stored_to_governed_delta=(
            stored_to_governed
        ),
        drift_detected=(
            abs(
                stored_to_baseline
            )
            > 0.1
        ),
        legacy_control_input=(
            legacy_input
        ),
        effective_control_input=(
            effective_input
        ),
        control_input_mode=(
            guarded_effectiveness.mode
        ),
        activation_ready=(
            guarded_effectiveness.mode
            == "Governed"
        ),
    )
