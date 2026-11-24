"""Additive, append-only note history migration on isolated synthetic data."""
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.db import AnalystNoteRevision, Base, build_engine


ROOT = Path(__file__).resolve().parents[1]
BEFORE = "0014a_membership_identity_guard"
HEAD = "0015a_note_target_retention"
NOW = datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc)


def configuration():
    result = Config(str(ROOT / "alembic.ini"))
    result.set_main_option("script_location", str(ROOT / "migrations"))
    return result


def snapshot(connection, columns):
    quote = connection.dialect.identifier_preparer.quote
    return {table: tuple(tuple(row) for row in connection.exec_driver_sql(
        "SELECT " + ", ".join(quote(column) for column in names)
        + " FROM " + quote(table) + " ORDER BY id")) for table, names in columns.items()}


@pytest.fixture(scope="module", params=("sqlite", "postgres"))
def migrated(request, tmp_path_factory):
    admin, schema = None, None
    if request.param == "postgres":
        source = os.getenv("DATABASE_URL", "")
        if os.getenv("GITHUB_ACTIONS") != "true" or not source.startswith("postgresql"):
            pytest.skip("Note migration PostgreSQL variants require the synthetic test service.")
        admin = sa.create_engine(source)
        schema = "note_revision_migration_" + uuid4().hex
        with admin.begin() as connection:
            connection.execute(sa.schema.CreateSchema(schema))
        url = sa.engine.make_url(source).update_query_dict({"options": "-csearch_path=" + schema})
        url = url.render_as_string(hide_password=False)
    else:
        url = "sqlite:///" + str(tmp_path_factory.mktemp("note_migration") / "synthetic%notes.db")
    environment = pytest.MonkeyPatch()
    environment.setenv("DATABASE_URL", url)
    engine = sa.create_engine(url)
    if request.param == "sqlite":
        @sa.event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    try:
        command.upgrade(configuration(), BEFORE)
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO vendors (id, legal_name, display_name) VALUES (701, 'Synthetic vendor', 'Synthetic vendor')")
            connection.exec_driver_sql("INSERT INTO engagements (id, vendor_id, service_name) VALUES (702, 701, 'Synthetic service')")
            connection.exec_driver_sql("INSERT INTO assessments (id, vendor_id, assessment_type, notes) VALUES (703, 701, 'Synthetic', 'Original adverse rationale; source section 4, uncertainty unresolved')")
            connection.exec_driver_sql("INSERT INTO evidence (id, vendor_id, assessment_id, document_type, document_name, analyst_notes) VALUES (704, 701, 703, 'Synthetic', 'synthetic.txt', 'Original evidence concern; synthetic citation page 7')")
            connection.execute(sa.text("INSERT INTO audit_logs (id, actor_subject, actor_role, action, object_type, object_id, vendor_id, outcome, details_json, created_at) VALUES (705, 'legacy-subject', 'Analyst', 'synthetic.old.event', 'assessment', '703', 701, 'success', NULL, :created_at)"), {"created_at": NOW.replace(tzinfo=None).isoformat(sep=" ")})
            columns = {table: tuple(column["name"] for column in sa.inspect(connection).get_columns(table))
                       for table in ("vendors", "engagements", "assessments", "evidence", "audit_logs")}
            previous = snapshot(connection, columns)
            root_pages = tuple(connection.exec_driver_sql(
                "SELECT name, rootpage FROM sqlite_master WHERE name IN ('assessments','evidence','audit_logs') ORDER BY name"
            )) if request.param == "sqlite" else None
        command.upgrade(configuration(), HEAD)
        yield {"engine": engine, "url": url, "columns": columns, "previous": previous,
               "root_pages": root_pages, "schema": schema}
    finally:
        engine.dispose()
        environment.undo()
        if admin is not None:
            with admin.begin() as connection:
                connection.execute(sa.schema.DropSchema(schema, cascade=True))
            admin.dispose()


