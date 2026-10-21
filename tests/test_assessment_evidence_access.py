"""Synthetic trust-adapter outputs exercise a future, metadata-only read guard.

The fixture authority is server-owned test wiring, not a production identity or
an application registration. Request selectors and role labels grant no access.
"""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

import src.assessment_evidence_access as access
import src.authz as authz
from src.assessment_evidence_access import (
    AssessmentLink, AuthenticatedIdentity, EngagementLink, EvidenceLink,
    EvidenceReadGrant, EvidenceReadRequest, preflight_evidence_read,
)
from src.authz import PERMISSION_EVIDENCE_READ, Principal, ROLE_VIEWER


NOW = datetime(2026, 10, 21, 22, 30, tzinfo=timezone.utc)


class SyntheticAuthority:
    """Explicit server-side test double; never inferred from request metadata."""

    def __init__(self, identity, grant):
        self.identity = identity
        self.grant = grant
        self.calls = []

    def authenticated_identity(self):
        self.calls.append("identity")
        return self.identity

    def authorize_evidence_read(self, identity, request):
        self.calls.append(("authorize", identity, request))
        return self.grant


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(access, "_utc_now", lambda: NOW)
    principal = Principal("synthetic-reader", "Synthetic Reader", "reader@synthetic.invalid", ROLE_VIEWER)
    identity = AuthenticatedIdentity(
        principal=principal, issuer="https://identity.synthetic.invalid", audience="lma-synthetic",
        session_id="synthetic-session-1", organization_id=1,
        issued_at=NOW - timedelta(minutes=10), expires_at=NOW + timedelta(minutes=30),
    )
    request = EvidenceReadRequest(organization_id=1, engagement_id=11, vendor_id=22,
                                  assessment_id=33, evidence_id=44)
    grant = EvidenceReadGrant(
        decision_id="synthetic-relationship-decision", subject=principal.subject,
        issuer=identity.issuer, audience=identity.audience, session_id=identity.session_id,
        organization_id=1, engagement_id=11, vendor_id=22, assessment_id=33, evidence_id=44,
        issued_at=NOW - timedelta(minutes=1), expires_at=NOW + timedelta(minutes=5),
        engagements=(EngagementLink(engagement_id=11, vendor_id=22, organization_id=1),),
        assessments=(AssessmentLink(assessment_id=33, vendor_id=22, engagement_id=11, organization_id=1),),
        evidence=(EvidenceLink(evidence_id=44, vendor_id=22, assessment_id=33, engagement_id=11,
                               organization_id=1, storage_key="vendors/22/evidence/synthetic_report.txt"),),
    )
    return request, identity, grant


def denied(result):
    assert result.allowed is False
    assert result.authorization is None
    assert isinstance(result.reason, str) and result.reason.strip()


def test_missing_authority_is_an_explicit_blocker_even_for_known_request_ids(context):
    request, _, _ = context
    denied(preflight_evidence_read(request))


def test_environment_demo_role_is_not_a_trusted_identity_or_relationship(context, monkeypatch):
    from src.auth_context import get_current_principal

    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("DEV_USER_ROLE", "Admin")
    demo = get_current_principal()
    request, _, _ = context
    denied(preflight_evidence_read(request, authority=demo))


@pytest.mark.parametrize("fake", [None, {"verified": True, "role": "Admin", "vendor_id": 22}, "authenticated"])
def test_caller_shaped_identity_values_cannot_authorize(context, fake):
    request, _, grant = context
    authority = SyntheticAuthority(fake, grant)
    denied(preflight_evidence_read(request, authority=authority))
    assert authority.calls == ["identity"]


def test_broad_viewer_read_permission_does_not_supply_relationship_authorization(context):
    request, identity, _ = context
    assert authz.can(identity.principal, PERMISSION_EVIDENCE_READ)
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, None)))


def test_verified_relationship_does_not_bypass_role_permission(context, monkeypatch):
    request, identity, grant = context
    monkeypatch.setitem(authz.ROLE_PERMISSIONS, ROLE_VIEWER, frozenset())
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, grant)))


@pytest.mark.parametrize("fake", [{"verified": True, "vendor_id": 22}, True, "permit"])
def test_caller_shaped_grants_are_not_verified_linkage(context, fake):
    request, identity, _ = context
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, fake)))


@pytest.mark.parametrize("field", ["organization_id", "engagement_id", "vendor_id", "assessment_id", "evidence_id"])
@pytest.mark.parametrize("value", [None, 0, True, "22"])
def test_request_selectors_require_positive_integer_ids(context, field, value):
    request, identity, grant = context
    denied(preflight_evidence_read(replace(request, **{field: value}),
                                  authority=SyntheticAuthority(identity, grant)))


@pytest.mark.parametrize("field", ["subject", "issuer", "audience", "session_id", "organization_id",
                                  "engagement_id", "vendor_id", "assessment_id", "evidence_id"])
def test_verified_grant_must_match_identity_session_and_exact_requested_relationship(context, field):
    request, identity, grant = context
    value = 999 if field.endswith("_id") and field != "session_id" else "other-synthetic-context"
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, replace(grant, **{field: value}))))


@pytest.mark.parametrize("field", ["issuer", "audience", "session_id"])
def test_identity_requires_nonempty_verifier_context(context, field):
    request, identity, grant = context
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(replace(identity, **{field: " "}), grant)))


@pytest.mark.parametrize("kind", ["identity_expired", "identity_future", "identity_naive", "grant_expired",
                                 "grant_future", "grant_outlives_identity", "grant_naive"])
