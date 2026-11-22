"""Synthetic metadata consistency and authorization; no files or live identity."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
import json
import os
import re
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, event, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateSchema, DropSchema

import src.tenant_read_scope as scoped
from src.assessment_snapshot import SyntheticAssessmentSnapshotService
from src.authz import ROLE_ANALYST, ROLE_VIEWER
from src.db import (
    Assessment, Base, Engagement, EngagementAccessGrant, Evidence,
    Organization, OrganizationMembership, Vendor,
)
from src.server_sessions import InMemorySessionStore, SessionManager, VerifiedSubject
from src.session_identity_source import SessionIdentitySource
from test_session_identity_source import ISSUER, signing_key, synthetic_code_flow_session
from test_tenant_read_scope import NOW, rows


TABLES = (Evidence, Assessment, EngagementAccessGrant, OrganizationMembership,
          Engagement, Vendor, Organization)
FIELDS = {
    "schema_version", "synthetic", "organization_id", "vendor_id", "engagement_id",
    "assessment_id", "context_version", "source_version", "context_fingerprint",
    "source_fingerprint",
}


@pytest.fixture(scope="module")
def snapshot_engine():
    url = os.getenv("DATABASE_URL", "")
    if os.getenv("GITHUB_ACTIONS") == "true" and url.startswith("postgresql"):
        # Only the ephemeral Actions service; never public or customer tables.
        schema = "m7_snapshot_" + uuid4().hex
        root = create_engine(url)
        with root.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = root.execution_options(schema_translate_map={None: schema})
        try:
            Base.metadata.create_all(engine)  # Includes the mandatory PG guard.
            yield engine
        finally:
            with root.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            root.dispose()
    else:
        engine = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture
def snapshot_ctx(snapshot_engine, monkeypatch):
    factory = sessionmaker(bind=snapshot_engine, expire_on_commit=False, autoflush=False)
    rows(factory)
    with factory.begin() as database:
        database.execute(delete(Evidence).where(Evidence.id == 9501))
        database.execute(update(OrganizationMembership).where(OrganizationMembership.id == 501)
                         .values(issuer=ISSUER, subject="reader"))
        database.execute(update(Assessment).where(Assessment.id == 1001).values(
            notes="synthetic analyst note", risk_score=73, approval_status="Pending"))
        database.execute(update(Evidence).where(Evidence.id == 9001).values(
            file_hash="a" * 64, analyst_notes="synthetic source interpretation"))
    clock = [NOW]
    sessions = SessionManager(InMemorySessionStore(), clock=lambda: clock[0],
                              idle_seconds=30, absolute_seconds=90)
    # Trusted internal issuance is synthetic-only. A separate regression below
    # exercises the actual locally signed OIDC code flow rather than this helper.
    handle = sessions.issue(VerifiedSubject(ISSUER, "reader", "synthetic-client"))
    source = SessionIdentitySource(sessions, handle, factory, clock=lambda: clock[0])
    service = SyntheticAssessmentSnapshotService(factory, identity_source=source)
    monkeypatch.setattr(scoped, "_utc_now", lambda: clock[0])
    try:
        yield SimpleNamespace(engine=snapshot_engine, factory=factory, clock=clock,
                              sessions=sessions, handle=handle, source=source, service=service)
    finally:
        with factory.begin() as database:
            for model in TABLES:
                database.execute(delete(model))


def change(ctx, model, row_id, **values):
    with ctx.factory.begin() as database:
        database.execute(update(model).where(model.id == row_id).values(**values))


def deny_both(ctx, packet):
    assert ctx.service.capture(1001) is None
    assert ctx.service.validate_resume(1001, packet) is None


def test_actual_signed_local_code_flow_captures_and_round_trips(snapshot_ctx, signing_key):
    ctx = snapshot_ctx
    handle = synthetic_code_flow_session(ctx.sessions, ctx.clock, signing_key)
    source = SessionIdentitySource(ctx.sessions, handle, ctx.factory, clock=lambda: ctx.clock[0])
    service = SyntheticAssessmentSnapshotService(ctx.factory, identity_source=source)
    packet = service.capture(1001)
    assert type(packet) is bytes and 0 < len(packet) <= 2048
    value = json.loads(packet)
    assert set(value) == FIELDS
    assert (value["organization_id"], value["vendor_id"], value["engagement_id"],
            value["assessment_id"]) == (1, 11, 101, 1001)
    assert value["schema_version"] == 1 and value["synthetic"] is True
    assert value["context_version"] == "linked-assessment-metadata-v1"
    assert value["source_version"] == "evidence-inventory-metadata-v1"
    assert all(re.fullmatch(r"[a-f0-9]{64}", value[key]) for key in
               ("context_fingerprint", "source_fingerprint"))
    assert service.validate_resume(1001, packet) == packet
    # Presentation whitespace is data, not a capability or stored application state.
    assert service.validate_resume(1001, json.dumps(value, indent=2).encode()) == packet
    for forbidden in (handle, "reader", "allowed.txt", "vendors/11/evidence",
                      "synthetic analyst note", "synthetic source interpretation",
                      "risk_score", "approval_status", "facts", "bytes"):
        assert forbidden.encode() not in packet


@pytest.mark.parametrize("assessment_id", [1002, 2001, 3001, 4001, 5001, 9999,
                                            0, -1, True, "1001", 1001.0, None])
def test_cross_org_sibling_legacy_wrong_links_and_invalid_targets_deny(snapshot_ctx, assessment_id):
    ctx = snapshot_ctx
    packet = ctx.service.capture(1001)
    assert packet is not None
    assert ctx.service.capture(assessment_id) is None
    assert ctx.service.validate_resume(assessment_id, packet) is None


@pytest.mark.parametrize("model,row_id", [(OrganizationMembership, 501), (EngagementAccessGrant, 701)])
@pytest.mark.parametrize("values", [{"status": "revoked"}, {"expires_at": NOW},
                                     {"valid_from": NOW + timedelta(seconds=1)}])
def test_current_member_and_exact_grant_checked_for_every_operation(snapshot_ctx, model, row_id, values):
    ctx = snapshot_ctx
    packet = ctx.service.capture(1001)
    assert packet is not None
    change(ctx, model, row_id, **values)
    deny_both(ctx, packet)


def test_fresh_membership_role_and_ambiguity_override_any_account_claim(snapshot_ctx):
    ctx = snapshot_ctx
    packet = ctx.service.capture(1001)
    change(ctx, OrganizationMembership, 501, role=ROLE_VIEWER)
    deny_both(ctx, packet)
    change(ctx, OrganizationMembership, 501, role=ROLE_ANALYST)
    with ctx.factory.begin() as database:
        database.add(OrganizationMembership(
            organization_id=2, issuer=ISSUER, subject="reader", role=ROLE_ANALYST,
            status="active", valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1)))
    deny_both(ctx, packet)


@pytest.mark.parametrize("operation", ["revoke", "rotate", "expire", "idle"])
def test_session_revocation_rotation_and_expiry_prevent_authority_reuse(snapshot_ctx, operation):
    ctx = snapshot_ctx
    packet = ctx.service.capture(1001)
    assert packet is not None
    if operation in ("revoke", "rotate"):
        assert getattr(ctx.sessions, operation)(ctx.handle)
    else:
        ctx.clock[0] += timedelta(seconds=90 if operation == "expire" else 30)
    deny_both(ctx, packet)


def test_missing_configuration_dto_and_fake_source_cannot_supply_authority(snapshot_ctx):
    ctx = snapshot_ctx
    identity = ctx.source.authenticated_identity()
    stand_in = SimpleNamespace(authenticated_identity=lambda: identity)
    for service in (
        SyntheticAssessmentSnapshotService(),
        SyntheticAssessmentSnapshotService(ctx.factory),
        SyntheticAssessmentSnapshotService(identity_source=ctx.source),
        SyntheticAssessmentSnapshotService(ctx.factory, identity_source=identity),
        SyntheticAssessmentSnapshotService(ctx.factory, identity_source=stand_in),
        SyntheticAssessmentSnapshotService(sessionmaker(bind=ctx.engine), identity_source=ctx.source),
    ):
        assert service.capture(1001) is None


@pytest.mark.parametrize("metadata", [None, {}, "{}", bytearray(b"{}"), b"", b"[]", b"null",
                                      b"not-json", b"\xff", b"{}" + b" " * 2048])
def test_only_bounded_well_formed_bytes_are_accepted(snapshot_ctx, metadata):
    assert snapshot_ctx.service.validate_resume(1001, metadata) is None


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 2), ("synthetic", 1), ("synthetic", False),
    ("context_version", "other-v1"), ("source_version", "other-v1"),
    ("organization_id", 2), ("vendor_id", 22), ("engagement_id", 102), ("assessment_id", 1002),
    ("organization_id", True), ("assessment_id", "1001"), ("assessment_id", 2**64),
    ("context_fingerprint", "A" * 64), ("source_fingerprint", "z" * 64),
    ("source_fingerprint", "b" * 64), ("context_fingerprint", "b" * 64),
])
def test_malformed_versions_types_ownership_and_fingerprints_deny(snapshot_ctx, field, value):
    ctx = snapshot_ctx
    packet = json.loads(ctx.service.capture(1001))
    packet[field] = value
    assert ctx.service.validate_resume(1001, json.dumps(packet).encode()) is None


@pytest.mark.parametrize("field,value", [("evidence_bytes", "synthetic bytes"), ("token", "fake"),
                                        ("approval_status", "Approved"), ("facts", []), ("notes", "x")])
def test_unknown_sensitive_fields_are_never_restored(snapshot_ctx, field, value):
    ctx = snapshot_ctx
    packet = json.loads(ctx.service.capture(1001))
    packet[field] = value
    assert ctx.service.validate_resume(1001, json.dumps(packet).encode()) is None


def test_missing_and_duplicate_fields_deny_even_when_duplicate_values_match(snapshot_ctx):
    ctx = snapshot_ctx
    packet = ctx.service.capture(1001)
    value = json.loads(packet)
    value.pop("source_version")
    assert ctx.service.validate_resume(1001, json.dumps(value).encode()) is None
    duplicate = packet[:-1] + b',"assessment_id":1001}'
    assert ctx.service.validate_resume(1001, duplicate) is None


@pytest.mark.parametrize("model,row_id,values,changed_hash", [
    (Assessment, 1001, {"assessment_type": "Changed"}, "context_fingerprint"),
    (Assessment, 1001, {"assessment_reason": "Reassessment"}, "context_fingerprint"),
    (Assessment, 1001, {"status": "In Progress"}, "context_fingerprint"),
    (Engagement, 101, {"service_name": "Changed service"}, "context_fingerprint"),
    (Engagement, 101, {"business_criticality": "Critical"}, "context_fingerprint"),
    (Engagement, 101, {"data_classification": "Restricted"}, "context_fingerprint"),
    (Engagement, 101, {"production_access": True}, "context_fingerprint"),
    (Engagement, 101, {"network_access": True}, "context_fingerprint"),
    (Engagement, 101, {"privileged_access": True}, "context_fingerprint"),
    (Engagement, 101, {"ai_enabled": True}, "context_fingerprint"),
    (Evidence, 9001, {"file_hash": "b" * 64}, "source_fingerprint"),
    (Evidence, 9001, {"document_type": "Recovery test"}, "source_fingerprint"),
    (Evidence, 9001, {"document_date": "2026-10-01"}, "source_fingerprint"),
    (Evidence, 9001, {"coverage_end": "2026-10-01"}, "source_fingerprint"),
    (Evidence, 9001, {"status": "Analyzed"}, "source_fingerprint"),
])
def test_changed_selected_context_or_inventory_invalidates_old_metadata(
        snapshot_ctx, model, row_id, values, changed_hash):
    ctx = snapshot_ctx
    before = ctx.service.capture(1001)
    assert before is not None
    change(ctx, model, row_id, **values)
    assert ctx.service.validate_resume(1001, before) is None
    after = ctx.service.capture(1001)
    assert after is not None
    assert json.loads(after)[changed_hash] != json.loads(before)[changed_hash]
    assert ctx.service.validate_resume(1001, after) == after


def test_inventory_addition_removal_and_wrong_vendor_cannot_be_silently_ignored(snapshot_ctx):
    ctx = snapshot_ctx
    before = ctx.service.capture(1001)
    with ctx.factory.begin() as database:
        database.add(Evidence(id=9990, vendor_id=11, assessment_id=1001,
                              document_type="Synthetic", document_name="extra.txt"))
    assert ctx.service.validate_resume(1001, before) is None
    added = ctx.service.capture(1001)
    assert added is not None
    with ctx.factory.begin() as database:
        database.execute(delete(Evidence).where(Evidence.id == 9990))
    assert ctx.service.validate_resume(1001, added) is None
    assert ctx.service.capture(1001) == before
    change(ctx, Evidence, 9001, vendor_id=22)
    deny_both(ctx, before)


@pytest.mark.parametrize("model,row_id,values", [
    (Assessment, 1001, {"engagement_id": 102}),
    (Assessment, 1001, {"vendor_id": 22}),
    (Engagement, 101, {"vendor_id": 22}),
    (Vendor, 11, {"organization_id": 2}),
])
def test_reparented_assessment_cannot_restore_prior_scope(snapshot_ctx, model, row_id, values):
    ctx = snapshot_ctx
    packet = ctx.service.capture(1001)
    assert packet is not None
    change(ctx, model, row_id, **values)
    deny_both(ctx, packet)


def test_bounded_inventory_allows_200_then_denies_overflow_without_truncation(snapshot_ctx):
    ctx = snapshot_ctx
    with ctx.factory.begin() as database:
        database.add_all(Evidence(id=10000 + i, vendor_id=11, assessment_id=1001,
                                 document_type="Synthetic", document_name=f"extra-{i}.txt")
                         for i in range(199))
    packet = ctx.service.capture(1001)
    assert packet is not None
    with ctx.factory.begin() as database:
        database.add(Evidence(id=10200, vendor_id=11, assessment_id=1001,
                              document_type="Synthetic", document_name="overflow.txt"))
    deny_both(ctx, packet)


def test_packet_is_only_metadata_and_capture_never_writes_or_restores(snapshot_ctx):
    ctx = snapshot_ctx

    def state():
        with ctx.factory() as database:
            return tuple(tuple(database.execute(select(model.__table__)).all()) for model in TABLES)

    before = state()
    mutations = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if re.match(r"\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE)\b", statement, re.I):
            mutations.append(statement)

    event.listen(ctx.engine, "before_cursor_execute", observe)
    try:
        packet = ctx.service.capture(1001)
        assert packet is not None and ctx.service.validate_resume(1001, packet) == packet
    finally:
        event.remove(ctx.engine, "before_cursor_execute", observe)
    assert mutations == [] and state() == before
    # Excluded contents neither enter the packet nor become implied restored state.
    change(ctx, Evidence, 9001, document_name="renamed.txt", storage_path="different/synthetic/key",
           analyst_notes="a different synthetic interpretation")
    change(ctx, Assessment, 1001, notes="different draft", risk_score=99, approval_status="Pending")
    assert ctx.service.validate_resume(1001, packet) == packet


@pytest.mark.parametrize("failure", ["commit", "source_factory", "pending_write"])
def test_transaction_failure_pending_write_and_swapped_dependency_release_no_metadata(
        snapshot_ctx, failure):
    ctx = snapshot_ctx
    packet = ctx.service.capture(1001)
    assert packet is not None
    if failure == "pending_write":
        def dirty_factory():
            database = ctx.factory()
            database.add(Organization(id=990, name="Synthetic pending", external_key="pending"))
            return database
        source = SessionIdentitySource(ctx.sessions, ctx.handle, dirty_factory, clock=lambda: ctx.clock[0])
        service = SyntheticAssessmentSnapshotService(dirty_factory, identity_source=source)
        assert service.capture(1001) is None
        with ctx.factory() as database:
            assert database.get(Organization, 990) is None
        return

    def before_commit(_database):
        if failure == "commit":
            raise RuntimeError("synthetic commit failure")
        ctx.source._database_sessions = sessionmaker(bind=ctx.engine)

    event.listen(ctx.factory, "before_commit", before_commit)
    try:
        assert ctx.service.capture(1001) is None
    finally:
        event.remove(ctx.factory, "before_commit", before_commit)
        ctx.source._database_sessions = ctx.factory
    assert ctx.service.validate_resume(1001, packet) == packet  # Lease cleanup succeeds.


def test_sql_transaction_is_acquired_before_session_lease(snapshot_ctx, monkeypatch):
    ctx = snapshot_ctx
    begun, observed = [], []
    store = ctx.sessions._store
    original = store.operation_lease

    def after_begin(database, _transaction, _connection):
        begun.append(database)

    @contextmanager
    def ordered_lease(key):
        # Closed identity-lookup sessions are not sufficient: the authorization
        # transaction itself must still be active when the store lease starts.
        observed.append(any(database.in_transaction() for database in begun))
        assert observed[-1], "store lease preceded the SQL authority transaction"
        with original(key):
            yield

    event.listen(ctx.factory, "after_begin", after_begin)
    monkeypatch.setattr(store, "operation_lease", ordered_lease)
    try:
        assert ctx.service.capture(1001) is not None
        assert observed == [True]
    finally:
        event.remove(ctx.factory, "after_begin", after_begin)


def test_session_expiry_during_final_sql_commit_releases_no_metadata(snapshot_ctx):
    ctx = snapshot_ctx

    def expire(_database):
        ctx.clock[0] += timedelta(seconds=90)

    event.listen(ctx.factory, "before_commit", expire)
    try:
        assert ctx.service.capture(1001) is None
    finally:
        event.remove(ctx.factory, "before_commit", expire)


@pytest.mark.parametrize("model,row_id", [
    (OrganizationMembership, 501), (EngagementAccessGrant, 701),
])
def test_membership_or_grant_expiry_during_sql_commit_releases_no_metadata(
        snapshot_ctx, model, row_id):
    ctx = snapshot_ctx
    change(ctx, model, row_id, expires_at=NOW + timedelta(seconds=1))

    def expire_authorization(_database):
        # SQL final checks observed a current grant/member. Simulate time spent
        # committing without expiring the independently valid server session.
        ctx.clock[0] += timedelta(seconds=2)

    event.listen(ctx.factory, "before_commit", expire_authorization)
    try:
        assert ctx.service.capture(1001) is None
    finally:
        event.remove(ctx.factory, "before_commit", expire_authorization)
    assert ctx.sessions.authenticate(ctx.handle) is not None


@pytest.mark.parametrize("model,row_id", [
    (OrganizationMembership, 501), (EngagementAccessGrant, 701),
])
def test_membership_or_grant_expiry_during_lease_cleanup_releases_no_metadata(
        snapshot_ctx, monkeypatch, model, row_id):
    ctx = snapshot_ctx
    change(ctx, model, row_id, expires_at=NOW + timedelta(seconds=1))
    store = ctx.sessions._store
    original = store.operation_lease
    cleaned_up = []

    @contextmanager
    def delayed_cleanup(key):
        with original(key):
            yield
        # SQL has committed and the manager's final authenticate has already
        # succeeded. A later cached authority-window check must still deny.
        ctx.clock[0] += timedelta(seconds=2)
        cleaned_up.append(True)

    monkeypatch.setattr(store, "operation_lease", delayed_cleanup)
    assert ctx.service.capture(1001) is None
    assert cleaned_up == [True]
    assert ctx.sessions.authenticate(ctx.handle) is not None


@pytest.mark.parametrize("stage", ["initial_identity", "commit"])
@pytest.mark.parametrize("dependency", [
    "service_source", "service_factory", "source_manager", "source_factory",
    "source_handle", "source_clock", "manager_store", "manager_clock",
    "manager_idle", "manager_absolute",
])
def test_dependency_replacement_denies_even_with_equivalent_identity_and_database(
        snapshot_ctx, monkeypatch, stage, dependency):
    ctx = snapshot_ctx
    original_identity = ctx.source.authenticated_identity()
    invoked = []

    def mutate():
        if invoked:
            return
        invoked.append(True)
        replacements = {
            "service_source": (ctx.service, "_identity_source", SessionIdentitySource(
                ctx.sessions, ctx.handle, ctx.factory, clock=ctx.source._clock)),
            "service_factory": (ctx.service, "_sessions", sessionmaker(bind=ctx.engine)),
            "source_manager": (ctx.source, "_sessions", SessionManager(
                ctx.sessions._store, clock=ctx.sessions._clock, idle_seconds=30, absolute_seconds=90)),
            "source_factory": (ctx.source, "_database_sessions", sessionmaker(bind=ctx.engine)),
            "source_handle": (ctx.source, "_handle", ctx.handle[::-1]),
            "source_clock": (ctx.source, "_clock", lambda: ctx.clock[0]),
            "manager_clock": (ctx.sessions, "_clock", lambda: ctx.clock[0]),
            "manager_idle": (ctx.sessions, "_idle", 31),
            "manager_absolute": (ctx.sessions, "_absolute", 91),
        }
        # The synthetic copy returns exactly the same authenticated session;
        # equality of a DTO cannot excuse replacement of the server dependency.
        other_store = InMemorySessionStore()
        other_store._records = dict(ctx.sessions._store._records)
        replacements["manager_store"] = (ctx.sessions, "_store", other_store)
        owner, attribute, value = replacements[dependency]
        monkeypatch.setattr(owner, attribute, value)

    if stage == "initial_identity":
        original = ctx.source.authenticated_identity

        def authenticated_identity():
            identity = original()
            if not invoked:
                assert identity == original_identity
                mutate()
            return identity

        monkeypatch.setattr(ctx.source, "authenticated_identity", authenticated_identity)
        assert ctx.service.capture(1001) is None
    else:
        def before_commit(_database):
            mutate()

        event.listen(ctx.factory, "before_commit", before_commit)
        try:
            assert ctx.service.capture(1001) is None
        finally:
            event.remove(ctx.factory, "before_commit", before_commit)
    assert invoked == [True]


@pytest.mark.parametrize("operation", ["revoke", "rotate"])
def test_session_mutation_waits_through_final_sql_commit_then_old_handle_denies(
        snapshot_ctx, monkeypatch, operation):
    ctx = snapshot_ctx
    committing, release, attempted = Event(), Event(), Event()
    store = ctx.sessions._store
    original_mutation = getattr(store, operation)

    def pause_commit(_database):
        committing.set()
        assert release.wait(5), "synthetic test did not release SQL commit"

    def observed_mutation(*args):
        attempted.set()
        return original_mutation(*args)

    monkeypatch.setattr(store, operation, observed_mutation)
    event.listen(ctx.factory, "before_commit", pause_commit)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            capture = workers.submit(ctx.service.capture, 1001)
            try:
                assert committing.wait(5), "capture did not reach its final SQL commit"
                mutation = workers.submit(getattr(ctx.sessions, operation), ctx.handle)
                assert attempted.wait(2)
                with pytest.raises(TimeoutError):
                    mutation.result(timeout=0.05)
            finally:
                release.set()
            packet = capture.result(timeout=5)
            assert packet is not None
            assert mutation.result(timeout=5)
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause_commit)
    deny_both(ctx, packet)


@pytest.mark.parametrize("model,row_id,values", [
    (EngagementAccessGrant, 701, {"status": "revoked"}),
    (Assessment, 1001, {"engagement_id": 102}),
])
def test_postgres_grant_and_parent_mutations_cannot_pass_final_commit_boundary(
        snapshot_ctx, model, row_id, values):
    ctx = snapshot_ctx
    if ctx.engine.dialect.name != "postgresql":
        pytest.skip("requires Actions' isolated PostgreSQL service and two connections")
    committing, release = Event(), Event()

    def pause_commit(_database):
        committing.set()
        assert release.wait(5), "synthetic test did not release SQL commit"

    event.listen(ctx.factory, "before_commit", pause_commit)
    try:
        with ThreadPoolExecutor(max_workers=1) as workers:
            capture = workers.submit(ctx.service.capture, 1001)
            try:
                assert committing.wait(5), "capture did not reach its final SQL commit"
                with ctx.engine.connect() as connection:
                    with pytest.raises(DBAPIError) as error:
                        with connection.begin():
                            connection.exec_driver_sql("SET LOCAL lock_timeout = '150ms'")
                            connection.execute(update(model).where(model.id == row_id).values(**values))
                    assert (getattr(error.value.orig, "sqlstate", None)
                            or getattr(error.value.orig, "pgcode", None)) == "55P03"
            finally:
                release.set()
            packet = capture.result(timeout=5)
            assert packet is not None
    finally:
        release.set()
        event.remove(ctx.factory, "before_commit", pause_commit)
    # The same competing change can commit after issuance; the next call denies.
    change(ctx, model, row_id, **values)
    deny_both(ctx, packet)
