"""Synthetic custody prerequisites only; no bytes, real identity or storage."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
import re
from threading import Event
from types import SimpleNamespace

import pytest
from sqlalchemy import event, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

import src.authz as authz
import src.storage as storage
from src.assessment_evidence_access import EvidenceReadRequest
from src.db import (
    Assessment, Engagement, EngagementAccessGrant, Evidence,
    Organization, OrganizationMembership, Vendor,
)
from src.evidence_custody_preflight import SyntheticEvidenceCustodyPreflightService
from src.evidence_custody_preflight import _EvidenceLinkageReader
from src.server_sessions import InMemorySessionStore, SessionManager
from src.session_identity_source import SessionIdentitySource
from test_assessment_snapshot import TABLES, change, snapshot_ctx, snapshot_engine
from test_session_identity_source import ISSUER, signing_key, synthetic_code_flow_session
from test_tenant_read_scope import NOW


REQUEST = EvidenceReadRequest(1, 101, 11, 1001, 9001)
KEY = "vendors/11/evidence/allowed.txt"


@pytest.fixture
def custody_ctx(snapshot_ctx):
    ctx = snapshot_ctx
    ctx.service = SyntheticEvidenceCustodyPreflightService(ctx.factory, identity_source=ctx.source)
    return ctx


def test_signed_local_session_proves_only_current_readiness(custody_ctx, signing_key):
    ctx = custody_ctx
    handle = synthetic_code_flow_session(ctx.sessions, ctx.clock, signing_key)
    source = SessionIdentitySource(ctx.sessions, handle, ctx.factory, clock=lambda: ctx.clock[0])
    service = SyntheticEvidenceCustodyPreflightService(ctx.factory, identity_source=source)
    assert service.preflight(REQUEST) is True
    assert service.preflight(REQUEST) is True  # Each call reauthorizes; no grant DTO.


def test_no_storage_existence_or_byte_operations_and_no_database_mutations(custody_ctx, monkeypatch):
    ctx = custody_ctx
    def blocked(*args, **kwargs):
        pytest.fail("preflight touched storage instead of checking SQL linkage")

    monkeypatch.setattr(storage, "get_evidence_storage", blocked)
    for backend in (storage.LocalEvidenceStorage, storage.S3EvidenceStorage):
        for method in ("save", "exists", "delete", "__init__"):
            monkeypatch.setattr(backend, method, blocked)

    def state():
        with ctx.factory() as database:
            return tuple(tuple(database.execute(select(model.__table__)).all()) for model in TABLES)

    before, mutations = state(), []
    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if re.match(r"\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE)\b", statement, re.I):
            mutations.append(statement)
    event.listen(ctx.engine, "before_cursor_execute", observe)
    try:
        assert ctx.service.preflight(REQUEST) is True
        assert ctx.service.preflight(replace(REQUEST, evidence_id=99999)) is False
    finally:
        event.remove(ctx.engine, "before_cursor_execute", observe)
    assert mutations == [] and state() == before


@pytest.mark.parametrize("candidate", [None, {}, tuple(REQUEST.__dict__.values()),
    SimpleNamespace(**REQUEST.__dict__), True])
def test_untyped_request_is_not_authority(custody_ctx, candidate):
    assert custody_ctx.service.preflight(candidate) is False


@pytest.mark.parametrize("field", REQUEST.__dict__)
@pytest.mark.parametrize("value", [None, True, False, 0, -1, "1", 1.0, 2**64])
def test_all_selectors_require_bounded_positive_integer_ids(custody_ctx, field, value):
    assert custody_ctx.service.preflight(replace(REQUEST, **{field: value})) is False


@pytest.mark.parametrize("candidate", [
    EvidenceReadRequest(1, 102, 11, 1002, 9002),  # Ungranted sibling.
    EvidenceReadRequest(2, 201, 22, 2001, 9201),  # Other organization.
    EvidenceReadRequest(1, 301, 33, 3001, 9301),  # Unassigned legacy vendor.
    EvidenceReadRequest(1, 101, 11, 1001, 9401),  # Missing assessment link.
    EvidenceReadRequest(1, 101, 22, 5001, 9601),  # Inconsistent parent.
    EvidenceReadRequest(1, 101, 11, 4001, 9701),  # Missing engagement link.
    replace(REQUEST, organization_id=2), replace(REQUEST, engagement_id=102),
    replace(REQUEST, vendor_id=22), replace(REQUEST, assessment_id=1002),
    replace(REQUEST, evidence_id=9002), replace(REQUEST, evidence_id=99999),
])
def test_cross_org_sibling_missing_mismatched_and_unrelated_ids_all_deny(custody_ctx, candidate):
    assert custody_ctx.service.preflight(REQUEST) is True
    assert custody_ctx.service.preflight(candidate) is False


@pytest.mark.parametrize("model,row_id,values", [
    (Evidence, 9001, {"vendor_id": 22}), (Evidence, 9001, {"assessment_id": 1002}),
    (Evidence, 9001, {"assessment_id": None}), (Assessment, 1001, {"vendor_id": 22}),
    (Assessment, 1001, {"engagement_id": 102}), (Assessment, 1001, {"engagement_id": None}),
    (Engagement, 101, {"vendor_id": 22}), (Vendor, 11, {"organization_id": 2}),
    (Vendor, 11, {"organization_id": None}),
])
def test_current_exact_chain_must_be_reproved_for_every_call(custody_ctx, model, row_id, values):
    ctx = custody_ctx
    assert ctx.service.preflight(REQUEST) is True
    change(ctx, model, row_id, **values)
    assert ctx.service.preflight(REQUEST) is False


@pytest.mark.parametrize("key", [None, "", "/tmp/synthetic.txt", "s3://synthetic/" + KEY,
    "uploaded_evidence/" + KEY, "vendors/22/evidence/allowed.txt", "vendors/011/evidence/a",
    "vendors/11/evidence/../a", "vendors/11/evidence/%2e%2e", "vendors/11/evidence/a/b",
    "vendors\\11\\evidence\\a", "vendors/11/evidence/a\x00", " " + KEY, KEY + " ",
    "vendors/11/evidence/" + "a" * 256])
def test_legacy_locations_unsafe_keys_and_vendor_mismatch_deny_without_relink(custody_ctx, key):
    ctx = custody_ctx
    change(ctx, Evidence, 9001, storage_path=key)
    assert ctx.service.preflight(REQUEST) is False
    with ctx.factory() as database:
        assert database.execute(select(Evidence.storage_path).where(Evidence.id == 9001)).scalar_one() == key


@pytest.mark.parametrize("alias_id", [9002, 9201, 9301, 9401])
def test_key_alias_in_ungranted_other_org_legacy_or_unlinked_row_denies(custody_ctx, alias_id):
    ctx = custody_ctx
    assert ctx.service.preflight(REQUEST) is True
    change(ctx, Evidence, alias_id, storage_path=KEY)
    assert ctx.service.preflight(REQUEST) is False
    # The result reveals no hidden ID, key, document name or failure reason.
    assert ctx.service.preflight(replace(REQUEST, evidence_id=99999)) is False


@pytest.mark.parametrize("model,row_id", [(OrganizationMembership, 501), (EngagementAccessGrant, 701)])
@pytest.mark.parametrize("values", [{"status": "revoked"}, {"expires_at": NOW},
    {"valid_from": NOW + timedelta(seconds=1)}])
def test_current_member_and_grant_required(custody_ctx, model, row_id, values):
    ctx = custody_ctx
    assert ctx.service.preflight(REQUEST) is True
    change(ctx, model, row_id, **values)
    assert ctx.service.preflight(REQUEST) is False


def test_membership_ambiguity_denies_and_viewer_still_requires_read_permission(custody_ctx, monkeypatch):
    ctx = custody_ctx
    change(ctx, OrganizationMembership, 501, role=authz.ROLE_VIEWER)
    assert ctx.service.preflight(REQUEST) is True
    with monkeypatch.context() as permissions:
        permissions.setitem(authz.ROLE_PERMISSIONS, authz.ROLE_VIEWER, frozenset())
        assert ctx.service.preflight(REQUEST) is False
    with ctx.factory.begin() as database:
        database.add(OrganizationMembership(organization_id=2, issuer=ISSUER, subject="reader",
            role=authz.ROLE_ANALYST, status="active", valid_from=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=1)))
    assert ctx.service.preflight(REQUEST) is False


@pytest.mark.parametrize("row_id,key", [(9001, "vendors/11/evidence/changed.txt"), (9201, KEY)])
def test_key_change_and_hidden_alias_observed_before_final_validation_deny(custody_ctx, monkeypatch, row_id, key):
    ctx = custody_ctx
    original = _EvidenceLinkageReader._relationships
    invoked = []
    def changed(reader, session, scope, *, lock):
        # Inject after the last independent identity lookup, so the synthetic
        # SQLite shared connection cannot roll back this simulated SQL change.
        if not lock:
            session.execute(update(Evidence).where(Evidence.id == row_id).values(storage_path=key))
            invoked.append(True)
        return original(reader, session, scope, lock=lock)
    monkeypatch.setattr(_EvidenceLinkageReader, "_relationships", changed)
    assert ctx.service.preflight(REQUEST) is False
    assert invoked == [True]
    # A failed preflight also rolls back the injected concurrent-change simulation.
    with ctx.factory() as database:
        assert database.execute(select(Evidence.storage_path).where(Evidence.id == 9001)).scalar_one() == KEY


@pytest.mark.parametrize("operation", ["revoke", "rotate", "idle", "absolute"])
def test_old_session_preflight_cannot_be_reused(custody_ctx, operation):
    ctx = custody_ctx
    assert ctx.service.preflight(REQUEST) is True
    if operation in ("revoke", "rotate"):
        assert getattr(ctx.sessions, operation)(ctx.handle)
    else:
        ctx.clock[0] += timedelta(seconds=30 if operation == "idle" else 90)
    assert ctx.service.preflight(REQUEST) is False


def test_missing_fake_identity_and_mismatched_factory_deny(custody_ctx):
    ctx = custody_ctx
    identity = ctx.source.authenticated_identity()
    for service in (
        SyntheticEvidenceCustodyPreflightService(), SyntheticEvidenceCustodyPreflightService(ctx.factory),
        SyntheticEvidenceCustodyPreflightService(identity_source=ctx.source),
        SyntheticEvidenceCustodyPreflightService(ctx.factory, identity_source=identity),
        SyntheticEvidenceCustodyPreflightService(ctx.factory,
            identity_source=SimpleNamespace(authenticated_identity=lambda: identity)),
        SyntheticEvidenceCustodyPreflightService(sessionmaker(bind=ctx.engine), identity_source=ctx.source),
    ):
        assert service.preflight(REQUEST) is False


@pytest.mark.parametrize("failure", ["commit", "source", "factory", "pending_write"])
def test_outages_failed_commit_and_pending_writes_release_no_readiness(custody_ctx, monkeypatch, failure):
    ctx = custody_ctx
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic private dependency diagnostic")
    if failure == "source":
        monkeypatch.setattr(ctx.source, "authenticated_identity", fail)
    elif failure in ("factory", "pending_write"):
        def factory():
            if failure == "factory":
                return fail()
            database = ctx.factory()
            database.add(Organization(id=990, name="Synthetic pending", external_key="pending"))
            return database
        source = SessionIdentitySource(ctx.sessions, ctx.handle, factory, clock=lambda: ctx.clock[0])
        service = SyntheticEvidenceCustodyPreflightService(factory, identity_source=source)
        assert service.preflight(REQUEST) is False
        with ctx.factory() as database:
            assert database.get(Organization, 990) is None
        return
    else:
        event.listen(ctx.factory, "before_commit", fail)
    try:
        assert ctx.service.preflight(REQUEST) is False
    finally:
        if failure == "commit":
            event.remove(ctx.factory, "before_commit", fail)


@pytest.mark.parametrize("stage", ["initial_identity", "commit", "cleanup"])
@pytest.mark.parametrize("dependency", ["service_source", "service_factory", "source_manager",
    "source_factory", "source_handle", "source_clock", "manager_store", "manager_clock",
    "manager_idle", "manager_absolute"])
def test_dependency_substitution_denies_even_with_equal_identity(custody_ctx, monkeypatch, stage, dependency):
    ctx = custody_ctx
    observed = []
    def mutate():
        if observed:
            return
        observed.append(True)
        other_store = InMemorySessionStore()
        other_store._records = dict(ctx.sessions._store._records)
        replacements = {
            "service_source": (ctx.service, "_identity_source", SessionIdentitySource(
                ctx.sessions, ctx.handle, ctx.factory, clock=ctx.source._clock)),
            "service_factory": (ctx.service, "_sessions", sessionmaker(bind=ctx.engine)),
            "source_manager": (ctx.source, "_sessions", SessionManager(
                ctx.sessions._store, clock=ctx.sessions._clock, idle_seconds=30, absolute_seconds=90)),
            "source_factory": (ctx.source, "_database_sessions", sessionmaker(bind=ctx.engine)),
            "source_handle": (ctx.source, "_handle", ctx.handle[::-1]),
            "source_clock": (ctx.source, "_clock", lambda: ctx.clock[0]),
            "manager_store": (ctx.sessions, "_store", other_store),
            "manager_clock": (ctx.sessions, "_clock", lambda: ctx.clock[0]),
            "manager_idle": (ctx.sessions, "_idle", 31),
            "manager_absolute": (ctx.sessions, "_absolute", 91),
        }
        owner, attribute, replacement = replacements[dependency]
        monkeypatch.setattr(owner, attribute, replacement)
    if stage == "initial_identity":
        original = ctx.source.authenticated_identity
        def identity():
            result = original()
            mutate()
            return result
        monkeypatch.setattr(ctx.source, "authenticated_identity", identity)
    elif stage == "cleanup":
        store = ctx.sessions._store
        original = store.operation_lease
        @contextmanager
        def cleanup(key):
            with original(key):
                yield
            mutate()
        monkeypatch.setattr(store, "operation_lease", cleanup)
    else:
        def before_commit(_database):
            mutate()
        event.listen(ctx.factory, "before_commit", before_commit)
    try:
        assert ctx.service.preflight(REQUEST) is False
        assert observed == [True]
    finally:
        if stage == "commit":
            event.remove(ctx.factory, "before_commit", before_commit)


@pytest.mark.parametrize("deadline", ["session_idle", "session_absolute", "member", "grant"])
@pytest.mark.parametrize("stage", ["commit", "cleanup"])
def test_deadlines_rechecked_after_sql_commit_and_lease_cleanup(custody_ctx, monkeypatch, deadline, stage):
    ctx = custody_ctx
    seconds = 30 if deadline == "session_idle" else 90
    if deadline in ("member", "grant"):
        model, row_id = (OrganizationMembership, 501) if deadline == "member" else (EngagementAccessGrant, 701)
        change(ctx, model, row_id, expires_at=NOW + timedelta(seconds=1))
        seconds = 2
    invoked = []
    def expire(*args):
        invoked.append(True)
        ctx.clock[0] += timedelta(seconds=seconds)
    if stage == "commit":
        event.listen(ctx.factory, "before_commit", expire)
    else:
        original = ctx.sessions._store.operation_lease
        @contextmanager
        def delayed_cleanup(key):
            with original(key):
                yield
            expire()
        monkeypatch.setattr(ctx.sessions._store, "operation_lease", delayed_cleanup)
    try:
        assert ctx.service.preflight(REQUEST) is False
        assert invoked == [True]
    finally:
        if stage == "commit":
            event.remove(ctx.factory, "before_commit", expire)


@pytest.mark.parametrize("operation", ["revoke", "rotate"])
def test_session_mutation_serializes_through_final_commit(custody_ctx, monkeypatch, operation):
    ctx = custody_ctx
    committing, release, attempted = Event(), Event(), Event()
    original = getattr(ctx.sessions._store, operation)
    def pause(_database):
        committing.set()
        assert release.wait(5)
    def mutate(*args):
        attempted.set()
        return original(*args)
    monkeypatch.setattr(ctx.sessions._store, operation, mutate)
    event.listen(ctx.factory, "before_commit", pause)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            preflight = workers.submit(ctx.service.preflight, REQUEST)
            try:
                assert committing.wait(5)
                mutation = workers.submit(getattr(ctx.sessions, operation), ctx.handle)
                assert attempted.wait(2)
                with pytest.raises(TimeoutError):
                    mutation.result(timeout=0.05)
            finally:
                release.set()
            assert preflight.result(timeout=5) is True
            assert mutation.result(timeout=5)
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause)
    assert ctx.service.preflight(REQUEST) is False


@pytest.mark.parametrize("model,row_id,values", [
    (OrganizationMembership, 501, {"status": "revoked"}),
    (EngagementAccessGrant, 701, {"status": "revoked"}),
    (Assessment, 1001, {"engagement_id": 102}),
    (Evidence, 9001, {"storage_path": "vendors/22/evidence/changed.txt"}),
    (OrganizationMembership, None, {"id": 990, "organization_id": 2, "issuer": ISSUER,
        "subject": "reader", "role": authz.ROLE_ANALYST, "status": "active",
        "valid_from": NOW - timedelta(days=1), "expires_at": NOW + timedelta(days=1)}),
])
def test_postgres_current_authority_and_key_updates_wait_for_sql_completion(custody_ctx, model, row_id, values):
    ctx = custody_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires isolated Actions PostgreSQL service and two connections")
    committing, release = Event(), Event()
    def pause(_database):
        committing.set()
        assert release.wait(5)
    event.listen(ctx.factory, "before_commit", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as workers:
            preflight = workers.submit(ctx.service.preflight, REQUEST)
            try:
                assert committing.wait(5)
                with ctx.engine.connect() as connection:
                    with pytest.raises(DBAPIError) as error:
                        with connection.begin():
                            connection.exec_driver_sql("SET LOCAL lock_timeout = '150ms'")
                            mutation = (insert(model).values(**values) if row_id is None else
                                update(model).where(model.id == row_id).values(**values))
                            connection.execute(mutation)
                    assert (getattr(error.value.orig, "sqlstate", None)
                            or getattr(error.value.orig, "pgcode", None)) == "55P03"
            finally:
                release.set()
            assert preflight.result(timeout=5) is True
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause)
    if row_id is None:
        with ctx.factory.begin() as database:
            database.execute(insert(model).values(**values))
    else:
        change(ctx, model, row_id, **values)
    assert ctx.service.preflight(REQUEST) is False


def test_postgres_hidden_alias_committed_before_final_check_denies(custody_ctx, monkeypatch):
    ctx = custody_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires isolated Actions PostgreSQL service and two connections")
    checking, release = Event(), Event()
    original = _EvidenceLinkageReader._relationships
    def pause(reader, session, scope, *, lock):
        if not lock:
            checking.set()
            assert release.wait(5)
        return original(reader, session, scope, lock=lock)
    monkeypatch.setattr(_EvidenceLinkageReader, "_relationships", pause)
    with ThreadPoolExecutor(max_workers=1) as workers:
        preflight = workers.submit(ctx.service.preflight, REQUEST)
        try:
            assert checking.wait(5)
            # This row belongs to another organization and is outside the
            # current scope's row locks. Its committed alias must be observed.
            with ctx.engine.begin() as connection:
                connection.execute(update(Evidence).where(Evidence.id == 9201).values(storage_path=KEY))
        finally:
            release.set()
        assert preflight.result(timeout=5) is False
