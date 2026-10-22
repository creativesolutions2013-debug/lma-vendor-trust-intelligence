"""M4C-2B-2A: synthetic scoped report and unaudited-route denial tests."""
import ast
import csv
from dataclasses import replace
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest

from test_tenant_read_scope import ctx, update, NOW, ISSUER, TrustedSyntheticSource, rows
from src.assessment_evidence_access import AuthenticatedIdentity
from src.authz import Principal, ROLE_ADMIN, ROLE_VIEWER
from src.db import Engagement, EngagementAccessGrant, OrganizationMembership, Vendor
from src.production_route_policy import (
    LEGACY_PAGES, LEGACY_OPERATIONS, SCOPED_SERVICE_CAPABILITIES,
    classify_production_route,
)
from src.tenant_report_export import TenantReportService
from src.tenant_read_scope import ScopedCounts


def export(ctx):
    return TenantReportService(ctx.factory, identity_source=ctx.source).build()


def authorized_admin(ctx):
    # Global forged Admin is not sufficient; this changes the real DB membership
    # inside an isolated synthetic fixture to confirm the positive path.
    update(ctx, OrganizationMembership, 501, role=ROLE_ADMIN)


def test_active_analyst_cannot_export_despite_upstream_admin_role(ctx):
    assert ctx.identity.principal.role == ROLE_ADMIN
    assert export(ctx) is None


def test_current_member_with_report_permission_exports_only_granted_engagement(ctx):
    authorized_admin(ctx)
    result = export(ctx)
    assert result is not None
    assert len(result.rows) == 1
    row = result.rows[0]
    assert (row.vendor_id, row.engagement_id, row.assessments, row.evidence_items) == (11, 101, 1, 1)
    decoded = result.csv_bytes.decode("utf-8")
    reader = list(csv.reader(StringIO(decoded)))
    assert len(reader) == 2
    assert reader[1] == ["11", "Vendor A", "101", "A allowed service", "1", "1"]
    assert "hidden-sibling" not in decoded
    assert "B secret" not in decoded
    assert "vendors/11/evidence" not in decoded
    assert "risk_score" not in decoded and "storage_path" not in decoded
    assert "approval" not in decoded.lower()


def test_viewer_reports_are_scoped_to_own_organization(ctx):
    ctx.source.identity = AuthenticatedIdentity(
        Principal("reader-b", "B reader", "b@synthetic.invalid", ROLE_VIEWER),
        ISSUER, "lma-synthetic", "sid_b", 2,
        NOW - timedelta(minutes=1), NOW + timedelta(minutes=30),
    )
    result = export(ctx)
    assert result is not None
    assert [(x.vendor_id, x.engagement_id) for x in result.rows] == [(22, 201)]
    decoded = result.csv_bytes.decode("utf-8")
    assert "Vendor B" in decoded and "Vendor A" not in decoded


@pytest.mark.parametrize("which", ["membership", "grant"])
@pytest.mark.parametrize("change", ["revoked", "expired", "future"])
def test_revoked_and_stale_authority_returns_no_export(ctx, which, change):
    authorized_admin(ctx)
    kind, row_id = ((OrganizationMembership, 501) if which == "membership"
                    else (EngagementAccessGrant, 701))
    fields = ({"status": "revoked"} if change == "revoked"
              else {"expires_at": NOW - timedelta(seconds=1)} if change == "expired"
              else {"valid_from": NOW + timedelta(seconds=1)})
    update(ctx, kind, row_id, **fields)
    assert export(ctx) is None


def test_no_session_source_or_database_factory_denies(ctx):
    assert TenantReportService(ctx.factory).build() is None
    assert TenantReportService(None, identity_source=ctx.source).build() is None


def test_missing_engagement_grant_has_no_vendor_or_count_leak(ctx):
    authorized_admin(ctx)
    update(ctx, EngagementAccessGrant, 701, status="revoked")
    assert export(ctx) is None


