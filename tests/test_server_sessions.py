"""Synthetic server-session lifecycle and storage failure regressions."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from src.server_sessions import InMemorySessionStore, SessionManager, VerifiedSubject


NOW = datetime(2026, 10, 21, 23, 0, tzinfo=timezone.utc)
SUBJECT = VerifiedSubject("https://issuer.synthetic.invalid", "synthetic-subject", "synthetic-client")


@pytest.fixture
def context():
    clock = [NOW]
    store = InMemorySessionStore()
    manager = SessionManager(store, clock=lambda: clock[0], idle_seconds=30, absolute_seconds=90)
    handle = manager.issue(SUBJECT)
    return clock, store, manager, handle


def test_only_hashes_are_stored_and_identity_has_separate_non_bearer_id(context):
    _, store, manager, handle = context
    session = manager.authenticate(handle)
    assert list(store._records) == [sha256(handle.encode()).hexdigest()]
    assert handle not in repr(store._records)
    assert session.session_id != handle and manager.authenticate(session.session_id) is None
    assert session.issuer == SUBJECT.issuer and session.subject == SUBJECT.subject
    assert session.audience == SUBJECT.audience


def test_sliding_idle_window_never_changes_identity_or_absolute_deadline(context):
    clock, _, manager, handle = context
    initial = manager.authenticate(handle)
    for seconds in (20, 40, 60, 80, 89):
        clock[0] = NOW + timedelta(seconds=seconds)
        assert manager.authenticate(handle) == initial
    clock[0] = NOW + timedelta(seconds=90)
    assert manager.authenticate(handle) is None


def test_idle_expiry_is_exact_and_not_revived(context):
    clock, _, manager, handle = context
    clock[0] = NOW + timedelta(seconds=30)
    assert manager.authenticate(handle) is None
    clock[0] = NOW
    assert manager.authenticate(handle) is None


def test_clock_rollback_denies(context):
    clock, _, manager, handle = context
    clock[0] -= timedelta(seconds=1)
    assert manager.authenticate(handle) is None


def test_logout_revokes_and_cannot_be_reused(context):
    _, _, manager, handle = context
    assert manager.revoke(handle)
    assert manager.authenticate(handle) is None
    assert not manager.revoke(handle)
    assert manager.rotate(handle) is None


def test_rotation_invalidates_old_handle_and_preserves_absolute_expiry(context):
    clock, _, manager, handle = context
    original = manager.authenticate(handle)
    clock[0] += timedelta(seconds=20)
    rotated = manager.rotate(handle)
    assert rotated and rotated != handle
    assert manager.authenticate(handle) is None
    session = manager.authenticate(rotated)
    assert session.session_id != original.session_id
    assert (session.issued_at, session.expires_at) == (original.issued_at, original.expires_at)


def test_concurrent_rotations_have_one_winner(context):
    _, _, manager, handle = context
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: manager.rotate(handle), range(20)))
    winners = [x for x in results if x is not None]
    assert len(winners) == 1
    assert manager.authenticate(handle) is None
    assert manager.authenticate(winners[0]) is not None


@pytest.mark.parametrize("handle", [None, True, 1, {}, "", "a" * 42, "a" * 44, "../" + "a" * 40,
                                    "a" * 43, "a" * 10000])
def test_fabricated_or_malformed_handles_deny(context, handle):
    _, _, manager, _ = context
    assert manager.authenticate(handle) is None
    assert manager.rotate(handle) is None
    assert not manager.revoke(handle)


@pytest.mark.parametrize("corruption", ["object", "wrong_digest", "wrong_session", "naive_time", "future_time",
                                        "empty_subject", "bad_id", "extended_expiry", "wrong_time_type"])
def test_corrupted_records_deny_and_are_removed(context, corruption):
    _, store, manager, handle = context
    key = manager._key(handle)
    row = store._records[key]
    changes = {
        "object": object(),
        "wrong_digest": replace(row, key_digest="0" * 64),
        "wrong_session": replace(row, session={"role": "Admin"}),
        "naive_time": replace(row, last_seen_at=NOW.replace(tzinfo=None)),
        "future_time": replace(row, last_seen_at=NOW + timedelta(seconds=1)),
        "empty_subject": replace(row, session=replace(row.session, subject="")),
        "bad_id": replace(row, session=replace(row.session, session_id=handle)),
        "extended_expiry": replace(row, session=replace(row.session, expires_at=NOW + timedelta(days=1))),
        "wrong_time_type": replace(row, session=replace(row.session, issued_at=True)),
    }
    store._records[key] = changes[corruption]
    assert manager.authenticate(handle) is None
    assert key not in store._records


def test_slow_storage_cannot_return_expired_session(context, monkeypatch):
    clock, store, manager, handle = context
    authenticate = store.authenticate
    def slow(*args):
        row = authenticate(*args)
        clock[0] += timedelta(seconds=30)
        return row
    monkeypatch.setattr(store, "authenticate", slow)
    assert manager.authenticate(handle) is None


@pytest.mark.parametrize("method", ["create", "authenticate", "rotate", "revoke"])
def test_store_outage_fails_closed_without_error_leakage(context, monkeypatch, caplog, method):
    _, store, manager, handle = context
    secret = "provider-secret-error-do-not-log"
    def unavailable(*args):
        raise RuntimeError(secret)
    monkeypatch.setattr(store, method, unavailable)
    if method == "create":
        with pytest.raises(ValueError, match="^Server session could not be established.$") as error:
            manager.issue(SUBJECT)
        assert secret not in str(error.value)
    elif method == "authenticate":
        assert manager.authenticate(handle) is None
    elif method == "rotate":
        assert manager.rotate(handle) is None
    else:
        assert manager.revoke(handle) is False
    assert secret not in caplog.text and handle not in caplog.text


def test_capacity_does_not_evict_valid_session_and_expiry_releases_capacity():
    clock = [NOW]
    store = InMemorySessionStore(capacity=1)
    manager = SessionManager(store, clock=lambda: clock[0], idle_seconds=1, absolute_seconds=2)
    original = manager.issue(SUBJECT)
    with pytest.raises(ValueError, match="Server session could not be established"):
        manager.issue(SUBJECT)
    assert manager.authenticate(original) is not None
    clock[0] += timedelta(seconds=2)
    assert manager.issue(SUBJECT) != original


@pytest.mark.parametrize("identity", [None, {"issuer": SUBJECT.issuer, "subject": "attacker", "role": "Admin"},
                                      VerifiedSubject("", "a", "b"), VerifiedSubject("a", True, "b")])
def test_client_shaped_identity_is_not_accepted_by_internal_issuance(identity):
    manager = SessionManager(InMemorySessionStore(), clock=lambda: NOW)
    with pytest.raises(ValueError, match="^Server session could not be established.$"):
        manager.issue(identity)


@pytest.mark.parametrize("idle,absolute", [(True, 300), (0, 300), (301, 300), (300, 86401), (1, False)])
def test_invalid_session_configuration_rejected(idle, absolute):
    with pytest.raises(ValueError, match="Invalid server-session configuration"):
        SessionManager(InMemorySessionStore(), idle_seconds=idle, absolute_seconds=absolute)
