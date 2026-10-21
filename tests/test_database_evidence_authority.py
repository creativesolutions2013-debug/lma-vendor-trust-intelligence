"""Synthetic database authorization; no production login or evidence bytes.

Unit/local execution uses an isolated SQLite database. The PostgreSQL Actions job
uses its ephemeral service and a unique test schema, never shared public rows.
"""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import MetaData, UniqueConstraint, create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

import src.assessment_evidence_access as preflight
import src.authz as authz
import src.database_evidence_authority as database_authority
from src.assessment_evidence_access import AuthenticatedIdentity, EvidenceReadRequest, preflight_evidence_read
from src.authz import Principal, ROLE_ADMIN, ROLE_ANALYST, ROLE_VIEWER
from src.database_evidence_authority import DatabaseEvidenceAccessAuthority
from src.db import (
    Assessment, Base, Engagement, EngagementAccessGrant, Evidence, Organization,
    OrganizationMembership, Vendor,
)


NOW = datetime(2026, 10, 21, 23, 0, tzinfo=timezone.utc)
ISSUER = "https://identity.synthetic.invalid"


class SyntheticIdentitySource:
    """Server-injected test double, not request data or an implemented IdP."""
    def __init__(self, identity):
        self.identity = identity
        self.calls = 0

    def authenticated_identity(self):
        self.calls += 1
        return self.identity


@pytest.fixture(scope="module")
def isolated_engine():
    database_url = os.getenv("DATABASE_URL", "")
    postgres_ci = os.getenv("GITHUB_ACTIONS") == "true" and database_url.startswith("postgresql")
    if postgres_ci:
        # The CI service is synthetic. Never apply this schema setup to a local
        # environment merely because it happens to configure a PostgreSQL URL.
        schema = "m4c_authority_" + uuid4().hex
        root_engine = create_engine(database_url)
        with root_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = root_engine.execution_options(schema_translate_map={None: schema})
        try:
            Base.metadata.create_all(engine)
            yield engine
        finally:
            with root_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            root_engine.dispose()
    else:
        engine = create_engine("sqlite:///:memory:")
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(engine)
        try:
            yield engine
        finally:
            engine.dispose()


