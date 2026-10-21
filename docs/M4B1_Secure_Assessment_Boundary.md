# M4B-1 — Secure Assessment Boundary (implementation handoff)

**Status: implementation not yet complete.** Work is tracked in [Issue #9](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/9) and must be implemented on `feature/m4b-secure-assessment-boundary` in a draft PR. Do not claim that live vendor evidence or production authentication has been enabled.

## Why this milestone

M4A-1's synthetic, read-only worklist now connects applicable requirements, cited assurance, reviewed fact-specific needs and minimal *draft* vendor questions. Its merged commit is `720e50a8d4ac25d6aea921b91791a78521fa7f1a`; the main-branch post-merge Unit and PostgreSQL jobs passed in [run 39686140765](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/39686140765).

**Before wiring it to real evidence we must strengthen the trust boundary.** Current `get_current_principal()` intentionally rejects production auth; an environment-supplied demo role is **not** a verifiable identity. The current app initializes/seeds the database before resolving that identity. Local evidence storage accepts a caller key without verifying it remains under the storage root. Existing role permissions do not establish tenant/engagement-level authorization. A real-data integration would make these deficiencies material.

## Narrow M4B-1 scope

1. **Fail-closed app startup:** resolve production-mode/identity preflight before database initialization, demo seeding, storage or evidence/assessment actions. Under `AUTH_MODE=production`, abort with no side effects because production identity is not connected. Future production paths must never seed synthetic demo data.
2. **Confined local evidence keys:** enforce validated vendor-scoped object keys and safe root containment across `save`, `exists`, and `delete`. Reject traversal, absolute paths, malformed IDs, symlink escapes, and attempts to operate on unrelated vendor storage.
3. **Small deny-first access contract for future evidence integration:** role permission **plus** independently verified principal/tenant/engagement/assessment/vendor relationships. Fail closed when trusted relationship context is not available from the current model. The contract returns only authorization metadata, not evidence bytes, approvals, or real data. Exercise it on synthetic entities.
4. **Threat model + regression tests:** prove fail-closed order, path confinement, wrong-relationship rejection, and no effect on M4A worklist or governed risk workflows. Document precisely what remains absent.

**Non-goals:** A production IdP or OIDC integration, tenant DB schema migration, user account management, real vendor evidence, live ingestion, signed URLs, storage migration, email, new dashboards, AI calls or changed residual-risk outcomes. These demand a separate approved implementation after identity/tenant design is established.

## Review criteria

Preserve the product North Star (**assess the evidence before asking questions**) and M3D/M4A source-binding semantics. Follow repository `AGENTS.md`, official product blueprint, and [Issue #9](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/9). Check current working tree; implement on the existing feature branch and draft PR, never directly on `main`. Use only synthetic fixtures. Compile `app.py` and touched modules **before** isolated full pytest; run `git diff --check`, review the full change set, and require GitHub Actions Unit + PostgreSQL compatibility. Stop for independent security/TPRM review; do not auto-merge.

## Real-data pilot prerequisites still open

- Trusted external IdP, issuer/audience/session validation, deployment-specific role mapping, session expiration
- Organization/tenant and service engagement authorization that cannot be supplied by client-controlled selectors
- Secured, malware-scanned, encrypted and audited evidence ingestion/retrieval/retention; no arbitrary file-key reads
- Provenance/authenticity checks and customer/standards mapping validation
- Governed reviewer identity and decision audit, real analyst usability and accuracy validation

M4B-1 is a **protective foundation only** and must not be represented as production authorization or secure real-vendor processing.
