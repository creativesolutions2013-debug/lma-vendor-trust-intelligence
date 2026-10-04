from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional, Tuple


CONTROL_SUFFICIENCY_POLICY_VERSION = "CS-1.0"


@dataclass(frozen=True)
class EvidenceControlClaim:
    """
    Structured claim that a specific evidence artifact
    supports a specific control.

    This object is intentionally separate from the Evidence
    database model because document existence alone does not
    establish control sufficiency.
    """

    evidence_id: int
    control_id: str

    covered: bool = True
    tested: bool = True

    scope_matches: bool = True
    service_matches: bool = True

    exception_present: bool = False

    extraction_confidence: float = 1.0

    rationale: str = ""


@dataclass(frozen=True)
class ControlEvidenceDecision:
    control_id: str

    status: str

    supporting_evidence_ids: Tuple[int, ...]
    evidence_review_ids: Tuple[int, ...]

    reasons: Tuple[str, ...]

    analyst_review_required: bool

    policy_version: str = CONTROL_SUFFICIENCY_POLICY_VERSION


def _parse_date(
    value: Optional[str],
) -> Optional[date]:

    if not value:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(
                value,
                fmt,
            ).date()
        except ValueError:
            continue

    return None


def _evidence_is_expired(
    evidence,
    *,
    today: date,
) -> bool:

    expiration = _parse_date(
        getattr(
            evidence,
            "expiration_date",
            None,
        )
    )

    if expiration:
        return expiration < today

    status = (
        getattr(
            evidence,
            "status",
            "",
        )
        or ""
    ).strip().lower()

    return status == "expired"


def _evidence_is_expiring_soon(
    evidence,
    *,
    today: date,
    threshold_days: int = 60,
) -> bool:

    expiration = _parse_date(
        getattr(
            evidence,
            "expiration_date",
            None,
        )
    )

    if not expiration:
        return False

    days_remaining = (
        expiration - today
    ).days

    return (
        0 <= days_remaining <= threshold_days
    )


def _evidence_has_document_exception(
    evidence,
) -> bool:

    count = (
        getattr(
            evidence,
            "exceptions_count",
            0,
        )
        or 0
    )

    if count > 0:
        return True

    detected = (
        getattr(
            evidence,
            "detected_exceptions",
            "",
        )
        or ""
    ).strip()

    return bool(detected)


