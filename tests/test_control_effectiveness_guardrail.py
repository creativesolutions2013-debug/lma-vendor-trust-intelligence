from src.control_effectiveness_guardrail import (
    CONTROL_EFFECTIVENESS_GUARDRAIL_VERSION,
    select_control_effectiveness_input,
)


def test_missing_governed_score_uses_legacy():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=None,
            decision_coverage_percent=0,
        )
    )

    assert (
        result.effective_control_input
        == 70.0
    )

    assert (
        result.mode
        == "Legacy"
    )


def test_low_coverage_does_not_influence_residual_risk():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=30,
            decision_coverage_percent=14,
        )
    )

    assert (
        result.effective_control_input
        == 70.0
    )

    assert (
        result.governed_weight
        == 0.0
    )

    assert (
        result.mode
        == "Coverage Guardrail"
    )


def test_50_percent_coverage_blends_evenly():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=50,
        )
    )

    assert (
        result.effective_control_input
        == 70.0
    )

    assert (
        result.governed_weight
        == 0.5
    )

    assert (
        result.legacy_weight
        == 0.5
    )

    assert (
        result.mode
        == "Blended"
    )


def test_79_percent_coverage_still_blends():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=40,
            decision_coverage_percent=79,
        )
    )

    assert (
        result.effective_control_input
        == 60.0
    )

    assert (
        result.mode
        == "Blended"
    )


def test_80_percent_coverage_uses_governed_score():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=80,
        )
    )

    assert (
        result.effective_control_input
        == 60.0
    )

    assert (
        result.governed_weight
        == 1.0
    )

    assert (
        result.mode
        == "Governed"
    )


def test_100_percent_coverage_uses_governed_score():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=90,
            governed_effectiveness=55,
            decision_coverage_percent=100,
        )
    )

    assert (
        result.effective_control_input
        == 55.0
    )

    assert (
        result.mode
        == "Governed"
    )


def test_values_are_bounded():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=150,
            governed_effectiveness=-20,
            decision_coverage_percent=100,
        )
    )

    assert (
        result.legacy_effectiveness
        == 100.0
    )

    assert (
        result.governed_effectiveness
        == 0.0
    )

    assert (
        result.effective_control_input
        == 0.0
    )


def test_coverage_is_bounded():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=60,
            decision_coverage_percent=150,
        )
    )

    assert (
        result.decision_coverage_percent
        == 100
    )

    assert (
        result.mode
        == "Governed"
    )


def test_policy_version():
    result = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=60,
            decision_coverage_percent=14,
        )
    )

    assert (
        result.policy_version
        == CONTROL_EFFECTIVENESS_GUARDRAIL_VERSION
    )

    assert (
        result.policy_version
        == "CEG-1.0"
    )