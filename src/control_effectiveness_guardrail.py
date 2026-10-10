from dataclasses import dataclass


CONTROL_EFFECTIVENESS_GUARDRAIL_VERSION = "CEG-1.0"


@dataclass(frozen=True)
class GuardedControlEffectiveness:
    legacy_effectiveness: float
    governed_effectiveness: float | None
    decision_coverage_percent: int

    effective_control_input: float
    mode: str

    governed_weight: float
    legacy_weight: float

    reason: str

    policy_version: str = (
        CONTROL_EFFECTIVENESS_GUARDRAIL_VERSION
    )


def _bounded_score(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            100.0,
            float(value),
        ),
    )


def select_control_effectiveness_input(
    *,
    legacy_effectiveness: float,
    governed_effectiveness: float | None,
    decision_coverage_percent: int,
) -> GuardedControlEffectiveness:
    """
    Select the control-effectiveness input used by residual risk.

    Governance rules:

    < 50% decision coverage:
        Ignore governed effectiveness for residual-risk scoring.

    50-79% coverage:
        Blend governed and legacy effectiveness, but cap
        governed influence at 50%.

    >= 80% coverage:
        Governed effectiveness becomes the primary input.

    Missing governed effectiveness never becomes zero.
    """

    legacy = _bounded_score(
        legacy_effectiveness
    )

    coverage = max(
        0,
        min(
            100,
            int(
                decision_coverage_percent
            ),
        ),
    )

    if governed_effectiveness is None:
        return GuardedControlEffectiveness(
            legacy_effectiveness=legacy,
            governed_effectiveness=None,
            decision_coverage_percent=coverage,
            effective_control_input=legacy,
            mode="Legacy",
            governed_weight=0.0,
            legacy_weight=1.0,
            reason=(
                "No governed control-effectiveness score "
                "is available. Existing control effectiveness "
                "remains the residual-risk input."
            ),
        )

    governed = _bounded_score(
        governed_effectiveness
    )

    if coverage < 50:
        return GuardedControlEffectiveness(
            legacy_effectiveness=legacy,
            governed_effectiveness=governed,
            decision_coverage_percent=coverage,
            effective_control_input=legacy,
            mode="Coverage Guardrail",
            governed_weight=0.0,
            legacy_weight=1.0,
            reason=(
                "Decision coverage is below 50%. "
                "Governed effectiveness is informational only "
                "and does not influence residual risk."
            ),
        )

    if coverage < 80:
        governed_weight = 0.50
        legacy_weight = 0.50

        blended = (
            governed * governed_weight
            + legacy * legacy_weight
        )

        return GuardedControlEffectiveness(
            legacy_effectiveness=legacy,
            governed_effectiveness=governed,
            decision_coverage_percent=coverage,
            effective_control_input=round(
                blended,
                1,
            ),
            mode="Blended",
            governed_weight=governed_weight,
            legacy_weight=legacy_weight,
            reason=(
                "Decision coverage is between 50% and 79%. "
                "Governed effectiveness is blended with the "
                "existing control-effectiveness input."
            ),
        )

    return GuardedControlEffectiveness(
        legacy_effectiveness=legacy,
        governed_effectiveness=governed,
        decision_coverage_percent=coverage,
        effective_control_input=governed,
        mode="Governed",
        governed_weight=1.0,
        legacy_weight=0.0,
        reason=(
            "Decision coverage is at least 80%. "
            "Governed control effectiveness is used as the "
            "primary residual-risk control input."
        ),
    )