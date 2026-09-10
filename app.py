import json
import os
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from src.db import (
    Assessment,
    Engagement,
    Evidence,
    Finding,
    MonitoringEvent,
    Vendor,
    get_session,
    init_db,
)
from src.evidence_ai import extract_soc2_metadata
from src.scoring import (
    InherentRiskInput,
    calculate_inherent_risk,
    calculate_residual_risk,
    rating_from_score,
    tier_from_score,
)
from src.seed import seed_demo_data


# ---------------------------------------------------------
# Application configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="LMA Vendor Trust Intelligence",
    page_icon="🛡️",
    layout="wide",
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


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def metric_card(label, value):
    st.metric(label, value)


def evidence_status(expiration_date):
    if not expiration_date:
        return "Received"

    try:
        exp = datetime.strptime(
            expiration_date,
            "%Y-%m-%d",
        ).date()

        days = (exp - date.today()).days

        if days < 0:
            return "Expired"

        if days <= 60:
            return "Expiring Soon"

        return "Valid"

    except ValueError:
        return "Received"


def confidence_label(score):
    if score >= 0.85:
        return "High"

    if score >= 0.65:
        return "Medium"

    return "Low"


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
        return st.secrets.get(
            "OPENAI_API_KEY",
            "",
        )

    except Exception:
        return os.getenv(
            "OPENAI_API_KEY",
            "",
        )


def load_analyst_actions(raw_value):
    if not raw_value:
        return []

    try:
        parsed = json.loads(raw_value)

        if isinstance(parsed, list):
            return parsed

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        pass

    return []


# ---------------------------------------------------------
# Control Tower
# ---------------------------------------------------------

