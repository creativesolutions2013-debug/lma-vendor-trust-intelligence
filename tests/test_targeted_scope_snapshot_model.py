from src.db import Assessment


def test_assessment_stores_proposed_scope():
    assert hasattr(
        Assessment,
        "proposed_scope_json",
    )


def test_assessment_stores_approved_scope():
    assert hasattr(
        Assessment,
        "approved_scope_json",
    )


def test_assessment_stores_scope_override_rationale():
    assert hasattr(
        Assessment,
        "scope_override_rationale",
    )


def test_assessment_stores_scope_confirmation_identity():
    assert hasattr(
        Assessment,
        "scope_confirmed_by",
    )


def test_assessment_stores_scope_confirmation_time():
    assert hasattr(
        Assessment,
        "scope_confirmed_at",
    )
