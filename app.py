import os
from datetime import datetime, date

import streamlit as st
import pandas as pd
import plotly.express as px

from src.db import (
    init_db, get_session, Vendor, Engagement, Assessment,
    Evidence, Finding, MonitoringEvent
)
from src.seed import seed_demo_data
from src.evidence_ai import extract_soc2_metadata
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

EVIDENCE_DIR = "uploaded_evidence"
os.makedirs(EVIDENCE_DIR, exist_ok=True)

ASSESSMENT_TYPES = [
    "Full Security Assessment",
    "Enhanced Security Assessment",
    "Targeted Security Review",
    "AI Security Assessment",
    "PCI Review",
    "Incident-Triggered Reassessment",
    "Material Change Reassessment",
]

EVIDENCE_TYPES = [
    "SOC 2 Type II",
    "SOC 2 Type I",
    "ISO 27001 Certificate",
    "ISO 27001 Statement of Applicability",
    "PCI AOC",
    "Penetration Test",
    "SIG Questionnaire",
    "CAIQ",
    "BCP / DR Test",
    "Incident Response Plan",
    "Security Policy",
    "Architecture Diagram",
    "Other",
]

def metric_card(label, value):
    st.metric(label, value)

def evidence_status(expiration_date):
    if not expiration_date:
        return "Received"
    try:
        exp = datetime.strptime(expiration_date, "%Y-%m-%d").date()
        days = (exp - date.today()).days
        if days < 0:
            return "Expired"
        if days <= 60:
            return "Expiring Soon"
        return "Valid"
    except ValueError:
        return "Received"

def recommended_assessment(vendor):
    if vendor.inherent_risk_score >= 75:
        return "Full Security Assessment"
    if vendor.inherent_risk_score >= 50:
        return "Enhanced Security Assessment"
    if vendor.inherent_risk_score >= 25:
        return "Targeted Security Review"
    return "Basic Security Screening"


def get_openai_api_key():
    try:
        return st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        return os.getenv("OPENAI_API_KEY", "")

