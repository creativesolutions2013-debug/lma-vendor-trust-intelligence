"""Synthetic delivery provenance is additive, exact-source bound and immutable."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
from uuid import uuid4
import json
import os

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from src.authz import PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_READ
from src.db import Base, SyntheticEvidenceObject, SyntheticVendorHandoff
from src.synthetic_handoff_provenance import (
    encode_handoff_metadata, handoff_in_transaction, record_handoff_in_transaction,
    require_synthetic_handoff_guards, synthetic_handoff_guard_statements,
)
from src.tenant_read_scope import TenantReadService
from test_resumable_assessment import assessment_ctx, _source
from test_synthetic_custody_migration import object_values, seed
from test_synthetic_revision_migration import config, snapshot


HEAD = "0014d_vendor_handoff"
PREVIOUS = "0014c_assessment_revisions"


def metadata(**changes):
    result = dict(schema_version=1, invitation_id="a" * 32,
        vendor_issuer="https://127.0.0.1:8443/vendor/synthetic-idp", vendor_subject="synthetic-vendor",
        vendor_session_id="sid_" + "v" * 43, vendor_role="Authenticated synthetic invitee",
        submitted_at="2026-11-24T00:00:00+00:00", kind="test", observed_on="2026-11-23",
        requirement_id="BCP-01", inviter_issuer="https://127.0.0.1:8443/synthetic-idp",
        inviter_subject="synthetic-analyst", inviter_session_id="sid_" + "a" * 43)
    result.update(changes)
    return result


def handoff_values(**changes):
    source = object_values()
    payload = encode_handoff_metadata(metadata())
    result = {key: source[key] for key in ("evidence_id", "organization_id", "vendor_id", "engagement_id", "assessment_id", "generation", "sha256")}
    result.update(metadata_payload=payload, metadata_sha256=sha256(payload).hexdigest())
    result.update(changes)
    return result


@pytest.fixture(scope="module", params=("sqlite", "postgres"))
def migrated_handoff(request, tmp_path_factory):
    admin = schema = None
    if request.param == "postgres":
        source = os.getenv("DATABASE_URL", "")
        if os.getenv("GITHUB_ACTIONS") != "true" or not source.startswith("postgresql"):
            pytest.skip("Handoff PostgreSQL variants use only disposable CI service schemas.")
        schema = "m7_handoff_migration_" + uuid4().hex
        admin = sa.create_engine(source)
        with admin.begin() as connection:
            connection.execute(sa.schema.CreateSchema(schema))
        url = sa.engine.make_url(source).update_query_dict({"options": "-csearch_path=" + schema}).render_as_string(hide_password=False)
    else:
        url = "sqlite:///" + str(tmp_path_factory.mktemp("handoff_migration") / "synthetic%handoff.db")
    environment = pytest.MonkeyPatch()
    environment.setenv("DATABASE_URL", url)
    engine = sa.create_engine(url)
    try:
        command.upgrade(config(), PREVIOUS)
        with engine.begin() as connection:
            seed(connection)
            connection.execute(SyntheticEvidenceObject.__table__.insert(), object_values())
            before = snapshot(connection)
            roots = (dict(connection.exec_driver_sql("SELECT name,rootpage FROM sqlite_master WHERE type='table'").all())
                     if engine.dialect.name == "sqlite" else None)
        command.upgrade(config(), HEAD)
        yield dict(engine=engine, before=before, roots=roots)
    finally:
        engine.dispose()
        environment.undo()
        if admin is not None:
            with admin.begin() as connection:
                connection.execute(sa.schema.DropSchema(schema, cascade=True))
            admin.dispose()


@pytest.fixture
def guarded_handoff(migrated_handoff):
    with migrated_handoff["engine"].connect() as connection, connection.begin():
        connection.execute(SyntheticVendorHandoff.__table__.insert(), handoff_values())
        try:
            yield connection
        finally:
            connection.rollback()


def test_additive_upgrade_keeps_original_rows_and_sqlite_root_pages(migrated_handoff):
    with migrated_handoff["engine"].connect() as connection:
        assert snapshot(connection) == migrated_handoff["before"]
        assert connection.execute(sa.select(sa.func.count()).select_from(SyntheticVendorHandoff)).scalar_one() == 0
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        require_synthetic_handoff_guards(connection, SyntheticVendorHandoff.__table__)
        if migrated_handoff["roots"] is not None:
            roots = dict(connection.exec_driver_sql("SELECT name,rootpage FROM sqlite_master WHERE type='table'").all())
            assert all(roots[key] == value for key, value in migrated_handoff["roots"].items())


@pytest.mark.parametrize("changes", [dict(organization_id=2), dict(vendor_id=22), dict(engagement_id=201),
    dict(assessment_id=2001), dict(evidence_id=9201), dict(generation="b" * 32), dict(sha256="b" * 64),
    dict(metadata_payload=b""), dict(metadata_payload=b"x" * 4097), dict(metadata_payload="text"),
    dict(metadata_sha256="A" * 64), dict(metadata_sha256="g" * 64)])
def test_raw_insert_cannot_rebind_source_or_exceed_contract(migrated_handoff, changes):
    with migrated_handoff["engine"].connect() as connection, connection.begin():
        # psycopg rejects a Python str for bytea before SQL reaches the server.
        # Keep that adaptation failure separate from database guard failures.
        postgres_text = connection.dialect.name == "postgresql" and isinstance(changes.get("metadata_payload"), str)
        expected = TypeError if postgres_text else (DBAPIError, sa.exc.StatementError)
        with pytest.raises(expected, match="bytes or buffer expected" if postgres_text else None), connection.begin_nested():
            connection.execute(SyntheticVendorHandoff.__table__.insert(), handoff_values(**changes))
        assert connection.execute(sa.select(sa.func.count()).select_from(SyntheticVendorHandoff)).scalar_one() == 0


@pytest.mark.parametrize("operation", ["update", "delete", "replace", "rowid", "oid", "_rowid_"])
def test_history_cannot_be_mutated_or_replaced(guarded_handoff, operation):
    connection = guarded_handoff
    table = SyntheticVendorHandoff.__table__
    before = connection.execute(sa.select(table)).all()
    if operation == "update":
        statement = table.update().values(metadata_payload=b"changed")
    elif operation == "delete":
        statement = table.delete()
    elif operation == "replace":
        if connection.dialect.name != "sqlite":
            pytest.skip("REPLACE is a SQLite operation.")
        statement = table.insert().prefix_with("OR REPLACE").values(**handoff_values())
    else:
        if connection.dialect.name != "sqlite":
            pytest.skip("Hidden rowid aliases are SQLite-specific.")
        statement = sa.text(f"UPDATE synthetic_vendor_handoffs SET {operation}=42")
    with pytest.raises(DBAPIError), connection.begin_nested():
        connection.execute(statement)
    assert connection.execute(sa.select(table)).all() == before


def test_postgres_truncate_and_replica_session_cannot_remove_handoffs(guarded_handoff):
    if guarded_handoff.dialect.name != "postgresql":
        pytest.skip("PostgreSQL ALWAYS guards require disposable PostgreSQL.")
    connection = guarded_handoff
    connection.exec_driver_sql("SET LOCAL session_replication_role=replica")
    with pytest.raises(DBAPIError), connection.begin_nested():
        connection.exec_driver_sql("TRUNCATE synthetic_vendor_handoffs")
    with pytest.raises(DBAPIError), connection.begin_nested():
        connection.execute(SyntheticVendorHandoff.__table__.delete())
    assert connection.execute(sa.select(sa.func.count()).select_from(SyntheticVendorHandoff)).scalar_one() == 1


@pytest.mark.parametrize("name", ["m7_handoff_insert", "m7_handoff_no_update", "m7_handoff_no_delete"])
def test_missing_sqlite_guards_deny_health(name):
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP TRIGGER {name}")
            with pytest.raises(PermissionError):
                require_synthetic_handoff_guards(connection, SyntheticVendorHandoff.__table__)
    finally:
        engine.dispose()


def test_same_guard_names_on_rowid_prototype_do_not_pass_health():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE synthetic_vendor_handoffs(evidence_id INTEGER PRIMARY KEY)")
            for action in ("insert", "update", "delete"):
                name = "m7_handoff_insert" if action == "insert" else "m7_handoff_no_" + action
                connection.exec_driver_sql(f"CREATE TRIGGER {name} BEFORE {action} ON synthetic_vendor_handoffs BEGIN SELECT 1; END")
            with pytest.raises(PermissionError):
                require_synthetic_handoff_guards(connection, SyntheticVendorHandoff.__table__)
    finally:
        engine.dispose()


@pytest.mark.parametrize("changes", [dict(schema_version=True), dict(schema_version=2), dict(invitation_id="token"),
    dict(vendor_subject="synthetic-analyst"), dict(vendor_role="Analyst"), dict(vendor_session_id="v" * 43),
    dict(inviter_session_id="bearer"), dict(submitted_at="2026-11-24T00:00:00"), dict(kind="approved"),
    dict(observed_on="2026-11-25"), dict(requirement_id="../neighbor"), dict(vendor_issuer="https://local\nsecret")])
def test_metadata_contract_rejects_bearer_lookalikes_and_non_native_claims(changes):
    with pytest.raises((ValueError, TypeError)):
        encode_handoff_metadata(metadata(**changes))


def test_metadata_contract_rejects_unknown_or_missing_fields():
    for value in (dict(metadata(), invitation_token="never-persist"), {key: value for key, value in metadata().items() if key != "vendor_subject"}):
        with pytest.raises(ValueError):
            encode_handoff_metadata(value)


@contextmanager
def authorized(ctx):
    reader = TenantReadService(ctx.factory, identity_source=ctx.source)
    permissions = (PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_READ)
    with reader._authorized_transaction(permissions) as (session, scope):
        with ctx.source.session_operation():
            yield session, scope
            reader._finish_authorized(session, scope, permissions)
    reader._finish_cached_windows(scope, permissions)


def test_native_metadata_roundtrip_is_exact_source_bound(assessment_ctx):
    ctx = assessment_ctx
    _, receipt = _source(ctx)
    data = metadata(submitted_at=ctx.clock[0].isoformat(), observed_on=ctx.clock[0].date().isoformat())
    with authorized(ctx) as (session, scope):
        assert handoff_in_transaction(session, scope, receipt) is None
        record_handoff_in_transaction(session, scope, receipt, data)
        assert handoff_in_transaction(session, scope, receipt) == data
    with authorized(ctx) as (session, scope):
        assert handoff_in_transaction(session, scope, receipt) == data
    _, other = _source(ctx, name="another.txt", content=b"Other synthetic original")
    with authorized(ctx) as (session, scope):
        assert handoff_in_transaction(session, scope, other) is None
    with ctx.factory() as database:
        assert database.execute(sa.select(sa.func.count()).select_from(SyntheticVendorHandoff)).scalar_one() == 1


@pytest.mark.parametrize("changes", [dict(organization_id=2), dict(vendor_id=22), dict(assessment_id=2001),
    dict(engagement_id=201), dict(evidence_id=999), dict(generation="b" * 32), dict(sha256="b" * 64)])
def test_forged_receipts_never_authorize_metadata(assessment_ctx, changes):
    from dataclasses import replace
    ctx = assessment_ctx
    _, receipt = _source(ctx)
    with pytest.raises(PermissionError), authorized(ctx) as (session, scope):
        handoff_in_transaction(session, scope, replace(receipt, **changes))


@pytest.mark.parametrize("attack", ["hash", "duplicate", "noncanonical", "unknown", "bad_subject"])
def test_stored_metadata_tampering_is_withheld(assessment_ctx, attack):
    ctx = assessment_ctx
    _, receipt = _source(ctx)
    data = metadata(submitted_at=ctx.clock[0].isoformat(), observed_on=None)
    with authorized(ctx) as (session, scope):
        record_handoff_in_transaction(session, scope, receipt, data)
    # A privileged schema owner can bypass guards; consumers still reject
    # malformed or inconsistent metadata instead of publishing it as history.
    with ctx.factory.begin() as database:
        connection = database.connection()
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("DROP TRIGGER m7_handoff_no_update")
        else:
            # ORM SQL uses schema_translate_map, whereas raw SQL does not.
            # Target this test's UUID-owned schema, not the migration fixture's
            # current search_path (which may point to another handoff table).
            assert ctx.schema is not None
            quote = connection.dialect.identifier_preparer.quote
            handoffs = quote(ctx.schema) + "." + quote(SyntheticVendorHandoff.__tablename__)
            connection.exec_driver_sql(f"ALTER TABLE {handoffs} DISABLE TRIGGER m7_handoff_no_mutation")
        payload = encode_handoff_metadata(data)
        if attack == "duplicate":
            payload = payload[:-1] + b',"schema_version":1}'
        elif attack == "noncanonical":
            payload = json.dumps(data, indent=2).encode()
        elif attack == "unknown":
            payload = payload[:-1] + b',"approved":true}'
        elif attack == "bad_subject":
            payload = payload.replace(b"synthetic-vendor", b"synthetic-admin")
        digest = "b" * 64 if attack == "hash" else sha256(payload).hexdigest()
        database.execute(sa.update(SyntheticVendorHandoff).values(metadata_payload=payload, metadata_sha256=digest))
        # Restore health so this test exercises payload verification as well.
        if connection.dialect.name == "sqlite":
            statement = next(statement for statement in synthetic_handoff_guard_statements(connection.dialect)
                             if "m7_handoff_no_update" in statement)
            connection.exec_driver_sql(statement)
        else:
            connection.exec_driver_sql(f"ALTER TABLE {handoffs} ENABLE ALWAYS TRIGGER m7_handoff_no_mutation")
    with pytest.raises((ValueError, PermissionError)), authorized(ctx) as (session, scope):
        handoff_in_transaction(session, scope, receipt)


def test_downgrade_refuses_without_mutating_existing_records(migrated_handoff, monkeypatch):
    engine = migrated_handoff["engine"]
    with engine.connect() as connection:
        before = snapshot(connection)
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError, match="retention"):
        command.downgrade(config(), PREVIOUS)
    with engine.connect() as connection:
        assert snapshot(connection) == before
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD


def test_postgres_offline_upgrade_refuses_before_handoff_ddl(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://synthetic.invalid/never-connect")
    output = StringIO()
    cfg = config()
    cfg.output_buffer = output
    with pytest.raises(RuntimeError, match="online schema verification"):
        command.upgrade(cfg, PREVIOUS + ":" + HEAD, sql=True)
    assert "CREATE TABLE synthetic_vendor_handoffs" not in output.getvalue()
