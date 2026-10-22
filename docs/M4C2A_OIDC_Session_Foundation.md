# M4C-2A — Verified OIDC Identity and Session Foundation

**Status: implemented unwired synthetic proof on draft PR #15; independent security review required. Production login remains disabled.**

[Issue #14](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/14) is the authoritative acceptance specification. Implementation stays on `feature/m4c2-oidc-session-core` and the existing draft PR. This proof does not provide hosted OIDC login, customer account provisioning, or production evidence access.

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

[Repository protection is tracked in Issue #12](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/12). Do not bypass reviews or status checks.

## Implemented contract

`src/oidc_login.py` supplies an authorization-code **core with an injected synthetic
exchange**, not an HTTP callback or real provider client. Server wiring owns the
provider, verifier, exchange client, clock and stores. None is registered in the
application. `app.py`, `src/auth_context.py`, M3D/M4A and governed decisions are
unchanged; production still refuses before DB/storage/UI imports.

`ProviderConfig` requires exact HTTPS issuer, client ID, authorization/token/JWKS
endpoints and callback. Credentials, query/fragment injection, non-HTTPS URLs,
unknown algorithms and excessive clock skew deny. This slice deliberately has no
HTTP localhost exception. Endpoints need not share a hostname, but each must be
explicitly pinned by trusted server configuration. No discovery or header URL is
fetched. The configured JWKS URI documents the trusted provider binding; actual
JWKS transport, refresh and provider metadata verification are deferred.

Authlib **1.9.1** prepares `response_type=code`, `scope=openid` and PKCE S256.
`begin()` generates independent random state, nonce, verifier and login-context
binding. The verifier stays server-side; the challenge and nonce enter the
authorization URL. The returned binding must eventually be carried through a
separately secured browser lifecycle, never trusted from an arbitrary request.
No secure browser integration is claimed here.

`finish()` requires exact configured issuer/callback and the matching binding.
The locked store consumes state **before exchange**, including failed exchanges;
unsolicited, expired, mismatched and racing callbacks cannot issue sessions. The
exchange receives only the configured token endpoint/client/callback, code and
stored verifier. Its returned ID token passes real signature verification before
session issuance. The clock is sampled after exchange; an attempt expiring during
exchange denies. State expires after at most five minutes. Used code digests are
retained for fifteen minutes, and the bounded store refuses new attempts when
full. State keys, binding comparisons and used-code keys use SHA-256 digests;
nonces/verifiers exist only in pending server memory. These hashes use standard
library primitives for lookup, never JWT signing or custom cryptography.

joserfc **1.7.7** parses and verifies compact signed ID tokens using a copied,
issuer-bound pinned JWKS snapshot. The bounded algorithm surface is RS256 or
ES256, explicitly configured; RSA keys below 2048 bits, non-P-256 EC keys, private
or symmetric keys, unsuitable key operations and duplicate/missing key IDs deny.
Token headers cannot introduce keys, URLs, unsupported extensions or a different
algorithm/key type. Missing/unknown `kid`, wrong signature and `none`/HMAC
confusion deny. Key rotation means replacing the verified snapshot; removed keys
are not silently retained or fetched on demand.

Verification requires exact issuer, nonempty stable subject, expected audience,
matching nonce, integer `exp` and `iat`, valid optional `nbf`/`auth_time`, and exact
`azp` if supplied (required with multiple audiences). Booleans, floats, strings,
NaN/infinity, duplicate audiences, stale/future or inconsistent windows deny.
Skew defaults to 30 seconds and is capped at 60; expiration at the final allowed
boundary denies. Token lifetime and age default to at most 600 seconds plus
bounded age skew. Optional maximum authentication age binds `max_age` in the
request and requires fresh `auth_time`. Email, names, groups, role and org claims
never provide entitlements. Failures expose static messages without tokens,
codes, verifier, handle or provider/SQL diagnostics.

## Sessions and M4C-1 integration

`src/server_sessions.py` supplies the `SessionStore` interface and an explicitly
synthetic, bounded `InMemorySessionStore`. `SessionManager.issue()` is a trusted
internal step after verification; a `VerifiedSubject` DTO is not a client
credential. Handles contain 256 random bits and only their SHA-256 lookup digests
are stored. Authorization metadata gets an independent non-bearer session ID.
Default idle expiry is five minutes and absolute expiry thirty minutes. Each
authentication rechecks current storage, strict record shape, both deadlines and
the clock after storage work. Absolute identity timestamps stay stable while
idle access slides. Logout revokes; atomic rotation invalidates the previous
handle and changes the correlation ID without extending absolute expiry. Unknown,
expired, revoked, malformed, corrupted or unavailable-store reads deny. Failed
revocation returns false; callers must not claim successful logout on an outage.

`SessionIdentitySource` accepts only server-injected session/store and DB factory
dependencies; it has **no organization selector**. It finds exactly one current
issuer/subject membership joined to an organization, validates its window/role,
and rechecks the session after DB work. Multiple current memberships deny pending
a separately reviewed organization-selection flow. It returns a placeholder
Viewer role; `DatabaseEvidenceAccessAuthority` independently rereads membership
for the effective role and the exact current engagement/assessment/evidence
grant. A signed token or organization membership alone never authorizes evidence.
No bytes, provisioning, authority registration or database migration is added.

## Synthetic acceptance proof and limits

Tests generate asymmetric keys in memory and use `.invalid` provider URLs with
injected local clients. The fake exchange independently checks the S256 verifier
against the authorization challenge. Regressions cover real good/bad signatures,
claims/key confusion, weak keys, explicit snapshot rotation, injected URLs,
missing config, state/code/nonce replay, concurrent callbacks, corrupted PKCE,
expiry during exchange, server-store outages, idle/absolute expiration, rotation,
revocation and corrupted records. The integration proof traverses signed login,
one-time state/PKCE, session, membership and M4B metadata preflight with two
organizations and sibling engagements. Membership/grant revocation, ambiguous
organization context, pending-write isolation and expiry during DB work deny.
The new adapter integration uses SQLite locally and isolated synthetic PostgreSQL
schemas in the Actions PostgreSQL job. Existing production startup regressions
remain part of the full suite. Exact results are recorded below and in PR #15.

These are synthetic regression outcomes, **not** production penetration testing,
real IdP compatibility, browser CSRF/cookie validation or end-to-end SSO. No HTTP
token transport/client authentication, provider code lifecycle, JWKS refresh,
durable/multi-worker session or replay storage, deployed proxy, cookie issuer or
callback route exists here. The future provider must enforce one-time codes,
short code lifetime and PKCE independently. Process restart discards these test
stores; they must never be deployed as production authority. Store integrity is
trusted: hashed handles protect bearer lookup values at rest, not malicious
storage writes. A browser with both stolen state and binding remains outside
this unwired core's guarantees. Identity/session configuration alone cannot make
legacy global routes tenant-safe. All separate deployment gates above remain
required before confidential data or production authentication.

## Validation record

Compilation of `app.py` and all six new Python modules/tests passed before the
isolated full suite: **1,380 passed, 24 skipped** in 31.70s, including **163 new
synthetic cases**. The skips are 23 existing PostgreSQL migration variants and the
existing PostgreSQL smoke test; Actions runs them against its synthetic service.
Three existing Alembic path-separator deprecation warnings remain. `pip check`,
complete diff/dependency/security review and `git diff --check` passed. Both
required Actions results on the exact final head are recorded in PR #15.
