# M7 Phase 5: durable synthetic analyst assessment revisions

## Baseline, audit and decision before coding

[Issue #59](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/59)
starts from protected main `08e4e532b635cd54e75e850b812b20d087a5df2a`.
[Post-merge CI 45307405102](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/45307405102)
passed both jobs before implementation. Work uses a fresh worktree and
`feature/m7-resumable-analyst-assessment`. Read the issue/comments, AGENTS,
official E2E workflow, M7 audit/Phase 2–4 and actual upload, methodology, review,
report, custody, session and migration foundations. Existing 16 draft heads are
unchanged. Actual #21 adds notes/export and alternate 0015 migrations; #45/#47
contain superseded upload/intake UI changes. None is adopted or rewritten.

The customer Streamlit route stops before DB imports. Its demo role, methodology
registry, widgets and original uploads live in memory; it has no trusted browser
session transport. Wiring those objects to custody would promote a demo principal
to authentication. **Leave that UI isolated.** Build the issue's permitted real
server-internal durable save → leave/restart → resume → cited review/report path.
This is not an end-user Save button or completed E2E product.

## Smallest working slice and acceptance

Persist one bounded, versioned canonical JSON assessment contract as immutable
revisions. Do not serialize Streamlit state, Python objects/pickles, evaluated
facts, outcomes, risk calculations, worklists or report snapshots. Reconstruct
those using the existing upload/review/report functions and authorized originals.

- A strict contract carries explicit Intake fields, a full validated organization
  methodology/version/fingerprint, one to four exact custody references (IDs,
  generation, hash and size), source declaration metadata/fingerprints, bounded
  native analyst annotations and insufficient-only need reviews, and an optional
  completion fingerprint/time. Cap canonical state at 64 KiB and each original
  at the existing custody 64 KiB cap. The separate session upload's 2 MB/10 MB
  limits are not advertised or silently truncated by this path.
- Public save accepts configuration/original references only. Prior action,
  insufficiency and completion history is carried from the latest stored
  revision, never replaced by client-supplied review/approval flags. Separate
  fixed record-review/finish commands reconstruct the current model, invoke the
  existing review/completion functions and append their source-bound records.
  No generic CRUD, callback, state evaluator or new approval workflow.
- All commands freshly use the existing server-session lease and locked SQL
  membership, grant and exact assessment relationship boundary. Require
  assessment.manage plus evidence.read. Save originals first through the merged
  custody service; revisions reference staged immutable originals. Inside one
  revision transaction, reuse a narrow custody read primitive with that same
  session/scope; do not nest public custody transactions or reuse a preflight.
- Bind intake assessment ID and methodology organization to server-derived SQL
  identity, not browser names. Validate every source against the exact assessment,
  custody generation, original name/hash/size and captured date. Original source
  capture/scope declarations remain separate from current intake. Legacy paths,
  other organizations/siblings, mismatched generations and hashes deny uniformly.
- Resume retrieves originals afresh, rebuilds bounded source bindings and verifies
  their fingerprints. Evaluate under the current server UTC date, preserving each
  original capture/observation date and declared scope. Never recapture an old
  source with today's date or replay old Request Evidence commands as new reviews.
  Original review fingerprints determine currentness. Changed intake, sources,
  requirements, saved methodology or date-sensitive context stale old reviews
  and completion. Unexpected rebuilt source fingerprints or unsupported contract/
  engine versions deny. Rule/serializer upgrades require explicit version-
  compatibility review; matching hashes do not prove unchanged technical meaning.
- The saved methodology is the assessment's captured version. New saved versions
  invalidate affected reviews; there is no deployed authoritative active-policy
  registry, so external unsaved policy changes cannot be detected or claimed.
- Return the same provisional source-linked review/report and original-byte ZIP
  through the existing report/package builders, with an explicit durable,
  server-authorized synthetic persistence wrapper. Do not mislabel persisted data
  as session-only or claim production human authentication. No control approval,
  numerical residual risk, vendor decision or outreach is introduced.

## Ownership, revision and failure lifecycle

Add only `0014c_assessment_revisions` after `0014b`. One append-only table stores
assessment/revision, exact organization/vendor/engagement ownership, an anchor
custody Evidence reference, canonical state bytes/hash and server actor/time.
At least one verified immutable original is required; its existing custody guards
retain the assessment and all parents against deletion/replacement/ID reuse.
No duplicate parent-retention framework is needed. New table guards validate
anchor ownership, contiguous revision sequence, immutable rows and replacement
protection, including SQLite with foreign keys/recursive triggers off.

Require expected_revision for every mutation. The existing locked assessment row
serializes writers; a unique assessment/revision and guarded contiguous append
reject stale/replayed/concurrent updates. Resume returns only the latest revision;
old snapshots cannot roll back a newer methodology or source inventory. Retain old
rows for history, not as alternate authorization capabilities. Refuse destructive
downgrade and unsupported offline PostgreSQL migration before new DDL. Preserve
populated legacy rows/root pages. #21's alternate 0015 chain remains separate.

Staged originals and revision commits are separate operations: a failed revision
can leave an unattached immutable original. Pre-commit revision failures roll
back that append. Lost commit acknowledgements or later session cleanup can
leave a committed unacknowledged revision. Return no data then, never promise
rollback or delete provenance automatically. A fresh authorized latest resume
can recover the committed revision, and expected_revision prevents replaying an
old mutation. This does not supply general upload reconciliation or idempotency.

## Verification and remaining blockers

Prove actual original → save → destroy in-memory state/process-owned session →
new verified session → resume → cited insufficiency/finding → completion/report
and ZIP, then new evidence/methodology/date → stale history → explicit re-review.
Test strict malformed/oversized/duplicate/unknown JSON, no unsafe deserialization,
wrong tenant/sibling/IDs, expired/revoked/ambiguous authority, source/hash mismatch,
stale/replayed revisions, failed/ambiguous commits, immutable ownership, restart
durability and real PostgreSQL concurrency/migrations. Preserve all earlier tests.
Compile app.py and all touched Python before focused/full SQLite/PostgreSQL CI;
inspect complete diff/whitespace; require independent exact-head security review.
Draft PR only; no main changes or merge without explicit owner approval.

Still blocked: deployed IdP/browser/durable sessions, safe customer-route wiring,
larger/malicious-content custody, encryption, retention/deletion/backup, access
audit, authoritative active methodology administration, upload reconciliation,
vendor delivery and final governed decisions. SQL/session authorization remains
point-in-time; returned data cannot be retracted. Privileged DB writers and server
wiring remain trusted. Hashes prove consistency, not external authenticity.
No real/confidential evidence, production access, external AI or automatic risk
decision is enabled. Qualified TPRM professional validation remains deferred
until the complete E2E application is built.
