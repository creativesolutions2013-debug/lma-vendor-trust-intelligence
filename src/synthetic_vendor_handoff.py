"""Bounded process-local vendor delivery, separate from analyst byte custody.

An invitation never grants analyst permissions. Delivery uses an independent
vendor session and the live analyst's locked sponsorship; explicit analyst
capture is a later operation. Restart discards this inbox, never immutable originals. A
failed or ambiguous capture must not be blindly restaged or cleaned up.
"""
from dataclasses import dataclass, field, replace
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import re
import secrets
from threading import RLock
from uuid import uuid4

from src.authz import (
    PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_READ,
)
from src.resumable_assessment import _Command, _RevisionReader
from src.resumable_assessment_state import _intake
from src.server_sessions import SessionManager, ServerSession, utc_now
from src.session_identity_source import SessionIdentitySource
from src.session_leased_read import _SessionLeasedRead
from src.synthetic_evidence_custody import SyntheticEvidenceReceipt
from src.upload_assessment import read_upload, risk_and_applicability


_ANALYST = (PERMISSION_ASSESSMENT_MANAGE, PERMISSION_EVIDENCE_READ)
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_MAX_RECORDS = 32


@dataclass(frozen=True)
class IssuedInvitation:
    invitation_id: str
    token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class PendingSubmission:
    invitation_id: str
    assessment_id: int
    expected_revision: int
    requirement_id: str
    filename: str
    content: bytes = field(repr=False)
    sha256: str
    byte_length: int
    kind: str
    observed_on: date | None
    submitted_at: datetime
    vendor_issuer: str
    vendor_subject: str
    vendor_session_id: str
    vendor_role: str
    inviter_issuer: str
    inviter_subject: str
    inviter_session_id: str
    receipt: SyntheticEvidenceReceipt | None = None


@dataclass(frozen=True)
class InvitationSummary:
    invitation_id: str
    status: str
    requirement_id: str
    expires_at: datetime
    filename: str | None
    sha256: str | None


@dataclass(frozen=True)
class _Snapshot:
    relation: tuple
    head: tuple
    authority: tuple
    issuer: str
    subject: str
    session_id: str
    context_sha256: str
    requirements: tuple
    inventory: tuple
    parents: tuple


@dataclass(frozen=True)
class _Record:
    schema_version: int
    invitation_id: str
    token_digest: str = field(repr=False)
    expires_at: datetime
    requirement_id: str
    inviter: _Snapshot
    status: str = "issued"
    pending: PendingSubmission | None = None
    capture_active: bool = False


