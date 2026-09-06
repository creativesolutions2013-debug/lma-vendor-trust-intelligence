import streamlit as st
import pandas as pd
import plotly.express as px

from src.db import init_db, get_session, Vendor, Engagement, Finding, MonitoringEvent
from src.seed import seed_demo_data
from src.scoring import (
    InherentRiskInput,
    calculate_inherent_risk,
    calculate_residual_risk,
    tier_from_score,
    rating_from_score,
)

st.set_page_config(
    page_title="LMA Vendor Trust Intelligence",
    page_icon="🛡️",
    layout="wide"
)

init_db()
session = get_session()
seed_demo_data(session)

def metric_card(label, value):
    st.metric(label, value)

def render_control_tower():
    st.title("🛡️ Vendor Security Control Tower")
    st.caption("Which vendors need attention right now, why, and what should we do next?")

    vendors = session.query(Vendor).all()
    findings = session.query(Finding).all()
    events = session.query(MonitoringEvent).all()

    critical = sum(1 for v in vendors if v.criticality == "Critical")
    high_residual = sum(1 for v in vendors if v.residual_risk_score >= 50)
    open_findings = sum(1 for f in findings if f.status != "Closed")
    open_events = sum(1 for e in events if e.status != "Closed" and e.requires_review)

    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Vendors", len(vendors))
    with c2: metric_card("Critical Vendors", critical)
    with c3: metric_card("High/Critical Residual Risk", high_residual)
    with c4: metric_card("Attention Items", open_findings + open_events)

    st.subheader("Vendor Attention Queue")
    rows = []
    for v in vendors:
        vendor_events = [e for e in events if e.vendor_id == v.id and e.status != "Closed"]
        vendor_findings = [f for f in findings if f.vendor_id == v.id and f.status != "Closed"]
        reason = ""
        if vendor_events:
            reason = vendor_events[0].event_type
        elif vendor_findings:
            reason = vendor_findings[0].title
        elif v.residual_risk_score >= 50:
            reason = "Elevated residual risk"
        if reason:
            rows.append({
                "Vendor": v.display_name,
                "Residual Risk": v.residual_risk_score,
                "Rating": v.overall_risk_rating,
                "Reason": reason,
                "Priority": "P1" if v.residual_risk_score >= 75 else "P2",
            })
    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values("Residual Risk", ascending=False), use_container_width=True)
    else:
        st.success("No vendors currently require attention.")

    st.subheader("Risk Portfolio")
    chart_df = pd.DataFrame([{
        "Vendor": v.display_name,
        "Inherent Risk": v.inherent_risk_score,
        "Residual Risk": v.residual_risk_score,
        "External Risk": v.external_risk_score,
    } for v in vendors])
    if not chart_df.empty:
        fig = px.scatter(
            chart_df,
            x="Inherent Risk",
            y="Residual Risk",
            size="External Risk",
            hover_name="Vendor",
            range_x=[0,100],
            range_y=[0,100],
        )
        st.plotly_chart(fig, use_container_width=True)

def render_vendors():
    st.title("🏢 Vendor Inventory")
    vendors = session.query(Vendor).all()

    df = pd.DataFrame([{
        "ID": v.id,
        "Vendor": v.display_name,
        "Industry": v.industry,
        "Criticality": v.criticality,
        "Inherent Risk": v.inherent_risk_score,
        "Residual Risk": v.residual_risk_score,
        "External Risk": v.external_risk_score,
        "Rating": v.overall_risk_rating,
        "Status": v.relationship_status,
    } for v in vendors])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Vendor 360")
    if vendors:
        selected = st.selectbox("Select vendor", vendors, format_func=lambda v: v.display_name)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Inherent Risk", selected.inherent_risk_score)
        c2.metric("Residual Risk", selected.residual_risk_score)
        c3.metric("External Risk", selected.external_risk_score)
        c4.metric("Security Rating", selected.security_rating)

        tabs = st.tabs(["Overview", "Engagements", "Findings", "Monitoring"])
        with tabs[0]:
            st.write({
                "Legal name": selected.legal_name,
                "Primary domain": selected.primary_domain,
                "Industry": selected.industry,
                "Country": selected.headquarters_country,
                "Criticality": selected.criticality,
                "Overall risk": selected.overall_risk_rating,
            })
        with tabs[1]:
            engagements = session.query(Engagement).filter_by(vendor_id=selected.id).all()
            if engagements:
                st.dataframe(pd.DataFrame([{
                    "Service": e.service_name,
                    "Owner": e.business_owner,
                    "Criticality": e.business_criticality,
                    "Data": e.data_classification,
                    "Production Access": e.production_access,
                    "AI Enabled": e.ai_enabled,
                } for e in engagements]), use_container_width=True, hide_index=True)
            else:
                st.info("No engagements yet.")
        with tabs[2]:
            rows = session.query(Finding).filter_by(vendor_id=selected.id).all()
            if rows:
                st.dataframe(pd.DataFrame([{
                    "Finding": f.title,
                    "Severity": f.severity,
                    "Status": f.status,
                    "Source": f.source,
                    "Owner": f.owner,
                    "Target": f.target_date,
                } for f in rows]), use_container_width=True, hide_index=True)
            else:
                st.success("No findings.")
        with tabs[3]:
            rows = session.query(MonitoringEvent).filter_by(vendor_id=selected.id).all()
            if rows:
                st.dataframe(pd.DataFrame([{
                    "Event": e.event_type,
                    "Severity": e.severity,
                    "Status": e.status,
                    "Previous": e.previous_value,
                    "New": e.new_value,
                } for e in rows]), use_container_width=True, hide_index=True)
            else:
                st.info("No monitoring events.")

