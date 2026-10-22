"""Unwired OIDC code/session core. No HTTP, discovery, cookies or app registration.

Provider configuration, pinned JWKS, stores and exchange client are trusted server
dependencies. The only exchange client in this milestone is synthetic. This is
not hosted SSO; production startup continues to refuse authentication.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from threading import Lock
from typing import Protocol
from urllib.parse import urlsplit

from authlib.oauth2 import OAuth2Client
from joserfc import jwt
from joserfc.jwk import KeySet

from src.server_sessions import VerifiedSubject


class LoginRejected(ValueError):
    def __init__(self):
        super().__init__("Sign-in rejected.")


def _text(value, limit=2048):
    return (type(value) is str and 0 < len(value) <= limit
            and value == value.strip() and not any(ord(c) < 33 for c in value))


def _https(value):
    if not _text(value) or "\\" in value:
        return False
    parsed = urlsplit(value)
    return (parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None
            and parsed.password is None and not parsed.query and not parsed.fragment
            and parsed.port in (None, 443))


def _now(clock):
    value = clock()
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise LoginRejected()
    return value.astimezone(timezone.utc)


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderConfig:
    issuer: str
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    redirect_uri: str
    algorithms: tuple[str, ...] = ("RS256",)
    clock_skew_seconds: int = 30
    max_token_age_seconds: int = 600
    max_auth_age_seconds: int | None = None

    def __post_init__(self):
        try:
            valid = (all(_https(x) for x in (self.issuer, self.authorization_endpoint,
                     self.token_endpoint, self.jwks_uri, self.redirect_uri))
                     and _text(self.client_id, 255)
                     and type(self.algorithms) is tuple and bool(self.algorithms)
                     and len(set(self.algorithms)) == len(self.algorithms)
                     and set(self.algorithms) <= {"RS256", "ES256"}
                     and type(self.clock_skew_seconds) is int and 0 <= self.clock_skew_seconds <= 60
                     and type(self.max_token_age_seconds) is int and 1 <= self.max_token_age_seconds <= 3600
                     and (self.max_auth_age_seconds is None or (type(self.max_auth_age_seconds) is int
                          and 1 <= self.max_auth_age_seconds <= 3600)))
        except Exception:
            valid = False
        if not valid:
            raise ValueError("Invalid trusted provider configuration.")


class IDTokenVerifier:
    """JOSE verification using joserfc, with an immutable issuer-pinned key snapshot.

    No discovery/URL fetching. Rotation requires a new independently validated
    key snapshot; token headers cannot add keys or choose the provider.
    """
    def __init__(self, config: ProviderConfig, trusted_jwks: dict):
        try:
            if type(config) is not ProviderConfig or type(trusted_jwks) is not dict:
                raise ValueError()
            keys = json.loads(json.dumps(trusted_jwks))["keys"]
            if type(keys) is not list or not 1 <= len(keys) <= 20:
                raise ValueError()
            kids = set()
            for key in keys:
                if (type(key) is not dict or not _text(key.get("kid"), 255)
                        or key["kid"] in kids or key.get("kty") not in {"RSA", "EC"}
                        or key.get("use", "sig") != "sig"
                        or key.get("key_ops", ["verify"]) != ["verify"]
                        or any(x in key for x in ("d", "p", "q", "dp", "dq", "qi", "oth", "k"))):
                    raise ValueError()
                alg = "RS256" if key["kty"] == "RSA" else "ES256"
                if alg not in config.algorithms or key.get("alg", alg) != alg:
                    raise ValueError()
                if key["kty"] == "EC" and key.get("crv") != "P-256":
                    raise ValueError()
                kids.add(key["kid"])
            self._keys = KeySet.import_key_set({"keys": keys})
            if any(key.key_type == "RSA" and key.raw_value.key_size < 2048 for key in self._keys.keys):
                raise ValueError()
            self._key_algorithms = {k["kid"]: "RS256" if k["kty"] == "RSA" else "ES256" for k in keys}
            self.config = config
        except Exception:
            raise ValueError("Invalid trusted signing keys.") from None

    def _resolve_key(self, signature):
        header = signature.headers()
        # Library parsing handles compact JOSE. Never follow jku/x5u, embedded
        # jwk, unsupported critical extensions or algorithm-selected key types.
        if (set(header) - {"alg", "kid", "typ"} or not _text(header.get("kid"), 255)
                or header.get("alg") not in self.config.algorithms
                or self._key_algorithms.get(header["kid"]) != header["alg"]
                or header.get("typ", "JWT") != "JWT"):
            raise LoginRejected()
        return self._keys.get_by_kid(header["kid"])

    def verify(self, id_token, *, nonce, now):
        try:
            if not _text(id_token, 16384) or not _text(nonce, 255):
                raise LoginRejected()
            now = _now(lambda: now)
            token = jwt.decode(id_token, self._resolve_key, algorithms=list(self.config.algorithms))
            claims = token.claims
            if type(claims) is not dict:
                raise LoginRejected()
            for name in ("exp", "iat"):
                if type(claims.get(name)) is not int or claims[name] < 0:
                    raise LoginRejected()
            for name in ("nbf", "auth_time"):
                if name in claims and (type(claims[name]) is not int or claims[name] < 0):
                    raise LoginRejected()
            jwt.JWTClaimsRegistry(
                now=int(now.timestamp()), leeway=self.config.clock_skew_seconds,
                iss={"essential": True, "value": self.config.issuer},
                sub={"essential": True}, aud={"essential": True},
                exp={"essential": True}, iat={"essential": True},
                nonce={"essential": True, "value": nonce},
            ).validate(claims)
            audience = claims["aud"]
            audiences = [audience] if type(audience) is str else audience
            if (type(audiences) is not list or not audiences
                    or not all(_text(x, 255) for x in audiences)
                    or len(set(audiences)) != len(audiences)
                    or self.config.client_id not in audiences
                    or (len(audiences) > 1 and "azp" not in claims)
                    or ("azp" in claims and claims["azp"] != self.config.client_id)
                    or not _text(claims["sub"], 255)
                    or type(claims["iss"]) is not str or type(claims["nonce"]) is not str):
                raise LoginRejected()
            stamp = now.timestamp()
            skew = self.config.clock_skew_seconds
            if (claims["exp"] <= claims["iat"] or stamp >= claims["exp"] + skew
                    or claims["exp"] - claims["iat"] > self.config.max_token_age_seconds
                    or stamp - claims["iat"] > self.config.max_token_age_seconds + skew
                    or ("nbf" in claims and claims["nbf"] >= claims["exp"])):
                raise LoginRejected()
            auth_time = claims.get("auth_time")
            if (auth_time is not None and (auth_time > stamp + skew or auth_time > claims["iat"])):
                raise LoginRejected()
            if self.config.max_auth_age_seconds is not None and (
                    auth_time is None or stamp - auth_time > self.config.max_auth_age_seconds + skew):
                raise LoginRejected()
            # Ignore every display/email/role/group/org claim for authorization.
            return VerifiedSubject(self.config.issuer, claims["sub"], self.config.client_id)
        except Exception:
            raise LoginRejected() from None


@dataclass(frozen=True, repr=False)
class _Transaction:
    config: ProviderConfig
    nonce: str
    verifier: str
    binding_digest: str
    expires_at: datetime


@dataclass(frozen=True)
class LoginStart:
    authorization_url: str = field(repr=False)
    browser_binding: str = field(repr=False)


class InMemoryLoginTransactions:
    """Bounded atomic synthetic store, not a distributed production replay store."""
    def __init__(self, *, ttl_seconds=300, capacity=1000):
        if (type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300
                or type(capacity) is not int or not 1 <= capacity <= 10000):
            raise ValueError("Invalid transaction store configuration.")
        self._ttl = ttl_seconds
        self._capacity = capacity
        self._pending = {}
        self._codes = {}
        self._lock = Lock()

    def _prune(self, now):
        self._pending = {k: v for k, v in self._pending.items() if v.expires_at > now}
        self._codes = {k: v for k, v in self._codes.items() if v > now}

    def create(self, config, now):
        with self._lock:
            self._prune(now)
            if len(self._pending) + len(self._codes) >= self._capacity:
                raise LoginRejected()
            state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            transaction = _Transaction(config, secrets.token_urlsafe(32), secrets.token_urlsafe(48),
                                       _digest(binding), now + timedelta(seconds=self._ttl))
            if _digest(state) in self._pending:
                raise LoginRejected()
            self._pending[_digest(state)] = transaction
            return state, binding, transaction

    def consume(self, *, state, binding, config, issuer, redirect_uri, code, now):
        with self._lock:
            self._prune(now)
            transaction = self._pending.pop(_digest(state), None)
            code_digest = _digest(json.dumps([config.issuer, code]))
            if (type(transaction) is not _Transaction or transaction.config != config
                    or not secrets.compare_digest(transaction.binding_digest, _digest(binding))
                    or issuer != config.issuer or redirect_uri != config.redirect_uri
                    or code_digest in self._codes):
                raise LoginRejected()
            # Consume before exchange, including failed exchanges. Code cache is
            # bounded to 15 minutes; a future provider must enforce code one-use
            # and a shorter lifetime too. Nonces remain transaction-specific.
            self._codes[code_digest] = now + timedelta(minutes=15)
            return transaction


class ProviderClient(Protocol):
    """Trusted exchange dependency. No live implementation/configuration here."""
    def exchange_code(self, *, token_endpoint, client_id, redirect_uri, code, code_verifier) -> dict: ...


class LoginService:
    def __init__(self, config, verifier, transactions, sessions, provider_client, *,
                 clock=lambda: datetime.now(timezone.utc)):
        if type(config) is not ProviderConfig or verifier.config != config:
            raise ValueError("Invalid trusted login configuration.")
        self._config, self._verifier, self._transactions = config, verifier, transactions
        self._sessions, self._provider, self._clock = sessions, provider_client, clock

    def begin(self):
        try:
            state, binding, transaction = self._transactions.create(self._config, _now(self._clock))
            client = OAuth2Client(None, client_id=self._config.client_id, scope="openid",
                                  redirect_uri=self._config.redirect_uri, code_challenge_method="S256")
            extras = {"nonce": transaction.nonce}
            if self._config.max_auth_age_seconds is not None:
                extras["max_age"] = self._config.max_auth_age_seconds
            url, _ = client.create_authorization_url(self._config.authorization_endpoint,
                state=state, code_verifier=transaction.verifier, **extras)
            return LoginStart(url, binding)
        except Exception:
            raise LoginRejected() from None

    def finish(self, *, state, code, issuer, redirect_uri, browser_binding):
        try:
            if not all(_text(x) for x in (state, code, issuer, redirect_uri, browser_binding)):
                raise LoginRejected()
            transaction = self._transactions.consume(state=state, binding=browser_binding,
                config=self._config, issuer=issuer, redirect_uri=redirect_uri, code=code, now=_now(self._clock))
            tokens = self._provider.exchange_code(token_endpoint=self._config.token_endpoint,
                client_id=self._config.client_id, redirect_uri=self._config.redirect_uri,
                code=code, code_verifier=transaction.verifier)
            now = _now(self._clock)
            if now >= transaction.expires_at or type(tokens) is not dict:
                raise LoginRejected()
            subject = self._verifier.verify(tokens.get("id_token"), nonce=transaction.nonce, now=now)
            return self._sessions.issue(subject)
        except Exception:
            raise LoginRejected() from None
