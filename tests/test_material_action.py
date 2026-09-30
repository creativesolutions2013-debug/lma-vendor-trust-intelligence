import pytest

from src.material_action import (
    plan_material_action,
)


def test_monitor_does_not_create_assessment():
    result = plan_material_action(
        "Monitor"
    )

    assert result.create_assessment is False
    assert result.assessment_type is None


def test_request_evidence_does_not_create_reassessment():
    result = plan_material_action(
        "Request Evidence"
    )

    assert result.create_assessment is False


def test_targeted_review_creates_targeted_assessment():
    result = plan_material_action(
        "Targeted Review"
    )

    assert result.create_assessment is True
    assert (
        result.assessment_type
        == "Targeted Material Change Review"
    )


def test_full_reassessment_requires_rationale():
    result = plan_material_action(
        "Full Reassessment"
    )

    assert result.create_assessment is True
    assert result.requires_rationale is True


def test_escalation_requires_rationale():
    result = plan_material_action(
        "Escalate"
    )

    assert result.create_assessment is False
    assert result.requires_rationale is True


def test_dismiss_requires_reason_and_closes_event():
    result = plan_material_action(
        "Dismiss"
    )

    assert result.requires_rationale is True
    assert result.close_event is True


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError):
        plan_material_action(
            "Do Something Else"
        )
