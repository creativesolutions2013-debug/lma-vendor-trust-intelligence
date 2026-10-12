from dataclasses import dataclass

from src.control_effectiveness import (
    evaluate_control_effectiveness,
)
from src.residual_risk_activation_validity import (
    RESIDUAL_RISK_ACTIVATION_VALIDITY_POLICY_VERSION,
    STATUS_CHALLENGED,
    STATUS_NOT_ACTIVATED,
    STATUS_REVALIDATION_REQUIRED,
    STATUS_VALID,
    evaluate_residual_risk_activation_validity,
)


@dataclass
class DispositionStub:
    id: int
    control_id: str
    final_disposition: str
    decided_at: int
    claim_basis_verified: bool = True


@dataclass
class ExecutionStub:
    activated_residual_risk: float = 25.0
    execution_policy_version: str = "RAE-1.0"
    activation_policy_version: str = "RRA-1.0"
    reconciliation_policy_version: str = "RRR-1.0"
    residual_risk_policy_version: str = "RR-2.0"


def governed_effectiveness():
    return evaluate_control_effectiveness(
        (
            "GOV-01",
            "IAM-01",
            "IR-01",
        ),
        (
            DispositionStub(
                id=1,
                control_id="GOV-01",
                final_disposition="Satisfied",
                decided_at=1,
            ),
            DispositionStub(
                id=2,
                control_id="IAM-01",
                final_disposition="Satisfied",
                decided_at=2,
            ),
            DispositionStub(
                id=3,
                control_id="IR-01",
                final_disposition="Satisfied",
                decided_at=3,
            ),
        ),
    )


def ungoverned_effectiveness():
    return evaluate_control_effectiveness(
        (
            "GOV-01",
            "IAM-01",
            "IR-01",
        ),
        (),
    )


def test_no_activation_returns_not_activated():
    result = (
        evaluate_residual_risk_activation_validity(
            latest_execution=None,
            current_authoritative_risk=25,
            control_effectiveness=(
                governed_effectiveness()
            ),
            assessment_complete=True,
        )
    )

    assert result.status == STATUS_NOT_ACTIVATED
    assert result.valid is False
    assert result.revalidation_required is False


def test_valid_activation_remains_valid():
    result = (
        evaluate_residual_risk_activation_validity(
            latest_execution=ExecutionStub(),
            current_authoritative_risk=25,
            control_effectiveness=(
                governed_effectiveness()
            ),
            assessment_complete=True,
        )
    )

    assert result.status == STATUS_VALID
    assert result.valid is True
    assert result.revalidation_required is False
    assert result.reasons == ()


def test_loss_of_governed_effectiveness_requires_revalidation():
    result = (
        evaluate_residual_risk_activation_validity(
            latest_execution=ExecutionStub(),
            current_authoritative_risk=25,
            control_effectiveness=(
                ungoverned_effectiveness()
            ),
            assessment_complete=True,
        )
    )

    assert (
        result.status
        == STATUS_REVALIDATION_REQUIRED
    )

    assert (
        "GOVERNED_EFFECTIVENESS_UNAVAILABLE"
        in result.reasons
    )

    assert (
        "GOVERNED_DECISION_COVERAGE_BELOW_THRESHOLD"
        in result.reasons
    )


def test_incomplete_assessment_requires_revalidation():
    result = (
        evaluate_residual_risk_activation_validity(
            latest_execution=ExecutionStub(),
            current_authoritative_risk=25,
            control_effectiveness=(
                governed_effectiveness()
            ),
            assessment_complete=False,
        )
    )

    assert (
        result.status
        == STATUS_REVALIDATION_REQUIRED
    )

    assert (
        "ASSESSMENT_NOT_COMPLETE"
        in result.reasons
    )


def test_authoritative_score_change_challenges_activation():
    result = (
        evaluate_residual_risk_activation_validity(
            latest_execution=ExecutionStub(),
            current_authoritative_risk=40,
            control_effectiveness=(
                governed_effectiveness()
            ),
            assessment_complete=True,
        )
    )

    assert result.status == STATUS_CHALLENGED
    assert result.challenged is True

    assert (
        "AUTHORITATIVE_RISK_CHANGED_AFTER_ACTIVATION"
        in result.reasons
    )


def test_outdated_execution_policy_requires_revalidation():
    execution = ExecutionStub(
        execution_policy_version="RAE-0.9"
    )

    result = (
        evaluate_residual_risk_activation_validity(
            latest_execution=execution,
            current_authoritative_risk=25,
            control_effectiveness=(
                governed_effectiveness()
            ),
            assessment_complete=True,
        )
    )

    assert (
        result.status
        == STATUS_REVALIDATION_REQUIRED
    )

    assert (
        "EXECUTION_POLICY_VERSION_OUTDATED"
        in result.reasons
    )


def test_outdated_risk_policy_requires_revalidation():
    execution = ExecutionStub(
        residual_risk_policy_version="RR-1.0"
    )

    result = (
        evaluate_residual_risk_activation_validity(
            latest_execution=execution,
            current_authoritative_risk=25,
            control_effectiveness=(
                governed_effectiveness()
            ),
            assessment_complete=True,
        )
    )

    assert (
        "RESIDUAL_RISK_POLICY_VERSION_OUTDATED"
        in result.reasons
    )


def test_policy_version():
    result = (
        evaluate_residual_risk_activation_validity(
            latest_execution=None,
            current_authoritative_risk=25,
            control_effectiveness=(
                governed_effectiveness()
            ),
            assessment_complete=True,
        )
    )

    assert (
        result.policy_version
        == RESIDUAL_RISK_ACTIVATION_VALIDITY_POLICY_VERSION
    )

    assert result.policy_version == "RAV-1.0"
