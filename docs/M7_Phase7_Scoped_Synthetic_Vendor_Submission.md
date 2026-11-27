# M7 Phase 7: scoped synthetic vendor evidence handoff

## Baseline and decision before implementation

Issue #63 starts at protected main
`aaff7b1c4581c86e358497c2e1d4c3649c443e36`. Both required jobs in post-merge
Actions run `45527409536` succeeded before coding. Work uses the fresh branch
`feature/m7-scoped-synthetic-vendor`. AGENTS, the official end-to-end workflow,
Phase 4–6 custody/revision/identity contracts and live services were inspected.
The 16 open drafts, including #21's alternate migration chain and superseded
#45/#47, are not adopted or changed. No original handoff document is attached.

Build one narrow cross-role journey on the existing development-only HTTPS
surface. A separately authenticated fixed vendor representative receives a
short-lived assessment invitation by explicit local copy, submits one synthetic
TXT original, and an analyst explicitly captures and appends it to the existing
assessment. The analyst sees exact sources, provisional gaps and history, then
reviews and exports the intact report package. No email or real invitation is
sent. No production access or governed decision is enabled.

The existing membership and immutable custody tables have frozen role constraints
that exclude vendors. Rewriting them, mislabeling the vendor as an analyst, or granting the
vendor assessment.manage would violate this slice's boundary. Therefore vendor
delivery enters a bounded, immutable-in-memory pending record first. Explicit
analyst capture uses the unchanged custody API under the analyst's own current
authority. A new additive immutable sidecar records actual vendor delivery
identity separately from the analyst custody actor, atomically with the source
append revision. Delivery alone is not durable custody or analyst acceptance.

## Trust boundaries and bounded contracts

- Explicit opt-in development runtime only: fixed loopback HTTPS, private local
  SQLite, synthetic fixtures and independent operator-chosen passwords. Vendor
  OIDC uses its own fixed subject, audience, signing key, session store and CSRF
  key. Separate cookie names and authentication paths prevent analyst cookies
  or callbacks from authorizing vendor requests or the reverse.
- The vendor has no SQL organization membership, role or engagement grant. Its
  signed server session plus one invitation authorizes only pending delivery.
  Existing tenant/evidence/revision services therefore deny vendor sessions.
  An invitation selects one exact assessment and requirement. Browser IDs and
  role fields confer nothing. Pending delivery requires the inviting analyst's
  original live session and freshly locked SQL authority; signing out, expiry or
  rotation invalidates an unsubmitted invitation. This deliberately narrow local
  sponsorship does not implement durable vendor delegation.
- Invitation v1 state is process-local, bounded to 32 records and one TXT per
  invitation, at most 64 KiB. A 256-bit token is stored hashed, expires after ten
  minutes, is revocable and is reserved once under a lock. It is shown once only
  to the authorized analyst for local transfer to the fixed representative.
  It appears only in a vendor POST, never a URL, cookie, log or report. Public
  correlation IDs are not bearer capabilities. Restart invalidates invitations.
  Delivery revalidates the exact issued record after vendor lease entry and
  authentication callbacks; an acknowledged revocation or completed one-use
  delivery cannot be overwritten by an older invitation snapshot.
- Fresh SQL membership/grant, exact ownership, current session and optimistic
  revision checks gate delivery and capture. Revocation, ambiguity, expiry,
  rotation, cross-scope requests and changed authorization deny. Pending bytes
  are not returned to the vendor or other identities. Vendor pages contain only
  sign-in, invitation/token and single-file submission controls plus a generic
  acknowledgment, not assessment internals.
- Analyst capture preserves existing originals. Under the locked revision
  transaction, append exactly one verified custody reference, enforce four total
  originals, unique names/hashes/references and the existing 64 KiB state cap.
  Preserve all review/completion history. Changed requirement evidence stales
  relevant review and completion; unrelated unchanged judgments remain current.
