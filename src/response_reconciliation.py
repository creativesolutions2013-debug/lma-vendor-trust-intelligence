from dataclasses import dataclass
from typing import Iterable, Sequence

from src.targeted_gap import (
    analyze_targeted_evidence_gaps,
)


@dataclass(frozen=True)
class ReconciliationItem:
    requirement: str
    status: str
    evidence_state: str
    evidence_id: int | None
    document_name: str | None
    reason: str


@dataclass(frozen=True)
class ResponseReconciliation:
    total_requested: int
    satisfied: int
    validation_required: int
    outstanding: int
    completion_percent: int
    items: tuple[ReconciliationItem, ...]


def reconcile_evidence_response(
    requested_items: Sequence[str],
    evidence_records: Iterable,
) -> ResponseReconciliation:
    requested_items = list(
        dict.fromkeys(requested_items)
    )

    if not requested_items:
        return ResponseReconciliation(
            total_requested=0,
            satisfied=0,
            validation_required=0,
            outstanding=0,
            completion_percent=100,
            items=(),
        )

    gap_analysis = analyze_targeted_evidence_gaps(
        requested_items,
        evidence_records,
    )

    results = []

    for item in gap_analysis.items:
        if item.workflow_action == "Reuse":
            status = "Satisfied"

        elif (
            item.workflow_action
            == "Analyst Validate"
        ):
            status = "Validate"

        else:
            status = "Outstanding"

        results.append(
            ReconciliationItem(
                requirement=item.requirement,
                status=status,
                evidence_state=(
                    item.evidence_state
                ),
                evidence_id=item.evidence_id,
                document_name=(
                    item.document_name
                ),
                reason=item.reason,
            )
        )

    satisfied = sum(
        1
        for item in results
        if item.status == "Satisfied"
    )

    validation_required = sum(
        1
        for item in results
        if item.status == "Validate"
    )

    outstanding = sum(
        1
        for item in results
        if item.status == "Outstanding"
    )

    total_requested = len(results)

    completion_percent = round(
        (
            satisfied
            / total_requested
        )
        * 100
    )

    return ResponseReconciliation(
        total_requested=total_requested,
        satisfied=satisfied,
        validation_required=(
            validation_required
        ),
        outstanding=outstanding,
        completion_percent=(
            completion_percent
        ),
        items=tuple(results),
    )