def evaluate_control_evidence(
    control_id: str,
    evidence_records: Iterable,
    claims: Iterable[EvidenceControlClaim],
    *,
    today: Optional[date] = None,
    minimum_confidence: float = 0.65,
) -> ControlEvidenceDecision:
    """
    Evaluate whether available evidence is sufficient for one
    specific control.

    Decision hierarchy:

    SUPPORTED
        Current evidence contains a tested, in-scope,
        high-confidence claim with no known blocker.

    PARTIAL
        Evidence supports the control but has a material
        limitation such as an exception or approaching expiry.

    REVIEW
        A potentially relevant claim exists but confidence,
        scope, service alignment, or test status requires
        analyst validation.

    UNSUPPORTED
        No usable claim supports the control.
    """

    today = today or date.today()

    evidence_by_id = {
        getattr(
            evidence,
            "id",
            None,
        ): evidence
        for evidence in evidence_records
        if getattr(
            evidence,
            "id",
            None,
        )
        is not None
    }

    control_claims = [
        claim
        for claim in claims
        if claim.control_id == control_id
    ]

    if not control_claims:
        return ControlEvidenceDecision(
            control_id=control_id,
            status="UNSUPPORTED",
            supporting_evidence_ids=(),
            evidence_review_ids=(),
            reasons=(
                "No structured evidence claim supports this control.",
            ),
            analyst_review_required=False,
        )

    supported_ids = []
    partial_ids = []
    review_ids = []

    supported_reasons = []
    partial_reasons = []
    review_reasons = []

    for claim in control_claims:

        evidence = evidence_by_id.get(
            claim.evidence_id
        )

        if evidence is None:
            review_ids.append(
                claim.evidence_id
            )

            review_reasons.append(
                (
                    f"Evidence {claim.evidence_id} is referenced "
                    "by a control claim but the evidence record "
                    "is unavailable."
                )
            )

            continue

        if not claim.covered:
            continue

        if _evidence_is_expired(
            evidence,
            today=today,
        ):
            continue

        if not claim.scope_matches:
            review_ids.append(
                claim.evidence_id
            )

            review_reasons.append(
                (
                    f"Evidence {claim.evidence_id} may address "
                    f"{control_id}, but its scope does not match "
                    "the assessed service."
                )
            )

            continue

        if not claim.service_matches:
            review_ids.append(
                claim.evidence_id
            )

            review_reasons.append(
                (
                    f"Evidence {claim.evidence_id} does not "
                    "clearly map to the vendor service under review."
                )
            )

            continue

        if not claim.tested:
            review_ids.append(
                claim.evidence_id
            )

            review_reasons.append(
                (
                    f"Evidence {claim.evidence_id} references "
                    f"{control_id}, but operating effectiveness "
                    "was not demonstrated."
                )
            )

            continue

        if (
            claim.extraction_confidence
            < minimum_confidence
        ):
            review_ids.append(
                claim.evidence_id
            )

            review_reasons.append(
                (
                    f"Evidence {claim.evidence_id} has low "
                    "confidence for this control mapping."
                )
            )

            continue

        document_exception = (
            _evidence_has_document_exception(
                evidence
            )
        )

        if (
            claim.exception_present
            or document_exception
        ):
            partial_ids.append(
                claim.evidence_id
            )

            partial_reasons.append(
                (
                    f"Evidence {claim.evidence_id} supports "
                    f"{control_id}, but an exception or testing "
                    "issue requires consideration."
                )
            )

            continue

        if _evidence_is_expiring_soon(
            evidence,
            today=today,
        ):
            partial_ids.append(
                claim.evidence_id
            )

            partial_reasons.append(
                (
                    f"Evidence {claim.evidence_id} currently "
                    "supports the control but is approaching "
                    "expiration."
                )
            )

            continue

        supported_ids.append(
            claim.evidence_id
        )

        supported_reasons.append(
            (
                f"Evidence {claim.evidence_id} provides current, "
                f"tested, in-scope support for {control_id}."
            )
        )

    # -------------------------------------------------
    # Strongest available evidence wins.
    # -------------------------------------------------

    if supported_ids:
        return ControlEvidenceDecision(
            control_id=control_id,
            status="SUPPORTED",
            supporting_evidence_ids=tuple(
                dict.fromkeys(
                    supported_ids
                )
            ),
            evidence_review_ids=tuple(
                dict.fromkeys(
                    review_ids
                )
            ),
            reasons=tuple(
                dict.fromkeys(
                    supported_reasons
                    + review_reasons
                )
            ),
            analyst_review_required=bool(
                review_ids
            ),
        )

    if partial_ids:
        return ControlEvidenceDecision(
            control_id=control_id,
            status="PARTIAL",
            supporting_evidence_ids=tuple(
                dict.fromkeys(
                    partial_ids
                )
            ),
            evidence_review_ids=tuple(
                dict.fromkeys(
                    review_ids
                )
            ),
            reasons=tuple(
                dict.fromkeys(
                    partial_reasons
                    + review_reasons
                )
            ),
            analyst_review_required=True,
        )

    if review_ids:
        return ControlEvidenceDecision(
            control_id=control_id,
            status="REVIEW",
            supporting_evidence_ids=(),
            evidence_review_ids=tuple(
                dict.fromkeys(
                    review_ids
                )
            ),
            reasons=tuple(
                dict.fromkeys(
                    review_reasons
                )
            ),
            analyst_review_required=True,
        )

    return ControlEvidenceDecision(
        control_id=control_id,
        status="UNSUPPORTED",
        supporting_evidence_ids=(),
        evidence_review_ids=(),
        reasons=(
            (
                "Available evidence does not provide current, "
                "tested, in-scope support for this control."
            ),
        ),
        analyst_review_required=False,
    )


def evaluate_control_set(
    control_ids: Iterable[str],
    evidence_records: Iterable,
    claims: Iterable[EvidenceControlClaim],
    *,
    today: Optional[date] = None,
    minimum_confidence: float = 0.65,
) -> Tuple[ControlEvidenceDecision, ...]:

    evidence_records = tuple(
        evidence_records
    )

    claims = tuple(
        claims
    )

    return tuple(
        evaluate_control_evidence(
            control_id,
            evidence_records,
            claims,
            today=today,
            minimum_confidence=minimum_confidence,
        )
        for control_id in control_ids
    )