"""Independent synthetic vendor sign-in must confer no analyst identity.

Only generated fixture keys/passwords are used; no external provider or account
is contacted. HTTP cookie and endpoint separation belong to the pilot tests.
"""
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

import pytest

import src.synthetic_browser_auth as auth_module
from src.oidc_login import LoginRejected
from src.synthetic_browser_auth import SyntheticPilotIdentity


ANALYST_PASSWORD = "Synthetic-analyst-fixture-password-42"
VENDOR_PASSWORD = "Synthetic-vendor-fixture-password-73"
NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def identities():
    return (SyntheticPilotIdentity(8443, ANALYST_PASSWORD, clock=lambda: NOW),
            SyntheticPilotIdentity(8443, VENDOR_PASSWORD, vendor=True, clock=lambda: NOW))


def _parameters(url):
    return dict(parse_qsl(urlsplit(url).query, strict_parsing=True))


def _start(identity):
    begun = identity.begin_login()
    params = _parameters(begun.authorization_url)
    return begun, params, identity.provider_form_token(params, begun.browser_binding)


def _authorized(identity, password):
    begun, params, csrf = _start(identity)
    callback = identity.authorize(params, begun.browser_binding, password, csrf)
    return begun, _parameters(callback)


def _login(identity, password):
    begun, callback = _authorized(identity, password)
    return identity.finish_login(callback, begun.browser_binding)


def test_signed_vendor_flow_has_distinct_fixed_identity_and_session_store(identities):
    analyst, vendor = identities
    analyst_handle = _login(analyst, ANALYST_PASSWORD)
    vendor_handle = _login(vendor, VENDOR_PASSWORD)
    session = vendor.sessions.authenticate(vendor_handle)
    assert session.subject == "synthetic-vendor" == vendor.subject
    assert session.issuer == "https://127.0.0.1:8443/vendor/synthetic-idp"
    assert session.audience == "lma-synthetic-vendor"
    assert analyst.subject == "synthetic-analyst"
    assert analyst.sessions.authenticate(vendor_handle) is None
    assert vendor.sessions.authenticate(analyst_handle) is None
    assert not hasattr(session, "role") and not hasattr(session, "organization_id")


def test_password_and_all_csrf_contexts_are_separate(identities):
    analyst, vendor = identities
    begun, params, csrf = _start(vendor)
    with pytest.raises(LoginRejected):
        vendor.authorize(params, begun.browser_binding, ANALYST_PASSWORD, csrf)
    with pytest.raises(LoginRejected):
        vendor.authorize(params, begun.browser_binding, VENDOR_PASSWORD,
                         analyst.browser_csrf(begun.browser_binding))
    assert not vendor.valid_browser_csrf(begun.browser_binding,
                                         analyst.browser_csrf(begun.browser_binding))
    callback = vendor.authorize(params, begun.browser_binding, VENDOR_PASSWORD, csrf)
    vendor_handle = vendor.finish_login(_parameters(callback), begun.browser_binding)
    analyst_handle = _login(analyst, ANALYST_PASSWORD)
    assert not analyst.valid_csrf(vendor_handle, vendor.csrf_token(vendor_handle))
    assert not vendor.valid_csrf(analyst_handle, analyst.csrf_token(analyst_handle))
    assert not vendor.valid_csrf(vendor_handle, analyst.csrf_token(analyst_handle))


@pytest.mark.parametrize("reverse", [False, True])
def test_other_identity_cannot_use_authorization_or_callback(identities, reverse):
    analyst, vendor = identities
    owner, other = (vendor, analyst) if reverse else (analyst, vendor)
    password = VENDOR_PASSWORD if reverse else ANALYST_PASSWORD
    begun, params, csrf = _start(owner)
    with pytest.raises(LoginRejected):
        other.provider_form_token(params, begun.browser_binding)
    with pytest.raises(LoginRejected):
        other.authorize(params, begun.browser_binding, password, csrf)
    callback = _parameters(owner.authorize(params, begun.browser_binding, password, csrf))
    with pytest.raises(LoginRejected):
        other.finish_login(callback, begun.browser_binding)
    assert owner.sessions.authenticate(owner.finish_login(callback, begun.browser_binding))


@pytest.mark.parametrize("reverse", [False, True])
def test_other_identity_signing_key_cannot_issue_even_matching_claims(identities, monkeypatch, reverse):
    analyst, vendor = identities
    owner, other = (vendor, analyst) if reverse else (analyst, vendor)
    begun, callback = _authorized(owner, VENDOR_PASSWORD if reverse else ANALYST_PASSWORD)
    original = auth_module.jwt.encode

    def foreign_key(header, claims, key):
        # Keep the expected issuer/audience/nonce; only the signing authority
        # changes, so successful rejection specifically proves key isolation.
        return original(header, claims, other._key)

    monkeypatch.setattr(auth_module.jwt, "encode", foreign_key)
    with pytest.raises(LoginRejected):
        owner.finish_login(callback, begun.browser_binding)


@pytest.mark.parametrize("field", ["issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "redirect_uri"])
@pytest.mark.parametrize("reverse", [False, True])
def test_complete_loopback_profiles_cannot_mix_provider_and_callback(identities, field, reverse):
    analyst, vendor = identities
    owner, other = (vendor, analyst) if reverse else (analyst, vendor)
    with pytest.raises(ValueError):
        replace(owner.config, **{field: getattr(other.config, field)})


@pytest.mark.parametrize("vendor", [None, 0, 1, "vendor", {}, []])
def test_browser_like_profile_values_cannot_select_account(vendor):
    with pytest.raises(ValueError):
        SyntheticPilotIdentity(8443, VENDOR_PASSWORD, vendor=vendor)


def test_vendor_logout_does_not_revoke_analyst_session(identities):
    analyst, vendor = identities
    analyst_handle = _login(analyst, ANALYST_PASSWORD)
    vendor_handle = _login(vendor, VENDOR_PASSWORD)
    assert vendor.logout(vendor_handle)
    assert vendor.sessions.authenticate(vendor_handle) is None
    assert analyst.sessions.authenticate(analyst_handle) is not None
