# M5D release-candidate revalidation

Owner review record, 2026-11-10 (America/Chicago). Synthetic evidence only.
No release, merge, production security approval or field-accuracy claim follows
from this record.

## Candidate and scope

- Latest inspected `main`: `3509245e3e454d5028f450df86ac2b38682a25c8`, including merged PR #35.
- Inspected draft PR #34: `27992caa294182caf9c01ae2f18223d5139ec0e8`.
- Dedicated branch: `feature/m5d-rc-revalidation`; integration commit `66b484ae4399e13cdee51f55395de6ea52dd0c9b`.
- Read `AGENTS.md`, `README.md` and the end-to-end workflow before validation.
- Clean integration preserves PR #35's captured organization policy, threshold,
  freshness and accepted-evidence-kind handling. No additional extraction fix was
  justified. Added 15 synthetic compatibility regressions and this report.
- `main` and PR #34 were not modified. No PR was merged. No database schema,
  authentication, protected security boundary or benchmark annotation was changed.

## Compatibility and verification

The new regressions exercise M5D port recognition and compound RTO/RPO against
strict/lenient captured thresholds, organization freshness and accepted-kind
gates, and excluded recovery dependencies. They also verify that a later policy
version cannot rewrite a completed package: original evidence bytes/hashes,
captured policy/hash, unconfirmed facts and an open analyst finding remain intact;
residual risk stays unset and vendor approval false.

`app.py`, `src/upload_evaluation.py` and all affected/new Python test modules were
compiled before pytest. Full SQLite uses `DATABASE_URL=sqlite:///:memory:`.
PostgreSQL validation uses a disposable local PostgreSQL 16 database with synthetic
fixtures only, including Alembic upgrade, CI schema verification and the full suite
with `GITHUB_ACTIONS=true` to exercise PostgreSQL-specific CI paths.

| Check | Local result |
| --- | --- |
| Compile before pytest | Pass |
| New methodology compatibility regressions | 15 passed |
| Full SQLite suite | 2,058 passed; 65 PostgreSQL-only skipped; six Alembic deprecation warnings |
| Full PostgreSQL 16 suite, migrations and schema | 2,123 passed; no skips; 12 Alembic deprecation warnings; migration head `0014a_membership_identity_guard` |
| Frozen M5C benchmark | Pass on provenance/confirmation invariants; descriptive quality below |
| Complete diff and independent review | No actionable P1/P2 found; `git diff --check` clean |

## Frozen benchmark

Reproduced M5C-holdout-1.1 at frozen `as_of=2026-11-01`: 16 cases across TXT,
PDF and DOCX, eight TLS and eight DR. Results equal the prior M5D RC:

| Metric | Revalidated result |
| --- | ---: |
| Material exception cases surfaced | 7/8 (87.5%) |
| Annotated typed facts matched | 25/29 (86.21% recall) |
| Precision against annotations | 25/26 (96.15%); one extra |
| False adverse alarms, two non-exception cases | 0 |
| Adverse overclaims, six abstention cases | 0 |

Frozen corpus blob remains `8caa0d5031ff2b83bd71aa9ec9e89eeb8ffe0c8f`;
scorer blob remains `98572ab4a3c7ab0664cf09e35470b5fada294abf`.
No gold labels or scoring logic were altered. These are small authored synthetic
measurements, not external field precision, comprehensive assurance or measured ROI.

## Remaining risks and decision

1. **DR narrative miss remains.** `dr-failover-narrative` describes switching
   duration and an upper bound on data loss without numeric RTO/RPO syntax. The
   bounded parser does not extract those two metrics. Treating them as exact
   achieved recovery values requires independently reviewed semantic coverage;
   retain analyst review and the measured miss.
2. **TLS subject mismatch remains.** The adverse exception in
   `tls-gateway-caption` is surfaced, with source-faithful subject `legacy gateway
   port 9443`; frozen gold expects `gateway port 9443`. Removing descriptors to
   improve a score could collapse asset/scope distinctions. Preserve both parser
   and frozen annotation; this is one unmatched gold and one extra typed fact.
3. The fourth unmatched fact is the year-qualified DR metric; its current meaning
   remains unestablished. Exact source quotation is not semantic confirmation.
4. No human TPRM walkthrough, measured analyst effort, real vendor validation or
   production identity/custody readiness is established. Organization methodology
   remains the session-only pilot described in PR #35.

Historical CI is green for PR #34's exact head in run
[41772715697](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/41772715697)
(Unit and PostgreSQL), and PR #35's source head in run
[42547267746](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/42547267746).
Historical runs do not establish CI for this combined candidate. Check the draft
revalidation PR's exact-head Unit/PostgreSQL jobs and frozen benchmark artifact.

**Recommendation: defer release/merge pending exact-head CI and owner quality
approval.** Engineering review found no compatibility blocker or unsupported
control approval, fabricated citation, authoritative risk mutation or protected
boundary change. After CI, the owner must explicitly accept the documented recall
limits and complete the synthetic human quality checklist in
`M5D_Release_Candidate_Acceptance.md`. Keep the candidate draft and unmerged until
that approval; broader narrative extraction belongs in a separate reviewed slice.
