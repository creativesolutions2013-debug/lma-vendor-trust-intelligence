import json
from dataclasses import dataclass
from typing import Iterable, Tuple

from src.authz import (
    Principal,
    ROLE_ADMIN,
)
from src.control_claims import (
    STATUS_ACCEPTED,
)
from src.db import (
    ControlClaimRecord,
    ControlDispositionRecord,
)


CONTROL_DISPOSITION_BASIS_POLICY_VERSION = "CBE-1.0"

BASIS_MODE_CLAIM = "CLAIM"
BASIS_MODE_ADMIN_OVERRIDE = "ADMIN_OVERRIDE"
BASIS_MODE_UNVERIFIED = "UNVERIFIED"
BASIS_MODE_LEGACY_UNVERIFIED = "LEGACY_UNVERIFIED"


@dataclass(frozen=True)
class ControlDispositionBasisDecision:
    verified: bool
    mode: str

    claim_record_ids: Tuple[int, ...]
    evidence_ids: Tuple[int, ...]

    reason: str
    override_reason: str | None = None

    policy_version: str = (
        CONTROL_DISPOSITION_BASIS_POLICY_VERSION
    )


def _normalize_evidence_ids(
    values: Iterable[int],
) -> tuple[int, ...]:
    normalized = []

    for value in values:
        try:
            evidence_id = int(value)
        except (TypeError, ValueError):
            continue

        if evidence_id not in normalized:
            normalized.append(evidence_id)

    return tuple(normalized)


def _latest_current_claims(
    session,
    *,
    vendor_id: int,
    assessment_id: int,
    control_id: str,
) -> tuple[ControlClaimRecord, ...]:
    records = (
        session.query(
            ControlClaimRecord
        )
        .filter_by(
            vendor_id=vendor_id,
            assessment_id=assessment_id,
            control_id=control_id,
            generation_status=STATUS_ACCEPTED,
            human_confirmed=True,
        )
        .order_by(
            ControlClaimRecord.created_at.desc(),
            ControlClaimRecord.id.desc(),
        )
        .all()
    )

    latest_by_evidence = {}

    for record in records:
        if record.evidence_id not in latest_by_evidence:
            latest_by_evidence[
                record.evidence_id
            ] = record

    return tuple(
        latest_by_evidence.values()
    )


def evaluate_control_disposition_basis(
    session,
    *,
    vendor_id: int,
    assessment_id: int,
    control_id: str,
    evidence_ids: Iterable[int],
    principal: Principal,
    allow_admin_override: bool = False,
    override_reason: str | None = None,
) -> ControlDispositionBasisDecision:
    """
    Verify that a control disposition is grounded in a current,
    accepted, human-confirmed governed claim.

    An explicit Admin override is available for exceptional,
    controlled use. It must include a reason.
    """

    normalized_control_id = (
        control_id
        or ""
    ).strip().upper()

    normalized_evidence_ids = (
        _normalize_evidence_ids(
            evidence_ids
        )
    )

    current_claims = (
        _latest_current_claims(
            session,
            vendor_id=vendor_id,
            assessment_id=assessment_id,
            control_id=normalized_control_id,
        )
    )

    matching_claims = tuple(
        record
        for record in current_claims
        if (
            record.evidence_id
            in normalized_evidence_ids
        )
    )

    if matching_claims:
        return ControlDispositionBasisDecision(
            verified=True,
            mode=BASIS_MODE_CLAIM,
            claim_record_ids=tuple(
                record.id
                for record in matching_claims
            ),
            evidence_ids=tuple(
                dict.fromkeys(
                    record.evidence_id
                    for record in matching_claims
                )
            ),
            reason=(
                "Disposition is backed by a current accepted "
                "human-confirmed evidence-to-control claim."
            ),
        )

    if allow_admin_override:
        if principal.role != ROLE_ADMIN:
            raise PermissionError(
                "Only an Admin may override claim-basis "
                "enforcement."
            )

        normalized_reason = (
            override_reason
            or ""
        ).strip()

        if not normalized_reason:
            raise ValueError(
                "Admin claim-basis override requires a reason."
            )

        return ControlDispositionBasisDecision(
            verified=True,
            mode=BASIS_MODE_ADMIN_OVERRIDE,
            claim_record_ids=(),
            evidence_ids=normalized_evidence_ids,
            reason=(
                "Claim-basis enforcement was explicitly "
                "overridden by an Admin."
            ),
            override_reason=normalized_reason,
        )

    if not normalized_evidence_ids:
        reason = (
            "Disposition does not identify evidence that can "
            "be traced to an accepted governed claim."
        )
    elif not current_claims:
        reason = (
            "No current accepted human-confirmed governed claim "
            "exists for this vendor, assessment, and control."
        )
    else:
        reason = (
            "Disposition evidence does not match the evidence "
            "supporting the current accepted governed claim."
        )

    return ControlDispositionBasisDecision(
        verified=False,
        mode=BASIS_MODE_UNVERIFIED,
        claim_record_ids=(),
        evidence_ids=normalized_evidence_ids,
        reason=reason,
    )


def _json_list(
    raw_value,
) -> list:
    if not raw_value:
        return []

    try:
        parsed = json.loads(raw_value)
    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return []

    return (
        parsed
        if isinstance(parsed, list)
        else []
    )


def backfill_control_disposition_bases(
    session,
) -> dict:
    """
    Backfill historical dispositions only when their recorded
    evidence can be matched to a current accepted governed claim.

    Unverifiable historical dispositions remain explicitly
    LEGACY_UNVERIFIED.
    """

    records = (
        session.query(
            ControlDispositionRecord
        )
        .order_by(
            ControlDispositionRecord.id.asc()
        )
        .all()
    )

    verified = 0
    skipped = 0

    system_principal = Principal(
        subject="cbe-backfill",
        display_name="CBE Backfill",
        email="cbe-backfill@example.invalid",
        role=ROLE_ADMIN,
    )

    for record in records:
        if record.claim_basis_verified:
            continue

        evidence_ids = tuple(
            dict.fromkeys(
                _json_list(
                    record.supporting_evidence_ids_json
                )
                + _json_list(
                    record.review_evidence_ids_json
                )
            )
        )

        basis = (
            evaluate_control_disposition_basis(
                session,
                vendor_id=record.vendor_id,
                assessment_id=record.assessment_id,
                control_id=record.control_id,
                evidence_ids=evidence_ids,
                principal=system_principal,
            )
        )

        if not basis.verified:
            record.claim_basis_mode = (
                BASIS_MODE_LEGACY_UNVERIFIED
            )

            skipped += 1
            continue

        record.claim_basis_verified = True
        record.claim_basis_mode = basis.mode

        record.claim_basis_record_ids_json = (
            json.dumps(
                list(
                    basis.claim_record_ids
                )
            )
        )

        record.claim_basis_evidence_ids_json = (
            json.dumps(
                list(
                    basis.evidence_ids
                )
            )
        )

        record.claim_basis_policy_version = (
            basis.policy_version
        )

        verified += 1

    return {
        "verified": verified,
        "legacy_unverified": skipped,
        "total": len(records),
    }
