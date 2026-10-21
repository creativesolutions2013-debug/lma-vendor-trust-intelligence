# M4C-1 — Authoritative Organization & Engagement Evidence Access

**Status: implemented database authorization prototype on draft PR #13; independent review required.** Acceptance is tracked in [Issue #11](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/11). No production authentication, real evidence retrieval or application authority registration is enabled.

## Reason for this slice

LMA is an evidence-first third-party assurance platform: assess the evidence before asking questions. M4A provides a synthetic worklist; M4B provides deny-first startup, confined local storage and an unwired evidence-read preflight. M4C adds explicit database ownership, membership and engagement entitlements for that contract. Mere `Vendor.id` or role `Admin` remains insufficient; legacy rows are not assigned ownership or access automatically.

The baseline is M4B merge `16d48fc9dbe8d5309630ce1df823bdb9108f8341`, with successful postmerge [Unit and PostgreSQL CI](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/39689214521). Revision `0014_organization_engagement_authorization` follows `0013_revalidation_case_records`. Branch protection is tracked separately in [Issue #12](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/12); the permission check is recorded below.

## Architecture decision

**M4C-1 is the relationship-backed authorization layer, not a login screen.** Real-world production identity requires a separate configured and independently validated OIDC provider (M4C-2); deployment identity choice is not yet known. Do not improvise a static signing secret, accept a raw self-proclaimed identity, or allow a browser to supply `EvidenceAccessAuthority`.

A future upstream *trusted server-only* identity resolver authenticates a session and supplies issuer, subject, audience, session and expiry. M4C-1 tests the **database authorization** step against such an identity using synthetic fixtures and keeps the actual production resolver unregistered, so `AUTH_MODE=production` remains fail-closed.

### Minimal relational design

The additive `0014_organization_engagement_authorization` revision implements:

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

M4C-2: select the external IdP and implement JWT signature verification against trusted JWKS with an algorithm allowlist, configured issuer/audience checks, nonce/state validation, key rotation, short server-owned sessions, revocation and secure browser-session handling. Reject unsigned/static demo tokens. The future provider adapter supplies only validated identity/session context; organization roles still come from server-managed membership. Deployment configuration and secrets remain outside the repository.

M4D: only after independent verification, implement authorized, audited, controlled evidence-byte custody/read, malware scanning, encryption/retention and provenance. Prove analyst usability with authorized real-world or permissioned test evidence. Until then, all existing analysis previews remain **synthetic only**, and the current application does **not** have general multi-tenant isolation across legacy screens.

## Implemented resolver and trust boundary

`DatabaseEvidenceAccessAuthority(session_factory, identity_source=...)` in
`src/database_evidence_authority.py` implements the existing M4B authority protocol.
Both dependencies must be supplied by trusted server wiring. No source is
configured in `app.py`; omitted identity sources deny. A raw identity DTO, demo
principal, role string or token is not a source of verified identity.

The upstream adapter must provide an already authenticated issuer/subject,
audience, session, organization context and valid aware timestamps. M4C checks
their shape and validity, **not** signatures or credentials. It looks up exactly
one current membership by organization + issuer + subject, ignoring incoming
global role claims. The membership supplies the server-managed organization role.
Membership alone grants no engagement access.

Authorization re-reads the upstream session and current membership, entitlement,
organization/vendor/engagement/assessment/evidence columns. It verifies every
vendor equality and the explicit assessment engagement. Null links and missing,
duplicate, revoked, expired or inconsistent rows deny without hidden metadata.
Both the early and final role checks use current membership; a role/session change
between calls cannot reuse a prior effective identity. Fresh dedicated sessions,
scalar projections and disabled autoflush avoid stale ORM objects and pending
write flushes. Queries are bounded and scoped to the requested relationship;
there is no enumeration endpoint or metadata on denial.

The grant contains only the database's canonical vendor-bound object key and
verified linkage. Its expiry is capped by the session, membership, entitlement
and a one-minute metadata lifetime. This is a point-in-time authorization result,
**not** a reusable bearer capability or permission to read bytes later. Future
reads must reauthenticate/re-authorize and enforce storage custody. M4B now checks
the clock after provider/database work and rechecks session expiry after grant
issuance; this accepts a legitimately newly issued grant while denying a session
that expires during the lookup.

## Migration and operational safety

The revision creates only three constrained authorization tables and adds nullable
`Vendor.organization_id` and `Assessment.engagement_id` with indexes/FKs. Evidence
derives engagement/organization through its verified parents; no duplicate scope
columns are added. The numeric organization identity is the authorization key;
display names and emails never determine identity or membership.

There are no defaults granting access, data rewrites, automatic assignments,
production membership seeds or migration-time backfills. PostgreSQL uses additive
column/FK DDL. SQLite uses native `ADD COLUMN ... REFERENCES` rather than rebuilding
populated vendor or assessment tables. Tests preserve all original columns/rows
in six populated legacy tables and verify unchanged SQLite root pages. FK,
uniqueness, nonempty issuer/subject, valid-role/status and date-window checks are
tested. Cross-row vendor consistency is also checked in the resolver because
individual FKs cannot prove that chain.

Alembic configuration escapes percent characters before ConfigParser processes
database URLs, preserving encoded connection options. The local migration fixture
also uses a percent-bearing temporary filename to exercise that path.

New membership/entitlement windows are explicit and nonnull; stored timestamps
are UTC. PostgreSQL preserves timezone metadata; SQLite's naive values are
interpreted as UTC. Existing SQLite connection FK configuration is unchanged;
tests enable FK enforcement to validate the definitions, and the resolver does
not assume potentially inconsistent legacy rows are safe.

`downgrade()` deliberately refuses **before any mutation**. Removing ownership
and entitlement history requires a separately reviewed backup, retention and
rollback plan. Do not treat an automatic schema downgrade as a safe production
rollback. Applying this feature's additive migration to customer databases or
deploying it remains outside this task's authorization.

## Synthetic validation and limits

Fixtures include two organizations, two owned vendors, two engagements under one
vendor, separately linked assessments/evidence, plus unassigned and inconsistent
legacy records. They exercise exact-scope metadata success, cross-organization
and sibling-engagement denial, server-managed role changes, revocation/expiry,
issuer/subject/session mismatch, unsafe storage keys, null parents and ambiguous
rows. A deliberately corrupted isolated schema removes unique constraints to
prove duplicate results are rejected rather than selecting an arbitrary row.
Pending session writes and storage byte operations are blocked during the
read-only checks. These are contract tests, not proof of IdP authenticity or full
application tenancy.

SQLite migration tests use a temporary populated database. PostgreSQL migration
and resolver tests run only in the Actions PostgreSQL job's synthetic service,
using separate UUID-named schemas and cleaning up only those test schemas. Local
PostgreSQL-only migration variants are skipped; no customer database is inspected
or migrated. Final compile/full-suite and both CI results are recorded in PR #13.
M3D/M4A requirement semantics, fact confirmations, citations, exception priority,
synthetic worklist and governed decision flows are unchanged.

## Legacy production blockers — intentionally not retrofitted

The new resolver does not make every historical route tenant-safe:

- [Evidence Center](../app.py#L6669) globally lists vendors/evidence; [review](../app.py#L7498) repeats global evidence lookup behind role-based navigation.
- [Assessment selection](../app.py#L6857) uses a selected vendor and allows optional assessment linkage, without engagement entitlement.
- [Legacy upload](../app.py#L7252) writes through storage directly, without this relationship authorization contract.
- [Reports](../app.py#L9051) aggregate global vendor/evidence/assessment rows. Existing governance services generally bind assessment to vendor, not organization entitlement.

These paths block a confidential, multi-tenant production pilot. No existing
stored-path byte retrieval route was found or enabled. A broad historical query/
upload retrofit, database row-level isolation, provisioning/admin controls,
byte-access audit, encrypted custody, malware/retention and external IdP/session
integration require separate reviewed milestones. Production login remains
fail-closed, and no real vendor data is connected to the new worklist.

## Issue #12 — read-only administration check

The repository API reports account permissions `admin: true` (also maintain/push),
so the owner has repository-level rights to configure main protection in GitHub
Settings, subject to applicable platform rules. The `main` branch response still
reports `protected: false` with required checks off. Available connected tools
expose repository/PR/file operations but no branch-protection/ruleset mutation;
repository admin rights alone do not add that tool capability or prove the
connector has administration-write permission. No credential was inspected,
settings changed, or direct push to main attempted.

Issue #12 remains open for the owner to configure required PR review, exact
**Unit tests** and **PostgreSQL compatibility** checks, force-push/deletion blocks
and minimal bypass rights. This milestone neither bypasses nor claims to have
configured those protections.

## Validation record

Compilation of `app.py`, all touched source modules, the migration and both new
test modules passed before full isolated pytest: **1,217 passed, 24 skipped** in
28.17s. The skips are 23 PostgreSQL migration variants and the existing PostgreSQL
smoke test; Actions executes them against its synthetic PostgreSQL service. Local
coverage adds 56 authorization cases and 23 SQLite migration cases, with the
migration cases also parameterized for PostgreSQL. The existing Alembic config
emits three non-failing path-separator deprecation warnings.

Migration/diff/security review checked no backfill or destructive upgrade, explicit
scope joins, fresh role/revocation/session reads, ambiguity rejection, no pending
write flush, no byte retrieval and continued production-auth refusal. Both CI job
results on the exact feature head are recorded in PR #13. Independent security,
product and TPRM review remains required; do not merge automatically.
