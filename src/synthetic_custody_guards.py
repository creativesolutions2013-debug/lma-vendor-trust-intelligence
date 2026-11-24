"""Fixed database guards for the isolated, synthetic SQL byte-custody proof.

The database/schema and DDL are trusted server configuration. Guard presence is
checked at use; this is not cryptographic verification against a database owner.
"""
from sqlalchemy import text


MAX_SYNTHETIC_EVIDENCE_BYTES = 65536
TABLE_NAME = "synthetic_evidence_objects"
_PARENTS = {
    "organizations": ("organization_id", ("id",)),
    "vendors": ("vendor_id", ("id", "organization_id")),
    "engagements": ("engagement_id", ("id", "vendor_id")),
    "assessments": ("assessment_id", ("id", "vendor_id", "engagement_id")),
    "evidence": ("evidence_id", ("id", "vendor_id", "assessment_id", "storage_path", "file_hash")),
}


def _schema(table, connection):
    mapping = connection.get_execution_options().get("schema_translate_map") or {}
    schema = mapping.get(table.schema, table.schema)
    if schema is None and connection.dialect.name == "postgresql":
        schema = connection.exec_driver_sql("SELECT pg_catalog.current_schema()").scalar_one()
    return schema


def _expected(dialect):
    if dialect == "sqlite":
        result = [(TABLE_NAME, "m7_custody_no_" + action, None)
                  for action in ("insert", "update", "delete")]
        result.extend((parent, "m7_custody_" + parent + "_" + action, None)
                      for parent in _PARENTS for action in ("insert", "update", "delete"))
        return result
    if dialect == "postgresql":
        return [(TABLE_NAME, "m7_custody_insert", 7),
                (TABLE_NAME, "m7_custody_no_mutation", 27),
                (TABLE_NAME, "m7_custody_no_truncate", 34),
                *((parent, "m7_custody_" + parent + "_retain", 27) for parent in _PARENTS)]
    raise RuntimeError("Synthetic custody requires SQLite or PostgreSQL.")


