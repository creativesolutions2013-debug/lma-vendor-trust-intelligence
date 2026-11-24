"""Original synthetic bytes under current authority; no file or object service."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import os
from threading import Event
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, delete, event, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

import src.authz as authz
import src.storage as storage
import src.synthetic_evidence_custody as custody
import src.tenant_read_scope as scoped
from src.assessment_evidence_access import EvidenceReadRequest
from src.db import (
    Assessment, Base, EngagementAccessGrant, Evidence, Organization,
    OrganizationMembership, SyntheticEvidenceObject, Vendor,
)
from src.server_sessions import InMemorySessionStore, SessionManager, VerifiedSubject
from src.session_identity_source import SessionIdentitySource
from src.synthetic_custody_guards import synthetic_custody_guard_statements
from test_session_identity_source import ISSUER, signing_key, synthetic_code_flow_session
from test_tenant_read_scope import NOW, rows


CONTENT = b"Synthetic custody fixture only.\x00\xff\n"
NAME = "synthetic-control-proof.txt"


@pytest.fixture
def custody_ctx(tmp_path, monkeypatch):
    url = os.getenv("DATABASE_URL", "")
    root, schema = None, None
    if os.getenv("GITHUB_ACTIONS") == "true" and url.startswith("postgresql"):
        schema = "m7_bytes_" + uuid4().hex
        root = create_engine(url)
        with root.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = root.execution_options(schema_translate_map={None: schema})
    else:
        # Separate connections let identity lookups close independently without
        # rolling back the custody transaction, unlike a shared StaticPool.
        engine = create_engine(f"sqlite:///{tmp_path / 'synthetic.sqlite'}",
                               connect_args={"check_same_thread": False})
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        rows(factory)
        with factory.begin() as database:
            database.execute(delete(Evidence).where(Evidence.id == 9501))
            database.execute(update(OrganizationMembership).where(OrganizationMembership.id == 501)
                             .values(issuer=ISSUER, subject="reader"))
        clock = [NOW]
        sessions = SessionManager(InMemorySessionStore(), clock=lambda: clock[0],
                                  idle_seconds=30, absolute_seconds=90)
        handle = sessions.issue(VerifiedSubject(ISSUER, "reader", "synthetic-client"))
        source = SessionIdentitySource(sessions, handle, factory, clock=lambda: clock[0])
        service = custody.SyntheticEvidenceCustodyService(factory, identity_source=source)
        monkeypatch.setattr(scoped, "_utc_now", lambda: clock[0])
        yield SimpleNamespace(engine=engine, schema=schema, factory=factory, clock=clock,
                              sessions=sessions, handle=handle, source=source, service=service)
    finally:
        if root is not None:
            with root.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            root.dispose()
        else:
            engine.dispose()


def request_for(receipt):
    return EvidenceReadRequest(receipt.organization_id, receipt.engagement_id, receipt.vendor_id,
                               receipt.assessment_id, receipt.evidence_id)


def save(ctx, content=CONTENT, name=NAME):
    return ctx.service.save(1001, content, document_name=name)


def state(ctx):
    with ctx.factory() as database:
        return tuple(tuple(database.execute(select(model.__table__).order_by(
            *model.__table__.primary_key.columns)).all()) for model in (
                Evidence, SyntheticEvidenceObject, Assessment, OrganizationMembership, EngagementAccessGrant))


def change(ctx, model, row_id, **values):
    with ctx.factory.begin() as database:
        database.execute(update(model).where(model.id == row_id).values(**values))


@pytest.mark.parametrize("content", [b"x", CONTENT, b"Z" * 65536])
def test_authorized_original_byte_hash_and_provenance_round_trip(custody_ctx, content):
    ctx = custody_ctx
    before = state(ctx)
    receipt = save(ctx, content)
    assert type(receipt) is custody.SyntheticEvidenceReceipt
    assert (receipt.organization_id, receipt.vendor_id, receipt.engagement_id,
            receipt.assessment_id) == (1, 11, 101, 1001)
    assert receipt.evidence_id not in {row[0] for row in before[0]}
    assert receipt.sha256 == sha256(content).hexdigest()
    assert receipt.byte_length == len(content) and receipt.document_name == NAME
    assert len(receipt.generation) == 32 and UUID(receipt.generation).hex == receipt.generation
    result = ctx.service.retrieve(request_for(receipt), generation=receipt.generation)
    assert type(result) is custody.SyntheticEvidenceResult
    assert result.receipt == receipt and type(result.content) is bytes and result.content == content
    with ctx.factory() as database:
        recorded = database.execute(select(SyntheticEvidenceObject.__table__)).mappings().one()
        assert recorded["issuer"] == ISSUER and recorded["subject"] == "reader"
        assert recorded["session_id"] == ctx.sessions.authenticate(ctx.handle).session_id
        assert recorded["session_id"] != ctx.handle
        assert recorded["effective_role"] == authz.ROLE_ANALYST and recorded["membership_id"] == 501
        assert recorded["storage_key"] == f"vendors/11/evidence/m7_{receipt.generation}.bin"
        assert recorded["payload"] == content
    after = state(ctx)
    assert after[2:] == before[2:]  # No assessment, risk, membership or grant mutation.


def test_actual_signed_local_code_flow_is_accepted_without_files_or_object_store(custody_ctx, signing_key, monkeypatch):
    ctx = custody_ctx
    handle = synthetic_code_flow_session(ctx.sessions, ctx.clock, signing_key)
    source = SessionIdentitySource(ctx.sessions, handle, ctx.factory, clock=lambda: ctx.clock[0])
    ctx.service = custody.SyntheticEvidenceCustodyService(ctx.factory, identity_source=source)
    def blocked(*args, **kwargs):
        pytest.fail("SQL custody accessed an external storage implementation")
    monkeypatch.setattr(storage, "get_evidence_storage", blocked)
    for backend in (storage.LocalEvidenceStorage, storage.S3EvidenceStorage):
        for method in ("save", "exists", "delete", "__init__"):
            monkeypatch.setattr(backend, method, blocked)
    receipt = save(ctx)
    assert receipt is not None
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation).content == CONTENT


@pytest.mark.parametrize("content", [None, "synthetic", bytearray(b"synthetic"), memoryview(b"synthetic"),
    b"", b"x" * 65537, True, {}])
def test_malformed_empty_and_oversized_payload_denies_without_partial_evidence(custody_ctx, content):
    ctx = custody_ctx
    before = state(ctx)
    assert save(ctx, content) is None
    assert state(ctx) == before


@pytest.mark.parametrize("name", [None, "", " ", " leading.txt", "trailing.txt ", "../escape.txt",
    "/tmp/escape.txt", "a/b.txt", "a\\b.txt", "link/../escape.txt", "s3://synthetic/object",
    "control\x00.txt", "line\nbreak.txt", "a" * 121, "résumé.txt", ".hidden", "encoded%20.txt", {}, True])
def test_document_name_cannot_be_path_url_control_text_or_unbounded(custody_ctx, name):
    ctx = custody_ctx
    before = state(ctx)
    assert save(ctx, name=name) is None
    assert state(ctx) == before


@pytest.mark.parametrize("assessment_id", [1002, 2001, 3001, 4001, 5001, 99999, None, True, "1001", 0, -1, 2**64])
def test_save_requires_current_exact_granted_assessment(custody_ctx, assessment_id):
    ctx = custody_ctx
    before = state(ctx)
    assert ctx.service.save(assessment_id, CONTENT, document_name=NAME) is None
    assert state(ctx) == before


@pytest.mark.parametrize("field,value", [("organization_id", 2), ("engagement_id", 102),
    ("vendor_id", 22), ("assessment_id", 1002), ("evidence_id", 9001),
    ("evidence_id", True), ("assessment_id", "1001"), ("evidence_id", 2**64)])
def test_receipt_and_known_generation_never_authorize_wrong_relationship(custody_ctx, field, value):
    ctx = custody_ctx
    receipt = save(ctx)
    assert receipt is not None
    assert ctx.service.retrieve(replace(request_for(receipt), **{field: value}), generation=receipt.generation) is None


@pytest.mark.parametrize("generation", [None, "", "../escape", "s3://synthetic/object", "A" * 32,
    "0" * 31, "0" * 33, True, {}, "f" * 32])
def test_bad_or_stale_generation_and_legacy_locations_never_read(custody_ctx, generation):
    ctx = custody_ctx
    receipt = save(ctx)
    assert receipt is not None
    assert ctx.service.retrieve(request_for(receipt), generation=generation) is None
    change(ctx, Evidence, 9001, storage_path="/tmp/synthetic-legacy.txt")
    assert ctx.service.retrieve(EvidenceReadRequest(1, 101, 11, 1001, 9001), generation=receipt.generation) is None


@pytest.mark.parametrize("model,row_id,values", [
    (OrganizationMembership, 501, {"status": "revoked"}),
    (OrganizationMembership, 501, {"expires_at": NOW}),
    (EngagementAccessGrant, 701, {"status": "revoked"}),
    (EngagementAccessGrant, 701, {"expires_at": NOW}),
])
def test_current_member_grant_revocation_and_expiry_block_saved_bytes_and_new_writes(custody_ctx, model, row_id, values):
    ctx = custody_ctx
    receipt = save(ctx)
    assert receipt is not None
    change(ctx, model, row_id, **values)
    before = state(ctx)
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation) is None
    assert save(ctx) is None and state(ctx) == before


@pytest.mark.parametrize("operation", ["revoke", "rotate", "idle", "absolute"])
def test_old_session_cannot_retrieve_or_save(custody_ctx, operation):
    ctx = custody_ctx
    receipt = save(ctx)
    assert receipt is not None
    if operation in ("revoke", "rotate"):
        assert getattr(ctx.sessions, operation)(ctx.handle)
    else:
        ctx.clock[0] += timedelta(seconds=30 if operation == "idle" else 90)
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation) is None
    assert save(ctx) is None


def test_current_effective_permissions_apply_separately_to_write_and_read(custody_ctx, monkeypatch):
    ctx = custody_ctx
    receipt = save(ctx)
    assert receipt is not None
    change(ctx, OrganizationMembership, 501, role=authz.ROLE_VIEWER)
    assert save(ctx) is None
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation).content == CONTENT
    with monkeypatch.context() as permissions:
        permissions.setitem(authz.ROLE_PERMISSIONS, authz.ROLE_VIEWER, frozenset())
        assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation) is None
    change(ctx, OrganizationMembership, 501, role=authz.ROLE_ANALYST)
    for missing in (authz.PERMISSION_ASSESSMENT_MANAGE, authz.PERMISSION_EVIDENCE_UPLOAD):
        with monkeypatch.context() as permissions:
            permissions.setitem(authz.ROLE_PERMISSIONS, authz.ROLE_ANALYST,
                                authz.ROLE_PERMISSIONS[authz.ROLE_ANALYST] - {missing})
            assert save(ctx) is None


def test_duplicate_generation_rolls_back_new_evidence_and_preserves_original(custody_ctx, monkeypatch):
    ctx = custody_ctx
    generation = UUID("12345678123456781234567812345678")
    monkeypatch.setattr(custody, "uuid4", lambda: generation)
    receipt = save(ctx)
    assert receipt is not None
    before = state(ctx)
    assert save(ctx, b"different synthetic content") is None
    assert state(ctx) == before
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation).content == CONTENT


def test_repeated_payload_creates_fresh_immutable_generation_without_overwrite(custody_ctx):
    ctx = custody_ctx
    first, second = save(ctx), save(ctx)
    assert first is not None and second is not None
    assert first.evidence_id != second.evidence_id and first.generation != second.generation
    assert first.sha256 == second.sha256 == sha256(CONTENT).hexdigest()
    for receipt in (first, second):
        assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation).content == CONTENT


def test_corrupted_bytes_are_rehashed_after_admin_fixture_bypasses_then_restores_guard(custody_ctx):
    ctx = custody_ctx
    receipt = save(ctx)
    assert receipt is not None
    # Explicitly model trusted-admin tampering in this disposable fixture only.
    # Restore guard health before calling the service so denial must come from
    # byte-integrity validation, rather than a deliberately missing guard.
    quote = ctx.engine.dialect.identifier_preparer.quote
    relation = (quote(ctx.schema) + "." if ctx.schema else "") + quote("synthetic_evidence_objects")
    postgres = ctx.engine.dialect.name == "postgresql"
    trigger = quote("m7_custody_no_mutation" if postgres else "m7_custody_no_update")
    tampered = b"X" + CONTENT[1:]
    with ctx.engine.begin() as connection:
        connection.exec_driver_sql(f"ALTER TABLE {relation} DISABLE TRIGGER {trigger}" if postgres else
                                   f"DROP TRIGGER {trigger}")
        connection.execute(update(SyntheticEvidenceObject).where(
            SyntheticEvidenceObject.evidence_id == receipt.evidence_id).values(payload=tampered))
        if postgres:
            connection.exec_driver_sql(f"ALTER TABLE {relation} ENABLE ALWAYS TRIGGER {trigger}")
        else:
            statements = synthetic_custody_guard_statements(ctx.engine.dialect)
            statement = next(value for value in statements if value.startswith("CREATE TRIGGER m7_custody_no_update "))
            connection.exec_driver_sql(statement)
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation) is None
    with ctx.factory() as database:
        digest = database.execute(select(SyntheticEvidenceObject.sha256).where(
            SyntheticEvidenceObject.evidence_id == receipt.evidence_id)).scalar_one()
        assert digest == receipt.sha256 and sha256(tampered).hexdigest() != digest


def test_legacy_key_alias_never_acquires_immutable_custody_ownership(custody_ctx):
    ctx = custody_ctx
    receipt = save(ctx)
    assert receipt is not None
    change(ctx, Evidence, 9001, storage_path=f"vendors/11/evidence/m7_{receipt.generation}.bin",
           file_hash=receipt.sha256)
    alias = EvidenceReadRequest(1, 101, 11, 1001, 9001)
    assert ctx.service.retrieve(alias, generation=receipt.generation) is None
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation).content == CONTENT


@pytest.mark.parametrize("failure", ["object_insert", "commit"])
def test_object_write_and_commit_failures_roll_back_bytes_and_evidence_together(custody_ctx, failure):
    ctx = custody_ctx
    before, invoked = state(ctx), []
    def fail_insert(_connection, _cursor, statement, _parameters, _context, _many):
        if re_match_object_insert(statement):
            invoked.append(True)
            raise RuntimeError("synthetic object-write failure")
    def fail_commit(_database):
        invoked.append(True)
        raise RuntimeError("synthetic SQL-commit failure")
    target, name, hook = (ctx.engine, "before_cursor_execute", fail_insert) if failure == "object_insert" else (
        ctx.factory, "before_commit", fail_commit)
    event.listen(target, name, hook)
    try:
        assert save(ctx) is None
        assert invoked == [True]
    finally:
        event.remove(target, name, hook)
    assert state(ctx) == before


def re_match_object_insert(statement):
    normalized = statement.lstrip().upper().replace('"', '')
    return normalized.startswith("INSERT INTO ") and "SYNTHETIC_EVIDENCE_OBJECT" in normalized


def test_postcommit_cleanup_failure_withholds_receipt_but_keeps_immutable_record(custody_ctx, monkeypatch):
    ctx = custody_ctx
    original = ctx.sessions._store.operation_lease
    cleaned = []
    @contextmanager
    def failed_cleanup(key):
        with original(key):
            yield
        cleaned.append(True)
        raise RuntimeError("synthetic cleanup/acknowledgement failure")
    with monkeypatch.context() as patch:
        patch.setattr(ctx.sessions._store, "operation_lease", failed_cleanup)
        assert save(ctx) is None
        assert cleaned == [True]
    with ctx.factory() as database:
        retained = database.execute(select(SyntheticEvidenceObject.__table__)).mappings().one()
    known = EvidenceReadRequest(retained["organization_id"], retained["engagement_id"], retained["vendor_id"],
                               retained["assessment_id"], retained["evidence_id"])
    result = ctx.service.retrieve(known, generation=retained["generation"])
    assert result is not None and result.content == CONTENT


@pytest.mark.parametrize("kind", ["source", "factory", "store"])
def test_dependency_replacement_during_save_commit_withholds_receipt(custody_ctx, monkeypatch, kind):
    ctx = custody_ctx
    invoked = []
    def replace_dependency(_database):
        invoked.append(True)
        if kind == "source":
            monkeypatch.setattr(ctx.service, "_identity_source", SessionIdentitySource(
                ctx.sessions, ctx.handle, ctx.factory, clock=ctx.source._clock))
        elif kind == "factory":
            monkeypatch.setattr(ctx.source, "_database_sessions", sessionmaker(bind=ctx.engine))
        else:
            replacement = InMemorySessionStore()
            replacement._records = dict(ctx.sessions._store._records)
            monkeypatch.setattr(ctx.sessions, "_store", replacement)
    event.listen(ctx.factory, "before_commit", replace_dependency)
    try:
        assert save(ctx) is None
        assert invoked == [True]
    finally:
        event.remove(ctx.factory, "before_commit", replace_dependency)


def test_missing_configuration_and_caller_identity_dto_cannot_supply_authority(custody_ctx):
    ctx = custody_ctx
    identity = ctx.source.authenticated_identity()
    for service in (custody.SyntheticEvidenceCustodyService(),
        custody.SyntheticEvidenceCustodyService(ctx.factory),
        custody.SyntheticEvidenceCustodyService(ctx.factory, identity_source=identity),
        custody.SyntheticEvidenceCustodyService(ctx.factory,
            identity_source=SimpleNamespace(authenticated_identity=lambda: identity))):
        assert service.save(1001, CONTENT, document_name=NAME) is None
        assert service.retrieve(EvidenceReadRequest(1, 101, 11, 1001, 9001), generation="a" * 32) is None


@pytest.mark.parametrize("mutation", ["grant_revoke", "membership_insert", "parent_delete"])
def test_postgres_mutations_serialize_through_custody_save_commit(custody_ctx, mutation):
    ctx = custody_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires isolated Actions PostgreSQL service and independent connections")
    committing, release = Event(), Event()
    created = []
    def pause(database):
        created.extend(database.execute(select(SyntheticEvidenceObject.evidence_id)).scalars())
        committing.set()
        assert release.wait(5)
    event.listen(ctx.factory, "before_commit", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as workers:
            saving = workers.submit(save, ctx)
            try:
                assert committing.wait(5)
                with ctx.engine.connect() as connection:
                    with pytest.raises(DBAPIError) as error:
                        with connection.begin():
                            connection.exec_driver_sql("SET LOCAL lock_timeout = '150ms'")
                            if mutation == "grant_revoke":
                                connection.execute(update(EngagementAccessGrant).where(
                                    EngagementAccessGrant.id == 701).values(status="revoked"))
                            elif mutation == "membership_insert":
                                connection.execute(insert(OrganizationMembership).values(
                                    id=990, organization_id=2, issuer=ISSUER, subject="reader",
                                    role=authz.ROLE_ANALYST, status="active", valid_from=NOW - timedelta(days=1),
                                    expires_at=NOW + timedelta(days=1)))
                            else:
                                assert len(created) == 1
                                connection.execute(delete(Assessment).where(Assessment.id == 1001))
                    assert (getattr(error.value.orig, "sqlstate", None)
                            or getattr(error.value.orig, "pgcode", None)) == "55P03"
            finally:
                release.set()
            receipt = saving.result(timeout=5)
            assert receipt is not None
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause)
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation).content == CONTENT


def test_postgres_concurrent_legacy_alias_cannot_retrieve_committed_custody(custody_ctx):
    ctx = custody_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires isolated Actions PostgreSQL service and independent connections")
    committing, release = Event(), Event()
    captured = []
    def pause(database):
        captured.append(database.execute(select(SyntheticEvidenceObject.__table__)).mappings().one())
        committing.set()
        assert release.wait(5)
    event.listen(ctx.factory, "before_commit", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as workers:
            saving = workers.submit(save, ctx)
            try:
                assert committing.wait(5)
                with ctx.engine.begin() as connection:
                    connection.exec_driver_sql("SET LOCAL lock_timeout = '1s'")
                    # Its actual parents are outside the locked current scope;
                    # copying a vendor key string cannot change those parents.
                    connection.execute(insert(Evidence).values(id=99999, vendor_id=22, assessment_id=2001,
                        document_type="Synthetic legacy alias", document_name="alias.txt",
                        storage_path=captured[0]["storage_key"], file_hash=captured[0]["sha256"]))
            finally:
                release.set()
            receipt = saving.result(timeout=5)
            assert receipt is not None
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause)
    assert ctx.service.retrieve(EvidenceReadRequest(1, 101, 11, 1001, 99999),
                                generation=receipt.generation) is None
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation).content == CONTENT


def test_postgres_concurrent_generation_collision_keeps_one_atomic_record(custody_ctx, monkeypatch):
    ctx = custody_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires isolated Actions PostgreSQL service and independent connections")
    change(ctx, OrganizationMembership, 601, issuer=ISSUER, subject="other", role=authz.ROLE_ANALYST)
    other_sessions = SessionManager(InMemorySessionStore(), clock=lambda: ctx.clock[0],
                                    idle_seconds=30, absolute_seconds=90)
    other_handle = other_sessions.issue(VerifiedSubject(ISSUER, "other", "synthetic-client"))
    other_source = SessionIdentitySource(other_sessions, other_handle, ctx.factory, clock=lambda: ctx.clock[0])
    other_service = custody.SyntheticEvidenceCustodyService(ctx.factory, identity_source=other_source)
    monkeypatch.setattr(custody, "uuid4", lambda: UUID("12345678123456781234567812345678"))
    before = state(ctx)
    committing, release, attempted = Event(), Event(), Event()
    def pause(_database):
        if not committing.is_set():
            committing.set()
            assert release.wait(5)
    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if committing.is_set() and re_match_object_insert(statement):
            attempted.set()
    event.listen(ctx.factory, "before_commit", pause)
    event.listen(ctx.engine, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(save, ctx)
            try:
                assert committing.wait(5)
                second = workers.submit(other_service.save, 2001, b"different synthetic bytes", document_name=NAME)
                assert attempted.wait(3)
                with pytest.raises(TimeoutError):
                    second.result(timeout=0.05)
            finally:
                release.set()
            receipt = first.result(timeout=5)
            assert receipt is not None and second.result(timeout=5) is None
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause)
        event.remove(ctx.engine, "before_cursor_execute", observe)
    after = state(ctx)
    assert len(after[0]) == len(before[0]) + 1 and len(after[1]) == len(before[1]) + 1
    assert ctx.service.retrieve(request_for(receipt), generation=receipt.generation).content == CONTENT
