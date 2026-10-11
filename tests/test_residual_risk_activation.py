from src.control_effectiveness_guardrail import (
    select_control_effectiveness_input,
)
from src.residual_risk_activation import (
    RESIDUAL_RISK_ACTIVATION_POLICY_VERSION,
    STATUS_AWAITING_APPROVAL,
    STATUS_BLOCKED,
    STATUS_ELIGIBLE,
    evaluate_residual_risk_activation,
)
from src.residual_risk_reconciliation import (
    reconcile_residual_risk,
)
from src.scoring import (
    ResidualRiskContext,
    evaluate_residual_risk,
)


def _build_reconciliation(
    *,
    coverage: float,
):
    guarded = (
        select_control_effectiveness_input(
            legacy_effectiveness=80,
            governed_effectiveness=60,
            decision_coverage_percent=coverage,
        )
    )

    return reconcile_residual_risk(
        inherent_risk=80,
        external_risk=70,
        stored_residual_risk=66,
        legacy_effectiveness=80,
        guarded_effectiveness=guarded,
    )


def _build_risk_decision(
    *,
    control_effectiveness: float = 60,
    context=None,
):
    return evaluate_residual_risk(
        inherent_risk=80,
        control_effectiveness=(
            control_effectiveness
        ),
        external_risk=70,
        context=context,
    )


def test_low_coverage_blocks_activation():
    reconciliation = (
        _build_reconciliation(
            coverage=14,
        )
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                _build_risk_decision()
            ),
        )
    )

    assert decision.system_ready is False
    assert decision.activation_eligible is False
    assert decision.status == STATUS_BLOCKED

    assert (
        "GOVERNED_COVERAGE_INSUFFICIENT"
        in decision.blocking_reasons
    )


def test_blended_mode_blocks_activation():
    reconciliation = (
        _build_reconciliation(
            coverage=60,
        )
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                _build_risk_decision()
            ),
        )
    )

    assert decision.system_ready is False

    assert (
        "GOVERNED_COVERAGE_INSUFFICIENT"
        in decision.blocking_reasons
    )


def test_governed_mode_waits_for_analyst():
    reconciliation = (
        _build_reconciliation(
            coverage=100,
        )
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                _build_risk_decision()
            ),
            analyst_approved=False,
        )
    )

    assert decision.system_ready is True
    assert decision.activation_eligible is False

    assert (
        decision.status
        == STATUS_AWAITING_APPROVAL
    )


def test_governed_mode_with_approval_is_eligible():
    reconciliation = (
        _build_reconciliation(
            coverage=100,
        )
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                _build_risk_decision()
            ),
            analyst_approved=True,
        )
    )

    assert decision.system_ready is True
    assert decision.analyst_approved is True
    assert decision.activation_eligible is True

    assert (
        decision.status
        == STATUS_ELIGIBLE
    )


def test_incomplete_lineage_blocks_activation():
    reconciliation = (
        _build_reconciliation(
            coverage=100,
        )
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                _build_risk_decision()
            ),
            inputs_traceable=False,
            analyst_approved=True,
        )
    )

    assert decision.activation_eligible is False

    assert (
        "INPUT_LINEAGE_INCOMPLETE"
        in decision.blocking_reasons
    )


def test_rr2_approval_guardrail_blocks_activation():
    reconciliation = (
        _build_reconciliation(
            coverage=100,
        )
    )

    risk_decision = (
        _build_risk_decision(
            context=ResidualRiskContext(
                required_evidence_expired=True,
            )
        )
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                risk_decision
            ),
            analyst_approved=True,
        )
    )

    assert decision.activation_eligible is False

    assert (
        "RR2_APPROVAL_BLOCKED"
        in decision.blocking_reasons
    )

    assert (
        "RR2_GUARDRAIL:"
        "REQUIRED_EVIDENCE_EXPIRED"
        in decision.blocking_reasons
    )


def test_rr2_escalation_blocks_activation():
    reconciliation = (
        _build_reconciliation(
            coverage=100,
        )
    )

    risk_decision = (
        _build_risk_decision(
            context=ResidualRiskContext(
                active_critical_incident=True,
            )
        )
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                risk_decision
            ),
            analyst_approved=True,
        )
    )

    assert decision.activation_eligible is False

    assert (
        "RR2_ESCALATION_REQUIRED"
        in decision.blocking_reasons
    )


def test_policy_lineage_is_exposed():
    reconciliation = (
        _build_reconciliation(
            coverage=100,
        )
    )

    risk_decision = (
        _build_risk_decision()
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                risk_decision
            ),
        )
    )

    assert (
        decision.policy_version
        == RESIDUAL_RISK_ACTIVATION_POLICY_VERSION
    )

    assert decision.policy_version == "RRA-1.0"

    assert (
        decision.reconciliation_policy_version
        == "RRR-1.0"
    )

    assert (
        decision.residual_risk_policy_version
        == "RR-2.0"
    )


def test_governed_result_is_carried_forward():
    reconciliation = (
        _build_reconciliation(
            coverage=100,
        )
    )

    risk_decision = (
        _build_risk_decision()
    )

    decision = (
        evaluate_residual_risk_activation(
            reconciliation=reconciliation,
            residual_risk_decision=(
                risk_decision
            ),
        )
    )

    assert (
        decision.governed_residual_risk
        == reconciliation.governed_preview_risk
    )

    assert (
        decision.governed_rating
        == risk_decision.final_rating
    )
