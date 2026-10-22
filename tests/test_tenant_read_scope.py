"""M4C-2B-1 synthetic tenant read security regressions; no app or live IdP."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import src.authz as authz
import src.tenant_read_scope as scoped
from src.assessment_evidence_access import AuthenticatedIdentity
from src.authz import Principal, ROLE_ADMIN, ROLE_ANALYST, ROLE_VIEWER
from src.db import (
    Assessment, Base, Engagement, EngagementAccessGrant, Evidence,
    Organization, OrganizationMembership, Vendor,
)
from src.tenant_read_scope import TenantReadService


NOW = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)
ISSUER = "https://id.synthetic.invalid"


class TrustedSyntheticSource:
    """Injected test-only verified-session stand-in; DTOs are not credentials."""
    def __init__(self, identity):
        self.identity = identity
        self.calls = 0

    def authenticated_identity(self):
        self.calls += 1
        return self.identity


def rows(factory):
    start, finish = NOW - timedelta(days=1), NOW + timedelta(days=1)
    with factory() as session:
        session.add_all([
            Organization(id=1, external_key="synthetic-a", name="Org A"),
            Organization(id=2, external_key="synthetic-b", name="Org B"),
        ])
        session.flush()
        session.add_all([
            Vendor(id=11, legal_name="A secret vendor", display_name="Vendor A", organization_id=1),
            Vendor(id=22, legal_name="B secret vendor", display_name="Vendor B", organization_id=2),
            Vendor(id=33, legal_name="Legacy", display_name="Legacy", organization_id=None),
        ])
        session.flush()
        session.add_all([
            Engagement(id=101, vendor_id=11, service_name="A allowed service"),
            Engagement(id=102, vendor_id=11, service_name="A ungranted sibling"),
            Engagement(id=201, vendor_id=22, service_name="B secret service"),
            Engagement(id=301, vendor_id=33, service_name="Legacy service"),
        ])
        session.flush()
        session.add_all([
            Assessment(id=1001, vendor_id=11, engagement_id=101, assessment_type="Allowed"),
            Assessment(id=1002, vendor_id=11, engagement_id=102, assessment_type="Hidden sibling"),
            Assessment(id=2001, vendor_id=22, engagement_id=201, assessment_type="Hidden org"),
            Assessment(id=3001, vendor_id=33, engagement_id=301, assessment_type="Legacy"),
            Assessment(id=4001, vendor_id=11, engagement_id=None, assessment_type="Unassigned"),
            Assessment(id=5001, vendor_id=22, engagement_id=101, assessment_type="Cross-parent"),
        ])
        session.flush()
        session.add_all([
            Evidence(id=9001, vendor_id=11, assessment_id=1001, document_type="SOC2",
                     document_name="allowed.txt", storage_path="vendors/11/evidence/allowed.txt"),
            Evidence(id=9002, vendor_id=11, assessment_id=1002, document_type="SOC2",
                     document_name="hidden-sibling.txt", storage_path="vendors/11/evidence/sibling.txt"),
            Evidence(id=9201, vendor_id=22, assessment_id=2001, document_type="SOC2",
                     document_name="hidden-org.txt", storage_path="vendors/22/evidence/org.txt"),
            Evidence(id=9301, vendor_id=33, assessment_id=3001, document_type="SOC2",
                     document_name="hidden-legacy.txt", storage_path="vendors/33/evidence/legacy.txt"),
            Evidence(id=9401, vendor_id=11, assessment_id=None, document_type="SOC2",
                     document_name="missing-parent.txt"),
            Evidence(id=9501, vendor_id=22, assessment_id=1001, document_type="SOC2",
                     document_name="wrong-vendor.txt"),
            Evidence(id=9601, vendor_id=22, assessment_id=5001, document_type="SOC2",
                     document_name="cross-parent.txt"),
            Evidence(id=9701, vendor_id=11, assessment_id=4001, document_type="SOC2",
                     document_name="missing-engagement.txt"),
        ])
        session.add_all([
            OrganizationMembership(id=501, organization_id=1, issuer=ISSUER,
                                   subject="reader-a", role=ROLE_ANALYST, status="active",
                                   valid_from=start, expires_at=finish),
            OrganizationMembership(id=601, organization_id=2, issuer=ISSUER,
                                   subject="reader-b", role=ROLE_VIEWER, status="active",
                                   valid_from=start, expires_at=finish),
        ])
        session.flush()
        session.add_all([
            EngagementAccessGrant(id=701, membership_id=501, engagement_id=101,
                                  status="active", valid_from=start, expires_at=finish),
            EngagementAccessGrant(id=801, membership_id=601, engagement_id=201,
                                  status="active", valid_from=start, expires_at=finish),
        ])
        session.commit()


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    rows(factory)
    clock = [NOW]
    monkeypatch.setattr(scoped, "_utc_now", lambda: clock[0])
    identity = AuthenticatedIdentity(
        Principal("reader-a", "A reader", "reader@synthetic.invalid", ROLE_ADMIN),
        ISSUER, "lma-synthetic", "sid_synthetic", 1,
        NOW - timedelta(minutes=1), NOW + timedelta(minutes=30),
    )
    source = TrustedSyntheticSource(identity)
    service = TenantReadService(factory, identity_source=source)
    try:
        yield SimpleNamespace(factory=factory, source=source, service=service,
                              identity=identity, clock=clock)
    finally:
        engine.dispose()


def update(ctx, model, row_id, **values):
    with ctx.factory() as db:
        obj = db.get(model, row_id)
        for k, v in values.items():
            setattr(obj, k, v)
        db.commit()


def test_exact_scoped_projection_and_counts_exclude_hidden_names_and_paths(ctx):
    assert [r.id for r in ctx.service.list_vendors()] == [11]
    assert [r.id for r in ctx.service.list_engagements()] == [101]
    assert [r.id for r in ctx.service.list_assessments()] == [1001]
    assert [r.id for r in ctx.service.list_evidence()] == [9001]
    assert ctx.service.visible_counts() == scoped.ScopedCounts(1, 1, 1, 1)
    assert ctx.service.get_vendor(11).display_name == "Vendor A"
    assert ctx.service.get_engagement(101).service_name == "A allowed service"
    assert ctx.service.get_assessment(1001).assessment_type == "Allowed"
    item = ctx.service.get_evidence(9001)
    assert item.document_name == "allowed.txt"
    assert not {"storage_path", "file_hash", "bytes", "approval_status", "risk_score"} & item.__dict__.keys()
    exported = repr((ctx.service.list_vendors(), ctx.service.list_engagements(),
                     ctx.service.list_assessments(), ctx.service.list_evidence()))
    for sensitive in ("B secret", "ungranted sibling", "hidden-sibling", "hidden-org",
                      "vendors/11/evidence", "A secret vendor"):
        assert sensitive not in exported


@pytest.mark.parametrize("type_name,id_value", [
    ("vendor", 22), ("vendor", 33), ("engagement", 102), ("engagement", 201),
    ("assessment", 1002), ("assessment", 2001), ("assessment", 3001),
    ("assessment", 4001), ("assessment", 5001),
    ("evidence", 9002), ("evidence", 9201), ("evidence", 9301),
    ("evidence", 9401), ("evidence", 9501), ("evidence", 9601), ("evidence", 9701),
    ("evidence", 9999),
])
def test_sibling_other_org_null_legacy_and_inconsistent_parents_all_look_absent(ctx, type_name, id_value):
    assert getattr(ctx.service, "get_" + type_name)(id_value) is None


@pytest.mark.parametrize("method,kwargs", [
    ("list_engagements", {"vendor_id": 22}),
    ("list_assessments", {"engagement_id": 102}),
    ("list_evidence", {"assessment_id": 1002}),
])
def test_caller_selected_parent_cannot_overcome_scope(ctx, method, kwargs):
    assert getattr(ctx.service, method)(**kwargs) == ()


@pytest.mark.parametrize("invalid", [0, -1, True, False, "11", 1.0, None, object()])
def test_malformed_exact_selectors_deny(ctx, invalid):
    assert ctx.service.get_vendor(invalid) is None
    assert ctx.service.get_evidence(invalid) is None


@pytest.mark.parametrize("invalid", [0, -1, True, "11", 11.0])
def test_malformed_optional_scope_filters_deny(ctx, invalid):
    assert ctx.service.list_engagements(vendor_id=invalid) == ()
    assert ctx.service.list_assessments(engagement_id=invalid) == ()
    assert ctx.service.list_evidence(assessment_id=invalid) == ()


@pytest.mark.parametrize("change", [
    {"issuer": "https://wrong.synthetic.invalid"}, {"organization_id": 2},
    {"session_id": ""}, {"audience": ""}, {"expires_at": NOW},
    {"issued_at": NOW + timedelta(minutes=1)},
    {"principal": Principal("forged", "X", "x@synthetic.invalid", ROLE_ADMIN)},
])
def test_forged_wrong_or_expired_session_does_not_list(ctx, change):
    ctx.source.identity = replace(ctx.identity, **change)
    assert ctx.service.list_vendors() == ()


@pytest.mark.parametrize("bad", [None, {}, {"subject": "reader-a", "role": "Admin"}, "synthetic-token"])
def test_no_trusted_identity_denies_and_suppresses_metadata(ctx, bad):
    ctx.source.identity = bad
    assert ctx.service.list_vendors() == ()
    assert ctx.service.visible_counts() == scoped.ScopedCounts(0, 0, 0, 0)


def test_missing_identity_source_and_missing_session_factory_deny(ctx):
    assert TenantReadService(ctx.factory).list_vendors() == ()
    assert TenantReadService(None, identity_source=ctx.source).list_vendors() == ()


def test_forged_admin_role_does_not_grant_permission(ctx, monkeypatch):
    monkeypatch.setitem(authz.ROLE_PERMISSIONS, ROLE_ANALYST, frozenset())
    assert ctx.identity.principal.role == ROLE_ADMIN
    assert ctx.service.list_vendors() == ()
    assert ctx.service.list_evidence() == ()


@pytest.mark.parametrize("model,row_id", [
    (OrganizationMembership, 501), (EngagementAccessGrant, 701),
])
@pytest.mark.parametrize("state", ["revoked", "expired", "future"])
def test_current_member_and_grant_required_each_call(ctx, model, row_id, state):
    assert ctx.service.get_evidence(9001) is not None
    changes = ({"status": "revoked"} if state == "revoked"
               else {"expires_at": NOW - timedelta(seconds=1)} if state == "expired"
               else {"valid_from": NOW + timedelta(seconds=1)})
    update(ctx, model, row_id, **changes)
    assert ctx.service.list_vendors() == ()
    assert ctx.service.list_evidence() == ()


def test_multiple_current_organization_memberships_denies(ctx):
    start, end = NOW - timedelta(days=1), NOW + timedelta(days=1)
    with ctx.factory() as db:
        db.add(OrganizationMembership(
            organization_id=2, issuer=ISSUER, subject="reader-a", role=ROLE_ADMIN,
            status="active", valid_from=start, expires_at=end,
        ))
        db.commit()
    assert ctx.service.list_vendors() == ()


def test_organization_membership_is_not_itself_an_engagement_grant(ctx):
    update(ctx, EngagementAccessGrant, 701, status="revoked")
    assert ctx.service.get_vendor(11) is None


def test_reader_of_second_organization_sees_only_own_scope(ctx):
    ctx.source.identity = AuthenticatedIdentity(
        Principal("reader-b", "Other reader", "b@synthetic.invalid", ROLE_VIEWER),
        ISSUER, "lma-synthetic", "sid_b", 2,
        NOW - timedelta(minutes=1), NOW + timedelta(minutes=30),
    )
    assert [x.id for x in ctx.service.list_vendors()] == [22]
    assert [x.id for x in ctx.service.list_engagements()] == [201]
    assert [x.id for x in ctx.service.list_assessments()] == [2001]
    assert [x.id for x in ctx.service.list_evidence()] == [9201]


def test_revocation_during_data_query_never_releases_previously_selected_rows(ctx, monkeypatch):
    original = ctx.service._project
    calls = [0]
    def revoke_after_first_read(*args, **kwargs):
        result = original(*args, **kwargs)
        calls[0] += 1
        if calls[0] == 1:
            update(ctx, EngagementAccessGrant, 701, status="revoked")
        return result
    monkeypatch.setattr(ctx.service, "_project", revoke_after_first_read)
    assert ctx.service.list_evidence() == ()


def test_expiry_during_data_query_denies(ctx, monkeypatch):
    original = ctx.service._project
    def slow(*args, **kwargs):
        result = original(*args, **kwargs)
        ctx.clock[0] = ctx.identity.expires_at
        return result
    monkeypatch.setattr(ctx.service, "_project", slow)
    assert ctx.service.list_vendors() == ()


def test_parent_fk_change_during_query_denies_stale_result(ctx, monkeypatch):
    original = ctx.service._project
    calls = [0]
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        calls[0] += 1
        if calls[0] == 1:
            update(ctx, Assessment, 1001, vendor_id=22)
        return result
    monkeypatch.setattr(ctx.service, "_project", mutate)
    assert ctx.service.list_evidence() == ()


def test_session_changes_during_query_deny(ctx, monkeypatch):
    original = ctx.service._project
    def rotate(*args, **kwargs):
        result = original(*args, **kwargs)
        ctx.source.identity = replace(ctx.identity, session_id="sid_new_session")
        return result
    monkeypatch.setattr(ctx.service, "_project", rotate)
    assert ctx.service.list_vendors() == ()


def test_source_and_database_outages_deny_without_leaking_errors(ctx, monkeypatch, caplog):
    secret = "private-tenant-database-secret"
    def fail():
        raise RuntimeError(secret)
    monkeypatch.setattr(ctx.source, "authenticated_identity", fail)
    assert ctx.service.list_vendors() == ()
    assert secret not in caplog.text
    monkeypatch.setattr(ctx.source, "authenticated_identity", lambda: ctx.identity)
    ctx.service._sessions = fail
    assert ctx.service.list_evidence() == ()
    assert secret not in caplog.text


def test_source_changes_at_final_post_io_check_denies(ctx, monkeypatch):
    original = ctx.source.authenticated_identity
    def replace_on_third():
        result = original()
        if ctx.source.calls == 3:
            ctx.source.identity = replace(ctx.identity, session_id="sid_rotated")
            return ctx.source.identity
        return result
    monkeypatch.setattr(ctx.source, "authenticated_identity", replace_on_third)
    assert ctx.service.list_vendors() == ()


def test_uncommitted_request_session_data_is_not_read_or_flushed(ctx):
    with ctx.factory() as request_db:
        request_db.add(Vendor(id=44, legal_name="Request secret", display_name="Request secret", organization_id=1))
        assert [x.id for x in ctx.service.list_vendors()] == [11]
        assert request_db.new
        request_db.rollback()


def test_membership_expiry_during_authority_database_read_denies(ctx):
    update(ctx, OrganizationMembership, 501, expires_at=NOW + timedelta(seconds=1))
    original = ctx.service._sessions
    def delayed_factory():
        session = original()
        ctx.clock[0] = NOW + timedelta(seconds=1)
        return session
    ctx.service._sessions = delayed_factory
    assert ctx.service.list_vendors() == ()


def test_revocation_during_final_projection_denies(ctx, monkeypatch):
    original = ctx.service._project
    calls = [0]
    def revoke_after_second_read(*args, **kwargs):
        result = original(*args, **kwargs)
        calls[0] += 1
        if calls[0] == 2:
            update(ctx, EngagementAccessGrant, 701, status="revoked")
        return result
    monkeypatch.setattr(ctx.service, "_project", revoke_after_second_read)
    assert ctx.service.list_evidence() == ()
