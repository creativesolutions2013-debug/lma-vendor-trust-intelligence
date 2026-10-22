"""Database predicate guard for the unambiguous issuer/subject membership rule.

PostgreSQL readers share an identity-specific transaction lock; an ALWAYS row
trigger takes the exclusive counterpart for raw SQL membership mutations. This
covers absent/new membership rows as well as existing rows. Hash collisions can
only add contention, never authorize another identity. SQLite's enclosing BEGIN
IMMEDIATE provides writer serialization and needs no trigger. No live wiring.
"""
from sqlalchemy import text


TRIGGER_NAME = "membership_identity_predicate_guard"
FUNCTION_NAME = "guard_membership_identity_predicate"


def _schema(table, connection):
    mapping = connection.get_execution_options().get("schema_translate_map") or {}
    schema = mapping.get(table.schema, table.schema)
    if connection.dialect.name == "postgresql" and schema is None:
        schema = connection.exec_driver_sql("SELECT pg_catalog.current_schema()").scalar_one()
    return schema


def membership_identity_guard_statements(dialect, schema=None, table_name="organization_memberships"):
    """Fixed DDL with quoted server-owned identifiers, no request-controlled SQL."""
    if dialect.name == "sqlite":
        return ()
    if dialect.name != "postgresql":
        raise RuntimeError("Membership identity serialization requires SQLite or PostgreSQL.")
    quote = dialect.identifier_preparer.quote
    prefix = quote(schema) + "." if schema else ""
    table = prefix + quote(table_name)
    function = prefix + quote(FUNCTION_NAME)
    trigger = quote(TRIGGER_NAME)
    return (
        f"""CREATE OR REPLACE FUNCTION {function}() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE old_key bigint; new_key bigint; identity_key bigint;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        old_key := pg_catalog.hashtextextended(pg_catalog.jsonb_build_array(
            TG_RELID::bigint, OLD.issuer::text, OLD.subject::text)::text, 0);
    END IF;
    IF TG_OP <> 'DELETE' THEN
        new_key := pg_catalog.hashtextextended(pg_catalog.jsonb_build_array(
            TG_RELID::bigint, NEW.issuer::text, NEW.subject::text)::text, 0);
    END IF;
    FOR identity_key IN
        SELECT DISTINCT candidate FROM pg_catalog.unnest(ARRAY[old_key, new_key]) AS keys(candidate)
        WHERE candidate IS NOT NULL ORDER BY candidate
    LOOP
        PERFORM pg_catalog.pg_advisory_xact_lock(identity_key);
    END LOOP;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$""",
        f"DROP TRIGGER IF EXISTS {trigger} ON {table}",
        f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION {function}()",
        f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER {trigger}",
    )


def install_membership_identity_guard(table, connection, **_):
    for statement in membership_identity_guard_statements(connection.dialect, _schema(table, connection), table.name):
        connection.exec_driver_sql(statement)


def acquire_membership_identity_guard(connection, table, issuer, subject):
    """Acquire only inside the read service's dedicated transaction.

    The DB trigger is mandatory: an advisory reader lock without coordinated SQL
    writers does not protect the membership predicate. Privileged owners can
    still disable/replace guards and are outside this prototype's threat model.
    READ COMMITTED is mandatory so the first authority query gets a fresh
    snapshot after any wait for a writer's exclusive identity lock.
    """
    if connection.dialect.name == "sqlite":
        return
    if (connection.dialect.name != "postgresql" or not connection.in_transaction()
            or getattr(connection.connection.driver_connection, "autocommit", None) is not False
            or connection.get_isolation_level() != "READ COMMITTED"
            or type(issuer) is not str or not 0 < len(issuer) <= 500
            or type(subject) is not str or not 0 < len(subject) <= 255):
        raise PermissionError("Scoped access denied.")
    schema = _schema(table, connection)
    quote = connection.dialect.identifier_preparer.quote
    relation = quote(schema) + "." + quote(table.name)
    matches = connection.execute(text("""
        SELECT t.tgrelid::bigint
        FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE t.tgrelid = pg_catalog.to_regclass(:relation)
          AND t.tgname = :trigger_name AND t.tgenabled = 'A'
          AND t.tgtype = 31 AND t.tgqual IS NULL AND NOT t.tgisinternal
          AND p.proname = :function_name AND n.nspname = :schema
    """), {"relation": relation, "trigger_name": TRIGGER_NAME,
           "function_name": FUNCTION_NAME, "schema": schema}).all()
    if len(matches) != 1:
        raise PermissionError("Scoped access denied.")
    connection.execute(text("""
        SELECT pg_catalog.pg_advisory_xact_lock_shared(pg_catalog.hashtextextended(
            pg_catalog.jsonb_build_array(CAST(:table_oid AS bigint), CAST(:issuer AS text),
                                        CAST(:subject AS text))::text, 0))
    """), {"table_oid": matches[0][0], "issuer": issuer, "subject": subject})