def render_control_tower():
    st.title("🛡️ Vendor Security Control Tower")
    st.caption("Which vendors need attention right now, why, and what should we do next?")

    vendors = session.query(Vendor).all()
    findings = session.query(Finding).all()
    events = session.query(MonitoringEvent).all()
    evidence = session.query(Evidence).all()
    assessments = session.query(Assessment).all()

    critical = sum(1 for v in vendors if v.criticality == "Critical")
    high_residual = sum(1 for v in vendors if v.residual_risk_score >= 50)
    open_findings = sum(1 for f in findings if f.status != "Closed")
    open_events = sum(1 for e in events if e.status != "Closed" and e.requires_review)
    evidence_attention = sum(1 for e in evidence if evidence_status(e.expiration_date) in ["Expired", "Expiring Soon"])
    open_assessments = sum(1 for a in assessments if a.status not in ["Completed", "Closed"])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: metric_card("Vendors", len(vendors))
    with c2: metric_card("Critical Vendors", critical)
    with c3: metric_card("High/Critical Residual Risk", high_residual)
    with c4: metric_card("Open Assessments", open_assessments)
    with c5: metric_card("Attention Items", open_findings + open_events + evidence_attention)

    st.subheader("Vendor Attention Queue")
    rows = []
    for v in vendors:
        vendor_events = [e for e in events if e.vendor_id == v.id and e.status != "Closed"]
        vendor_findings = [f for f in findings if f.vendor_id == v.id and f.status != "Closed"]
        vendor_evidence = [e for e in evidence if e.vendor_id == v.id]
        stale = [e for e in vendor_evidence if evidence_status(e.expiration_date) in ["Expired", "Expiring Soon"]]
        reason = ""
        if vendor_events:
            reason = vendor_events[0].event_type
        elif vendor_findings:
            reason = vendor_findings[0].title
        elif stale:
            reason = f"{stale[0].document_type}: {evidence_status(stale[0].expiration_date)}"
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

        tabs = st.tabs(["Overview", "Engagements", "Assessments", "Evidence", "Findings", "Monitoring"])
        with tabs[0]:
            st.write({
                "Legal name": selected.legal_name,
                "Primary domain": selected.primary_domain,
                "Industry": selected.industry,
                "Country": selected.headquarters_country,
                "Criticality": selected.criticality,
                "Overall risk": selected.overall_risk_rating,
                "Recommended assessment": recommended_assessment(selected),
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
            rows = session.query(Assessment).filter_by(vendor_id=selected.id).all()
            if rows:
                st.dataframe(pd.DataFrame([{
                    "Assessment": a.assessment_type,
                    "Reason": a.assessment_reason,
                    "Status": a.status,
                    "Assigned To": a.assigned_to,
                    "Due": a.due_date,
                    "Approval": a.approval_status,
                } for a in rows]), use_container_width=True, hide_index=True)
            else:
                st.info("No assessments yet.")
        with tabs[3]:
            rows = session.query(Evidence).filter_by(vendor_id=selected.id).all()
            if rows:
                st.dataframe(pd.DataFrame([{
                    "Type": e.document_type,
                    "Document": e.document_name,
                    "Issuer": e.issuer,
                    "Expiration": e.expiration_date,
                    "Status": evidence_status(e.expiration_date),
                    "Exceptions": e.exceptions_count,
                } for e in rows]), use_container_width=True, hide_index=True)
            else:
                st.info("No evidence yet.")
        with tabs[4]:
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
        with tabs[5]:
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
        st.write(f"**Recommended assessment:** {recommended_assessment(vendor)}")
        st.write(f"**Initial residual risk:** {residual} — {rating_from_score(residual)}")

def render_assessments():
    st.title("🧭 Assessments")
    st.caption("Launch, assign, and track risk-based vendor security assessments.")
    vendors = session.query(Vendor).order_by(Vendor.display_name).all()
    assessments = session.query(Assessment).order_by(Assessment.created_at.desc()).all()

    if assessments:
        st.dataframe(pd.DataFrame([{
            "ID": a.id,
            "Vendor": a.vendor.display_name if a.vendor else a.vendor_id,
            "Assessment": a.assessment_type,
            "Reason": a.assessment_reason,
            "Status": a.status,
            "Assigned To": a.assigned_to,
            "Due": a.due_date,
            "Approval": a.approval_status,
        } for a in assessments]), use_container_width=True, hide_index=True)
    else:
        st.info("No assessments created yet.")

    st.subheader("Create assessment")
    if not vendors:
        st.warning("Create a vendor first.")
        return

    with st.form("create_assessment"):
        vendor = st.selectbox("Vendor", vendors, format_func=lambda v: v.display_name)
        st.caption(f"Recommended based on inherent risk: {recommended_assessment(vendor)}")
        assessment_type = st.selectbox("Assessment type", ASSESSMENT_TYPES)
        reason = st.selectbox("Assessment reason", [
            "New vendor", "Annual review", "Contract renewal", "Material change",
            "Security incident", "Security rating deterioration", "AI capability introduced"
        ])
        assigned_to = st.text_input("Assigned analyst")
        due_date = st.date_input("Due date")
        notes = st.text_area("Scope / notes")
        if st.form_submit_button("Launch assessment", type="primary"):
            assessment = Assessment(
                vendor_id=vendor.id,
                assessment_type=assessment_type,
                assessment_reason=reason,
                status="In Progress",
                assigned_to=assigned_to,
                due_date=str(due_date),
                started_at=datetime.utcnow(),
                notes=notes,
            )
            session.add(assessment)
            session.commit()
            st.success(f"{assessment_type} launched for {vendor.display_name}.")

    st.subheader("Update assessment")
    active = session.query(Assessment).order_by(Assessment.created_at.desc()).all()
    if active:
        with st.form("update_assessment"):
            chosen = st.selectbox(
                "Assessment",
                active,
                format_func=lambda a: f"#{a.id} — {a.vendor.display_name} — {a.assessment_type}"
            )
            status = st.selectbox("Status", ["Not Started", "In Progress", "Vendor Responding", "Analyst Review", "Completed", "Closed"],
                                  index=["Not Started", "In Progress", "Vendor Responding", "Analyst Review", "Completed", "Closed"].index(chosen.status)
                                  if chosen.status in ["Not Started", "In Progress", "Vendor Responding", "Analyst Review", "Completed", "Closed"] else 1)
            approval = st.selectbox("Approval status", ["Pending", "Approved", "Approved with Conditions", "Rejected"])
            risk_score = st.slider("Assessment risk score", 0, 100, int(chosen.risk_score or 0))
            if st.form_submit_button("Save assessment update"):
                chosen.status = status
                chosen.approval_status = approval
                chosen.risk_score = risk_score
                if status in ["Completed", "Closed"]:
                    chosen.completed_at = datetime.utcnow()
                session.commit()
                st.success("Assessment updated.")

def render_evidence():
    st.title("📁 Evidence Center")
    st.caption("Track assurance artifacts, validity, coverage, and key report metadata.")
    vendors = session.query(Vendor).order_by(Vendor.display_name).all()
    evidence_rows = session.query(Evidence).order_by(Evidence.created_at.desc()).all()

    if evidence_rows:
        df = pd.DataFrame([{
            "ID": e.id,
            "Vendor": e.vendor.display_name if e.vendor else e.vendor_id,
            "Type": e.document_type,
            "Document": e.document_name,
            "Issuer": e.issuer,
            "Coverage End": e.coverage_end,
            "Expiration": e.expiration_date,
            "Status": evidence_status(e.expiration_date),
            "Exceptions": e.exceptions_count,
        } for e in evidence_rows])
        st.dataframe(df, use_container_width=True, hide_index=True)

        attention = df[df["Status"].isin(["Expired", "Expiring Soon"])]
        if not attention.empty:
            st.warning(f"{len(attention)} evidence item(s) require attention.")
            st.dataframe(attention, use_container_width=True, hide_index=True)
    else:
        st.info("No evidence has been registered yet.")

    st.subheader("Register evidence")
    if not vendors:
        st.warning("Create a vendor first.")
        return

    vendor = st.selectbox("Vendor", vendors, format_func=lambda v: v.display_name, key="evidence_vendor")
    vendor_assessments = session.query(Assessment).filter_by(vendor_id=vendor.id).all()
    assessment_choices = [None] + vendor_assessments
    assessment = st.selectbox(
        "Linked assessment (optional)",
        assessment_choices,
        format_func=lambda a: "None" if a is None else f"#{a.id} — {a.assessment_type}",
        key="evidence_assessment"
    )
    document_type = st.selectbox("Document type", EVIDENCE_TYPES, key="evidence_type")
    uploaded = st.file_uploader("Upload evidence file", type=["pdf", "docx", "xlsx", "csv", "txt"], key="evidence_upload")

    if uploaded and document_type in ["SOC 2 Type II", "SOC 2 Type I"]:
        st.markdown("#### AI Evidence Analyst")
        api_key = get_openai_api_key()
        if api_key:
            st.success("OpenAI extraction is configured.")
        else:
            st.info("No OpenAI API key is configured yet. The app will use the local test parser so you can validate the workflow.")

        if st.button("Analyze SOC 2 report", type="primary", key="analyze_soc2"):
            try:
                with st.spinner("Analyzing SOC 2 report..."):
                    result = extract_soc2_metadata(uploaded.getvalue(), api_key=api_key or None)
                    st.session_state["soc2_extraction"] = result
                st.success(f"Analysis complete using {result.get('extraction_method', 'extractor')}.")
            except Exception as exc:
                st.error(f"Could not analyze the report: {exc}")

    extraction = st.session_state.get("soc2_extraction", {}) if uploaded else {}

    if extraction:
        st.markdown("##### Extracted metadata — analyst review required")
        c1, c2, c3 = st.columns(3)
        c1.metric("Confidence", f"{float(extraction.get('confidence', 0))*100:.0f}%")
        c2.metric("Exceptions", extraction.get("exceptions_count", 0))
        c3.metric("Method", extraction.get("extraction_method", "Unknown"))

        if extraction.get("exceptions"):
            st.markdown("**Detected exceptions**")
            st.dataframe(pd.DataFrame(extraction["exceptions"]), use_container_width=True, hide_index=True)

        if extraction.get("cuecs_summary"):
            with st.expander("CUECs detected"):
                st.write(extraction["cuecs_summary"])
        if extraction.get("subservice_organizations_summary"):
            with st.expander("Subservice organizations detected"):
                st.write(extraction["subservice_organizations_summary"])
        if extraction.get("review_notes"):
            st.caption(extraction["review_notes"])

    with st.form("register_evidence"):
        document_name = st.text_input(
            "Document name",
            value=uploaded.name if uploaded else "",
        )
        c1, c2 = st.columns(2)
        with c1:
            issuer = st.text_input("Issuer / auditor", value=extraction.get("issuer", ""))
            document_date = st.text_input("Document date (YYYY-MM-DD)", value=extraction.get("document_date", ""))
            coverage_start = st.text_input("Coverage start (YYYY-MM-DD)", value=extraction.get("coverage_start", ""))
            coverage_end = st.text_input("Coverage end (YYYY-MM-DD)", value=extraction.get("coverage_end", ""))
        with c2:
            expiration_date = st.text_input("Expiration date (YYYY-MM-DD)")
            opinion_options = ["", "Unqualified", "Qualified", "Pass", "Pass with Exceptions", "Fail", "Not Applicable"]
            extracted_opinion = extraction.get("opinion", "")
            opinion_index = opinion_options.index(extracted_opinion) if extracted_opinion in opinion_options else 0
            opinion = st.selectbox("Opinion / result", opinion_options, index=opinion_index)
            exceptions_count = st.number_input(
                "Exceptions / findings count",
                min_value=0,
                step=1,
                value=int(extraction.get("exceptions_count", 0) or 0),
            )
            analyst_notes = st.text_area(
                "Analyst notes",
                value=extraction.get("review_notes", ""),
            )

        accept_extracted = st.checkbox(
            "I reviewed the extracted metadata and confirm it is appropriate to save.",
            value=False if extraction else True,
        )

        if st.form_submit_button("Save evidence", type="primary"):
            final_name = document_name.strip()
            if not final_name:
                st.error("Upload a file or enter a document name.")
            elif extraction and not accept_extracted:
                st.error("Review and confirm the extracted metadata before saving.")
            else:
                storage_path = None
                if uploaded:
                    safe_name = f"{vendor.id}_{int(datetime.utcnow().timestamp())}_{uploaded.name}"
                    storage_path = os.path.join(EVIDENCE_DIR, safe_name)
                    with open(storage_path, "wb") as f:
                        f.write(uploaded.getbuffer())

                ev = Evidence(
                    vendor_id=vendor.id,
                    assessment_id=assessment.id if assessment else None,
                    document_type=document_type,
                    document_name=final_name,
                    document_date=document_date,
                    coverage_start=coverage_start,
                    coverage_end=coverage_end,
                    expiration_date=expiration_date,
                    issuer=issuer,
                    opinion=opinion,
                    exceptions_count=int(exceptions_count),
                    status=evidence_status(expiration_date),
                    storage_path=storage_path,
                    analyst_notes=analyst_notes,
                )
                session.add(ev)
                session.commit()

                # Turn extracted SOC 2 exceptions into reviewable findings.
                created_findings = 0
                for item in extraction.get("exceptions", []):
                    title = f"{item.get('control_id', 'SOC 2')} exception"
                    existing = session.query(Finding).filter_by(vendor_id=vendor.id, title=title).first()
                    if not existing:
                        session.add(Finding(
                            vendor_id=vendor.id,
                            title=title,
                            description=item.get("description", ""),
                            source="Evidence Review",
                            severity=item.get("severity", "Moderate"),
                            status="Open",
                            owner="",
                        ))
                        created_findings += 1
                session.commit()

                st.success(
                    f"{document_type} registered for {vendor.display_name}."
                    + (f" {created_findings} finding(s) created from detected exceptions." if created_findings else "")
                )
                st.session_state.pop("soc2_extraction", None)

    st.subheader("Evidence review")
    latest = session.query(Evidence).order_by(Evidence.created_at.desc()).all()
    if latest:
        selected = st.selectbox(
            "Select evidence",
            latest,
            format_func=lambda e: f"#{e.id} — {e.vendor.display_name} — {e.document_type}"
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Status", evidence_status(selected.expiration_date))
        c2.metric("Exceptions", selected.exceptions_count)
        c3.metric("Opinion", selected.opinion or "Not recorded")
        st.write({
            "Document": selected.document_name,
            "Issuer": selected.issuer,
            "Coverage": f"{selected.coverage_start or '—'} to {selected.coverage_end or '—'}",
            "Expiration": selected.expiration_date or "—",
            "Linked assessment": selected.assessment_id or "None",
        })
        if selected.analyst_notes:
            st.markdown("**Analyst notes**")
            st.write(selected.analyst_notes)

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
    evidence = session.query(Evidence).all()
    assessments = session.query(Assessment).all()

    df = pd.DataFrame([{
        "Vendor": v.display_name,
        "Criticality": v.criticality,
        "Inherent": v.inherent_risk_score,
        "External": v.external_risk_score,
        "Control Effectiveness": v.control_effectiveness,
        "Residual": v.residual_risk_score,
        "Rating": v.overall_risk_rating,
        "Assessments": sum(1 for a in assessments if a.vendor_id == v.id),
        "Evidence Items": sum(1 for e in evidence if e.vendor_id == v.id),
    } for v in vendors])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button(
        "Download vendor risk register CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="vendor_risk_register.csv",
        mime="text/csv"
    )

    if evidence:
        st.subheader("Evidence Coverage")
        ev_df = pd.DataFrame([{
            "Vendor": e.vendor.display_name if e.vendor else e.vendor_id,
            "Type": e.document_type,
            "Status": evidence_status(e.expiration_date),
            "Expiration": e.expiration_date,
        } for e in evidence])
        st.dataframe(ev_df, use_container_width=True, hide_index=True)

st.sidebar.title("LMA Vendor Trust Intelligence")
page = st.sidebar.radio(
    "Navigation",
    [
        "Control Tower",
        "Vendors",
        "New Vendor Intake",
        "Assessments",
        "Evidence Center",
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
elif page == "Assessments":
    render_assessments()
elif page == "Evidence Center":
    render_evidence()
elif page == "Findings":
    render_findings()
elif page == "Monitoring":
    render_monitoring()
elif page == "Reports":
    render_reports()
