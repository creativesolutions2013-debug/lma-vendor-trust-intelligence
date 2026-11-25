"""Analyst acceptance preserves originals and commits vendor provenance atomically.

These tests use only isolated synthetic databases. Vendor browser authorization
is tested separately; this private command receives server-generated capture
receipts and independently authenticated vendor delivery metadata.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json
from threading import Event
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.orm import sessionmaker

from src.db import EngagementAccessGrant, OrganizationMembership, SyntheticAssessmentRevision, SyntheticVendorHandoff
from src.resumable_assessment import SyntheticResumableAssessmentService
from src.server_sessions import InMemorySessionStore, SessionManager, VerifiedSubject
from src.session_identity_source import SessionIdentitySource
from test_resumable_assessment import assessment_ctx, _draft, _login, _saved, _source
from test_session_identity_source import ISSUER


VENDOR_ISSUER = "https://127.0.0.1:19443/vendor/synthetic-idp"


def _metadata(ctx, **changes):
    # A real server-owned session supplies correlation identity. No bearer
    # handle, invitation capability or browser-selected role is persisted.
    vendor_sessions = SessionManager(InMemorySessionStore(), clock=lambda: ctx.clock[0])
    vendor_handle = vendor_sessions.issue(VerifiedSubject(
        VENDOR_ISSUER, "synthetic-vendor", "lma-synthetic-vendor"))
    vendor = vendor_sessions.authenticate(vendor_handle)
    inviter = ctx.sessions.authenticate(ctx.handle)
    assert vendor is not None and inviter is not None
    assert vendor.session_id != vendor_handle and inviter.session_id != ctx.handle
    metadata = dict(schema_version=1, invitation_id=uuid4().hex,
        vendor_issuer=vendor.issuer, vendor_subject=vendor.subject,
        vendor_session_id=vendor.session_id, vendor_role="Authenticated synthetic invitee",
        submitted_at=ctx.clock[0].isoformat(), kind="test", observed_on=ctx.clock[0].date().isoformat(),
        requirement_id="BCP-01", inviter_issuer=inviter.issuer,
        inviter_subject=inviter.subject, inviter_session_id=inviter.session_id)
    metadata.update(changes)
    return metadata


def _test_bytes(ctx, *, suffix=""):
    return (f"Completed synthetic recovery exercise{suffix}.\nService: {ctx.intake.service}\n"
            f"Environment: {ctx.intake.environment}\nObservation date: {ctx.clock[0].date()}\n"
            "Achieved RTO 300 minutes and RPO 90 minutes.\n"
            "Identity service was excluded from the exercise.\n").encode()


def _stage(ctx, *, name="vendor-recovery-test.txt", content=None):
    return _source(ctx, name, _test_bytes(ctx) if content is None else content, kind="test")[1]


def _append(ctx, revision, receipt, metadata=None):
    return ctx.service.append_vendor_source(1001, expected_revision=revision,
        receipt=receipt, metadata=_metadata(ctx) if metadata is None else metadata)


def _snapshot(ctx):
    with ctx.factory() as database:
        return tuple(tuple(database.execute(select(model.__table__).order_by(
            *model.__table__.primary_key.columns)).all())
            for model in (SyntheticAssessmentRevision, SyntheticVendorHandoff))


def test_vendor_append_stales_only_changed_requirement_and_exports_exact_originals_after_new_session(assessment_ctx):
    ctx = assessment_ctx
    tls = _source(ctx, "tls-configuration.txt", (
        f"TLS configuration export\nService: {ctx.intake.service}\nEnvironment: {ctx.intake.environment}\n"
        f"Observation date: {ctx.clock[0].date()}\nListener 443: TLS 1.0 is enabled.\n").encode(),
        requirements=("ENC-01",), kind="configuration")
    dr = _source(ctx)
    saved = _saved(ctx, _draft(ctx, (tls, dr)))
    tls_review = ctx.service.record_review(1001, expected_revision=saved.revision,
        requirement_id="ENC-01", action="Create Finding", rationale="Synthetic TLS exposure needs validation.")
    assert tls_review is not None
    dr_review = ctx.service.record_review(1001, expected_revision=tls_review.revision,
        requirement_id="BCP-01", action="Request Evidence", confirms_insufficiency=True,
        rationale="Provide completed recovery metrics and actual dependency coverage.")
    assert dr_review is not None
    finished = ctx.service.finish(1001, expected_revision=dr_review.revision)
    before = ctx.service.resume(1001)
    assert finished is not None and before.completion is not None and not before.completion_stale
    assert {action["status"] for action in before.report["analyst_actions"]} == {"Current"}
    receipt, content = _stage(ctx), _test_bytes(ctx)
    metadata = _metadata(ctx)
    appended = _append(ctx, finished.revision, receipt, metadata)
    assert appended is not None and appended.revision == finished.revision + 1

    # Recovery uses a fresh server session/service, not cached pending bytes or
    # a trusted report snapshot retained by the receiving browser.
    assert ctx.sessions.revoke(ctx.handle)
    _login(ctx)
    result = ctx.service.resume(1001)
    assert result is not None and result.revision == appended.revision
    assert result.completion is None and result.completion_stale
    assert result.actions == before.actions
    states = {action["requirement_id"]: action["status"] for action in result.report["analyst_actions"]}
    assert states == {"ENC-01": "Current", "BCP-01": "Stale context"}
    assert result.report["evidence_gap_reviews"][0]["status"] == "Stale context"
    originals = {upload.evidence.source.filename: upload.evidence.source.content for upload in result.uploads}
    assert originals == {tls[1].document_name: tls[0].evidence.source.content,
                         dr[1].document_name: dr[0].evidence.source.content, receipt.document_name: content}
    provenance = result.report["persistence"]["source_custody"]
    delivered = next(item for item in provenance if item["evidence_id"] == receipt.evidence_id)
    assert delivered["sha256"] == sha256(content).hexdigest()
    assert delivered["generation"] == receipt.generation and delivered["vendor_delivery"] == metadata
    assert delivered["capture_actor"]["subject"] == "reader"
    assert all(item["vendor_delivery"] is None for item in provenance if item is not delivered)
    row = next(row for row in result.report["requirements"] if row["requirement_id"] == "BCP-01")
    assert any(citation["filename"] == receipt.document_name and citation["quote"] in content.decode()
               for citation in row["citations"])
    assert result.report["risk"]["residual_score"] is None
    assert result.report["review_completion"]["vendor_approved"] is False
    assert all(row["outcome"] not in ("Met", "Risk Identified") for row in result.report["requirements"])
    with ZipFile(BytesIO(result.package)) as archive:
        assert json.loads(archive.read("report.json")) == result.report
        artifacts = json.loads(archive.read("manifest.json"))["artifacts"]
        assert len(artifacts) == 3
        for artifact in artifacts:
            original = originals[artifact["filename"]]
            assert archive.read(artifact["archive_path"]) == original
            assert artifact["sha256"] == sha256(original).hexdigest()


@pytest.mark.parametrize("duplicate", ["name", "hash", "receipt"])
def test_duplicate_vendor_original_is_rejected_without_provenance_or_revision(assessment_ctx, duplicate):
    ctx = assessment_ctx
    original = _source(ctx)
    saved = _saved(ctx, _draft(ctx, (original,)))
    if duplicate == "receipt":
        receipt = original[1]
    elif duplicate == "name":
        receipt = _stage(ctx, name=original[1].document_name)
    else:
        receipt = _stage(ctx, content=original[0].evidence.source.content)
    before = _snapshot(ctx)
    assert _append(ctx, saved.revision, receipt) is None
    assert _snapshot(ctx) == before
    assert len(ctx.service.resume(1001).uploads) == 1


def test_full_source_inventory_refuses_fifth_original_without_dropping_any(assessment_ctx):
    ctx = assessment_ctx
    sources = tuple(_source(ctx, f"analyst-source-{index}.txt", f"Synthetic original {index}".encode())
                    for index in range(4))
    saved = _saved(ctx, _draft(ctx, sources))
    receipt = _stage(ctx)
    before = _snapshot(ctx)
    assert _append(ctx, saved.revision, receipt) is None
    assert _snapshot(ctx) == before
    result = ctx.service.resume(1001)
    assert [upload.evidence.source.content for upload in result.uploads] == [u.evidence.source.content for u, _ in sources]


@pytest.mark.parametrize("revision", [0, 2, True, -1])
def test_expected_revision_conflict_does_not_append_or_claim_delivery(assessment_ctx, revision):
    ctx = assessment_ctx
    _saved(ctx)
    receipt = _stage(ctx)
    before = _snapshot(ctx)
    assert _append(ctx, revision, receipt) is None
    assert _snapshot(ctx) == before


@pytest.mark.parametrize("field,value", [
    ("assessment_id", 1002), ("organization_id", 2), ("vendor_id", 22),
    ("engagement_id", 102), ("evidence_id", 999999), ("generation", "f" * 32),
    ("sha256", "f" * 64), ("byte_length", 1), ("document_name", "forged.txt"),
    ("subject", "forged-capture-actor"),
])
def test_changed_capture_receipt_cannot_substitute_an_original(assessment_ctx, field, value):
    ctx = assessment_ctx
    saved = _saved(ctx)
    receipt = _stage(ctx)
    before = _snapshot(ctx)
    assert _append(ctx, saved.revision, replace(receipt, **{field: value})) is None
    assert _snapshot(ctx) == before


@pytest.mark.parametrize("changes", [
    {"schema_version": 2}, {"vendor_subject": "synthetic-analyst"},
    {"vendor_role": "Analyst"}, {"vendor_session_id": "bearer-cannot-be-provenance"},
    {"invitation_id": "token-instead-of-public-id"}, {"kind": "approved"},
    {"observed_on": "not-a-date"}, {"observed_on": "2099-01-01"},
    {"requirement_id": "UNKNOWN-REQUIREMENT"}, {"approval": True},
])
def test_invalid_vendor_declarations_and_nonapplicable_requirement_deny(assessment_ctx, changes):
    ctx = assessment_ctx
    saved = _saved(ctx)
    receipt = _stage(ctx)
    before = _snapshot(ctx)
    assert _append(ctx, saved.revision, receipt, _metadata(ctx, **changes)) is None
    assert _snapshot(ctx) == before


@pytest.mark.parametrize("authority", ["membership", "grant", "session"])
def test_append_reauthorizes_after_original_capture(assessment_ctx, authority):
    ctx = assessment_ctx
    saved = _saved(ctx)
    receipt = _stage(ctx)
    metadata = _metadata(ctx)
    if authority == "session":
        assert ctx.sessions.revoke(ctx.handle)
    else:
        model, identifier = ((OrganizationMembership, 501) if authority == "membership"
                             else (EngagementAccessGrant, 701))
        with ctx.factory.begin() as database:
            database.execute(update(model).where(model.id == identifier).values(status="revoked"))
    before = _snapshot(ctx)
    assert _append(ctx, saved.revision, receipt, metadata) is None
    assert _snapshot(ctx) == before


@pytest.mark.parametrize("failure", ["handoff_insert", "revision_insert", "commit"])
def test_revision_and_handoff_provenance_roll_back_together_on_failure(assessment_ctx, failure):
    ctx = assessment_ctx
    saved = _saved(ctx)
    receipt = _stage(ctx)
    metadata, before, invoked = _metadata(ctx), _snapshot(ctx), []

    def fail_insert(_connection, _cursor, statement, _parameters, _context, _many):
        normalized = statement.lstrip().upper().replace('"', '')
        target = (SyntheticVendorHandoff if failure == "handoff_insert" else SyntheticAssessmentRevision).__tablename__.upper()
        if normalized.startswith("INSERT INTO ") and target in normalized:
            invoked.append(True)
            raise RuntimeError("Synthetic append failure")

    def fail_commit(_database):
        invoked.append(True)
        raise RuntimeError("Synthetic append commit failure")

    target, name, hook = ((ctx.factory, "before_commit", fail_commit) if failure == "commit"
                          else (ctx.engine, "before_cursor_execute", fail_insert))
    event.listen(target, name, hook)
    try:
        assert _append(ctx, saved.revision, receipt, metadata) is None
        assert invoked == [True], "fault did not reach the intended write boundary"
    finally:
        event.remove(target, name, hook)
    assert _snapshot(ctx) == before
    assert len(ctx.service.resume(1001).uploads) == 1


def test_lost_append_acknowledgement_recovers_durable_source_and_blocks_duplicate_retry(assessment_ctx, monkeypatch):
    ctx = assessment_ctx
    saved = _saved(ctx)
    receipt = _stage(ctx)
    metadata, cleanup, invoked = _metadata(ctx), ctx.sessions._store.operation_lease, []

    @contextmanager
    def failed_cleanup(key):
        with cleanup(key):
            yield
        invoked.append(True)
        raise RuntimeError("Synthetic acknowledgement lost after commit")

    with monkeypatch.context() as patch:
        patch.setattr(ctx.sessions._store, "operation_lease", failed_cleanup)
        assert _append(ctx, saved.revision, receipt, metadata) is None
        assert invoked == [True]
    latest = ctx.service.resume(1001)
    assert latest is not None and latest.revision == saved.revision + 1 and len(latest.uploads) == 2
    delivered = next(item for item in latest.report["persistence"]["source_custody"]
                     if item["evidence_id"] == receipt.evidence_id)
    assert delivered["vendor_delivery"] == metadata
    before = _snapshot(ctx)
    assert _append(ctx, saved.revision, receipt, metadata) is None
    assert _append(ctx, latest.revision, receipt, metadata) is None
    assert _snapshot(ctx) == before


def test_postgres_concurrent_different_vendor_originals_append_once_at_same_expected_revision(assessment_ctx):
    ctx = assessment_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires isolated Actions PostgreSQL and independent connections")
    saved = _saved(ctx)
    first_receipt = _stage(ctx, name="vendor-test-one.txt", content=_test_bytes(ctx, suffix=" one"))
    second_receipt = _stage(ctx, name="vendor-test-two.txt", content=_test_bytes(ctx, suffix=" two"))
    first_metadata, second_metadata = _metadata(ctx), _metadata(ctx)
    manager = SessionManager(InMemorySessionStore(), clock=lambda: ctx.clock[0])
    handle = manager.issue(VerifiedSubject(ISSUER, "reader", "synthetic-client"))
    factory = sessionmaker(bind=ctx.engine, expire_on_commit=False, autoflush=False)
    source = SessionIdentitySource(manager, handle, factory, clock=lambda: ctx.clock[0])
    competitor = SyntheticResumableAssessmentService(factory, identity_source=source)
    committing, release, second_sql = Event(), Event(), Event()

    def pause(_database):
        committing.set()
        assert release.wait(5), "first vendor append was not released"

    def observe(orm_execute):
        if getattr(orm_execute.statement, "_for_update_arg", None) is not None:
            second_sql.set()

    event.listen(ctx.factory, "before_commit", pause)
    event.listen(factory, "do_orm_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(_append, ctx, saved.revision, first_receipt, first_metadata)
            try:
                assert committing.wait(5)
                second = workers.submit(competitor.append_vendor_source, 1001,
                    expected_revision=saved.revision, receipt=second_receipt, metadata=second_metadata)
                assert second_sql.wait(5), "competing append did not reach SQL row locking"
                assert not second.done(), "competing append bypassed the held assessment lock"
            finally:
                release.set()
            assert first.result(timeout=10) is not None
            assert second.result(timeout=10) is None
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause)
        event.remove(factory, "do_orm_execute", observe)
    latest = ctx.service.resume(1001)
    assert latest.revision == saved.revision + 1
    assert {upload.evidence.source.filename for upload in latest.uploads} == {
        "recovery-plan.txt", first_receipt.document_name}
    with ctx.factory() as database:
        assert database.execute(select(SyntheticVendorHandoff.evidence_id)).scalars().all() == [first_receipt.evidence_id]
