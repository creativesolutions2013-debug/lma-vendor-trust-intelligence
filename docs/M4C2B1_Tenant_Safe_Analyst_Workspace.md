# M4C-2B-1 — Tenant-Safe Analyst Assessment Workspace Boundary

**Status: ENGINEERING HANDOFF ONLY; no implementation yet.** [GitHub Issue #17](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/17) contains the authoritative scope and test criteria. Real production authentication and real vendor evidence are still **disabled**.

## Verified baseline — October 22, 2026

- M4C-2A (OIDC cryptographic proof, server sessions, current org identity adapter) merged as `b9329829cb3a513aeabf1eb9bf1f24a8ca7038f7`; [post-merge GitHub Actions run 39703820226](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/39703820226) passed Unit and PostgreSQL compatibility.
- `main` uses active [Protect main](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/rules/25603527) ruleset requiring a PR and passing Unit + PostgreSQL checks.
- M4C-1 `DatabaseEvidenceAccessAuthority` requires verified organization membership and per-engagement grants for metadata-only evidence access, with unconfigured trusted identity denied.
- M4A's assessment worklist remains a synthetic, exception-first, read-only proof for any applicable customer control. Control quality, citations and analyst confirmation are not to be altered.
- Legacy `app.py` pages are not production tenant-safe: global evidence and vendor inventories, globally listed assessment update forms with authoritative approval/risk-score edits, global report exports and storage writes with optional assessment links. A UI role flag or verified OIDC identity **alone cannot scope these queries**.
- `AUTH_MODE=production` deliberately fails before database and UI imports; do not weaken it.

## Technical recommendation

**Do not turn on Streamlit `st.login()` for the existing app.** Official Streamlit documentation says OIDC authenticates but does not authorize resources and describes a nonconfigurable identity cookie lifetime of 30 days, and already-open browser sessions surviving logout elsewhere. Even a valid login does not make legacy global vendor queries safe. See https://docs.streamlit.io/develop/concepts/connections/authentication

### Build this single, small read-only vertical slice

1. Add `src/authorized_assessment_workspace.py` (or a similarly narrow module) that accepts **server-supplied authenticated current identity via the trusted M4C-2A session adapter** and dedicated fresh database-session factory. Query exactly current `OrganizationMembership`, `EngagementAccessGrant`, `Organization`, `Vendor`, `Engagement`, `Assessment`; never trust a browser-supplied organization, vendor or role label. Derive role and specific engagement entitlements from database, with bounded timestamp and session validation, no pending ORM write flush.
2. Return a typed minimal list/read-only detail of **entitled assessments**, with only currently allowed vendor and service label, review status/assignment and due date; **do not include evidence file names, storage references, bytes, personal contact info, risk decision updates or global aggregate counts**. Require exact same organization→vendor→engagement→assessment join; missing `Vendor.organization_id` or `Assessment.engagement_id` is **DENY**. All IDs positive integers (not booleans), no authorization inferred from IDs. Distinct sibling engagements under same vendor must not bleed into each other. Give deterministic bounded pagination and recheck for exact-row lookup to avoid stale cached permissions.
3. Introduce a tiny deny-default **production route/action inventory** for the existing pages so no authenticated-production path can inherit demo-only legacy route permissions by accident. Include unknown/new page in denial. Treat historic evidence uploads, reports, assessment writes/approvals and vendor/global list screens as **unsafe until independently audited**. A pure gate that isn't wired to a real runtime is a *contract* and must be labeled as such. Don't broadly refactor the 9,000-line UI or implement a new dashboard.
4. Prove authorization with fully synthetic tests: two organizations, sibling engagements, current membership/grant allow, revoked/expired session and membership, wrong vendor/assessment/org ID, cross-joined FK, legacy null links, duplicate memberships, query failure, mid-read expiry/revocation, pending writes, hidden/nonexistent ID equality, bounded pagination, and default-deny routing. No actual file bytes or real identities.
5. Keep `AUTH_MODE=production` rejection unchanged. No Streamlit browser login/cookie activation, real provider, token transport, migrations, new customer workflow, evidence uploads, external calls, AI, or governed writes.

## Next explicit deployment gates

- M4C-2B-2: real provider choice, server-verified end-to-end callback, secure browser cookie/session binding and logout/revocation, and authorized app routing with all legacy unsafe paths denied or tenant-scoped. Reconcile the M4C-2A internal session core with deployment platform; no invented bearer trust.
- M4D: tenant-controlled secure evidence ingestion/retrieval, independent byte-time authorization, malware/type/size checks, encryption, retention/deletion, access/denial audit, provenance, and authorized analyst decision review.

## Engineering workflow

Codex: read `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, `docs/LMA_Vendor_Trust_Intelligence_End_to_End_Workflow.md`, `docs/M4C1_Organization_Engagement_Authorization.md`, `docs/M4C2A_OIDC_Session_Foundation.md` and Issue #17. Implement **only** on `feature/m4c2b-tenant-safe-analyst-workspace`, reusing the existing **draft PR**.

Verify clean working tree first. Keep the change small; compile `app.py` and touched modules **before** isolated full pytest; `git diff --check`, inspect entire diff and authorizations, verify Unit + PostgreSQL GitHub Actions on the exact final feature head. No real customer data or destructive tests. Stop for independent security/TPRM/product review; do not merge. Record what is implemented versus still blocked.

**This document is planning, not proof of production identity or tenant isolation.**
