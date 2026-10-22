"""Synthetic M4C-2B-2B scope-enforced review-note write regressions.

Only these optional annotations may be updated; no approval, score, source file,
status or AI disposition changes are permitted by this service.
"""
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import event, select

from test_tenant_read_scope import NOW, ctx, update, ISSUER
from test_database_evidence_authority import isolated_engine as synthetic_isolated_engine
from src.assessment_evidence_access import AuthenticatedIdentity
from src.authz import Principal, ROLE_ADMIN, ROLE_VIEWER
from src.db import (
    Assessment, AuditLog, EngagementAccessGrant, Evidence, OrganizationMembership,
)
import src.tenant_assessment_evidence_operations as operations
from src.tenant_assessment_evidence_operations import TenantAssessmentEvidenceOperations


@pytest.fixture
def guarded(ctx, monkeypatch):
    monkeypatch.setattr(operations, "_utc_now", lambda: ctx.clock[0])
    return ctx, TenantAssessmentEvidenceOperations(
        ctx.factory, identity_source=ctx.source
    )


def database_snapshot(ctx):
    with ctx.factory() as session:
        a = session.get(Assessment, 1001)
        e = session.get(Evidence, 9001)
        entries = session.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
        return (a.notes, a.status, a.approval_status, a.risk_score,
                e.analyst_notes, e.storage_path, e.status,
                [(x.action, x.object_type, x.object_id, x.actor_subject,
                  x.actor_role, x.vendor_id, x.details_json) for x in entries])


@pytest.mark.parametrize("kind,identifier", [("assessment", 1001), ("evidence", 9001)])
def test_authorized_analyst_can_update_only_review_note_and_audit(guarded, kind, identifier):
    ctx, service = guarded
    before = database_snapshot(ctx)
    note = "Follow up on missing operational evidence; no control conclusion."
    method = getattr(service, "record_" + kind + "_review_note")
    assert method(identifier, note) is True
    after = database_snapshot(ctx)
    assert len(after[-1]) == len(before[-1]) + 1
    event_row = after[-1][-1]
    assert event_row == (kind + ".review_note_updated", kind, str(identifier),
                         "reader-a", "Analyst", 11, None)
    assert note not in repr(event_row)
    if kind == "assessment":
        assert after[0] == note and after[1:4] == before[1:4]
        assert after[4:7] == before[4:7]
    else:
        assert after[4] == note and after[:4] == before[:4]
        assert after[5:7] == before[5:7]


@pytest.mark.parametrize("kind,target", [
    ("assessment", 1002), ("assessment", 2001),
    ("assessment", 3001), ("assessment", 4001), ("assessment", 5001),
    ("evidence", 9002), ("evidence", 9201), ("evidence", 9301),
    ("evidence", 9401), ("evidence", 9501), ("evidence", 9601),
    ("evidence", 9701), ("evidence", 999999),
])
def test_sibling_other_tenant_legacy_and_broken_parent_are_denied(guarded, kind, target):
    ctx, service = guarded
    before = database_snapshot(ctx)
    assert getattr(service, "record_" + kind + "_review_note")(target, "No access") is False
    assert database_snapshot(ctx) == before


@pytest.mark.parametrize("kind,method", [
    ("assessment", "record_assessment_review_note"),
    ("evidence", "record_evidence_review_note"),
])
@pytest.mark.parametrize("invalid", [None, True, 0, -1, 1.2, "1001", [], {}, object()])
def test_invalid_identifiers_never_mutate_or_audit(guarded, kind, method, invalid):
    ctx, service = guarded
    before = database_snapshot(ctx)
    assert getattr(service, method)(invalid, "note") is False
    assert database_snapshot(ctx) == before


@pytest.mark.parametrize("invalid", [
    None, True, "", " ", "  leading", "trailing  ", "x" * 1201,
    "binary\x00payload", "\x7fbad", ["text"], {"text": "x"},
])
def test_note_text_is_bounded_and_validated(guarded, invalid):
    ctx, service = guarded
    before = database_snapshot(ctx)
    assert service.record_evidence_review_note(9001, invalid) is False
    assert database_snapshot(ctx) == before


def test_viewer_and_upstream_forged_admin_cannot_write(guarded):
    ctx, service = guarded
    before = database_snapshot(ctx)
    update(ctx, OrganizationMembership, 501, role=ROLE_VIEWER)
    assert ctx.identity.principal.role == ROLE_ADMIN
    assert service.record_assessment_review_note(1001, "Not permitted") is False
    assert service.record_evidence_review_note(9001, "Not permitted") is False
    assert database_snapshot(ctx) == before


