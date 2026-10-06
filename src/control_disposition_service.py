import json

from src.audit import record_audit_event
from src.authz import (
    PERMISSION_ASSESSMENT_MANAGE,
    Principal,
    require,
)
from src.control_disposition import (
    ControlDispositionDecision,
)
from src.db import ControlDispositionRecord


def _serialize_json(
    value,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def save_control_disposition(
    session,
    *,
    vendor_id: int,
    assessment_id: int,
    sufficiency_status: str,
    decision: ControlDispositionDecision,
    principal: Principal,
    orchestrator_policy_version: str | None = None,
) -> ControlDispositionRecord:
    """
    Persist a human-confirmed control disposition and write
    a corresponding audit event.

    This service intentionally persists only analyst-confirmed
    decisions. Automated recommendations remain recommendations
    until a human reviewer accepts or overrides them.

    The caller owns transaction commit/rollback.
    """

    require(
        principal,
        PERMISSION_ASSESSMENT_MANAGE,
    )

    if not decision.human_confirmed:
        raise ValueError(
            "Only human-confirmed control dispositions "
            "may be persisted."
        )

    if not decision.decision_rationale:
        raise ValueError(
            "A persisted control disposition requires "
            "an analyst rationale."
        )

    normalized_status = (
        sufficiency_status
        or ""
    ).strip()

    if not normalized_status:
        raise ValueError(
            "sufficiency_status is required."
        )

    record = ControlDispositionRecord(
        vendor_id=vendor_id,
        assessment_id=assessment_id,
        control_id=decision.control_id,
        sufficiency_status=normalized_status,
        system_recommendation=(
            decision.recommended_disposition
        ),
        final_disposition=(
            decision.final_disposition
        ),
        supporting_evidence_ids_json=(
            _serialize_json(
                list(
                    decision.supporting_evidence_ids
                )
            )
        ),
        review_evidence_ids_json=(
            _serialize_json(
                list(
                    decision.review_evidence_ids
                )
            )
        ),
        system_reasons_json=(
            _serialize_json(
                list(
                    decision.reasons
                )
            )
        ),
        analyst_subject=principal.subject,
        analyst_name=principal.display_name,
        analyst_email=principal.email,
        analyst_role=principal.role,
        rationale=decision.decision_rationale,
        compensating_control=(
            decision.compensating_control
        ),
        disposition_policy_version=(
            decision.policy_version
        ),
        orchestrator_policy_version=(
            orchestrator_policy_version
        ),
    )

    session.add(
        record
    )

    session.flush()

    record_audit_event(
        session,
        principal=principal,
        action="control_disposition.record",
        object_type="control_disposition",
        object_id=record.id,
        vendor_id=vendor_id,
        details={
            "assessment_id": assessment_id,
            "control_id": decision.control_id,
            "sufficiency_status": (
                normalized_status
            ),
            "system_recommendation": (
                decision.recommended_disposition
            ),
            "final_disposition": (
                decision.final_disposition
            ),
            "supporting_evidence_ids": list(
                decision.supporting_evidence_ids
            ),
            "review_evidence_ids": list(
                decision.review_evidence_ids
            ),
            "disposition_policy_version": (
                decision.policy_version
            ),
            "orchestrator_policy_version": (
                orchestrator_policy_version
            ),
            "rationale": (
                decision.decision_rationale
            ),
            "compensating_control": (
                decision.compensating_control
            ),
        },
        dedupe_window_seconds=0,
    )

    return record