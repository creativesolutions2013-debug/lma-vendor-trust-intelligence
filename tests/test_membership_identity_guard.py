"""Synthetic predicate insertion races; no customer database or live identity."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event
from uuid import uuid4
import os

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from test_tenant_read_scope import ISSUER, NOW, postgres_ctx
from src.db import Organization, OrganizationMembership
from src.membership_identity_guard import (
    TRIGGER_NAME, acquire_membership_identity_guard,
)
from src.tenant_read_scope import ScopedCounts, TenantReadService


ROOT = Path(__file__).resolve().parents[1]
BEFORE = "0014_organization_engagement_authorization"
HEAD = "0014a_membership_identity_guard"


def configuration():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


def membership(**changes):
    row = dict(id=951, organization_id=2, issuer=ISSUER, subject="reader-a",
               role="Analyst", status="active", valid_from=NOW - timedelta(days=1),
               expires_at=NOW + timedelta(days=1))
    row.update(changes)
    return row


def qualified_table(ctx):
    schema = ctx.engine.get_execution_options()["schema_translate_map"][None]
    quote = ctx.engine.dialect.identifier_preparer.quote
    return quote(schema) + "." + quote("organization_memberships")


@pytest.mark.parametrize("operation", ["list_evidence", "visible_counts"])
@pytest.mark.parametrize("replica", [False, True])
def test_postgres_new_membership_blocks_after_final_validation_through_commit(postgres_ctx, monkeypatch,
                                                                           operation, replica):
    """The original hole occurs after _finish_authorized, before context commit.

    A real second physical connection must time out on INSERT, even in replica
    mode, instead of committing an ambiguity while the result is being issued.
    """
    ctx = postgres_ctx
    validated, release = Event(), Event()
    original = ctx.service._finish_authorized
    def finish(*args, **kwargs):
        original(*args, **kwargs)
        validated.set()
        if not release.wait(10):
            raise RuntimeError("Synthetic issuance coordination timed out")
    monkeypatch.setattr(ctx.service, "_finish_authorized", finish)
    def insert():
        with ctx.factory() as database:
            database.execute(sa.text("SET LOCAL lock_timeout = '500ms'"))
            if replica:
                database.execute(sa.text("SET LOCAL session_replication_role = 'replica'"))
            with pytest.raises(OperationalError) as failure:
                database.execute(OrganizationMembership.__table__.insert(), membership())
            assert getattr(failure.value.orig, "sqlstate", None) == "55P03"
            database.rollback()
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(getattr(ctx.service, operation))
        try:
            assert validated.wait(10)
            executor.submit(insert).result(timeout=10)
        finally:
            release.set()
        result = pending.result(timeout=10)
    if operation == "list_evidence":
        assert [row.id for row in result] == [9001]
    else:
        assert result == ScopedCounts(1, 1, 1, 1)
    # The same INSERT succeeds after issuance. It invalidates the next request.
    monkeypatch.setattr(ctx.service, "_finish_authorized", original)
    with ctx.factory() as database:
        database.execute(OrganizationMembership.__table__.insert(), membership())
        database.commit()
    assert ctx.service.list_evidence() == ()
    assert ctx.service.visible_counts() == ScopedCounts(0, 0, 0, 0)


@pytest.mark.parametrize("change", [{"issuer": "https://different.synthetic.invalid"},
                                    {"subject": "different-subject"}])
def test_postgres_other_identity_inserts_are_not_globally_serialized(postgres_ctx, change):
    ctx = postgres_ctx
    with ctx.service._authorized_transaction("vendor.read") as (session, scope):
        def insert():
            with ctx.factory() as database:
                database.execute(sa.text("SET LOCAL lock_timeout = '500ms'"))
                database.execute(OrganizationMembership.__table__.insert(), membership(**change))
                database.commit()
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(insert).result(timeout=10)
        ctx.service._finish_authorized(session, scope, "vendor.read")
    assert ctx.service.list_vendors()


@pytest.mark.parametrize("change", [{"issuer": ISSUER, "subject": "reader-a"},
                                    {"subject": "reader-a"}])
def test_postgres_update_into_guarded_identity_takes_exclusive_predicate_lock(postgres_ctx, change):
    ctx = postgres_ctx
    initial = membership(issuer=ISSUER if "issuer" not in change else "https://old.synthetic.invalid",
                         subject="unrelated-original")
    with ctx.factory() as database:
        database.execute(OrganizationMembership.__table__.insert(), initial)
        database.commit()
    with ctx.service._authorized_transaction("vendor.read") as (session, scope):
        def rename():
            with ctx.factory() as database:
                database.execute(sa.text("SET LOCAL lock_timeout = '500ms'"))
                with pytest.raises(OperationalError) as failure:
                    database.execute(sa.update(OrganizationMembership).where(
                        OrganizationMembership.id == 951).values(**change))
                assert getattr(failure.value.orig, "sqlstate", None) == "55P03"
                database.rollback()
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(rename).result(timeout=10)
        ctx.service._finish_authorized(session, scope, "vendor.read")


@pytest.mark.parametrize("state", ["absent", "disabled", "normal"])
def test_postgres_guard_absent_or_not_always_enabled_denies(postgres_ctx, state):
    ctx = postgres_ctx
    table = qualified_table(ctx)
    statement = (f"DROP TRIGGER {TRIGGER_NAME} ON {table}" if state == "absent"
                 else f"ALTER TABLE {table} {'DISABLE' if state == 'disabled' else 'ENABLE'} TRIGGER {TRIGGER_NAME}")
    with ctx.engine.begin() as connection:
        connection.exec_driver_sql(statement)
    assert ctx.service.list_evidence() == ()
    assert ctx.service.visible_counts() == ScopedCounts(0, 0, 0, 0)


def test_postgres_wrong_table_cannot_borrow_another_tables_guard(postgres_ctx):
    ctx = postgres_ctx
    schema = ctx.engine.get_execution_options()["schema_translate_map"][None]
    quote = ctx.engine.dialect.identifier_preparer.quote
    with ctx.engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE TABLE {quote(schema)}.unprotected_memberships (LIKE {qualified_table(ctx)} INCLUDING ALL)")
        unprotected = sa.Table("unprotected_memberships", sa.MetaData())
        with pytest.raises(PermissionError, match="Scoped access denied"):
            acquire_membership_identity_guard(connection, unprotected, ISSUER, "reader-a")


def test_postgres_autocommit_cannot_release_a_transaction_lock_early(postgres_ctx):
    with postgres_ctx.engine.execution_options(isolation_level="AUTOCOMMIT").connect() as connection:
        connection.execute(sa.text("SELECT 1"))  # SQLAlchemy's logical transaction exists.
        assert connection.in_transaction()
        with pytest.raises(PermissionError, match="Scoped access denied"):
            acquire_membership_identity_guard(connection, OrganizationMembership.__table__, ISSUER, "reader-a")


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
def test_postgres_snapshot_isolation_cannot_hide_membership_committed_before_guard(postgres_ctx, isolation):
    """A transaction snapshot cannot be repaired by taking a later advisory lock."""
    ctx = postgres_ctx
    with ctx.engine.execution_options(isolation_level=isolation).connect() as connection:
        with connection.begin():
            total = sa.select(sa.func.count()).select_from(OrganizationMembership)
            before = connection.execute(total).scalar_one()
            with ctx.factory() as writer:
                writer.execute(OrganizationMembership.__table__.insert(), membership())
                writer.commit()
            assert connection.execute(total).scalar_one() == before
            with pytest.raises(PermissionError, match="Scoped access denied"):
                acquire_membership_identity_guard(connection, OrganizationMembership.__table__, ISSUER, "reader-a")


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
def test_postgres_non_read_committed_scope_denies_even_with_valid_identity(postgres_ctx, isolation):
    factory = sessionmaker(bind=postgres_ctx.engine.execution_options(isolation_level=isolation),
                           autoflush=False, expire_on_commit=False)
    service = TenantReadService(factory, identity_source=postgres_ctx.source)
    assert service.list_evidence() == ()
    assert service.visible_counts() == ScopedCounts(0, 0, 0, 0)


@pytest.fixture(scope="module", params=("sqlite", "postgres"))
def migrated(request, tmp_path_factory):
    root, schema = None, None
    if request.param == "postgres":
        source = os.getenv("DATABASE_URL", "")
        if os.getenv("GITHUB_ACTIONS") != "true" or not source.startswith("postgresql"):
            pytest.skip("Predicate migration PostgreSQL cases use the synthetic service only.")
        root = sa.create_engine(source)
        schema = "membership_guard_migration_" + uuid4().hex
        with root.begin() as connection:
            connection.execute(sa.schema.CreateSchema(schema))
        url = sa.engine.make_url(source).update_query_dict({"options": "-csearch_path=" + schema}).render_as_string(hide_password=False)
    else:
        url = "sqlite:///" + str(tmp_path_factory.mktemp("membership_guard") / "synthetic%guard.db")
    engine = sa.create_engine(url)
    try:
        with pytest.MonkeyPatch.context() as environment:
            environment.setenv("DATABASE_URL", url)
            command.upgrade(configuration(), BEFORE)
            with engine.begin() as connection:
                connection.execute(Organization.__table__.insert(), dict(id=1, external_key="synthetic-guard", name="Synthetic guard"))
                connection.execute(OrganizationMembership.__table__.insert(), membership(id=1, organization_id=1))
                columns = tuple(column["name"] for column in sa.inspect(connection).get_columns("organization_memberships"))
                previous = tuple(tuple(row) for row in connection.exec_driver_sql("SELECT * FROM organization_memberships ORDER BY id"))
                root_page = connection.exec_driver_sql("SELECT rootpage FROM sqlite_master WHERE name='organization_memberships'").scalar_one() if request.param == "sqlite" else None
            command.upgrade(configuration(), HEAD)
        yield dict(engine=engine, url=url, previous=previous, columns=columns, root_page=root_page, schema=schema)
    finally:
        engine.dispose()
        if root is not None:
            with root.begin() as connection:
                connection.execute(sa.schema.DropSchema(schema, cascade=True))
            root.dispose()


def test_guard_upgrade_preserves_existing_membership_rows_and_constraints(migrated):
    with migrated["engine"].connect() as connection:
        assert tuple(tuple(row) for row in connection.exec_driver_sql("SELECT * FROM organization_memberships ORDER BY id")) == migrated["previous"]
        assert tuple(column["name"] for column in sa.inspect(connection).get_columns("organization_memberships")) == migrated["columns"]
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        assert any(set(item["column_names"]) == {"organization_id", "issuer", "subject"}
                   for item in sa.inspect(connection).get_unique_constraints("organization_memberships"))
        if migrated["root_page"] is not None:
            assert connection.exec_driver_sql("SELECT rootpage FROM sqlite_master WHERE name='organization_memberships'").scalar_one() == migrated["root_page"]


def test_guard_installs_in_the_current_schema_or_uses_native_sqlite_reservation(migrated):
    with migrated["engine"].begin() as connection:
        if connection.dialect.name == "postgresql":
            trigger = connection.execute(sa.text("""
                SELECT t.tgenabled, n.nspname FROM pg_catalog.pg_trigger t
                JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
                JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
                WHERE t.tgname=:name AND t.tgrelid=pg_catalog.to_regclass('organization_memberships')
            """), {"name": TRIGGER_NAME}).one()
            assert tuple(trigger) == ("A", migrated["schema"])
        acquire_membership_identity_guard(connection, OrganizationMembership.__table__, ISSUER, "reader-a")


def test_guard_downgrade_refuses_before_removing_serialization(migrated, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", migrated["url"])
    with pytest.raises(RuntimeError, match="reviewed authorization rollback plan"):
        command.downgrade(configuration(), BEFORE)
    with migrated["engine"].begin() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        acquire_membership_identity_guard(connection, OrganizationMembership.__table__, ISSUER, "reader-a")


def test_sqlite_guard_needs_no_additional_schema_or_identity_configuration():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            acquire_membership_identity_guard(connection, sa.Table("organization_memberships", sa.MetaData()), ISSUER, "reader-a")
    finally:
        engine.dispose()
