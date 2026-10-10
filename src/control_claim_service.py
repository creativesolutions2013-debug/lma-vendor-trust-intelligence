from dataclasses import dataclass

from src.audit import record_audit_event
from src.authz import (
    PERMISSION_ASSESSMENT_MANAGE,
    Principal,
    require,
)
from src.control_claim_review import (
    ControlClaimReviewResult,
)
from src.control_claims import (
    STATUS_ACCEPTED,
)
from src.control_sufficiency import (
    EvidenceControlClaim,
)
from src.db import (
    ControlClaimRecord,
    Evidence,
)


@dataclass(frozen=True)
class ControlClaimHistoryItem:
    record_id: int

    evidence_id: int
    evidence_name: str
    evidence_type: str

    control_id: str

    statement: str
    source_reference: str

    covered: bool
    tested: bool
    scope_matches: bool
    service_matches: bool
    exception_present: bool

    confidence: float

    confirmed_by: str | None
    analyst_rationale: str | None

    claim_policy_version: str
    review_policy_version: str | None

    created_at: object

    is_current: bool


def save_control_claim(
    session,
    *,
    vendor_id: int,
    assessment_id: int,
    review: ControlClaimReviewResult,
    principal: Principal,
) -> ControlClaimRecord:
    """
    Persist one analyst-confirmed authoritative
    evidence-to-control claim.

    The caller owns commit / rollback.
    """

    require(
        principal,
        PERMISSION_ASSESSMENT_MANAGE,
    )

    generated = review.result

    if generated.claim is None:
        raise ValueError(
            "Only an accepted control claim "
            "may be persisted."
        )

    provenance = generated.provenance

    if (
        provenance.generation_status
        != STATUS_ACCEPTED
    ):
        raise ValueError(
            "Control claim must have ACCEPTED status."
        )

    if not provenance.human_confirmed:
        raise ValueError(
            "Persistent governed control claims "
            "must be human-confirmed."
        )

    if not review.complete_confirmation:
        raise ValueError(
            "Control claim confirmation is incomplete."
        )

    if (
        provenance.confirmed_by
        != principal.subject
    ):
        raise ValueError(
            "The confirming analyst does not match "
            "the authenticated principal."
        )

    claim = generated.claim

    record = ControlClaimRecord(
        vendor_id=vendor_id,
        assessment_id=assessment_id,
        evidence_id=claim.evidence_id,
        control_id=claim.control_id,
        statement=(
            provenance.statement
        ),
        source_reference=(
            provenance.source_reference
        ),
        covered=claim.covered,
        tested=claim.tested,
        scope_matches=(
            claim.scope_matches
        ),
        service_matches=(
            claim.service_matches
        ),
        exception_present=(
            claim.exception_present
        ),
        confidence=(
            claim.extraction_confidence
        ),
        generation_status=(
            provenance.generation_status
        ),
        human_confirmed=(
            provenance.human_confirmed
        ),
        confirmed_by=(
            provenance.confirmed_by
        ),
        analyst_rationale=(
            review.analyst_rationale
        ),
        claim_policy_version=(
            provenance.policy_version
        ),
        review_policy_version=(
            review.policy_version
        ),
    )

    session.add(
        record
    )

    session.flush()

    record_audit_event(
        session,
        principal=principal,
        action="control_claim.record",
        object_type="control_claim",
        object_id=record.id,
        vendor_id=vendor_id,
        details={
            "assessment_id": (
                assessment_id
            ),
            "evidence_id": (
                record.evidence_id
            ),
            "control_id": (
                record.control_id
            ),
            "covered": (
                record.covered
            ),
            "tested": (
                record.tested
            ),
            "scope_matches": (
                record.scope_matches
            ),
            "service_matches": (
                record.service_matches
            ),
            "exception_present": (
                record.exception_present
            ),
            "confidence": (
                record.confidence
            ),
            "claim_policy_version": (
                record.claim_policy_version
            ),
            "review_policy_version": (
                record.review_policy_version
            ),
        },
        dedupe_window_seconds=0,
    )

    return record


