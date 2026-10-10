from dataclasses import dataclass
from typing import Iterable, Tuple

from src.control_disposition import (
    DISPOSITION_COMPENSATING_CONTROL,
    DISPOSITION_NOT_APPLICABLE,
    DISPOSITION_NOT_SATISFIED,
    DISPOSITION_PARTIALLY_SATISFIED,
    DISPOSITION_SATISFIED,
)


CONTROL_EFFECTIVENESS_POLICY_VERSION = "CE-1.0"


DISPOSITION_WEIGHTS = {
    DISPOSITION_SATISFIED: 100.0,
    DISPOSITION_COMPENSATING_CONTROL: 75.0,
    DISPOSITION_PARTIALLY_SATISFIED: 60.0,
    DISPOSITION_NOT_SATISFIED: 0.0,
}


@dataclass(frozen=True)
class ControlEffectivenessItem:
    control_id: str
    disposition: str | None
    score: float | None
    included_in_score: bool
    reason: str


@dataclass(frozen=True)
class ControlEffectivenessResult:
    effectiveness_score: float | None
    decision_coverage_percent: int

    total_applicable_controls: int
    scored_controls: int
    unknown_controls: int
    not_applicable_controls: int

    status: str

    items: Tuple[
        ControlEffectivenessItem,
        ...,
    ]

    policy_version: str = (
        CONTROL_EFFECTIVENESS_POLICY_VERSION
    )


def _latest_dispositions_by_control(
    records: Iterable,
) -> dict:
    latest = {}

    ordered = sorted(
        records,
        key=lambda item: (
            getattr(
                item,
                "decided_at",
                None,
            ),
            getattr(
                item,
                "id",
                0,
            ),
        ),
        reverse=True,
    )

    for record in ordered:
        control_id = (
            getattr(
                record,
                "control_id",
                "",
            )
            or ""
        ).strip().upper()

        if (
            control_id
            and control_id not in latest
        ):
            latest[
                control_id
            ] = record

    return latest


def evaluate_control_effectiveness(
    applicable_control_ids: Iterable[str],
    disposition_records: Iterable,
) -> ControlEffectivenessResult:
    """
    Calculate governed control effectiveness from the latest
    human-confirmed disposition for each applicable control.

    Important governance rule:

    A control with no confirmed disposition is UNKNOWN.
    It is not treated as ineffective and does not contribute
    a zero to the effectiveness score.

    Not Applicable controls are excluded from the score and
    denominator.
    """

    applicable = tuple(
        dict.fromkeys(
            (
                control_id
                or ""
            ).strip().upper()
            for control_id
            in applicable_control_ids
            if (
                control_id
                and control_id.strip()
            )
        )
    )

    latest = (
        _latest_dispositions_by_control(
            disposition_records
        )
    )

    items = []

    score_values = []

    not_applicable = 0
    unknown = 0

    for control_id in applicable:
        record = latest.get(
            control_id
        )

        if record is None:
            unknown += 1

            items.append(
                ControlEffectivenessItem(
                    control_id=control_id,
                    disposition=None,
                    score=None,
                    included_in_score=False,
                    reason=(
                        "No human-confirmed control "
                        "disposition is available."
                    ),
                )
            )

            continue

        disposition = (
            getattr(
                record,
                "final_disposition",
                "",
            )
            or ""
        ).strip()

        if (
            disposition
            == DISPOSITION_NOT_APPLICABLE
        ):
            not_applicable += 1

            items.append(
                ControlEffectivenessItem(
                    control_id=control_id,
                    disposition=(
                        disposition
                    ),
                    score=None,
                    included_in_score=False,
                    reason=(
                        "Control is confirmed Not Applicable "
                        "and is excluded from effectiveness scoring."
                    ),
                )
            )

            continue

        score = (
            DISPOSITION_WEIGHTS.get(
                disposition
            )
        )

        if score is None:
            unknown += 1

            items.append(
                ControlEffectivenessItem(
                    control_id=control_id,
                    disposition=(
                        disposition
                    ),
                    score=None,
                    included_in_score=False,
                    reason=(
                        "Disposition is not recognized by "
                        "the control-effectiveness policy."
                    ),
                )
            )

            continue

        score_values.append(
            score
        )

        items.append(
            ControlEffectivenessItem(
                control_id=control_id,
                disposition=(
                    disposition
                ),
                score=score,
                included_in_score=True,
                reason=(
                    "Effectiveness contribution is based on "
                    "the latest human-confirmed disposition."
                ),
            )
        )

    total_applicable = len(
        applicable
    )

    effective_denominator = (
        total_applicable
        - not_applicable
    )

    scored_controls = len(
        score_values
    )

    if effective_denominator > 0:
        coverage_percent = round(
            (
                scored_controls
                / effective_denominator
            )
            * 100
        )
    else:
        coverage_percent = 100

    if score_values:
        effectiveness = round(
            sum(
                score_values
            )
            / len(
                score_values
            ),
            1,
        )
    else:
        effectiveness = None

    if effectiveness is None:
        status = "Insufficient Decisions"

    elif coverage_percent < 50:
        status = "Provisional"

    elif coverage_percent < 100:
        status = "Partially Governed"

    else:
        status = "Governed"

    return ControlEffectivenessResult(
        effectiveness_score=(
            effectiveness
        ),
        decision_coverage_percent=(
            coverage_percent
        ),
        total_applicable_controls=(
            total_applicable
        ),
        scored_controls=(
            scored_controls
        ),
        unknown_controls=(
            unknown
        ),
        not_applicable_controls=(
            not_applicable
        ),
        status=status,
        items=tuple(
            items
        ),
    )