def seed_relationships(factory):
    start, finish = NOW - timedelta(days=1), NOW + timedelta(days=1)
    with factory() as session:
        session.add_all([
            Organization(id=1, name="Synthetic Organization A", external_key="synthetic-org-a"),
            Organization(id=2, name="Synthetic Organization B", external_key="synthetic-org-b"),
        ])
        session.flush()
        session.add_all([
            Vendor(id=11, legal_name="Synthetic A", display_name="Synthetic vendor A", organization_id=1),
            Vendor(id=22, legal_name="Synthetic B", display_name="Synthetic vendor B", organization_id=2),
            Vendor(id=33, legal_name="Synthetic Legacy", display_name="Synthetic legacy", organization_id=None),
        ])
        session.flush()
        session.add_all([
            Engagement(id=101, vendor_id=11, service_name="Synthetic service A"),
            Engagement(id=102, vendor_id=11, service_name="Synthetic service A sibling"),
            Engagement(id=201, vendor_id=22, service_name="Synthetic service B"),
            Engagement(id=301, vendor_id=33, service_name="Synthetic legacy service"),
        ])
        session.flush()
        session.add_all([
            Assessment(id=1001, vendor_id=11, engagement_id=101, assessment_type="Synthetic"),
            Assessment(id=1002, vendor_id=11, engagement_id=102, assessment_type="Synthetic"),
            Assessment(id=2001, vendor_id=22, engagement_id=201, assessment_type="Synthetic"),
            Assessment(id=3001, vendor_id=33, engagement_id=301, assessment_type="Synthetic legacy"),
            Assessment(id=4001, vendor_id=11, engagement_id=None, assessment_type="Synthetic legacy"),
            Assessment(id=5001, vendor_id=22, engagement_id=101, assessment_type="Synthetic inconsistent"),
        ])
        session.flush()
        session.add_all([
            Evidence(id=9001, vendor_id=11, assessment_id=1001, document_type="Synthetic", document_name="synthetic-a.txt", storage_path="vendors/11/evidence/synthetic_a.txt"),
            Evidence(id=9002, vendor_id=11, assessment_id=1002, document_type="Synthetic", document_name="synthetic-a-sibling.txt", storage_path="vendors/11/evidence/synthetic_sibling.txt"),
            Evidence(id=9201, vendor_id=22, assessment_id=2001, document_type="Synthetic", document_name="synthetic-b.txt", storage_path="vendors/22/evidence/synthetic_b.txt"),
            Evidence(id=9301, vendor_id=33, assessment_id=3001, document_type="Synthetic", document_name="synthetic-legacy.txt", storage_path="vendors/33/evidence/synthetic_legacy.txt"),
            Evidence(id=9401, vendor_id=11, assessment_id=None, document_type="Synthetic", document_name="synthetic-no-parent.txt", storage_path="vendors/11/evidence/synthetic_no_parent.txt"),
            Evidence(id=9501, vendor_id=22, assessment_id=1001, document_type="Synthetic", document_name="synthetic-cross-vendor.txt", storage_path="vendors/22/evidence/synthetic_cross.txt"),
            Evidence(id=9601, vendor_id=22, assessment_id=5001, document_type="Synthetic", document_name="synthetic-inconsistent-parent.txt", storage_path="vendors/22/evidence/synthetic_inconsistent.txt"),
            Evidence(id=9701, vendor_id=11, assessment_id=4001, document_type="Synthetic", document_name="synthetic-unlinked-assessment.txt", storage_path="vendors/11/evidence/synthetic_unlinked.txt"),
        ])
        session.add_all([
            OrganizationMembership(id=501, organization_id=1, issuer=ISSUER, subject="synthetic-reader", role=ROLE_ANALYST, status="active", valid_from=start, expires_at=finish),
            OrganizationMembership(id=601, organization_id=2, issuer=ISSUER, subject="synthetic-other-reader", role=ROLE_VIEWER, status="active", valid_from=start, expires_at=finish),
        ])
        session.flush()
        session.add_all([
            EngagementAccessGrant(id=701, membership_id=501, engagement_id=101, status="active", valid_from=start, expires_at=NOW + timedelta(minutes=10)),
            EngagementAccessGrant(id=801, membership_id=601, engagement_id=201, status="active", valid_from=start, expires_at=finish),
        ])
        session.commit()


@pytest.fixture
def context(isolated_engine, monkeypatch):
    monkeypatch.setattr(preflight, "_utc_now", lambda: NOW)
    monkeypatch.setattr(database_authority, "_utc_now", lambda: NOW)
    connection = isolated_engine.connect()
    transaction = connection.begin()
    if connection.dialect.name == "sqlite":
        # Ensure releasing session savepoints does not commit the fixture root.
        connection.exec_driver_sql("BEGIN")
    factory = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False,
                           join_transaction_mode="create_savepoint")
    seed_relationships(factory)
    identity = AuthenticatedIdentity(
        principal=Principal("synthetic-reader", "Synthetic reader", "reader@synthetic.invalid", ROLE_ADMIN),
        issuer=ISSUER, audience="lma-synthetic", session_id="synthetic-session-a", organization_id=1,
        issued_at=NOW - timedelta(minutes=30), expires_at=NOW + timedelta(hours=1),
    )
    source = SyntheticIdentitySource(identity)
    authority = DatabaseEvidenceAccessAuthority(factory, identity_source=source)
    request = EvidenceReadRequest(organization_id=1, engagement_id=101, vendor_id=11,
                                  assessment_id=1001, evidence_id=9001)
    try:
        yield SimpleNamespace(factory=factory, source=source, identity=identity, authority=authority, request=request)
    finally:
        transaction.rollback()
        connection.close()


def result(context, **changes):
    return preflight_evidence_read(replace(context.request, **changes), authority=context.authority)


