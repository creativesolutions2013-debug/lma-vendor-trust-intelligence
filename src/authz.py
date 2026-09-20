from dataclasses import dataclass
from typing import FrozenSet

ROLE_ADMIN = "Admin"
ROLE_RISK_MANAGER = "Risk Manager"
ROLE_ANALYST = "Analyst"
ROLE_VIEWER = "Viewer"

VALID_ROLES = {ROLE_ADMIN, ROLE_RISK_MANAGER, ROLE_ANALYST, ROLE_VIEWER}

PERMISSION_VENDOR_READ = "vendor.read"
PERMISSION_VENDOR_WRITE = "vendor.write"
PERMISSION_ASSESSMENT_MANAGE = "assessment.manage"
PERMISSION_EVIDENCE_READ = "evidence.read"
PERMISSION_EVIDENCE_UPLOAD = "evidence.upload"
PERMISSION_EVIDENCE_ANALYZE = "evidence.analyze"
PERMISSION_FINDING_MANAGE = "finding.manage"
PERMISSION_MONITORING_MANAGE = "monitoring.manage"
PERMISSION_REPORT_EXPORT = "report.export"
PERMISSION_ADMIN = "admin.manage"
PERMISSION_AUDIT_READ = "audit.read"

ALL_PERMISSIONS = frozenset({
    PERMISSION_VENDOR_READ,
    PERMISSION_VENDOR_WRITE,
    PERMISSION_ASSESSMENT_MANAGE,
    PERMISSION_EVIDENCE_READ,
    PERMISSION_EVIDENCE_UPLOAD,
    PERMISSION_EVIDENCE_ANALYZE,
    PERMISSION_FINDING_MANAGE,
    PERMISSION_MONITORING_MANAGE,
    PERMISSION_REPORT_EXPORT,
    PERMISSION_ADMIN,
    PERMISSION_AUDIT_READ,
})

ROLE_PERMISSIONS = {
    ROLE_ADMIN: ALL_PERMISSIONS,
    ROLE_RISK_MANAGER: frozenset({
        PERMISSION_AUDIT_READ,
        PERMISSION_VENDOR_READ,
        PERMISSION_VENDOR_WRITE,
        PERMISSION_ASSESSMENT_MANAGE,
        PERMISSION_EVIDENCE_READ,
        PERMISSION_EVIDENCE_UPLOAD,
        PERMISSION_EVIDENCE_ANALYZE,
        PERMISSION_FINDING_MANAGE,
        PERMISSION_MONITORING_MANAGE,
        PERMISSION_REPORT_EXPORT,
    }),
    ROLE_ANALYST: frozenset({
        PERMISSION_VENDOR_READ,
        PERMISSION_ASSESSMENT_MANAGE,
        PERMISSION_EVIDENCE_READ,
        PERMISSION_EVIDENCE_UPLOAD,
        PERMISSION_EVIDENCE_ANALYZE,
        PERMISSION_FINDING_MANAGE,
        PERMISSION_MONITORING_MANAGE,
    }),
    ROLE_VIEWER: frozenset({
        PERMISSION_VENDOR_READ,
        PERMISSION_EVIDENCE_READ,
        PERMISSION_REPORT_EXPORT,
    }),
}

@dataclass(frozen=True)
class Principal:
    subject: str
    display_name: str
    email: str
    role: str

    def __post_init__(self):
        if self.role not in VALID_ROLES:
            raise ValueError(
                f"Unsupported role: {self.role}. "
                f"Expected one of: {sorted(VALID_ROLES)}"
            )

def permissions_for_role(role: str) -> FrozenSet[str]:
    if role not in ROLE_PERMISSIONS:
        raise ValueError(
            f"Unsupported role: {role}. "
            f"Expected one of: {sorted(VALID_ROLES)}"
        )
    return ROLE_PERMISSIONS[role]

def can(principal: Principal, permission: str) -> bool:
    if permission not in ALL_PERMISSIONS:
        return False
    return permission in permissions_for_role(principal.role)

def require(principal: Principal, permission: str) -> None:
    if not can(principal, permission):
        raise PermissionError(
            f"{principal.role} does not have permission: {permission}"
        )
