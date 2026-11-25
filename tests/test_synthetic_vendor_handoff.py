"""Separate authenticated vendor delivery; disposable SQLite/PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace
from threading import Event

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from src.authz import ROLE_VIEWER
from src.db import Assessment, EngagementAccessGrant, OrganizationMembership, SyntheticEvidenceObject, Vendor
from src.resumable_assessment_state import encode_draft
from src.server_sessions import InMemorySessionStore, SessionManager, VerifiedSubject
from src.synthetic_vendor_handoff import SyntheticVendorHandoff
from test_resumable_assessment import assessment_ctx, _saved, _source
from test_session_identity_source import ISSUER


VENDOR_ISSUER = "https://vendor.synthetic.invalid"
VENDOR_SUBJECT = "synthetic-vendor"
VENDOR_CONTENT = b"Synthetic completed recovery test. RTO 30 minutes and RPO 10 minutes.\n"


@pytest.fixture
def handoff_ctx(assessment_ctx):
    ctx = assessment_ctx
    ctx.upload, ctx.receipt = _source(ctx)
    _saved(ctx, encode_draft(ctx.intake, (ctx.upload,), (ctx.receipt,)))
    clock = lambda: ctx.clock[0]
    ctx.sessions = SessionManager(InMemorySessionStore(), clock=clock, idle_seconds=3600, absolute_seconds=7200)
    ctx.handle = ctx.sessions.issue(VerifiedSubject(ISSUER, "reader", "synthetic-client"))
    ctx.identity = SimpleNamespace(sessions=ctx.sessions, clock=clock)
    vendor_sessions = SessionManager(InMemorySessionStore(), clock=clock, idle_seconds=3600, absolute_seconds=7200)
    ctx.vendor = SimpleNamespace(sessions=vendor_sessions, clock=clock)
    ctx.vendor_handle = vendor_sessions.issue(VerifiedSubject(VENDOR_ISSUER, VENDOR_SUBJECT, "vendor-client"))
    ctx.handoff = SyntheticVendorHandoff(ctx.factory, 1001, VENDOR_ISSUER, VENDOR_SUBJECT, clock=clock)
    return ctx


def invite(ctx):
    result = ctx.handoff.create(ctx.handle, ctx.identity, 1, "BCP-01")
    assert result is not None
    return result


def deliver(ctx, issued, **changes):
    values = dict(handle=ctx.vendor_handle, identity=ctx.vendor, token=issued.token,
        filename="vendor-recovery.txt", content=VENDOR_CONTENT, kind="test", observed_on=ctx.clock[0].date())
    values.update(changes)
    return ctx.handoff.submit(**values)


def count(ctx):
    with ctx.factory() as database:
        return database.execute(select(func.count()).select_from(SyntheticEvidenceObject)).scalar_one()


def test_distinct_vendor_delivers_exact_pending_bytes_without_membership_custody_or_analysis(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert issued.token not in repr(issued) and issued.token not in repr(ctx.handoff._records)
    assert ctx.handoff.get_pending(ctx.handle, ctx.identity, issued.invitation_id) is None
    before = count(ctx)
    assert deliver(ctx, issued)
    assert count(ctx) == before
    pending = ctx.handoff.get_pending(ctx.handle, ctx.identity, issued.invitation_id)
    assert pending.content == VENDOR_CONTENT and pending.sha256 == sha256(VENDOR_CONTENT).hexdigest()
    assert pending.byte_length == len(VENDOR_CONTENT) and pending.receipt is None
    assert pending.vendor_issuer == VENDOR_ISSUER and pending.vendor_subject == VENDOR_SUBJECT
    assert pending.vendor_role == "Authenticated synthetic invitee"
    assert pending.vendor_session_id == ctx.vendor.sessions.authenticate(ctx.vendor_handle).session_id
    assert pending.inviter_issuer == ISSUER and pending.inviter_subject == "reader"
    assert pending.requirement_id == "BCP-01"
    assert not deliver(ctx, issued)
    assert ctx.handoff.get_pending(ctx.vendor_handle, ctx.vendor, issued.invitation_id) is None
    assert ctx.handoff.list_invitations(ctx.vendor_handle, ctx.vendor) is None
    with ctx.factory() as database:
        assert not database.execute(select(OrganizationMembership.id).where(
            OrganizationMembership.subject == VENDOR_SUBJECT)).all()


def test_token_without_independent_fixed_vendor_session_denies_and_does_not_consume(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert not deliver(ctx, issued, identity=ctx.identity, handle=ctx.handle)
    other = ctx.vendor.sessions.issue(VerifiedSubject(VENDOR_ISSUER, "unrelated-vendor", "vendor-client"))
    assert not deliver(ctx, issued, handle=other)
    assert not deliver(ctx, issued, handle="x" * 43)
    assert deliver(ctx, issued)


@pytest.mark.parametrize("operation", ["revoke", "rotate", "expire"])
def test_inviter_session_revocation_rotation_or_expiry_invalidates_unsubmitted_invitation(handoff_ctx, operation):
    ctx = handoff_ctx
    issued = invite(ctx)
    if operation == "expire":
        ctx.clock[0] += timedelta(hours=2)
    else:
        assert getattr(ctx.sessions, operation)(ctx.handle)
    assert not deliver(ctx, issued) and count(ctx) == 1


@pytest.mark.parametrize("operation", ["revoke", "rotate", "expire"])
def test_vendor_session_revocation_rotation_or_expiry_denies_delivery(handoff_ctx, operation):
    ctx = handoff_ctx
    issued = invite(ctx)
    if operation == "expire":
        ctx.clock[0] += timedelta(hours=2)
    else:
        assert getattr(ctx.vendor.sessions, operation)(ctx.vendor_handle)
    assert not deliver(ctx, issued) and count(ctx) == 1


@pytest.mark.parametrize("model,identifier,changes", [
    (OrganizationMembership, 501, {"status": "revoked"}),
    (OrganizationMembership, 501, {"role": ROLE_VIEWER}),
    (EngagementAccessGrant, 701, {"status": "revoked"}),
    (Assessment, 1001, {"assessment_type": "Changed assessment scope"}),
    (Vendor, 11, {"display_name": "Changed vendor scope"}),
])
def test_changed_authorization_or_ownership_denies_pending_delivery(handoff_ctx, model, identifier, changes):
    ctx = handoff_ctx
    issued = invite(ctx)
    with ctx.factory.begin() as database:
        database.execute(update(model).where(model.id == identifier).values(**changes))
    assert not deliver(ctx, issued) and count(ctx) == 1


@pytest.mark.parametrize("model,identifier,changes", [
    (Assessment, 1001, {"engagement_id": 102}), (Vendor, 11, {"organization_id": 2}),
])
def test_existing_custody_guards_prevent_reparenting_issued_invitation(handoff_ctx, model, identifier, changes):
    ctx = handoff_ctx
    issued = invite(ctx)
    with pytest.raises(DBAPIError), ctx.factory.begin() as database:
        database.execute(update(model).where(model.id == identifier).values(**changes))
    assert deliver(ctx, issued) and count(ctx) == 1


def test_stale_expected_revision_denies_instead_of_replacing_existing_sources(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert ctx.service.record_review(1001, expected_revision=1, requirement_id="BCP-01",
        action="Challenge", rationale="Review source meaning.") is not None
    assert not deliver(ctx, issued) and count(ctx) == 1


def test_completed_delivery_survives_logout_and_fresh_analyst_session(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert deliver(ctx, issued)
    assert ctx.sessions.revoke(ctx.handle)
    assert ctx.vendor.sessions.revoke(ctx.vendor_handle)
    assert ctx.handoff.get_pending(ctx.handle, ctx.identity, issued.invitation_id) is None
    fresh = ctx.sessions.issue(VerifiedSubject(ISSUER, "reader", "synthetic-client"))
    assert ctx.handoff.get_pending(fresh, ctx.identity, issued.invitation_id).content == VENDOR_CONTENT


def test_review_only_revision_change_keeps_pending_but_changed_context_withholds_it(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert deliver(ctx, issued)
    assert ctx.service.record_review(1001, expected_revision=1, requirement_id="BCP-01",
        action="Challenge", rationale="Review source meaning.") is not None
    assert ctx.handoff.get_pending(ctx.handle, ctx.identity, issued.invitation_id) is not None
    changed = replace(ctx.intake, use_case="Changed assessment purpose")
    draft = encode_draft(changed, (ctx.upload,), (ctx.receipt,))
    assert ctx.service.save(1001, expected_revision=2, draft=draft) is not None
    assert ctx.handoff.get_pending(ctx.handle, ctx.identity, issued.invitation_id) is None


@pytest.mark.parametrize("filename,content", [("../unsafe.txt", VENDOR_CONTENT),
    ("vendor.pdf", VENDOR_CONTENT), ("vendor.txt", b""), ("vendor.txt", b"X" * 65537),
    ("vendor.txt", b"\xff\xfe"), ("control\x00.txt", VENDOR_CONTENT)])
def test_malformed_sources_deny_before_consumption_and_preserve_inventory(handoff_ctx, filename, content):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert not deliver(ctx, issued, filename=filename, content=content)
    assert deliver(ctx, issued) and count(ctx) == 1


@pytest.mark.parametrize("duplicate", ["name", "hash"])
def test_duplicate_existing_original_denies_without_drop_or_replacement(handoff_ctx, duplicate):
    ctx = handoff_ctx
    issued = invite(ctx)
    changes = {"filename": ctx.receipt.document_name} if duplicate == "name" else {
        "content": ctx.upload.evidence.source.content}
    assert not deliver(ctx, issued, **changes) and count(ctx) == 1


def test_expired_revoked_unknown_and_other_process_tokens_deny(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    other = SyntheticVendorHandoff(ctx.factory, 1001, VENDOR_ISSUER, VENDOR_SUBJECT, clock=ctx.identity.clock)
    assert not other.submit(ctx.vendor_handle, ctx.vendor, issued.token, "vendor.txt", VENDOR_CONTENT)
    assert not deliver(ctx, issued, token="x" * 43)
    assert ctx.handoff.revoke(ctx.handle, ctx.identity, issued.invitation_id)
    assert not deliver(ctx, issued)
    second = invite(ctx)
    ctx.clock[0] += timedelta(minutes=10)
    assert not deliver(ctx, second)
    assert count(ctx) == 1


def test_concurrent_same_token_deliveries_accept_exactly_once_on_real_backend(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: deliver(ctx, issued), range(2)))
    assert sorted(results) == [False, True]
    assert count(ctx) == 1
    assert len(ctx.handoff.list_invitations(ctx.handle, ctx.identity)) == 1


def test_capture_is_separate_authorized_once_and_retains_confirmed_receipt(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert deliver(ctx, issued)
    pending = ctx.handoff.begin_capture(ctx.handle, ctx.identity, issued.invitation_id)
    assert pending is not None
    assert ctx.handoff.begin_capture(ctx.handle, ctx.identity, issued.invitation_id) is None
    receipt = ctx.custody.save(1001, pending.content, document_name=pending.filename)
    assert receipt is not None and receipt.subject == "reader"
    assert ctx.handoff.record_capture(ctx.handle, ctx.identity, issued.invitation_id, receipt)
    assert ctx.handoff.get_pending(ctx.handle, ctx.identity, issued.invitation_id).receipt == receipt
    assert ctx.handoff.begin_capture(ctx.handle, ctx.identity, issued.invitation_id) is None
    assert ctx.handoff.mark_imported(ctx.handle, ctx.identity, issued.invitation_id)
    assert ctx.handoff.get_pending(ctx.handle, ctx.identity, issued.invitation_id) is None
    assert count(ctx) == 2


def test_ambiguous_capture_is_terminal_without_restage_or_destructive_cleanup(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert deliver(ctx, issued)
    assert ctx.handoff.begin_capture(ctx.handle, ctx.identity, issued.invitation_id) is not None
    assert ctx.handoff.mark_unconfirmed(ctx.handle, ctx.identity, issued.invitation_id)
    assert ctx.handoff.begin_capture(ctx.handle, ctx.identity, issued.invitation_id) is None
    assert ctx.handoff.get_pending(ctx.handle, ctx.identity, issued.invitation_id) is None
    assert not deliver(ctx, issued) and count(ctx) == 1


def test_explicit_four_original_capacity_is_refused_before_inviting(handoff_ctx):
    ctx = handoff_ctx
    sources = [(ctx.upload, ctx.receipt)] + [_source(ctx, f"source-{n}.txt", f"Synthetic source {n}".encode())
                                          for n in range(3)]
    uploads, receipts = zip(*sources)
    assert ctx.service.save(1001, expected_revision=1,
        draft=encode_draft(ctx.intake, tuple(uploads), tuple(receipts))) is not None
    assert ctx.handoff.create(ctx.handle, ctx.identity, 2, "BCP-01") is None
    assert count(ctx) == 4


def test_inbox_record_count_is_bounded_without_retaining_raw_tokens(handoff_ctx):
    ctx = handoff_ctx
    for _ in range(32):
        issued = invite(ctx)
        assert ctx.handoff.revoke(ctx.handle, ctx.identity, issued.invitation_id)
    assert ctx.handoff.create(ctx.handle, ctx.identity, 1, "BCP-01") is None
    assert len(ctx.handoff._records) == 32


def test_revocation_serializes_with_complete_capture_import_operation(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert deliver(ctx, issued)
    entered, release, revoking, revoked = Event(), Event(), Event(), Event()

    def importing():
        with ctx.handoff.capture_operation(ctx.handle, ctx.identity, issued.invitation_id) as allowed:
            assert allowed
            pending = ctx.handoff.begin_capture(ctx.handle, ctx.identity, issued.invitation_id)
            assert pending is not None
            entered.set()
            assert release.wait(5)
            receipt = ctx.custody.save(1001, pending.content, document_name=pending.filename)
            assert receipt is not None
            assert ctx.handoff.record_capture(ctx.handle, ctx.identity, issued.invitation_id, receipt)
            assert ctx.handoff.mark_imported(ctx.handle, ctx.identity, issued.invitation_id)
            return True

    def revoking_import():
        revoking.set()
        result = ctx.handoff.revoke(ctx.handle, ctx.identity, issued.invitation_id)
        revoked.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        importing_result = pool.submit(importing)
        assert entered.wait(5)
        revoking_result = pool.submit(revoking_import)
        assert revoking.wait(5)
        assert not revoked.wait(.1)
        release.set()
        assert importing_result.result(timeout=5)
        assert revoking_result.result(timeout=5) is False
    assert ctx.handoff.list_invitations(ctx.handle, ctx.identity)[0].status == "imported"


def test_revocation_before_capture_guard_denies_and_caller_exceptions_propagate(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert deliver(ctx, issued)
    with pytest.raises(RuntimeError, match="caller failure"):
        with ctx.handoff.capture_operation(ctx.handle, ctx.identity, issued.invitation_id) as allowed:
            assert allowed
            raise RuntimeError("caller failure")
    assert ctx.handoff.revoke(ctx.handle, ctx.identity, issued.invitation_id)
    with ctx.handoff.capture_operation(ctx.handle, ctx.identity, issued.invitation_id) as allowed:
        assert not allowed
    assert count(ctx) == 1


def test_reentrant_revocation_cannot_acknowledge_pending_intake_during_import(handoff_ctx):
    ctx = handoff_ctx
    issued = invite(ctx)
    assert deliver(ctx, issued)
    with ctx.handoff.capture_operation(ctx.handle, ctx.identity, issued.invitation_id) as allowed:
        assert allowed
        pending = ctx.handoff.begin_capture(ctx.handle, ctx.identity, issued.invitation_id)
        receipt = ctx.custody.save(1001, pending.content, document_name=pending.filename)
        assert receipt is not None
        assert ctx.handoff.record_capture(ctx.handle, ctx.identity, issued.invitation_id, receipt)
        # A callback on this thread can reenter an RLock. The explicit active
        # reservation must still refuse a successful revocation acknowledgment.
        assert not ctx.handoff.revoke(ctx.handle, ctx.identity, issued.invitation_id)
        with ctx.handoff.capture_operation(ctx.handle, ctx.identity, issued.invitation_id) as nested:
            assert not nested
        assert ctx.handoff.mark_imported(ctx.handle, ctx.identity, issued.invitation_id)
    assert not ctx.handoff.revoke(ctx.handle, ctx.identity, issued.invitation_id)
