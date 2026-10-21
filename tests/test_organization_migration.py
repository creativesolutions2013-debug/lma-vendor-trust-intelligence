"""Additive authorization migration over isolated, populated synthetic databases."""
from datetime import datetime, timedelta, timezone
from importlib import import_module
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from src.db import (
    Assessment, EngagementAccessGrant, Organization, OrganizationMembership, Vendor,
)


ROOT = Path(__file__).resolve().parents[1]
LEGACY = "0013_revalidation_case_records"
HEAD = "0014_organization_engagement_authorization"
LEGACY_TABLES = ("vendors", "engagements", "assessments", "evidence", "findings", "monitoring_events")
NOW = datetime(2026, 10, 21, 22, 30, tzinfo=timezone.utc)


def config():
    result = Config(str(ROOT / "alembic.ini"))
    result.set_main_option("script_location", str(ROOT / "migrations"))
    return result


def rows(connection, table, columns):
    # Names come from this fixed fixture/SQLAlchemy introspection, never input.
    quote = connection.dialect.identifier_preparer.quote
    statement = "SELECT " + ", ".join(quote(x) for x in columns) + " FROM " + quote(table) + " ORDER BY id"
    return tuple(tuple(row) for row in connection.exec_driver_sql(statement))


@pytest.fixture(scope="module", params=("sqlite", "postgres"))
def migrated(request, tmp_path_factory):
    admin = None
    schema = None
    if request.param == "postgres":
        source = os.getenv("DATABASE_URL", "")
        if os.getenv("GITHUB_ACTIONS") != "true" or not source.startswith("postgresql"):
            pytest.skip("PostgreSQL migration regression uses an isolated schema only in PostgreSQL CI.")
        schema = "m4c_migration_" + uuid4().hex
        admin = sa.create_engine(source)
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        url = sa.engine.make_url(source).update_query_dict({"options": "-csearch_path=" + schema})
        url_string = url.render_as_string(hide_password=False)
    else:
        # Exercise ConfigParser URL escaping locally as well as PostgreSQL's
        # percent-encoded isolated-schema connection options in CI.
        file = tmp_path_factory.mktemp("m4c_migration") / "synthetic%isolated.db"
        url_string = "sqlite:///" + str(file)
    environment = pytest.MonkeyPatch()
    environment.setenv("DATABASE_URL", url_string)
    engine = sa.create_engine(url_string)
    if request.param == "sqlite":
        @sa.event.listens_for(engine, "connect")
        def foreign_keys(dbapi, _):
            dbapi.execute("PRAGMA foreign_keys=ON")
    try:
        command.upgrade(config(), LEGACY)
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO vendors (id, legal_name, display_name) VALUES (701, 'Synthetic Legacy Vendor', 'Synthetic Legacy Vendor')")
            connection.exec_driver_sql("INSERT INTO engagements (id, vendor_id, service_name) VALUES (702, 701, 'Synthetic legacy service')")
            connection.exec_driver_sql("INSERT INTO assessments (id, vendor_id, assessment_type, notes) VALUES (703, 701, 'Synthetic legacy assessment', 'Preserve this unassigned record')")
            connection.exec_driver_sql("INSERT INTO evidence (id, vendor_id, assessment_id, document_type, document_name, storage_path) VALUES (704, 701, 703, 'Synthetic report', 'synthetic-legacy.txt', 'vendors/701/evidence/synthetic-legacy.txt')")
            connection.exec_driver_sql("INSERT INTO findings (id, vendor_id, evidence_id, title) VALUES (705, 701, 704, 'Synthetic legacy finding')")
            connection.exec_driver_sql("INSERT INTO monitoring_events (id, vendor_id, event_type) VALUES (706, 701, 'Synthetic legacy event')")
            columns = {table: tuple(c["name"] for c in sa.inspect(connection).get_columns(table)) for table in LEGACY_TABLES}
            before = {table: rows(connection, table, names) for table, names in columns.items()}
            root_pages = (tuple(connection.exec_driver_sql(
                "SELECT name, rootpage FROM sqlite_master WHERE name IN ('vendors','assessments') ORDER BY name"
            )) if request.param == "sqlite" else None)
        command.upgrade(config(), HEAD)
        yield {"engine": engine, "url": url_string, "columns": columns, "before": before, "root_pages": root_pages}
    finally:
        engine.dispose()
        environment.undo()
        if admin is not None:
            with admin.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            admin.dispose()


