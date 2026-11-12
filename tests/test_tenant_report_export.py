"""M4C-2B-2A: synthetic scoped report and unaudited-route denial tests."""
import ast
import csv
from dataclasses import replace
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest

from test_tenant_read_scope import ctx, postgres_ctx, update, NOW, ISSUER, TrustedSyntheticSource, rows
from test_database_evidence_authority import isolated_engine as synthetic_isolated_engine
from src.assessment_evidence_access import AuthenticatedIdentity
from src.authz import Principal, ROLE_ADMIN, ROLE_VIEWER
from src.db import Assessment, Engagement, EngagementAccessGrant, Evidence, OrganizationMembership, Vendor
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
    original = service._data
    first = [True]
    def revoked(*args, **kwargs):
        answer = original(*args, **kwargs)
        if first[0]:
            first[0] = False
            update(ctx, EngagementAccessGrant, 701, status="revoked")
        return answer
    monkeypatch.setattr(service, "_data", revoked)
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
        # The already-open transaction must fail closed on its final SQL
        # authority check, rather than relying on a new session factory.
        monkeypatch.setattr(service._reader, "_scope", lambda *args, **kwargs: failed())
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


def test_direct_isolated_postgresql_scoped_metadata_and_export(
        synthetic_isolated_engine, monkeypatch):
    # The imported fixture creates an isolated temporary schema *only* in
    # GitHub's synthetic PostgreSQL service, never a customer database.
    if synthetic_isolated_engine.dialect.name != "postgresql":
        pytest.skip("Direct PostgreSQL exercise runs in GitHub Actions only")
    from sqlalchemy.orm import sessionmaker
    import src.tenant_read_scope as tenant_scope
    from src.tenant_read_scope import TenantReadService

    factory = sessionmaker(bind=synthetic_isolated_engine,
                           autoflush=False, expire_on_commit=False)
    rows(factory)
    with factory() as db:
        db.get(OrganizationMembership, 501).role = ROLE_ADMIN
        db.commit()
    monkeypatch.setattr(tenant_scope, "_utc_now", lambda: NOW)
    identity = AuthenticatedIdentity(
        Principal("reader-a", "Synthetic reader", "synthetic@invalid.test", ROLE_ADMIN),
        ISSUER, "lma-synthetic", "sid_postgresql_synthetic", 1,
        NOW - timedelta(minutes=1), NOW + timedelta(minutes=30),
    )
    source = TrustedSyntheticSource(identity)
    service = TenantReadService(factory, identity_source=source)
    assert [x.id for x in service.list_vendors()] == [11]
    assert [x.id for x in service.list_engagements()] == [101]
    assert [x.id for x in service.list_assessments()] == [1001]
    assert [x.id for x in service.list_evidence()] == [9001]
    assert service.get_evidence(9002) is None
    assert service.get_evidence(9201) is None
    assert service.visible_counts() == ScopedCounts(1, 1, 1, 1)
    report_service = TenantReportService(factory, identity_source=source)
    before = report_service.build()
    assert before is not None and len(before.rows) == 1
    assert before.rows[0].evidence_items == 1
    with factory() as db:
        db.get(EngagementAccessGrant, 701).status = "revoked"
        db.commit()
    assert service.list_evidence() == ()
    assert report_service.build() is None


def test_ownership_changed_while_csv_is_built_denies_stale_export(ctx, monkeypatch):
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    original = service._csv
    def changed_after_queries(*args, **kwargs):
        content = original(*args, **kwargs)
        update(ctx, Engagement, 101, vendor_id=22)
        return content
    monkeypatch.setattr(service, "_csv", changed_after_queries)
    assert service.build() is None


def test_grant_revoked_while_csv_is_built_denies_export(ctx, monkeypatch):
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    original = service._csv
    def revoked_after_queries(*args, **kwargs):
        content = original(*args, **kwargs)
        update(ctx, EngagementAccessGrant, 701, status="revoked")
        return content
    monkeypatch.setattr(service, "_csv", revoked_after_queries)
    assert service.build() is None


