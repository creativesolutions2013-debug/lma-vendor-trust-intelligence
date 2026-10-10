from src.control_effectiveness_guardrail import (
    select_control_effectiveness_input,
)
from src.governed_residual_risk import (
    GOVERNED_RESIDUAL_RISK_POLICY_VERSION,
    preview_governed_residual_risk,
)


def test_low_coverage_keeps_legacy_risk_input():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=40,
            decision_coverage_percent=14,
        )
    )

    result = preview_governed_residual_risk(
        inherent_risk=80,
        external_risk=70,
        existing_residual_risk=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.effective_control_input
        == 70.0
    )

    assert (
        result.control_input_mode
        == "Coverage Guardrail"
    )

    assert (
        result.preview_residual_risk
        == 70.0
    )

    assert (
        result.ready_for_activation
        is False
    )


def test_blended_coverage_stays_preview_only():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=60,
        )
    )

    result = preview_governed_residual_risk(
        inherent_risk=80,
        external_risk=70,
        existing_residual_risk=66,
        guarded_effectiveness=guarded,
    )

    assert (
        result.effective_control_input
        == 70.0
    )

    assert (
        result.control_input_mode
        == "Blended"
    )

    assert (
        result.ready_for_activation
        is False
    )


def test_governed_mode_can_be_activation_ready():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=80,
        )
    )

    result = preview_governed_residual_risk(
        inherent_risk=80,
        external_risk=70,
        existing_residual_risk=66,
        guarded_effectiveness=guarded,
    )

    assert (
        result.effective_control_input
        == 60.0
    )

    assert (
        result.control_input_mode
        == "Governed"
    )

    assert (
        result.ready_for_activation
        is True
    )


def test_preview_does_not_mutate_existing_score():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=50,
            decision_coverage_percent=100,
        )
    )

    result = preview_governed_residual_risk(
        inherent_risk=80,
        external_risk=70,
        existing_residual_risk=55,
        guarded_effectiveness=guarded,
    )

    assert (
        result.existing_residual_risk
        == 55.0
    )

    assert (
        result.preview_residual_risk
        != result.existing_residual_risk
    )


def test_score_delta_is_explainable():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=100,
        )
    )

    result = preview_governed_residual_risk(
        inherent_risk=80,
        external_risk=70,
        existing_residual_risk=66,
        guarded_effectiveness=guarded,
    )

    assert (
        result.score_delta
        == (
            result.preview_residual_risk
            - result.existing_residual_risk
        )
    )


def test_preview_exposes_rating():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=70,
            decision_coverage_percent=100,
        )
    )

    result = preview_governed_residual_risk(
        inherent_risk=80,
        external_risk=70,
        existing_residual_risk=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.preview_rating
        == "High"
    )


def test_policy_version():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=60,
            decision_coverage_percent=14,
        )
    )

    result = preview_governed_residual_risk(
        inherent_risk=80,
        external_risk=70,
        existing_residual_risk=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.policy_version
        == GOVERNED_RESIDUAL_RISK_POLICY_VERSION
    )

    assert (
        result.policy_version
        == "GRR-1.0"
    )