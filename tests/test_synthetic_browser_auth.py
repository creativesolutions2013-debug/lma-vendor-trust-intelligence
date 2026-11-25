"""Signed local synthetic sign-in and browser/session binding regressions.

No HTTP provider, real identity, confidential data or production login is used.
Actual HTTP cookies/headers are exercised by the separate pilot server tests.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import re
import socket
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest

import src.synthetic_browser_auth as auth_module
from src.oidc_login import LoginRejected, ProviderConfig
from src.synthetic_browser_auth import SyntheticPilotIdentity


NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)
PASSWORD = "Synthetic-fixture-password-42"


@pytest.fixture
def identity():
    clock = [NOW]
    auth = SyntheticPilotIdentity(8443, PASSWORD, clock=lambda: clock[0])
    return SimpleNamespace(auth=auth, clock=clock)


def parameters(url):
    pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    assert len(pairs) == len(dict(pairs))
    return dict(pairs)


def start(identity):
    begun = identity.auth.begin_login()
    params = parameters(begun.authorization_url)
    csrf = identity.auth.provider_form_token(params, begun.browser_binding)
    return begun, params, csrf


def authorize(identity):
    begun, params, csrf = start(identity)
    callback = identity.auth.authorize(params, begun.browser_binding, PASSWORD, csrf)
    return begun, params, parameters(callback)


def login(identity):
    begun, _, callback = authorize(identity)
    return identity.auth.finish_login(callback, begun.browser_binding)


def rejected(call):
    with pytest.raises(LoginRejected, match=r"^Sign-in rejected\.$"):
        call()


def test_real_signed_local_flow_issues_fresh_server_session_without_network(identity, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic sign-in attempted an external connection")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    auth = identity.auth
    begun, params, csrf = start(identity)
    assert auth.origin == "https://127.0.0.1:8443"
    assert auth.config.issuer == auth.origin + "/synthetic-idp"
    assert urlsplit(begun.authorization_url)._replace(query="").geturl() == auth.config.authorization_endpoint
    assert params["response_type"] == "code" and params["scope"] == "openid"
    assert params["code_challenge_method"] == "S256"
    assert params["redirect_uri"] == auth.config.redirect_uri
    assert "code_verifier" not in params
    assert re.fullmatch(r"[0-9a-f]{64}", csrf)
    callback_url = auth.authorize(params, begun.browser_binding, PASSWORD, csrf)
    assert urlsplit(callback_url)._replace(query="").geturl() == auth.config.redirect_uri
    callback = parameters(callback_url)
    assert set(callback) == {"code", "state", "iss"}
    assert callback["state"] == params["state"] and callback["iss"] == auth.config.issuer
    handle = auth.finish_login(callback, begun.browser_binding)
    session = auth.sessions.authenticate(handle)
    assert session is not None
    assert session.subject == "synthetic-analyst" and session.issuer == auth.config.issuer
    assert session.session_id != handle and session.audience == auth.config.client_id
    assert not hasattr(session, "role") and not hasattr(session, "organization_id")
    another = login(identity)
    assert handle != another
    assert auth.sessions.authenticate(another).session_id != session.session_id
    assert PASSWORD not in repr(auth) + repr(begun)


@pytest.mark.parametrize("field,value", [
    ("client_id", "other-client"), ("response_type", "token"), ("scope", "openid email"),
    ("redirect_uri", "https://attacker.invalid/callback"), ("redirect_uri", "https://127.0.0.1:8444/oidc/callback"),
    ("state", "f" * 43), ("nonce", "n" * 43), ("code_challenge", "c" * 43),
    ("code_challenge_method", "plain"), ("role", "Admin"), ("organization_id", "999"),
])
def test_provider_rejects_changed_or_invented_authorization_parameters(identity, field, value):
    begun, params, csrf = start(identity)
    changed = dict(params, **{field: value})
    rejected(lambda: identity.auth.provider_form_token(changed, begun.browser_binding))
    rejected(lambda: identity.auth.authorize(changed, begun.browser_binding, PASSWORD, csrf))


@pytest.mark.parametrize("invalid", [None, {}, [], "state=caller-selected", {"state": True}])
def test_provider_rejects_noncanonical_parameter_shape(identity, invalid):
    begun, _, _ = start(identity)
    rejected(lambda: identity.auth.provider_form_token(invalid, begun.browser_binding))


def test_provider_requires_own_browser_binding_and_context_specific_csrf(identity):
    one, params, csrf = start(identity)
    two, _, _ = start(identity)
    rejected(lambda: identity.auth.provider_form_token(params, two.browser_binding))
    rejected(lambda: identity.auth.authorize(params, two.browser_binding, PASSWORD, csrf))
    browser_token = identity.auth.browser_csrf(one.browser_binding)
    assert browser_token != csrf
    assert identity.auth.valid_browser_csrf(one.browser_binding, browser_token)
    assert not identity.auth.valid_browser_csrf(two.browser_binding, browser_token)
    assert not identity.auth.valid_browser_csrf(one.browser_binding, csrf)
    rejected(lambda: identity.auth.authorize(params, one.browser_binding, PASSWORD, browser_token))


@pytest.mark.parametrize("bad", [None, "", "f" * 63, "f" * 65, "g" * 64, True, {}, b"f" * 64])
def test_provider_does_not_accept_malformed_csrf(identity, bad):
    begun, params, _ = start(identity)
    rejected(lambda: identity.auth.authorize(params, begun.browser_binding, PASSWORD, bad))


@pytest.mark.parametrize("binding", [None, "", "x" * 42, "x" * 44, "!" * 43, True, {}])
def test_browser_csrf_helpers_deny_malformed_binding(identity, binding):
    rejected(lambda: identity.auth.browser_csrf(binding))
    assert identity.auth.valid_browser_csrf(binding, "f" * 64) is False


def test_authorization_is_one_use_and_wrong_password_never_issues_code(identity):
    begun, params, csrf = start(identity)
    rejected(lambda: identity.auth.authorize(params, begun.browser_binding, "Wrong-synthetic-password", csrf))
    callback = identity.auth.authorize(params, begun.browser_binding, PASSWORD, csrf)
    rejected(lambda: identity.auth.authorize(params, begun.browser_binding, PASSWORD, csrf))
    assert identity.auth.sessions.authenticate(identity.auth.finish_login(parameters(callback), begun.browser_binding))


def test_password_attempt_budget_is_global_bounded_and_recovers_after_window(identity):
    begun, params, csrf = start(identity)
    another, other_params, other_csrf = start(identity)
    for _ in range(5):
        rejected(lambda: identity.auth.authorize(params, begun.browser_binding, "Wrong-synthetic-password", csrf))
    rejected(lambda: identity.auth.authorize(other_params, another.browser_binding, PASSWORD, other_csrf))
    identity.clock[0] += timedelta(seconds=61)
    callback = identity.auth.authorize(other_params, another.browser_binding, PASSWORD, other_csrf)
    assert identity.auth.finish_login(parameters(callback), another.browser_binding)


def test_callback_with_another_browser_binding_consumes_and_denies_replay(identity):
    begun, _, callback = authorize(identity)
    other, _, _ = start(identity)
    rejected(lambda: identity.auth.finish_login(callback, other.browser_binding))
    rejected(lambda: identity.auth.finish_login(callback, begun.browser_binding))


@pytest.mark.parametrize("field,value", [("code", "x" * 43), ("state", "x" * 43),
    ("iss", "https://attacker.invalid"), ("role", "Admin"),
    ("redirect_uri", "https://attacker.invalid/callback")])
def test_callback_cannot_change_issuer_state_code_or_add_identity_fields(identity, field, value):
    begun, _, callback = authorize(identity)
    rejected(lambda: identity.auth.finish_login(dict(callback, **{field: value}), begun.browser_binding))


def test_racing_callback_issues_one_session_and_replay_is_rejected(identity):
    begun, _, callback = authorize(identity)
    def finish():
        try:
            return identity.auth.finish_login(callback, begun.browser_binding)
        except LoginRejected:
            return None
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: finish(), range(2)))
    handles = [value for value in results if value is not None]
    assert len(handles) == 1 and identity.auth.sessions.authenticate(handles[0])
    rejected(lambda: identity.auth.finish_login(callback, begun.browser_binding))


def test_provider_independently_checks_pkce_and_consumes_a_bad_exchange(identity):
    begun, _, callback = authorize(identity)
    config = identity.auth.config
    rejected(lambda: identity.auth._exchange(config.token_endpoint, config.client_id,
        config.redirect_uri, callback["code"], "incorrect-verifier-value-that-is-bounded-and-long-enough"))
    rejected(lambda: identity.auth.finish_login(callback, begun.browser_binding))


def test_invalid_provider_token_cannot_bypass_existing_signature_verification(identity, monkeypatch):
    begun, _, callback = authorize(identity)
    monkeypatch.setattr(auth_module.jwt, "encode", lambda *args, **kwargs: "not-a-signed-token")
    rejected(lambda: identity.auth.finish_login(callback, begun.browser_binding))


def test_signed_wrong_nonce_cannot_bypass_existing_claim_verification(identity, monkeypatch):
    begun, _, callback = authorize(identity)
    original = auth_module.jwt.encode
    def wrong_nonce(header, claims, key):
        return original(header, dict(claims, nonce="wrong-synthetic-nonce"), key)
    monkeypatch.setattr(auth_module.jwt, "encode", wrong_nonce)
    rejected(lambda: identity.auth.finish_login(callback, begun.browser_binding))


def test_pending_authorization_and_code_expire_independently(identity):
    begun, params, csrf = start(identity)
    identity.clock[0] += timedelta(seconds=300)
    rejected(lambda: identity.auth.provider_form_token(params, begun.browser_binding))
    rejected(lambda: identity.auth.authorize(params, begun.browser_binding, PASSWORD, csrf))
    begun, _, callback = authorize(identity)
    identity.clock[0] += timedelta(seconds=60)
    rejected(lambda: identity.auth.finish_login(callback, begun.browser_binding))


def test_app_login_transaction_expiry_cannot_be_extended_by_late_authorization(identity):
    begun, params, csrf = start(identity)
    identity.clock[0] += timedelta(seconds=241)
    callback = identity.auth.authorize(params, begun.browser_binding, PASSWORD, csrf)
    identity.clock[0] += timedelta(seconds=59)
    rejected(lambda: identity.auth.finish_login(parameters(callback), begun.browser_binding))


def test_session_csrf_is_separate_from_login_and_provider_contexts(identity):
    begun, params, provider_csrf = start(identity)
    browser_csrf = identity.auth.browser_csrf(begun.browser_binding)
    callback = identity.auth.authorize(params, begun.browser_binding, PASSWORD, provider_csrf)
    handle = identity.auth.finish_login(parameters(callback), begun.browser_binding)
    session_csrf = identity.auth.csrf_token(handle)
    assert re.fullmatch(r"[0-9a-f]{64}", session_csrf)
    assert len({session_csrf, browser_csrf, provider_csrf}) == 3
    assert identity.auth.valid_csrf(handle, session_csrf)
    assert not identity.auth.valid_csrf(handle, provider_csrf)
    assert not identity.auth.valid_csrf(handle, browser_csrf)
    assert not identity.auth.valid_browser_csrf(begun.browser_binding, session_csrf)
    other_handle = login(identity)
    assert not identity.auth.valid_csrf(other_handle, session_csrf)


@pytest.mark.parametrize("operation", ["logout", "rotate", "idle", "absolute"])
def test_revoked_rotated_and_expired_handles_cannot_mint_or_use_csrf(identity, operation):
    handle = login(identity)
    token = identity.auth.csrf_token(handle)
    if operation == "logout":
        assert identity.auth.logout(handle) is True
    elif operation == "rotate":
        rotated = identity.auth.sessions.rotate(handle)
        assert rotated and identity.auth.sessions.authenticate(rotated)
        assert not identity.auth.valid_csrf(rotated, token)
    elif operation == "idle":
        identity.clock[0] += timedelta(seconds=300)
    else:
        deadline = identity.auth.sessions.authenticate(handle).expires_at
        while identity.clock[0] + timedelta(seconds=240) < deadline:
            identity.clock[0] += timedelta(seconds=240)
            assert identity.auth.sessions.authenticate(handle)
        identity.clock[0] = deadline
    assert identity.auth.sessions.authenticate(handle) is None
    assert identity.auth.valid_csrf(handle, token) is False
    rejected(lambda: identity.auth.csrf_token(handle))


def test_logout_does_not_claim_success_on_revoke_failure(identity, monkeypatch):
    handle = login(identity)
    def unavailable(_key):
        raise RuntimeError("synthetic session-store outage")
    monkeypatch.setattr(identity.auth.sessions._store, "revoke", unavailable)
    assert identity.auth.logout(handle) is False
    assert identity.auth.sessions.authenticate(handle) is not None


@pytest.mark.parametrize("password", [None, True, b"Synthetic-fixture-password-42", "a" * 15,
    "a" * 257, "é" * 129])
def test_operator_password_is_a_bounded_plain_string(password):
    with pytest.raises(ValueError):
        SyntheticPilotIdentity(8443, password)


@pytest.mark.parametrize("port", [None, True, False, 443, 1023, 65536, "8443", 8443.0])
def test_pilot_constructor_requires_an_explicit_high_loopback_port(port):
    with pytest.raises(ValueError):
        SyntheticPilotIdentity(port, PASSWORD)


def normal_config(**changes):
    values = dict(issuer="https://issuer.synthetic.invalid", client_id="synthetic-client",
        authorization_endpoint="https://issuer.synthetic.invalid/authorize",
        token_endpoint="https://issuer.synthetic.invalid/token", jwks_uri="https://issuer.synthetic.invalid/jwks",
        redirect_uri="https://app.synthetic.invalid/oidc/callback")
    values.update(changes)
    return ProviderConfig(**values)


def test_normal_provider_configuration_remains_https_only_with_no_loopback_exception():
    assert normal_config().synthetic_loopback_port is None
    with pytest.raises(ValueError):
        normal_config(redirect_uri="http://127.0.0.1:8443/oidc/callback")
    with pytest.raises(ValueError):
        normal_config(redirect_uri="https://127.0.0.1:8443/oidc/callback")


@pytest.mark.parametrize("field,value", [
    ("issuer", "https://127.0.0.1:8443/other-idp"),
    ("authorization_endpoint", "https://127.0.0.1:8444/synthetic-idp/authorize"),
    ("token_endpoint", "http://127.0.0.1:8443/synthetic-idp/token"),
    ("jwks_uri", "https://localhost:8443/synthetic-idp/jwks"),
    ("redirect_uri", "https://127.0.0.1:8443/oidc/callback?next=evil"),
    ("redirect_uri", "https://127.0.0.1:8443/oidc/callback#fragment"),
    ("redirect_uri", "https://127.0.0.1:8443/oidc/callback/"),
    ("redirect_uri", "https://127.0.0.2:8443/oidc/callback"),
    ("redirect_uri", "https://user@127.0.0.1:8443/oidc/callback"),
    ("synthetic_loopback_port", 8444), ("synthetic_loopback_port", True),
])
def test_loopback_configuration_is_exactly_pinned_to_all_five_known_urls(identity, field, value):
    with pytest.raises(ValueError):
        replace(identity.auth.config, **{field: value})


def test_loopback_configuration_is_explicit_and_does_not_apply_to_arbitrary_https_provider():
    with pytest.raises(ValueError):
        normal_config(synthetic_loopback_port=8443)
