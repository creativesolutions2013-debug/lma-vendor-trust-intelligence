from dataclasses import dataclass

from src.control_effectiveness_guardrail import (
    GuardedControlEffectiveness,
)
from src.scoring import (
    calculate_residual_risk,
    rating_from_score,
)


GOVERNED_RESIDUAL_RISK_POLICY_VERSION = "GRR-1.0"


@dataclass(frozen=True)
class GovernedResidualRiskPreview:
    existing_residual_risk: float
    preview_residual_risk: float

    existing_rating: str
    preview_rating: str

    effective_control_input: float
    control_input_mode: str

    score_delta: float

    ready_for_activation: bool
    activation_reason: str

    policy_version: str = (
        GOVERNED_RESIDUAL_RISK_POLICY_VERSION
    )


def preview_governed_residual_risk(
    *,
    inherent_risk: float,
    external_risk: float,
    existing_residual_risk: float,
    guarded_effectiveness: GuardedControlEffectiveness,
) -> GovernedResidualRiskPreview:
    """
    Preview residual risk using the guarded control-effectiveness
    input without changing any stored vendor risk values.

    Activation is permitted only when governed control
    effectiveness has reached sufficient decision coverage.
    """

    preview_score = calculate_residual_risk(
        inherent_risk=inherent_risk,
        control_effectiveness=(
            guarded_effectiveness
            .effective_control_input
        ),
        external_risk=external_risk,
    )

    existing_score = round(
        max(
            0.0,
            min(
                100.0,
                float(
                    existing_residual_risk
                ),
            ),
        ),
        1,
    )

    existing_rating = rating_from_score(
        existing_score
    )

    preview_rating = rating_from_score(
        preview_score
    )

    score_delta = round(
        preview_score
        - existing_score,
        1,
    )

    ready_for_activation = (
        guarded_effectiveness.mode
        == "Governed"
    )

    if ready_for_activation:
        activation_reason = (
            "Decision coverage is at least 80%. "
            "Governed control effectiveness is eligible "
            "to become the residual-risk control input."
        )

    elif (
        guarded_effectiveness.mode
        == "Blended"
    ):
        activation_reason = (
            "Decision coverage is between 50% and 79%. "
            "The governed signal remains blended and "
            "should stay in preview mode."
        )

    elif (
        guarded_effectiveness.mode
        == "Coverage Guardrail"
    ):
        activation_reason = (
            "Decision coverage is below 50%. "
            "Governed effectiveness cannot change "
            "stored residual risk."
        )

    else:
        activation_reason = (
            "No sufficiently governed effectiveness "
            "signal is available for activation."
        )

    return GovernedResidualRiskPreview(
        existing_residual_risk=(
            existing_score
        ),
        preview_residual_risk=(
            preview_score
        ),
        existing_rating=(
            existing_rating
        ),
        preview_rating=(
            preview_rating
        ),
        effective_control_input=(
            guarded_effectiveness
            .effective_control_input
        ),
        control_input_mode=(
            guarded_effectiveness.mode
        ),
        score_delta=(
            score_delta
        ),
        ready_for_activation=(
            ready_for_activation
        ),
        activation_reason=(
            activation_reason
        ),
    )