@pytest.mark.parametrize("change", [
    "member_revoke", "grant_revoke", "role", "vendor_org", "engagement_parent",
    "assessment_parent", "evidence_parent", "member_expiry", "grant_expiry",
    "session_expiry", "rotation", "unavailable",
])
def test_final_identity_lookup_cannot_release_stale_export(ctx, monkeypatch, change):
    """Original final-window bug: the CSV exists before the blocking lookup.

    SQLite's shared synthetic connection permits this deliberate internal
    mutation injection. Physical PostgreSQL connections below separately prove
    that external writers actually serialize through the issuance boundary.
    """
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    prepared, mutated = [False], [False]
    original_csv = service._csv
    def csv_ready(*args, **kwargs):
        result = original_csv(*args, **kwargs)
        prepared[0] = True
        return result
    def final_identity():
        if prepared[0] and not mutated[0]:
            mutated[0] = True
            mutations = {
                "member_revoke": (OrganizationMembership, 501, {"status": "revoked"}),
                "grant_revoke": (EngagementAccessGrant, 701, {"status": "revoked"}),
                "role": (OrganizationMembership, 501, {"role": ROLE_VIEWER}),
                "vendor_org": (Vendor, 11, {"organization_id": 2}),
                "engagement_parent": (Engagement, 101, {"vendor_id": 22}),
                "assessment_parent": (Assessment, 1001, {"engagement_id": 102}),
                "evidence_parent": (Evidence, 9001, {"assessment_id": 1002}),
            }
            if change in mutations:
                model, identifier, values = mutations[change]
                update(ctx, model, identifier, **values)
            elif change in ("member_expiry", "grant_expiry"):
                model, identifier = ((OrganizationMembership, 501) if change == "member_expiry"
                                     else (EngagementAccessGrant, 701))
                update(ctx, model, identifier, expires_at=NOW + timedelta(seconds=1))
                ctx.clock[0] = NOW + timedelta(seconds=1)
            elif change == "session_expiry":
                ctx.clock[0] = ctx.identity.expires_at
            elif change == "rotation":
                ctx.source.identity = replace(ctx.identity, session_id="sid_final_export_rotation")
            else:
                ctx.source.identity = None
        return ctx.source.identity
    monkeypatch.setattr(service, "_csv", csv_ready)
    monkeypatch.setattr(ctx.source, "authenticated_identity", final_identity)
    assert service.build() is None
    assert prepared[0] and mutated[0], "The final identity I/O must be exercised after CSV construction"


def test_export_aggregates_all_scoped_records_beyond_list_page_limit(ctx):
    authorized_admin(ctx)
    with ctx.factory() as database:
        database.add_all([
            Assessment(id=20000 + i, vendor_id=11, engagement_id=101, assessment_type="Synthetic count")
            for i in range(130)
        ])
        database.flush()
        database.add_all([
            Evidence(id=30000 + i * 2 + j, vendor_id=11, assessment_id=20000 + i,
                     document_type="Synthetic", document_name=f"synthetic-count-{i}-{j}.txt")
            for i in range(130) for j in range(2)
        ])
        database.commit()
    result = export(ctx)
    assert result is not None
    assert len(result.rows) == 1
    assert (result.rows[0].assessments, result.rows[0].evidence_items) == (131, 261)
    assert "synthetic-count" not in result.csv_bytes.decode("utf-8")


def test_failed_transaction_commit_discards_already_constructed_csv(ctx, monkeypatch, caplog):
    from sqlalchemy import event
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    prepared = [False]
    original_csv = service._csv
    def csv_ready(*args, **kwargs):
        content = original_csv(*args, **kwargs)
        prepared[0] = True
        return content
    def failed_commit(session):
        raise RuntimeError("synthetic-private-export-commit-diagnostic")
    monkeypatch.setattr(service, "_csv", csv_ready)
    event.listen(ctx.factory.class_, "before_commit", failed_commit)
    try:
        assert service.build() is None
    finally:
        event.remove(ctx.factory.class_, "before_commit", failed_commit)
    assert prepared[0], "Constructed CSV must not be issued before successful transaction completion"
    assert "synthetic-private-export-commit-diagnostic" not in caplog.text


def test_export_row_bound_rejects_overflow_instead_of_releasing_partial_report(ctx):
    authorized_admin(ctx)
    with ctx.factory() as database:
        database.add_all([Engagement(id=2000 + i, vendor_id=11, service_name=f"Synthetic service {i}")
                          for i in range(200)])
        database.flush()
        database.add_all([
            EngagementAccessGrant(id=2000 + i, membership_id=501, engagement_id=2000 + i,
                                  status="active", valid_from=NOW - timedelta(days=1),
                                  expires_at=NOW + timedelta(days=1))
            for i in range(199)
        ])
        database.commit()
    result = export(ctx)
    assert result is not None and len(result.rows) == 200
    with ctx.factory() as database:
        database.add(EngagementAccessGrant(id=2199, membership_id=501, engagement_id=2199,
                                          status="active", valid_from=NOW - timedelta(days=1),
                                          expires_at=NOW + timedelta(days=1)))
        database.commit()
    assert export(ctx) is None


