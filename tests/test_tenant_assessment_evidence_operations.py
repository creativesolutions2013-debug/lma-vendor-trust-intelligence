"""Synthetic M4C-2B-2B scope-enforced review-note write regressions.

Only these optional annotations may be updated; no approval, score, source file,
status or AI disposition changes are permitted by this service.
"""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest
from sqlalchemy import event, select

from test_tenant_read_scope import NOW, ctx, postgres_ctx, update, ISSUER
from test_database_evidence_authority import isolated_engine as synthetic_isolated_engine
from src.assessment_evidence_access import AuthenticatedIdentity
from src.authz import PERMISSION_VENDOR_READ, Principal, ROLE_ADMIN, ROLE_ANALYST, ROLE_VIEWER
from src.db import (
    AnalystNoteRevision, Assessment, AuditLog, EngagementAccessGrant, Evidence,
    OrganizationMembership, Vendor,
)
import src.tenant_assessment_evidence_operations as operations
from src.tenant_assessment_evidence_operations import TenantAssessmentEvidenceOperations


@pytest.fixture
def guarded(ctx, monkeypatch):
    monkeypatch.setattr(operations, "_utc_now", lambda: ctx.clock[0])
    return ctx, TenantAssessmentEvidenceOperations(
        ctx.factory, identity_source=ctx.source
    )


@pytest.fixture(params=("sqlite", "postgres"))
def quarantine_guarded(request, monkeypatch):
    context = request.getfixturevalue("ctx" if request.param == "sqlite" else "postgres_ctx")
    monkeypatch.setattr(operations, "_utc_now", lambda: context.clock[0])
    return context, TenantAssessmentEvidenceOperations(
        context.factory, identity_source=context.source
    )


def database_snapshot(ctx):
    with ctx.factory() as session:
        a = session.get(Assessment, 1001)
        e = session.get(Evidence, 9001)
        entries = session.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
        revisions = session.execute(select(AnalystNoteRevision).order_by(AnalystNoteRevision.id)).scalars().all()
        return (a.notes, a.status, a.approval_status, a.risk_score,
                e.analyst_notes, e.storage_path, e.status,
                [(x.id, x.organization_id, x.vendor_id, x.engagement_id, x.assessment_id,
                  x.evidence_id, x.object_type, x.object_id, x.actor_issuer,
                  x.actor_subject, x.actor_role, x.membership_id, x.session_id,
                  x.created_at, x.origin, x.content) for x in revisions],
                [(x.action, x.object_type, x.object_id, x.actor_subject,
                  x.actor_role, x.vendor_id, x.details_json, x.actor_issuer,
                  x.organization_id, x.membership_id, x.session_id) for x in entries])


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
                         "reader-a", "Analyst", 11, None, ISSUER, 1, 501,
                         ctx.identity.session_id)
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


@pytest.mark.parametrize("kind,target", [("assessment", 1001), ("evidence", 9001)])
def test_repeated_attributed_notes_preserve_rationale_and_individual_attribution(guarded, kind, target):
    ctx, service = guarded
    model, field = (Assessment, "notes") if kind == "assessment" else (Evidence, "analyst_notes")
    record = getattr(service, "record_" + kind + "_review_note")
    history = getattr(service, "list_" + kind + "_note_revisions")
    first = "Source p.8: follow-up requested; no assurance conclusion."
    second = "Source p.9: scope remains uncertain; analyst review required."
    assert record(target, first)
    ctx.clock[0] += timedelta(seconds=1)
    assert record(target, second)
    revisions = history(target)
    assert [row.content for row in revisions] == [first, second]
    assert [row.origin for row in revisions] == ["analyst", "analyst"]
    for row in revisions:
        assert (row.organization_id, row.vendor_id, row.engagement_id, row.assessment_id) == (1, 11, 101, 1001)
        assert (row.actor_issuer, row.actor_subject, row.actor_role, row.membership_id,
                row.session_id) == (ISSUER, "reader-a", ROLE_ANALYST, 501, ctx.identity.session_id)
        assert row.object_type == kind and row.object_id == target
        assert row.evidence_id == (9001 if kind == "evidence" else None)
        assert row.created_at.tzinfo is not None
    with pytest.raises(FrozenInstanceError):
        revisions[0].content = "Erase prior exception"
    assert revisions[0].created_at == NOW
    assert revisions[1].created_at == NOW + timedelta(seconds=1)
    with ctx.factory() as database:
        assert getattr(database.get(model, target), field) == second
        audits = database.execute(select(AuditLog)).scalars().all()
        assert len(audits) == 2
        for row in audits:
            assert row.details_json is None
            assert not any(text in repr(row.__dict__) for text in (first, second))


