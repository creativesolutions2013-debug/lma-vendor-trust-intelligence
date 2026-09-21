import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.audit import record_audit_event
from src.authz import Principal, ROLE_ANALYST
from src.db import AuditLog, Base


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )()


def make_principal():
    return Principal(
        subject="user-123",
        display_name="Test Analyst",
        email="analyst@example.com",
        role=ROLE_ANALYST,
    )


def test_record_audit_event_persists_actor_action_and_target():
    session = make_session()
    principal = make_principal()

    event = record_audit_event(
        session,
        principal=principal,
        action="evidence.upload",
        object_type="evidence",
        object_id="42",
        vendor_id=7,
        details={
            "document_type": "SOC 2 Type II",
            "source": "synthetic-test",
        },
    )
    session.commit()

    saved = (
        session.query(AuditLog)
        .filter_by(id=event.id)
        .one()
    )

    assert saved.actor_subject == "user-123"
    assert saved.actor_role == ROLE_ANALYST
    assert saved.action == "evidence.upload"
    assert saved.object_type == "evidence"
    assert saved.object_id == "42"
    assert saved.vendor_id == 7
    assert saved.outcome == "success"

    details = json.loads(saved.details_json)
    assert details["document_type"] == "SOC 2 Type II"

    session.close()


def test_record_audit_event_allows_system_level_event_without_vendor():
    session = make_session()

    principal = Principal(
        subject="admin-1",
        display_name="Admin User",
        email="admin@example.com",
        role="Admin",
    )

    event = record_audit_event(
        session,
        principal=principal,
        action="report.export",
        object_type="risk_register",
    )
    session.commit()

    saved = (
        session.query(AuditLog)
        .filter_by(id=event.id)
        .one()
    )

    assert saved.vendor_id is None
    assert saved.object_id is None
    assert saved.details_json is None

    session.close()


def test_identical_immediate_audit_event_is_deduplicated():
    session = make_session()
    principal = make_principal()

    first = record_audit_event(
        session,
        principal=principal,
        action="finding.update",
        object_type="finding",
        object_id="8",
        vendor_id=1,
        details={
            "status": "In Remediation",
            "owner": "Test Analyst",
        },
    )
    session.commit()

    second = record_audit_event(
        session,
        principal=principal,
        action="finding.update",
        object_type="finding",
        object_id="8",
        vendor_id=1,
        details={
            "owner": "Test Analyst",
            "status": "In Remediation",
        },
    )
    session.commit()

    assert first.id == second.id
    assert session.query(AuditLog).count() == 1

    session.close()


def test_changed_audit_details_create_new_event():
    session = make_session()
    principal = make_principal()

    record_audit_event(
        session,
        principal=principal,
        action="finding.update",
        object_type="finding",
        object_id="8",
        vendor_id=1,
        details={"status": "Open"},
    )
    session.commit()

    record_audit_event(
        session,
        principal=principal,
        action="finding.update",
        object_type="finding",
        object_id="8",
        vendor_id=1,
        details={"status": "Closed"},
    )
    session.commit()

    assert session.query(AuditLog).count() == 2

    session.close()


def test_deduplication_can_be_disabled():
    session = make_session()
    principal = make_principal()

    for _ in range(2):
        record_audit_event(
            session,
            principal=principal,
            action="report.export",
            object_type="risk_register",
            dedupe_window_seconds=0,
        )
        session.commit()

    assert session.query(AuditLog).count() == 2

    session.close()
