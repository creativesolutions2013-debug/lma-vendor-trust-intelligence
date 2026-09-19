from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base, Vendor, Engagement, Finding, MonitoringEvent
from src.seed import seed_demo_data


def test_seed_demo_data_round_trip():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()

    try:
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
        session.close()