def synthetic_custody_guard_statements(dialect, schema=None):
    """Return fixed, schema-quoted DDL; no request-controlled SQL identifiers."""
    quote = dialect.identifier_preparer.quote
    prefix = quote(schema) + "." if schema else ""
    relation = lambda name: prefix + quote(name)
    custody = relation(TABLE_NAME)
    chain = (
        f"SELECT 1 FROM {relation('evidence')} d "
        f"JOIN {relation('assessments')} a ON a.id=d.assessment_id AND a.vendor_id=d.vendor_id "
        f"JOIN {relation('engagements')} e ON e.id=a.engagement_id AND e.vendor_id=a.vendor_id "
        f"JOIN {relation('vendors')} v ON v.id=e.vendor_id "
        f"JOIN {relation('organizations')} o ON o.id=v.organization_id "
        "WHERE d.id=NEW.evidence_id AND a.id=NEW.assessment_id "
        "AND e.id=NEW.engagement_id AND v.id=NEW.vendor_id AND o.id=NEW.organization_id "
        "AND d.storage_path=NEW.storage_key AND d.file_hash=NEW.sha256 "
        "AND d.document_name=NEW.document_name"
    )
    key = "'vendors/' || CAST(NEW.vendor_id AS TEXT) || '/evidence/m7_' || NEW.generation || '.bin'"
    if dialect.name == "sqlite":
        statements = [
            f"CREATE TRIGGER {relation('m7_custody_no_' + action)} BEFORE {action.upper()} ON {custody} "
            "BEGIN SELECT RAISE(ABORT, 'Synthetic custody is immutable'); END"
            for action in ("update", "delete")
        ]
        statements.append(
            f"CREATE TRIGGER {relation('m7_custody_no_insert')} BEFORE INSERT ON {custody} BEGIN "
            f"SELECT CASE WHEN EXISTS (SELECT 1 FROM {custody} WHERE evidence_id=NEW.evidence_id "
            "OR generation=NEW.generation OR storage_key=NEW.storage_key) "
            "THEN RAISE(ABORT, 'Synthetic custody cannot be replaced') END; "
            "SELECT CASE WHEN length(NEW.generation)<>32 OR NEW.generation GLOB '*[^0-9a-f]*' "
            "OR length(NEW.sha256)<>64 OR NEW.sha256 GLOB '*[^0-9a-f]*' "
            f"OR NEW.storage_key<>({key}) OR typeof(NEW.payload)<>'blob' "
            f"OR NOT EXISTS ({chain}) THEN RAISE(ABORT, 'Invalid synthetic custody linkage') END; END"
        )
        for parent, (reference, columns) in _PARENTS.items():
            old = f"EXISTS (SELECT 1 FROM {custody} WHERE {quote(reference)}=OLD.id)"
            new = f"EXISTS (SELECT 1 FROM {custody} WHERE {quote(reference)}=NEW.id)"
            changed = " OR ".join(f"OLD.{quote(column)} IS NOT NEW.{quote(column)}" for column in columns)
            insert = new
            conflict = "0"
            if parent == "organizations":
                # REPLACE can delete via external_key rather than the PK. UPDATE
                # OR REPLACE from an unrelated row must not delete a retained org.
                clash = (f"EXISTS (SELECT 1 FROM {relation(parent)} p JOIN {custody} c "
                         "ON c.organization_id=p.id WHERE p.external_key=NEW.external_key")
                insert += " OR " + clash + ")"
                conflict = clash + " AND p.id<>OLD.id)"
            for action, condition in (
                ("insert", insert), ("delete", old),
                ("update", f"(({changed}) AND ({old} OR {new})) OR ({conflict})"),
            ):
                statements.append(
                    f"CREATE TRIGGER {relation('m7_custody_' + parent + '_' + action)} "
                    f"BEFORE {action.upper()} ON {relation(parent)} WHEN {condition} "
                    "BEGIN SELECT RAISE(ABORT, 'Synthetic custody parent is retained'); END"
                )
        return tuple(statements)
    if dialect.name != "postgresql":
        raise RuntimeError("Synthetic custody requires SQLite or PostgreSQL.")
    immutable = relation("m7_custody_reject_mutation")
    insert_function = relation("m7_custody_validate_insert")
    # Lock raw SQL insertions in the existing authorization boundary's parent
    # order. FOR SHARE also excludes non-key ownership updates. Volatile PL/pgSQL
    # queries see fresh committed rows after a competing row-lock wait.
    locks = "\n".join(
        f"PERFORM id FROM {relation(parent)} WHERE id=NEW.{reference} FOR SHARE; "
        "IF NOT FOUND THEN RAISE EXCEPTION 'Invalid synthetic custody parent'; END IF;"
        for parent, reference in (("organizations", "organization_id"),
                                  ("engagements", "engagement_id"), ("vendors", "vendor_id"),
                                  ("assessments", "assessment_id"), ("evidence", "evidence_id"))
    )
    statements = [
        f"CREATE OR REPLACE FUNCTION {immutable}() RETURNS trigger LANGUAGE plpgsql "
        "SET search_path=pg_catalog AS $$ BEGIN RAISE EXCEPTION 'Synthetic custody is immutable'; END; $$",
        f"CREATE OR REPLACE FUNCTION {insert_function}() RETURNS trigger LANGUAGE plpgsql VOLATILE "
        f"SET search_path=pg_catalog AS $$ BEGIN {locks} "
        "IF NEW.generation !~ '^[0-9a-f]{32}$' OR NEW.sha256 !~ '^[0-9a-f]{64}$' "
        f"OR NEW.storage_key<>({key}) OR NOT EXISTS ({chain}) "
        "THEN RAISE EXCEPTION 'Invalid synthetic custody linkage'; END IF; RETURN NEW; END; $$",
    ]
    for name, operations, function in (
        ("m7_custody_insert", "INSERT", insert_function),
        ("m7_custody_no_mutation", "UPDATE OR DELETE", immutable),
        ("m7_custody_no_truncate", "TRUNCATE", immutable),
    ):
        statements.extend((
            f"CREATE TRIGGER {quote(name)} BEFORE {operations} ON {custody} "
            f"FOR EACH {'STATEMENT' if operations == 'TRUNCATE' else 'ROW'} EXECUTE FUNCTION {function}()",
            f"ALTER TABLE {custody} ENABLE ALWAYS TRIGGER {quote(name)}",
        ))
    for parent, (reference, columns) in _PARENTS.items():
        function = relation("m7_custody_retain_" + parent)
        changed = " OR ".join(f"OLD.{quote(column)} IS DISTINCT FROM NEW.{quote(column)}" for column in columns)
        exists = f"EXISTS (SELECT 1 FROM {custody} WHERE {quote(reference)}=OLD.id"
        statements.extend((
            f"CREATE OR REPLACE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql VOLATILE "
            f"SET search_path=pg_catalog AS $$ BEGIN IF TG_OP='DELETE' THEN IF {exists}) "
            "THEN RAISE EXCEPTION 'Synthetic custody parent is retained'; END IF; RETURN OLD; "
            f"ELSE IF ({changed}) AND {exists} OR {quote(reference)}=NEW.id) "
            "THEN RAISE EXCEPTION 'Synthetic custody parent is retained'; END IF; RETURN NEW; END IF; END; $$",
            f"CREATE TRIGGER {quote('m7_custody_' + parent + '_retain')} BEFORE UPDATE OR DELETE "
            f"ON {relation(parent)} FOR EACH ROW EXECUTE FUNCTION {function}()",
            f"ALTER TABLE {relation(parent)} ENABLE ALWAYS TRIGGER {quote('m7_custody_' + parent + '_retain')}",
        ))
    return tuple(statements)


def install_synthetic_custody_guards(table, connection, **_):
    for statement in synthetic_custody_guard_statements(connection.dialect, _schema(table, connection)):
        connection.exec_driver_sql(statement)


def require_synthetic_custody_guards(connection, table):
    """Deny an incomplete/disabled schema before any custody byte operation."""
    dialect = connection.dialect.name
    schema = _schema(table, connection)
    expected = set(_expected(dialect))
    if dialect == "sqlite":
        quote = connection.dialect.identifier_preparer.quote
        prefix = quote(schema) + "." if schema else ""
        rows = connection.exec_driver_sql(
            f"SELECT tbl_name, name FROM {prefix}sqlite_master WHERE type='trigger'"
        ).all()
        actual = {(parent, name, None) for parent, name in rows}
    else:
        rows = connection.execute(text("""
            SELECT c.relname, t.tgname, t.tgtype
            FROM pg_catalog.pg_trigger t
            JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
            JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
            WHERE n.nspname=:schema AND pn.nspname=:schema AND t.tgenabled='A'
              AND NOT t.tgisinternal AND t.tgqual IS NULL
        """), {"schema": schema}).all()
        actual = {tuple(row) for row in rows}
    if not expected <= actual:
        raise PermissionError("Synthetic custody guards are unavailable.")
