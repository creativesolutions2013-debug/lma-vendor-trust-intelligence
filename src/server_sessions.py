"""Unwired server-owned session core; the in-memory store is synthetic-only.

Only the trusted code-flow service may issue sessions after cryptographic token
validation. DTO creation is not authentication. No cookie, Streamlit state,
production store, login route, role claim or organization selector is used here.
"""
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from secrets import token_urlsafe
from threading import RLock
from typing import Protocol


def utc_now():
    return datetime.now(timezone.utc)


def _text(value):
    return type(value) is str and 0 < len(value) <= 500 and value == value.strip()


def _time(value):
    return (type(value) is datetime and value.tzinfo is not None
            and value.utcoffset() is not None)


@dataclass(frozen=True)
class VerifiedSubject:
    """Server-only verifier output, not a browser-accepted credential."""
    issuer: str
    subject: str
    audience: str


@dataclass(frozen=True)
class ServerSession:
    issuer: str
    subject: str
    audience: str
    session_id: str  # Separate correlation ID: never the bearer handle.
    issued_at: datetime
    expires_at: datetime  # Stable absolute deadline; idle expiry is separate.


@dataclass(frozen=True)
class _SessionRecord:
    key_digest: str = field(repr=False)
    session: ServerSession
    last_seen_at: datetime


def _valid(record, key, now, idle_seconds, absolute_seconds):
    if type(record) is not _SessionRecord or record.key_digest != key:
        return False
    s = record.session
    return (type(s) is ServerSession and _time(now)
            and all(_text(x) for x in (s.issuer, s.subject, s.audience, s.session_id))
            and re.fullmatch(r"sid_[A-Za-z0-9_-]{43}", s.session_id) is not None
            and all(_time(x) for x in (s.issued_at, s.expires_at, record.last_seen_at))
            and s.issued_at <= record.last_seen_at <= now < s.expires_at
            and now < record.last_seen_at + timedelta(seconds=idle_seconds)
            and s.expires_at - s.issued_at <= timedelta(seconds=absolute_seconds))


class SessionStore(Protocol):
    """Trusted server dependency; implementations must make each operation atomic."""
    def create(self, key, record, now) -> bool: ...
    def authenticate(self, key, now, idle_seconds, absolute_seconds) -> _SessionRecord | None: ...
    def revoke(self, key) -> bool: ...
    def rotate(self, key, new_key, session_id, now, idle_seconds, absolute_seconds) -> _SessionRecord | None: ...


class InMemorySessionStore:
    """Isolated, thread-safe synthetic proof; not persistent or multi-worker safe."""
    def __init__(self, *, capacity=1000):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Invalid synthetic session-store configuration.")
        self._records = {}
        self._lock = RLock()
        self._capacity = capacity

    def create(self, key, record, now):
        with self._lock:
            # Bounded synthetic memory. Never evict a current session to admit
            # another one; absolute expiry is sufficient for safe cleanup.
            for digest, old in list(self._records.items()):
                if (type(old) is not _SessionRecord or type(old.session) is not ServerSession
                        or not _time(old.session.expires_at) or old.session.expires_at <= now):
                    del self._records[digest]
            if key in self._records or len(self._records) >= self._capacity:
                return False
            self._records[key] = record
            return True

    def authenticate(self, key, now, idle_seconds, absolute_seconds):
        with self._lock:
            record = self._records.get(key)
            if not _valid(record, key, now, idle_seconds, absolute_seconds):
                self._records.pop(key, None)
                return None
            record = replace(record, last_seen_at=now)
            self._records[key] = record
            return record

    def revoke(self, key):
        with self._lock:
            return self._records.pop(key, None) is not None

    def rotate(self, key, new_key, session_id, now, idle_seconds, absolute_seconds):
        with self._lock:
            record = self._records.get(key)
            if not _valid(record, key, now, idle_seconds, absolute_seconds):
                self._records.pop(key, None)
                return None
            if new_key in self._records:
                return None
            rotated = _SessionRecord(new_key, replace(record.session, session_id=session_id), now)
            del self._records[key]
            self._records[new_key] = rotated
            return rotated


class SessionManager:
    """Revalidate server storage on every request; deny on unavailable storage.

    ``issue`` is a trusted internal operation after the OIDC code-flow verifier,
    never a public endpoint accepting a VerifiedSubject dataclass from a client.
    """
    def __init__(self, store: SessionStore, *, clock=utc_now, idle_seconds=300, absolute_seconds=1800):
        if (type(idle_seconds) is not int or type(absolute_seconds) is not int
                or not 1 <= idle_seconds <= absolute_seconds <= 86400 or not callable(clock)):
            raise ValueError("Invalid server-session configuration.")
        self._store, self._clock = store, clock
        self._idle, self._absolute = idle_seconds, absolute_seconds

    @staticmethod
    def _key(handle):
        if type(handle) is not str or re.fullmatch(r"[A-Za-z0-9_-]{43}", handle) is None:
            return None
        return sha256(handle.encode("ascii")).hexdigest()

    def issue(self, identity: VerifiedSubject) -> str:
        try:
            if (type(identity) is not VerifiedSubject
                    or not all(_text(x) for x in (identity.issuer, identity.subject, identity.audience))):
                raise ValueError
            now = self._clock()
            if not _time(now):
                raise ValueError
            handle = token_urlsafe(32)
            key = self._key(handle)
            session = ServerSession(identity.issuer, identity.subject, identity.audience,
                                    "sid_" + token_urlsafe(32), now,
                                    now + timedelta(seconds=self._absolute))
            if not self._store.create(key, _SessionRecord(key, session, now), now):
                raise ValueError
            if self.authenticate(handle) != session:
                self.revoke(handle)
                raise ValueError
            return handle
        except Exception:
            raise ValueError("Server session could not be established.") from None

    def authenticate(self, handle) -> ServerSession | None:
        try:
            key = self._key(handle)
            if key is None:
                return None
            record = self._store.authenticate(key, self._clock(), self._idle, self._absolute)
            if not _valid(record, key, self._clock(), self._idle, self._absolute):
                self._store.revoke(key)
                return None
            return record.session
        except Exception:
            return None

    def revoke(self, handle) -> bool:
        try:
            key = self._key(handle)
            return key is not None and self._store.revoke(key) is True
        except Exception:
            return False

    def rotate(self, handle) -> str | None:
        try:
            key = self._key(handle)
            if key is None:
                return None
            new_handle = token_urlsafe(32)
            new_key = self._key(new_handle)
            record = self._store.rotate(key, new_key, "sid_" + token_urlsafe(32),
                                        self._clock(), self._idle, self._absolute)
            if not _valid(record, new_key, self._clock(), self._idle, self._absolute):
                self._store.revoke(new_key)
                return None
            return new_handle
        except Exception:
            return None
