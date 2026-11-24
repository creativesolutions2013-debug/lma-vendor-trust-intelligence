"""M4C-2B-2A legacy route inventory and future-production deny contract.

This is a *planning/test* boundary: it is NOT wired to Streamlit and cannot
authorize any live route. AUTH_MODE=production still refuses at app startup.
Every legacy page/action remains blocked for authenticated production users
until a separate server-enforced tenant-safe service replaces its data paths.
"""

from dataclasses import dataclass


LEGACY_PAGES = frozenset({
    "Control Tower", "Vendors", "New Vendor Intake", "Assessments",
    "Evidence Center", "Findings", "Monitoring", "Reports", "Audit Log",
})

LEGACY_OPERATIONS = frozenset({
    "list", "detail", "create", "update", "delete", "upload", "download",
    "export", "approve", "reject", "audit", "report", "monitor", "evaluate",
})

# These are backend *capability names*, not Streamlit pages. Recognition does
# not grant permission: the service must separately validate current sessions,
# database membership, effective role, exact engagement grant and parent links.
SCOPED_SERVICE_CAPABILITIES = frozenset({
    "tenant.metadata.read", "tenant.report.export",
})


@dataclass(frozen=True)
class ProductionRouteDecision:
    allowed: bool
    classification: str
    reason: str


def classify_production_route(page, operation):
    """Classify, but NEVER authorize, a future production request.

    Do not pass browser-supplied roles/tenant flags, or treat a policy record as
    sufficient for access. Only a wired and reviewed server authorization
    service could eventually permit a specific operation.
    """
    if type(page) is not str or type(operation) is not str:
        return ProductionRouteDecision(False, "unknown-denied", "Unrecognized operation.")
    if page in LEGACY_PAGES:
        return ProductionRouteDecision(
            False, "legacy-blocked",
            "Legacy application path is not independently tenant-authorized.",
        )
    if page in SCOPED_SERVICE_CAPABILITIES and operation in {"read", "export"}:
        return ProductionRouteDecision(
            False, "separate-verification-required",
            "A server-verified scoped service is required; route naming never grants access.",
        )
    return ProductionRouteDecision(False, "unknown-denied", "Unrecognized operation.")