def load_accepted_control_claims(
    session,
    *,
    vendor_id: int,
    assessment_id: int,
) -> tuple[EvidenceControlClaim, ...]:
    """
    Load the latest accepted claim for each unique
    evidence/control pair.

    Historical records remain in the database for auditability,
    while the orchestrator consumes only the latest governed
    conclusion for each evidence/control mapping.
    """

    records = (
        session.query(
            ControlClaimRecord
        )
        .filter_by(
            vendor_id=vendor_id,
            assessment_id=assessment_id,
            generation_status=STATUS_ACCEPTED,
        )
        .order_by(
            ControlClaimRecord.created_at.desc(),
            ControlClaimRecord.id.desc(),
        )
        .all()
    )

    latest = {}

    for record in records:
        key = (
            record.evidence_id,
            record.control_id,
        )

        if key not in latest:
            latest[key] = record

    return tuple(
        EvidenceControlClaim(
            evidence_id=record.evidence_id,
            control_id=record.control_id,
            covered=record.covered,
            tested=record.tested,
            scope_matches=(
                record.scope_matches
            ),
            service_matches=(
                record.service_matches
            ),
            exception_present=(
                record.exception_present
            ),
            extraction_confidence=(
                record.confidence
            ),
            rationale=(
                record.analyst_rationale
                or record.statement
            ),
        )
        for record
        in latest.values()
    )


def load_control_claim_history(
    session,
    *,
    vendor_id: int,
    assessment_id: int,
    control_id: str | None = None,
) -> tuple[ControlClaimHistoryItem, ...]:
    """
    Load governed claim history with evidence provenance.

    Historical records are preserved for traceability.

    is_current identifies the latest accepted record for each
    unique evidence/control pair. Older records remain visible
    but no longer drive the assessment orchestrator.
    """

    query = (
        session.query(
            ControlClaimRecord,
            Evidence,
        )
        .join(
            Evidence,
            Evidence.id
            == ControlClaimRecord.evidence_id,
        )
        .filter(
            ControlClaimRecord.vendor_id
            == vendor_id,
            ControlClaimRecord.assessment_id
            == assessment_id,
            ControlClaimRecord.generation_status
            == STATUS_ACCEPTED,
        )
    )

    normalized_control_id = (
        (control_id or "")
        .strip()
        .upper()
    )

    if normalized_control_id:
        query = query.filter(
            ControlClaimRecord.control_id
            == normalized_control_id
        )

    rows = (
        query
        .order_by(
            ControlClaimRecord.created_at.desc(),
            ControlClaimRecord.id.desc(),
        )
        .all()
    )

    current_pairs = set()
    history = []

    for record, evidence in rows:
        pair = (
            record.evidence_id,
            record.control_id,
        )

        is_current = (
            pair not in current_pairs
        )

        if is_current:
            current_pairs.add(
                pair
            )

        history.append(
            ControlClaimHistoryItem(
                record_id=record.id,
                evidence_id=record.evidence_id,
                evidence_name=(
                    evidence.document_name
                ),
                evidence_type=(
                    evidence.document_type
                ),
                control_id=(
                    record.control_id
                ),
                statement=(
                    record.statement
                ),
                source_reference=(
                    record.source_reference
                ),
                covered=(
                    record.covered
                ),
                tested=(
                    record.tested
                ),
                scope_matches=(
                    record.scope_matches
                ),
                service_matches=(
                    record.service_matches
                ),
                exception_present=(
                    record.exception_present
                ),
                confidence=(
                    record.confidence
                ),
                confirmed_by=(
                    record.confirmed_by
                ),
                analyst_rationale=(
                    record.analyst_rationale
                ),
                claim_policy_version=(
                    record.claim_policy_version
                ),
                review_policy_version=(
                    record.review_policy_version
                ),
                created_at=(
                    record.created_at
                ),
                is_current=is_current,
            )
        )

    return tuple(
        history
    )

