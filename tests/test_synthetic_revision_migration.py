"""Additive revision migration and pragma-independent contiguous append guards."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import uuid4
import os

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from src.db import (
    Assessment, Base, Engagement, Evidence, Organization, SyntheticAssessmentRevision,
    SyntheticEvidenceObject, Vendor,
)
from src.synthetic_revision_guards import (
    install_synthetic_revision_guards, require_synthetic_revision_guards,
)
from test_synthetic_custody_migration import object_values, seed


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "0014b_synthetic_custody"
HEAD = "0014c_assessment_revisions"
PRESERVED = (Organization, Vendor, Engagement, Assessment, Evidence, SyntheticEvidenceObject)


def config():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def revision_values(**changes):
    state = b'{"schema_version":1,"synthetic":true}'
    result = dict(assessment_id=1001, revision=1, organization_id=1, vendor_id=11,
        engagement_id=101, anchor_evidence_id=9001, state_payload=state,
        state_sha256=sha256(state).hexdigest(), created_at=datetime(2026, 11, 24, tzinfo=timezone.utc),
        issuer="https://synthetic.invalid", subject="synthetic-reader",
        session_id="sid_synthetic_correlation", effective_role="Analyst", membership_id=501)
    result.update(changes)
    return result


def snapshot(connection):
    return {model.__tablename__: tuple(tuple(row) for row in connection.execute(sa.select(model.__table__)))
            for model in PRESERVED}


@pytest.fixture(scope="module", params=("sqlite", "postgres"))
def migrated(request, tmp_path_factory):
    admin = schema = None
    if request.param == "postgres":
        source = os.getenv("DATABASE_URL", "")
        if os.getenv("GITHUB_ACTIONS") != "true" or not source.startswith("postgresql"):
            pytest.skip("Revision PostgreSQL variants use only the disposable CI service.")
        schema = "m7_revision_migration_" + uuid4().hex
        admin = sa.create_engine(source)
        with admin.begin() as connection:
            connection.execute(sa.schema.CreateSchema(schema))
        url = sa.engine.make_url(source).update_query_dict({"options": "-csearch_path=" + schema}).render_as_string(hide_password=False)
    else:
        url = "sqlite:///" + str(tmp_path_factory.mktemp("revision_migration") / "synthetic%revision.db")
    environment = pytest.MonkeyPatch()
    environment.setenv("DATABASE_URL", url)
    engine = sa.create_engine(url)
    try:
        command.upgrade(config(), PREVIOUS)
        with engine.begin() as connection:
            seed(connection)
            connection.execute(SyntheticEvidenceObject.__table__.insert(), object_values())
            connection.execute(Vendor.__table__.insert(), dict(id=701, legal_name="Synthetic legacy", display_name="Synthetic legacy"))
            connection.execute(Assessment.__table__.insert(), dict(id=703, vendor_id=701, assessment_type="Synthetic legacy"))
            connection.execute(Evidence.__table__.insert(), dict(id=704, vendor_id=701, assessment_id=703,
                document_type="Synthetic legacy", document_name="legacy.txt", storage_path="s3://historical-synthetic/legacy.txt"))
            before = snapshot(connection)
            roots = (tuple(connection.exec_driver_sql("SELECT name, rootpage FROM sqlite_master WHERE type='table' ORDER BY name"))
                     if engine.dialect.name == "sqlite" else None)
        command.upgrade(config(), HEAD)
        yield dict(engine=engine, url=url, before=before, roots=roots)
    finally:
        engine.dispose()
        environment.undo()
        if admin is not None:
            with admin.begin() as connection:
                connection.execute(sa.schema.DropSchema(schema, cascade=True))
            admin.dispose()


@pytest.fixture
def guarded(migrated):
    with migrated["engine"].connect() as connection, connection.begin():
        if connection.dialect.name == "sqlite":
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA recursive_triggers").scalar_one() == 0
        connection.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values())
        try:
            yield connection
        finally:
            connection.rollback()


def test_additive_upgrade_preserves_populated_legacy_and_custody(migrated):
    with migrated["engine"].connect() as connection:
        assert snapshot(connection) == migrated["before"]
        assert connection.execute(sa.select(sa.func.count()).select_from(SyntheticAssessmentRevision)).scalar_one() == 0
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        require_synthetic_revision_guards(connection, SyntheticAssessmentRevision.__table__)
        if migrated["roots"] is not None:
            roots = dict(connection.exec_driver_sql("SELECT name, rootpage FROM sqlite_master WHERE type='table'").all())
            assert all(roots[name] == page for name, page in migrated["roots"])


def test_revision_schema_has_compound_primary_key_and_retained_anchor(migrated):
    inspector = sa.inspect(migrated["engine"])
    assert inspector.get_pk_constraint("synthetic_assessment_revisions")["constrained_columns"] == ["assessment_id", "revision"]
    fks = inspector.get_foreign_keys("synthetic_assessment_revisions")
    assert any(fk["constrained_columns"] == ["anchor_evidence_id"] and fk["referred_table"] == "synthetic_evidence_objects"
               and fk["referred_columns"] == ["evidence_id"] for fk in fks)
    assert not any(fk["constrained_columns"] == ["membership_id"] for fk in fks)
    if migrated["engine"].dialect.name == "sqlite":
        with migrated["engine"].connect() as connection:
            ddl = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='synthetic_assessment_revisions'").scalar_one()
            assert "WITHOUT ROWID" in ddl.upper()
            assert next(row for row in connection.exec_driver_sql("PRAGMA main.table_list")
                        if row[1] == "synthetic_assessment_revisions")[4] == 1


def test_contiguous_append_retains_original_revisions(guarded):
    original = guarded.execute(sa.select(SyntheticAssessmentRevision.__table__)).one()
    for revision in (2, 3):
        guarded.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values(revision=revision))
    assert guarded.execute(sa.select(SyntheticAssessmentRevision.revision).order_by(SyntheticAssessmentRevision.revision)).scalars().all() == [1, 2, 3]
    assert guarded.execute(sa.select(SyntheticAssessmentRevision.__table__).where(SyntheticAssessmentRevision.revision == 1)).one() == original


def test_exact_maximum_state_size_is_retained_without_truncation(guarded):
    state = b"x" * 65536
    guarded.execute(SyntheticAssessmentRevision.__table__.insert(),
                    revision_values(revision=2, state_payload=state, state_sha256=sha256(state).hexdigest()))
    assert guarded.execute(sa.select(SyntheticAssessmentRevision.state_payload)
                           .where(SyntheticAssessmentRevision.revision == 2)).scalar_one() == state


@pytest.mark.parametrize("revision", [0, -1, 1, 3, 100])
def test_gaps_replayed_and_invalid_revision_numbers_deny(guarded, revision):
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values(revision=revision))
    assert guarded.execute(sa.select(SyntheticAssessmentRevision.revision)).scalars().all() == [1]


@pytest.mark.parametrize("values", [{"state_payload": b"changed"}, {"state_sha256": "b" * 64},
    {"anchor_evidence_id": 9201}, {"assessment_id": 2001}, {"revision": 2}, {"issuer": "changed"}])
def test_update_and_delete_never_rewrite_history(guarded, values):
    table = SyntheticAssessmentRevision.__table__
    before = guarded.execute(sa.select(table)).one()
    for statement in (table.update().values(**values), table.delete()):
        with pytest.raises(DBAPIError), guarded.begin_nested():
            guarded.execute(statement)
    assert guarded.execute(sa.select(table)).one() == before


@pytest.mark.parametrize("values", [
    {"anchor_evidence_id": 99999}, {"anchor_evidence_id": 9201}, {"organization_id": 2},
    {"vendor_id": 22}, {"engagement_id": 201}, {"assessment_id": 2001},
    {"state_sha256": "z" * 64}, {"state_sha256": "A" * 64}, {"state_payload": b""},
    {"state_payload": b"x" * 65537}, {"membership_id": 0}, {"effective_role": "Unknown"},
])
def test_orphan_mismatched_anchor_hash_shape_and_payload_bound_deny(guarded, values):
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values(revision=2, **values))
    assert guarded.execute(sa.select(SyntheticAssessmentRevision.revision)).scalars().all() == [1]


def test_an_actual_other_organization_custody_anchor_cannot_be_rebound(guarded):
    other = object_values(evidence_id=9201, organization_id=2, vendor_id=22,
        engagement_id=201, assessment_id=2001, generation="b" * 32,
        storage_key="vendors/22/evidence/m7_" + "b" * 32 + ".bin")
    guarded.execute(sa.update(Evidence).where(Evidence.id == 9201).values(
        storage_path=other["storage_key"], file_hash=other["sha256"]))
    guarded.execute(SyntheticEvidenceObject.__table__.insert(), other)
    for value in (revision_values(revision=2, anchor_evidence_id=9201),
                  revision_values(assessment_id=2001, organization_id=2, vendor_id=22,
                                  engagement_id=201, anchor_evidence_id=9001)):
        with pytest.raises(DBAPIError), guarded.begin_nested():
            guarded.execute(SyntheticAssessmentRevision.__table__.insert(), value)


def test_sqlite_replace_cannot_erase_a_revision_with_recursive_triggers_off(guarded):
    if guarded.dialect.name != "sqlite":
        pytest.skip("REPLACE is a SQLite concept")
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.execute(SyntheticAssessmentRevision.__table__.insert().prefix_with("OR REPLACE"), revision_values(state_payload=b"replacement"))


@pytest.mark.parametrize("alias", ["rowid", "oid", "_rowid_"])
@pytest.mark.parametrize("operation", ["insert_replace", "update", "update_replace"])
def test_sqlite_hidden_rowid_operations_cannot_erase_or_reidentify_history(guarded, alias, operation):
    if guarded.dialect.name != "sqlite":
        pytest.skip("hidden rowids are a SQLite concept")
    assert guarded.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
    assert guarded.exec_driver_sql("PRAGMA recursive_triggers").scalar_one() == 0
    table = SyntheticAssessmentRevision.__table__
    before = guarded.execute(sa.select(table)).all()
    if operation == "insert_replace":
        columns = list(revision_values())
        selection = ",".join("2" if column == "revision" else column for column in columns)
        # Everything except the hidden-rowid selector is a valid next revision.
        # The old prototype silently replaced revision 1 through rowid=1.
        sql = (f"INSERT OR REPLACE INTO synthetic_assessment_revisions ({alias}," + ",".join(columns)
               + ") SELECT 1," + selection + " FROM synthetic_assessment_revisions WHERE revision=1")
    else:
        sql = ("UPDATE " + ("OR REPLACE " if operation == "update_replace" else "")
               + f"synthetic_assessment_revisions SET {alias}=99 WHERE revision=1")
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.exec_driver_sql(sql)
    assert guarded.execute(sa.select(table)).all() == before
    guarded.execute(table.insert(), revision_values(revision=2))
    assert guarded.execute(sa.select(table).where(table.c.revision == 1)).one() == before[0]


def test_revision_health_rejects_rowid_prototype_with_identical_guard_names():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            Base.metadata.create_all(connection)
            table = SyntheticAssessmentRevision.__table__
            connection.exec_driver_sql("DROP TABLE synthetic_assessment_revisions")
            ddl = str(sa.schema.CreateTable(table).compile(dialect=connection.dialect))
            assert "WITHOUT ROWID" in ddl
            connection.exec_driver_sql(ddl.replace("WITHOUT ROWID", ""))
            install_synthetic_revision_guards(table, connection)
            assert {row[0] for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE tbl_name='synthetic_assessment_revisions' AND type='trigger'")} == {
                    "m7_revision_insert", "m7_revision_no_update", "m7_revision_no_delete"}
            assert next(row for row in connection.exec_driver_sql("PRAGMA main.table_list")
                        if row[1] == table.name)[4] == 0
            with pytest.raises(PermissionError):
                require_synthetic_revision_guards(connection, table)
    finally:
        engine.dispose()


def test_revision_health_denies_unavailable_table_list(guarded, monkeypatch):
    if guarded.dialect.name != "sqlite":
        pytest.skip("table_list is a SQLite pragma")
    original = guarded.exec_driver_sql
    observed = []

    def unavailable(statement, *args, **kwargs):
        if statement.startswith("PRAGMA ") and statement.endswith(".table_list"):
            observed.append(statement)
            return SimpleNamespace(all=lambda: [])
        return original(statement, *args, **kwargs)

    monkeypatch.setattr(guarded, "exec_driver_sql", unavailable)
    with pytest.raises(PermissionError):
        require_synthetic_revision_guards(guarded, SyntheticAssessmentRevision.__table__)
    assert observed == ["PRAGMA main.table_list"]


def test_sqlite_revision_shape_check_uses_the_quoted_attached_schema():
    engine = sa.create_engine("sqlite:///:memory:")
    schema = 'synthetic "revision scope"'
    try:
        with engine.begin() as connection:
            quoted = connection.dialect.identifier_preparer.quote(schema)
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS " + quoted)
            mapped = connection.execution_options(schema_translate_map={None: schema})
            Base.metadata.create_all(mapped)
            require_synthetic_revision_guards(mapped, SyntheticAssessmentRevision.__table__)
            assert next(row for row in mapped.exec_driver_sql(f"PRAGMA {quoted}.table_list")
                        if row[1] == "synthetic_assessment_revisions")[4] == 1
    finally:
        engine.dispose()


def test_sqlite_text_is_not_an_acceptable_binary_payload(guarded):
    if guarded.dialect.name != "sqlite":
        pytest.skip("PostgreSQL enforces its bytea column type")
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.exec_driver_sql("""INSERT INTO synthetic_assessment_revisions
            (assessment_id,revision,organization_id,vendor_id,engagement_id,anchor_evidence_id,
             state_payload,state_sha256,created_at,issuer,subject,session_id,effective_role,membership_id)
            SELECT assessment_id,2,organization_id,vendor_id,engagement_id,anchor_evidence_id,
                   'untrusted text',state_sha256,created_at,issuer,subject,session_id,effective_role,membership_id
            FROM synthetic_assessment_revisions WHERE revision=1""")


@pytest.mark.parametrize("target,change", [(Assessment, {"engagement_id": 201}),
    (Vendor, {"organization_id": 2}), (Evidence, {"assessment_id": 2001})])
def test_existing_custody_anchor_guards_retain_revision_parent_identity(guarded, target, change):
    identifier = {Assessment: 1001, Vendor: 11, Evidence: 9001}[target]
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.execute(sa.update(target).where(target.id == identifier).values(**change))


@pytest.mark.parametrize("operation", ["truncate", "truncate_cascade"])
def test_postgresql_truncate_cannot_erase_revisions(guarded, operation):
    if guarded.dialect.name != "postgresql":
        pytest.skip("TRUNCATE is a PostgreSQL concept")
    sql = ("TRUNCATE synthetic_assessment_revisions" if operation == "truncate"
           else "TRUNCATE assessments CASCADE")
    with pytest.raises(DBAPIError), guarded.begin_nested():
        guarded.exec_driver_sql(sql)


def test_missing_or_disabled_guards_fail_health_check(guarded):
    sql = ("DROP TRIGGER m7_revision_insert" if guarded.dialect.name == "sqlite"
           else "ALTER TABLE synthetic_assessment_revisions DISABLE TRIGGER m7_revision_insert")
    with guarded.begin_nested() as savepoint:
        guarded.exec_driver_sql(sql)
        with pytest.raises(PermissionError):
            require_synthetic_revision_guards(guarded, SyntheticAssessmentRevision.__table__)
        savepoint.rollback()
    require_synthetic_revision_guards(guarded, SyntheticAssessmentRevision.__table__)


def test_destructive_downgrade_refuses_before_mutation(migrated, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", migrated["url"])
    with pytest.raises(RuntimeError, match="reviewed retention and rollback plan"):
        command.downgrade(config(), PREVIOUS)
    test_additive_upgrade_preserves_populated_legacy_and_custody(migrated)


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_offline_never_assumes_postgresql_schema(dialect, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:" if dialect == "sqlite" else "postgresql://synthetic.invalid/example")
    cfg = config()
    cfg.output_buffer = StringIO()
    if dialect == "postgresql":
        with pytest.raises(RuntimeError, match="requires online schema verification"):
            command.upgrade(cfg, PREVIOUS + ":" + HEAD, sql=True)
        assert "CREATE TABLE synthetic_assessment_revisions" not in cfg.output_buffer.getvalue()
    else:
        command.upgrade(cfg, PREVIOUS + ":" + HEAD, sql=True)
        assert "CREATE TABLE synthetic_assessment_revisions" in cfg.output_buffer.getvalue()
        assert "CREATE TRIGGER m7_revision_insert" in cfg.output_buffer.getvalue()


@pytest.mark.parametrize("next_number", [1, 2])
def test_postgresql_raw_appends_serialize_before_sequence_check(migrated, next_number):
    if migrated["engine"].dialect.name != "postgresql":
        pytest.skip("requires two PostgreSQL connections")
    # Own a disposable schema because committed immutable rows cannot be cleaned
    # with DELETE. Never use or modify customer/default schemas.
    schema = "m7_revision_race_" + uuid4().hex
    root = sa.create_engine(migrated["url"])
    with root.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    engine = root.execution_options(schema_translate_map={None: schema})
    locked, release = Event(), Event()
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            seed(connection)
            connection.execute(SyntheticEvidenceObject.__table__.insert(), object_values())

        def hold_first():
            with engine.begin() as connection:
                connection.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values())
                locked.set()
                assert release.wait(5), "test did not release the first revision append"

        with ThreadPoolExecutor(max_workers=1) as workers:
            first = workers.submit(hold_first)
            try:
                assert locked.wait(5), "first revision append did not hold the assessment lock"
                with engine.connect() as connection:
                    with pytest.raises(DBAPIError) as error, connection.begin():
                        connection.exec_driver_sql("SET LOCAL lock_timeout='150ms'")
                        connection.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values(revision=next_number))
                    assert (getattr(error.value.orig, "sqlstate", None)
                            or getattr(error.value.orig, "pgcode", None)) == "55P03"
            finally:
                release.set()
            first.result(timeout=5)
        # A replay still denies after the wait; an exact next revision succeeds.
        with engine.connect() as connection:
            if next_number == 1:
                with pytest.raises(DBAPIError), connection.begin():
                    connection.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values())
            else:
                with connection.begin():
                    connection.execute(SyntheticAssessmentRevision.__table__.insert(), revision_values(revision=2))
    finally:
        release.set()
        with root.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        root.dispose()
