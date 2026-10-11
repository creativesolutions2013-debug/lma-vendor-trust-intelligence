import json

from src.audit import record_audit_event
from src.authz import (
    PERMISSION_ASSESSMENT_MANAGE,
    Principal,
    require,
)
from src.db import (
    ResidualRiskActivationRecord,
)
from src.residual_risk_activation import (
    ResidualRiskActivationDecision,
)
from src.residual_risk_reconciliation import (
    ResidualRiskReconciliation,
)


def _serialize_json(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def save_residual_risk_activation_review(
    session,
    *,
    vendor_id: int,
    assessment_id: int,
    reconciliation: ResidualRiskReconciliation,
    decision: ResidualRiskActivationDecision,
    principal: Principal,
    rationale: str,
) -> ResidualRiskActivationRecord:
    """
    Persist a human-reviewed residual-risk activation decision.

    Important:
    This records the review and policy lineage only.

    It does NOT modify the vendor's authoritative residual-risk
    score. Authoritative activation must be handled separately.
    """

    require(
        principal,
        PERMISSION_ASSESSMENT_MANAGE,
    )

    normalized_rationale = (
        rationale
        or ""
    ).strip()

    if not normalized_rationale:
        raise ValueError(
            "Residual risk activation review requires "
            "an analyst rationale."
        )

    if (
        decision.reconciliation_policy_version
        != reconciliation.policy_version
    ):
        raise ValueError(
            "Activation decision reconciliation policy "
            "does not match the supplied reconciliation."
        )

    if (
        abs(
            decision.governed_residual_risk
            - reconciliation.governed_preview_risk
        )
        > 0.01
    ):
        raise ValueError(
            "Activation decision risk does not match "
            "the governed reconciliation preview."
        )

    if (
        decision.analyst_approved
        and not decision.activation_eligible
    ):
        raise ValueError(
            "An analyst-approved activation must be "
            "eligible under RRA policy."
        )

    record = ResidualRiskActivationRecord(
        vendor_id=vendor_id,
        assessment_id=assessment_id,
        stored_residual_risk=(
            reconciliation.stored_residual_risk
        ),
        fresh_baseline_risk=(
            reconciliation.fresh_baseline_risk
        ),
        proposed_residual_risk=(
            reconciliation.governed_preview_risk
        ),
        stored_to_baseline_delta=(
            reconciliation.stored_to_baseline_delta
        ),
        governed_contribution_delta=(
            reconciliation.governed_contribution_delta
        ),
        stored_to_governed_delta=(
            reconciliation.stored_to_governed_delta
        ),
        governed_rating=(
            decision.governed_rating
        ),
        control_input_mode=(
            decision.control_input_mode
        ),
        decision_status=(
            decision.status
        ),
        system_ready=(
            decision.system_ready
        ),
        analyst_approved=(
            decision.analyst_approved
        ),
        activation_eligible=(
            decision.activation_eligible
        ),
        blocking_reasons_json=(
            _serialize_json(
                list(
                    decision.blocking_reasons
                )
            )
        ),
        analyst_subject=(
            principal.subject
        ),
        analyst_name=(
            principal.display_name
        ),
        analyst_email=(
            principal.email
        ),
        analyst_role=(
            principal.role
        ),
        rationale=(
            normalized_rationale
        ),
        activation_policy_version=(
            decision.policy_version
        ),
        reconciliation_policy_version=(
            decision.reconciliation_policy_version
        ),
        residual_risk_policy_version=(
            decision.residual_risk_policy_version
        ),
    )

    session.add(record)
    session.flush()

    record_audit_event(
        session,
        principal=principal,
        action="residual_risk_activation.review",
        object_type="residual_risk_activation",
        object_id=record.id,
        vendor_id=vendor_id,
        details={
            "assessment_id": assessment_id,
            "stored_residual_risk": (
                reconciliation.stored_residual_risk
            ),
            "fresh_baseline_risk": (
                reconciliation.fresh_baseline_risk
            ),
            "proposed_residual_risk": (
                reconciliation.governed_preview_risk
            ),
            "stored_to_baseline_delta": (
                reconciliation.stored_to_baseline_delta
            ),
            "governed_contribution_delta": (
                reconciliation.governed_contribution_delta
            ),
            "stored_to_governed_delta": (
                reconciliation.stored_to_governed_delta
            ),
            "decision_status": (
                decision.status
            ),
            "system_ready": (
                decision.system_ready
            ),
            "analyst_approved": (
                decision.analyst_approved
            ),
            "activation_eligible": (
                decision.activation_eligible
            ),
            "blocking_reasons": list(
                decision.blocking_reasons
            ),
            "activation_policy_version": (
                decision.policy_version
            ),
            "reconciliation_policy_version": (
                decision.reconciliation_policy_version
            ),
            "residual_risk_policy_version": (
                decision.residual_risk_policy_version
            ),
            "rationale": (
                normalized_rationale
            ),
        },
        dedupe_window_seconds=0,
    )

    return record
