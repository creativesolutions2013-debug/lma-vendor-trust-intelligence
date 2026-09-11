from sqlalchemy import create_engine

from src.db import Base
from src.db_health import check_database_health


def test_health_check_reports_ready_schema():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(bind=engine)

    # Alembic owns this table in the application database, so create
    # a minimal equivalent for this isolated health-check test.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version "
            "(version_num VARCHAR(32) NOT NULL)"
        )

    result = check_database_health(engine)

    assert result["healthy"] is True
    assert result["connectivity"] is True
    assert result["schema_ready"] is True
    assert result["missing_tables"] == []


def test_health_check_detects_missing_schema():
    engine = create_engine("sqlite:///:memory:")

    result = check_database_health(engine)

    assert result["healthy"] is False
    assert result["connectivity"] is True
    assert result["schema_ready"] is False
    assert "vendors" in result["missing_tables"]
    assert "alembic_version" in result["missing_tables"]
    assert "alembic upgrade head" in result["message"]


def test_health_check_does_not_expose_database_url():
    engine = create_engine("sqlite:///:memory:")

    result = check_database_health(engine)

    serialized = str(result)

    assert "sqlite:///:memory:" not in serialized