def render_intake():
    st.title("📝 New Vendor Intake")
    st.caption("Create the vendor + engagement and automatically calculate inherent risk.")

    with st.form("vendor_intake"):
        col1, col2 = st.columns(2)
        with col1:
            vendor_name = st.text_input("Vendor name *")
            service_name = st.text_input("Service / engagement name *")
            website = st.text_input("Website")
            industry = st.text_input("Industry")
            business_owner = st.text_input("Business owner")
            department = st.text_input("Department")
        with col2:
            country = st.text_input("Headquarters country", value="United States")
            criticality_label = st.selectbox("Business criticality", ["Low", "Moderate", "High", "Critical"])
            data_label = st.selectbox(
                "Highest data sensitivity",
                ["Public", "Internal", "Confidential", "PII", "Sensitive PII", "PHI / PCI / Credentials"]
            )
            production_access = st.checkbox("Production access")
            privileged_access = st.checkbox("Privileged access")
            network_access = st.checkbox("Network access")
            ai_enabled = st.checkbox("AI-enabled service")

        st.markdown("#### Risk factors")
        data_map = {
            "Public": 0, "Internal": 5, "Confidential": 10,
            "PII": 15, "Sensitive PII": 20, "PHI / PCI / Credentials": 25
        }
        crit_map = {"Low": 5, "Moderate": 10, "High": 15, "Critical": 20}
        access_score = 20 if privileged_access else 16 if production_access else 12 if network_access else 0
        data_volume = st.slider("Data volume risk", 0, 10, 5)
        regulatory = st.slider("Regulatory exposure", 0, 10, 5)
        fourth_party = st.slider("Fourth-party dependency", 0, 5, 2)
        geographic = st.slider("Geographic risk", 0, 5, 1)
        ai_autonomy = st.slider("AI / autonomy risk", 0, 5, 3 if ai_enabled else 0)

        submitted = st.form_submit_button("Create vendor and calculate risk", type="primary")

    if submitted:
        if not vendor_name or not service_name:
            st.error("Vendor name and service name are required.")
            return

        inherent = calculate_inherent_risk(InherentRiskInput(
            data_sensitivity=data_map[data_label],
            system_access=access_score,
            business_criticality=crit_map[criticality_label],
            data_volume=data_volume,
            regulatory_exposure=regulatory,
            fourth_party_dependency=fourth_party,
            geographic_risk=geographic,
            ai_autonomy=ai_autonomy,
        ))
        residual = calculate_residual_risk(inherent, 50, 25)

        vendor = Vendor(
            legal_name=vendor_name,
            display_name=vendor_name,
            website=website,
            industry=industry,
            headquarters_country=country,
            relationship_status="Prospective",
            criticality=criticality_label,
            inherent_risk_score=inherent,
            external_risk_score=25,
            control_effectiveness=50,
            residual_risk_score=residual,
            overall_risk_rating=rating_from_score(residual),
        )
        session.add(vendor)
        session.commit()

        engagement = Engagement(
            vendor_id=vendor.id,
            service_name=service_name,
            business_owner=business_owner,
            department=department,
            business_criticality=criticality_label,
            data_classification=data_label,
            production_access=production_access,
            privileged_access=privileged_access,
            network_access=network_access,
            ai_enabled=ai_enabled,
        )
        session.add(engagement)
        session.commit()

        st.success(f"{vendor_name} created.")
        st.metric("Inherent Risk", inherent)
        st.write(f"**Tier:** {tier_from_score(inherent)}")
        st.write(f"**Initial residual risk:** {residual} — {rating_from_score(residual)}")

