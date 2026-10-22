"""Local signed synthetic tokens exercise the unwired OIDC trust boundary.

No provider, network, account, browser cookie or customer document is used.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.errors import SecurityWarning
from joserfc.jwk import ECKey, OctKey, RSAKey
from joserfc.jws import JWSRegistry
from joserfc.registry import HeaderParameter

from src.oidc_login import (
    IDTokenVerifier, InMemoryLoginTransactions, LoginRejected, LoginService,
    ProviderConfig,
)
from src.server_sessions import InMemorySessionStore, SessionManager


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
ISSUER = "https://issuer.synthetic.invalid"
CLIENT = "synthetic-lma-client"
NONCE = "synthetic-expected-nonce"


@pytest.fixture(scope="module")
def signing_key():
    # Generated only in memory; no private key or real identity is committed.
    return RSAKey.generate_key(2048, {"kid": "synthetic-key", "alg": "RS256", "use": "sig"})


@pytest.fixture
def config():
    return ProviderConfig(
        issuer=ISSUER, client_id=CLIENT,
        authorization_endpoint=ISSUER + "/authorize",
        token_endpoint=ISSUER + "/token", jwks_uri=ISSUER + "/jwks",
        redirect_uri="https://lma.synthetic.invalid/oidc/callback",
    )


def claims(**changes):
    result = {
        "iss": ISSUER, "sub": "synthetic-reader", "aud": CLIENT,
        "exp": int(NOW.timestamp()) + 300, "iat": int(NOW.timestamp()) - 10,
        "nonce": NONCE,
    }
    result.update(changes)
    return result


def signed(key, payload=None, **header):
    # Test-only signing permits a malformed kid while retaining a real signature.
    # Verification always uses the library's normal registry and strict core.
    registry = None
    if "kid" in header and not isinstance(header["kid"], str):
        registry = JWSRegistry(header_registry={"kid": HeaderParameter("Synthetic malformed kid", lambda _: None)})
    return jwt.encode({"alg": "RS256", "kid": "synthetic-key", **header},
                      claims() if payload is None else payload, key, registry=registry)


def verifier(config, key):
    return IDTokenVerifier(config, {"keys": [key.as_dict(private=False)]})


def test_signed_token_establishes_only_stable_account_identity(config, signing_key):
    verified = verifier(config, signing_key).verify(
        signed(signing_key, claims(role="Admin", org_id=999, groups=["owners"],
                                   email="imposter@synthetic.invalid")), nonce=NONCE, now=NOW,
    )
    assert (verified.issuer, verified.subject, verified.audience) == (ISSUER, "synthetic-reader", CLIENT)
    assert not hasattr(verified, "organization_id")
    assert not hasattr(verified, "role")


@pytest.mark.parametrize("change", [
    {"iss": "https://other.synthetic.invalid"}, {"iss": ISSUER + "/"}, {"iss": None},
    {"sub": ""}, {"sub": 123}, {"aud": "other-client"}, {"aud": []},
    {"aud": [CLIENT, "other-client"]}, {"aud": [CLIENT, CLIENT]},
    {"aud": [CLIENT, 123]}, {"aud": {"client": CLIENT}},
    {"azp": "other-client"}, {"azp": None},
    {"nonce": "other-nonce"}, {"nonce": ""}, {"nonce": 42},
    {"exp": int(NOW.timestamp()) - 31}, {"exp": True}, {"exp": "9999999999"},
    {"exp": None}, {"exp": float("nan")}, {"exp": float("inf")},
    {"iat": int(NOW.timestamp()) + 31}, {"iat": False}, {"iat": "10"},
    {"iat": int(NOW.timestamp()) - 601},
    {"iat": int(NOW.timestamp()) + 20, "exp": int(NOW.timestamp()) + 10},
    {"nbf": int(NOW.timestamp()) + 31}, {"nbf": True}, {"nbf": "10"},
    {"auth_time": int(NOW.timestamp()) + 31}, {"auth_time": True},
])
def test_signed_but_invalid_claims_deny(config, signing_key, change):
    with pytest.raises(LoginRejected, match="^Sign-in rejected\\.$"):
        verifier(config, signing_key).verify(signed(signing_key, claims(**change)), nonce=NONCE, now=NOW)


@pytest.mark.parametrize("missing", ["iss", "sub", "aud", "exp", "iat", "nonce"])
def test_required_claims_cannot_be_omitted(config, signing_key, missing):
    payload = claims()
    payload.pop(missing)
    with pytest.raises(LoginRejected):
        verifier(config, signing_key).verify(signed(signing_key, payload), nonce=NONCE, now=NOW)


def test_multiple_audiences_require_exact_authorized_party(config, signing_key):
    verified = verifier(config, signing_key).verify(
        signed(signing_key, claims(aud=[CLIENT, "another-resource"], azp=CLIENT)), nonce=NONCE, now=NOW,
    )
    assert verified.audience == CLIENT


@pytest.mark.parametrize("auth_time", [None, int(NOW.timestamp()) - 301])
def test_requested_authentication_freshness_requires_current_auth_time(config, signing_key, auth_time):
    payload = claims()
    if auth_time is not None:
        payload["auth_time"] = auth_time
    with pytest.raises(LoginRejected):
        verifier(replace(config, max_auth_age_seconds=60), signing_key).verify(
            signed(signing_key, payload), nonce=NONCE, now=NOW,
        )


def test_current_auth_time_is_accepted_when_requested(config, signing_key):
    assert verifier(replace(config, max_auth_age_seconds=60), signing_key).verify(
        signed(signing_key, claims(auth_time=int(NOW.timestamp()) - 10)), nonce=NONCE, now=NOW,
    ).subject == "synthetic-reader"


@pytest.mark.parametrize("token", ["", "malformed", "a.b.c.d", None,
    "eyJhbGciOiJub25lIiwia2lkIjoic3ludGhldGljLWtleSJ9.e30."])
def test_malformed_unsigned_tokens_deny(config, signing_key, token):
    with pytest.raises(LoginRejected):
        verifier(config, signing_key).verify(token, nonce=NONCE, now=NOW)


def test_wrong_signature_and_hmac_algorithm_confusion_deny(config, signing_key):
    other = RSAKey.generate_key(2048, {"kid": "synthetic-key"})
    hmac_key = OctKey.generate_key(256)
    hmac_token = jwt.encode({"alg": "HS256", "kid": "synthetic-key"}, claims(), hmac_key)
    for token in (signed(other), hmac_token):
        with pytest.raises(LoginRejected):
            verifier(config, signing_key).verify(token, nonce=NONCE, now=NOW)


@pytest.mark.parametrize("header", [
    {"kid": "unknown-key"}, {"kid": ""}, {"kid": 1},
    {"jku": "https://attacker.synthetic.invalid/jwks"},
    {"x5u": "https://attacker.synthetic.invalid/cert"},
    {"jwk": {"kty": "oct", "k": "c3ludGhldGlj"}},
])
def test_key_selection_is_pinned_and_never_uses_header_urls(config, signing_key, header):
    with pytest.raises(LoginRejected):
        verifier(config, signing_key).verify(signed(signing_key, **header), nonce=NONCE, now=NOW)


def test_missing_kid_does_not_fallback_to_the_only_key(config, signing_key):
    # Remove metadata from a copy of the same private key, so the signature is
    # valid but no kid can be supplied implicitly by the signing library.
    data = signing_key.as_dict(private=True)
    data.pop("kid")
    key_without_id = RSAKey.import_key(data)
    token = jwt.encode({"alg": "RS256"}, claims(), key_without_id)
    with pytest.raises(LoginRejected):
        verifier(config, signing_key).verify(token, nonce=NONCE, now=NOW)


@pytest.mark.parametrize("mutation", ["duplicate", "empty", "missing-kid", "encryption", "hmac"])
def test_invalid_or_ambiguous_trusted_jwks_denies_configuration(config, signing_key, mutation):
    key = signing_key.as_dict(private=False)
    keys = [key]
    if mutation == "duplicate":
        keys.append(dict(key))
    elif mutation == "empty":
        keys = []
    elif mutation == "missing-kid":
        key.pop("kid")
    elif mutation == "encryption":
        key["use"] = "enc"
    else:
        keys = [OctKey.generate_key(256, {"kid": "synthetic-hmac"}).as_dict()]
    with pytest.raises(ValueError):
        IDTokenVerifier(config, {"keys": keys})


def test_explicit_pinned_key_rotation_does_not_retain_old_keys(config, signing_key):
    rotated = RSAKey.generate_key(2048, {"kid": "rotated-key", "alg": "RS256", "use": "sig"})
    current = verifier(config, rotated)
    with pytest.raises(LoginRejected):
        current.verify(signed(signing_key), nonce=NONCE, now=NOW)
    assert current.verify(signed(rotated, kid="rotated-key"), nonce=NONCE, now=NOW).subject == "synthetic-reader"


def test_weak_rsa_key_cannot_enter_the_trusted_snapshot(config):
    with pytest.warns(SecurityWarning, match="2048"):
        weak = RSAKey.generate_key(1024, {"kid": "synthetic-weak-key", "alg": "RS256", "use": "sig"})
    with pytest.warns(SecurityWarning, match="2048"), pytest.raises(ValueError):
        IDTokenVerifier(config, {"keys": [weak.as_dict(private=False)]})


def test_allowlisted_ec_signature_uses_library_verification(config):
    key = ECKey.generate_key("P-256", {"kid": "synthetic-ec", "alg": "ES256", "use": "sig"})
    token = jwt.encode({"alg": "ES256", "kid": "synthetic-ec"}, claims(), key)
    assert verifier(replace(config, algorithms=("ES256",)), key).verify(
        token, nonce=NONCE, now=NOW,
    ).subject == "synthetic-reader"


@pytest.mark.parametrize("change", [
    {"issuer": ""}, {"issuer": "http://issuer.synthetic.invalid"},
    {"issuer": "https://user:password@issuer.synthetic.invalid"},
    {"issuer": ISSUER + "#fragment"}, {"client_id": ""},
    {"authorization_endpoint": "https://attacker.synthetic.invalid/authorize?redirect_uri=evil"},
    {"token_endpoint": "http://issuer.synthetic.invalid/token"},
    {"jwks_uri": "file:///tmp/keys"},
    {"redirect_uri": "https://lma.synthetic.invalid/callback#fragment"},
    {"redirect_uri": "http://localhost/callback"},
    {"algorithms": ("none",)}, {"algorithms": ("HS256",)}, {"algorithms": ()},
    {"clock_skew_seconds": 301}, {"clock_skew_seconds": True},
    {"max_token_age_seconds": 0},
])
def test_missing_or_unsafe_provider_config_fails_closed(config, change):
    with pytest.raises(ValueError):
        replace(config, **change)


class FakeProvider:
    """Injected local provider: signs only claims for the current authorization URL."""
    def __init__(self, key):
        self.key = key
        self.nonce = NONCE
        self.challenge = None
        self.calls = []
        self.failure = False
        self.payload_changes = {}

    def bind(self, start):
        params = parse_qs(urlsplit(start.authorization_url).query)
        self.nonce = params["nonce"][0]
        assert params["code_challenge_method"] == ["S256"]
        self.challenge = params["code_challenge"][0]
        return params

    def exchange_code(self, **request):
        self.calls.append(request)
        if self.failure:
            raise RuntimeError("provider-private-token-and-code")
        if create_s256_code_challenge(request["code_verifier"]) != self.challenge:
            raise RuntimeError("PKCE mismatch")
        return {"id_token": signed(self.key, claims(nonce=self.nonce, **self.payload_changes))}


@pytest.fixture
def flow(config, signing_key):
    clock = [NOW]
    provider = FakeProvider(signing_key)
    sessions = SessionManager(InMemorySessionStore(), clock=lambda: clock[0])
    service = LoginService(config, verifier(config, signing_key), InMemoryLoginTransactions(),
                           sessions, provider, clock=lambda: clock[0])
    return service, provider, sessions, clock


def callback(service, provider, config, *, code="synthetic-code", **changes):
    start = service.begin()
    params = provider.bind(start)
    request = dict(state=params["state"][0], code=code, issuer=config.issuer,
                   redirect_uri=config.redirect_uri, browser_binding=start.browser_binding)
    request.update(changes)
    return start, params, request


def test_code_flow_uses_one_time_random_state_nonce_and_pkce_s256(flow, config):
    service, provider, sessions, _ = flow
    start, params, request = callback(service, provider, config)
    assert params["response_type"] == ["code"]
    assert params["client_id"] == [CLIENT]
    assert params["redirect_uri"] == [config.redirect_uri]
    assert params["code_challenge_method"] == ["S256"]
    assert "openid" in params["scope"][0].split()
    assert len(params["state"][0]) >= 32
    assert len(params["nonce"][0]) >= 32
    assert start.browser_binding not in start.authorization_url
    handle = service.finish(**request)
    session = sessions.authenticate(handle)
    assert session.subject == "synthetic-reader"
    exchange = provider.calls[0]
    assert exchange["token_endpoint"] == config.token_endpoint
    assert exchange["client_id"] == CLIENT
    assert exchange["redirect_uri"] == config.redirect_uri
    assert len(exchange["code_verifier"]) >= 43
    assert create_s256_code_challenge(exchange["code_verifier"]) == params["code_challenge"][0]
    assert exchange["code_verifier"] not in start.authorization_url
    with pytest.raises(LoginRejected):
        service.finish(**request)
    assert len(provider.calls) == 1
    next_start = service.begin()
    next_params = provider.bind(next_start)
    assert next_params["state"] != params["state"]
    assert next_params["nonce"] != params["nonce"]
    assert next_params["code_challenge"] != params["code_challenge"]


@pytest.mark.parametrize("change", [
    {"state": "unsolicited-state"}, {"state": ""},
    {"browser_binding": "different-browser"},
    {"issuer": "https://other.synthetic.invalid"},
    {"redirect_uri": "https://attacker.synthetic.invalid/callback"},
    {"redirect_uri": "https://lma.synthetic.invalid/oidc/callback?next=evil"},
    {"code": ""}, {"code": None},
])
def test_unsolicited_or_mismatched_callback_never_exchanges(flow, config, change):
    service, provider, _, _ = flow
    _, _, request = callback(service, provider, config, **change)
    with pytest.raises(LoginRejected):
        service.finish(**request)
    assert provider.calls == []


def test_expired_login_state_denies_before_exchange(flow, config):
    service, provider, _, clock = flow
    _, _, request = callback(service, provider, config)
    clock[0] += timedelta(seconds=301)
    with pytest.raises(LoginRejected):
        service.finish(**request)
    assert provider.calls == []


def test_reused_code_with_a_fresh_transaction_still_denies(flow, config):
    service, provider, _, _ = flow
    _, _, first = callback(service, provider, config)
    service.finish(**first)
    _, _, second = callback(service, provider, config)
    with pytest.raises(LoginRejected):
        service.finish(**second)
    assert len(provider.calls) == 1


def test_racing_callbacks_issue_only_one_session(flow, config):
    service, provider, sessions, _ = flow
    _, _, request = callback(service, provider, config)
    def finish():
        try:
            return service.finish(**request)
        except LoginRejected:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: finish(), range(2)))
    accepted = [handle for handle in outcomes if handle]
    assert len(accepted) == 1
    assert sessions.authenticate(accepted[0]) is not None
    assert len(provider.calls) == 1


def test_exchange_failure_consumes_attempt_without_leaking_provider_data(flow, config, caplog):
    service, provider, _, _ = flow
    _, _, request = callback(service, provider, config)
    provider.failure = True
    with pytest.raises(LoginRejected) as error:
        service.finish(**request)
    assert str(error.value) == "Sign-in rejected."
    assert "provider-private" not in caplog.text
    provider.failure = False
    with pytest.raises(LoginRejected):
        service.finish(**request)
    assert len(provider.calls) == 1


def test_stale_nonce_token_cannot_be_replayed_in_a_new_transaction(flow, config):
    service, provider, _, _ = flow
    _, params, first = callback(service, provider, config)
    service.finish(**first)
    _, _, second = callback(service, provider, config, code="another-code")
    provider.nonce = params["nonce"][0]
    with pytest.raises(LoginRejected):
        service.finish(**second)


def test_transaction_expiring_during_exchange_cannot_issue_session(flow, config):
    service, provider, _, clock = flow
    _, _, request = callback(service, provider, config)
    exchange = provider.exchange_code
    def slow_exchange(**kwargs):
        response = exchange(**kwargs)
        clock[0] += timedelta(seconds=301)
        return response
    provider.exchange_code = slow_exchange
    with pytest.raises(LoginRejected):
        service.finish(**request)


def test_provider_pkce_mismatch_cannot_establish_a_session(flow, config):
    service, provider, _, _ = flow
    _, _, request = callback(service, provider, config)
    provider.challenge = create_s256_code_challenge("different-synthetic-verifier" * 3)
    with pytest.raises(LoginRejected):
        service.finish(**request)
    assert len(provider.calls) == 1
    with pytest.raises(LoginRejected):
        service.finish(**request)
    assert len(provider.calls) == 1


def test_mutated_transaction_verifier_is_rejected_by_provider_pkce(flow, config):
    service, provider, _, _ = flow
    _, _, request = callback(service, provider, config)
    # Deliberately corrupt only the isolated server store. The synthetic provider
    # independently retains the original challenge from the authorization URL.
    pending = service._transactions._pending
    key, transaction = next(iter(pending.items()))
    pending[key] = replace(transaction, verifier="different-synthetic-verifier" * 3)
    with pytest.raises(LoginRejected):
        service.finish(**request)
    assert len(provider.calls) == 1


def test_requested_authentication_freshness_is_bound_to_authorization_url(config, signing_key):
    config = replace(config, max_auth_age_seconds=60)
    provider = FakeProvider(signing_key)
    sessions = SessionManager(InMemorySessionStore(), clock=lambda: NOW)
    service = LoginService(config, verifier(config, signing_key), InMemoryLoginTransactions(),
                           sessions, provider, clock=lambda: NOW)
    params = provider.bind(service.begin())
    assert params["max_age"] == ["60"]


@pytest.mark.parametrize("skew", [0, 30])
def test_expiration_at_the_exact_allowed_boundary_is_rejected(config, signing_key, skew):
    config = replace(config, clock_skew_seconds=skew)
    payload = claims(exp=int(NOW.timestamp()) - skew, iat=int(NOW.timestamp()) - 100)
    with pytest.raises(LoginRejected):
        verifier(config, signing_key).verify(signed(signing_key, payload), nonce=NONCE, now=NOW)


def test_transaction_store_unavailable_denies_without_provider_exchange(flow, config, caplog):
    service, provider, _, _ = flow
    _, _, request = callback(service, provider, config)
    class UnavailableStore:
        def create(self, *args):
            raise RuntimeError("private-store-diagnostic")
        def consume(self, **kwargs):
            raise RuntimeError("private-store-diagnostic")
    service._transactions = UnavailableStore()
    for operation in (service.begin, lambda: service.finish(**request)):
        with pytest.raises(LoginRejected) as error:
            operation()
        assert str(error.value) == "Sign-in rejected."
    assert "private-store-diagnostic" not in caplog.text
    assert provider.calls == []
