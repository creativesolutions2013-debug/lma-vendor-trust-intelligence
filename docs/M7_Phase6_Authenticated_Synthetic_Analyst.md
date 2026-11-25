# M7 Phase 6: authenticated synthetic analyst journey

## Baseline and decision before coding

Issue #61 and its owner implementation handoff authorize work after PR #60's
merge. Protected main is `d66c981c01df233ddbab30ddb84a8266170482be`.
[Post-merge run 45522462933](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/45522462933)
completed both Unit tests and PostgreSQL compatibility successfully before code
changes. Work starts on `feature/m7-authenticated-synthetic-analyst` in a fresh
worktree. AGENTS, the official end-to-end workflow, M7 Phase 2–5 and M4 identity,
session and tenant-read contracts were read. The 16 other open drafts retain
their previously audited heads; #21's alternate migration chain, superseded
#45/#47 and frozen M5/M6 work are not adopted or changed.

The current Streamlit assessment runs with development roles and in-memory
widgets, not a trusted browser session. Its WebSocket/rerun/cache lifecycle has
no cookie-to-server identity bridge. Wiring a Save button there would grant
authority to demo state. The existing OIDC core verifies signed tokens and
state/nonce/PKCE, but has no HTTP transport. The custody and revision services
already provide the actual authorized save/rebuild/review/export operations.

Decision: build one separate, loopback-only HTTPS synthetic analyst surface,
with one server-provisioned identity and assessment. Reuse the existing OIDC,
server sessions, SQL membership/grants, custody and revision services. This is
a usable browser proof, not a production identity provider, vendor portal or
replacement dashboard. Binding an existing authorized assessment avoids adding
provisioning and approval workflows.

## Threats and acceptance

- Explicit development startup only; bind literal `127.0.0.1`, HTTPS and a pinned
  high port. Preserve normal OIDC HTTPS configuration; allow the pilot's exact
  HTTPS loopback URLs only through an explicit synthetic configuration. Never
  substitute a logical callback for the browser's actual callback URL.
- A local test-only IdP authenticates a fixed synthetic analyst using an
  operator-chosen synthetic password. Store only a salted password derivation in
  process memory. No credential in argv, environment, source, logs or database.
  Generate independent token-signing and TLS keys; verify actual signatures via
  the merged OIDC verifier. Bound state, code lifetime, attempts and stores.
- Browser-bound one-use state/nonce/PKCE, exact issuer/client/callback, separate
  login/provider/session CSRF tokens, exact POST Origin and Host. Reject duplicate
  fields, cookies, ambiguous framing and unsupported requests. Secure, HttpOnly,
  host-only SameSite cookies; no handles/tokens in URLs or HTML. Logout must
  revoke before claiming success. No trust in forwarded headers or DTO roles.
- Fresh server session and SQL tenant/evidence authorization for each save,
  resume, review, finish and ZIP read. Scope is server-owned; submitted IDs,
  histories, approval flags or storage references cannot choose authority.
- A concise page binds the authorized assessment, accepts a short use case and
  synthetic TXT originals, shows customer thresholds, exact citations, provisional
  outcomes, gaps and history, and records explicit review/rationale. Save, leave,
  sign back in, resume the latest revision and export the existing intact ZIP.
- At most four originals of 64 KiB each, with the existing 64 KiB canonical state
  cap. No silent truncation or reuse of the Streamlit 2/10 MB upload limits.
  Initial intake or explicit full replacement inventories are supported; incremental
  attachment reconciliation and general file custody remain separate.
- Changed source/context/threshold/date preserves and stales historical review.
  Expected revision rejects stale writes. Fail closed for wrong scope, revoked,
  expired or rotated sessions, revoked grants, tampering and ambiguous outcomes.
  Render all source, filename and analyst text as escaped text. No untrusted HTML.
- Test actual HTTPS request/cookie journeys and a real Chromium UI journey using
  only synthetic certificate trust. Compile app.py and touched Python before
  focused/full SQLite and PostgreSQL tests; retain real database concurrency and
  migration checks. Inspect the complete diff and obtain independent exact-head
  security/code review. Draft PR only; no merge without owner approval.