@pytest.mark.parametrize("kind,target", [("assessment", 1001), ("evidence", 9001)])
def test_untracked_legacy_change_blocks_overwrite_without_inventing_actor(quarantine_guarded, kind, target):
    ctx, service = quarantine_guarded
    model, field = (Assessment, "notes") if kind == "assessment" else (Evidence, "analyst_notes")
    record = getattr(service, "record_" + kind + "_review_note")
    assert record(target, "First tracked rationale")
    update(ctx, model, target, **{field: "Legacy writer changed rationale; attribution unknown"})
    before = database_snapshot(ctx)
    assert not record(target, "New explicit analyst rationale")
    assert database_snapshot(ctx) == before
    history = getattr(service, "list_" + kind + "_note_revisions")(target)
    assert [row.content for row in history] == ["First tracked rationale"]
    assert history[0].origin == "analyst"


def move_synthetic_target_scope(ctx, move):
    """Keep the caller authorized after a move, without assigning note ownership."""
    if move == "engagement":
        update(ctx, Assessment, 1001, engagement_id=102)
        with ctx.factory() as database:
            database.add(EngagementAccessGrant(id=702, membership_id=501, engagement_id=102,
                         status="active", valid_from=NOW - timedelta(days=1),
                         expires_at=NOW + timedelta(days=1)))
            database.commit()
    elif move == "organization":
        update(ctx, Vendor, 11, organization_id=2)
        update(ctx, OrganizationMembership, 601, role=ROLE_ADMIN)
        with ctx.factory() as database:
            database.add(EngagementAccessGrant(id=802, membership_id=601, engagement_id=101,
                         status="active", valid_from=NOW - timedelta(days=1),
                         expires_at=NOW + timedelta(days=1)))
            database.commit()
        ctx.source.identity = AuthenticatedIdentity(
            Principal("reader-b", "Other reviewer", "other@synthetic.invalid", ROLE_ADMIN),
            ISSUER, "lma-synthetic", "sid_other", 2,
            NOW - timedelta(minutes=1), NOW + timedelta(minutes=30),
        )


def insert_synthetic_unknown_revision(ctx, kind, target, content):
    """Represent an old-version capture; current linkage proves no provenance."""
    with ctx.factory() as database:
        assessment = database.get(Assessment, 1001)
        vendor = database.get(Vendor, assessment.vendor_id)
        database.add(AnalystNoteRevision(
            organization_id=vendor.organization_id, vendor_id=vendor.id,
            engagement_id=assessment.engagement_id, assessment_id=assessment.id,
            evidence_id=target if kind == "evidence" else None,
            object_type=kind, object_id=target, content=content,
            origin="legacy_unknown", created_at=NOW,
        ))
        database.commit()


