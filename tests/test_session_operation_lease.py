"""Synthetic session-operation serialization and pinned-dependency regressions."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic

import pytest

from src.server_sessions import (
    InMemorySessionStore, ServerSession, SessionManager, SessionStore, VerifiedSubject,
)
from src.session_identity_source import SessionIdentitySource


NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
SUBJECT = VerifiedSubject('https://session.synthetic.invalid', 'synthetic-reader', 'synthetic-client')
MANAGER_ERROR = '^Server session operation is unavailable\\.$'
SOURCE_ERROR = '^Session identity operation is unavailable\\.$'


@pytest.fixture
def context():
    clock = [NOW]
    store = InMemorySessionStore(operation_timeout_seconds=0.2)
    manager = SessionManager(store, clock=lambda: clock[0], idle_seconds=30, absolute_seconds=90)
    handle = manager.issue(SUBJECT)
    return clock, store, manager, handle


def source_for(manager, handle, clock):
    def database_factory():
        raise AssertionError('A session lease must not open a database or issue SQL authority.')
    return SessionIdentitySource(manager, handle, database_factory, clock=lambda: clock[0])


def test_manager_yields_only_immutable_internal_session_and_source_yields_no_authority(context):
    clock, _, manager, handle = context
    with manager.operation_lease(handle) as session:
        assert type(session) is ServerSession
        assert session == manager.authenticate(handle)
        assert session.session_id != handle
        with pytest.raises(FrozenInstanceError):
            session.subject = 'different-reader'
    with source_for(manager, handle, clock).session_operation() as authority:
        assert authority is None
    assert manager.revoke(handle) is True


@pytest.mark.parametrize('mutation', ['revoke', 'rotate'])
def test_operation_acquired_first_serializes_before_competing_session_mutation(context, mutation, monkeypatch):
    _, store, manager, handle = context
    attempted = Event()
    original = getattr(store, mutation)

    def competing(*args):
        attempted.set()
        return original(*args)

    monkeypatch.setattr(store, mutation, competing)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with manager.operation_lease(handle) as leased:
            pending = pool.submit(getattr(manager, mutation), handle)
            assert attempted.wait(1)
            with pytest.raises(TimeoutError):
                pending.result(timeout=0.05)
            assert manager.authenticate(handle) == leased
        result = pending.result(timeout=1)
    assert (result is True) if mutation == 'revoke' else (type(result) is str)
    assert manager.authenticate(handle) is None
    if mutation == 'rotate':
        assert manager.authenticate(result) is not None
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            pytest.fail('The old handle became usable after revocation or rotation.')


@pytest.mark.parametrize('mutation', ['revoke', 'rotate'])
def test_completed_session_mutation_before_acquisition_denies_old_handle(context, mutation):
    _, _, manager, handle = context
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(getattr(manager, mutation), handle).result(timeout=1)
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            pytest.fail('Pre-acquisition mutation was ignored.')
    if mutation == 'rotate':
        with manager.operation_lease(result) as session:
            assert session.subject == SUBJECT.subject


def test_same_thread_revoke_rotate_and_nested_leases_deny_without_mutation(context):
    _, store, manager, handle = context
    another = manager.issue(SUBJECT)
    with manager.operation_lease(handle) as original:
        records = dict(store._records)
        assert manager.revoke(handle) is False
        assert manager.rotate(handle) is None
        assert store._records == records
        for nested in (handle, another):
            with pytest.raises(PermissionError, match=MANAGER_ERROR):
                with manager.operation_lease(nested):
                    pytest.fail('A reentrant operation lease was admitted.')
        assert manager.authenticate(handle) == original
    assert not store._leased_keys
    assert manager.rotate(handle) is not None


@pytest.mark.parametrize('unsupported', ['missing', 'protocol-default'])
def test_stores_without_operation_coordination_deny(context, unsupported):
    _, store, manager, handle = context

    class AtomicOnly:
        def __getattr__(self, name):
            if name == 'operation_lease':
                raise AttributeError(name)
            return getattr(store, name)

    class DefaultDenyStore(AtomicOnly, SessionStore):
        pass

    manager._store = AtomicOnly() if unsupported == 'missing' else DefaultDenyStore()
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            pytest.fail('Atomic individual operations were treated as an operation lease.')


@pytest.mark.parametrize('handle', [None, True, '', '../invalid', 'A' * 43])
def test_missing_or_invalid_handle_never_enters_operation(context, handle):
    _, store, manager, _ = context
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            pytest.fail('Missing server session entered an operation.')
    assert not store._leased_keys


@pytest.mark.parametrize('dependency', ['_store', '_clock', '_idle', '_absolute'])
def test_manager_dependency_swap_during_operation_denies(context, dependency):
    _, store, manager, handle = context
    replacements = {'_store': InMemorySessionStore(), '_clock': lambda: NOW,
                    '_idle': 29, '_absolute': 89}
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            setattr(manager, dependency, replacements[dependency])
    assert not store._leased_keys
    assert store.revoke(manager._key(handle)) is True


@pytest.mark.parametrize('phase', ['entry', 'cleanup'])
def test_manager_pins_dependencies_across_store_entry_and_post_cleanup(context, phase, monkeypatch):
    _, store, manager, handle = context
    lease = store.operation_lease

    @contextmanager
    def changed(key):
        with lease(key):
            if phase == 'entry':
                manager._clock = lambda: NOW
            yield
        if phase == 'cleanup':
            manager._clock = lambda: NOW

    monkeypatch.setattr(store, 'operation_lease', changed)
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            pass
    assert not store._leased_keys


@pytest.mark.parametrize('dependency', ['_sessions', '_handle', '_database_sessions', '_clock'])
def test_identity_source_pins_server_dependencies(context, dependency):
    clock, store, manager, handle = context
    source = source_for(manager, handle, clock)
    replacements = {'_sessions': SessionManager(InMemorySessionStore(), clock=lambda: NOW),
                    '_handle': 'A' * 43, '_database_sessions': lambda: None,
                    '_clock': lambda: NOW}
    with pytest.raises(PermissionError, match=SOURCE_ERROR):
        with source.session_operation():
            setattr(source, dependency, replacements[dependency])
    assert not store._leased_keys
    assert manager.revoke(handle) is True


def test_identity_source_checks_dependencies_after_manager_cleanup(context, monkeypatch):
    clock, store, manager, handle = context
    source = source_for(manager, handle, clock)
    lease = store.operation_lease

    @contextmanager
    def changed(key):
        with lease(key):
            yield
        source._database_sessions = lambda: None

    monkeypatch.setattr(store, 'operation_lease', changed)
    with pytest.raises(PermissionError, match=SOURCE_ERROR):
        with source.session_operation():
            pass
    assert not store._leased_keys


def test_identity_source_rejects_request_shaped_identity_manager(context):
    clock, _, manager, handle = context
    session = manager.authenticate(handle)

    class IdentityStandIn:
        @contextmanager
        def operation_lease(self, supplied):
            assert supplied == handle
            yield session

    source = source_for(IdentityStandIn(), handle, clock)
    with pytest.raises(PermissionError, match=SOURCE_ERROR):
        with source.session_operation():
            pytest.fail('A copied session DTO was accepted as server authority.')


@pytest.mark.parametrize('expiry', ['idle', 'absolute', 'rollback'])
def test_clock_expiry_or_rollback_during_operation_denies_and_releases(context, expiry):
    clock, store, manager, handle = context
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            clock[0] = NOW + timedelta(seconds={'idle': 30, 'absolute': 90, 'rollback': -1}[expiry])
    assert not store._leased_keys
    assert manager.authenticate(handle) is None


def test_changed_server_session_record_during_operation_denies(context):
    _, store, manager, handle = context
    key = manager._key(handle)
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            store._records[key] = replace(store._records[key], session=replace(
                store._records[key].session, subject='another-synthetic-reader'))
    assert not store._leased_keys


def test_lock_acquisition_timeout_is_bounded_and_does_not_mutate_session(context):
    _, store, manager, handle = context
    entered, release = Event(), Event()

    def hold_lock():
        with store._lock:
            entered.set()
            assert release.wait(2)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(hold_lock)
        assert entered.wait(1)
        start = monotonic()
        try:
            with pytest.raises(PermissionError, match=MANAGER_ERROR):
                with manager.operation_lease(handle):
                    pytest.fail('An unavailable lease lock was bypassed.')
            assert monotonic() - start < 1
        finally:
            release.set()
        pending.result(timeout=1)
    assert not store._leased_keys
    assert manager.authenticate(handle) is not None


@pytest.mark.parametrize('operation', ['create', 'authenticate', 'revoke', 'rotate'])
def test_individual_store_operations_also_have_bounded_lock_waits(context, operation):
    _, store, manager, handle = context
    entered, release = Event(), Event()

    def hold_lock():
        with store._lock:
            entered.set()
            assert release.wait(2)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(hold_lock)
        assert entered.wait(1)
        start = monotonic()
        try:
            if operation == 'create':
                with pytest.raises(ValueError, match='^Server session could not be established\\.$'):
                    manager.issue(SUBJECT)
            else:
                result = getattr(manager, operation)(handle)
                assert result is (False if operation == 'revoke' else None)
            assert monotonic() - start < 1
        finally:
            release.set()
        pending.result(timeout=1)
    assert len(store._records) == 1
    assert manager.authenticate(handle) is not None


@pytest.mark.parametrize('timeout', [0, -1, 3.01, float('nan'), float('inf'), True, '0.1'])
def test_unbounded_or_invalid_operation_timeout_configuration_denies(timeout):
    with pytest.raises(ValueError, match='Invalid synthetic session-store configuration'):
        InMemorySessionStore(operation_timeout_seconds=timeout)


def test_exceptions_cleanup_lock_and_do_not_leak_error_details(context, caplog):
    clock, store, manager, handle = context
    marker = 'synthetic-sensitive-error-never-return'
    for operation, expected in ((manager.operation_lease(handle), MANAGER_ERROR),
                                (source_for(manager, handle, clock).session_operation(), SOURCE_ERROR)):
        with pytest.raises(PermissionError, match=expected) as error:
            with operation:
                raise RuntimeError(marker)
        assert marker not in str(error.value) and marker not in caplog.text
        assert not store._leased_keys
    assert manager.revoke(handle) is True


def test_store_cannot_suppress_failed_operation_and_claim_success(context, monkeypatch):
    _, store, manager, handle = context
    lease = store.operation_lease

    @contextmanager
    def suppressing(key):
        try:
            with lease(key):
                yield
        except PermissionError:
            pass

    monkeypatch.setattr(store, 'operation_lease', suppressing)
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle):
            raise RuntimeError('Synthetic failure')
    assert not store._leased_keys


@pytest.mark.parametrize('cleanup_phase', ['under-lease', 'after-lease'])
@pytest.mark.parametrize('expiry', ['idle', 'absolute', 'rollback'])
def test_store_cleanup_cannot_issue_session_after_expiry_or_clock_rollback(
        context, monkeypatch, cleanup_phase, expiry):
    clock, store, manager, handle = context
    lease = store.operation_lease
    offset = {'idle': 30, 'absolute': 90, 'rollback': -1}[expiry]

    @contextmanager
    def delayed_cleanup(key):
        with lease(key):
            yield
            if cleanup_phase == 'under-lease':
                clock[0] = NOW + timedelta(seconds=offset)
        if cleanup_phase == 'after-lease':
            clock[0] = NOW + timedelta(seconds=offset)

    monkeypatch.setattr(store, 'operation_lease', delayed_cleanup)
    with pytest.raises(PermissionError, match=MANAGER_ERROR):
        with manager.operation_lease(handle) as session:
            assert session == manager.authenticate(handle)
    assert not store._leased_keys
    assert manager.authenticate(handle) is None