- Add only `0014d_vendor_handoff` after `0014c`, retaining existing custody and
  revision tables and populated rows. Sidecar v1 canonical JSON is capped at
  4 KiB and anchored to exact custody ownership, ID, generation and hash. Record
  the non-bearer vendor session, invitation purpose/correlation, source
  declarations and inviting analyst. SQLite WITHOUT ROWID plus replacement
  denial and PostgreSQL ENABLE ALWAYS mutation guards preserve history.
- All declarations remain unverified. Existing source-linked evaluators compare
  customer thresholds; neither delivery, capture, annotation nor finish confirms
  facts, establishes compliance, approves a vendor or assigns residual risk.

## Failure, restart and scope limits

Pending delivery is lost on restart; the UI must never label it durable. A
captured original and appended source survive restart through existing custody
and revision services. Custody capture and revision append remain separate
commits: an append failure can leave an unattached immutable original. An
ambiguous custody acknowledgment is terminal for automatic capture; do not
blindly stage another copy, delete provenance or promise rollback. If capture
was acknowledged, retain its receipt in the queue and retry only the explicit
revision append after fresh authorization. An ambiguous append is recovered by
resuming the latest authorized revision and checking its exact source reference.

This is a single-process local synthetic proof. Production IdP/durable sessions,
real vendor communication, encryption/key management, quarantine, retention,
backup, reconciliation and professional assurance remain separate gates. Human
TPRM evaluation stays deferred until the complete E2E application works.

## Required verification

Run a new private runtime (existing Phase 6 directories are never upgraded or
repaired automatically):

```bash
env -u DATABASE_URL AUTH_MODE=development python -m src.synthetic_analyst_pilot \
  --directory /tmp/lma-synthetic-vendor-pilot --port 8443 --vendor-submissions
```

Choose different synthetic analyst/vendor passwords at the terminal prompts.
Trust only this local runtime's generated TLS certificate. Sign in as analyst at
`https://127.0.0.1:8443/` and save a small initial source. Select a requirement and
**Create local vendor invitation**. Privately copy the one-use code to the fixed
representative's separate browser profile, then return to the assessment while
remaining signed in. At `https://127.0.0.1:8443/vendor`, sign in using the vendor
password and submit the code plus one synthetic TXT original and its declarations.
The [authored recovery exercise](../fixtures/synthetic_vendor_pilot/recovery-test.txt)
is a small example; choose kind **test** and its stated observation date. Its
scope, metrics and exception remain unverified source claims.
The vendor sees only a generic pending-delivery acknowledgment. Back in the
analyst browser, refresh and select **Capture vendor evidence and reassess**.
Inspect original hashes, exact quotations, current/stale review labels and the
remaining focused gaps; record a draft review, finish, sign out/sign in, resume
and download the package. Vendor delivery provenance is included in report.json
and the printable summary, separately from the analyst custody actor. It proves
local fixture attribution and retained consistency, never external source truth.

An invitation expires for submission after ten minutes. An already acknowledged
pending delivery remains available for explicit capture until revoked or process
exit. Capture/import holds the queue operation lock through its outcome, so
revocation either precedes intake or follows a completed import; it cannot claim
successful revocation while the same pending intake is being appended.

Compile app.py and every touched Python/migration before tests. Exercise actual
HTTPS and Chromium analyst invite → independently authenticated vendor submit →
analyst capture/reassess/review → report, including fresh login/resume. Verify
original bytes/hashes, durable delivery provenance, targeted staleness and no
governed writes. Test hostile input, token disclosure/replay/concurrency,
expired/revoked sessions/invitations, changed grants/ownership, adjacent scopes,
capacity/duplicates, stale revisions and ambiguous failures. Run full SQLite and
PostgreSQL CI, additive migration checks, full diff/whitespace inspection and
independent exact-head security/code review. Open a draft PR only. No merge is
authorized.

Recommendation: **build** this verified cross-role synthetic handoff, **simplify**
to one fixed representative and explicit analyst capture, **defer** durable
delegation, production delivery/storage and governed decisions, and **reject**
promoting invitation possession or vendor assertions into analyst authority or
control assurance. The next E2E blocker is source-safe human semantic confirmation
and governed findings/decisions, alongside a separately designed durable vendor
delegation and delivery lifecycle.
