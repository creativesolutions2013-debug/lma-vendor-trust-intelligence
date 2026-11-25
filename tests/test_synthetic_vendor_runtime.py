"""Independent vendor identity has no SQL membership or analyst authority."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest
from sqlalchemy import select, update

from src.authz import PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_READ, PERMISSION_EVIDENCE_UPLOAD
from src.db import Base, Engagement, EngagementAccessGrant, OrganizationMembership
from urllib.parse import parse_qsl, urlsplit

from src.session_identity_source import SessionIdentitySource
from src.synthetic_browser_auth import SyntheticPilotIdentity
from src.synthetic_evidence_custody import SyntheticEvidenceCustodyService
from src.synthetic_pilot_runtime import prepare_runtime
from src.tenant_read_scope import TenantReadService


PORT = 19443
ISSUER = f"https://127.0.0.1:{PORT}/synthetic-idp"
VENDOR_ISSUER = f"https://127.0.0.1:{PORT}/vendor/synthetic-idp"


@pytest.fixture(autouse=True)
def development_only(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _runtime(directory, *, vendor=True):
    return prepare_runtime(directory, PORT, ISSUER, "synthetic-analyst", vendor_submissions=vendor)


def _source(runtime):
    password = "Synthetic-vendor-test-password-42"
    identity = SyntheticPilotIdentity(PORT, password, vendor=True)
    started = identity.begin_login()
    params = dict(parse_qsl(urlsplit(started.authorization_url).query))
    csrf = identity.provider_form_token(params, started.browser_binding)
    callback = identity.authorize(params, started.browser_binding, password, csrf)
    handle = identity.finish_login(dict(parse_qsl(urlsplit(callback).query)), started.browser_binding)
    verified = identity.sessions.authenticate(handle)
    assert (verified.issuer, verified.subject) == (VENDOR_ISSUER, "synthetic-vendor")
    return SessionIdentitySource(identity.sessions, handle, runtime.factory)


def _rows(runtime):
    with runtime.factory() as database:
        return tuple(tuple(database.execute(select(model.__table__).order_by(model.id)).all())
                     for model in (OrganizationMembership, EngagementAccessGrant))


def _files(directory):
    return {path.name: sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}


def test_opt_in_pins_distinct_vendor_profile_without_sql_membership_or_grant(tmp_path):
    directory = tmp_path / "runtime"
    runtime = _runtime(directory)
    try:
        marker = json.loads((directory / "runtime.json").read_text())
        assert marker["format"] == "lma-synthetic-vendor-runtime-v2"
        assert (marker["vendor_issuer"], marker["vendor_subject"]) == (VENDOR_ISSUER, "synthetic-vendor")
        assert runtime.vendor_submissions is True
        with runtime.factory() as database:
            members = database.execute(select(OrganizationMembership).order_by(OrganizationMembership.id)).scalars().all()
            assert [(m.id, m.issuer, m.subject, m.role) for m in members] == [
                (501, ISSUER, "synthetic-analyst", "Analyst")]
            grants = database.execute(select(EngagementAccessGrant).order_by(EngagementAccessGrant.id)).scalars().all()
            assert [(g.id, g.membership_id, g.engagement_id) for g in grants] == [(701, 501, 101)]
        source = _source(runtime)
        assert source.authenticated_identity() is None
        service = TenantReadService(runtime.factory, identity_source=source)
        assert service._scope(PERMISSION_EVIDENCE_UPLOAD) is None
        assert service._scope(PERMISSION_ASSESSMENT_MANAGE) is None
        assert service._scope(PERMISSION_EVIDENCE_READ) is None
        assert service.get_assessment(1001) is None
        assert service.list_vendors() == ()
        # Possessing a valid independently signed vendor session does not
        # confer a SQL role, assessment scope or original-byte authority.
        custody = SyntheticEvidenceCustodyService(runtime.factory, identity_source=source)
        assert custody.save(1001, b"Synthetic fixture only", document_name="vendor.txt") is None
    finally:
        runtime.close()


def test_default_phase6_runtime_remains_analyst_only(tmp_path):
    runtime = _runtime(tmp_path / "runtime", vendor=False)
    try:
        assert runtime.vendor_submissions is False
        assert json.loads((tmp_path / "runtime" / "runtime.json").read_text())["format"] == "lma-synthetic-analyst-runtime-v1"
        with runtime.factory() as database:
            assert database.execute(select(OrganizationMembership.id)).scalars().all() == [501]
            assert database.get(OrganizationMembership, 502) is None
            assert database.get(EngagementAccessGrant, 702) is None
    finally:
        runtime.close()


@pytest.mark.parametrize("value", [None, 0, 1, "true", {}, []])
def test_vendor_opt_in_requires_exact_bool_before_creating_files(tmp_path, value):
    with pytest.raises(ValueError, match="fixed localhost"):
        prepare_runtime(tmp_path / "runtime", PORT, ISSUER, "synthetic-analyst", vendor_submissions=value)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("initial,next_mode", [(False, True), (True, False)])
def test_existing_runtime_cannot_silently_change_identity_mode(tmp_path, initial, next_mode):
    directory = tmp_path / "runtime"
    runtime = _runtime(directory, vendor=initial)
    runtime.close()
    before = _files(directory)
    with pytest.raises(ValueError, match="origin or format"):
        _runtime(directory, vendor=next_mode)
    assert _files(directory) == before


def test_restart_preserves_analyst_revocation_role_deadlines_and_changed_grant(tmp_path, monkeypatch):
    directory = tmp_path / "runtime"
    runtime = _runtime(directory)
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    with runtime.factory.begin() as database:
        database.execute(update(OrganizationMembership).where(OrganizationMembership.id == 501)
            .values(status="revoked", role="Viewer", valid_from=expired - timedelta(days=1), expires_at=expired))
        database.execute(update(EngagementAccessGrant).where(EngagementAccessGrant.id == 701)
            .values(status="revoked", valid_from=expired - timedelta(days=1), expires_at=expired))
    before_rows = _rows(runtime)
    runtime.close()
    before_files = _files(directory)

    def no_schema(*args, **kwargs):
        pytest.fail("restart attempted schema initialization")
    monkeypatch.setattr(Base.metadata, "create_all", no_schema)
    reopened = _runtime(directory)
    try:
        assert _rows(reopened) == before_rows
        assert _source(reopened).authenticated_identity() is None
        assert _files(directory) == before_files
    finally:
        reopened.close()


def test_reopen_refuses_new_sql_membership_for_vendor_without_repair(tmp_path):
    directory = tmp_path / "runtime"
    runtime = _runtime(directory)
    with runtime.factory.begin() as database:
        now = datetime.now(timezone.utc)
        database.add(OrganizationMembership(id=502, organization_id=1, issuer=VENDOR_ISSUER,
            subject="synthetic-vendor", role="Viewer", status="active",
            valid_from=now - timedelta(minutes=1), expires_at=now + timedelta(days=1)))
    runtime.close()
    before = _files(directory)
    with pytest.raises(ValueError, match="vendor must have no SQL membership"):
        _runtime(directory)
    assert _files(directory) == before


def test_reopen_refuses_changed_analyst_engagement_without_repair(tmp_path):
    directory = tmp_path / "runtime"
    runtime = _runtime(directory)
    with runtime.factory.begin() as database:
        database.add(Engagement(id=102, vendor_id=11, service_name="Synthetic neighboring service"))
        database.flush()
        database.execute(update(EngagementAccessGrant).where(EngagementAccessGrant.id == 701)
            .values(engagement_id=102))
    runtime.close()
    before = _files(directory)
    with pytest.raises(ValueError, match="fixture ownership differs"):
        _runtime(directory)
    assert _files(directory) == before


def test_reopen_with_missing_handoff_guard_refuses_without_schema_repair(tmp_path):
    directory = tmp_path / "runtime"
    runtime = _runtime(directory)
    with runtime.engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER m7_handoff_no_update")
    runtime.close()
    before = _files(directory)
    with pytest.raises(PermissionError, match="handoff guards"):
        _runtime(directory)
    assert _files(directory) == before
