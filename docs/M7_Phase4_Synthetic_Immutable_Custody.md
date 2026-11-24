# M7 Phase 4: synthetic immutable evidence save/retrieve

## Baseline and pre-code custody assessment

[Issue #57](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/57)
starts from protected main `9ec4f9ba34a6eb964fbbbf46d71161274ba77b33`.
[Post-merge CI 45302903791](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/45302903791)
passed both jobs before implementation. Work uses a fresh worktree and branch
`feature/m7-synthetic-immutable-custody`. Read the full issue and empty comments,
AGENTS, official E2E workflow, M7 audits/Phase 2/3, M4 security contracts, actual
storage/models/authorization/session code and legacy upload. The existing 16
drafts retain the heads recorded in the M7 audit. Actual #21 changes concern
notes, export, retention and migrations; no custody code is copied or merged.
The historical handoff described in the audit is not a new attached source here.

Threat: a vendor prefix, legacy location or preflight boolean cannot authorize
bytes. Mutable or aliased metadata can transfer historical evidence to a new
assessment or reused ID. Local save overwrites; it has no bounded verified read.
Writing files and SQL separately creates partial-write/orphan cleanup, generation
and acknowledgement problems. A filename, hash or current FK is not provenance.

Decision: a small **SQL-backed synthetic byte store**. Create fresh Evidence and
one immutable custody row with original bytes, server-generated key/generation,
SHA-256, length, exact ownership and server-session provenance in the **same SQL
transaction**. Use existing authorization/lease foundations at point of use.
This is an actual bounded byte round trip, not another preflight or save/resume.

Rejected for this increment: local/S3 objects require a second resource's
publication/cleanup/versioning contract; a separate in-memory dictionary has the
same atomicity gap and restart loss; adopting historical paths infers custody
that was never captured. SQL BLOB/bytea is suitable only for small synthetic
fixtures here, not a production large-file storage selection.

## Intended implementation and acceptance

- A fixed server-internal service saves nonempty exact bytes up to 64 KiB for a
  current authorized assessment. Require current `assessment.manage` AND
  `evidence.upload`; derive organization/vendor/engagement from SQL, never from a
  browser's ownership assertion. Validate a plain ASCII document name of at most
  120 characters; never
  interpret it as a path or parse/execute the content.
- Allocate a fresh Evidence ID and UUID generation; build the exact canonical key
  `vendors/<vendor>/evidence/m7_<generation>.bin`. Unique custody evidence/key/
  generation constraints prevent replacement/collision. No caller key or URL.
- A new empty custody table stores all bytes and immutable metadata together.
  It references the fresh Evidence row and all original parents. Record verified
  issuer/subject, non-bearer session correlation, effective role/membership and
  capture time. This proves recorded ingestion provenance, not external truth.
- Narrow database guards reject custody UPDATE/DELETE/REPLACE, referenced parent
  deletion/replacement/ID changes, ownership reassignment, and changes to the
  custodial Evidence key/hash. Protect SQLite with foreign-key/recursive triggers
  off, including rowid aliases and organizations' unique external_key. Preserve
  unrelated descriptive changes and all rows without custody. PostgreSQL guards
  coordinate insertion with parent changes; require guards enabled ALWAYS.
- Retrieval accepts existing exact relationship selectors plus generation, then
  freshly authenticates and authorizes `evidence.read`. Join current exact parents
  to the immutable original ownership; require exact generation/key/hash/size.
  Fetch at most 64 KiB + 1 from SQL and recompute SHA-256 before returning bytes.
  No key-only, legacy-path, URI, download URL or preflight-boolean read API.
- Resolve bytes only through the immutable custody row's evidence ID and
  generation. A legacy Evidence row may copy a key string, but cannot acquire
  the custody row or its bytes. Global legacy string uniqueness is not required
  for this store and is not claimed; #56 remains a conservative metadata check.
- Extend the private leased-read orchestration with one fixed server-side result
  hook. Preserve SQL-before-lease order, current membership predicate/grant/parent
  locks, dependency pinning, commit inside the lease and final cached deadlines.
  Save excludes only its own newly inserted Evidence row from the prior inventory
  comparison; validate that new row/object independently. No public callback/CRUD
  or new identity framework. Existing read/snapshot behavior must remain intact.
- Object INSERT and pre-commit failures roll back the new Evidence and bytes
  together: no external file to clean up. A lost SQL commit acknowledgement can
  leave the transaction outcome indeterminate; a confirmed commit can also be
  followed by failed session cleanup/deadline checks. Release no receipt or bytes,
  but
  do not claim rollback: an immutable unacknowledged record may remain. No blind
  automatic retry, destructive compensating delete or false successful logout.
  Reconciliation of unacknowledged writes remains a later workflow; any recovered
  reference must still pass fresh authorization to retrieve.

Migration: additive `0014b_synthetic_custody` after `0014a_membership_identity_guard`;
create only the empty table and guards, never backfill or rebuild old tables.
Refuse destructive downgrade before mutation. Test populated legacy rows and
SQLite root pages unchanged. #21's unmerged 0015 independently descends from
0014a; future owner-approved integration must reconcile that chain explicitly.
No production/customer database is migrated by this task.
PostgreSQL migration requires online schema verification; offline generation
refuses before the custody DDL rather than assume a target schema. SQLite offline
DDL emission is covered by a regression.

Acceptance includes exact original-byte/hash/provenance round trip, maximum bound,
wrong IDs/org/sibling/generation, revoked/expired/ambiguous session/member/grant,
key/path/symlink-like name rejection, collision/overwrite/alias/delete races,
tampering, failed insert/commit and post-commit cleanup, dependency substitution,
pragma-independent retention and actual PostgreSQL concurrency/migrations. Compile
app.py and touched Python before focused/full tests. Run full SQLite/PostgreSQL
CI, complete diff/whitespace review and independent exact-head security review.
Open a draft PR only; no merge or main changes.

## Scope and remaining limits

Implemented behavior must be classified as **synthetic and unwired**. Production
startup stays fail closed; no writable customer route, S3 credentials, provider,
external AI, real vendor evidence, parsing or automatic control/risk decision.
This does not connect session save/resume, vendor delivery or the analyst UI yet.

SQL locks define point-in-time authorization through transaction completion;
the synthetic single-process session lease serializes revoke/rotate until release.
Final cached checks reject expiry during commit/cleanup, not later SQL revocations.
Returned bytes cannot be retracted. Trusted database administrators can bypass
guards or replace bytes and hashes together; SHA-256 detects corruption against
the retained digest, not malicious privileged rewriting. Existing scope scans,
lock timeouts and process-local sessions do not prove deployment scale or durable
identity. Guard installation/health checks are required, not optional metadata.

Malware quarantine, encryption/key management, customer retention/deletion,
backup/restore, access audit, unacknowledged-write reconciliation, production
storage and identity deployment remain blocked. No delete API is supplied:
retaining synthetic records avoids silently destroying provenance, but is not a
customer retention policy. E2E completion and qualified TPRM professional
validation are not claimed; professional review remains deferred by the owner.
