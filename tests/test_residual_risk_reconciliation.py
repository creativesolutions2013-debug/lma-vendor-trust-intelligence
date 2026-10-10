from src.control_effectiveness_guardrail import (
    select_control_effectiveness_input,
)
from src.residual_risk_reconciliation import (
    RESIDUAL_RISK_RECONCILIATION_POLICY_VERSION,
    reconcile_residual_risk,
)


def test_no_drift_when_stored_matches_fresh_baseline():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=40,
            decision_coverage_percent=14,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=70,
        legacy_effectiveness=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.fresh_baseline_risk
        == 70.0
    )

    assert (
        result.stored_to_baseline_delta
        == 0.0
    )

    assert (
        result.drift_detected
        is False
    )


def test_stored_score_drift_is_detected():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=40,
            decision_coverage_percent=14,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=64,
        legacy_effectiveness=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.fresh_baseline_risk
        == 70.0
    )

    assert (
        result.stored_to_baseline_delta
        == 6.0
    )

    assert (
        result.drift_detected
        is True
    )


def test_low_coverage_has_zero_governed_contribution():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=40,
            decision_coverage_percent=14,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=64,
        legacy_effectiveness=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.control_input_mode
        == "Coverage Guardrail"
    )

    assert (
        result.governed_contribution_delta
        == 0.0
    )

    assert (
        result.governed_preview_risk
        == result.fresh_baseline_risk
    )


def test_blended_mode_separates_governed_contribution():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=60,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=66,
        legacy_effectiveness=80,
        guarded_effectiveness=guarded,
    )

    assert (
        result.control_input_mode
        == "Blended"
    )

    assert (
        result.effective_control_input
        == 70.0
    )

    assert (
        result.governed_contribution_delta
        > 0
    )


def test_governed_mode_is_activation_ready():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=100,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=66,
        legacy_effectiveness=80,
        guarded_effectiveness=guarded,
    )

    assert (
        result.control_input_mode
        == "Governed"
    )

    assert (
        result.activation_ready
        is True
    )


def test_total_delta_reconciles():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=100,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=60,
        legacy_effectiveness=80,
        guarded_effectiveness=guarded,
    )

    assert (
        result.stored_to_governed_delta
        == round(
            result.stored_to_baseline_delta
            + result.governed_contribution_delta,
            1,
        )
    )


def test_ratings_are_exposed():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=70,
            decision_coverage_percent=100,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=70,
        legacy_effectiveness=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.stored_rating
        == "High"
    )

    assert (
        result.baseline_rating
        == "High"
    )

    assert (
        result.governed_rating
        == "High"
    )


def test_stored_score_is_bounded():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=70,
            decision_coverage_percent=100,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=150,
        legacy_effectiveness=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.stored_residual_risk
        == 100.0
    )


def test_policy_version():
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=70,
            governed_effectiveness=60,
            decision_coverage_percent=14,
        )
    )

    result = reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=70,
        legacy_effectiveness=70,
        guarded_effectiveness=guarded,
    )

    assert (
        result.policy_version
        == RESIDUAL_RISK_RECONCILIATION_POLICY_VERSION
    )

    assert (
        result.policy_version
        == "RRR-1.0"
    )