def valid_revision(**changes):
    value = dict(id=1001, organization_id=1, vendor_id=701, engagement_id=702,
                 assessment_id=703, evidence_id=None, object_type="assessment", object_id=703,
                 actor_issuer="https://identity.synthetic.invalid", actor_subject="synthetic-analyst",
                 actor_role="Analyst", membership_id=501, session_id="sid_synthetic_non_bearer",
                 created_at=NOW, content="Synthetic uncertainty; preserve original source reference.", origin="analyst")
    value.update(changes)
    return value


def test_upgrade_preserves_legacy_text_audit_and_original_tables(migrated):
    with migrated["engine"].connect() as connection:
        assert snapshot(connection, migrated["columns"]) == migrated["previous"]
        assert connection.exec_driver_sql("SELECT count(*) FROM analyst_note_revisions").scalar_one() == 0
        assert tuple(connection.exec_driver_sql("SELECT actor_issuer, organization_id, membership_id, session_id FROM audit_logs WHERE id=705").one()) == (None, None, None, None)
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        if migrated["root_pages"] is not None:
            assert tuple(connection.exec_driver_sql(
                "SELECT name, rootpage FROM sqlite_master WHERE name IN ('assessments','evidence','audit_logs') ORDER BY name"
            )) == migrated["root_pages"]


def test_nullable_audit_compatibility_and_revision_indexes_foreign_keys(migrated):
    inspector = sa.inspect(migrated["engine"])
    audit = {column["name"]: column for column in inspector.get_columns("audit_logs")}
    assert all(audit[name]["nullable"] for name in ("actor_issuer", "organization_id", "membership_id", "session_id"))
    assert any(index["column_names"] == ["organization_id", "object_type", "object_id", "id"]
               for index in inspector.get_indexes("analyst_note_revisions"))
    foreign_keys = inspector.get_foreign_keys("analyst_note_revisions")
    assert {(key["constrained_columns"][0], key["referred_table"]) for key in foreign_keys} == {
        ("assessment_id", "assessments"), ("evidence_id", "evidence"),
    }
    assert all(key["options"].get("ondelete") == "RESTRICT" for key in foreign_keys)


@pytest.mark.parametrize("change", [
    {"organization_id": 0}, {"vendor_id": -1}, {"engagement_id": 0},
    {"assessment_id": 9999, "object_id": 9999}, {"object_id": 9999},
    {"object_type": "approval"}, {"object_type": "evidence", "evidence_id": None},
    {"evidence_id": 704}, {"content": ""}, {"content": None},
    {"origin": "invented"}, {"actor_issuer": None}, {"actor_issuer": " "},
    {"actor_subject": ""}, {"actor_role": None}, {"actor_role": "Superuser"},
    {"membership_id": None}, {"membership_id": 0}, {"session_id": None},
    {"session_id": " "}, {"created_at": None},
    {"origin": "legacy_unknown"},
])
def test_revision_scope_target_content_and_attribution_constraints(migrated, change):
    with migrated["engine"].connect() as connection:
        transaction = connection.begin()
        try:
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(AnalystNoteRevision.__table__.insert(), valid_revision(**change))
        finally:
            transaction.rollback()


def test_legacy_baseline_allows_only_honestly_unknown_attribution(migrated):
    baseline = valid_revision(origin="legacy_unknown", actor_issuer=None, actor_subject=None,
                              actor_role=None, membership_id=None, session_id=None)
    with migrated["engine"].connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(AnalystNoteRevision.__table__.insert(), baseline)
            assert connection.exec_driver_sql("SELECT origin, actor_issuer, actor_subject FROM analyst_note_revisions WHERE id=1001").one() == ("legacy_unknown", None, None)
        finally:
            transaction.rollback()


def test_history_reference_blocks_ordinary_evidence_deletion(migrated):
    with migrated["engine"].connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(AnalystNoteRevision.__table__.insert(),
                               valid_revision(object_type="evidence", object_id=704, evidence_id=704))
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.exec_driver_sql("DELETE FROM evidence WHERE id=704")
            assert connection.exec_driver_sql("SELECT count(*) FROM analyst_note_revisions").scalar_one() == 1
            assert connection.exec_driver_sql("SELECT count(*) FROM evidence WHERE id=704").scalar_one() == 1
        finally:
            transaction.rollback()