@pytest.mark.parametrize("kind,target", [("assessment", 1001), ("evidence", 9001)])
@pytest.mark.parametrize("move", ["unchanged", "organization", "engagement"])
def test_first_unattributed_note_is_quarantined_even_for_currently_authorized_owner(quarantine_guarded,
                                                                                 kind, target, move):
    ctx, service = quarantine_guarded
    model, field = (Assessment, "notes") if kind == "assessment" else (Evidence, "analyst_notes")
    legacy = "Private original rationale: unresolved material exception, source p.7."
    update(ctx, model, target, **{field: legacy})
    move_synthetic_target_scope(ctx, move)
    # Denial must concern unattributed content, not a missing current entitlement.
    assert getattr(service._reader, "get_" + kind)(target) is not None
    before = database_snapshot(ctx)
    assert before[-2] == [] and before[-1] == []
    history = getattr(service, "list_" + kind + "_note_revisions")
    record = getattr(service, "record_" + kind + "_review_note")
    assert history(target) == ()
    assert record(target, "New owner rationale") is False
    assert history(target) == ()
    assert database_snapshot(ctx) == before


@pytest.mark.parametrize("kind,target", [("assessment", 1001), ("evidence", 9001)])
@pytest.mark.parametrize("move", ["unchanged", "organization"])
@pytest.mark.parametrize("prior_analyst", [False, True])
def test_preexisting_unknown_revision_cannot_authorize_content_or_overwrite(quarantine_guarded, kind, target,
                                                                          move, prior_analyst):
    ctx, service = quarantine_guarded
    model, field = (Assessment, "notes") if kind == "assessment" else (Evidence, "analyst_notes")
    content = "Original private uncertainty; not an assurance conclusion."
    record = getattr(service, "record_" + kind + "_review_note")
    if prior_analyst:
        assert record(target, content)
    else:
        update(ctx, model, target, **{field: content})
    move_synthetic_target_scope(ctx, move)
    # Reproduce an earlier unsafe capture under the current (possibly new)
    # tenant. Matching content and present-day scope must not validate it.
    insert_synthetic_unknown_revision(ctx, kind, target, content)
    before = database_snapshot(ctx)
    assert before[-2][-1][-2:] == ("legacy_unknown", content)
    expected = [content] if prior_analyst and move == "unchanged" else []
    visible = getattr(service, "list_" + kind + "_note_revisions")(target)
    assert [row.content for row in visible] == expected
    assert all(row.origin == "analyst" for row in visible)
    assert record(target, "Cannot assign unknown provenance") is False
    assert database_snapshot(ctx) == before


@pytest.mark.parametrize("kind,target", [("assessment", 1001), ("evidence", 9001)])
def test_unknown_history_filter_precedes_pagination_without_deleting_captures(quarantine_guarded, kind, target):
    ctx, service = quarantine_guarded
    record = getattr(service, "record_" + kind + "_review_note")
    history = getattr(service, "list_" + kind + "_note_revisions")
    insert_synthetic_unknown_revision(ctx, kind, target, "Quarantined first capture")
    assert record(target, "First attributed note from an empty current field")
    assert record(target, "Second attributed note")
    insert_synthetic_unknown_revision(ctx, kind, target, "Quarantined later capture")
    before = database_snapshot(ctx)
    first = history(target, limit=1)
    assert [row.content for row in first] == ["First attributed note from an empty current field"]
    second = history(target, limit=1, after_id=first[0].id)
    assert [row.content for row in second] == ["Second attributed note"]
    assert history(target, limit=1, after_id=second[0].id) == ()
    assert database_snapshot(ctx) == before
    assert [row[-2] for row in before[-2]] == ["legacy_unknown", "analyst", "analyst", "legacy_unknown"]


@pytest.mark.parametrize("kind,target", [("assessment", 1002), ("assessment", 2001),
                                         ("evidence", 9002), ("evidence", 9201),
                                         ("evidence", 999999)])
def test_history_reads_reauthorize_exact_tenant_and_engagement(guarded, kind, target):
    _, service = guarded
    assert service.record_assessment_review_note(1001, "Confidential scoped rationale")
    assert service.record_evidence_review_note(9001, "Source-bound scoped rationale")
    assert getattr(service, "list_" + kind + "_note_revisions")(target) == ()


@pytest.mark.parametrize("mutation", ["membership", "grant", "role", "session",
                                     "membership_expiry", "grant_expiry", "session_expiry"])
