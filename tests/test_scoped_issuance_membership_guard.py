"""Synthetic issuance regressions across export, note writes and note history."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from test_tenant_read_scope import ISSUER, NOW, ctx, postgres_ctx, update
from test_tenant_assessment_evidence_operations import database_snapshot
from src.authz import ROLE_ADMIN
from src.db import OrganizationMembership
import src.tenant_assessment_evidence_operations as operations
from src.tenant_assessment_evidence_operations import TenantAssessmentEvidenceOperations
from src.tenant_report_export import TenantReportService


OPERATIONS = ("export", "assessment_write", "evidence_write",
              "assessment_history", "evidence_history")
NOTE = "Synthetic source exception remains provisional; analyst review required."


def operation(ctx, name):
    if name == "export":
        update(ctx, OrganizationMembership, 501, role=ROLE_ADMIN)
        service = TenantReportService(ctx.factory, identity_source=ctx.source)
        return service._reader, service.build
    service = TenantAssessmentEvidenceOperations(ctx.factory, identity_source=ctx.source)
    kind, action = name.split("_")
    target = 1001 if kind == "assessment" else 9001
    record = getattr(service, "record_" + kind + "_review_note")
    if action == "history":
        assert record(target, NOTE)
        history = getattr(service, "list_" + kind + "_note_revisions")
        return service._reader, lambda: history(target)
    return service._reader, lambda: record(target, NOTE)


def assert_success(name, result, before, after):
    if name == "export":
        assert result is not None
        assert [(row.vendor_id, row.engagement_id, row.assessments, row.evidence_items)
                for row in result.rows] == [(11, 101, 1, 1)]
        assert result.csv_bytes
        assert after == before
    elif name.endswith("_history"):
        assert [row.content for row in result] == [NOTE]
        assert after == before
    else:
        assert result is True
        assert len(after[-2]) == len(before[-2]) + 1  # One committed revision.
        assert len(after[-1]) == len(before[-1]) + 1  # One atomic audit record.
        assert after[-2][-1][-1] == NOTE
        if name == "assessment_write":
            assert after[0] == NOTE
            assert after[1:7] == before[1:7]
        else:
            assert after[4] == NOTE
            assert after[:4] == before[:4]
            assert after[5:7] == before[5:7]


def assert_denied(name, result):
    if name == "export":
        assert result is None
    elif name.endswith("_write"):
        assert result is False
    else:
        assert result == ()


def insert_ambiguous_membership(ctx):
    with ctx.factory() as database:
        # Core SQL bypasses the service/ORM write paths: the database trigger
        # must coordinate this newly inserted row with the issuance lock.
        database.execute(OrganizationMembership.__table__.insert(), dict(
            id=951, organization_id=2, issuer=ISSUER, subject="reader-a",
            role="Analyst", status="active", valid_from=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=1),
        ))
        database.commit()


@pytest.mark.parametrize("name", OPERATIONS)
def test_postgres_scoped_issuance_blocks_new_membership_after_final_validation(
        postgres_ctx, monkeypatch, name):
    ctx = postgres_ctx
    monkeypatch.setattr(operations, "_utc_now", lambda: ctx.clock[0])
    reader, call = operation(ctx, name)
    before = database_snapshot(ctx)
    validated, release = Event(), Event()
    original = reader._finish_authorized

    def finish(*args, **kwargs):
        original(*args, **kwargs)
        validated.set()  # All final SQL checks finished; commit has not begun.
        if not release.wait(10):
            raise RuntimeError("Synthetic issuance coordination timed out")

    monkeypatch.setattr(reader, "_finish_authorized", finish)

    def concurrent_insert():
        with ctx.factory() as database:
            database.execute(text("SET LOCAL lock_timeout = '500ms'"))
            with pytest.raises(OperationalError) as failure:
                database.execute(OrganizationMembership.__table__.insert(), dict(
                    id=951, organization_id=2, issuer=ISSUER, subject="reader-a",
                    role="Analyst", status="active", valid_from=NOW - timedelta(days=1),
                    expires_at=NOW + timedelta(days=1),
                ))
            assert getattr(failure.value.orig, "sqlstate", None) == "55P03"
            database.rollback()

    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(call)
        try:
            assert validated.wait(10), "Operation must reach the post-validation issuance window"
            executor.submit(concurrent_insert).result(timeout=10)
        finally:
            release.set()
        result = pending.result(timeout=10)

    after = database_snapshot(ctx)
    assert_success(name, result, before, after)
    monkeypatch.setattr(reader, "_finish_authorized", original)
    insert_ambiguous_membership(ctx)  # Succeeds only after transaction issuance.
    assert_denied(name, call())
    assert database_snapshot(ctx) == after  # No partial note, revision or audit.


@pytest.fixture(params=("sqlite", "postgres"))
def issuance_ctx(request):
    return request.getfixturevalue("ctx" if request.param == "sqlite" else "postgres_ctx")


@pytest.mark.parametrize("name", OPERATIONS)
def test_identical_identity_source_swap_after_final_validation_denies_atomically(
        issuance_ctx, monkeypatch, name):
    ctx = issuance_ctx
    monkeypatch.setattr(operations, "_utc_now", lambda: ctx.clock[0])
    reader, call = operation(ctx, name)
    before = database_snapshot(ctx)
    calls_before = ctx.source.calls

    class CopiedIdentitySource:
        calls = 0

        def authenticated_identity(self):
            self.calls += 1
            return replace(ctx.identity)

    replacement = CopiedIdentitySource()
    original = reader._finish_authorized
    validated = []

    def finish(*args, **kwargs):
        original(*args, **kwargs)
        validated.append(True)
        reader._identity_source = replacement

    monkeypatch.setattr(reader, "_finish_authorized", finish)
    assert_denied(name, call())
    assert validated == [True]
    assert ctx.source.calls == calls_before + 2
    assert replacement.calls == 0  # Copied claims do not replace the pinned verifier.
    assert database_snapshot(ctx) == before