def render_control_tower():
    st.title("🛡️ Vendor Security Control Tower")

    st.caption(
        "Which vendors need attention right now, "
        "why, and what should we do next?"
    )

    vendors = session.query(Vendor).all()
    findings = session.query(Finding).all()
    events = session.query(MonitoringEvent).all()
    evidence = session.query(Evidence).all()
    assessments = session.query(Assessment).all()

    critical = sum(
        1
        for vendor in vendors
        if vendor.criticality == "Critical"
    )

    high_residual = sum(
        1
        for vendor in vendors
        if vendor.residual_risk_score >= 50
    )

    open_findings = sum(
        1
        for finding in findings
        if finding.status != "Closed"
    )

    open_events = sum(
        1
        for event in events
        if event.status != "Closed"
        and event.requires_review
    )

    evidence_attention = sum(
        1
        for item in evidence
        if evidence_status(
            item.expiration_date
        )
        in [
            "Expired",
            "Expiring Soon",
        ]
    )

    open_assessments = sum(
        1
        for assessment in assessments
        if assessment.status
        not in [
            "Completed",
            "Closed",
        ]
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        metric_card(
            "Vendors",
            len(vendors),
        )

    with c2:
        metric_card(
            "Critical Vendors",
            critical,
        )

    with c3:
        metric_card(
            "High/Critical Residual Risk",
            high_residual,
        )

    with c4:
        metric_card(
            "Open Assessments",
            open_assessments,
        )

    with c5:
        metric_card(
            "Attention Items",
            open_findings
            + open_events
            + evidence_attention,
        )

    st.subheader(
        "Vendor Attention Queue"
    )

    rows = []

    for vendor in vendors:
        vendor_events = [
            event
            for event in events
            if event.vendor_id == vendor.id
            and event.status != "Closed"
        ]

        vendor_findings = [
            finding
            for finding in findings
            if finding.vendor_id == vendor.id
            and finding.status != "Closed"
        ]

        vendor_evidence = [
            item
            for item in evidence
            if item.vendor_id == vendor.id
        ]

        stale = [
            item
            for item in vendor_evidence
            if evidence_status(
                item.expiration_date
            )
            in [
                "Expired",
                "Expiring Soon",
            ]
        ]

        reason = ""

        if vendor_events:
            reason = vendor_events[0].event_type

        elif vendor_findings:
            reason = vendor_findings[0].title

        elif stale:
            reason = (
                f"{stale[0].document_type}: "
                f"{evidence_status(stale[0].expiration_date)}"
            )

        elif vendor.residual_risk_score >= 50:
            reason = "Elevated residual risk"

        if reason:
            rows.append(
                {
                    "Vendor": vendor.display_name,
                    "Residual Risk": (
                        vendor.residual_risk_score
                    ),
                    "Rating": (
                        vendor.overall_risk_rating
                    ),
                    "Reason": reason,
                    "Priority": (
                        "P1"
                        if vendor.residual_risk_score >= 75
                        else "P2"
                    ),
                }
            )

    if rows:
        attention_df = (
            pd.DataFrame(rows)
            .sort_values(
                "Residual Risk",
                ascending=False,
            )
        )

        st.dataframe(
            attention_df,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.success(
            "No vendors currently require attention."
        )

    st.subheader(
        "Risk Portfolio"
    )

    chart_df = pd.DataFrame(
        [
            {
                "Vendor": vendor.display_name,
                "Inherent Risk": (
                    vendor.inherent_risk_score
                ),
                "Residual Risk": (
                    vendor.residual_risk_score
                ),
                "External Risk": (
                    vendor.external_risk_score
                ),
            }
            for vendor in vendors
        ]
    )

    if not chart_df.empty:
        fig = px.scatter(
            chart_df,
            x="Inherent Risk",
            y="Residual Risk",
            size="External Risk",
            hover_name="Vendor",
            range_x=[0, 100],
            range_y=[0, 100],
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )


# ---------------------------------------------------------
# Vendor Inventory / Vendor 360
# ---------------------------------------------------------

def render_vendors():
    st.title(
        "🏢 Vendor Inventory"
    )

    vendors = session.query(
        Vendor
    ).all()

    df = pd.DataFrame(
        [
            {
                "ID": vendor.id,
                "Vendor": vendor.display_name,
                "Industry": vendor.industry,
                "Criticality": vendor.criticality,
                "Inherent Risk": (
                    vendor.inherent_risk_score
                ),
                "Residual Risk": (
                    vendor.residual_risk_score
                ),
                "External Risk": (
                    vendor.external_risk_score
                ),
                "Rating": vendor.overall_risk_rating,
                "Status": vendor.relationship_status,
            }
            for vendor in vendors
        ]
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader(
        "Vendor 360"
    )

    if not vendors:
        st.info(
            "No vendors available."
        )
        return

    selected = st.selectbox(
        "Select vendor",
        vendors,
        format_func=lambda vendor: (
            vendor.display_name
        ),
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Inherent Risk",
        selected.inherent_risk_score,
    )

    c2.metric(
        "Residual Risk",
        selected.residual_risk_score,
    )

    c3.metric(
        "External Risk",
        selected.external_risk_score,
    )

    c4.metric(
        "Security Rating",
        selected.security_rating,
    )

    tabs = st.tabs(
        [
            "Overview",
            "Engagements",
            "Assessments",
            "Evidence",
            "Findings",
            "Monitoring",
        ]
    )

    with tabs[0]:
        st.write(
            {
                "Legal name": (
                    selected.legal_name
                ),
                "Primary domain": (
                    selected.primary_domain
                ),
                "Industry": (
                    selected.industry
                ),
                "Country": (
                    selected.headquarters_country
                ),
                "Criticality": (
                    selected.criticality
                ),
                "Overall risk": (
                    selected.overall_risk_rating
                ),
                "Recommended assessment": (
                    recommended_assessment(
                        selected
                    )
                ),
            }
        )

    with tabs[1]:
        engagements = (
            session.query(Engagement)
            .filter_by(
                vendor_id=selected.id
            )
            .all()
        )

        if engagements:
            engagement_df = pd.DataFrame(
                [
                    {
                        "Service": (
                            engagement.service_name
                        ),
                        "Owner": (
                            engagement.business_owner
                        ),
                        "Criticality": (
                            engagement.business_criticality
                        ),
                        "Data": (
                            engagement.data_classification
                        ),
                        "Production Access": (
                            engagement.production_access
                        ),
                        "AI Enabled": (
                            engagement.ai_enabled
                        ),
                    }
                    for engagement in engagements
                ]
            )

            st.dataframe(
                engagement_df,
                use_container_width=True,
                hide_index=True,
            )

        else:
            st.info(
                "No engagements yet."
            )

    with tabs[2]:
        assessments = (
            session.query(Assessment)
            .filter_by(
                vendor_id=selected.id
            )
            .all()
        )

        if assessments:
            assessment_df = pd.DataFrame(
                [
                    {
                        "Assessment": (
                            assessment.assessment_type
                        ),
                        "Reason": (
                            assessment.assessment_reason
                        ),
                        "Status": (
                            assessment.status
                        ),
                        "Assigned To": (
                            assessment.assigned_to
                        ),
                        "Due": (
                            assessment.due_date
                        ),
                        "Approval": (
                            assessment.approval_status
                        ),
                    }
                    for assessment
                    in assessments
                ]
            )

            st.dataframe(
                assessment_df,
                use_container_width=True,
                hide_index=True,
            )

        else:
            st.info(
                "No assessments yet."
            )

    with tabs[3]:
        evidence_rows = (
            session.query(Evidence)
            .filter_by(
                vendor_id=selected.id
            )
            .all()
        )

        if evidence_rows:
            evidence_df = pd.DataFrame(
                [
                    {
                        "Type": item.document_type,
                        "Document": item.document_name,
                        "Issuer": item.issuer,
                        "Expiration": item.expiration_date,
                        "Status": evidence_status(
                            item.expiration_date
                        ),
                        "Exceptions": (
                            item.exceptions_count
                        ),
                    }
                    for item in evidence_rows
                ]
            )

            st.dataframe(
                evidence_df,
                use_container_width=True,
                hide_index=True,
            )

        else:
            st.info(
                "No evidence yet."
            )

    with tabs[4]:
        findings = (
            session.query(Finding)
            .filter_by(
                vendor_id=selected.id
            )
            .all()
        )

        if findings:
            findings_df = pd.DataFrame(
                [
                    {
                        "Finding": finding.title,
                        "Severity": finding.severity,
                        "Status": finding.status,
                        "Source": finding.source,
                        "Owner": finding.owner,
                        "Target": finding.target_date,
                    }
                    for finding in findings
                ]
            )

            st.dataframe(
                findings_df,
                use_container_width=True,
                hide_index=True,
            )

        else:
            st.success(
                "No findings."
            )

    with tabs[5]:
        events = (
            session.query(MonitoringEvent)
            .filter_by(
                vendor_id=selected.id
            )
            .all()
        )

        if events:
            events_df = pd.DataFrame(
                [
                    {
                        "Event": event.event_type,
                        "Severity": event.severity,
                        "Status": event.status,
                        "Previous": (
                            event.previous_value
                        ),
                        "New": event.new_value,
                    }
                    for event in events
                ]
            )

            st.dataframe(
                events_df,
                use_container_width=True,
                hide_index=True,
            )

        else:
            st.info(
                "No monitoring events."
            )


# ---------------------------------------------------------
# Vendor Intake
# ---------------------------------------------------------

def render_intake():
    st.title(
        "📝 New Vendor Intake"
    )

    st.caption(
        "Create the vendor + engagement and "
        "automatically calculate inherent risk."
    )

    with st.form(
        "vendor_intake"
    ):
        col1, col2 = st.columns(2)

        with col1:
            vendor_name = st.text_input(
                "Vendor name *"
            )

            service_name = st.text_input(
                "Service / engagement name *"
            )

            website = st.text_input(
                "Website"
            )

            industry = st.text_input(
                "Industry"
            )

            business_owner = st.text_input(
                "Business owner"
            )

            department = st.text_input(
                "Department"
            )

        with col2:
            country = st.text_input(
                "Headquarters country",
                value="United States",
            )

            criticality_label = st.selectbox(
                "Business criticality",
                [
                    "Low",
                    "Moderate",
                    "High",
                    "Critical",
                ],
            )

            data_label = st.selectbox(
                "Highest data sensitivity",
                [
                    "Public",
                    "Internal",
                    "Confidential",
                    "PII",
                    "Sensitive PII",
                    "PHI / PCI / Credentials",
                ],
            )

            production_access = st.checkbox(
                "Production access"
            )

            privileged_access = st.checkbox(
                "Privileged access"
            )

            network_access = st.checkbox(
                "Network access"
            )

            ai_enabled = st.checkbox(
                "AI-enabled service"
            )

        st.markdown(
            "#### Risk factors"
        )

        data_map = {
            "Public": 0,
            "Internal": 5,
            "Confidential": 10,
            "PII": 15,
            "Sensitive PII": 20,
            "PHI / PCI / Credentials": 25,
        }

        crit_map = {
            "Low": 5,
            "Moderate": 10,
            "High": 15,
            "Critical": 20,
        }

        if privileged_access:
            access_score = 20

        elif production_access:
            access_score = 16

        elif network_access:
            access_score = 12

        else:
            access_score = 0

        data_volume = st.slider(
            "Data volume risk",
            0,
            10,
            5,
        )

        regulatory = st.slider(
            "Regulatory exposure",
            0,
            10,
            5,
        )

        fourth_party = st.slider(
            "Fourth-party dependency",
            0,
            5,
            2,
        )

        geographic = st.slider(
            "Geographic risk",
            0,
            5,
            1,
        )

        ai_autonomy = st.slider(
            "AI / autonomy risk",
            0,
            5,
            3 if ai_enabled else 0,
        )

        submitted = st.form_submit_button(
            "Create vendor and calculate risk",
            type="primary",
        )

    if submitted:
        if not vendor_name or not service_name:
            st.error(
                "Vendor name and service name "
                "are required."
            )
            return

        inherent = calculate_inherent_risk(
            InherentRiskInput(
                data_sensitivity=(
                    data_map[data_label]
                ),
                system_access=access_score,
                business_criticality=(
                    crit_map[
                        criticality_label
                    ]
                ),
                data_volume=data_volume,
                regulatory_exposure=regulatory,
                fourth_party_dependency=(
                    fourth_party
                ),
                geographic_risk=geographic,
                ai_autonomy=ai_autonomy,
            )
        )

        residual = calculate_residual_risk(
            inherent,
            50,
            25,
        )

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
            overall_risk_rating=(
                rating_from_score(
                    residual
                )
            ),
        )

        session.add(vendor)
        session.commit()

        engagement = Engagement(
            vendor_id=vendor.id,
            service_name=service_name,
            business_owner=business_owner,
            department=department,
            business_criticality=(
                criticality_label
            ),
            data_classification=data_label,
            production_access=(
                production_access
            ),
            privileged_access=(
                privileged_access
            ),
            network_access=network_access,
            ai_enabled=ai_enabled,
        )

        session.add(
            engagement
        )

        session.commit()

        st.success(
            f"{vendor_name} created."
        )

        st.metric(
            "Inherent Risk",
            inherent,
        )

        st.write(
            f"**Tier:** "
            f"{tier_from_score(inherent)}"
        )

        st.write(
            "**Recommended assessment:** "
            f"{recommended_assessment(vendor)}"
        )

        st.write(
            f"**Initial residual risk:** "
            f"{residual} — "
            f"{rating_from_score(residual)}"
        )


# ---------------------------------------------------------
# Assessments
# ---------------------------------------------------------

def render_assessments():
    st.title(
        "🧭 Assessments"
    )

    st.caption(
        "Launch, assign, and track risk-based "
        "vendor security assessments."
    )

    vendors = (
        session.query(Vendor)
        .order_by(
            Vendor.display_name
        )
        .all()
    )

    assessments = (
        session.query(Assessment)
        .order_by(
            Assessment.created_at.desc()
        )
        .all()
    )

    if assessments:
        assessment_df = pd.DataFrame(
            [
                {
                    "ID": assessment.id,
                    "Vendor": (
                        assessment.vendor.display_name
                        if assessment.vendor
                        else assessment.vendor_id
                    ),
                    "Assessment": (
                        assessment.assessment_type
                    ),
                    "Reason": (
                        assessment.assessment_reason
                    ),
                    "Status": assessment.status,
                    "Assigned To": (
                        assessment.assigned_to
                    ),
                    "Due": assessment.due_date,
                    "Approval": (
                        assessment.approval_status
                    ),
                }
                for assessment in assessments
            ]
        )

        st.dataframe(
            assessment_df,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.info(
            "No assessments created yet."
        )

    st.subheader(
        "Create assessment"
    )

    if not vendors:
        st.warning(
            "Create a vendor first."
        )
        return

    with st.form(
        "create_assessment"
    ):
        vendor = st.selectbox(
            "Vendor",
            vendors,
            format_func=lambda item: (
                item.display_name
            ),
        )

        st.caption(
            "Recommended based on inherent risk: "
            f"{recommended_assessment(vendor)}"
        )

        assessment_type = st.selectbox(
            "Assessment type",
            ASSESSMENT_TYPES,
        )

        reason = st.selectbox(
            "Assessment reason",
            [
                "New vendor",
                "Annual review",
                "Contract renewal",
                "Material change",
                "Security incident",
                "Security rating deterioration",
                "AI capability introduced",
            ],
        )

        assigned_to = st.text_input(
            "Assigned analyst"
        )

        due_date = st.date_input(
            "Due date"
        )

        notes = st.text_area(
            "Scope / notes"
        )

        if st.form_submit_button(
            "Launch assessment",
            type="primary",
        ):
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

            session.add(
                assessment
            )

            session.commit()

            st.success(
                f"{assessment_type} launched "
                f"for {vendor.display_name}."
            )

    st.subheader(
        "Update assessment"
    )

    active = (
        session.query(Assessment)
        .order_by(
            Assessment.created_at.desc()
        )
        .all()
    )

    if active:
        status_options = [
            "Not Started",
            "In Progress",
            "Vendor Responding",
            "Analyst Review",
            "Completed",
            "Closed",
        ]

        with st.form(
            "update_assessment"
        ):
            chosen = st.selectbox(
                "Assessment",
                active,
                format_func=lambda assessment: (
                    f"#{assessment.id} — "
                    f"{assessment.vendor.display_name} — "
                    f"{assessment.assessment_type}"
                ),
            )

            status_index = (
                status_options.index(
                    chosen.status
                )
                if chosen.status
                in status_options
                else 1
            )

            status = st.selectbox(
                "Status",
                status_options,
                index=status_index,
            )

            approval = st.selectbox(
                "Approval status",
                [
                    "Pending",
                    "Approved",
                    "Approved with Conditions",
                    "Rejected",
                ],
            )

            risk_score = st.slider(
                "Assessment risk score",
                0,
                100,
                int(
                    chosen.risk_score
                    or 0
                ),
            )

            if st.form_submit_button(
                "Save assessment update"
            ):
                chosen.status = status
                chosen.approval_status = approval
                chosen.risk_score = risk_score

                if status in [
                    "Completed",
                    "Closed",
                ]:
                    chosen.completed_at = (
                        datetime.utcnow()
                    )

                session.commit()

                st.success(
                    "Assessment updated."
                )


# ---------------------------------------------------------
# Evidence Center
# ---------------------------------------------------------

def render_evidence():
    st.title(
        "📁 Evidence Center"
    )

    st.caption(
        "Track assurance artifacts, validity, "
        "coverage, and key report metadata."
    )

    vendors = (
        session.query(Vendor)
        .order_by(
            Vendor.display_name
        )
        .all()
    )

    evidence_rows = (
        session.query(Evidence)
        .order_by(
            Evidence.created_at.desc()
        )
        .all()
    )

    if evidence_rows:
        df = pd.DataFrame(
            [
                {
                    "ID": item.id,
                    "Vendor": (
                        item.vendor.display_name
                        if item.vendor
                        else item.vendor_id
                    ),
                    "Type": item.document_type,
                    "Document": item.document_name,
                    "Issuer": item.issuer,
                    "Coverage End": (
                        item.coverage_end
                    ),
                    "Expiration": (
                        item.expiration_date
                    ),
                    "Status": evidence_status(
                        item.expiration_date
                    ),
                    "Exceptions": (
                        item.exceptions_count
                    ),
                }
                for item in evidence_rows
            ]
        )

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

        attention = df[
            df["Status"].isin(
                [
                    "Expired",
                    "Expiring Soon",
                ]
            )
        ]

        if not attention.empty:
            st.warning(
                f"{len(attention)} evidence "
                "item(s) require attention."
            )

            st.dataframe(
                attention,
                use_container_width=True,
                hide_index=True,
            )

    else:
        st.info(
            "No evidence has been registered yet."
        )

    st.subheader(
        "Register evidence"
    )

    if not vendors:
        st.warning(
            "Create a vendor first."
        )
        return

    vendor = st.selectbox(
        "Vendor",
        vendors,
        format_func=lambda item: (
            item.display_name
        ),
        key="evidence_vendor",
    )

    vendor_assessments = (
        session.query(Assessment)
        .filter_by(
            vendor_id=vendor.id
        )
        .all()
    )

    assessment_choices = (
        [None]
        + vendor_assessments
    )

    assessment = st.selectbox(
        "Linked assessment (optional)",
        assessment_choices,
        format_func=lambda item: (
            "None"
            if item is None
            else (
                f"#{item.id} — "
                f"{item.assessment_type}"
            )
        ),
        key="evidence_assessment",
    )

    document_type = st.selectbox(
        "Document type",
        EVIDENCE_TYPES,
        key="evidence_type",
    )

    uploaded = st.file_uploader(
        "Upload evidence file",
        type=[
            "pdf",
            "docx",
            "xlsx",
            "csv",
            "txt",
        ],
        key="evidence_upload",
    )

    if (
        uploaded
        and document_type
        in [
            "SOC 2 Type II",
            "SOC 2 Type I",
        ]
    ):
        st.markdown(
            "#### AI Evidence Analyst"
        )

        api_key = get_openai_api_key()

        if api_key:
            st.success(
                "OpenAI extraction is configured."
            )

        else:
            st.info(
                "No OpenAI API key is configured. "
                "The application will use the local "
                "SOC 2 parser for this analysis."
            )

        if st.button(
            "Analyze SOC 2 report",
            type="primary",
            key="analyze_soc2",
        ):
            try:
                with st.spinner(
                    "Analyzing SOC 2 report..."
                ):
                    result = (
                        extract_soc2_metadata(
                            uploaded.getvalue(),
                            api_key=(
                                api_key
                                or None
                            ),
                        )
                    )

                    st.session_state[
                        "soc2_extraction"
                    ] = result

                st.success(
                    "Analysis complete using "
                    f"{result.get('extraction_method', 'extractor')}."
                )

            except Exception as exc:
                st.error(
                    "Could not analyze "
                    f"the report: {exc}"
                )

    extraction = (
        st.session_state.get(
            "soc2_extraction",
            {},
        )
        if uploaded
        else {}
    )

    # -----------------------------------------------------
    # Extraction review UI
    # -----------------------------------------------------

    if extraction:
        st.markdown(
            "##### Extracted metadata — "
            "analyst review required"
        )

        confidence_score = float(
            extraction.get(
                "confidence",
                0,
            )
        )

        confidence_text = (
            confidence_label(
                confidence_score
            )
        )

        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric(
                "Extraction Confidence",
                f"{confidence_score * 100:.0f}%",
            )

            st.caption(
                f"Confidence level: "
                f"**{confidence_text}**"
            )

        with c2:
            st.metric(
                "Exceptions",
                extraction.get(
                    "exceptions_count",
                    0,
                ),
            )

        with c3:
            st.metric(
                "Method",
                extraction.get(
                    "extraction_method",
                    "Unknown",
                ),
            )

        if confidence_text == "High":
            st.success(
                "High extraction confidence — "
                "key SOC 2 metadata was successfully "
                "identified. Analyst validation is "
                "still required."
            )

        elif confidence_text == "Medium":
            st.warning(
                "Medium extraction confidence — "
                "some expected SOC 2 metadata may be "
                "missing or ambiguous. Review the "
                "extracted fields carefully."
            )

        else:
            st.error(
                "Low extraction confidence — "
                "important report metadata could not "
                "be reliably identified. Manual "
                "evidence review is recommended."
            )

        confidence_reasons = extraction.get(
            "confidence_reasons",
            [],
        )

        confidence_gaps = extraction.get(
            "confidence_gaps",
            [],
        )

        confidence_actions = extraction.get(
            "confidence_actions",
            [],
        )

        if (
            confidence_reasons
            or confidence_gaps
            or confidence_actions
        ):
            with st.expander(
                "Why this confidence score?"
            ):
                if confidence_reasons:
                    st.markdown(
                        "**Identified**"
                    )

                    for reason in (
                        confidence_reasons
                    ):
                        st.write(
                            f"✓ {reason}"
                        )

                if confidence_gaps:
                    st.markdown(
                        "**Missing / needs "
                        "analyst review**"
                    )

                    for gap in (
                        confidence_gaps
                    ):
                        st.write(
                            f"⚠ {gap}"
                        )

                if not confidence_gaps:
                    st.caption(
                        "No expected metadata gaps "
                        "were identified by the "
                        "extraction parser."
                    )

                if confidence_actions:
                    st.markdown("---")

                    st.markdown(
                        "**Recommended analyst actions**"
                    )

                    for item in (
                        confidence_actions
                    ):
                        gap = item.get(
                            "gap",
                            "Missing metadata",
                        )

                        action = item.get(
                            "action",
                            "Review the report manually.",
                        )

                        st.markdown(
                            f"**{gap}**"
                        )

                        st.write(
                            f"→ {action}"
                        )

        if extraction.get(
            "exceptions"
        ):
            st.markdown(
                "**Detected exceptions**"
            )

            st.dataframe(
                pd.DataFrame(
                    extraction[
                        "exceptions"
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

        if extraction.get(
            "cuecs_summary"
        ):
            with st.expander(
                "CUECs detected"
            ):
                st.write(
                    extraction[
                        "cuecs_summary"
                    ]
                )

        if extraction.get(
            "subservice_organizations_summary"
        ):
            with st.expander(
                "Subservice organizations detected"
            ):
                st.write(
                    extraction[
                        "subservice_organizations_summary"
                    ]
                )

        if extraction.get(
            "review_notes"
        ):
            st.caption(
                extraction[
                    "review_notes"
                ]
            )

    # -----------------------------------------------------
    # Evidence registration form
    # -----------------------------------------------------

    with st.form(
        "register_evidence"
    ):
        document_name = st.text_input(
            "Document name",
            value=(
                uploaded.name
                if uploaded
                else ""
            ),
        )

        c1, c2 = st.columns(2)

        with c1:
            issuer = st.text_input(
                "Issuer / auditor",
                value=extraction.get(
                    "issuer",
                    "",
                ),
            )

            document_date = st.text_input(
                "Document date (YYYY-MM-DD)",
                value=extraction.get(
                    "document_date",
                    "",
                ),
            )

            coverage_start = st.text_input(
                "Coverage start (YYYY-MM-DD)",
                value=extraction.get(
                    "coverage_start",
                    "",
                ),
            )

            coverage_end = st.text_input(
                "Coverage end (YYYY-MM-DD)",
                value=extraction.get(
                    "coverage_end",
                    "",
                ),
            )

        with c2:
            expiration_date = st.text_input(
                "Expiration date (YYYY-MM-DD)"
            )

            opinion_options = [
                "",
                "Unmodified",
                "Unqualified",
                "Qualified",
                "Adverse",
                "Disclaimer",
                "Pass",
                "Pass with Exceptions",
                "Fail",
                "Not Applicable",
            ]

            extracted_opinion = (
                extraction.get(
                    "opinion",
                    "",
                )
            )

            opinion_index = (
                opinion_options.index(
                    extracted_opinion
                )
                if extracted_opinion
                in opinion_options
                else 0
            )

            opinion = st.selectbox(
                "Opinion / result",
                opinion_options,
                index=opinion_index,
            )

            exceptions_count = (
                st.number_input(
                    "Exceptions / findings count",
                    min_value=0,
                    step=1,
                    value=int(
                        extraction.get(
                            "exceptions_count",
                            0,
                        )
                        or 0
                    ),
                )
            )

            analyst_notes = st.text_area(
                "Analyst notes",
                value=extraction.get(
                    "review_notes",
                    "",
                ),
            )

        accept_extracted = st.checkbox(
            "I reviewed the extracted metadata "
            "and confirm it is appropriate to save.",
            value=(
                False
                if extraction
                else True
            ),
        )

        if st.form_submit_button(
            "Save evidence",
            type="primary",
        ):
            final_name = (
                document_name.strip()
            )

            if not final_name:
                st.error(
                    "Upload a file or enter "
                    "a document name."
                )

            elif (
                extraction
                and not accept_extracted
            ):
                st.error(
                    "Review and confirm the "
                    "extracted metadata before saving."
                )

            else:
                storage_path = None

                if uploaded:
                    safe_name = (
                        f"{vendor.id}_"
                        f"{int(datetime.utcnow().timestamp())}_"
                        f"{uploaded.name}"
                    )

                    storage_path = (
                        os.path.join(
                            EVIDENCE_DIR,
                            safe_name,
                        )
                    )

                    with open(
                        storage_path,
                        "wb",
                    ) as evidence_file:
                        evidence_file.write(
                            uploaded.getbuffer()
                        )

                persisted_actions = (
                    extraction.get(
                        "confidence_actions",
                        [],
                    )
                )

                analyst_actions_json = (
                    json.dumps(
                        persisted_actions,
                        ensure_ascii=False,
                    )
                    if persisted_actions
                    else None
                )

                evidence_item = Evidence(
                    vendor_id=vendor.id,
                    assessment_id=(
                        assessment.id
                        if assessment
                        else None
                    ),
                    document_type=document_type,
                    document_name=final_name,
                    document_date=document_date,
                    coverage_start=coverage_start,
                    coverage_end=coverage_end,
                    expiration_date=(
                        expiration_date
                    ),
                    issuer=issuer,
                    opinion=opinion,
                    exceptions_count=int(
                        exceptions_count
                    ),
                    status=evidence_status(
                        expiration_date
                    ),
                    storage_path=storage_path,
                    analyst_notes=analyst_notes,
                    analyst_actions=(
                        analyst_actions_json
                    ),
                )

                session.add(
                    evidence_item
                )

                session.commit()

                created_findings = 0

                for item in extraction.get(
                    "exceptions",
                    [],
                ):
                    title = (
                        f"{item.get('control_id', 'SOC 2')} "
                        "exception"
                    )

                    existing = (
                        session.query(Finding)
                        .filter_by(
                            vendor_id=vendor.id,
                            title=title,
                        )
                        .first()
                    )

                    if not existing:
                        finding = Finding(
                            vendor_id=vendor.id,
                            title=title,
                            description=item.get(
                                "description",
                                "",
                            ),
                            source="Evidence Review",
                            severity=item.get(
                                "severity",
                                "Moderate",
                            ),
                            status="Open",
                            owner="",
                        )

                        session.add(
                            finding
                        )

                        created_findings += 1

                session.commit()

                message = (
                    f"{document_type} registered "
                    f"for {vendor.display_name}."
                )

                if created_findings:
                    message += (
                        f" {created_findings} "
                        "finding(s) created from "
                        "detected exceptions."
                    )

                if persisted_actions:
                    message += (
                        f" {len(persisted_actions)} "
                        "analyst action(s) preserved "
                        "with the evidence record."
                    )

                st.success(
                    message
                )

                st.session_state.pop(
                    "soc2_extraction",
                    None,
                )

    # -----------------------------------------------------
    # Evidence review
    # -----------------------------------------------------

    st.subheader(
        "Evidence review"
    )

    latest = (
        session.query(Evidence)
        .order_by(
            Evidence.created_at.desc()
        )
        .all()
    )

    if latest:
        selected = st.selectbox(
            "Select evidence",
            latest,
            format_func=lambda item: (
                f"#{item.id} — "
                f"{item.vendor.display_name} — "
                f"{item.document_type}"
            ),
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Status",
            evidence_status(
                selected.expiration_date
            ),
        )

        c2.metric(
            "Exceptions",
            selected.exceptions_count,
        )

        c3.metric(
            "Opinion",
            selected.opinion
            or "Not recorded",
        )

        st.write(
            {
                "Document": (
                    selected.document_name
                ),
                "Issuer": (
                    selected.issuer
                ),
                "Coverage": (
                    f"{selected.coverage_start or '—'} "
                    f"to "
                    f"{selected.coverage_end or '—'}"
                ),
                "Expiration": (
                    selected.expiration_date
                    or "—"
                ),
                "Linked assessment": (
                    selected.assessment_id
                    or "None"
                ),
            }
        )

        if selected.analyst_notes:
            st.markdown(
                "**Analyst notes**"
            )

            st.write(
                selected.analyst_notes
            )

        persisted_actions = (
            load_analyst_actions(
                selected.analyst_actions
            )
        )

        if persisted_actions:
            st.markdown(
                "**Persisted analyst actions**"
            )

            st.caption(
                "These recommendations were saved "
                "with the evidence record during "
                "the original evidence analysis."
            )

            for item in (
                persisted_actions
            ):
                gap = item.get(
                    "gap",
                    "Missing metadata",
                )

                action = item.get(
                    "action",
                    "Review the report manually.",
                )

                st.markdown(
                    f"**⚠ {gap}**"
                )

                st.write(
                    f"→ {action}"
                )


# ---------------------------------------------------------
# Findings
# ---------------------------------------------------------

def render_findings():
    st.title(
        "⚠️ Findings & Remediation"
    )

    vendors = session.query(
        Vendor
    ).all()

    findings = session.query(
        Finding
    ).all()

    if findings:
        findings_df = pd.DataFrame(
            [
                {
                    "ID": finding.id,
                    "Vendor": next(
                        (
                            vendor.display_name
                            for vendor in vendors
                            if vendor.id
                            == finding.vendor_id
                        ),
                        finding.vendor_id,
                    ),
                    "Finding": finding.title,
                    "Severity": finding.severity,
                    "Status": finding.status,
                    "Owner": finding.owner,
                    "Target": finding.target_date,
                }
                for finding in findings
            ]
        )

        st.dataframe(
            findings_df,
            use_container_width=True,
            hide_index=True,
        )

    st.subheader(
        "Create finding"
    )

    if not vendors:
        st.warning(
            "Create a vendor first."
        )
        return

    with st.form(
        "create_finding"
    ):
        vendor = st.selectbox(
            "Vendor",
            vendors,
            format_func=lambda item: (
                item.display_name
            ),
        )

        title = st.text_input(
            "Finding title"
        )

        description = st.text_area(
            "Description"
        )

        source = st.selectbox(
            "Source",
            [
                "Questionnaire",
                "Evidence Review",
                "External Telemetry",
                "Incident",
                "Analyst",
            ],
        )

        severity = st.selectbox(
            "Severity",
            [
                "Low",
                "Moderate",
                "High",
                "Critical",
            ],
        )

        owner = st.text_input(
            "Owner"
        )

        target_date = st.text_input(
            "Target date (YYYY-MM-DD)"
        )

        if st.form_submit_button(
            "Create finding"
        ):
            if not title:
                st.error(
                    "Finding title is required."
                )

            else:
                finding = Finding(
                    vendor_id=vendor.id,
                    title=title,
                    description=description,
                    source=source,
                    severity=severity,
                    owner=owner,
                    target_date=target_date,
                )

                session.add(
                    finding
                )

                session.commit()

                st.success(
                    "Finding created."
                )


# ---------------------------------------------------------
# Continuous Monitoring
# ---------------------------------------------------------

def render_monitoring():
    st.title(
        "📡 Continuous Monitoring"
    )

    vendors = session.query(
        Vendor
    ).all()

    events = (
        session.query(MonitoringEvent)
        .order_by(
            MonitoringEvent.event_date.desc()
        )
        .all()
    )

    if events:
        events_df = pd.DataFrame(
            [
                {
                    "Vendor": next(
                        (
                            vendor.display_name
                            for vendor in vendors
                            if vendor.id
                            == event.vendor_id
                        ),
                        event.vendor_id,
                    ),
                    "Event": event.event_type,
                    "Severity": event.severity,
                    "Status": event.status,
                    "Previous": (
                        event.previous_value
                    ),
                    "New": event.new_value,
                    "Review Required": (
                        event.requires_review
                    ),
                }
                for event in events
            ]
        )

        st.dataframe(
            events_df,
            use_container_width=True,
            hide_index=True,
        )

    st.subheader(
        "Record monitoring event"
    )

    if not vendors:
        st.warning(
            "Create a vendor first."
        )
        return

    with st.form(
        "monitor_event"
    ):
        vendor = st.selectbox(
            "Vendor",
            vendors,
            format_func=lambda item: (
                item.display_name
            ),
        )

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
            ],
        )

        severity = st.selectbox(
            "Severity",
            [
                "Low",
                "Moderate",
                "High",
                "Critical",
            ],
        )

        description = st.text_area(
            "Description"
        )

        previous_value = st.text_input(
            "Previous value"
        )

        new_value = st.text_input(
            "New value"
        )

        if st.form_submit_button(
            "Record event"
        ):
            event = MonitoringEvent(
                vendor_id=vendor.id,
                event_type=event_type,
                severity=severity,
                description=description,
                previous_value=previous_value,
                new_value=new_value,
                requires_review=True,
            )

            session.add(
                event
            )

            severity_bump = {
                "Low": 2,
                "Moderate": 5,
                "High": 10,
                "Critical": 25,
            }[severity]

            vendor.external_risk_score = min(
                100,
                vendor.external_risk_score
                + severity_bump,
            )

            vendor.residual_risk_score = (
                calculate_residual_risk(
                    vendor.inherent_risk_score,
                    vendor.control_effectiveness,
                    vendor.external_risk_score,
                )
            )

            vendor.overall_risk_rating = (
                rating_from_score(
                    vendor.residual_risk_score
                )
            )

            session.commit()

            st.success(
                "Monitoring event recorded and "
                "vendor risk recalculated."
            )


# ---------------------------------------------------------
# Reports
# ---------------------------------------------------------

def render_reports():
    st.title(
        "📊 Reports"
    )

    vendors = session.query(
        Vendor
    ).all()

    evidence = session.query(
        Evidence
    ).all()

    assessments = session.query(
        Assessment
    ).all()

    df = pd.DataFrame(
        [
            {
                "Vendor": vendor.display_name,
                "Criticality": vendor.criticality,
                "Inherent": (
                    vendor.inherent_risk_score
                ),
                "External": (
                    vendor.external_risk_score
                ),
                "Control Effectiveness": (
                    vendor.control_effectiveness
                ),
                "Residual": (
                    vendor.residual_risk_score
                ),
                "Rating": (
                    vendor.overall_risk_rating
                ),
                "Assessments": sum(
                    1
                    for assessment in assessments
                    if assessment.vendor_id
                    == vendor.id
                ),
                "Evidence Items": sum(
                    1
                    for item in evidence
                    if item.vendor_id
                    == vendor.id
                ),
            }
            for vendor in vendors
        ]
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download vendor risk register CSV",
        df.to_csv(
            index=False
        ).encode(
            "utf-8"
        ),
        file_name=(
            "vendor_risk_register.csv"
        ),
        mime="text/csv",
    )

    if evidence:
        st.subheader(
            "Evidence Coverage"
        )

        evidence_df = pd.DataFrame(
            [
                {
                    "Vendor": (
                        item.vendor.display_name
                        if item.vendor
                        else item.vendor_id
                    ),
                    "Type": item.document_type,
                    "Status": evidence_status(
                        item.expiration_date
                    ),
                    "Expiration": (
                        item.expiration_date
                    ),
                }
                for item in evidence
            ]
        )

        st.dataframe(
            evidence_df,
            use_container_width=True,
            hide_index=True,
        )


# ---------------------------------------------------------
# Navigation
# ---------------------------------------------------------

st.sidebar.title(
    "LMA Vendor Trust Intelligence"
)

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
    ],
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