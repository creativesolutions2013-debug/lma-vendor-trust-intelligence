from dataclasses import dataclass
from datetime import datetime, timedelta

from src.control_effectiveness import (
    CONTROL_EFFECTIVENESS_POLICY_VERSION,
    evaluate_control_effectiveness,
)


@dataclass
class DispositionStub:
    id: int
    control_id: str
    final_disposition: str
    decided_at: datetime


def record(
    *,
    id,
    control_id,
    disposition,
    minutes=0,
):
    return DispositionStub(
        id=id,
        control_id=control_id,
        final_disposition=disposition,
        decided_at=(
            datetime(
                2026,
                10,
                9,
                12,
                0,
                0,
            )
            + timedelta(
                minutes=minutes
            )
        ),
    )


def test_no_decisions_are_unknown_not_zero():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
                "VM-01",
            ),
            (),
        )
    )

    assert (
        result.effectiveness_score
        is None
    )

    assert (
        result.decision_coverage_percent
        == 0
    )

    assert (
        result.unknown_controls
        == 2
    )

    assert (
        result.status
        == "Insufficient Decisions"
    )


def test_satisfied_control_scores_100():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
            ),
            (
                record(
                    id=1,
                    control_id="IAM-01",
                    disposition="Satisfied",
                ),
            ),
        )
    )

    assert (
        result.effectiveness_score
        == 100.0
    )

    assert (
        result.decision_coverage_percent
        == 100
    )

    assert (
        result.status
        == "Governed"
    )


def test_partial_and_satisfied_average():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
                "VM-01",
            ),
            (
                record(
                    id=1,
                    control_id="IAM-01",
                    disposition="Satisfied",
                ),
                record(
                    id=2,
                    control_id="VM-01",
                    disposition="Partially Satisfied",
                ),
            ),
        )
    )

    assert (
        result.effectiveness_score
        == 80.0
    )


def test_not_satisfied_scores_zero():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
            ),
            (
                record(
                    id=1,
                    control_id="IAM-01",
                    disposition="Not Satisfied",
                ),
            ),
        )
    )

    assert (
        result.effectiveness_score
        == 0.0
    )


def test_compensating_control_scores_75():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
            ),
            (
                record(
                    id=1,
                    control_id="IAM-01",
                    disposition="Compensating Control",
                ),
            ),
        )
    )

    assert (
        result.effectiveness_score
        == 75.0
    )


def test_not_applicable_is_excluded():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
                "VM-01",
            ),
            (
                record(
                    id=1,
                    control_id="IAM-01",
                    disposition="Satisfied",
                ),
                record(
                    id=2,
                    control_id="VM-01",
                    disposition="Not Applicable",
                ),
            ),
        )
    )

    assert (
        result.effectiveness_score
        == 100.0
    )

    assert (
        result.not_applicable_controls
        == 1
    )

    assert (
        result.decision_coverage_percent
        == 100
    )


def test_unknown_control_reduces_coverage_not_score():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
                "VM-01",
            ),
            (
                record(
                    id=1,
                    control_id="IAM-01",
                    disposition="Satisfied",
                ),
            ),
        )
    )

    assert (
        result.effectiveness_score
        == 100.0
    )

    assert (
        result.decision_coverage_percent
        == 50
    )

    assert (
        result.unknown_controls
        == 1
    )

    assert (
        result.status
        == "Partially Governed"
    )


def test_latest_disposition_wins():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
            ),
            (
                record(
                    id=1,
                    control_id="IAM-01",
                    disposition="Not Satisfied",
                    minutes=0,
                ),
                record(
                    id=2,
                    control_id="IAM-01",
                    disposition="Satisfied",
                    minutes=10,
                ),
            ),
        )
    )

    assert (
        result.effectiveness_score
        == 100.0
    )


def test_policy_version():
    result = (
        evaluate_control_effectiveness(
            (
                "IAM-01",
            ),
            (),
        )
    )

    assert (
        result.policy_version
        == CONTROL_EFFECTIVENESS_POLICY_VERSION
    )

    assert (
        result.policy_version
        == "CE-1.0"
    )