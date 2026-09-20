import pytest

from src.authz import (
    PERMISSION_ADMIN,
    PERMISSION_AUDIT_READ,
    PERMISSION_EVIDENCE_UPLOAD,
    PERMISSION_FINDING_MANAGE,
    PERMISSION_REPORT_EXPORT,
    PERMISSION_VENDOR_READ,
    PERMISSION_VENDOR_WRITE,
    Principal,
    ROLE_ADMIN,
    ROLE_ANALYST,
    ROLE_RISK_MANAGER,
    ROLE_VIEWER,
    can,
    permissions_for_role,
    require,
)

def principal(role):
    return Principal(
        subject="test-user",
        display_name="Test User",
        email="test@example.com",
        role=role,
    )

def test_admin_has_high_privilege_permissions():
    user = principal(ROLE_ADMIN)
    assert can(user, PERMISSION_ADMIN)
    assert can(user, PERMISSION_VENDOR_WRITE)
    assert can(user, PERMISSION_EVIDENCE_UPLOAD)

def test_risk_manager_can_manage_risk_but_not_administer_system():
    user = principal(ROLE_RISK_MANAGER)
    assert can(user, PERMISSION_VENDOR_WRITE)
    assert can(user, PERMISSION_FINDING_MANAGE)
    assert not can(user, PERMISSION_ADMIN)

def test_analyst_can_work_evidence_but_not_edit_vendor_master():
    user = principal(ROLE_ANALYST)
    assert can(user, PERMISSION_VENDOR_READ)
    assert can(user, PERMISSION_EVIDENCE_UPLOAD)
    assert can(user, PERMISSION_FINDING_MANAGE)
    assert not can(user, PERMISSION_VENDOR_WRITE)

def test_viewer_is_read_only_with_report_export():
    user = principal(ROLE_VIEWER)
    assert can(user, PERMISSION_VENDOR_READ)
    assert can(user, PERMISSION_REPORT_EXPORT)
    assert not can(user, PERMISSION_EVIDENCE_UPLOAD)
    assert not can(user, PERMISSION_VENDOR_WRITE)

def test_require_raises_for_denied_permission():
    with pytest.raises(PermissionError):
        require(principal(ROLE_VIEWER), PERMISSION_EVIDENCE_UPLOAD)

def test_unknown_role_is_rejected():
    with pytest.raises(ValueError, match="Unsupported role"):
        principal("Superuser")

def test_permissions_for_role_rejects_unknown_role():
    with pytest.raises(ValueError, match="Unsupported role"):
        permissions_for_role("Unknown")


def test_admin_and_risk_manager_can_read_audit_log():
    assert can(principal(ROLE_ADMIN), PERMISSION_AUDIT_READ)
    assert can(principal(ROLE_RISK_MANAGER), PERMISSION_AUDIT_READ)
    assert not can(principal(ROLE_ANALYST), PERMISSION_AUDIT_READ)
    assert not can(principal(ROLE_VIEWER), PERMISSION_AUDIT_READ)
