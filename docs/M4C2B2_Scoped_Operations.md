# M4C-2B-2 — Scoped operations, first slice

**Status:** Draft implementation stacked on M4C-2B-1 PR #19. The new services are NOT wired into app.py and do not provide production authentication or complete tenant isolation. Track Issue #20.

## Why this is smaller than rewriting every page

The current Streamlit application uses global ORM queries and writes in Control Tower, Vendors, Intake, Assessments, Evidence Center, Findings, Monitoring, Reports and Audit Log. Those paths cannot safely become available to authenticated customers simply because OIDC sessions were verified. Role-based menu visibility does not prevent record-level access.

M4C-2B-1 introduces the test-only tenant-scoped read contract. M4C-2B-2 first extends that contract where a real disclosure would otherwise occur: CSV report export. Safe mutation integration requires separate, reviewed server-authorized business services and is NOT achieved by wrapping Streamlit forms in conditionals.

## Added contracts

- `src/tenant_report_export.py`: metadata-only report with one row per *explicitly granted* engagement and assessment/evidence counts. It reuses PR #19's locked `TenantReadService` transaction, current identity, membership, exact grant and independent `report.export` permission; a claimed global Admin role is ignored. SQL aggregates validate organization/vendor/engagement/assessment/evidence parent links. CSV preparation and final authorization occur under the same held locks. No storage paths, source quotations, evidence bytes, risk scores or governed approvals appear in the CSV.
- `src/production_route_policy.py`: an inventory and deny-first classification for every existing legacy navigation page and common operation, plus unknown paths. Even named scoped capability routes require a separate source-authorized service; **classification never authorizes**.
- `tests/test_tenant_report_export.py`: synthetic authorization, tenant and sibling suppression, role, revocation, expiry, race, CSV injection, and route-coverage regressions.

## Critical limitations

The route policy is NOT connected to Streamlit/HTTP and is NOT sufficient to protect existing pages. Production startup in `src/auth_context.py` remains disabled before side effects; no IdP or cookies are wired. The existing global `render_reports` CSV and other legacy read/write/upload services remain unchanged and MUST remain blocked in any real authenticated deployment.

The corrected export uses one dedicated transaction through a defined issuance
boundary. PostgreSQL locks existing membership/grants and canonical organization,
engagement, vendor, assessment and evidence rows in that order (IDs sorted within
each table); SQLite uses a writer reservation. CSV is prepared before the final
session lookup, then fresh locked SQL authority/relationship and post-I/O time
checks run. Data is returned only after successful transaction completion. A
concurrent revocation or parent reassignment commits before acquisition or waits
until issuance; changed/expired sessions observed at the final lookup deny.
The export caps engagement rows at 200 and denies overflow, rather than silently
truncating either rows or their aggregate counts. CSV formula defenses remain.

Reads, export, note writes and note-history issuance also inherit PR #19's
issuer/subject predicate guard. A PostgreSQL ALWAYS trigger serializes raw SQL
membership INSERT/UPDATE/DELETE against each authorized transaction, including
new same-identity memberships in another organization after the final check.
Read Committed and non-autocommit connections are mandatory; other isolation
modes deny. Unrelated identities do not share an application-wide lock. See
[the foundation boundary](M4C2B_Tenant_Read_Boundary.md) for migration and timeout
limits. Each transaction pins its source and session factory throughout issuance.

This is a point-in-time issuance model, not revocation of metadata already issued.
SQL does not atomically lease an external session store; changes after the last
successful session observation need a future coordinated lease/delivery design.
Authorization fingerprints still scan/lock the granted hierarchy despite bounded
returned rows. PostgreSQL uses 3s lock waits and 10s per-statement timeouts; these
are not whole-request cost or latency guarantees. A deployed endpoint still needs
secure transport, export audit, session timeouts and source custody review.

PR #21 remains stacked on corrected, unmerged draft PR #19. PR #18 was closed
without merge; Issue #17 retains unfinished workspace requirements. No PR is
merged by this correction.

## Next implementation gates

