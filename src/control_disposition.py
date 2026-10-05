from dataclasses import dataclass
from typing import Tuple

from src.control_sufficiency import ControlEvidenceDecision


CONTROL_DISPOSITION_POLICY_VERSION = "CD-1.0"

DISPOSITION_SATISFIED = "Satisfied"
DISPOSITION_PARTIALLY_SATISFIED = "Partially Satisfied"
DISPOSITION_NOT_SATISFIED = "Not Satisfied"
DISPOSITION_NOT_APPLICABLE = "Not Applicable"
DISPOSITION_COMPENSATING_CONTROL = "Compensating Control"
DISPOSITION_ANALYST_REVIEW = "Analyst Review Required"


FINAL_DISPOSITIONS = {
    DISPOSITION_SATISFIED,
    DISPOSITION_PARTIALLY_SATISFIED,
    DISPOSITION_NOT_SATISFIED,
    DISPOSITION_NOT_APPLICABLE,
    DISPOSITION_COMPENSATING_CONTROL,
}


@dataclass(frozen=True)
class AnalystDisposition:
    """
    Human disposition applied after review.

    Missing evidence is not automatically treated as proof
    that the control failed.
    """

    control_id: str
    disposition: str
    rationale: str
    decided_by: str
    compensating_control: str | None = None


@dataclass(frozen=True)
class ControlDispositionDecision:
    control_id: str

    recommended_disposition: str
    final_disposition: str

    supporting_evidence_ids: Tuple[int, ...]
    review_evidence_ids: Tuple[int, ...]

    reasons: Tuple[str, ...]

    analyst_review_required: bool
    human_confirmed: bool

    decided_by: str | None = None
    decision_rationale: str | None = None
    compensating_control: str | None = None

    policy_version: str = CONTROL_DISPOSITION_POLICY_VERSION


def _normalized_text(
    value: str | None,
) -> str:
    return (value or "").strip()


def _recommend_disposition(
    sufficiency: ControlEvidenceDecision,
) -> tuple[str, bool, tuple[str, ...]]:
    """
    Translate evidence sufficiency into a control-disposition
    recommendation without overstating what the evidence proves.
    """

    if sufficiency.status == "SUPPORTED":
        return (
            DISPOSITION_SATISFIED,
            sufficiency.analyst_review_required,
            sufficiency.reasons,
        )

    if sufficiency.status == "PARTIAL":
        return (
            DISPOSITION_PARTIALLY_SATISFIED,
            True,
            sufficiency.reasons,
        )

    if sufficiency.status == "REVIEW":
        return (
            DISPOSITION_ANALYST_REVIEW,
            True,
            sufficiency.reasons,
        )

    if sufficiency.status == "UNSUPPORTED":
        return (
            DISPOSITION_ANALYST_REVIEW,
            True,
            tuple(
                sufficiency.reasons
                + (
                    (
                        "Insufficient evidence is not treated "
                        "as proof that the control is ineffective. "
                        "Human review or additional vendor "
                        "evidence is required."
                    ),
                )
            ),
        )

    raise ValueError(
        "Unsupported control sufficiency status: "
        f"{sufficiency.status}"
    )


def evaluate_control_disposition(
    sufficiency: ControlEvidenceDecision,
    analyst_decision: AnalystDisposition | None = None,
) -> ControlDispositionDecision:
    """
    Produce a governed disposition for a control.

    Automated evidence analysis generates a recommendation.
    A human analyst may confirm or override that recommendation.
    """

    (
        recommendation,
        review_required,
        reasons,
    ) = _recommend_disposition(
        sufficiency
    )

    if analyst_decision is None:
        return ControlDispositionDecision(
            control_id=sufficiency.control_id,
            recommended_disposition=recommendation,
            final_disposition=recommendation,
            supporting_evidence_ids=(
                sufficiency.supporting_evidence_ids
            ),
            review_evidence_ids=(
                sufficiency.evidence_review_ids
            ),
            reasons=reasons,
            analyst_review_required=review_required,
            human_confirmed=False,
        )

    if (
        analyst_decision.control_id
        != sufficiency.control_id
    ):
        raise ValueError(
            "Analyst disposition control_id does not match "
            "the control evidence decision."
        )

    if (
        analyst_decision.disposition
        not in FINAL_DISPOSITIONS
    ):
        raise ValueError(
            "Invalid analyst control disposition: "
            f"{analyst_decision.disposition}"
        )

    rationale = _normalized_text(
        analyst_decision.rationale
    )

    decided_by = _normalized_text(
        analyst_decision.decided_by
    )

    if not rationale:
        raise ValueError(
            "Analyst disposition requires a rationale."
        )

    if not decided_by:
        raise ValueError(
            "Analyst disposition requires decided_by."
        )

    compensating_control = _normalized_text(
        analyst_decision.compensating_control
    )

    if (
        analyst_decision.disposition
        == DISPOSITION_COMPENSATING_CONTROL
        and not compensating_control
    ):
        raise ValueError(
            "Compensating Control disposition requires a "
            "compensating control description."
        )

    if (
        analyst_decision.disposition
        != DISPOSITION_COMPENSATING_CONTROL
    ):
        compensating_control = ""

    decision_reasons = tuple(
        dict.fromkeys(
            reasons
            + (
                (
                    "Human disposition recorded: "
                    f"{analyst_decision.disposition}. "
                    f"Rationale: {rationale}"
                ),
            )
        )
    )

    return ControlDispositionDecision(
        control_id=sufficiency.control_id,
        recommended_disposition=recommendation,
        final_disposition=(
            analyst_decision.disposition
        ),
        supporting_evidence_ids=(
            sufficiency.supporting_evidence_ids
        ),
        review_evidence_ids=(
            sufficiency.evidence_review_ids
        ),
        reasons=decision_reasons,
        analyst_review_required=False,
        human_confirmed=True,
        decided_by=decided_by,
        decision_rationale=rationale,
        compensating_control=(
            compensating_control or None
        ),
    )