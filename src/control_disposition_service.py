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
from src.control_disposition_basis import (
    evaluate_control_disposition_basis,
)
from src.db import (
    ControlDispositionRecord,
)


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
    allow_unbacked_admin_override: bool = False,
    basis_override_reason: str | None = None,
) -> ControlDispositionRecord:
    """
    Persist one human-confirmed control disposition.

    CBE-1.0 requires the disposition to be traceable to a
    current accepted human-confirmed evidence-to-control claim.

    Only an explicit Admin override may bypass claim-backed
    enforcement.

    Caller owns commit / rollback.
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

    disposition_evidence_ids = tuple(
        dict.fromkeys(
            tuple(
                decision.supporting_evidence_ids
            )
            + tuple(
                decision.review_evidence_ids
            )
        )
    )

    basis = (
        evaluate_control_disposition_basis(
            session,
            vendor_id=vendor_id,
            assessment_id=assessment_id,
            control_id=decision.control_id,
            evidence_ids=(
                disposition_evidence_ids
            ),
            principal=principal,
            allow_admin_override=(
                allow_unbacked_admin_override
            ),
            override_reason=(
                basis_override_reason
            ),
        )
    )

    if not basis.verified:
        raise ValueError(
            "Control disposition is not backed by an "
            f"accepted governed claim. {basis.reason}"
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
        claim_basis_verified=True,
        claim_basis_mode=(
            basis.mode
        ),
        claim_basis_record_ids_json=(
            _serialize_json(
                list(
                    basis.claim_record_ids
                )
            )
        ),
        claim_basis_evidence_ids_json=(
            _serialize_json(
                list(
                    basis.evidence_ids
                )
            )
        ),
        claim_basis_override_reason=(
            basis.override_reason
        ),
        claim_basis_policy_version=(
            basis.policy_version
        ),
    )

    session.add(record)
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
            "claim_basis_verified": True,
            "claim_basis_mode": (
                basis.mode
            ),
            "claim_basis_record_ids": list(
                basis.claim_record_ids
            ),
            "claim_basis_evidence_ids": list(
                basis.evidence_ids
            ),
            "claim_basis_policy_version": (
                basis.policy_version
            ),
            "claim_basis_override_reason": (
                basis.override_reason
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
