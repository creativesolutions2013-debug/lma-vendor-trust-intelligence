from dataclasses import dataclass

import pytest

from src.residual_risk_activation_validity import (
    ResidualRiskActivationValidity,
)
from src.revalidation_case import (
    REVALIDATION_CASE_POLICY_VERSION,
    STATUS_OPEN,
    build_revalidation_case_snapshot,
)


@dataclass
class ExecutionStub:
    id: int = 44


def validity(
    *,
    status="Revalidation Required",
    revalidation_required=True,
    reasons=(
        "GOVERNED_EFFECTIVENESS_UNAVAILABLE",
        "GOVERNED_DECISION_COVERAGE_BELOW_THRESHOLD",
    ),
    activated_residual_risk=5.8,
):
    return ResidualRiskActivationValidity(
        status=status,
        valid=False,
        revalidation_required=revalidation_required,
        challenged=False,
        reasons=reasons,
        activated_residual_risk=activated_residual_risk,
        current_authoritative_risk=5.8,
        decision_coverage_percent=0,
        control_effectiveness_status="Insufficient Decisions",
    )


def test_builds_open_case_from_rav_revalidation():
    snapshot = build_revalidation_case_snapshot(
        validity=validity(),
        latest_execution=ExecutionStub(),
    )

    assert snapshot.status == STATUS_OPEN
    assert snapshot.activation_execution_id == 44
    assert snapshot.activated_residual_risk == 5.8
    assert snapshot.current_authoritative_risk == 5.8
    assert snapshot.decision_coverage_percent == 0
    assert snapshot.rav_policy_version == "RAV-1.0"
    assert snapshot.policy_version == REVALIDATION_CASE_POLICY_VERSION


def test_preserves_rav_trigger_reasons():
    snapshot = build_revalidation_case_snapshot(
        validity=validity(),
        latest_execution=ExecutionStub(),
    )

    assert snapshot.trigger_reasons == (
        "GOVERNED_EFFECTIVENESS_UNAVAILABLE",
        "GOVERNED_DECISION_COVERAGE_BELOW_THRESHOLD",
    )


def test_deduplicates_trigger_reasons():
    snapshot = build_revalidation_case_snapshot(
        validity=validity(
            reasons=(
                "CONTROL_EFFECTIVENESS_NOT_GOVERNED",
                "CONTROL_EFFECTIVENESS_NOT_GOVERNED",
            )
        ),
        latest_execution=ExecutionStub(),
    )

    assert snapshot.trigger_reasons == (
        "CONTROL_EFFECTIVENESS_NOT_GOVERNED",
    )


def test_rejects_case_when_rav_does_not_require_revalidation():
    with pytest.raises(
        ValueError,
        match="RAV requires revalidation",
    ):
        build_revalidation_case_snapshot(
            validity=validity(
                status="Valid",
                revalidation_required=False,
            ),
            latest_execution=ExecutionStub(),
        )


def test_rejects_case_without_prior_activation():
    with pytest.raises(
        ValueError,
        match="prior controlled",
    ):
        build_revalidation_case_snapshot(
            validity=validity(),
            latest_execution=None,
        )


def test_rejects_case_without_trigger_reasons():
    with pytest.raises(
        ValueError,
        match="trigger reason",
    ):
        build_revalidation_case_snapshot(
            validity=validity(
                reasons=(),
            ),
            latest_execution=ExecutionStub(),
        )


def test_rejects_case_without_activation_risk():
    with pytest.raises(
        ValueError,
        match="activated residual-risk",
    ):
        build_revalidation_case_snapshot(
            validity=validity(
                activated_residual_risk=None,
            ),
            latest_execution=ExecutionStub(),
        )


def test_rejects_unpersisted_activation_execution():
    @dataclass
    class UnpersistedExecution:
        id: int | None = None

    with pytest.raises(
        ValueError,
        match="persistent execution identifier",
    ):
        build_revalidation_case_snapshot(
            validity=validity(),
            latest_execution=UnpersistedExecution(),
        )
