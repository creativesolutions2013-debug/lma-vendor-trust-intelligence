"""Fixed, in-process signed IdP for the isolated HTTPS loopback analyst pilot.

This is one synthetic account, never a production provider or browser-selected
identity/role. The HTTP surface owns TLS, exact Host/Origin, cookies, bounded
parsing and response headers. No password, signing key, code or session is
persisted or logged here. Restart discards authentication, not assessment SQL.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256, scrypt
import hmac
import json
import re
import secrets
from threading import RLock
from urllib.parse import parse_qsl, urlencode, urlsplit

from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.jwk import RSAKey

from src.oidc_login import (
    IDTokenVerifier, InMemoryLoginTransactions, LoginRejected, LoginService, ProviderConfig,
)
from src.server_sessions import InMemorySessionStore, ServerSession, SessionManager, utc_now


_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_CSRF = re.compile(r"[0-9a-f]{64}")
_AUTH_FIELDS = frozenset(("response_type", "client_id", "redirect_uri", "scope", "state", "nonce",
                          "code_challenge", "code_challenge_method"))
_CAPACITY = 1000
_LOGIN_SECONDS = 300
_CODE_SECONDS = 60
_ATTEMPTS = 5
_ATTEMPT_SECONDS = 60


def _token(value):
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def _digest(value):
    return sha256(value.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class _Start:
    parameters: tuple
    binding_digest: str
    expires_at: datetime
    authorization_used: bool = False


@dataclass(frozen=True)
class _Code:
    nonce: str
    challenge: str
    expires_at: datetime


class _SyntheticProvider:
    """Trusted direct exchange; no HTTP token endpoint or remote key fetching."""
    def __init__(self, owner):
        self._owner = owner

    def exchange_code(self, *, token_endpoint, client_id, redirect_uri, code, code_verifier):
        return self._owner._exchange(token_endpoint, client_id, redirect_uri, code, code_verifier)


class SyntheticPilotIdentity:
    """One operator-password synthetic account, using the existing OIDC core.

    Callers may select candidates and submit the password; only this server owns
    subject, issuer, keys, provider, session manager and authorization settings.
    The entry point must additionally require explicit development mode and TLS
    bound to 127.0.0.1. CSRF values are never identity or tenant authority.
    """
    def __init__(self, port, password, *, clock=utc_now):
        try:
            encoded = password.encode("utf-8") if type(password) is str else b""
            if (type(port) is not int or not 1024 <= port <= 65535 or not callable(clock)
                    or not 16 <= len(encoded) <= 256 or not password.strip()
                    or any(ord(char) < 32 or ord(char) == 127 for char in password)):
                raise ValueError
            self._origin = f"https://127.0.0.1:{port}"
            self._clock = clock
            self._lock = RLock()
            self._last_checked = self._now()
            self._salt = secrets.token_bytes(16)
            self._password_digest = self._password_hash(encoded)
            self._csrf_key = secrets.token_bytes(32)
            self._starts = {}
            self._codes = {}
            self._attempts = []
            self._config = ProviderConfig(
                issuer=self._origin + "/synthetic-idp", client_id="lma-synthetic-analyst",
                authorization_endpoint=self._origin + "/synthetic-idp/authorize",
                token_endpoint=self._origin + "/synthetic-idp/token",
                jwks_uri=self._origin + "/synthetic-idp/jwks",
                redirect_uri=self._origin + "/oidc/callback", synthetic_loopback_port=port,
                clock_skew_seconds=0, max_token_age_seconds=120,
            )
            self._key = RSAKey.generate_key(2048, {"kid": "synthetic-pilot-key", "alg": "RS256", "use": "sig"})
            verifier = IDTokenVerifier(self._config, {"keys": [self._key.as_dict(private=False)]})
            self._sessions = SessionManager(InMemorySessionStore(), clock=clock)
            self._login = LoginService(self._config, verifier, InMemoryLoginTransactions(),
                self._sessions, _SyntheticProvider(self), clock=clock)
        except Exception:
            raise ValueError("Invalid synthetic pilot identity configuration.") from None

    @property
    def origin(self):
        return self._origin

    @property
    def config(self):
        return self._config

    @property
    def sessions(self):
        return self._sessions

    @property
    def clock(self):
        return self._clock

    def _now(self):
        value = self._clock()
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise LoginRejected()
        return value.astimezone(timezone.utc)

    def _prune(self, now):
        if now < self._last_checked:
            raise LoginRejected()
        self._last_checked = now
        self._starts = {key: value for key, value in self._starts.items() if value.expires_at > now}
        self._codes = {key: value for key, value in self._codes.items() if value.expires_at > now}
        self._attempts = [stamp for stamp in self._attempts if stamp + timedelta(seconds=_ATTEMPT_SECONDS) > now]

    def _password_hash(self, encoded):
        return scrypt(encoded, salt=self._salt, n=16384, r=8, p=1, dklen=32)

    def _csrf(self, purpose, binding, parameters=None):
        if not _token(binding):
            raise LoginRejected()
        context = json.dumps([purpose, binding, parameters], sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("ascii")
        return hmac.new(self._csrf_key, context, sha256).hexdigest()

    @staticmethod
    def _valid_csrf_value(value):
        return type(value) is str and _CSRF.fullmatch(value) is not None

    def browser_csrf(self, binding):
        """Bind the anonymous sign-in POST to its server-created browser cookie."""
        return self._csrf("anonymous-browser", binding)

    def valid_browser_csrf(self, binding, token):
        try:
            return self._valid_csrf_value(token) and hmac.compare_digest(token, self.browser_csrf(binding))
        except Exception:
            return False

    def csrf_token(self, handle):
        if not _token(handle) or type(self._sessions.authenticate(handle)) is not ServerSession:
            raise LoginRejected()
        return self._csrf("authenticated-session", handle)

    def valid_csrf(self, handle, token):
        try:
            return (self._valid_csrf_value(token)
                    and hmac.compare_digest(token, self._csrf("authenticated-session", handle))
                    and type(self._sessions.authenticate(handle)) is ServerSession)
        except Exception:
            return False

    def logout(self, handle):
        return _token(handle) and self._sessions.revoke(handle) is True

    def _parameters(self, params):
        if (type(params) is not dict or set(params) != _AUTH_FIELDS
                or any(type(value) is not str for value in params.values())
                or params["response_type"] != "code" or params["client_id"] != self._config.client_id
                or params["redirect_uri"] != self._config.redirect_uri or params["scope"] != "openid"
                or params["code_challenge_method"] != "S256"
                or any(not _token(params[field]) for field in ("state", "nonce", "code_challenge"))):
            raise LoginRejected()
        return tuple(sorted(params.items()))

    def _start(self, params, binding, now, *, unused):
        parameters = self._parameters(params)
        if not _token(binding):
            raise LoginRejected()
        self._prune(now)
        start = self._starts.get(_digest(params["state"]))
        if (type(start) is not _Start or start.parameters != parameters
                or not hmac.compare_digest(start.binding_digest, _digest(binding))
                or unused and start.authorization_used):
            raise LoginRejected()
        return start

    def begin_login(self):
        try:
            with self._lock:
                now = self._now()
                self._prune(now)
                if len(self._starts) >= _CAPACITY:
                    raise LoginRejected()
                started = self._login.begin()
                parsed = urlsplit(started.authorization_url)
                if parsed.scheme + "://" + parsed.netloc + parsed.path != self._config.authorization_endpoint:
                    raise LoginRejected()
                pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=16)
                params = dict(pairs)
                if len(params) != len(pairs) or not _token(started.browser_binding):
                    raise LoginRejected()
                parameters = self._parameters(params)
                key = _digest(params["state"])
                if key in self._starts:
                    raise LoginRejected()
                self._starts[key] = _Start(parameters, _digest(started.browser_binding),
                                           now + timedelta(seconds=_LOGIN_SECONDS))
                return started
        except Exception:
            raise LoginRejected() from None

    def provider_form_token(self, params, binding):
        try:
            with self._lock:
                start = self._start(params, binding, self._now(), unused=True)
                return self._csrf("synthetic-provider", binding, start.parameters)
        except Exception:
            raise LoginRejected() from None

    def authorize(self, params, binding, password, csrf_token):
        """Check the local fixture password, then issue one short PKCE-bound code."""
        try:
            with self._lock:
                now = self._now()
                start = self._start(params, binding, now, unused=True)
                if (not self._valid_csrf_value(csrf_token) or not hmac.compare_digest(
                        csrf_token, self._csrf("synthetic-provider", binding, start.parameters))
                        or len(self._attempts) >= _ATTEMPTS or len(self._codes) >= _CAPACITY):
                    raise LoginRejected()
                self._attempts.append(now)
                encoded = password.encode("utf-8") if type(password) is str else b""
                if (not 16 <= len(encoded) <= 256 or not hmac.compare_digest(
                        self._password_hash(encoded), self._password_digest)):
                    raise LoginRejected()
                code = secrets.token_urlsafe(32)
                digest = _digest(code)
                if not _token(code) or digest in self._codes:
                    raise LoginRejected()
                self._codes[digest] = _Code(params["nonce"], params["code_challenge"],
                                           min(start.expires_at, now + timedelta(seconds=_CODE_SECONDS)))
                self._starts[_digest(params["state"])] = replace(start, authorization_used=True)
                return self._config.redirect_uri + "?" + urlencode({
                    "state": params["state"], "code": code, "iss": self._config.issuer})
        except Exception:
            raise LoginRejected() from None

    def _exchange(self, endpoint, client_id, redirect_uri, code, verifier):
        if (endpoint != self._config.token_endpoint or client_id != self._config.client_id
                or redirect_uri != self._config.redirect_uri or not _token(code)
                or type(verifier) is not str or re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier) is None):
            raise LoginRejected()
        with self._lock:
            now = self._now()
            self._prune(now)
            recorded = self._codes.pop(_digest(code), None)
            if (type(recorded) is not _Code or not hmac.compare_digest(
                    recorded.challenge, create_s256_code_challenge(verifier))):
                raise LoginRejected()
            stamp = int(now.timestamp())
            token = jwt.encode({"alg": "RS256", "kid": "synthetic-pilot-key"}, {
                "iss": self._config.issuer, "sub": "synthetic-analyst", "aud": self._config.client_id,
                "iat": stamp, "exp": stamp + _CODE_SECONDS, "nonce": recorded.nonce,
            }, self._key)
            return {"id_token": token}

    def finish_login(self, params, binding):
        try:
            if (type(params) is not dict or set(params) != {"state", "code", "iss"}
                    or not _token(params["state"]) or not _token(params["code"])
                    or type(params["iss"]) is not str or params["iss"] != self._config.issuer
                    or not _token(binding)):
                raise LoginRejected()
            with self._lock:
                self._prune(self._now())
                start = self._starts.pop(_digest(params["state"]), None)
                if (type(start) is not _Start or not start.authorization_used
                        or not hmac.compare_digest(start.binding_digest, _digest(binding))):
                    raise LoginRejected()
            return self._login.finish(state=params["state"], code=params["code"], issuer=params["iss"],
                redirect_uri=self._config.redirect_uri, browser_binding=binding)
        except Exception:
            raise LoginRejected() from None