@pytest.mark.parametrize("mutation", ["member", "grant", "vendor", "engagement", "assessment", "evidence"])
def test_postgres_export_locks_authority_and_exact_parents_through_issuance(postgres_ctx, monkeypatch, mutation):
    """Real two-connection UPDATE attempts cannot race the prepared export."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import text, update as sql_update
    from sqlalchemy.exc import OperationalError
    ctx = postgres_ctx
    authorized_admin(ctx)
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    at_final, release = Event(), Event()
    model, identifier, values = {
        "member": (OrganizationMembership, 501, {"status": "revoked"}),
        "grant": (EngagementAccessGrant, 701, {"status": "revoked"}),
        "vendor": (Vendor, 11, {"organization_id": 2}),
        "engagement": (Engagement, 101, {"vendor_id": 22}),
        "assessment": (Assessment, 1001, {"engagement_id": 102}),
        "evidence": (Evidence, 9001, {"assessment_id": 1002}),
    }[mutation]
    original_identity = ctx.source.authenticated_identity
    def identity():
        result = original_identity()
        if ctx.source.calls == 2:
            at_final.set()
            if not release.wait(10):
                raise RuntimeError("Synthetic export coordination timed out")
        return result
    monkeypatch.setattr(ctx.source, "authenticated_identity", identity)
    def concurrent_writer():
        with ctx.factory() as database:
            database.execute(text("SET LOCAL lock_timeout = '500ms'"))
            with pytest.raises(OperationalError) as error:
                database.execute(sql_update(model).where(model.id == identifier).values(**values))
            assert getattr(error.value.orig, "sqlstate", None) == "55P03"
            database.rollback()
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(service.build)
        try:
            assert at_final.wait(10), "Prepared CSV must reach final session check under SQL locks"
            executor.submit(concurrent_writer).result(timeout=10)
        finally:
            release.set()
        result = pending.result(timeout=10)
    assert result is not None
    assert [(row.vendor_id, row.engagement_id, row.assessments, row.evidence_items)
            for row in result.rows] == [(11, 101, 1, 1)]
    # After the defined issuance boundary the writer can commit. Each new
    # request must independently authorize and cannot release the stale report.
    with ctx.factory() as database:
        database.execute(sql_update(model).where(model.id == identifier).values(**values))
        database.commit()
    next_result = service.build()
    if mutation in ("assessment", "evidence"):
        # Moving a child out of scope changes only its new aggregate; it does
        # not revoke the parent engagement or justify a global empty fallback.
        assert next_result is not None
        assert next_result.rows[0].evidence_items == 0
        assert next_result.rows[0].assessments == (0 if mutation == "assessment" else 1)
    else:
        assert next_result is None


@pytest.mark.parametrize("change", ["member_expiry", "grant_expiry", "session_expiry", "rotation", "unavailable"])
def test_postgres_export_discards_csv_when_final_session_lookup_changes_authority(postgres_ctx, monkeypatch, change):
    ctx = postgres_ctx
    authorized_admin(ctx)
    if change == "member_expiry":
        update(ctx, OrganizationMembership, 501, expires_at=NOW + timedelta(seconds=1))
    elif change == "grant_expiry":
        update(ctx, EngagementAccessGrant, 701, expires_at=NOW + timedelta(seconds=1))
    service = TenantReportService(ctx.factory, identity_source=ctx.source)
    original_identity = ctx.source.authenticated_identity
    def identity():
        value = original_identity()
        if ctx.source.calls == 2:
            if change == "rotation":
                ctx.source.identity = replace(ctx.identity, session_id="sid_pg_final_export_rotation")
                return ctx.source.identity
            if change == "unavailable":
                return None
            ctx.clock[0] = ctx.identity.expires_at if change == "session_expiry" else NOW + timedelta(seconds=1)
        return value
    monkeypatch.setattr(ctx.source, "authenticated_identity", identity)
    assert service.build() is None
    assert ctx.source.calls == 2