def test_identity_and_grant_windows_are_current_aware_and_session_bounded(context, kind):
    request, identity, grant = context
    if kind == "identity_expired":
        identity = replace(identity, expires_at=NOW)
    elif kind == "identity_future":
        identity = replace(identity, issued_at=NOW + timedelta(seconds=1))
    elif kind == "identity_naive":
        identity = replace(identity, issued_at=NOW.replace(tzinfo=None))
    elif kind == "grant_expired":
        grant = replace(grant, expires_at=NOW)
    elif kind == "grant_future":
        grant = replace(grant, issued_at=NOW + timedelta(seconds=1))
    elif kind == "grant_outlives_identity":
        grant = replace(grant, expires_at=identity.expires_at + timedelta(seconds=1))
    else:
        grant = replace(grant, expires_at=NOW.replace(tzinfo=None))
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, grant)))


@pytest.mark.parametrize("collection", ["engagements", "assessments", "evidence"])
@pytest.mark.parametrize("kind", ["missing", "duplicate", "null_id"])
def test_linkage_snapshot_must_be_unique_and_present(context, collection, kind):
    request, identity, grant = context
    rows = getattr(grant, collection)
    if kind == "missing":
        rows = ()
    elif kind == "duplicate":
        rows = rows + rows
    else:
        field = {"engagements": "engagement_id", "assessments": "assessment_id", "evidence": "evidence_id"}[collection]
        rows = (replace(rows[0], **{field: None}),)
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, replace(grant, **{collection: rows}))))


@pytest.mark.parametrize("collection,field", [
    ("engagements", "vendor_id"), ("engagements", "organization_id"),
    ("assessments", "vendor_id"), ("assessments", "engagement_id"), ("assessments", "organization_id"),
    ("evidence", "vendor_id"), ("evidence", "assessment_id"), ("evidence", "engagement_id"),
    ("evidence", "organization_id"),
])
def test_source_metadata_cannot_cross_vendor_assessment_engagement_or_organization(context, collection, field):
    request, identity, grant = context
    row = replace(getattr(grant, collection)[0], **{field: 999})
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, replace(grant, **{collection: (row,)}))))


def test_current_schema_missing_tenant_engagement_proof_is_blocked_not_inferred_from_vendor(context):
    request, identity, grant = context
    # Present ORM evidence/assessment vendor IDs alone cannot populate verified
    # organization/engagement relationships. Do not derive them from selections.
    assessment = replace(grant.assessments[0], organization_id=None, engagement_id=None)
    evidence = replace(grant.evidence[0], organization_id=None, engagement_id=None)
    incomplete = replace(grant, assessments=(assessment,), evidence=(evidence,))
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, incomplete)))


@pytest.mark.parametrize("key", [
    "/tmp/synthetic-secret.txt", "../synthetic.txt", "vendors/22/evidence/../../outside.txt",
    "vendors/23/evidence/synthetic_report.txt", "vendors/022/evidence/report.txt",
    r"vendors\22\evidence\report.txt", "vendors/22/evidence/%2e%2e.txt", "",
])
def test_unsafe_or_wrong_vendor_storage_reference_cannot_be_authorized(context, key):
    request, identity, grant = context
    evidence = replace(grant.evidence[0], storage_key=key)
    denied(preflight_evidence_read(request, authority=SyntheticAuthority(identity, replace(grant, evidence=(evidence,)))))


@pytest.mark.parametrize("stage", ["identity", "relationship"])
def test_verifier_failures_fail_closed_without_echoing_exception_details(context, stage):
    request, identity, grant = context

    class BrokenAuthority(SyntheticAuthority):
        def authenticated_identity(self):
            if stage == "identity":
                raise RuntimeError("SYNTHETIC_CREDENTIAL_MUST_NOT_APPEAR")
            return identity

        def authorize_evidence_read(self, identity, request):
            raise RuntimeError("SYNTHETIC_CREDENTIAL_MUST_NOT_APPEAR")

    result = preflight_evidence_read(request, authority=BrokenAuthority(identity, grant))
    denied(result)
    assert "SYNTHETIC_CREDENTIAL" not in repr(result)


def test_success_is_bounded_metadata_and_does_not_read_files_or_change_decisions(context, monkeypatch):
    from pathlib import Path
    import os
    import src.storage as storage

    def forbidden(*args, **kwargs):
        raise AssertionError("Read authorization preflight must not perform filesystem or governed operations.")

    for name in ("save", "exists", "delete"):
        monkeypatch.setattr(storage.LocalEvidenceStorage, name, forbidden)
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    request, identity, grant = context
    before = (identity, grant)
    authority = SyntheticAuthority(identity, grant)
    result = preflight_evidence_read(request, authority=authority)
    assert result.allowed is True and result.authorization is not None
    data = asdict(result.authorization)
    assert data["evidence_id"] == request.evidence_id
    assert data["assessment_id"] == request.assessment_id
    assert data["vendor_id"] == request.vendor_id
    assert data["engagement_id"] == request.engagement_id
    assert data["organization_id"] == request.organization_id
    assert data["storage_key"] == grant.evidence[0].storage_key
    assert not any(isinstance(value, bytes) for value in data.values())
    assert not any(key in data for key in ("content", "file_path", "risk_score", "approval", "download_url"))
    assert (identity, grant) == before
    assert authority.calls == ["identity", ("authorize", identity, request)]
