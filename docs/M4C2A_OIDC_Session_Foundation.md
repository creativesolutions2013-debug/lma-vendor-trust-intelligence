# M4C-2A — Verified OIDC Identity and Session Foundation

**Status: implementation handoff only; not an authenticated production feature.**

[Issue #14](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/14) is the authoritative acceptance specification. Implement on `feature/m4c2-oidc-session-core` and the existing draft PR. This file does not imply OIDC login, customer account provisioning, or production evidence access already exists.

## Why this narrow build

M3D/M4A created the **evidence-first, cross-control, read-only assurance worklist**. M4B restricted startup and file-key handling. M4C-1 merged database-backed org memberships and per-engagement entitlement in `src/database_evidence_authority.py`, while awaiting a trusted upstream identity source. M4C-1 post-merge Unit and PostgreSQL tests passed in [run 39694157565](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/39694157565) at `d1d4233e5fc8f034a53228b5df58d8679442ccd6`.

**This slice supplies a defensible cryptographic and session trust foundation**, not a new application feature or UI. Real login and evidence bytes remain disallowed until authorized tenant isolation across historical routes and deployment-specific IdP configuration are complete.

## Trust boundaries

1. **Untrusted:** browser callback parameters, claims before cryptographic validation, access/ID tokens, email/display name/group claims, client-supplied organization/role/session IDs, external URLs in JOSE headers.
2. **Trusted only after independent verification:** server-pinned OIDC provider settings, trusted JWKS transport/keys, actual signature and ID-token claims, one-time state/nonce/PKCE transaction, server-issued session handle, server-owned current membership and engagement grants.
3. **Not a source of authority:** dataclass creation, global `Admin` env role, `streamlit.session_state`, vendor ID, storage key prefix, URL query parameters, or presence of an OIDC-looking token.
4. **Read boundary still closed:** `AUTH_MODE=production` must fail before side effects. Do not inject a live principal into `app.py`, register an authority, call the evidence store, or infer a tenant from a verified JWT's arbitrary custom claims.

## Smallest acceptable implementation

- Use a maintained, vetted Python OIDC/JWT library. Prepare transaction-specific cryptographically random `state`, `nonce`, PKCE S256 and exact redirect/issuer binding. One-time exchange with an injected fake provider client in tests. No live network in tests.
- Verify asymmetric token signatures and allowlisted algorithms against **trusted, preconfigured issuer-bound keys**; reject dynamically supplied key URLs. Strict `iss`, `aud`, `azp`, `exp`, `iat`, `nonce` and bounded skew. Prevent callback/transaction replay and cross-issuer mix-up.
- Use server-side opaque, expiring, revocable sessions, with secure random identifiers; compromised/fabricated client cookies must not produce an identity. Deny on unavailable session storage.
- Adapter to M4C-1 may resolve a **server-verified organization membership** for a validated issuer/sub/session; effective role and engagement permission still come from database rows. No direct browser-selected organization ID as authority.
- Keep this core **unwired**, with synthetic cryptographic fixtures; no hosted IdP, no real accounts, no login screen, no organization admin dashboard, no production-readiness claim.
- If a complete standard authorization-code exchange is out of scope, document the exact unimplemented callback/provider-session pieces, rather than accept raw ID tokens as sign-in. The token verifier on its own does not constitute secure SSO.

## Review gates

- Read repo `AGENTS.md`, official workflow, `docs/M4C1_Organization_Engagement_Authorization.md`, Issue #14.
- Regression tests: signed good/bad tokens, JWKS ambiguity, wrong alg/issuer/audience/nonce, replayed state/code, PKCE, provider mix-up, grant/context revocation, session expiry/invalidation and denied unconfigured production startup.
- Compile `app.py` and touched modules before full pytest; diff and dependency review; GitHub Unit tests and PostgreSQL compatibility green on latest PR head.
- No live migrations, proprietary evidence, real tokens/credentials, external requests, governed decisions or main edits. Independent security review and explicit owner authorization before merging.

## Separate deployment gates

- Select actual IdP (Entra ID / Okta / Auth0 / Google Workspace or another standards-compliant provider), configure its exact issuer/client/redirect/JWKS metadata and external credentials through a reviewed deployment mechanism.
- Secure callback and browser cookie/SameSite/HttpOnly/Secure/TLS lifecycle, session fixation/CSRF/logout/revocation and hosting proxy trust; production login remains disabled until checked end-to-end.
- Tenant-scoped authorization across **all legacy application routes** and all relevant reads/writes, not only the M4C metadata resolver.
- Audit access/denials, encrypted and malware-scanned evidence custody, scoped byte reads, retention/deletion, source authenticity and authorized real-data pilot.

[Repository protection Issue #12](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/12) remains an admin task; `main` was unprotected at setup time. Do not bypass reviews or status checks.
