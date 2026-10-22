# M4C-2B-1 — Tenant-scoped read proof

**Status:** Draft, unwired read service and synthetic tests, corrected for PR #19's independent review. Not connected to app.py or real authentication. Production remains disabled. Tracks Issues #16/#17.

## Boundary

The read-only TenantReadService returns immutable vendor, engagement, assessment, evidence metadata and scoped counts. It requires an injected trusted identity source, database-verified current membership, role permission and explicit current engagement grants. All read queries constrain organization and matching vendor/engagement/assessment/evidence relationships. Sibling engagements without grants and legacy null links are not returned. Storage paths, bytes, tokens, risk scores and governed actions are never returned.

Identity providers, cookies, callbacks, distributed session storage and deployed tenant protections are **not implemented** by this slice. Caller-created identity objects are not authentication; the source must be secured by separately reviewed server integration. This is a synthetic proof, not a production guarantee.

## Authorization consistency and issuance

Each list, exact lookup and complete counts result uses one dedicated database
transaction. PostgreSQL locks membership, grants and canonical parent rows with
`FOR UPDATE` in a fixed order before projection, holding those locks through the
last session lookup and authorization validation. Concurrent revocation, role or
ownership changes on those rows must commit before authorization is acquired or
wait until issuance completes. SQLite uses `BEGIN IMMEDIATE` to reserve the writer
for the same bounded operation; it is not proof of PostgreSQL locking behavior.
Unsupported dialects, dirty sessions and database/identity failures deny.

Each transaction pins the exact server-supplied identity-source object and SQL
session factory before its first authentication call. Both identity lookups use
that captured source; replacing either dependency during authentication, SQL work
or final validation discards the complete response, even when a replacement
returns identical issuer/subject/session fields. Scope DTOs are not credentials.

PostgreSQL also holds a shared transaction advisory lock for the membership-table
OID and exact issuer/subject predicate before reading membership rows. A database
trigger takes the corresponding exclusive lock for membership INSERT/UPDATE/DELETE,
including both old and new identity keys. This serializes new same-identity
memberships in another organization through issuance, including direct SQL writers.
Unrelated identities and independently owned schemas use different keys. Hash
collisions can add contention; they do not grant permission. The database trigger
must be installed and enabled ALWAYS; an absent or disabled guard denies reads.
PostgreSQL transactions must use Read Committed; repeatable snapshots and driver
autocommit deny because they cannot provide this issuance contract. Existing
databases must apply the guard migration before scoped reads can resume.

The additive `0014a_membership_identity_guard` migration installs only PostgreSQL
guard functions/triggers and advances the migration version; it does not backfill
memberships, assign ownership or rewrite data. SQLite retains its native writer
reservation. Destructive guard downgrade requires separate owner review. A row
UPDATE can acquire its tuple lock before its trigger runs, so conflicting lock
orders may abort a transaction under the existing bounded SQL timeouts; callers
must treat that as denial/retry. This is not a deadlock-free scheduling claim.
Privileged database owners can disable guards; ordinary SQL writers cannot bypass
them, and deployed administrative privileges remain a separate security boundary.

The final check compares the current server session with the initial session,
then validates current membership, effective role, grants, relationship snapshot
and fresh time windows under the held locks. No identity-provider lookup follows
that database check. Results are issued only when the transaction successfully
finishes; failed validation or commit discards the entire result. Counts use
SQL aggregates in this one scope and return four zeros on any failure, never a
mixture of successful and denied child lists.

This defines a point-in-time issuance boundary, not retrospective revocation of
metadata already issued. SQL locks do not atomically lease an external session
store: a rotation/revocation observed during the final session lookup denies;
a change after its successful observation cannot retract issued metadata. A
future deployed session/SQL integration must define a coordinated session lease,
timeouts and delivery lifecycle before claiming stronger revocation guarantees.
New grants/rows are not permission to expand an already captured scope. No live
runtime or byte-read capability is enabled here.

## Bounded discovery

List methods retain immutable tuple results and add keyword-only `limit` (default
100, maximum 200) and `after_id` (default 0). IDs sort ascending; use the last
returned ID as the next cursor. Invalid page arguments deny. Parent filters and
exact lookups independently reauthorize. Counts describe the entire authorized
scope, independently of list limits. Pages are separate authorized transactions;
there is no cross-page snapshot or cursor authority token. Assignment and due-date
UX remain separate Issue #17 work.

Returned pages are bounded; authorization fingerprints still scan/lock the
existing granted hierarchy, and whole-scope counts require aggregate scans.
This is not a production-scale query-cost bound. PostgreSQL lock waits are
limited to three seconds and each statement to ten seconds; timeout denies.
Narrower page-specific locking and deployed identity-call timeouts remain
performance/availability review items before live integration.

## Legacy route inventory: all remain blocked for production

| Source location | Gap |
| --- | --- |
| app.py:440 Control Tower | Global vendor, finding, event, evidence and assessment reads |
| app.py:868 Vendors | Global vendor selection and related detail reads |
| app.py:4891 Intake | Writes and links require organization ownership and permission enforcement |
| app.py:5095 Assessments | Global vendor/assessment selectors, downstream reads and updates |
| app.py:6661 Evidence Center | Global vendor/evidence listing |
| app.py:7252 Evidence upload | Direct stored byte write based on selected vendor |
| app.py:7498 Evidence review | Global evidence selection and related records |
| app.py:7781 Findings | Global vendor/finding reads and update paths |
| app.py:8200 Monitoring | Global vendor/event reads and writes |
| app.py:9048 Reports | Global aggregate/CSV export |
| app.py:9135 Audit | Global log reads |
| Other existing services | Complete tenant isolation not verified |

The service does **not** make these paths safe; no route was wired in this milestone. Streamlit role checks are insufficient for relationship-scoped authorization.

## Acceptance and limitations

Synthetic tests cover two organizations, different roles, siblings, null/inconsistent parent links, expired/revoked grants/memberships and sessions, forged roles and selectors, changed relationships during I/O, source outages, consistent counts and bounded pages. Direct PostgreSQL integration/concurrency cases use temporary UUID-owned schemas in a synthetic service; they never inspect customer schemas. No real secrets or evidence are involved. Exact validation results and remaining limits are recorded in PR #19.

Before merge compile app.py and touched Python files, run full pytest, check diff and both GitHub Actions jobs, and obtain independent security/product review and explicit owner approval.

**Next:** M4C-2B-2 scopes all legacy reads, writes, uploads and exports. M4C-2B-3 integrates an explicitly selected IdP and secure browser/session deployment. Evidence-byte storage/audit/encryption/retention controls and external review remain separate launch gates.