def test_different_organization_uses_its_own_member_and_grant(guarded):
    ctx, service = guarded
    ctx.source.identity = AuthenticatedIdentity(
        Principal("reader-b", "Other reviewer", "other@synthetic.invalid", ROLE_ADMIN),
        ISSUER, "lma-synthetic", "sid_other", 2,
        NOW - timedelta(minutes=2), NOW + timedelta(minutes=30),
    )
    before = database_snapshot(ctx)
    # DB member has Viewer role even though upstream says Admin.
    assert service.record_evidence_review_note(9201, "Bad") is False
    assert database_snapshot(ctx) == before
    update(ctx, OrganizationMembership, 601, role=ROLE_ADMIN)
    assert service.record_evidence_review_note(9201, "Allowed for organization B") is True
    assert service.record_evidence_review_note(9001, "Different customer") is False
    with ctx.factory() as session:
        assert session.get(Evidence, 9201).analyst_notes == "Allowed for organization B"


@pytest.mark.parametrize("obj,pk", [
    (OrganizationMembership, 501), (EngagementAccessGrant, 701),
])
@pytest.mark.parametrize("change", [
    {"status": "revoked"},
    {"expires_at": NOW - timedelta(seconds=1)},
    {"valid_from": NOW + timedelta(seconds=1)},
])
def test_revoked_expired_and_future_grants_and_memberships_cannot_write(
        guarded, obj, pk, change):
    ctx, service = guarded
    update(ctx, obj, pk, **change)
    before = database_snapshot(ctx)
    assert service.record_assessment_review_note(1001, "Nope") is False
    assert service.record_evidence_review_note(9001, "Nope") is False
    assert database_snapshot(ctx) == before


@pytest.mark.parametrize("source", [
    None, {}, {"role": "Admin", "subject": "reader-a"}, "fake-token",
])
def test_untrusted_session_source_fails_closed(guarded, source):
    ctx, service = guarded
    ctx.source.identity = source
    before = database_snapshot(ctx)
    assert service.record_assessment_review_note(1001, "Nope") is False
    assert database_snapshot(ctx) == before


@pytest.mark.parametrize("field,value", [
    ("issuer", "https://forged.invalid"),
    ("organization_id", 2),
    ("session_id", ""),
    ("issued_at", NOW + timedelta(seconds=1)),
    ("expires_at", NOW),
    ("principal", Principal("forged", "X", "x@synthetic.invalid", ROLE_ADMIN)),
])
def test_invalid_authenticated_session_is_denied(guarded, field, value):
    ctx, service = guarded
    ctx.source.identity = replace(ctx.identity, **{field: value})
    before = database_snapshot(ctx)
    assert service.record_evidence_review_note(9001, "Denied") is False
    assert database_snapshot(ctx) == before


def test_dual_current_memberships_denied_even_for_same_email(guarded):
    ctx, service = guarded
    # Test fixture enforces DB uniqueness per organization, not per issuer
    # across organizations; tenant selection must be unambiguous.
    with ctx.factory() as session:
        session.add(OrganizationMembership(
            organization_id=2, issuer=ISSUER, subject="reader-a", role=ROLE_ADMIN,
            status="active", valid_from=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=1),
        ))
        session.commit()
    before = database_snapshot(ctx)
    assert service.record_evidence_review_note(9001, "Nope") is False
    assert database_snapshot(ctx) == before


def test_session_rotation_during_authorization_denies(guarded, monkeypatch):
    ctx, service = guarded
    original = service._grant
    def rotate(*args, **kwargs):
        result = original(*args, **kwargs)
        ctx.source.identity = replace(ctx.identity, session_id="sid_rotated")
        return result
    monkeypatch.setattr(service, "_grant", rotate)
    before = database_snapshot(ctx)
    assert service.record_evidence_review_note(9001, "Nope") is False
    assert database_snapshot(ctx) == before


def test_expiry_during_authorization_denies(guarded, monkeypatch):
    ctx, service = guarded
    original = service._grant
    def expire(*args, **kwargs):
        result = original(*args, **kwargs)
        ctx.clock[0] = ctx.identity.expires_at
        return result
    monkeypatch.setattr(service, "_grant", expire)
    before = database_snapshot(ctx)
    assert service.record_evidence_review_note(9001, "Nope") is False
    assert database_snapshot(ctx) == before


def test_audit_write_failure_rolls_back_note(guarded, monkeypatch):
    ctx, service = guarded
    before = database_snapshot(ctx)
    def fail_on_audit(mapper, connection, obj):
        raise RuntimeError("synthetic audit backend failure")
    event.listen(AuditLog, "before_insert", fail_on_audit)
    try:
        assert service.record_assessment_review_note(1001, "Never commit without audit") is False
    finally:
        event.remove(AuditLog, "before_insert", fail_on_audit)
    assert database_snapshot(ctx) == before