def test_untrusted_spreadsheet_fields_are_neutralized_and_utf8_preserved(ctx):
    authorized_admin(ctx)
    update(ctx, Vendor, 11, display_name=" =HYPERLINK(\"https://bad.invalid\",\"click\")")
    update(ctx, Engagement, 101, service_name="@SUM(1,2), Åwesome service")
    result = export(ctx)
    assert result is not None
    data = list(csv.reader(StringIO(result.csv_bytes.decode("utf-8"))))
    assert data[1][1].startswith("' =HYPERLINK(")
    assert data[1][3] == "'@SUM(1,2), Åwesome service"


@pytest.mark.parametrize("prefix", ["=1+2", "+1+2", "-1+2", "@SUM(1)", "\t=1+2", "\r=1+2", "\n=1+2"])
def test_csv_formula_prefixes_always_quote_with_apostrophe(ctx, prefix):
    authorized_admin(ctx)
    update(ctx, Vendor, 11, display_name=prefix)
    result = export(ctx)
    assert result is not None
    table = list(csv.reader(StringIO(result.csv_bytes.decode("utf-8"))))
    assert table[1][1] == "'" + prefix


def test_grant_revocation_during_projection_denies_csv(ctx, monkeypatch):
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    original = service._reader._project
    first = [True]
    def revoked(*args, **kwargs):
        answer = original(*args, **kwargs)
        if first[0]:
            first[0] = False
            update(ctx, EngagementAccessGrant, 701, status="revoked")
        return answer
    monkeypatch.setattr(service._reader, "_project", revoked)
    assert service.build() is None


def test_identity_rotation_after_assembly_denies_csv(ctx, monkeypatch):
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    original = service._csv
    def changed(*args, **kwargs):
        data = original(*args, **kwargs)
        ctx.source.identity = replace(ctx.identity, session_id="sid_rotated")
        return data
    monkeypatch.setattr(service, "_csv", changed)
    assert service.build() is None


def test_session_expiry_after_assembly_denies_csv(ctx, monkeypatch):
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    original = service._csv
    def expired(*args, **kwargs):
        data = original(*args, **kwargs)
        ctx.clock[0] = ctx.identity.expires_at
        return data
    monkeypatch.setattr(service, "_csv", expired)
    assert service.build() is None


def test_outage_after_report_query_denies_with_no_diagnostics(ctx, monkeypatch, caplog):
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    secret = "private-database-connection-secret"
    def failed():
        raise RuntimeError(secret)
    original = service._csv
    def outage(*args, **kwargs):
        answer = original(*args, **kwargs)
        service._reader._sessions = failed
        return answer
    monkeypatch.setattr(service, "_csv", outage)
    assert service.build() is None
    assert secret not in caplog.text


def test_data_parent_reassignment_during_report_denies_stale_snapshot(ctx, monkeypatch):
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    original = service._data
    once = [True]
    def changed(*args, **kwargs):
        snapshot = original(*args, **kwargs)
        if once[0]:
            once[0] = False
            update(ctx, Engagement, 101, vendor_id=22)
        return snapshot
    monkeypatch.setattr(service, "_data", changed)
    assert service.build() is None


def test_production_contract_denies_all_legacy_pages_actions_and_unknowns():
    assert len(LEGACY_PAGES) >= 9
    for page in LEGACY_PAGES:
        for action in LEGACY_OPERATIONS:
            result = classify_production_route(page, action)
            assert result.allowed is False
            assert result.classification == "legacy-blocked"
    for page in SCOPED_SERVICE_CAPABILITIES:
        for action in ("read", "export"):
            decision = classify_production_route(page, action)
            assert decision.allowed is False
            assert decision.classification == "separate-verification-required"
    for page, action in (("new-unreviewed", "read"), ("Reports", ""), (None, "export"),
                         ("tenant.report.export", "approve"), (object(), "upload")):
        assert classify_production_route(page, action).allowed is False


def test_navigation_page_registry_matches_real_app_source_without_importing_app():
    app_file = Path(__file__).resolve().parents[1] / "app.py"
    source = ast.parse(app_file.read_text(encoding="utf-8"))
    found = set()
    for node in source.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PAGE_PERMISSIONS"
            for target in node.targets
        ):
            found = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    assert found == LEGACY_PAGES
