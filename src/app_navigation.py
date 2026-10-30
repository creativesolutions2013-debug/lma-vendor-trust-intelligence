"""Development navigation; the synthetic journey requires no data access."""
import streamlit as st

from src.authz import (
    PERMISSION_ASSESSMENT_MANAGE, PERMISSION_AUDIT_READ,
    PERMISSION_EVIDENCE_UPLOAD, PERMISSION_FINDING_MANAGE,
    PERMISSION_MONITORING_MANAGE, PERMISSION_REPORT_EXPORT,
    PERMISSION_VENDOR_READ, PERMISSION_VENDOR_WRITE, can,
)


LEGACY_PAGE_PERMISSIONS = {
    "Control Tower": PERMISSION_VENDOR_READ,
    "Vendors": PERMISSION_VENDOR_READ,
    "New Vendor Intake": PERMISSION_VENDOR_WRITE,
    "Assessments": PERMISSION_ASSESSMENT_MANAGE,
    "Evidence Center": PERMISSION_EVIDENCE_UPLOAD,
    "Findings": PERMISSION_FINDING_MANAGE,
    "Monitoring": PERMISSION_MONITORING_MANAGE,
    "Reports": PERMISSION_REPORT_EXPORT,
    "Audit Log": PERMISSION_AUDIT_READ,
}


def select_app_page(principal):
    st.sidebar.title("LMA Vendor Trust Intelligence")
    st.sidebar.caption("Development identity — not production authentication")
    st.sidebar.write({"User": principal.display_name, "Role": principal.role})
    pages = ["New Assessment"]
    if st.sidebar.checkbox("Show internal development tools", value=False):
        pages += ["Guided Assessment Demo"] + [
            name for name, permission in LEGACY_PAGE_PERMISSIONS.items()
            if can(principal, permission)
        ]
    selected = st.sidebar.radio("Navigation", pages)
    if selected not in {"New Assessment", "Guided Assessment Demo"}:
        st.sidebar.caption("Legacy development pages use global records. Synthetic data only.")
    return selected
