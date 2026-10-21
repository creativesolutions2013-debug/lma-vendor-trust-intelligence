# M4C-1 — Authoritative Organization & Engagement Evidence Access

**Status: planned feature-branch implementation, not yet delivered.** This document is the reviewed handoff for [Issue #11](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/11), **not evidence of functional authorization**. No real evidence data or production authentication is enabled.

## Reason for this slice

LMA is an evidence-first third-party assurance platform: assess the evidence before asking questions. M4A provides a synthetic assessment worklist; M4B provides deny-first startup, secure local-key syntax/no-follow storage, and a deliberately unwired `EvidenceAccessAuthority`. The current ORM, however, does **not** associate an assessment unambiguously with a service engagement, or establish organization membership and grants. Mere `Vendor.id` and role `Admin` are insufficient to authorize a confidential document read.

The verified baseline is M4B merge `16d48fc9dbe8d5309630ce1df823bdb9108f8341`; main postmerge unit and PostgreSQL jobs passed in [run 39689214521](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/39689214521). The previous last Alembic revision is `0013_revalidation_case_records.py`. `main` branch protections are separately tracked in [Issue #12](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/12), **not currently configured**.

## Architecture decision

**M4C-1 is the relationship-backed authorization layer, not a login screen.** Real-world production identity requires a separate configured and independently validated OIDC provider (M4C-2); deployment identity choice is not yet known. Do not improvise a static signing secret, accept a raw self-proclaimed identity, or allow a browser to supply `EvidenceAccessAuthority`.

A future upstream *trusted server-only* identity resolver authenticates a session and supplies issuer, subject, audience, session and expiry. M4C-1 tests the **database authorization** step against such an identity using synthetic fixtures and keeps the actual production resolver unregistered, so `AUTH_MODE=production` remains fail-closed.

### Minimal relational design

Prefer a small additive revision `0014_...` after inspecting existing metadata/migration conventions:

- `Organization` with an immutable identity. `Vendor.organization_id` is nullable for existing legacy records and must be explicitly set/verified for any secure access.
- `OrganizationMembership` keyed uniquely by `organization_id + issuer + subject` (email/display name do **not** define identity), with active/revoked status and server-governed role.
- `EngagementAccessGrant` uniquely binds an **active member** to an explicit **engagement** and supports revocation/expiration; no “organization member may read every vendor” default.
- `Assessment.engagement_id` is an **optional additive FK** for legacy compatibility; it must be present for any secure read. Existing `Evidence.assessment_id` remains optional for legacy data; secure read **denies null**. Evidence engagement is derived through the verified assessment→engagement join, not through a user-supplied field.
- Enforce exact chain **membership→grant→engagement→vendor (organization)→assessment (vendor and engagement)→evidence (vendor and assessment)**. Verify links against authoritative rows and reject mismatches/ambiguities.
- Do **not** auto-backfill orphan records, grant users access from their names, seed production memberships or alter historical control meanings. Never run a migration against live/customer data as part of this task.

Consider composite constraints/unique indexes to reduce inconsistent link creation; where cross-row relationships cannot be expressed in a single FK, the resolver must check them in one bounded, testable query/transaction. Avoid adding duplicate organization/engagement IDs to `Evidence` unless demonstrably necessary.

### Authorization service contract

Implement a small **read-only server-owned resolver** compatible with `src/assessment_evidence_access.py`. Given a **trusted authenticated identity supplied by the server**, obtain current membership, server-managed effective role and active engagement grant. Join exact current ORM rows; construct only verified `EngagementLink`, `AssessmentLink`, `EvidenceLink` and an expiring grant for the existing `preflight_evidence_read`. Don't let a caller select the authority implementation, self-assert an Admin role, pass a customer-supplied grant or infer tenancy from key prefixes.

Successful synthetic test result is **metadata only**, never evidence bytes, download URL, final reviewer approval, or persisted risk outcome. Identity validity/revocation and actual file access must be rechecked at time of future use. No production authority is registered in `app.py`, and no real document is retrievable.

## Exact negative cases to cover

- Two organizations, two vendors and two engagements **under the same vendor**; access to one engagement cannot read its sibling, and one organization's membership cannot access the other.
- Wrong vendor, org, assessment, evidence, or principal; stale/revoked member/grant; inconsistent evidence→assessment→vendor; missing evidence assessment; duplicate active grants/memberships; missing supplier session; authorization errors without cross-tenant metadata leakage.
- A legacy row with null organization/engagement linkage always denies. No migration backfill or permissive fallback.
- Global `ROLE_ADMIN` or `ROLE_VIEWER` plus a selected vendor ID cannot circumvent the server-maintained membership/grant.
- No-auth authority remains unconfigured, `AUTH_MODE=production` still refuses before DB imports; M3D/M4A synthetic worklist unchanged.
- SQLite migration on populated synthetic legacy DB and PostgreSQL migration+suite succeed with existing data untouched.

## Operational gate

1. Inspect `AGENTS.md`, `README.md`, official end-to-end product blueprint, `ARCHITECTURE.md`, `src/db.py`, Alembic revision chain, `src/auth_context.py`, `src/assessment_evidence_access.py`, M4B threat-model documentation and Issue #11. Design small, no broad `app.py` rewrite.
2. Implement **only** on `feature/m4c-org-engagement-authorization`; add focused synthetic isolation tests and migration checks. No secrets, real customer/vendor evidence, billable AI, network auth calls, scope-broad DB queries or governed writes.
3. `python -m py_compile app.py` and touched modules before `DATABASE_URL=sqlite:///:memory: python -m pytest -q`; execute `git diff --check`, review complete diff and DB migration downgrade/upgrade safety. GitHub Unit and PostgreSQL CI on the final head must both pass.
4. Update existing **draft PR**, stop for independent TPRM/security/product review, **do not merge** without owner approval.

## Later gates (not claimed here)

M4C-2: select the intended external IdP and implement signed OIDC/JWKS verification, strict issuer/audience/nonce/state, short sessions, rotation/revocation, trusted authorization mapping and secure browser session. Deployment configuration and secrets remain outside repository.

M4D: only after independent verification, implement authorized, audited, controlled evidence-byte custody/read, malware scanning, encryption/retention and provenance. Prove analyst usability with authorized real-world or permissioned test evidence. Until then, all existing analysis previews remain **synthetic only**, and the current application does **not** have general multi-tenant isolation across legacy screens.