def test_history_does_not_reuse_prior_access_after_revocation_or_rotation(guarded, mutation):
    ctx, service = guarded
    assert service.record_evidence_review_note(9001, "Original uncertainty retained")
    assert service.list_evidence_note_revisions(9001)
    if mutation == "membership":
        update(ctx, OrganizationMembership, 501, status="revoked")
    elif mutation == "grant":
        update(ctx, EngagementAccessGrant, 701, status="revoked")
    elif mutation == "role":
        update(ctx, OrganizationMembership, 501, role=ROLE_VIEWER)
    elif mutation in ("membership_expiry", "grant_expiry"):
        model, row_id = ((OrganizationMembership, 501) if mutation == "membership_expiry"
                         else (EngagementAccessGrant, 701))
        update(ctx, model, row_id, expires_at=NOW + timedelta(seconds=1))
        ctx.clock[0] += timedelta(seconds=1)
    elif mutation == "session_expiry":
        ctx.clock[0] = ctx.identity.expires_at
    else:
        ctx.source.identity = None
    assert service.list_evidence_note_revisions(9001) == ()


def test_history_discards_rows_when_final_session_lookup_rotates(guarded, monkeypatch):
    ctx, service = guarded
    assert service.record_evidence_review_note(9001, "Never release after observed rotation")
    original = ctx.source.authenticated_identity
    calls = [0]
    def rotate_at_final():
        calls[0] += 1
        if calls[0] == 2:
            ctx.source.identity = replace(ctx.identity, session_id="sid_history_rotated")
        return original()
    monkeypatch.setattr(ctx.source, "authenticated_identity", rotate_at_final)
    assert service.list_evidence_note_revisions(9001) == ()
    assert calls[0] == 2


def test_history_is_bounded_with_exclusive_keyset_pages(guarded):
    _, service = guarded
    for number in range(3):
        assert service.record_assessment_review_note(1001, f"Synthetic revision {number}")
    first = service.list_assessment_note_revisions(1001, limit=1)
    rest = service.list_assessment_note_revisions(1001, limit=2, after_id=first[0].id)
    assert [r.content for r in first + rest] == [f"Synthetic revision {number}" for number in range(3)]
    assert service.list_assessment_note_revisions(1001, after_id=rest[-1].id) == ()


@pytest.mark.parametrize("arguments", [{"limit": 0}, {"limit": 201}, {"limit": True},
                                       {"after_id": -1}, {"after_id": "0"}, {"after_id": True}])
def test_invalid_history_page_parameters_deny(guarded, arguments):
    _, service = guarded
    assert service.list_assessment_note_revisions(1001, **arguments) == ()
    assert service.list_evidence_note_revisions(9001, **arguments) == ()


@pytest.mark.parametrize("invalid", [None, True, 0, -1, "1001", {}, 1.1])
def test_invalid_history_target_denies(guarded, invalid):
    _, service = guarded
    assert service.list_assessment_note_revisions(invalid) == ()
    assert service.list_evidence_note_revisions(invalid) == ()


def test_reassigned_engagement_cannot_read_or_relabel_prior_rationale(guarded):
    ctx, service = guarded
    assert service.record_assessment_review_note(1001, "Engagement 101 source exception")
    update(ctx, Assessment, 1001, engagement_id=102)
    assert service.list_assessment_note_revisions(1001) == ()
    with ctx.factory() as database:
        database.add(EngagementAccessGrant(id=702, membership_id=501, engagement_id=102,
                     status="active", valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1)))
        database.commit()
    assert service.list_assessment_note_revisions(1001) == ()
    assert service.record_assessment_review_note(1001, "New engagement 102 rationale")
    visible = service.list_assessment_note_revisions(1001)
    assert [row.content for row in visible] == ["New engagement 102 rationale"]
    with ctx.factory() as database:
        all_rows = database.execute(select(AnalystNoteRevision).order_by(AnalystNoteRevision.id)).scalars().all()
        assert [(row.engagement_id, row.content) for row in all_rows] == [
            (101, "Engagement 101 source exception"), (102, "New engagement 102 rationale")]


