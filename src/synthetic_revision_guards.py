"""Append-only database guards for bounded synthetic assessment revisions.

The immutable custody anchor retains original parent identities. These guards
add revision ordering and replacement protection, not another ownership system.
Database/schema configuration and privileged database owners remain trusted.
"""
from sqlalchemy import text

from src.synthetic_custody_guards import _schema


MAX_SYNTHETIC_ASSESSMENT_STATE_BYTES = 65536
TABLE_NAME = "synthetic_assessment_revisions"


def synthetic_revision_guard_statements(dialect, schema=None):
    """Fixed DDL with schema-quoted identifiers owned by server configuration."""
    quote = dialect.identifier_preparer.quote
    prefix = quote(schema) + "." if schema else ""
    relation = lambda name: prefix + quote(name)
    revisions = relation(TABLE_NAME)
    anchor = (
        f"SELECT 1 FROM {relation('synthetic_evidence_objects')} c "
        "WHERE c.evidence_id=NEW.anchor_evidence_id AND c.assessment_id=NEW.assessment_id "
        "AND c.organization_id=NEW.organization_id AND c.vendor_id=NEW.vendor_id "
        "AND c.engagement_id=NEW.engagement_id"
    )
    next_revision = (f"SELECT COALESCE(MAX(revision),0)+1 FROM {revisions} "
                     "WHERE assessment_id=NEW.assessment_id")
    if dialect.name == "sqlite":
        statements = [
            f"CREATE TRIGGER {relation('m7_revision_no_' + action)} BEFORE {action.upper()} ON {revisions} "
            "BEGIN SELECT RAISE(ABORT, 'Synthetic assessment revisions are immutable'); END"
            for action in ("update", "delete")
        ]
        statements.append(
            f"CREATE TRIGGER {relation('m7_revision_insert')} BEFORE INSERT ON {revisions} BEGIN "
            f"SELECT CASE WHEN EXISTS (SELECT 1 FROM {revisions} WHERE assessment_id=NEW.assessment_id "
            "AND revision=NEW.revision) THEN RAISE(ABORT, 'Synthetic revision cannot be replaced') END; "
            "SELECT CASE WHEN typeof(NEW.state_payload)<>'blob' OR length(NEW.state_sha256)<>64 "
            "OR NEW.state_sha256 GLOB '*[^0-9a-f]*' "
            f"OR NEW.revision<>({next_revision}) OR NOT EXISTS ({anchor}) "
            "THEN RAISE(ABORT, 'Invalid synthetic assessment revision') END; END"
        )
        return tuple(statements)
    if dialect.name != "postgresql":
        raise RuntimeError("Synthetic assessment revisions require SQLite or PostgreSQL.")
    immutable = relation("m7_revision_reject_mutation")
    insert = relation("m7_revision_validate_insert")
    statements = [
        f"CREATE OR REPLACE FUNCTION {immutable}() RETURNS trigger LANGUAGE plpgsql "
        "SET search_path=pg_catalog AS $$ BEGIN RAISE EXCEPTION 'Synthetic assessment revisions are immutable'; END; $$",
        f"CREATE OR REPLACE FUNCTION {insert}() RETURNS trigger LANGUAGE plpgsql VOLATILE "
        "SET search_path=pg_catalog AS $$ BEGIN "
        # Match the service's assessment lock before reading max(revision). A
        # waiting raw INSERT must sample a fresh sequence after its competitor.
        f"PERFORM id FROM {relation('assessments')} WHERE id=NEW.assessment_id FOR UPDATE; "
        "IF NOT FOUND THEN RAISE EXCEPTION 'Invalid synthetic assessment'; END IF; "
        "IF NEW.state_sha256 !~ '^[0-9a-f]{64}$' "
        f"OR NEW.revision<>({next_revision}) OR NOT EXISTS ({anchor}) "
        "THEN RAISE EXCEPTION 'Invalid synthetic assessment revision'; END IF; RETURN NEW; END; $$",
    ]
    for name, operation, function in (
        ("m7_revision_insert", "INSERT", insert),
        ("m7_revision_no_mutation", "UPDATE OR DELETE", immutable),
        ("m7_revision_no_truncate", "TRUNCATE", immutable),
    ):
        statements.extend((
            f"CREATE TRIGGER {quote(name)} BEFORE {operation} ON {revisions} "
            f"FOR EACH {'STATEMENT' if operation == 'TRUNCATE' else 'ROW'} EXECUTE FUNCTION {function}()",
            f"ALTER TABLE {revisions} ENABLE ALWAYS TRIGGER {quote(name)}",
        ))
    return tuple(statements)


def install_synthetic_revision_guards(table, connection, **_):
    for statement in synthetic_revision_guard_statements(connection.dialect, _schema(table, connection)):
        connection.exec_driver_sql(statement)


def require_synthetic_revision_guards(connection, table):
    """Reject missing or disabled guards; privileged DDL remains trusted."""
    dialect = connection.dialect.name
    schema = _schema(table, connection)
    if dialect == "sqlite":
        quote = connection.dialect.identifier_preparer.quote
        prefix = quote(schema) + "." if schema else ""
        # Trigger names alone also match the older rowid-table prototype. Its
        # hidden rowid allowed REPLACE to erase a different composite-PK row
        # with recursive triggers off. table_list is available from SQLite 3.37;
        # unsupported/empty results deny rather than assume a protected shape.
        tables = connection.exec_driver_sql(
            f"PRAGMA {quote(schema or 'main')}.table_list"
        ).all()
        retained = [row for row in tables if len(row) >= 5
                    and row[0] == (schema or "main") and row[1] == TABLE_NAME
                    and row[2] == "table" and row[4] == 1]
        if len(retained) != 1:
            raise PermissionError("Synthetic assessment revision guards are unavailable.")
        rows = connection.exec_driver_sql(
            f"SELECT name FROM {prefix}sqlite_master WHERE type='trigger' "
            "AND tbl_name='synthetic_assessment_revisions'"
        ).scalars().all()
        if not {"m7_revision_insert", "m7_revision_no_update", "m7_revision_no_delete"} <= set(rows):
            raise PermissionError("Synthetic assessment revision guards are unavailable.")
        return
    if dialect != "postgresql":
        raise PermissionError("Synthetic assessment revision guards are unavailable.")
    rows = connection.execute(text("""
        SELECT t.tgname, t.tgtype
        FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
        JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
        WHERE n.nspname=:schema AND pn.nspname=:schema
          AND c.relname='synthetic_assessment_revisions' AND t.tgenabled='A'
          AND NOT t.tgisinternal AND t.tgqual IS NULL
    """), {"schema": schema}).all()
    if not {("m7_revision_insert", 7), ("m7_revision_no_mutation", 27),
            ("m7_revision_no_truncate", 34)} <= {tuple(row) for row in rows}:
        raise PermissionError("Synthetic assessment revision guards are unavailable.")