def test_additive_upgrade_preserves_legacy_rows_without_linkage_or_grants(migrated):
    with migrated["engine"].connect() as connection:
        assert {table: rows(connection, table, names) for table, names in migrated["columns"].items()} == migrated["before"]
        assert connection.exec_driver_sql("SELECT organization_id FROM vendors WHERE id=701").scalar_one() is None
        assert connection.exec_driver_sql("SELECT engagement_id FROM assessments WHERE id=703").scalar_one() is None
        for table in ("organizations", "organization_memberships", "engagement_access_grants"):
            assert connection.exec_driver_sql("SELECT count(*) FROM " + table).scalar_one() == 0
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        if migrated["root_pages"] is not None:
            after = tuple(connection.exec_driver_sql(
                "SELECT name, rootpage FROM sqlite_master WHERE name IN ('vendors','assessments') ORDER BY name"
            ))
            assert after == migrated["root_pages"]  # Native additive columns, no old-table reconstruction.


def test_new_foreign_keys_indexes_and_legacy_nullability_match_contract(migrated):
    inspector = sa.inspect(migrated["engine"])
    for table, column, parent in (("vendors", "organization_id", "organizations"),
                                  ("assessments", "engagement_id", "engagements")):
        assert next(c for c in inspector.get_columns(table) if c["name"] == column)["nullable"] is True
        assert any(f["constrained_columns"] == [column] and f["referred_table"] == parent
                   for f in inspector.get_foreign_keys(table))
        assert any(i["column_names"] == [column] for i in inspector.get_indexes(table))
    for table, identity in (("organization_memberships", {"organization_id", "issuer", "subject"}),
                            ("engagement_access_grants", {"membership_id", "engagement_id"})):
        assert any(set(c["column_names"]) == identity for c in inspector.get_unique_constraints(table))
        assert {"valid_from", "expires_at", "status"} <= {c["name"] for c in inspector.get_columns(table) if not c["nullable"]}
    assert "engagement_id" not in {c["name"] for c in inspector.get_columns("evidence")}
    assert "organization_id" not in {c["name"] for c in inspector.get_columns("evidence")}


@pytest.fixture
def constrained(migrated):
    with migrated["engine"].connect() as connection:
        transaction = connection.begin()
        connection.execute(Organization.__table__.insert(), {"id": 1, "external_key": "synthetic-org", "name": "Synthetic Organization"})
        membership = {"id": 1, "organization_id": 1, "issuer": "https://identity.synthetic.invalid", "subject": "synthetic-subject",
                      "role": "Analyst", "status": "active", "valid_from": NOW - timedelta(days=1), "expires_at": NOW + timedelta(days=1)}
        connection.execute(OrganizationMembership.__table__.insert(), membership)
        grant = {"id": 1, "membership_id": 1, "engagement_id": 702, "status": "active",
                 "valid_from": NOW - timedelta(hours=1), "expires_at": NOW + timedelta(hours=1)}
        connection.execute(EngagementAccessGrant.__table__.insert(), grant)
        try:
            yield connection, membership, grant
        finally:
            transaction.rollback()


@pytest.mark.parametrize("change", [{"organization_id": 999}, {"issuer": " "}, {"subject": ""}, {"role": "Superuser"},
                                    {"status": "unknown"}, {"valid_from": None}, {"expires_at": None},
                                    {"expires_at": NOW - timedelta(days=2)}, {}])
def test_membership_foreign_key_identity_role_status_window_and_uniqueness(constrained, change):
    connection, membership, _ = constrained
    invalid = dict(membership, id=2, **change)
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(OrganizationMembership.__table__.insert(), invalid)


@pytest.mark.parametrize("change", [{"membership_id": 999}, {"engagement_id": 999}, {"status": "unknown"},
                                    {"valid_from": None}, {"expires_at": None},
                                    {"expires_at": NOW - timedelta(days=2)}, {}])
def test_entitlement_foreign_keys_status_window_and_uniqueness(constrained, change):
    connection, _, grant = constrained
    invalid = dict(grant, id=2, **change)
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(EngagementAccessGrant.__table__.insert(), invalid)


@pytest.mark.parametrize("table,values", [
    (Organization.__table__, {"id": 2, "external_key": "synthetic-org", "name": "Duplicate identity"}),
    (Organization.__table__, {"id": 2, "external_key": " ", "name": "Blank identity"}),
    (Vendor.__table__, {"id": 999, "organization_id": 999, "legal_name": "Synthetic", "display_name": "Synthetic"}),
    (Assessment.__table__, {"id": 999, "vendor_id": 701, "engagement_id": 999, "assessment_type": "Synthetic"}),
])
def test_organization_and_parent_link_integrity(constrained, table, values):
    connection, _, _ = constrained
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(table.insert(), values)


def test_no_automatic_destructive_authorization_downgrade(migrated, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", migrated["url"])
    with pytest.raises(RuntimeError, match="reviewed data-retention and rollback plan"):
        command.downgrade(config(), LEGACY)
    with migrated["engine"].connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == HEAD
        assert {table: rows(connection, table, names) for table, names in migrated["columns"].items()} == migrated["before"]
    assert "organizations" in sa.inspect(migrated["engine"]).get_table_names()
