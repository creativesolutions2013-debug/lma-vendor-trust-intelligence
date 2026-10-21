"""Deny-first contract for future assessment evidence reads; no live integration.

Only a server-configured authority may supply authenticated identity and verified
relationship snapshots. These DTOs and Python protocol conformance do not verify
credentials or membership. No production authority is implemented or registered.
The current schema cannot establish the required organization/engagement links.
This module returns bounded metadata only: no bytes, storage I/O or governance.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.authz import PERMISSION_EVIDENCE_READ, Principal, can
from src.storage import validate_evidence_key


@dataclass(frozen=True)
class EvidenceReadRequest:
    organization_id: int
    engagement_id: int
    vendor_id: int
    assessment_id: int
    evidence_id: int


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Trusted authority output, not a caller-supplied credential or demo role."""
    principal: Principal
    issuer: str
    audience: str
    session_id: str
    organization_id: int
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class EngagementLink:
    engagement_id: int
    vendor_id: int
    organization_id: int


@dataclass(frozen=True)
class AssessmentLink:
    assessment_id: int
    vendor_id: int
    engagement_id: int
    organization_id: int


@dataclass(frozen=True)
class EvidenceLink:
    evidence_id: int
    vendor_id: int
    assessment_id: int
    engagement_id: int
    organization_id: int
    storage_key: str


@dataclass(frozen=True)
class EvidenceReadGrant:
    """Authority's current relationship decision and unique server-side linkage.

    Future adapters must independently authenticate the session, validate issuer/
    audience and resolve membership plus authoritative rows. Never build this
    from browser IDs, document metadata, demo env roles or inferred vendor scope.
    """
    decision_id: str
    subject: str
    issuer: str
    audience: str
    session_id: str
    organization_id: int
    engagement_id: int
    vendor_id: int
    assessment_id: int
    evidence_id: int
    issued_at: datetime
    expires_at: datetime
    engagements: tuple[EngagementLink, ...]
    assessments: tuple[AssessmentLink, ...]
    evidence: tuple[EvidenceLink, ...]


class EvidenceAccessAuthority(Protocol):
    """Server-only dependency; absent until a separately reviewed integration.

    Not a request field, plugin loaded from customer input, or credential verifier
    implemented by this milestone. Test doubles prove the contract only.
    """
    def authenticated_identity(self) -> AuthenticatedIdentity | None: ...

    def authorize_evidence_read(self, identity: AuthenticatedIdentity,
                                request: EvidenceReadRequest) -> EvidenceReadGrant | None: ...


@dataclass(frozen=True)
class ReadAuthorization:
    organization_id: int
    engagement_id: int
    vendor_id: int
    assessment_id: int
    evidence_id: int
    storage_key: str
    expires_at: datetime
    decision_id: str


@dataclass(frozen=True)
class EvidenceAccessDecision:
    allowed: bool
    reason: str
    authorization: ReadAuthorization | None = None


def _utc_now():
    return datetime.now(timezone.utc)


def _positive_id(value):
    return type(value) is int and value > 0


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _current(start, end, now):
    return (type(start) is datetime and type(end) is datetime
            and start.tzinfo is not None and end.tzinfo is not None
            and start.utcoffset() is not None and end.utcoffset() is not None
            and start <= now < end)


def preflight_evidence_read(request: EvidenceReadRequest, *, authority: EvidenceAccessAuthority | None = None):
    """Check identity, RBAC, verified relationship and confined object-key syntax.

    Default denies. The app does not supply an authority or call this contract.
    Returning metadata does not read a file, issue a URL, authenticate an IdP,
    establish tenancy from current ORM rows or authorize any assessment decision.
    A future byte-read path must also use confined storage and recheck authority.
    """
    def deny(reason):
        return EvidenceAccessDecision(False, reason)

    if authority is None:
        return deny("Trusted identity and verified organization/engagement authorization are not configured; stored evidence access is blocked.")
    if type(request) is not EvidenceReadRequest or not all(_positive_id(x) for x in (
            request.organization_id, request.engagement_id, request.vendor_id, request.assessment_id, request.evidence_id)):
        return deny("Invalid evidence relationship request.")
    # Resolver failures fail closed without exposing provider errors or secrets.
    try:
        now = _utc_now()
        identity = authority.authenticated_identity()
        if (type(identity) is not AuthenticatedIdentity or type(identity.principal) is not Principal
                or not all(_text(x) for x in (identity.principal.subject, identity.issuer, identity.audience, identity.session_id))
                or not _positive_id(identity.organization_id)
                or identity.organization_id != request.organization_id
                or not _current(identity.issued_at, identity.expires_at, now)):
            return deny("A current server-authenticated identity for this organization is required.")
        if not can(identity.principal, PERMISSION_EVIDENCE_READ):
            return deny("Evidence read permission is required in addition to relationship authorization.")
        grant = authority.authorize_evidence_read(identity, request)
        if (type(grant) is not EvidenceReadGrant or not _text(grant.decision_id)
                or (grant.subject, grant.issuer, grant.audience, grant.session_id)
                != (identity.principal.subject, identity.issuer, identity.audience, identity.session_id)
                or not all(_positive_id(x) for x in (grant.organization_id, grant.engagement_id, grant.vendor_id,
                                                    grant.assessment_id, grant.evidence_id))
                or (grant.organization_id, grant.engagement_id, grant.vendor_id, grant.assessment_id, grant.evidence_id)
                != (request.organization_id, request.engagement_id, request.vendor_id, request.assessment_id, request.evidence_id)
                or not _current(grant.issued_at, grant.expires_at, now)
                or grant.issued_at < identity.issued_at or grant.expires_at > identity.expires_at):
            return deny("Verified authorization for the exact evidence relationship is unavailable or expired.")
        groups = ((grant.engagements, EngagementLink), (grant.assessments, AssessmentLink), (grant.evidence, EvidenceLink))
        if any(type(rows) is not tuple or len(rows) != 1 or type(rows[0]) is not kind for rows, kind in groups):
            return deny("Unique verified assessment, engagement and evidence linkage is required.")
        for rows, _ in groups:
            row = rows[0]
            for name in ("organization_id", "engagement_id", "vendor_id", "assessment_id", "evidence_id"):
                if hasattr(row, name) and (not _positive_id(getattr(row, name)) or getattr(row, name) != getattr(request, name)):
                    return deny("Verified organization/engagement linkage is missing or differs from the requested relationship.")
        try:
            key = validate_evidence_key(grant.evidence[0].storage_key, vendor_id=request.vendor_id)
        except (TypeError, ValueError):
            return deny("A safe vendor-bound evidence object key is required.")
        return EvidenceAccessDecision(True, "Read authorization metadata only; no evidence bytes accessed.", ReadAuthorization(
            request.organization_id, request.engagement_id, request.vendor_id, request.assessment_id, request.evidence_id,
            key, grant.expires_at, grant.decision_id,
        ))
    except Exception:
        return deny("Trusted identity or relationship verification failed; stored evidence access remains blocked.")