@pytest.mark.parametrize("mutation", ["UPDATE analyst_note_revisions SET content='erase concern' WHERE id=1001",
                                      "DELETE FROM analyst_note_revisions WHERE id=1001"])
def test_database_rejects_direct_history_mutation(migrated, mutation):
    with migrated["engine"].connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(AnalystNoteRevision.__table__.insert(), valid_revision())
            with pytest.raises(DBAPIError, match="append-only"):
                with connection.begin_nested():
                    connection.exec_driver_sql(mutation)
            assert connection.exec_driver_sql("SELECT content FROM analyst_note_revisions WHERE id=1001").scalar_one() == valid_revision()["content"]
        finally:
            transaction.rollback()


def test_postgresql_rejects_history_truncate(migrated):
    if migrated["engine"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL TRUNCATE has no SQLite equivalent.")
    with migrated["engine"].connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(AnalystNoteRevision.__table__.insert(), valid_revision())
            with pytest.raises(DBAPIError, match="append-only"):
                with connection.begin_nested():
                    connection.exec_driver_sql("TRUNCATE analyst_note_revisions")
            assert connection.exec_driver_sql("SELECT count(*) FROM analyst_note_revisions").scalar_one() == 1
        finally:
            transaction.rollback()


def test_downgrade_refuses_before_erasing_history_or_attribution(migrated, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", migrated["url"])
    with pytest.raises(RuntimeError, match="reviewed data-retention and rollback plan"):
        command.downgrade(configuration(), BEFORE)
    with migrated["engine"].connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        assert snapshot(connection, migrated["columns"]) == migrated["previous"]


def test_metadata_create_all_installs_the_same_sqlite_append_only_guards():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            guards = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").scalars())
        assert {"note_revisions_no_update", "note_revisions_no_delete", "note_revisions_no_replace"} <= guards
        assert {f"note_history_{table}_no_{action}" for table in ("assessments", "evidence")
                for action in ("delete", "insert", "update")} <= guards
    finally:
        engine.dispose()


def test_metadata_guards_respect_postgresql_schema_translation(migrated):
    if migrated["engine"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL schema translation has no SQLite equivalent.")
    root = sa.create_engine(migrated["url"])
    schema = "note_metadata_guards_" + uuid4().hex
    with root.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    try:
        engine = root.execution_options(schema_translate_map={None: schema})
        Base.metadata.create_all(engine)
        with root.connect() as connection:
            installed = connection.execute(sa.text(
                "SELECT t.tgname, fn.nspname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "JOIN pg_proc p ON p.oid=t.tgfoid "
                "JOIN pg_namespace fn ON fn.oid=p.pronamespace "
                "WHERE n.nspname=:schema AND c.relname='analyst_note_revisions' "
                "AND NOT t.tgisinternal ORDER BY t.tgname"
            ), {"schema": schema}).all()
        assert installed == [("note_revisions_no_mutation", schema), ("note_revisions_no_truncate", schema)]
    finally:
        with root.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        root.dispose()


def seed_default_sqlite_targets(connection):
    connection.exec_driver_sql("INSERT INTO vendors (id, legal_name, display_name) VALUES (701, 'Synthetic vendor', 'Synthetic vendor')")
    for assessment_id in (703, 713):
        connection.execute(sa.text(
            "INSERT INTO assessments (id, vendor_id, assessment_type, notes) "
            "VALUES (:id, 701, 'Synthetic', 'Original assessment rationale')"
        ), {"id": assessment_id})
    for evidence_id, assessment_id in ((704, 703), (714, 713)):
        connection.execute(sa.text(
            "INSERT INTO evidence (id, vendor_id, assessment_id, document_type, document_name, analyst_notes) "
            "VALUES (:id, 701, :assessment, 'Synthetic', 'synthetic.txt', 'Original evidence rationale')"
        ), {"id": evidence_id, "assessment": assessment_id})


def sqlite_retention_snapshot(connection):
    columns = {table: tuple(column["name"] for column in sa.inspect(connection).get_columns(table))
               for table in ("assessments", "evidence", "analyst_note_revisions")}
    return snapshot(connection, columns)


@pytest.fixture(scope="module", params=("metadata", "migration"))
def default_sqlite_engine(request, tmp_path_factory):
    """Use the actual builder: do not make a missing guard pass by enabling FKs."""
    url = "sqlite:///" + str(tmp_path_factory.mktemp("default_sqlite_retention") / "synthetic.db")
    engine = build_engine(url)
    try:
        if request.param == "metadata":
            Base.metadata.create_all(engine)
        else:
            with pytest.MonkeyPatch.context() as environment:
                environment.setenv("DATABASE_URL", url)
                command.upgrade(configuration(), HEAD)
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA recursive_triggers").scalar_one() == 0
            seed_default_sqlite_targets(connection)
        yield engine
    finally:
        engine.dispose()


@pytest.mark.parametrize("table,target,revision_kind", [
    ("assessments", 703, "assessment"),
    ("assessments", 703, "evidence"),
    ("evidence", 704, "evidence"),
])
@pytest.mark.parametrize("mutation", [
    "delete", "rekey_id", "rekey_rowid", "rekey_oid", "rekey__rowid_",
    "insert_replace", "update_replace_id", "update_replace_rowid", "update_replace_oid", "update_replace__rowid_",
])
def test_default_sqlite_retains_history_target_against_deletion_rekey_and_replace(
        default_sqlite_engine, table, target, revision_kind, mutation):
    with default_sqlite_engine.connect() as connection:
        transaction = connection.begin()
        try:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA recursive_triggers").scalar_one() == 0
            revision = valid_revision(object_type=revision_kind,
                object_id=704 if revision_kind == "evidence" else 703,
                evidence_id=704 if revision_kind == "evidence" else None)
            connection.execute(AnalystNoteRevision.__table__.insert(), revision)
            previous = sqlite_retention_snapshot(connection)
            if mutation == "delete":
                statement = f"DELETE FROM {table} WHERE id={target}"
            elif mutation.startswith("rekey_"):
                alias = mutation.removeprefix("rekey_")
                statement = f"UPDATE {table} SET {alias}={target + 1000} WHERE id={target}"
            elif mutation == "insert_replace":
                if table == "assessments":
                    statement = f"INSERT OR REPLACE INTO assessments (id, vendor_id, assessment_type, notes) VALUES ({target}, 701, 'Replacement', 'Injected rationale')"
                else:
                    statement = f"INSERT OR REPLACE INTO evidence (id, vendor_id, assessment_id, document_type, document_name, analyst_notes) VALUES ({target}, 701, 703, 'Replacement', 'replacement.txt', 'Injected rationale')"
            else:
                alias = mutation.removeprefix("update_replace_")
                unrelated = 713 if table == "assessments" else 714
                statement = f"UPDATE OR REPLACE {table} SET {alias}={target} WHERE id={unrelated}"
            with pytest.raises(IntegrityError, match="history target is retained"):
                with connection.begin_nested():
                    connection.exec_driver_sql(statement)
            assert sqlite_retention_snapshot(connection) == previous
        finally:
            transaction.rollback()


@pytest.mark.parametrize("table,target", [("assessments", 703), ("evidence", 704)])
def test_default_sqlite_cannot_delete_then_reuse_a_history_target_id(default_sqlite_engine, table, target):
    with default_sqlite_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(AnalystNoteRevision.__table__.insert(),
                               valid_revision(object_type="evidence", object_id=704, evidence_id=704))
            previous = sqlite_retention_snapshot(connection)
            with pytest.raises(IntegrityError, match="history target is retained"):
                with connection.begin_nested():
                    connection.exec_driver_sql(f"DELETE FROM {table} WHERE id={target}")
            if table == "assessments":
                replacement = "INSERT INTO assessments (id, vendor_id, assessment_type) VALUES (703, 701, 'New identity')"
            else:
                replacement = "INSERT INTO evidence (id, vendor_id, document_type, document_name) VALUES (704, 701, 'New identity', 'new.txt')"
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.exec_driver_sql(replacement)
            assert sqlite_retention_snapshot(connection) == previous
        finally:
            transaction.rollback()


@pytest.mark.parametrize("mutation", ["insert_replace", "update_replace"])
def test_default_sqlite_revision_replace_cannot_erase_rationale(default_sqlite_engine, mutation):
    with default_sqlite_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(AnalystNoteRevision.__table__.insert(), valid_revision())
            connection.execute(AnalystNoteRevision.__table__.insert(),
                               valid_revision(id=1002, content="Second immutable uncertainty"))
            previous = sqlite_retention_snapshot(connection)
            with pytest.raises(IntegrityError, match="append-only"):
                with connection.begin_nested():
                    if mutation == "insert_replace":
                        connection.execute(AnalystNoteRevision.__table__.insert().prefix_with("OR REPLACE"),
                                           valid_revision(content="Erase original uncertainty"))
                    else:
                        connection.exec_driver_sql("UPDATE OR REPLACE analyst_note_revisions SET id=1001 WHERE id=1002")
            assert sqlite_retention_snapshot(connection) == previous
        finally:
            transaction.rollback()


def test_default_sqlite_target_guards_allow_unrelated_rows_and_current_note_edits(default_sqlite_engine):
    with default_sqlite_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(AnalystNoteRevision.__table__.insert(),
                               valid_revision(object_type="evidence", object_id=704, evidence_id=704))
            previous_history = tuple(connection.execute(sa.select(AnalystNoteRevision.__table__)))
            connection.exec_driver_sql("UPDATE assessments SET notes='New explicit annotation' WHERE id=703")
            connection.exec_driver_sql("UPDATE evidence SET analyst_notes='New explicit annotation' WHERE id=704")
            connection.exec_driver_sql("UPDATE assessments SET rowid=813 WHERE id=713")
            connection.exec_driver_sql("UPDATE evidence SET id=814 WHERE id=714")
            connection.exec_driver_sql("DELETE FROM evidence WHERE id=814")
            connection.exec_driver_sql("DELETE FROM assessments WHERE id=813")
            connection.exec_driver_sql("INSERT INTO assessments (id, vendor_id, assessment_type) VALUES (713, 701, 'New unrelated record')")
            connection.exec_driver_sql("INSERT INTO evidence (id, vendor_id, document_type, document_name) VALUES (714, 701, 'Synthetic', 'new-unrelated.txt')")
            assert tuple(connection.execute(sa.select(AnalystNoteRevision.__table__))) == previous_history
            assert connection.exec_driver_sql("SELECT notes FROM assessments WHERE id=703").scalar_one() == "New explicit annotation"
            assert connection.exec_driver_sql("SELECT analyst_notes FROM evidence WHERE id=704").scalar_one() == "New explicit annotation"
        finally:
            transaction.rollback()


@pytest.mark.parametrize("table", ["assessments", "evidence"])
def test_default_sqlite_auto_allocated_id_cannot_reassociate_older_orphan_history(default_sqlite_engine, table):
    with default_sqlite_engine.connect() as connection:
        transaction = connection.begin()
        try:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            # Model an orphan left by an older FK-off database before retention
            # guards existed. The next SQLite automatic INTEGER PK is one.
            connection.exec_driver_sql(f"DELETE FROM {table}")
            if table == "assessments":
                revision = valid_revision(assessment_id=1, object_id=1)
                insert = "INSERT INTO assessments (vendor_id, assessment_type) VALUES (701, 'Unrelated new identity')"
            else:
                revision = valid_revision(object_type="evidence", object_id=1, evidence_id=1)
                insert = "INSERT INTO evidence (vendor_id, document_type, document_name) VALUES (701, 'Synthetic', 'unrelated-new-identity.txt')"
            connection.execute(AnalystNoteRevision.__table__.insert(), revision)
            previous = sqlite_retention_snapshot(connection)
            with pytest.raises(IntegrityError, match="history target is retained"):
                with connection.begin_nested():
                    connection.exec_driver_sql(insert)
            assert sqlite_retention_snapshot(connection) == previous
            assert connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one() == 0
        finally:
            transaction.rollback()


def test_additive_retention_upgrade_protects_existing_sqlite_history_with_foreign_keys_off(tmp_path, monkeypatch):
    """Published 0015 installs lacked these guards; an upgrade must add them."""
    url = "sqlite:///" + str(tmp_path / "synthetic-existing-history.db")
    engine = build_engine(url)
    monkeypatch.setenv("DATABASE_URL", url)
    try:
        command.upgrade(configuration(), "0015_analyst_note_revisions")
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            seed_default_sqlite_targets(connection)
            connection.execute(AnalystNoteRevision.__table__.insert(),
                               valid_revision(object_type="evidence", object_id=704, evidence_id=704))
            # Reproduce the already-published 0015 guard set, without changing
            # any source/history row or the append-only UPDATE/DELETE guards.
            for name in ("note_revisions_no_replace", *(f"note_history_{table}_no_{action}"
                         for table in ("assessments", "evidence") for action in ("delete", "insert", "update"))):
                connection.exec_driver_sql("DROP TRIGGER " + connection.dialect.identifier_preparer.quote(name))
            previous = sqlite_retention_snapshot(connection)
            root_pages = tuple(connection.exec_driver_sql(
                "SELECT name, rootpage FROM sqlite_master WHERE name IN "
                "('assessments','evidence','analyst_note_revisions','audit_logs') ORDER BY name"
            ))
        command.upgrade(configuration(), HEAD)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            assert sqlite_retention_snapshot(connection) == previous
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
            assert tuple(connection.exec_driver_sql(
                "SELECT name, rootpage FROM sqlite_master WHERE name IN "
                "('assessments','evidence','analyst_note_revisions','audit_logs') ORDER BY name"
            )) == root_pages
            for table, target in (("assessments", 703), ("evidence", 704)):
                with pytest.raises(IntegrityError, match="history target is retained"):
                    with connection.begin_nested():
                        connection.exec_driver_sql(f"DELETE FROM {table} WHERE id={target}")
            assert sqlite_retention_snapshot(connection) == previous
    finally:
        engine.dispose()


def test_metadata_target_guards_respect_quoted_sqlite_schema_translation(tmp_path):
    engine = build_engine("sqlite:///" + str(tmp_path / "synthetic-main.db"))
    schema = 'synthetic "notes'
    try:
        with engine.begin() as connection:
            quote = connection.dialect.identifier_preparer.quote
            connection.execute(sa.text("ATTACH DATABASE :path AS " + quote(schema)),
                               {"path": str(tmp_path / "synthetic-attached.db")})
            translated = connection.execution_options(schema_translate_map={None: schema})
            Base.metadata.create_all(translated)
            tables = Base.metadata.tables
            translated.execute(tables["vendors"].insert(),
                               dict(id=701, legal_name="Synthetic", display_name="Synthetic"))
            translated.execute(tables["assessments"].insert(),
                               dict(id=703, vendor_id=701, assessment_type="Synthetic"))
            translated.execute(AnalystNoteRevision.__table__.insert(), valid_revision())
            with pytest.raises(IntegrityError, match="history target is retained"):
                with connection.begin_nested():
                    translated.execute(tables["assessments"].delete().where(tables["assessments"].c.id == 703))
            assert translated.execute(sa.select(AnalystNoteRevision.content)).scalar_one() == valid_revision()["content"]
            # The guards belong to the attached schema; no public/main table
            # or trigger is created accidentally by unquoted schema handling.
            assert connection.exec_driver_sql("SELECT count(*) FROM main.sqlite_master WHERE type='trigger'").scalar_one() == 0
            installed = set(connection.exec_driver_sql(
                f"SELECT name FROM {quote(schema)}.sqlite_master WHERE type='trigger'"
            ).scalars())
            assert "note_history_assessments_no_delete" in installed
    finally:
        engine.dispose()