def test_source_error_does_not_leak_or_modify_data(guarded, monkeypatch, caplog):
    ctx, service = guarded
    before = database_snapshot(ctx)
    secret = "private-idp-secret"
    def outage():
        raise RuntimeError(secret)
    monkeypatch.setattr(ctx.source, "authenticated_identity", outage)
    assert service.record_evidence_review_note(9001, "Cannot access") is False
    assert secret not in caplog.text
    assert database_snapshot(ctx) == before


def test_request_session_uncommitted_changes_are_not_flushed(guarded):
    ctx, service = guarded
    with ctx.factory() as dirty_session:
        dirty_session.add(Assessment(
            id=7777, vendor_id=11, engagement_id=101, assessment_type="Uncommitted"
        ))
        assert service.record_evidence_review_note(9001, "Legitimate independent note")
        assert dirty_session.new
        assert any(item.id == 7777 for item in dirty_session.new)
        dirty_session.rollback()


def test_postgresql_transactional_note_audit_integrity(
        guarded, synthetic_isolated_engine, monkeypatch):
    if synthetic_isolated_engine.dialect.name != "postgresql":
        pytest.skip("Direct PostgreSQL check runs in isolated GitHub Actions only")
    from sqlalchemy.orm import sessionmaker
    from test_tenant_read_scope import rows, TrustedSyntheticSource
    engine = synthetic_isolated_engine
    # Each test owns a root transaction; commits inside the dedicated note
    # sessions are savepoints and never persist into other PostgreSQL tests.
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection, autoflush=False, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        rows(factory)
        monkeypatch.setattr(operations, "_utc_now", lambda: NOW)
        identity = AuthenticatedIdentity(
            Principal("reader-a", "Reader", "reader@synthetic.invalid", ROLE_ADMIN),
            ISSUER, "lma-synthetic", "sid_pg_write", 1,
            NOW - timedelta(minutes=1), NOW + timedelta(minutes=30),
        )
        source = TrustedSyntheticSource(identity)
        service = TenantAssessmentEvidenceOperations(factory, identity_source=source)
        assert service.record_assessment_review_note(1001, "Scoped PG assessment note")
        assert service.record_evidence_review_note(9001, "Scoped PG evidence note")
        assert not service.record_evidence_review_note(9002, "Sibling denied")
        assert not service.record_assessment_review_note(2001, "Other tenant denied")
        with factory() as session:
            assert session.get(Assessment, 1001).notes == "Scoped PG assessment note"
            assert session.get(Evidence, 9001).analyst_notes == "Scoped PG evidence note"
            assert session.get(Assessment, 1001).approval_status == "Pending"
            assert session.get(Evidence, 9001).storage_path is not None
            assert session.query(AuditLog).count() == 2
        with factory() as session:
            session.get(EngagementAccessGrant, 701).status = "revoked"
            session.commit()
        assert service.record_evidence_review_note(9001, "After revocation") is False
    finally:
        transaction.rollback()
        connection.close()


def test_internal_operation_kind_cannot_be_substituted(guarded):
    ctx, service = guarded
    before = database_snapshot(ctx)
    assert service._record("approval", 9001, "Nope") is False
    assert service._record(None, 9001, "Nope") is False
    assert database_snapshot(ctx) == before


def test_session_rotation_after_audit_insert_rolls_back_everything(guarded):
    ctx, service = guarded
    before = database_snapshot(ctx)
    def rotate_during_audit(mapper, connection, obj):
        ctx.source.identity = replace(ctx.identity, session_id="sid_rotated_during_audit")
    event.listen(AuditLog, "before_insert", rotate_during_audit)
    try:
        assert service.record_assessment_review_note(1001, "Rollback after audit") is False
    finally:
        event.remove(AuditLog, "before_insert", rotate_during_audit)
    assert database_snapshot(ctx) == before


def test_expiry_after_audit_insert_rolls_back_everything(guarded):
    ctx, service = guarded
    before = database_snapshot(ctx)
    def expire_during_audit(mapper, connection, obj):
        ctx.clock[0] = ctx.identity.expires_at
    event.listen(AuditLog, "before_insert", expire_during_audit)
    try:
        assert service.record_evidence_review_note(9001, "Rollback after expiry") is False
    finally:
        event.remove(AuditLog, "before_insert", expire_during_audit)
    assert database_snapshot(ctx) == before
