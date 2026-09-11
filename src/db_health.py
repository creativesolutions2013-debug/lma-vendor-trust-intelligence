from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError


REQUIRED_TABLES = {
    "vendors",
    "engagements",
    "assessments",
    "evidence",
    "findings",
    "monitoring_events",
    "alembic_version",
}


def check_database_health(engine):
    """
    Validate database connectivity and expected schema.

    Returns a structured result that is safe for UI display.
    Connection strings and credentials are intentionally excluded.
    """
    result = {
        "healthy": False,
        "database": engine.dialect.name,
        "connectivity": False,
        "schema_ready": False,
        "missing_tables": [],
        "message": "",
    }

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        result["connectivity"] = True

        inspector = inspect(engine)
        actual_tables = set(inspector.get_table_names())
        missing = sorted(REQUIRED_TABLES - actual_tables)

        result["missing_tables"] = missing
        result["schema_ready"] = not missing
        result["healthy"] = result["connectivity"] and result["schema_ready"]

        if missing:
            result["message"] = (
                "Database connection succeeded, but the schema is incomplete. "
                "Run 'alembic upgrade head' before starting the application."
            )
        else:
            result["message"] = "Database connection and schema are healthy."

        return result

    except SQLAlchemyError as exc:
        result["message"] = (
            "Unable to connect to the configured database. "
            f"Database error: {exc.__class__.__name__}."
        )
        return result