def test_untracked_old_scope_text_cannot_be_imported_into_a_new_scope(guarded):
    ctx, service = guarded
    assert service.record_assessment_review_note(1001, "Original source exception")
    update(ctx, Assessment, 1001, notes="Untracked old engagement text", engagement_id=102)
    with ctx.factory() as database:
        database.add(EngagementAccessGrant(id=702, membership_id=501, engagement_id=102,
                     status="active", valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1)))
        database.commit()
    before = database_snapshot(ctx)
    assert not service.record_assessment_review_note(1001, "Cannot erase untracked old rationale")
    assert database_snapshot(ctx) == before


def test_new_tenant_cannot_read_prior_tenant_revisions_after_vendor_reassignment(guarded):
    ctx, service = guarded
    assert service.record_evidence_review_note(9001, "Organization A private rationale")
    update(ctx, Vendor, 11, organization_id=2)
    update(ctx, OrganizationMembership, 601, role=ROLE_ADMIN)
    with ctx.factory() as database:
        database.add(EngagementAccessGrant(id=802, membership_id=601, engagement_id=101,
                     status="active", valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1)))
        database.commit()
    ctx.source.identity = AuthenticatedIdentity(
        Principal("reader-b", "Other reviewer", "other@synthetic.invalid", ROLE_ADMIN),
        ISSUER, "lma-synthetic", "sid_other", 2,
        NOW - timedelta(minutes=1), NOW + timedelta(minutes=30),
    )
    assert service.list_evidence_note_revisions(9001) == ()
    assert service.record_evidence_review_note(9001, "Organization B new rationale")
    assert [row.content for row in service.list_evidence_note_revisions(9001)] == ["Organization B new rationale"]
    with ctx.factory() as database:
        rows = database.execute(select(AnalystNoteRevision).order_by(AnalystNoteRevision.id)).scalars().all()
        assert [(row.organization_id, row.content) for row in rows] == [
            (1, "Organization A private rationale"), (2, "Organization B new rationale")]
        audits = database.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
        assert [(row.organization_id, row.membership_id) for row in audits] == [(1, 501), (2, 601)]


def test_equal_subjects_at_different_issuers_produce_distinct_immutable_audit_identity(guarded):
    ctx, service = guarded
    assert service.record_assessment_review_note(1001, "Issuer A rationale")
    other_issuer = "https://other-id.synthetic.invalid"
    with ctx.factory() as database:
        database.add(OrganizationMembership(id=502, organization_id=1, issuer=other_issuer,
                     subject="reader-a", role=ROLE_ANALYST, status="active",
                     valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1)))
        database.flush()
        database.add(EngagementAccessGrant(id=702, membership_id=502, engagement_id=101,
                     status="active", valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1)))
        database.commit()
    ctx.source.identity = replace(ctx.identity, issuer=other_issuer, session_id="sid_issuer_b")
    assert service.record_assessment_review_note(1001, "Issuer B rationale")
    update(ctx, Vendor, 11, organization_id=2)
    with ctx.factory() as database:
        audits = database.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
        assert [(row.actor_subject, row.actor_issuer, row.organization_id, row.membership_id,
                 row.session_id) for row in audits] == [
            ("reader-a", ISSUER, 1, 501, ctx.identity.session_id),
            ("reader-a", other_issuer, 1, 502, "sid_issuer_b")]


@pytest.mark.parametrize("kind,target", [("assessment", 1001), ("evidence", 9001)])
def test_failed_revision_insert_rolls_back_legacy_note_history_and_audit(guarded, kind, target):
    ctx, service = guarded
    record = getattr(service, "record_" + kind + "_review_note")
    assert record(target, "Prior source-verifiable exception")
    before = database_snapshot(ctx)
    failures = []
    def failed_revision(mapper, connection, row):
        failures.append(row.content)
        raise RuntimeError("Synthetic revision storage failure")
    event.listen(AnalystNoteRevision, "before_insert", failed_revision)
    try:
        assert not record(target, "Never lose prior exception")
    finally:
        event.remove(AnalystNoteRevision, "before_insert", failed_revision)
    assert failures == ["Never lose prior exception"]
    assert database_snapshot(ctx) == before


