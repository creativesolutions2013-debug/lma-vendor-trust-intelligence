# M7 Phase 2: leased, server-authorized snapshot metadata prerequisite

## Verified baseline and security gap (before coding)

Implements [Issue #53](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/53)
from protected main `30dab84ce4dc709ba246bdebab12c1b75bb4b5b4` after #52.
[Main push CI 44983610018](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/44983610018)
passed Unit/SQLite and PostgreSQL. All 16 open PRs and actual diffs were checked
before design; their exact heads remain the checkpoint recorded in the M7 audit.
In particular #21 supplies unmerged notes/CSV/migrations, not snapshots, custody
or a transaction-bound save authority. None of that work is copied or merged.

Read AGENTS, the full issue and empty comment thread, official workflow, M7 audit,
and M4C identity/session, tenant-read and evidence-authorization documentation.
The October 20 handoff is historical. Professional TPRM validation stays deferred
until E2E completion by owner instruction; no validation results are invented.

The customer assessment remains session-only. `SessionIdentitySource` already
authenticates a server handle and resolves unique current membership.
`TenantReadService` already pins dependencies and locks membership/grants and
canonical relationships through successful SQL issuance. PostgreSQL uses the
mandatory membership predicate guard; SQLite reserves its writer. Reuse these
foundations and their exact assessment→engagement→vendor→organization links.

**Gap:** `SessionStore` makes authenticate/revoke/rotate atomic individually, but
does not coordinate a session operation through SQL transaction completion. Two
successful identity DTO observations cannot close that interval. The existing
read-boundary documentation explicitly acknowledges it. A separate
`get_assessment()` followed by saving client/session data would also introduce a
check/use gap and infer ownership of content that was never securely captured.

## Smallest defensible design

Build an **unwired, read-only synthetic metadata capture/revalidation proof**, with
the missing session-operation coordination first. Do not implement persistence
or application restore until deployed identity and custody/store semantics are
selected and reviewed. No DB model, table, migration or historical-row rewrite.

1. Extend the existing server-session store/manager with an optional operation
   lease. Unsupported stores deny. The synthetic in-memory implementation holds
   the same lock used by authenticate/revoke/rotate; acquisition is bounded and
   exceptions release it. Reentrant revoke/rotate of the leased handle fails
   without mutation; nested leases deny. Pin manager/store/clock/limits and source
   handle/database-factory dependencies. A lease/DTO is never a reusable tenant
   capability.
2. Reuse `SessionIdentitySource` and `TenantReadService` in one narrow server-side
   service. Each capture or validation gets a current session lease, a fresh
   locked SQL authority transaction and exact linked assessment ownership.
   Use assessment-manage permission from current membership, not a demo role.
   Release no metadata until SQL completion, final session validation and pinned
   dependency checks succeed. Missing configuration and request-supplied identity
   stand-ins deny. No browser organization selector or app registration.
3. Capture only a fixed, versioned, bounded **synthetic metadata envelope**:
   server-derived organization/vendor/engagement/assessment IDs plus versioned
   context and evidence-inventory metadata fingerprints. No arbitrary fields,
   uploaded bytes, filenames/keys as authority, tokens, notes, facts, review flags,
   approval state or risk values. Bound source inventory and selected column
   lengths; overflow/inconsistent ownership denies rather than truncates.
4. Validate a round-tripped envelope only after fresh authorization and recapture
   of those server-owned metadata bindings. Unknown/duplicate fields, invalid
   types/versions/size, wrong assessment/ownership or changed context/source
   inventory denies. The unsigned envelope is **data**, not a credential or proof
   of source authenticity. It cannot restore evidence, interpretations, reviews,
   methodology settings, approvals or Streamlit state.

The source fingerprint covers selected **database inventory metadata**, not bytes
or complete provenance; real evidence must be reattached and independently
validated later. This contract intentionally cannot resume the current customer
session, whose requirements/methodology/originals do not have trusted durable
ownership. Future persistence needs a new versioned, separately scoped contract.

## Concurrency and trust boundary

Revocation/rotation completed before acquisition denies. A leased operation that
acquires first serializes before competing revocation/rotation; successful future
operations must reauthenticate and deny the old handle. Same-thread mutation
attempts return failure, never a false successful logout. Lock timeout denies;
this synthetic global store lock favors a small proof over multi-user throughput.

Acquire SQL authority before the session lease, matching existing tenant reads'
SQL→session order. Complete successful SQL inside the lease; rollback after a
denied lease cannot issue metadata. This avoids a store→SQL / SQL→store wait
cycle with existing reads. SQL locks remain held through transaction completion.
Fresh checks reject observed
membership/grant/ownership changes. A synthetic blocked-commit regression also
reproduced grant-only and membership-only expiry after the existing final SQL
check. Extract the existing cached deadline check into one shared helper and
invoke it after successful SQL completion and lease cleanup, immediately before
return. This rejects expiry during commit or final session-store work without
new SQL, a new identity framework or any persistence. It checks deadline
freshness, not SQL revocations committed after the protected SQL boundary. This is a
**point-in-time issuance** contract: revocation after issuance cannot retract
returned metadata; time is checked at defined authorization points, not magically
atomically with SQL/network delivery. It does not provide instant cancellation,
distributed leases, durable sessions, deployed IdP trust, production login or
secure byte custody. Store/database administrators and server wiring are trusted.
Test doubles are confined to synthetic tests and never registered as production
authority. Production authentication remains disabled.

## Acceptance and affected files

- Authorized synthetic metadata capture→round-trip validation succeeds using
  actual server-session and membership/grant foundations; include signed local
  code-flow integration. No metadata is returned for absent/fake identity,
  expired/revoked/changed session, ambiguous membership, revoked grant, other org,
  ungranted sibling, unlinked or mismatched assessment, dirty/failed transaction
  or swapped server dependency.
- Strict envelope tests reject malformed/oversized/duplicate/unknown fields,
  source/context version or fingerprint changes, invented approvals/facts/bytes
  and changed ownership. Revalidation is never authority reuse. No listing API.
- Concurrency tests cover both revoke/rotate race orders, the final-check/commit
  interval, reentrant attempts, expiry, timeouts and exception cleanup. Real
  PostgreSQL connections exercise concurrent grant/parent changes with the
  existing guard; SQLite is not represented as proof of PostgreSQL locking.
- No stored evidence or review data, no persistent metadata table, no live provider
  or UI activation, no main/old-PR changes. The snapshot is a bounded consistency
  prerequisite, not production save/resume or a control outcome.
- Compile app.py and touched modules before focused/full pytest. Run full
  isolated SQLite and PostgreSQL Actions, inspect complete diff and require an
  independent exact-head security/code review. Draft PR; no merge without explicit owner approval.

Intended files: existing server-session and identity-source lease extension; shared cached-window
validation extracted from `tenant_read_scope.py`;
new metadata contract/service; synthetic lease, metadata and real-DB concurrency
tests; compile/focused CI steps; this document. Existing auth startup, DB models,
migrations, app.py/customer UI, storage, evaluators and governed services excluded.

## Remaining E2E work

Durable snapshot storage and immutable ownership/incarnation/versioning, deployed
session/IdP/browser transport, source custody/quarantine/encryption/retention,
methodology/source reattachment and stale-review restoration, multi-user handoff,
source-safe semantic control review and final governed decisions remain separate.
No professional validation, secure production save/resume or completion of M7 is
claimed by this prerequisite.