def render_findings():
    st.title("⚠️ Findings & Remediation")
    vendors = session.query(Vendor).all()
    findings = session.query(Finding).all()

    if findings:
        st.dataframe(pd.DataFrame([{
            "ID": f.id,
            "Vendor": next((v.display_name for v in vendors if v.id == f.vendor_id), f.vendor_id),
            "Finding": f.title,
            "Severity": f.severity,
            "Status": f.status,
            "Owner": f.owner,
            "Target": f.target_date,
        } for f in findings]), use_container_width=True, hide_index=True)

    st.subheader("Create finding")
    with st.form("create_finding"):
        vendor = st.selectbox("Vendor", vendors, format_func=lambda v: v.display_name)
        title = st.text_input("Finding title")
        description = st.text_area("Description")
        source = st.selectbox("Source", ["Questionnaire", "Evidence Review", "External Telemetry", "Incident", "Analyst"])
        severity = st.selectbox("Severity", ["Low", "Moderate", "High", "Critical"])
        owner = st.text_input("Owner")
        target_date = st.text_input("Target date (YYYY-MM-DD)")
        if st.form_submit_button("Create finding"):
            if not title:
                st.error("Finding title is required.")
            else:
                session.add(Finding(
                    vendor_id=vendor.id,
                    title=title,
                    description=description,
                    source=source,
                    severity=severity,
                    owner=owner,
                    target_date=target_date,
                ))
                session.commit()
                st.success("Finding created.")

def render_monitoring():
    st.title("📡 Continuous Monitoring")
    vendors = session.query(Vendor).all()
    events = session.query(MonitoringEvent).order_by(MonitoringEvent.event_date.desc()).all()

    if events:
        st.dataframe(pd.DataFrame([{
            "Vendor": next((v.display_name for v in vendors if v.id == e.vendor_id), e.vendor_id),
            "Event": e.event_type,
            "Severity": e.severity,
            "Status": e.status,
            "Previous": e.previous_value,
            "New": e.new_value,
            "Review Required": e.requires_review,
        } for e in events]), use_container_width=True, hide_index=True)

    st.subheader("Record monitoring event")
    with st.form("monitor_event"):
        vendor = st.selectbox("Vendor", vendors, format_func=lambda v: v.display_name)
        event_type = st.selectbox(
            "Event type",
            [
                "Security rating deterioration",
                "Critical KEV exposure",
                "Credential exposure",
                "Ransomware event",
                "Breach disclosure",
                "Expired assurance evidence",
                "Material vendor change",
            ]
        )
        severity = st.selectbox("Severity", ["Low", "Moderate", "High", "Critical"])
        description = st.text_area("Description")
        previous_value = st.text_input("Previous value")
        new_value = st.text_input("New value")
        if st.form_submit_button("Record event"):
            session.add(MonitoringEvent(
                vendor_id=vendor.id,
                event_type=event_type,
                severity=severity,
                description=description,
                previous_value=previous_value,
                new_value=new_value,
                requires_review=True,
            ))
            # MVP dynamic risk effect
            severity_bump = {"Low": 2, "Moderate": 5, "High": 10, "Critical": 25}[severity]
            vendor.external_risk_score = min(100, vendor.external_risk_score + severity_bump)
            vendor.residual_risk_score = calculate_residual_risk(
                vendor.inherent_risk_score,
                vendor.control_effectiveness,
                vendor.external_risk_score
            )
            vendor.overall_risk_rating = rating_from_score(vendor.residual_risk_score)
            session.commit()
            st.success("Monitoring event recorded and vendor risk recalculated.")

def render_reports():
    st.title("📊 Reports")
    vendors = session.query(Vendor).all()
    df = pd.DataFrame([{
        "Vendor": v.display_name,
        "Criticality": v.criticality,
        "Inherent": v.inherent_risk_score,
        "External": v.external_risk_score,
        "Control Effectiveness": v.control_effectiveness,
        "Residual": v.residual_risk_score,
        "Rating": v.overall_risk_rating,
    } for v in vendors])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button(
        "Download vendor risk register CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="vendor_risk_register.csv",
        mime="text/csv"
    )

st.sidebar.title("LMA Vendor Trust Intelligence")
page = st.sidebar.radio(
    "Navigation",
    [
        "Control Tower",
        "Vendors",
        "New Vendor Intake",
        "Findings",
        "Monitoring",
        "Reports",
    ]
)

if page == "Control Tower":
    render_control_tower()
elif page == "Vendors":
    render_vendors()
elif page == "New Vendor Intake":
    render_intake()
elif page == "Findings":
    render_findings()
elif page == "Monitoring":
    render_monitoring()
elif page == "Reports":
    render_reports()