def _context(packet):
    intake = dict(packet["intake"])
    intake.pop("as_of")
    return sha256(json.dumps([intake, packet["methodology_sha256"]], sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


class _AnalystReader(_RevisionReader):
    def __init__(self, factory, source, target):
        assessment_id, self.record = target
        super().__init__(factory, source, _Command(assessment_id, "resume"))

    def _binding(self, session, scope):
        binding = super()._binding(session, scope)
        record = self.record
        if record is not None:
            inviter = record.inviter
            if (binding[0] != inviter.relation or scope.authority != inviter.authority
                    or scope.identity.issuer != inviter.issuer
                    or scope.identity.principal.subject != inviter.subject):
                raise PermissionError("Synthetic handoff unavailable.")
            packet = self._read_state(session, binding[1])
            if packet is None or _context(packet) != inviter.context_sha256:
                raise PermissionError("Synthetic handoff unavailable.")
        return binding

    def _relationships(self, session, scope, *, lock):
        value = super()._relationships(session, scope, lock=lock)
        if self.record is not None and value[0][:-1] != self.record.inviter.parents:
            raise PermissionError("Synthetic handoff unavailable.")
        return value

    def materialize(self, session, scope):
        relation, head = scope.relationships[1]
        packet = self._read_state(session, head)
        if packet is None:
            raise PermissionError("Save an analyst revision before requesting evidence.")
        requirements = tuple(c.control_id for c in risk_and_applicability(_intake(packet))[2].controls)
        return _Snapshot(relation, head, scope.authority, scope.identity.issuer,
            scope.identity.principal.subject, scope.identity.session_id, _context(packet), requirements,
            tuple((source["filename"], source["sha256"]) for source in packet["sources"]),
            scope.relationships[0][:-1])


class _AnalystGate(_SessionLeasedRead):
    _reader_type = _AnalystReader

    def _materialize(self, reader, session, scope):
        return reader.materialize(session, scope)


@dataclass(frozen=True)
class _Delivery:
    record: _Record
    vendor_issuer: str
    vendor_subject: str
    vendor_session_id: str
    filename: str
    content: bytes = field(repr=False)
    kind: str
    observed_on: date | None


class _VendorReader(_RevisionReader):
    def __init__(self, factory, source, target):
        self.delivery = target
        super().__init__(factory, source, _Command(target.record.inviter.relation[3], "resume"))

    def _binding(self, session, scope):
        binding = super()._binding(session, scope)
        record = self.delivery.record
        inviter = record.inviter
        if (scope.identity.issuer != inviter.issuer
                or scope.identity.principal.subject != inviter.subject
                or scope.identity.session_id != inviter.session_id
                or scope.authority != inviter.authority
                or binding != (inviter.relation, inviter.head)):
            raise PermissionError("Synthetic handoff unavailable.")
        return binding

    def _relationships(self, session, scope, *, lock):
        value = super()._relationships(session, scope, lock=lock)
        if value[0][:-1] != self.delivery.record.inviter.parents:
            raise PermissionError("Synthetic handoff unavailable.")
        return value

    def materialize(self, session, scope):
        target, record = self.delivery, self.delivery.record
        packet = self._read_state(session, scope.relationships[1][1])
        if packet is None or len(packet["sources"]) >= 4:
            raise PermissionError("Synthetic handoff unavailable.")
        digest = sha256(target.content).hexdigest()
        if any(source["filename"] == target.filename or source["sha256"] == digest for source in packet["sources"]):
            raise PermissionError("Synthetic handoff unavailable.")
        intake = _intake(packet)
        now = self._now(scope)
        if now >= record.expires_at:
            raise PermissionError("Synthetic handoff unavailable.")
        read_upload(replace(intake, as_of=now.date()), target.filename, target.content,
            (record.requirement_id,), kind=target.kind, observed_on=target.observed_on,
            service=intake.service, environment=intake.environment)
        pending = PendingSubmission(record.invitation_id, int(intake.assessment_id),
            record.inviter.head[0], record.requirement_id, target.filename, target.content,
            digest, len(target.content), target.kind, target.observed_on, now,
            target.vendor_issuer, target.vendor_subject, target.vendor_session_id,
            "Authenticated synthetic invitee", record.inviter.issuer, record.inviter.subject,
            record.inviter.session_id)
        return pending


class _VendorGate(_SessionLeasedRead):
    _reader_type = _VendorReader

    def _materialize(self, reader, session, scope):
        return reader.materialize(session, scope)


class SyntheticVendorHandoff:
    """One synthetic assessment and fixed vendor actor; at most 32 inbox records.

    Records are version-1 frozen data, not serialized Python/session state. Each
    record can hold one <=64 KiB TXT original; no token is retained in cleartext.
    The original analyst session sponsors an unsubmitted invitation; logout,
    expiry or rotation invalidates delivery. Its locked SQL authority is not
    exposed to the separately authenticated vendor and grants pending delivery
    only, never custody or reads. Completed delivery may be captured by a fresh
    session of the same currently authorized analyst. Ambiguous capture is terminal.
    """
    def __init__(self, factory, assessment_id, vendor_issuer, vendor_subject, *, clock=utc_now):
        if (not callable(factory) or type(assessment_id) is not int or not 0 < assessment_id <= 2**63 - 1
                or not callable(clock) or any(type(value) is not str or not 1 <= len(value) <= 500
                                            for value in (vendor_issuer, vendor_subject))):
            raise ValueError("Use a fixed server-owned synthetic handoff scope.")
        self._factory, self._assessment_id = factory, assessment_id
        self._vendor_issuer, self._vendor_subject, self._clock = vendor_issuer, vendor_subject, clock
        self._lock, self._records, self._sponsors, self._last_time = RLock(), {}, {}, None

    def _now(self):
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise PermissionError("Synthetic handoff unavailable.")
        now = now.astimezone(timezone.utc)
        if self._last_time is not None and now < self._last_time:
            raise PermissionError("Synthetic handoff unavailable.")
        self._last_time = now
        return now

    def _source(self, handle, identity):
        return SessionIdentitySource(identity.sessions, handle, self._factory, clock=identity.clock)

    def _analyst(self, handle, identity, record=None):
        return _AnalystGate(self._factory, identity_source=self._source(handle, identity))._leased_read(
            (self._assessment_id, record), _ANALYST)

    def create(self, handle, identity, expected_revision, requirement_id):
        try:
            with self._lock:
                now = self._now()
                source = self._source(handle, identity)
                snapshot = _AnalystGate(self._factory, identity_source=source)._leased_read(
                    (self._assessment_id, None), _ANALYST)
                if (snapshot is None or type(expected_revision) is not int
                        or snapshot.head[0] != expected_revision or requirement_id not in snapshot.requirements
                        or len(snapshot.inventory) >= 4
                        or len(self._records) >= _MAX_RECORDS
                        or any(r.status in ("issued", "submitted", "capturing", "captured")
                               and r.expires_at > now for r in self._records.values())):
                    return None
                identifier, token = uuid4().hex, secrets.token_urlsafe(32)
                if not _TOKEN.fullmatch(token) or identifier in self._records:
                    return None
                expires = now + timedelta(minutes=10)
                self._records[identifier] = _Record(1, identifier, sha256(token.encode("ascii")).hexdigest(),
                    expires, requirement_id, snapshot)
                self._sponsors[identifier] = source
                return IssuedInvitation(identifier, token, expires)
        except Exception:
            return None

    def revoke(self, handle, identity, invitation_id):
        try:
            with self._lock:
                record = self._records.get(invitation_id)
                if (record is None or record.capture_active
                        or record.status not in ("issued", "submitted", "captured")
                        or self._analyst(handle, identity, record) is None):
                    return False
                if self._records.get(invitation_id) is not record:
                    return False  # Authorization callbacks may have completed intake.
                self._records[invitation_id] = replace(record, status="revoked", pending=None)
                return True
        except Exception:
            return False

    def submit(self, handle, identity, token, filename, content, kind="assertion", observed_on=None):
        try:
            if (type(token) is not str or _TOKEN.fullmatch(token) is None
                    or type(filename) is not str or filename != filename.strip()
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}", filename) is None
                    or not filename.lower().endswith(".txt") or type(content) is not bytes
                    or not 1 <= len(content) <= 65536 or kind not in ("assertion", "policy", "configuration", "test")
                    or observed_on is not None and type(observed_on) is not date):
                return False
            content.decode("utf-8", errors="strict")
            digest = sha256(token.encode("ascii")).hexdigest()
            with self._lock:
                now = self._now()
                record = next((r for r in self._records.values() if hmac.compare_digest(r.token_digest, digest)), None)
                if record is None or record.status != "issued" or now >= record.expires_at:
                    return False
                if observed_on is not None and observed_on > now.date():
                    return False
                # Consume before the attempted authorized operation. Any failed
                # acknowledgement remains terminal; replay cannot stage twice.
                sponsor = self._sponsors.get(record.invitation_id)
                manager = identity.sessions
                if (type(manager) is not SessionManager or sponsor is None
                        or manager is sponsor._sessions or manager._store is sponsor._sessions._store):
                    return False
                # The vendor's independent lease encloses the sponsoring SQL
                # transaction and analyst lease. No path acquires these locks
                # in the reverse order. SQL commit precedes both lease exits.
                with manager.operation_lease(handle) as vendor_session:
                    if (type(vendor_session) is not ServerSession
                            or vendor_session.issuer != self._vendor_issuer
                            or vendor_session.subject != self._vendor_subject):
                        return False
                    # Lease entry/authentication may reenter this RLock and
                    # revoke or consume the invitation. Only the exact issued
                    # record inspected above can be reserved for this delivery.
                    if self._records.get(record.invitation_id) is not record:
                        return False
                    self._records[record.invitation_id] = replace(record, status="unconfirmed")
                    target = _Delivery(record, vendor_session.issuer, vendor_session.subject,
                        vendor_session.session_id, filename, content, kind, observed_on)
                    pending = _VendorGate(self._factory, identity_source=sponsor)._leased_read(target, _ANALYST)
                    if pending is None:
                        return False
                if self._now() >= record.expires_at:
                    return False
                self._records[record.invitation_id] = replace(record, status="submitted", pending=pending)
                return True
        except Exception:
            return False

    def list_invitations(self, handle, identity):
        try:
            with self._lock:
                now = self._now()
                if self._analyst(handle, identity) is None:
                    return None
                return tuple(InvitationSummary(r.invitation_id,
                    "expired" if r.status == "issued" and now >= r.expires_at else r.status,
                    r.requirement_id, r.expires_at, r.pending.filename if r.pending else None,
                    r.pending.sha256 if r.pending else None) for r in self._records.values()
                    if self._analyst(handle, identity, r) is not None)
        except Exception:
            return None

    def get_pending(self, handle, identity, invitation_id):
        try:
            with self._lock:
                record = self._records.get(invitation_id)
                if (record is None or record.status not in ("submitted", "capturing", "captured")
                        or self._analyst(handle, identity, record) is None):
                    return None
                return record.pending
        except Exception:
            return None

    def begin_capture(self, handle, identity, invitation_id):
        try:
            with self._lock:
                record = self._records.get(invitation_id)
                snapshot = self._analyst(handle, identity, record) if record is not None else None
                if (record is None or record.status != "submitted" or snapshot is None
                        or len(snapshot.inventory) >= 4 or any(name == record.pending.filename
                        or digest == record.pending.sha256 for name, digest in snapshot.inventory)):
                    return None
                self._records[invitation_id] = replace(record, status="capturing")
                return record.pending
        except Exception:
            return None

    @contextmanager
    def capture_operation(self, handle, identity, invitation_id):
        """Serialize revocation with the complete explicit capture/import action.

        The caller holds this guard through custody, append and terminal marking.
        A successful revoke occurs before that action or after it; it cannot
        acknowledge revocation halfway through an import. Caller exceptions are
        propagated, never interpreted as a confirmed capture or rollback.
        """
        with self._lock:
            record = self._records.get(invitation_id)
            eligible = (record is not None and not record.capture_active
                        and record.status in ("submitted", "captured"))
            # Reserve before SQL/session authorization: its trusted callbacks
            # may reenter this RLock too. Never restore an old snapshot over an
            # already acknowledged revocation after those callbacks return.
            if eligible:
                reservation = replace(record, capture_active=True)
                self._records[invitation_id] = reservation
            allowed = False
            try:
                allowed = (eligible and self._analyst(handle, identity, record) is not None
                           and self._records.get(invitation_id) is reservation)
            except Exception:
                pass
            try:
                yield allowed
            finally:
                if eligible:
                    current = self._records[invitation_id]
                    self._records[invitation_id] = replace(current, capture_active=False)

    def record_capture(self, handle, identity, invitation_id, receipt):
        try:
            with self._lock:
                record = self._records.get(invitation_id)
                if (record is None or record.status != "capturing" or record.pending is None
                        or type(receipt) is not SyntheticEvidenceReceipt
                        or self._analyst(handle, identity, record) is None):
                    return False
                p = record.pending
                if (receipt.assessment_id != self._assessment_id or receipt.sha256 != p.sha256
                        or receipt.byte_length != p.byte_length or receipt.document_name != p.filename
                        or (receipt.organization_id, receipt.vendor_id, receipt.engagement_id, receipt.assessment_id)
                        != record.inviter.relation[:4]):
                    return False
                self._records[invitation_id] = replace(record, status="captured", pending=replace(p, receipt=receipt))
                return True
        except Exception:
            return False

    def mark_unconfirmed(self, handle, identity, invitation_id):
        return self._mark(handle, identity, invitation_id, "unconfirmed", ("capturing",))

    def mark_imported(self, handle, identity, invitation_id):
        return self._mark(handle, identity, invitation_id, "imported", ("captured",))

    def _mark(self, handle, identity, invitation_id, status, allowed):
        try:
            with self._lock:
                record = self._records.get(invitation_id)
                if record is None or record.status not in allowed or self._analyst(handle, identity, record) is None:
                    return False
                self._records[invitation_id] = replace(record, status=status, pending=None)
                return True
        except Exception:
            return False
