import json

from src.audit import record_audit_event
from src.authz import (
    PERMISSION_ASSESSMENT_MANAGE,
    Principal,
    require,
)
from src.db import (
    Assessment,
    RevalidationCaseRecord,
    ResidualRiskActivationExecution,
)
from src.revalidation_case import (
    REVALIDATION_CASE_POLICY_VERSION,
    STATUS_OPEN,
    RevalidationCaseSnapshot,
)
from src.residual_risk_activation_validity import (
    RESIDUAL_RISK_ACTIVATION_VALIDITY_POLICY_VERSION,
)


def open_revalidation_case(
    session,
    *,
    vendor_id: int,
    assessment_id: int,
    snapshot: RevalidationCaseSnapshot,
    principal: Principal,
    rationale: str,
) -> RevalidationCaseRecord:
    """
    Persist a governed residual-risk revalidation case.

    This service records workflow state only.

    It does not:
    - alter the authoritative residual-risk score
    - change assessment status
    - create or alter evidence
    - alter control claims or dispositions
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
            "Opening a revalidation case requires a rationale."
        )

    if snapshot.status != STATUS_OPEN:
        raise ValueError(
            "A new revalidation case must begin in Open status."
        )

    if (
        snapshot.policy_version
        != REVALIDATION_CASE_POLICY_VERSION
    ):
        raise ValueError(
            "Revalidation snapshot uses an outdated RVC policy."
        )

    if (
        snapshot.rav_policy_version
        != RESIDUAL_RISK_ACTIVATION_VALIDITY_POLICY_VERSION
    ):
        raise ValueError(
            "Revalidation snapshot uses an outdated RAV policy."
        )

    assessment = (
        session.query(Assessment)
        .filter_by(
            id=assessment_id,
            vendor_id=vendor_id,
        )
        .one_or_none()
    )

    if assessment is None:
        raise ValueError(
            "Revalidation assessment does not match the vendor."
        )

    execution = (
        session.query(
            ResidualRiskActivationExecution
        )
        .filter_by(
            id=snapshot.activation_execution_id,
            vendor_id=vendor_id,
            assessment_id=assessment_id,
        )
        .one_or_none()
    )

    if execution is None:
        raise ValueError(
            "Revalidation activation execution does not "
            "match the vendor and assessment."
        )

    existing = (
        session.query(
            RevalidationCaseRecord
        )
        .filter_by(
            activation_execution_id=execution.id
        )
        .one_or_none()
    )

    if existing is not None:
        raise ValueError(
            "A revalidation case already exists for "
            "this activation execution."
        )

    record = RevalidationCaseRecord(
        vendor_id=vendor_id,
        assessment_id=assessment_id,
        activation_execution_id=execution.id,
        status=snapshot.status,
        trigger_status=snapshot.trigger_status,
        trigger_reasons_json=json.dumps(
            list(snapshot.trigger_reasons),
            ensure_ascii=False,
        ),
        activated_residual_risk=(
            snapshot.activated_residual_risk
        ),
        current_authoritative_risk=(
            snapshot.current_authoritative_risk
        ),
        decision_coverage_percent=(
            snapshot.decision_coverage_percent
        ),
        control_effectiveness_status=(
            snapshot.control_effectiveness_status
        ),
        rav_policy_version=(
            snapshot.rav_policy_version
        ),
        revalidation_policy_version=(
            snapshot.policy_version
        ),
        opened_by_subject=(
            principal.subject
        ),
        opened_by_name=(
            principal.display_name
        ),
        opened_by_email=(
            principal.email
        ),
        opened_by_role=(
            principal.role
        ),
        opening_rationale=(
            normalized_rationale
        ),
    )

    session.add(record)
    session.flush()

    record_audit_event(
        session,
        principal=principal,
        action="residual_risk_revalidation.open",
        object_type="revalidation_case",
        object_id=record.id,
        vendor_id=vendor_id,
        details={
            "assessment_id": assessment_id,
            "activation_execution_id": execution.id,
            "status": record.status,
            "trigger_status": record.trigger_status,
            "trigger_reasons": list(
                snapshot.trigger_reasons
            ),
            "activated_residual_risk": (
                snapshot.activated_residual_risk
            ),
            "current_authoritative_risk": (
                snapshot.current_authoritative_risk
            ),
            "decision_coverage_percent": (
                snapshot.decision_coverage_percent
            ),
            "control_effectiveness_status": (
                snapshot.control_effectiveness_status
            ),
            "rav_policy_version": (
                snapshot.rav_policy_version
            ),
            "revalidation_policy_version": (
                snapshot.policy_version
            ),
            "opening_rationale": (
                normalized_rationale
            ),
        },
        dedupe_window_seconds=0,
    )

    return record