def assert_denied(decision):
    assert decision.allowed is False
    assert decision.authorization is None
    assert decision.reason and "synthetic-b" not in decision.reason


def update_row(context, model, row_id, **changes):
    with context.factory() as session:
        row = session.get(model, row_id)
        for name, value in changes.items():
            setattr(row, name, value)
        session.commit()


def test_explicit_membership_and_engagement_grant_allow_only_metadata(context):
    decision = result(context)
    assert decision.allowed is True
    authorization = asdict(decision.authorization)
    assert authorization["organization_id"] == 1 and authorization["engagement_id"] == 101
    assert authorization["vendor_id"] == 11 and authorization["assessment_id"] == 1001
    assert authorization["evidence_id"] == 9001
    assert authorization["storage_key"] == "vendors/11/evidence/synthetic_a.txt"
    assert authorization["expires_at"] <= NOW + timedelta(minutes=10)
    assert not any(isinstance(value, bytes) for value in authorization.values())
    assert not {"content", "download_url", "file_path", "risk_score", "approval"} & authorization.keys()


def test_role_is_derived_from_current_membership_not_upstream_admin_claim(context):
    effective = context.authority.authenticated_identity()
    assert effective.principal.role == ROLE_ANALYST
    assert context.identity.principal.role == ROLE_ADMIN
    update_row(context, OrganizationMembership, 501, role=ROLE_VIEWER)
    assert context.authority.authenticated_identity().principal.role == ROLE_VIEWER


def test_global_role_and_vendor_selector_cannot_grant_missing_engagement(context):
    assert_denied(result(context, engagement_id=102, assessment_id=1002, evidence_id=9002))
    context.source.identity = replace(context.identity, principal=replace(context.identity.principal, role=ROLE_VIEWER))
    assert_denied(result(context, engagement_id=102, assessment_id=1002, evidence_id=9002))


@pytest.mark.parametrize("changes", [
    {"organization_id": 2, "engagement_id": 201, "vendor_id": 22, "assessment_id": 2001, "evidence_id": 9201},
    {"engagement_id": 102, "assessment_id": 1002, "evidence_id": 9002},
    {"assessment_id": 1002}, {"evidence_id": 9002}, {"vendor_id": 22}, {"engagement_id": 201},
])
def test_cross_organization_engagement_assessment_and_evidence_selectors_deny(context, changes):
    assert_denied(result(context, **changes))


@pytest.mark.parametrize("model,row_id", [(OrganizationMembership, 501), (EngagementAccessGrant, 701)])
@pytest.mark.parametrize("change", ["revoked", "expired", "not_yet_valid"])
def test_revoked_or_stale_membership_and_entitlement_are_rechecked(context, model, row_id, change):
    assert result(context).allowed
    changes = ({"status": "revoked"} if change == "revoked" else
               {"expires_at": NOW - timedelta(seconds=1)} if change == "expired" else
               {"valid_from": NOW + timedelta(seconds=1)})
    update_row(context, model, row_id, **changes)
    assert_denied(result(context))


def test_current_db_role_permission_is_required_even_with_admin_claim(context, monkeypatch):
    monkeypatch.setitem(authz.ROLE_PERMISSIONS, ROLE_ANALYST, frozenset())
    assert_denied(result(context))


@pytest.mark.parametrize("field,value", [("issuer", "https://other.synthetic.invalid"),
                                        ("principal", Principal("other-subject", "Synthetic other", "reader@synthetic.invalid", ROLE_ADMIN)),
                                        ("session_id", ""), ("audience", ""),
                                        ("expires_at", NOW), ("issued_at", NOW + timedelta(seconds=1))])
def test_unknown_identity_or_invalid_session_cannot_authorize(context, field, value):
    context.source.identity = replace(context.identity, **{field: value})
    assert_denied(result(context))


