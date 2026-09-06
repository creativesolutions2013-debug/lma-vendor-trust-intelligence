from src.db import Vendor, Engagement, Finding, MonitoringEvent
from src.scoring import calculate_residual_risk, rating_from_score

def seed_demo_data(session):
    if session.query(Vendor).count() > 0:
        return

    vendors = [
        Vendor(
            legal_name="Northstar Cloud Systems, Inc.",
            display_name="Northstar Cloud",
            website="https://example.com",
            primary_domain="example.com",
            industry="SaaS",
            headquarters_country="United States",
            relationship_status="Active",
            criticality="Critical",
            inherent_risk_score=82,
            external_risk_score=48,
            control_effectiveness=68,
            security_rating=705,
        ),
        Vendor(
            legal_name="BluePeak Analytics LLC",
            display_name="BluePeak Analytics",
            website="https://example.org",
            primary_domain="example.org",
            industry="Analytics",
            headquarters_country="United States",
            relationship_status="Active",
            criticality="High",
            inherent_risk_score=64,
            external_risk_score=22,
            control_effectiveness=82,
            security_rating=792,
        ),
        Vendor(
            legal_name="Cedar Office Supply Co.",
            display_name="Cedar Office Supply",
            website="https://example.net",
            primary_domain="example.net",
            industry="Business Services",
            headquarters_country="United States",
            relationship_status="Active",
            criticality="Low",
            inherent_risk_score=18,
            external_risk_score=12,
            control_effectiveness=75,
            security_rating=815,
        ),
    ]

    for v in vendors:
        v.residual_risk_score = calculate_residual_risk(
            v.inherent_risk_score, v.control_effectiveness, v.external_risk_score
        )
        v.overall_risk_rating = rating_from_score(v.residual_risk_score)
        session.add(v)
    session.commit()

    northstar = session.query(Vendor).filter_by(display_name="Northstar Cloud").first()
    bluepeak = session.query(Vendor).filter_by(display_name="BluePeak Analytics").first()

    session.add_all([
        Engagement(
            vendor_id=northstar.id,
            service_name="Production Data Processing",
            service_description="Processes customer and operational data in a hosted SaaS environment.",
            business_owner="Operations",
            department="Technology",
            business_criticality="Critical",
            data_classification="PII / Confidential",
            production_access=True,
            network_access=True,
            privileged_access=False,
            ai_enabled=True,
        ),
        Engagement(
            vendor_id=bluepeak.id,
            service_name="Business Analytics",
            service_description="Provides analytics dashboards using internal business data.",
            business_owner="Business Intelligence",
            department="Finance",
            business_criticality="High",
            data_classification="Confidential",
            production_access=False,
            network_access=False,
            privileged_access=False,
            ai_enabled=False,
        ),
        Finding(
            vendor_id=northstar.id,
            title="Vulnerability remediation control weakness",
            description="Evidence indicates critical vulnerability remediation is not consistently meeting the stated SLA.",
            source="Evidence Review",
            severity="High",
            status="In Remediation",
            owner="Security Analyst",
            target_date="2026-10-15",
        ),
        MonitoringEvent(
            vendor_id=northstar.id,
            event_type="Security rating deterioration",
            severity="High",
            description="External security rating declined materially and requires analyst review.",
            previous_value="782",
            new_value="705",
            requires_review=True,
        ),
    ])
    session.commit()