1. Review/merge the tenant read foundation (PR #19) after direct isolated PostgreSQL evaluation, compile and independent review. Resolve overlap with PR #18, do not auto-merge.
2. Treat each existing page as blocked for authenticated production; migrate its **underlying data services**, including writes, approval and risk governance, before enabling the corresponding route. Test new selectors, IDOR, exports, audit, stale sessions, cross-tenant joins and adversarial forged role/org inputs.
3. Evidence upload/download needs safe storage authorization, malware scanning, encryption, retention, file size/type and access audit before real evidence.
4. Actual IdP client, browser callback, cookie/CSRF/reverse-proxy and distributed session/replay stores are a later reviewed M4C-2B-3 gate.

## Acceptance protocol

Compile app.py and touched code before isolated full pytest, review complete diff/whitespace and run Unit + PostgreSQL CI on exact head. Since base PR #19 is not yet merged, M4C-2B-2 must remain draft. Synthetic CI does NOT prove live enterprise multi-tenancy or readiness for customer evidence.

## Assessment and Evidence Center operation boundary (M4C-2B-2B)

`src/tenant_assessment_evidence_operations.py` adds two *unwired* database operations: `record_assessment_review_note(id, text)` and `record_evidence_review_note(id, text)`. They are optional analyst annotations, not new mandatory review steps. They never write approval/status, risk scores, control claims, evidence storage fields, AI outcomes or file bytes.

The trusted server-injected identity must be valid and unexpired. In one independent database transaction the operation obtains the current issuer/subject/organization membership and role, validates the requested assessment or evidence through exact organization/vendor/engagement/assessment/evidence joins, checks a unique active nonexpired grant for that engagement, and enforces the existing `assessment.manage` or `evidence.analyze` RBAC permission. Incoming Admin claims, role selectors and vendor IDs are ignored as authorization.

Note operations use the shared read/export lock order and final authorization
contract, avoiding a separate conflicting lock order. The legacy current-note
field remains compatible while each secure update appends an immutable revision
with exact record/tenant/vendor/engagement/assessment/evidence references,
authenticated issuer/subject/effective role, membership, non-bearer session ID,
timestamp and content. Nonempty legacy rationale without a matching latest
analyst-attributed revision is quarantined in place: a write denies without
overwriting text, creating history or audit, or assigning current ownership.
No automatic `legacy_unknown` capture occurs. This includes legacy notes before
any history exists, even if the present relationship appears authorized.

Revision reads independently reauthorize the exact current target and filter
stored tenant and parent snapshots; a new owner or sibling grant cannot read
earlier-scope history. History excludes all `legacy_unknown` rows before paging;
any previously captured unknown rows remain immutable and hidden. A matching
latest known analyst revision may remain under its original scope while a fresh
note is appended in a new authorized scope; old content is never copied or
returned to the new scope. Untracked edits fail closed. Visible history contains
only known attributed revisions and does not prove complete legacy provenance.
Unattributed ownership requires a separate, explicitly reviewed reconciliation
process; this slice adds no reconciliation endpoint or permission bypass.
There is no global note-history endpoint and no new form, approval step or UI
integration.

`list_assessment_note_revisions` and `list_evidence_note_revisions` return
immutable, exact-target history pages with `after_id` and `limit` (default 100,
maximum 200). They require the same current analyst permission as the associated
note operation and independently reauthorize every page.

Revision, latest-note compatibility update and AuditLog event commit in the same
transaction. The audit stores immutable-at-issuance issuer, organization,
membership and non-bearer session snapshots alongside existing fields; it never
contains note text. Failed revision/audit writes, late authorization failures or
commit errors roll back all related changes. Denied/nonexistent targets look alike.

## Additive history migration

Following PR #19's guard-only `0014a` revision, the essential additive revision,
`0015_analyst_note_revisions`, adds a
dedicated revision table and nullable audit identity columns for legacy
compatibility. It does not rewrite legacy notes/events, backfill identities, grant
access or change assessment decisions. SQLite/PostgreSQL guards reject revision
UPDATE/DELETE (and PostgreSQL TRUNCATE); normal service operations only append.
Existing data is preserved, and automatic destructive downgrade refuses before
mutation pending an independent retention/rollback plan. Tests apply migrations
only to disposable synthetic databases/schemas, never production.

These guards do not protect against a privileged database owner disabling them,
nor convert legacy audit rows into a cryptographic or external immutable ledger.
Database administration, backups, retention and deployed audit access remain
separate security gates. Exact compilation, full-suite, PostgreSQL concurrency,
migration and final-head Actions results are recorded in PR #21.

## Correction validation record

Compile `app.py` and every touched Python file before the full suites. Exact
SQLite/PostgreSQL counts, final-head CI links and independent-review receipts are
recorded in PR #21. PostgreSQL integration fixtures use temporary owned schemas;
only the disposable container's synthetic schema receives migrations. No
production database is accessed or migrated.

Regressions include final export revocation/reparenting, SQL aggregate counts
beyond list-page limits, CSV/commit failure, concurrent note appends retaining
both rationales, cross-tenant/sibling history suppression, equivalent subjects
from different issuers, late session changes, audit/revision rollback, migration
data preservation and actual database history mutation rejection. New cases
cover unattributed first notes after tenant/sibling moves, hidden unknown rows,
nonvacuous failed-revision rollback, source replacement and raw SQL membership
inserts after final validation for export, notes and history. Complete diff,
security/compatibility and whitespace checks are required; passing tests
authorize no merge.

The current `app.py` still has unrestricted legacy Assessment and Evidence Center selectors, uploads and writes. **These new operations are not registered with those pages**, and real production authentication still fails closed. This milestone does not make the existing pages, UI reporting, governed dispositions, document custody or byte retrieval safe for real customers.

### Remaining production gates

- Do not expose any existing legacy page to a production identity. Migrate Assessment list/detail, status, assignment and governed approval/risk decisions through separately reviewed authorization and audit services before activation.
- Evidence Center needs authorization on upload, download, deletion, preview, extraction/AI entrypoints, source custody and analyst review, not merely the new optional note field. Byte access requires malware scanning, storage confinement, encryption, retention and auditable read controls.
- Independently review PostgreSQL lock ordering, replay/session revalidation, transactional errors, model/permission drift and safe handling of concurrent changes; test against a real isolated ephemeral PostgreSQL service. Synthetic SQLite does not prove PostgreSQL isolation.
- Preserve the evidence-first UX: show sources, policy threshold, uncertainty, analyst-confirmed next action. Do not add an approval form simply because a note API exists.

**Security caveat:** These methods rely on a separately authenticated server-side identity source and dedicated session factory. Their synthetic tests do not establish a live enterprise authentication or multi-tenant production boundary. Neither the methods nor the route registry may be wired to the development demo identity for use with real evidence.