def test_changed_upstream_session_cannot_reuse_prior_effective_identity(context):
    effective = context.authority.authenticated_identity()
    context.source.identity = replace(context.identity, session_id="synthetic-new-session")
    assert context.authority.authorize_evidence_read(effective, context.request) is None


@pytest.mark.parametrize("fake", [None, {"verified": True, "subject": "synthetic-reader"}, "synthetic-static-token"])
def test_fake_identity_source_outputs_fail_closed(context, fake):
    context.source.identity = fake
    assert_denied(result(context))


def test_raw_identity_or_demo_principal_is_not_a_server_identity_source(context):
    for fake_source in (context.identity, context.identity.principal):
        authority = DatabaseEvidenceAccessAuthority(context.factory, identity_source=fake_source)
        assert_denied(preflight_evidence_read(context.request, authority=authority))
    assert_denied(preflight_evidence_read(context.request,
                                        authority=DatabaseEvidenceAccessAuthority(context.factory)))


@pytest.mark.parametrize("changes", [
    {"vendor_id": 33, "engagement_id": 301, "assessment_id": 3001, "evidence_id": 9301},
    {"assessment_id": 4001, "evidence_id": 9701},
    {"evidence_id": 9401},
    {"vendor_id": 22, "evidence_id": 9501},
    {"vendor_id": 22, "assessment_id": 5001, "evidence_id": 9601},
])
def test_legacy_null_and_cross_fk_links_are_never_inferred(context, changes):
    assert_denied(result(context, **changes))


@pytest.mark.parametrize("key", [None, "", "/tmp/synthetic.txt", "vendors/22/evidence/other.txt",
                               "vendors/11/evidence/../../outside.txt", "vendors/11/evidence/%2e%2e.txt"])
def test_missing_or_unsafe_storage_metadata_does_not_authorize(context, key):
    update_row(context, Evidence, 9001, storage_path=key)
    assert_denied(result(context))


def test_hidden_and_nonexistent_evidence_have_same_public_denial(context):
    hidden = result(context, evidence_id=9201)
    missing = result(context, evidence_id=999999)
    assert_denied(hidden)
    assert_denied(missing)
    assert hidden == missing


def test_database_reads_do_not_flush_pending_writes_or_access_file_bytes(context, monkeypatch):
    import pathlib
    import src.storage as storage

    def forbidden(*args, **kwargs):
        raise AssertionError("Authorization must not read/write evidence bytes or mutate governed decisions.")

    for method in ("save", "exists", "delete"):
        monkeypatch.setattr(storage.LocalEvidenceStorage, method, forbidden)
    monkeypatch.setattr(pathlib.Path, "read_bytes", forbidden)
    writes = []
    bind = context.factory.kw["bind"]
    def capture_sql(connection, cursor, statement, parameters, sql_context, executemany):
        verb = statement.lstrip().split(None, 1)[0].upper()
        if verb in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(verb)
    event.listen(bind, "before_cursor_execute", capture_sql)
    try:
        def pending_factory():
            session = context.factory()
            session.add(Vendor(id=99999, legal_name="Synthetic pending", display_name="Must never be flushed"))
            return session
        authority = DatabaseEvidenceAccessAuthority(pending_factory, identity_source=context.source)
        assert preflight_evidence_read(context.request, authority=authority).allowed is True
    finally:
        event.remove(bind, "before_cursor_execute", capture_sql)
    assert writes == []
    with context.factory() as session:
        assert session.get(Vendor, 99999) is None
        assert session.scalar(select(Vendor.organization_id).where(Vendor.id == 33)) is None
        assert session.scalar(select(Assessment.engagement_id).where(Assessment.id == 4001)) is None