## Lifecycle and limits

The local fixture IdP and application share one process/origin; this proves a
synthetic browser transport, not cross-site production SSO. Sessions and login
transactions are process-local; restart requires sign-in again. The dedicated
SQLite pilot directory contains synthetic durable state and an unencrypted TLS
private key and must be private. A self-signed certificate requires an explicit
local browser trust step. Never disable TLS verification for a deployed service.
No public bind, proxy deployment, production mode or live provider is supported.

The merged point-in-time SQL/session issuance boundaries still apply. Already
returned bytes cannot be recalled. A failed source batch or stale revision may
leave staged immutable originals; lost commit acknowledgement can leave a
committed revision. Do not promise rollback, blindly retry or delete provenance.
Fresh authorized resume is the recovery path. Fixed local provisioning is not
customer administration. Hashes prove retained consistency, not source truth.

All control outcomes remain provisional. Annotation/finish cannot confirm a
technical fact, approve a vendor or calculate authoritative residual risk.
Customer methodology is the captured snapshot; unsaved external policy changes
remain undetectable. Professional TPRM validation stays deferred until the full
end-to-end application is complete.

Remaining end-to-end gaps include secure vendor submission, source-safe semantic
confirmation, governed final decisions/remediation and their integrated report.
Production IdP/durable sessions, encryption/key management, malware quarantine,
retention/deletion/backup, reconciliation and access audit remain launch gates.
No confidential evidence, production access, external AI or outreach is enabled.

## Run the actual synthetic analyst journey

Install `requirements.txt` in a local virtual environment. The directory below
must be new on first launch; a marked existing runtime can subsequently be
reopened. Do not point this command at any customer database or existing data
directory.

```bash
env -u DATABASE_URL AUTH_MODE=development python -m src.synthetic_analyst_pilot \
  --directory /tmp/lma-synthetic-analyst --port 8443
```

1. Choose a synthetic-only password at the terminal prompt (at least 16
   characters). It is not persisted and must be chosen again after restart.
2. Explicitly trust only the generated `localhost.crt` for this local browser
   experiment, then open `https://127.0.0.1:8443`. Do not expose or forward this
   single-process fixture server publicly. No proxy/forwarded-header mode exists.
3. Select **Sign in**, then authenticate at the local synthetic IdP with that
   password. The workspace binds the preprovisioned Synthetic Vendor / Synthetic
   Analytics assessment through current SQL membership and engagement grants.
4. Attach [the synthetic recovery plan](../fixtures/synthetic_analyst_pilot/recovery-plan.txt)
   or your own nonconfidential UTF-8 TXT (1–4 files, at most 64 KiB each). Choose
   its declared kind, requirement and observation date. **Save evidence and
   evaluate** persists originals and the revision. Scope metadata is a declaration,
   never inferred authenticity or operating proof.
5. Open a requirement's exact quotations and threshold. Record a rationale and
   **Request Evidence** with explicit insufficiency confirmation, or another
   draft annotation. Requests are displayed/exported, never sent to a vendor.
6. **Sign out**, close the browser tab, sign back in and resume the latest saved
   revision automatically. **Finish review** and **Download assessment package**
   produce the existing source-traceable report/manifest/methodology/original ZIP.
   Finishing does not approve the vendor or supply numerical residual risk.

On a stale/denied/unconfirmed save, resume latest before resubmitting. Full-file
replacement can stale earlier review and completion. Runtime restart preserves
assessment history and authorization changes; it never reseeds or renews grants.
The fixture membership/grant expire after seven days and TLS certificate after
thirty days. Unknown/partial runtime directories are refused for manual
inspection; there is no destructive reset or automatic repair command.

Recommendation: **build** this small analyst path, **simplify** to one fixed
authorized scope and TXT fixtures, **defer** production deployment and vendor
delivery, and **reject** treating demo roles, a hash or a Save button as authority.
