import os

import pytest

from src.db import (
    Assessment,
    Engagement,
    Evidence,
    Finding,
    MonitoringEvent,
    SessionLocal,
    Vendor,
)
from src.seed import seed_demo_data


DATABASE_URL = os.getenv("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="PostgreSQL smoke test runs only when DATABASE_URL is PostgreSQL.",
)


def test_postgres_seed_and_query_round_trip():
    session = SessionLocal()

    try:
        # Keep the shared CI PostgreSQL database deterministic.
        session.query(Finding).delete()
        session.query(MonitoringEvent).delete()
        session.query(Evidence).delete()
        session.query(Assessment).delete()
        session.query(Engagement).delete()
        session.query(Vendor).delete()
        session.commit()

        seed_demo_data(session)

        vendors = session.query(Vendor).all()
        engagements = session.query(Engagement).all()
        findings = session.query(Finding).all()
        events = session.query(MonitoringEvent).all()

        assert len(vendors) == 3
        assert len(engagements) == 2
        assert len(findings) == 1
        assert len(events) == 1

        northstar = (
            session.query(Vendor)
            .filter_by(display_name="Northstar Cloud")
            .first()
        )

        assert northstar is not None
        assert northstar.residual_risk_score is not None
        assert northstar.overall_risk_rating is not None

    finally:
        session.query(Finding).delete()
        session.query(MonitoringEvent).delete()
        session.query(Evidence).delete()
        session.query(Assessment).delete()
        session.query(Engagement).delete()
        session.query(Vendor).delete()
        session.commit()
        session.close()
