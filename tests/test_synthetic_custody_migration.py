"""Synthetic additive migration, immutable linkage and pragma-independent guards."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
from threading import Event
from uuid import uuid4
import os

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from src.db import Assessment, Base, Engagement, Evidence, Organization, SyntheticEvidenceObject, Vendor
from src.synthetic_custody_guards import require_synthetic_custody_guards


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "0014a_membership_identity_guard"
HEAD = "0014b_synthetic_custody"
PARENTS = {"organizations": (Organization, 1), "vendors": (Vendor, 11),
           "engagements": (Engagement, 101), "assessments": (Assessment, 1001),
           "evidence": (Evidence, 9001)}


def config():
    result = Config(str(ROOT / "alembic.ini"))
    result.set_main_option("script_location", str(ROOT / "migrations"))
    return result


def object_values(**changes):
    payload = b"small original synthetic fixture\n"
    result = dict(evidence_id=9001, organization_id=1, vendor_id=11, engagement_id=101,
                  assessment_id=1001, generation="a" * 32,
                  storage_key="vendors/11/evidence/m7_" + "a" * 32 + ".bin",
                  byte_length=len(payload), payload=payload, sha256=sha256(payload).hexdigest(),
                  document_name="synthetic.txt", created_at=datetime(2026, 11, 24, tzinfo=timezone.utc),
                  issuer="https://synthetic.invalid", subject="synthetic-reader",
                  session_id="sid_synthetic_correlation", effective_role="Analyst", membership_id=501)
    result.update(changes)
    return result


def seed(connection):
    for org, vendor, engagement, assessment, evidence in ((1, 11, 101, 1001, 9001),
                                                         (2, 22, 201, 2001, 9201)):
        connection.execute(Organization.__table__.insert(), dict(id=org, external_key=f"synthetic-{org}", name="Synthetic"))
        connection.execute(Vendor.__table__.insert(), dict(id=vendor, organization_id=org, legal_name="Synthetic", display_name="Synthetic"))
        connection.execute(Engagement.__table__.insert(), dict(id=engagement, vendor_id=vendor, service_name="Synthetic"))
        connection.execute(Assessment.__table__.insert(), dict(id=assessment, vendor_id=vendor, engagement_id=engagement, assessment_type="Synthetic"))
        value = object_values()
        connection.execute(Evidence.__table__.insert(), dict(id=evidence, vendor_id=vendor, assessment_id=assessment,
            document_type="Synthetic", document_name="synthetic.txt",
            storage_path=value["storage_key"] if org == 1 else None,
            file_hash=value["sha256"] if org == 1 else None))


@pytest.fixture(scope="module", params=("sqlite", "postgres"))
def migrated(request, tmp_path_factory):
    admin = schema = None
    if request.param == "postgres":
        source = os.getenv("DATABASE_URL", "")
        if os.getenv("GITHUB_ACTIONS") != "true" or not source.startswith("postgresql"):
            pytest.skip("PostgreSQL migration variants require the disposable CI service.")
        schema = "m7_custody_migration_" + uuid4().hex
        admin = sa.create_engine(source)
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        url = sa.engine.make_url(source).update_query_dict({"options": "-csearch_path=" + schema}).render_as_string(hide_password=False)
    else:
        url = "sqlite:///" + str(tmp_path_factory.mktemp("custody_migration") / "synthetic%only.db")
    environment = pytest.MonkeyPatch()
    environment.setenv("DATABASE_URL", url)
    engine = sa.create_engine(url)
    try:
        command.upgrade(config(), PREVIOUS)
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO vendors (id, legal_name, display_name) VALUES (701, 'Synthetic legacy', 'Synthetic legacy')")
            connection.exec_driver_sql("INSERT INTO engagements (id, vendor_id, service_name) VALUES (702, 701, 'Synthetic legacy')")
            connection.exec_driver_sql("INSERT INTO assessments (id, vendor_id, assessment_type) VALUES (703, 701, 'Synthetic legacy')")
            connection.exec_driver_sql("INSERT INTO evidence (id, vendor_id, assessment_id, document_type, document_name, storage_path) VALUES (704, 701, 703, 'Synthetic', 'legacy.txt', 's3://historical-synthetic/legacy.txt')")
            before = {model.__tablename__: tuple(tuple(row) for row in connection.execute(sa.select(model.__table__)))
                      for model in (Vendor, Engagement, Assessment, Evidence)}
            roots = (tuple(connection.exec_driver_sql("SELECT name, rootpage FROM sqlite_master WHERE type='table' ORDER BY name"))
                     if engine.dialect.name == "sqlite" else None)
        command.upgrade(config(), HEAD)
        yield dict(engine=engine, url=url, before=before, roots=roots)
    finally:
        engine.dispose()
        environment.undo()
        if admin is not None:
            with admin.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            admin.dispose()


@pytest.fixture
def guarded(migrated):
    with migrated["engine"].connect() as connection, connection.begin():
        if connection.dialect.name == "sqlite":
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA recursive_triggers").scalar_one() == 0
        seed(connection)
        connection.execute(SyntheticEvidenceObject.__table__.insert(), object_values())
        try:
            yield connection
        finally:
            # Rollback, not DELETE: retained custody is intentionally immutable.
            connection.rollback()


def test_additive_upgrade_preserves_all_legacy_rows_and_root_pages(migrated):
    with migrated["engine"].connect() as connection:
        for model in (Vendor, Engagement, Assessment, Evidence):
            assert tuple(tuple(row) for row in connection.execute(sa.select(model.__table__))) == migrated["before"][model.__tablename__]
        assert connection.execute(sa.select(sa.func.count()).select_from(SyntheticEvidenceObject)).scalar_one() == 0
        require_synthetic_custody_guards(connection, SyntheticEvidenceObject.__table__)
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        if migrated["roots"] is not None:
            roots = dict(connection.exec_driver_sql("SELECT name, rootpage FROM sqlite_master WHERE type='table'").all())
            assert all(roots[name] == page for name, page in migrated["roots"])


def test_schema_retains_every_parent_and_unique_generation_and_key(migrated):
    inspector = sa.inspect(migrated["engine"])
    assert {tuple(fk["constrained_columns"]) for fk in inspector.get_foreign_keys("synthetic_evidence_objects")} == {
        (name,) for name in ("evidence_id", "organization_id", "vendor_id", "engagement_id", "assessment_id")}
    assert {tuple(unique["column_names"]) for unique in inspector.get_unique_constraints("synthetic_evidence_objects")} == {
        ("generation",), ("storage_key",)}


@pytest.mark.parametrize("values", [{"payload": b"changed"}, {"sha256": "b" * 64},
    {"organization_id": 2}, {"generation": "b" * 32}, {"issuer": "changed"}, {"evidence_id": 99999}])
def test_custody_update_and_delete_cannot_mutate_original(guarded, values):
    table = SyntheticEvidenceObject.__table__
    before = guarded.execute(sa.select(table)).one()
    for statement in (table.update().values(**values), table.delete()):
        with pytest.raises(DBAPIError), guarded.begin_nested():
            guarded.execute(statement)
    assert guarded.execute(sa.select(table)).one() == before


@pytest.mark.parametrize("table", PARENTS)
@pytest.mark.parametrize("operation", ["delete", "id", "rowid", "oid", "_rowid_"])
def test_referenced_parent_cannot_be_deleted_or_reidentified(guarded, table, operation):
    if operation in ("rowid", "oid", "_rowid_") and guarded.dialect.name != "sqlite":
        pytest.skip("rowid aliases are a SQLite concept")
    model, identifier = PARENTS[table]
    sql = (f"DELETE FROM {table} WHERE id={identifier}" if operation == "delete"
           else f"UPDATE {table} SET {operation}={identifier + 10000} WHERE id={identifier}")
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.exec_driver_sql(sql)
    assert guarded.execute(sa.select(model.id).where(model.id == identifier)).scalar_one() == identifier


@pytest.mark.parametrize("model,field,value", [(Vendor, "organization_id", 2), (Engagement, "vendor_id", 22),
    (Assessment, "vendor_id", 22), (Assessment, "engagement_id", 201), (Evidence, "vendor_id", 22),
    (Evidence, "assessment_id", 2001), (Evidence, "storage_path", "s3://synthetic/alternate"), (Evidence, "file_hash", "b" * 64)])
def test_captured_ownership_key_and_hash_are_frozen(guarded, model, field, value):
    identifier = PARENTS[model.__tablename__][1]
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.execute(sa.update(model).where(model.id == identifier).values(**{field: value}))


def test_descriptive_fields_and_unreferenced_records_keep_ordinary_behavior(guarded):
    for model, identifier, field in ((Organization, 1, "name"), (Vendor, 11, "display_name"),
        (Engagement, 101, "service_name"), (Assessment, 1001, "notes"), (Evidence, 9001, "analyst_notes")):
        guarded.execute(sa.update(model).where(model.id == identifier).values(**{field: "Fresh synthetic description"}))
    guarded.execute(sa.update(Assessment).where(Assessment.id == 2001).values(engagement_id=101))
    guarded.execute(sa.delete(Evidence).where(Evidence.id == 9201))


@pytest.mark.parametrize("table", PARENTS)
def test_sqlite_replace_cannot_destroy_referenced_parent_with_recursive_triggers_off(guarded, table):
    if guarded.dialect.name != "sqlite":
        pytest.skip("REPLACE is a SQLite operation")
    model, identifier = PARENTS[table]
    value = dict(guarded.execute(sa.select(model.__table__).where(model.id == identifier)).mappings().one())
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.execute(model.__table__.insert().prefix_with("OR REPLACE").values(**value))


@pytest.mark.parametrize("operation", ["insert", "update"])
def test_sqlite_organization_unique_key_replace_cannot_erase_custody_parent(guarded, operation):
    if guarded.dialect.name != "sqlite":
        pytest.skip("REPLACE is a SQLite operation")
    sql = ("INSERT OR REPLACE INTO organizations(id,external_key,name) VALUES(3,'synthetic-1','replacement')"
           if operation == "insert" else "UPDATE OR REPLACE organizations SET external_key='synthetic-1' WHERE id=2")
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.exec_driver_sql(sql)
    assert guarded.execute(sa.select(Organization.id).where(Organization.external_key == "synthetic-1")).scalar_one() == 1


@pytest.mark.parametrize("collision", ["evidence_id", "generation", "storage_key"])
def test_sqlite_object_replace_rejects_every_unique_collision(guarded, collision):
    if guarded.dialect.name != "sqlite":
        pytest.skip("REPLACE is a SQLite operation")
    original = object_values()
    altered = object_values(evidence_id=9201, generation="b" * 32, storage_key="vendors/22/evidence/m7_" + "b" * 32 + ".bin")
    altered[collision] = original[collision]
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.execute(SyntheticEvidenceObject.__table__.insert().prefix_with("OR REPLACE"), altered)
    assert guarded.execute(sa.select(SyntheticEvidenceObject.evidence_id)).scalars().all() == [9001]


@pytest.mark.parametrize("change", [{"organization_id": 2}, {"vendor_id": 22}, {"assessment_id": 2001},
    {"engagement_id": 201}, {"storage_key": "/tmp/synthetic"}, {"generation": "z" * 32},
    {"sha256": "z" * 64}, {"byte_length": 0}, {"payload": b"x" * 65537, "byte_length": 65537}])
def test_fresh_object_invalid_chain_keys_hash_and_bounds_deny_with_sqlite_fk_off(migrated, change):
    with migrated["engine"].connect() as connection, connection.begin():
        seed(connection)
        with pytest.raises(DBAPIError), connection.begin_nested():
            connection.execute(SyntheticEvidenceObject.__table__.insert(), object_values(**change))
        connection.rollback()


def test_disabled_or_missing_guards_fail_health_check(guarded):
    dialect = guarded.dialect.name
    sql = ("DROP TRIGGER m7_custody_evidence_update" if dialect == "sqlite"
           else "ALTER TABLE evidence DISABLE TRIGGER m7_custody_evidence_retain")
    with guarded.begin_nested() as savepoint:
        guarded.exec_driver_sql(sql)
        with pytest.raises(PermissionError):
            require_synthetic_custody_guards(guarded, SyntheticEvidenceObject.__table__)
        savepoint.rollback()
    require_synthetic_custody_guards(guarded, SyntheticEvidenceObject.__table__)


def test_postgres_truncate_cascade_cannot_erase_custody(guarded):
    if guarded.dialect.name != "postgresql":
        pytest.skip("TRUNCATE is a PostgreSQL operation")
    for table in ("synthetic_evidence_objects", "evidence", "organizations"):
        with pytest.raises(DBAPIError), guarded.begin_nested():
            guarded.exec_driver_sql("TRUNCATE " + table + " CASCADE")


def test_no_destructive_downgrade_or_legacy_mutation(migrated, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", migrated["url"])
    with pytest.raises(RuntimeError, match="reviewed retention and rollback plan"):
        command.downgrade(config(), PREVIOUS)
    test_additive_upgrade_preserves_all_legacy_rows_and_root_pages(migrated)


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_offline_migration_never_assumes_postgresql_schema(dialect, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:" if dialect == "sqlite" else "postgresql://synthetic.invalid/example")
    output = StringIO()
    cfg = config()
    cfg.output_buffer = output
    if dialect == "postgresql":
        with pytest.raises(RuntimeError, match="requires online schema verification"):
            command.upgrade(cfg, PREVIOUS + ":" + HEAD, sql=True)
        assert "CREATE TABLE synthetic_evidence_objects" not in output.getvalue()
    else:
        command.upgrade(cfg, PREVIOUS + ":" + HEAD, sql=True)
        assert "CREATE TABLE synthetic_evidence_objects" in output.getvalue()
        assert "CREATE TRIGGER m7_custody_no_insert" in output.getvalue()


@pytest.mark.parametrize("first", ["insert", "reparent"])
def test_postgres_raw_insert_and_parent_reassignment_serialize_both_orders(migrated, first):
    if migrated["engine"].dialect.name != "postgresql":
        pytest.skip("requires two real PostgreSQL connections")
    schema = "m7_custody_race_" + uuid4().hex
    root = sa.create_engine(migrated["url"])
    with root.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    engine = root.execution_options(schema_translate_map={None: schema})
    locked, release = Event(), Event()
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            seed(connection)
        insert = SyntheticEvidenceObject.__table__.insert().values(**object_values())
        reparent = sa.update(Assessment).where(Assessment.id == 1001).values(engagement_id=201)

        def hold_first():
            with engine.begin() as connection:
                connection.execute(insert if first == "insert" else reparent)
                locked.set()
                assert release.wait(5), "test did not release the first custody transaction"

        with ThreadPoolExecutor(max_workers=1) as workers:
            held = workers.submit(hold_first)
            try:
                assert locked.wait(5), "first custody transaction did not acquire its locks"
                with engine.connect() as connection:
                    with pytest.raises(DBAPIError) as error, connection.begin():
                        connection.exec_driver_sql("SET LOCAL lock_timeout='150ms'")
                        connection.execute(reparent if first == "insert" else insert)
                    assert (getattr(error.value.orig, "sqlstate", None)
                            or getattr(error.value.orig, "pgcode", None)) == "55P03"
            finally:
                release.set()
            held.result(timeout=5)
        # Once the winning operation commits, the loser cannot exploit the old
        # binding: immutable-parent denial or fresh insert-chain denial follows.
        with engine.connect() as connection:
            with pytest.raises(DBAPIError), connection.begin():
                connection.execute(reparent if first == "insert" else insert)
    finally:
        release.set()
        with root.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        root.dispose()
