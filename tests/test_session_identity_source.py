"""Synthetic signed code flow -> server session -> membership -> metadata access."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

import src.assessment_evidence_access as preflight
import src.database_evidence_authority as authority_module
from src.assessment_evidence_access import EvidenceReadRequest, preflight_evidence_read
from src.authz import ROLE_ANALYST, ROLE_VIEWER
from src.database_evidence_authority import DatabaseEvidenceAccessAuthority
from src.db import Assessment, Base, Engagement, EngagementAccessGrant, Evidence, Organization, OrganizationMembership, Vendor
from src.oidc_login import IDTokenVerifier, InMemoryLoginTransactions, LoginService, ProviderConfig
from src.server_sessions import InMemorySessionStore, SessionManager, VerifiedSubject
from src.session_identity_source import SessionIdentitySource


NOW = datetime(2026, 10, 21, 23, 0, tzinfo=timezone.utc)
ISSUER = "https://session.synthetic.invalid"


@pytest.fixture(scope="module")
def signing_key():
    return RSAKey.generate_key(2048, {"kid": "synthetic-session-key", "alg": "RS256", "use": "sig"})


@pytest.fixture(scope="module")
def isolated_engine():
    database_url = os.getenv("DATABASE_URL", "")
    if os.getenv("GITHUB_ACTIONS") == "true" and database_url.startswith("postgresql"):
        # Only Actions' ephemeral synthetic service may run this PostgreSQL
        # variant. Nothing reads, modifies or migrates public/customer rows.
        schema = "m4c_session_" + uuid4().hex
        root = create_engine(database_url)
        with root.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = root.execution_options(schema_translate_map={None: schema})
        try:
            Base.metadata.create_all(engine)
            yield engine
        finally:
            with root.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            root.dispose()
    else:
        engine = create_engine("sqlite:///:memory:")
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(engine)
        try:
            yield engine
        finally:
            engine.dispose()


def synthetic_code_flow_session(sessions, clock, key):
    config = ProviderConfig(ISSUER, "synthetic-client", ISSUER + "/authorize", ISSUER + "/token",
                            ISSUER + "/jwks", "https://application.synthetic.invalid/oidc/callback")
    class SyntheticProvider:
        """Local exchange double validates exact binding and PKCE; never HTTP."""
        def exchange_code(self, *, token_endpoint, client_id, redirect_uri, code, code_verifier):
            assert (token_endpoint, client_id, redirect_uri, code) == (
                config.token_endpoint, config.client_id, config.redirect_uri, "synthetic-code")
            assert parameters["code_challenge_method"] == ["S256"]
            assert create_s256_code_challenge(code_verifier) == parameters["code_challenge"][0]
            token = jwt.encode({"alg": "RS256", "kid": "synthetic-session-key"}, {
                "iss": ISSUER, "sub": "reader", "aud": config.client_id,
                "iat": int(clock[0].timestamp()), "exp": int(clock[0].timestamp()) + 300,
                "nonce": parameters["nonce"][0],
                # Even signed, these claims confer no role or organization.
                "role": "Admin", "org_id": 2, "groups": ["owners"],
                "email": "other-reader@synthetic.invalid",
            }, key)
            return {"id_token": token}
    flow = LoginService(config, IDTokenVerifier(config, {"keys": [key.as_dict(private=False)]}),
                        InMemoryLoginTransactions(), sessions, SyntheticProvider(), clock=lambda: clock[0])
    start = flow.begin()
    parameters = parse_qs(urlsplit(start.authorization_url).query)
    return flow.finish(state=parameters["state"][0], code="synthetic-code", issuer=ISSUER,
                       redirect_uri=config.redirect_uri, browser_binding=start.browser_binding)


@pytest.fixture
def context(monkeypatch, isolated_engine, signing_key):
    connection = isolated_engine.connect()
    transaction = connection.begin()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN")
    factory = sessionmaker(bind=connection, expire_on_commit=False, autoflush=False,
                           join_transaction_mode="create_savepoint")
    start, end = NOW - timedelta(days=1), NOW + timedelta(days=1)
    with factory() as database:
        database.add_all([Organization(id=i, name=f"Synthetic {i}", external_key=f"synthetic-{i}") for i in (1, 2)])
        database.flush()
        database.add_all([Vendor(id=i, legal_name=f"Synthetic {i}", display_name=f"Synthetic {i}", organization_id=i) for i in (1, 2)])
        database.flush()
        database.add_all([Engagement(id=i, vendor_id=v, service_name=f"Synthetic {i}") for i, v in ((11, 1), (12, 1), (21, 2))])
        database.flush()
        database.add_all([Assessment(id=i, vendor_id=v, engagement_id=e, assessment_type="Synthetic") for i, v, e in ((111, 1, 11), (112, 1, 12), (121, 2, 21))])
        database.flush()
        database.add_all([Evidence(id=i, vendor_id=v, assessment_id=a, document_type="Synthetic", document_name=f"synthetic-{i}.txt", storage_path=f"vendors/{v}/evidence/synthetic_{i}.txt") for i, v, a in ((1111, 1, 111), (1112, 1, 112), (1121, 2, 121))])
        database.add_all([
            OrganizationMembership(id=1, organization_id=1, issuer=ISSUER, subject="reader", role=ROLE_ANALYST, status="active", valid_from=start, expires_at=end),
            OrganizationMembership(id=2, organization_id=2, issuer=ISSUER, subject="other-reader", role=ROLE_VIEWER, status="active", valid_from=start, expires_at=end),
        ])
        database.flush()
        database.add_all([EngagementAccessGrant(id=i, membership_id=m, engagement_id=e, status="active", valid_from=start, expires_at=end) for i, m, e in ((1, 1, 11), (2, 2, 21))])
        database.commit()
    clock = [NOW]
    sessions = SessionManager(InMemorySessionStore(), clock=lambda: clock[0], idle_seconds=30, absolute_seconds=90)
    handle = synthetic_code_flow_session(sessions, clock, signing_key)
    source = SessionIdentitySource(sessions, handle, factory, clock=lambda: clock[0])
    authority = DatabaseEvidenceAccessAuthority(factory, identity_source=source)
    monkeypatch.setattr(preflight, "_utc_now", lambda: clock[0])
    monkeypatch.setattr(authority_module, "_utc_now", lambda: clock[0])
    try:
        yield factory, clock, sessions, handle, source, authority
    finally:
        transaction.rollback()
        connection.close()


REQUEST = EvidenceReadRequest(1, 11, 1, 111, 1111)


def test_session_and_current_membership_supply_org_but_database_supplies_role(context):
    _, _, sessions, handle, source, authority = context
    identity = source.authenticated_identity()
    assert identity.organization_id == 1 and identity.principal.role == ROLE_VIEWER
    assert identity.session_id != handle
    assert authority.authenticated_identity().principal.role == ROLE_ANALYST
    assert preflight_evidence_read(REQUEST, authority=authority).allowed
    assert sessions.authenticate(identity.session_id) is None


@pytest.mark.parametrize("read_request", [replace(REQUEST, organization_id=2), EvidenceReadRequest(2, 21, 2, 121, 1121),
                                     EvidenceReadRequest(1, 12, 1, 112, 1112)])
def test_session_does_not_authorize_other_org_or_sibling_engagement(context, read_request):
    assert not preflight_evidence_read(read_request, authority=context[-1]).allowed


@pytest.mark.parametrize("change", [{"status": "revoked"}, {"expires_at": NOW}, {"valid_from": NOW + timedelta(seconds=1)},
                                    {"subject": "not-reader"}, {"issuer": "https://other.synthetic.invalid"}])
def test_changed_membership_invalidates_source(context, change):
    factory, _, _, _, source, authority = context
    with factory() as database:
        row = database.get(OrganizationMembership, 1)
        for key, value in change.items():
            setattr(row, key, value)
        database.commit()
    assert source.authenticated_identity() is None
    assert not preflight_evidence_read(REQUEST, authority=authority).allowed


def test_ambiguous_current_memberships_do_not_choose_an_organization(context):
    factory, _, _, _, source, _ = context
    with factory() as database:
        database.add(OrganizationMembership(id=3, organization_id=2, issuer=ISSUER, subject="reader", role=ROLE_ANALYST,
                     status="active", valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=1)))
        database.commit()
    assert source.authenticated_identity() is None


def test_revoked_grant_denies_without_revoking_identity(context):
    factory, _, _, _, source, authority = context
    with factory() as database:
        database.get(EngagementAccessGrant, 1).status = "revoked"
        database.commit()
    assert source.authenticated_identity() is not None
    assert not preflight_evidence_read(REQUEST, authority=authority).allowed


@pytest.mark.parametrize("mutation", ["revoke", "expire", "rotate"])
def test_session_lifecycle_invalidates_adapter_and_preflight(context, mutation):
    _, clock, sessions, handle, source, authority = context
    if mutation == "expire":
        clock[0] += timedelta(seconds=30)
    elif mutation == "rotate":
        assert sessions.rotate(handle)
    else:
        sessions.revoke(handle)
    assert source.authenticated_identity() is None
    assert not preflight_evidence_read(REQUEST, authority=authority).allowed


def test_session_revoked_during_membership_lookup_denies(context):
    factory, _, sessions, handle, source, _ = context
    engine = factory.kw["bind"]
    @event.listens_for(engine, "after_cursor_execute")
    def revoke_after_query(connection, cursor, statement, params, execution_context, executemany):
        if "organization_memberships" in statement:
            sessions.revoke(handle)
    assert source.authenticated_identity() is None


@pytest.mark.parametrize("expiry", ["session", "membership"])
def test_expiry_during_database_lookup_denies(context, expiry):
    factory, clock, _, _, source, _ = context
    if expiry == "membership":
        with factory() as database:
            database.get(OrganizationMembership, 1).expires_at = NOW + timedelta(seconds=1)
            database.commit()
    @event.listens_for(factory.kw["bind"], "after_cursor_execute")
    def advance_clock(connection, cursor, statement, params, execution_context, executemany):
        if "organization_memberships" in statement:
            clock[0] = NOW + timedelta(seconds=31 if expiry == "session" else 1)
    assert source.authenticated_identity() is None


def test_membership_lookup_does_not_flush_pending_database_writes(context):
    factory, clock, sessions, handle, _, _ = context
    statements = []
    @event.listens_for(factory.kw["bind"], "before_cursor_execute")
    def capture_statement(connection, cursor, statement, params, execution_context, executemany):
        statements.append(statement.lstrip().upper())
    def pending_factory():
        database = factory()
        database.add(Organization(id=99, name="Pending synthetic", external_key="pending-synthetic"))
        return database
    source = SessionIdentitySource(sessions, handle, pending_factory, clock=lambda: clock[0])
    assert source.authenticated_identity() is not None
    assert any(statement.startswith("SELECT") for statement in statements)
    assert not any(statement.startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)


def test_stable_session_window_allows_repeated_m4c_checks(context):
    _, clock, _, _, source, authority = context
    initial = source.authenticated_identity()
    for seconds in (10, 20, 30, 40, 50):
        clock[0] = NOW + timedelta(seconds=seconds)
        assert source.authenticated_identity() == initial
        assert preflight_evidence_read(REQUEST, authority=authority).allowed


def test_bad_database_or_missing_dependency_denies_without_error_leakage(context, caplog):
    _, clock, sessions, handle, _, _ = context
    def broken_database():
        raise RuntimeError("synthetic-sensitive-database-error")
    source = SessionIdentitySource(sessions, handle, broken_database, clock=lambda: clock[0])
    assert source.authenticated_identity() is None
    assert SessionIdentitySource(sessions, handle, None).authenticated_identity() is None
    assert handle not in caplog.text and "synthetic-sensitive-database-error" not in caplog.text


def test_no_org_selector_or_client_claim_mapping_is_accepted(context):
    factory, _, sessions, handle, _, _ = context
    with pytest.raises(TypeError):
        SessionIdentitySource(sessions, handle, factory, organization_id=2)
    with pytest.raises(TypeError):
        VerifiedSubject(ISSUER, "reader", "synthetic-client", role="Admin", org_id=2)