@pytest.mark.parametrize("kind,target", [("assessment", 1001), ("evidence", 9001)])
def test_postgres_note_writer_uses_shared_issuance_lock_order(postgres_ctx, monkeypatch, kind, target):
    from concurrent.futures import ThreadPoolExecutor
    ctx = postgres_ctx
    monkeypatch.setattr(operations, "_utc_now", lambda: ctx.clock[0])
    service = TenantAssessmentEvidenceOperations(ctx.factory, identity_source=ctx.source)
    errors = []
    def capture_failure(exception_context):
        errors.append(getattr(exception_context.original_exception, "sqlstate", None))
    event.listen(ctx.engine, "handle_error", capture_failure)
    record = getattr(service, "record_" + kind + "_review_note")
    try:
        # A second physical connection attempts the actual note operation while
        # read/export's shared authority and parent locks are held.
        with ctx.service._authorized_transaction(PERMISSION_VENDOR_READ) as (session, scope):
            with ThreadPoolExecutor(max_workers=1) as executor:
                assert executor.submit(record, target, "Blocked concurrent note").result(timeout=8) is False
            assert "55P03" in errors
            ctx.service._finish_authorized(session, scope, PERMISSION_VENDOR_READ)
        assert record(target, "Committed after issuance")
        history = getattr(service, "list_" + kind + "_note_revisions")(target)
        assert [row.content for row in history] == ["Committed after issuance"]
    finally:
        event.remove(ctx.engine, "handle_error", capture_failure)


@pytest.mark.parametrize("kind,target", [("assessment", 1001), ("evidence", 9001)])
def test_postgres_concurrent_note_appends_preserve_both_rationales(postgres_ctx, monkeypatch, kind, target):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event, current_thread, local
    ctx = postgres_ctx
    monkeypatch.setattr(operations, "_utc_now", lambda: ctx.clock[0])
    service = TenantAssessmentEvidenceOperations(ctx.factory, identity_source=ctx.source)
    first_ready, second_attempt, release = Event(), Event(), Event()
    per_thread = local()
    original_identity = ctx.source.authenticated_identity
    def identity():
        value = original_identity()
        per_thread.calls = getattr(per_thread, "calls", 0) + 1
        if current_thread().name.startswith("first-note") and per_thread.calls == 2:
            first_ready.set()  # First revision/audit flushed, target locks held.
            if not release.wait(10):
                raise RuntimeError("Synthetic concurrent note coordination timed out")
        return value
    def before_sql(connection, cursor, statement, params, context, executemany):
        if current_thread().name.startswith("second-note") and "organization_memberships" in statement and "FOR UPDATE" in statement:
            second_attempt.set()
    monkeypatch.setattr(ctx.source, "authenticated_identity", identity)
    event.listen(ctx.engine, "before_cursor_execute", before_sql)
    record = getattr(service, "record_" + kind + "_review_note")
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="first-note") as first_pool, \
                ThreadPoolExecutor(max_workers=1, thread_name_prefix="second-note") as second_pool:
            first = first_pool.submit(record, target, "First source exception retained")
            try:
                assert first_ready.wait(10)
                second = second_pool.submit(record, target, "Second uncertainty retained")
                assert second_attempt.wait(10)
                with pytest.raises(TimeoutError):
                    second.result(timeout=0.2)
            finally:
                release.set()
            assert first.result(timeout=10)
            assert second.result(timeout=10)
        history = getattr(service, "list_" + kind + "_note_revisions")(target)
        assert [row.content for row in history] == ["First source exception retained", "Second uncertainty retained"]
        assert [row.origin for row in history] == ["analyst", "analyst"]
        with ctx.factory() as database:
            assert database.query(AuditLog).count() == 2
    finally:
        event.remove(ctx.engine, "before_cursor_execute", before_sql)