@pytest.mark.parametrize("model,row_id,changes", [
    (Vendor, 11, {"organization_id": None}),
    (Vendor, 11, {"organization_id": 2}),
    (Engagement, 101, {"vendor_id": 22}),
    (Assessment, 1001, {"engagement_id": None}),
    (Assessment, 1001, {"engagement_id": 102}),
    (Assessment, 1001, {"vendor_id": 22}),
    (Evidence, 9001, {"assessment_id": None}),
    (Evidence, 9001, {"assessment_id": 1002}),
    (Evidence, 9001, {"vendor_id": 22}),
])
def test_granted_target_is_rejected_when_authoritative_chain_changes(context, model, row_id, changes):
    # Start from an actual authorized read so absence of an entitlement cannot
    # mask a missing/crossed parent relationship in these regressions.
    assert result(context).allowed
    update_row(context, model, row_id, **changes)
    assert_denied(result(context))


def test_advancing_server_clock_accepts_freshly_issued_database_metadata(context, monkeypatch):
    tick = iter([NOW, NOW + timedelta(seconds=1), NOW + timedelta(milliseconds=1500), NOW + timedelta(seconds=3)])
    clock = lambda: next(tick, NOW + timedelta(seconds=4))
    monkeypatch.setattr(preflight, "_utc_now", clock)
    monkeypatch.setattr(database_authority, "_utc_now", clock)
    # The grant is issued after the first preflight timestamp. Its validity must
    # be checked at the actual current time after database authorization returns.
    assert result(context).allowed is True


def test_identity_expiring_during_database_authorization_cannot_allow_metadata(context, monkeypatch):
    context.source.identity = replace(context.identity, expires_at=NOW + timedelta(seconds=1))
    tick = iter([NOW, NOW + timedelta(milliseconds=200), NOW + timedelta(milliseconds=500), NOW + timedelta(seconds=2)])
    clock = lambda: next(tick, NOW + timedelta(seconds=3))
    monkeypatch.setattr(preflight, "_utc_now", clock)
    monkeypatch.setattr(database_authority, "_utc_now", clock)
    assert_denied(result(context))


def test_upstream_provider_error_does_not_expose_identity_or_exception_metadata(context):
    class BrokenSource:
        def authenticated_identity(self):
            raise RuntimeError("SYNTHETIC_SECRET_DO_NOT_EXPOSE")
    authority = DatabaseEvidenceAccessAuthority(context.factory, identity_source=BrokenSource())
    decision = preflight_evidence_read(context.request, authority=authority)
    assert_denied(decision)
    assert "SYNTHETIC_SECRET" not in repr(decision)


@pytest.mark.parametrize("kind", ["membership", "entitlement"])
def test_ambiguous_database_rows_fail_closed_even_if_unique_constraints_are_missing(context, kind):
    # Deliberately corrupted, isolated SQLite schema: prove the resolver does not
    # rely solely on the new schema's uniqueness constraints or ORM deduplication.
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        copy = table.to_metadata(metadata)
        if table.name in {"organization_memberships", "engagement_access_grants"}:
            for constraint in tuple(copy.constraints):
                if isinstance(constraint, UniqueConstraint):
                    copy.constraints.remove(constraint)
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    try:
        seed_relationships(factory)
        with factory() as session:
            if kind == "membership":
                session.add(OrganizationMembership(
                    id=502, organization_id=1, issuer=ISSUER, subject="synthetic-reader", role=ROLE_ADMIN,
                    status="active", valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1),
                ))
            else:
                session.add(EngagementAccessGrant(
                    id=702, membership_id=501, engagement_id=101, status="active",
                    valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1),
                ))
            session.commit()
        authority = DatabaseEvidenceAccessAuthority(factory, identity_source=context.source)
        assert_denied(preflight_evidence_read(context.request, authority=authority))
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind", ["membership", "role"])
def test_authorization_rechecks_membership_and_role_after_identity_resolution(context, monkeypatch, kind):
    effective = context.authority.authenticated_identity()
    assert effective is not None
    if kind == "membership":
        update_row(context, OrganizationMembership, 501, status="revoked")
    else:
        update_row(context, OrganizationMembership, 501, role=ROLE_VIEWER)
        monkeypatch.setitem(authz.ROLE_PERMISSIONS, ROLE_VIEWER, frozenset())
    assert context.authority.authorize_evidence_read(effective, context.request) is None
