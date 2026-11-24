# M7 Phase 3: authorized evidence-linkage preflight

## Baseline, defect and decision (before coding)

Implements the fallback in [Issue #55](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/55).
Protected main is `348e35133ec2c61b73b3daad216dbb00541752e6` after #54;
[post-merge CI 45294444136](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/45294444136)
passed Unit tests and PostgreSQL compatibility. Work starts in a fresh worktree
on `feature/m7-evidence-custody-preflight`. Existing checkouts are preserved.
Read the full issue, AGENTS, README, official E2E workflow, both M7 documents,
M4B/M4C security documents and #54's design. All 16 open PRs remain drafts at
the heads recorded in the M7 audit. Actual #21 file overlap is notes, exports,
DB retention/migrations and route policy, not evidence bytes or this preflight.
No existing PR is merged, copied, rebased or overwritten.

The exact defect is a check/use gap: the older evidence-read preflight issues
short-lived metadata, without holding the newer server-session lease and SQL
authority through completion. Using that metadata for a later storage call
would turn consistency data into authority. Vendor-prefixed keys also permit
two evidence rows, including ungranted siblings, to reference one object.

An independent feasibility assessment agrees that bytes would require a new
custody contract. `LocalEvidenceStorage` has no bounded, integrity-checked read;
save overwrites. Legacy upload stores the absolute local path or S3 URI returned
by save in `Evidence.storage_path`. The schema has no immutable object generation,
key ownership/incarnation, uniqueness or atomic DB/object-store lifecycle. An
actual IdP alone would not repair those gaps; synthetic byte operations still
need reviewed linkage and failure semantics. Do not normalize/relink historical
rows or change legacy save return values silently.

## Intended correction and acceptance

Implement only an unwired, read-only **synthetic linkage preflight**, with the
existing `EvidenceReadRequest` selectors and a boolean result. A successful
result is diagnostic at a defined point in time, never a byte-access capability.
No storage dependency, key, path, hidden IDs, hash, existence result or token is
returned. Every denial is exactly `False`.

- Extract #54's session-leased SQL read orchestration into one private shared
  base; preserve the snapshot contract and regression coverage. Reuse
  `SessionIdentitySource`, `SessionManager`, `TenantReadService`, membership
  predicate guard, effective `evidence.read` permission and exact linked SQL
  parents. Missing/fake identity dependencies deny; request DTOs select candidates
  and never supply authority.
- Acquire SQL authority before the session lease; complete SQL inside it. Pin
  service/source/factory/handle/store/clocks/limits before authentication and
  through completion. Recheck current authorization, target binding, dependencies
  and cached deadlines at the same defined points as #54. Failed/dirty transactions
  and failed cleanup discard the result.
- Within the locked transaction, require exact positive integer request IDs,
  authorized organization/engagement/vendor/assessment/evidence joins and a
  canonical vendor-bound key using the existing pure validator. Legacy absolute
  paths, S3 URIs and mismatches deny without reading storage or changing rows.
- Query exact key references across all evidence rows, including hidden scopes;
  require the target to be the only reference. Repeat the probe in final
  validation. Any observed alias or change denies. Do not disclose where another
  reference exists. Leave hidden rows unlocked: locking aliases after tenant
  parents risks cross-scope lock-order conflicts and cannot prevent new aliases.
- Prove success through locally signed synthetic OIDC code flow and fresh
  sessions. Cover revocation/expiry/ambiguity, permission/grant/relationship/key
  failures, dependency substitution, atomic denial, no storage I/O, and actual
  PostgreSQL serialization using disposable Actions service schemas.
- Compile app.py and every touched Python file before focused/full pytest;
  run full SQLite and PostgreSQL Actions with existing migrations/schema checks,
  inspect the complete diff and obtain independent exact-head security review.
  Open a draft PR only; leave main and all existing drafts unchanged.

Intended files: new private shared leased-read helper, snapshot orchestration
refactor, new evidence preflight, focused synthetic regressions, CI compile/focused
steps and this document. No models/migrations, storage implementation, app routes,
auth startup, evidence evaluators or governed-risk changes.

## Exact limits and blocked work

SQL row locks protect existing authorized relationships and the target's key
through SQL completion. PostgreSQL's membership predicate guard also
serializes same-identity membership inserts; SQLite reserves its writer. There
is no storage-key predicate lock or unique constraint: a new alias visible in a
final query denies, but a concurrent insert after that query can go unobserved.
This preflight does not reserve a key or authorize subsequent I/O. SQL revocation
after transaction completion and session revocation after lease release cannot
retract a returned boolean. Cached deadline checks reject expiry during commit
and session cleanup; they do not provide atomic delivery or instant cancellation.

Canonical syntax and a unique current SQL reference do not prove historical
ownership, original-byte integrity, trustworthy ingestion or physical storage
confinement. The helper never calls storage, including exists. Existing whole-scope
authorization scans remain; alias lookup may scan the evidence table. Bounded
result cardinality and SQL timeouts do not establish production query-cost bounds.
Timeouts, lock-order conflicts and provider/SQL failures deny uniformly.

Still blocked: immutable object/source linkage and versions, bounded integrity-
checked byte retrieval, atomic writes/failure cleanup, durable custody/audit,
malware quarantine, encryption/key management, retention/deletion/backups,
deployed IdP/browser/durable sessions, secure vendor submission, multi-user
save/resume and final governed decisions. No real vendor evidence, live provider,
external AI, customer-route wiring, production login or access is enabled.
Production remains fail closed. No complete E2E, professional validation or
production custody is claimed. Human TPRM professional review remains deferred
until E2E completion; independent engineering/security review is still required.
