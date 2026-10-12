import json

from src.audit import record_audit_event
from src.authz import (
    PERMISSION_VENDOR_WRITE,
    Principal,
    require,
)
from src.db import (
    Assessment,
    ResidualRiskActivationExecution,
    ResidualRiskActivationRecord,
    Vendor,
)
from src.residual_risk_activation import (
    RESIDUAL_RISK_ACTIVATION_POLICY_VERSION,
)
from src.residual_risk_reconciliation import (
    RESIDUAL_RISK_RECONCILIATION_POLICY_VERSION,
)
from src.scoring import (
    RESIDUAL_RISK_POLICY_VERSION,
    rating_from_score,
)


RESIDUAL_RISK_ACTIVATION_EXECUTION_POLICY_VERSION = (
    "RAE-1.0"
)


def execute_residual_risk_activation(
    session,
    *,
    activation_review_id: int,
    principal: Principal,
    rationale: str,
) -> ResidualRiskActivationExecution:
    """
    Execute one previously approved residual-risk activation.

    Governance protections:

    - executor requires vendor.write
    - review must already be system-ready
    - review must already be analyst-approved
    - review must already be activation-eligible
    - no blocking reasons may remain
    - policy lineage must still be current
    - authoritative vendor score must still match the score
      captured when the review occurred
    - each review may be executed only once

    Caller owns transaction commit / rollback.
    """

    require(
        principal,
        PERMISSION_VENDOR_WRITE,
    )

    normalized_rationale = (
        rationale
        or ""
    ).strip()

    if not normalized_rationale:
        raise ValueError(
            "Activation execution requires a rationale."
        )

    review = (
        session.query(
            ResidualRiskActivationRecord
        )
        .filter_by(
            id=activation_review_id
        )
        .one_or_none()
    )

    if review is None:
        raise ValueError(
            "Activation review was not found."
        )

    existing_execution = (
        session.query(
            ResidualRiskActivationExecution
        )
        .filter_by(
            activation_review_id=review.id
        )
        .first()
    )

    if existing_execution is not None:
        raise ValueError(
            "This activation review has already been executed."
        )

    if not review.system_ready:
        raise ValueError(
            "Activation review is not system-ready."
        )

    if not review.analyst_approved:
        raise ValueError(
            "Activation review has not been analyst-approved."
        )

    if not review.activation_eligible:
        raise ValueError(
            "Activation review is not eligible for activation."
        )

    blocking_reasons = json.loads(
        review.blocking_reasons_json
        or "[]"
    )

    if blocking_reasons:
        raise ValueError(
            "Activation review still contains blocking reasons."
        )

    if (
        review.control_input_mode
        != "Governed"
    ):
        raise ValueError(
            "Only a fully governed control input may be activated."
        )

    if (
        review.activation_policy_version
        != RESIDUAL_RISK_ACTIVATION_POLICY_VERSION
    ):
        raise ValueError(
            "Activation review uses an outdated RRA policy."
        )

    if (
        review.reconciliation_policy_version
        != RESIDUAL_RISK_RECONCILIATION_POLICY_VERSION
    ):
        raise ValueError(
            "Activation review uses an outdated reconciliation policy."
        )

    if (
        review.residual_risk_policy_version
        != RESIDUAL_RISK_POLICY_VERSION
    ):
        raise ValueError(
            "Activation review uses an outdated residual-risk policy."
        )

    vendor = (
        session.query(Vendor)
        .filter_by(
            id=review.vendor_id
        )
        .one_or_none()
    )

    if vendor is None:
        raise ValueError(
            "Vendor for activation review was not found."
        )

    assessment = (
        session.query(Assessment)
        .filter_by(
            id=review.assessment_id,
            vendor_id=review.vendor_id,
        )
        .one_or_none()
    )

    if assessment is None:
        raise ValueError(
            "Activation review assessment does not match the vendor."
        )

    current_score = float(
        vendor.residual_risk_score
        or 0
    )

    reviewed_score = float(
        review.stored_residual_risk
    )

    if abs(
        current_score
        - reviewed_score
    ) > 0.01:
        raise ValueError(
            "Activation review is stale because the vendor's "
            "authoritative residual risk changed after review."
        )

    proposed_score = float(
        review.proposed_residual_risk
    )

    if not (
        0.0
        <= proposed_score
        <= 100.0
    ):
        raise ValueError(
            "Proposed residual risk is outside the valid range."
        )

    previous_rating = (
        vendor.overall_risk_rating
        or rating_from_score(
            current_score
        )
    )

    activated_rating = (
        review.governed_rating
        or rating_from_score(
            proposed_score
        )
    )

    vendor.residual_risk_score = (
        proposed_score
    )

    vendor.overall_risk_rating = (
        activated_rating
    )

    execution = (
        ResidualRiskActivationExecution(
            activation_review_id=(
                review.id
            ),
            vendor_id=(
                review.vendor_id
            ),
            assessment_id=(
                review.assessment_id
            ),
            previous_residual_risk=(
                current_score
            ),
            activated_residual_risk=(
                proposed_score
            ),
            previous_risk_rating=(
                previous_rating
            ),
            activated_risk_rating=(
                activated_rating
            ),
            executor_subject=(
                principal.subject
            ),
            executor_name=(
                principal.display_name
            ),
            executor_email=(
                principal.email
            ),
            executor_role=(
                principal.role
            ),
            execution_rationale=(
                normalized_rationale
            ),
            execution_policy_version=(
                RESIDUAL_RISK_ACTIVATION_EXECUTION_POLICY_VERSION
            ),
            activation_policy_version=(
                review.activation_policy_version
            ),
            reconciliation_policy_version=(
                review.reconciliation_policy_version
            ),
            residual_risk_policy_version=(
                review.residual_risk_policy_version
            ),
        )
    )

    session.add(execution)
    session.flush()

    record_audit_event(
        session,
        principal=principal,
        action=(
            "residual_risk_activation.execute"
        ),
        object_type=(
            "residual_risk_activation_execution"
        ),
        object_id=execution.id,
        vendor_id=review.vendor_id,
        details={
            "activation_review_id": (
                review.id
            ),
            "assessment_id": (
                review.assessment_id
            ),
            "previous_residual_risk": (
                current_score
            ),
            "activated_residual_risk": (
                proposed_score
            ),
            "previous_risk_rating": (
                previous_rating
            ),
            "activated_risk_rating": (
                activated_rating
            ),
            "execution_policy_version": (
                RESIDUAL_RISK_ACTIVATION_EXECUTION_POLICY_VERSION
            ),
            "activation_policy_version": (
                review.activation_policy_version
            ),
            "reconciliation_policy_version": (
                review.reconciliation_policy_version
            ),
            "residual_risk_policy_version": (
                review.residual_risk_policy_version
            ),
            "execution_rationale": (
                normalized_rationale
            ),
        },
        dedupe_window_seconds=0,
    )

    return execution
