"""Private shared orchestration for the two unwired synthetic read proofs.

This preserves M7 Phase 2's SQL-before-session-lease order, dependency pinning,
commit-inside-lease and final cached deadline checks. It is not an endpoint,
persistence API or reusable authorization capability. Subclasses are trusted
server code; request data never selects a reader or authority implementation.
"""
from contextlib import ExitStack

from src.server_sessions import SessionManager
from src.session_identity_source import SessionIdentitySource


class _SessionLeasedRead:
    """Server-internal base; only fixed read-only subclasses provide a reader."""

    def __init__(self, session_factory=None, *, identity_source=None):
        self._sessions = session_factory
        self._identity_source = identity_source

    def _check(self, source, factory):
        if (type(source) is not SessionIdentitySource or factory is None
                or self._identity_source is not source or self._sessions is not factory
                or source._database_sessions is not factory):
            raise PermissionError("Leased read unavailable.")

    def _leased_read(self, target, permission, *, expected=None):
        try:
            source, factory = self._identity_source, self._sessions
            self._check(source, factory)
            manager, handle, source_clock = source._sessions, source._handle, source._clock
            if type(manager) is not SessionManager:
                raise PermissionError("Leased read unavailable.")
            store, clock, idle, absolute = manager._store, manager._clock, manager._idle, manager._absolute

            def pinned():
                # Pin inner dependencies before the initial SQL/source work as
                # well as during the later lease. Replacing one with an object
                # that returns identical identity fields cannot preserve scope.
                self._check(source, factory)
                if (source._sessions is not manager or source._handle != handle
                        or source._clock is not source_clock or manager._store is not store
                        or manager._clock is not clock or type(manager._idle) is not int
                        or manager._idle != idle or type(manager._absolute) is not int
                        or manager._absolute != absolute):
                    raise PermissionError("Leased read unavailable.")

            pinned()
            reader = self._reader_type(factory, source, target)
            # Existing tenant reads acquire SQL locks before their final session
            # lookup. Keep that order: acquire SQL authority first, then lease
            # the session and complete SQL while the lease is still held.
            with ExitStack() as database:
                session, scope = database.enter_context(
                    reader._authorized_transaction(permission))
                pinned()
                with source.session_operation():
                    pinned()
                    packet = scope.relationships[1]
                    if expected is not None and expected != packet:
                        raise PermissionError("Leased read unavailable.")
                    reader._finish_authorized(session, scope, permission)
                    pinned()
                    database.close()  # Commit/close SQL before releasing the lease.
                pinned()
            pinned()
            reader._finish_cached_windows(scope, permission)
            return packet  # Only after SQL completion and successful lease cleanup.
        except Exception:
            return None  # Uniform denial; no tokens, hidden metadata or provider errors.
