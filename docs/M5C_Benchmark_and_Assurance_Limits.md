# M5C baseline: evidence accuracy before parser expansion

**Status:** implementation on `feature/m5c-blind-evidence-benchmark`; **not merged**.
Product decision: **build the benchmark; defer new extractor rules** until we inspect measured misses and unsafe false alarms. This is not a claim of industry-grade accuracy.

## Corpus and scoring

The versioned `benchmarks/m5c_holdout_v1.json` contains **16 separately written synthetic cases** covering TLS and DR, across TXT, PDF and DOCX. **Version 1.0's first-run metrics are superseded by 1.1** after independent review identified a gold-label defect: an achieved 4-hour-30-minute RTO is a material exception to the 240-minute objective, regardless of parser support. The correction was made before accepting baseline findings. Gold annotations are now frozen at **M5C-holdout-1.1**; rule authors must not tune or rewrite these cases to improve scores. This initial set was written with knowledge of existing platform behavior and does **not** qualify as an external blind, representative real-world study. A later external analyst-authored corpus is still necessary.

A frozen `as_of=2026-11-01` keeps freshness checks reproducible. Synthetic DOCX examples are generated as complete minimal WordprocessingML packages with one paragraph per source line; PDF examples are readable simple text pages, not scans. Cases deliberately include healthy and weak listeners, weak secondary endpoints, disabled legacy versions, conditional/test-only/stale evidence, policy targets, recovery-objective overruns, incomplete dependency coverage, unsupported narrative synonyms, compound durations, historical exercises and out-of-scope services.

Run:

```bash
python -m py_compile app.py tests/test_m5c_benchmark.py
python -m pytest -s -q tests/test_m5c_benchmark.py
```

The standard GitHub Actions Unit job also runs the holdout separately and uploads a `m5c-baseline.json` artifact. Full SQLite and PostgreSQL suites remain required.

**Two separate measurement layers:**

- **Typed fact extraction:** human-annotated dimension/value/service subject/quote phrase versus all proposed typed facts; report matched facts, unmatched gold, extra typed facts, precision against annotations and recall. This measures *text candidate coverage*, not truth of real vendor statements.
- **Provisional material-exception triage:** case-level current eligible adverse candidates versus seven human-labelled material concerns; report missed cases. Two non-exception cases and seven intentional-abstain cases are scored for unsafe eligible adverse overclaims. A safe abstention is not an automatic control failure, and a text-only extracted warning with bad scope/date does not qualify as a current exception.

**Safety gate (always hard-fail):** facts must carry exact original document identity, source fingerprint, in-document location and verifiable quote; no automatic `Met`/authoritative `Risk Identified` in the control worklist; no confirmed technical facts. The accuracy score intentionally does **not** fail CI; otherwise developers could tune the rules to this small set rather than confronting defects. Negative findings are visible in the downloadable JSON.

The report contains per-case missed typed facts, unexpected typed facts, eligibility/outcome, context uncertainties and cited limitations. No claim of true external blind accuracy, general SOC 2/document understanding, comprehensive technical scope, customer-approved policies or verified vendor evidence is made.

## Analyst friction remains unmeasured

The automated harness **cannot** estimate minutes saved, user clicks, vendor-question reduction or analyst preference. Its JSON explicitly records these as `null`. The next acceptance exercise should be a short observed analyst walkthrough (or browser-operated agent test with recorded interactions) measuring whether decisive quotes, requirement, example threshold and the smallest follow-up can be found without typing dates or generating findings for evidence-only gaps. Avoid adding another analyst configuration dashboard.

## Prioritization gate

After the first CI artifact, review:
1. Any **false current adverse** comparison: immediate blocker to commercial assurance claims.
2. **Missed material exceptions**: determine whether narrow extraction, explicit abstention or targeted human review is the correct behavior.
3. **Exact provenance failures**: never acceptable.
4. **Analyst effort**: adjust defaults/labels only if observed behavior warrants it.

Approve a **small quality correction**, not a new control family or generic regex expansion, after independently reviewing the measured baseline. Keep PR #21 and production auth/evidence custody out of scope.
