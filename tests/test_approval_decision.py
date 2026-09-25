from src.db import ApprovalDecision, Vendor
from src.db_health import REQUIRED_TABLES


def test_approval_decision_table_name():
    assert (
        ApprovalDecision.__tablename__
        == "approval_decisions"
    )


def test_approval_decision_has_required_fields():
    columns = {
        column.name
        for column
        in ApprovalDecision.__table__.columns
    }

    expected = {
        "vendor_id",
        "system_recommendation",
        "system_reasons_json",
        "evidence_completion_percent",
        "residual_risk_score",
        "decision",
        "approver_subject",
        "approver_name",
        "approver_email",
        "approver_role",
        "rationale",
        "conditions",
        "decided_at",
    }

    assert expected.issubset(columns)


def test_vendor_has_approval_decision_relationship():
    assert hasattr(
        Vendor,
        "approval_decisions",
    )


def test_database_health_requires_approval_table():
    assert (
        "approval_decisions"
        in REQUIRED_TABLES
    )
