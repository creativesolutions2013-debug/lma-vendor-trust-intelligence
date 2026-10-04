from src.scoring import (
    ResidualRiskContext,
    calculate_residual_risk,
    evaluate_residual_risk,
    external_risk_adjustment,
)


def test_residual_risk_v2_formula():
    """
    Inherent Risk = 80
    Control Effectiveness = 70
    Control Deficiency = 30

    Base =
        (80 × .60) + (30 × .40)
        = 48 + 12
        = 60

    External Risk 70 = +10

    Final = 70
    """

    result = calculate_residual_risk(
        inherent_risk=80,
        control_effectiveness=70,
        external_risk=70,
    )

    assert result == 70.0


def test_external_risk_adjustments():
    assert external_risk_adjustment(10) == -5
    assert external_risk_adjustment(25) == 0
    assert external_risk_adjustment(55) == 5
    assert external_risk_adjustment(70) == 10
    assert external_risk_adjustment(90) == 20


def test_score_is_capped_at_100():
    result = calculate_residual_risk(
        inherent_risk=100,
        control_effectiveness=0,
        external_risk=100,
    )

    assert result == 100.0


def test_score_is_not_negative():
    result = calculate_residual_risk(
        inherent_risk=0,
        control_effectiveness=100,
        external_risk=0,
    )

    assert result == 0.0


def test_privileged_access_without_mfa_forces_high():
    decision = evaluate_residual_risk(
        inherent_risk=40,
        control_effectiveness=90,
        external_risk=25,
        context=ResidualRiskContext(
            privileged_access_without_mfa=True
        ),
    )

    assert decision.calculated_rating == "Moderate"
    assert decision.final_rating == "High"
    assert decision.approval_blocked is True
    assert decision.escalation_required is True

    assert (
        "PRIVILEGED_ACCESS_WITHOUT_MFA"
        in decision.triggered_guardrails
    )


def test_active_critical_incident_forces_critical():
    decision = evaluate_residual_risk(
        inherent_risk=30,
        control_effectiveness=95,
        external_risk=25,
        context=ResidualRiskContext(
            active_critical_incident=True
        ),
    )

    assert decision.final_rating == "Critical"
    assert decision.approval_blocked is True
    assert decision.escalation_required is True


def test_expired_evidence_blocks_approval():
    decision = evaluate_residual_risk(
        inherent_risk=40,
        control_effectiveness=80,
        external_risk=25,
        context=ResidualRiskContext(
            required_evidence_expired=True
        ),
    )

    assert decision.approval_blocked is True

    assert (
        "REQUIRED_EVIDENCE_EXPIRED"
        in decision.triggered_guardrails
    )


def test_incomplete_assessment_blocks_approval():
    decision = evaluate_residual_risk(
        inherent_risk=40,
        control_effectiveness=80,
        external_risk=25,
        context=ResidualRiskContext(
            assessment_complete=False
        ),
    )

    assert decision.approval_blocked is True

    assert (
        "ASSESSMENT_INCOMPLETE"
        in decision.triggered_guardrails
    )