# Preserve unchanged requirement reviews during evidence follow-up

## Verified baseline and defect (before implementation)

Protected main is `53e584454ec04e0b2600ef0a61b02d807290f705`.
[Main CI 44847581432](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/44847581432)
passed Unit tests and PostgreSQL compatibility. Work is isolated on
`fix/assessment-completion-correctness`, based on that commit.

Synthetic reproduction: evaluate a TLS configuration routed to ENC-01, record a
draft TLS finding, then evaluate an additional recovery exercise routed only to
BCP-01. The ENC-01 row and its source-bundle fingerprint remain identical, but its
annotation becomes **Stale context** and the identical TLS finding can be recorded
again. The default captured organization methodology reproduces this too.

Cause: `row_fingerprint` includes the entire `customer_context`, including all
requirements' `evaluations` and legacy `screening` entries. Unrelated evidence
therefore invalidates source-bound reviews, contrary to the function's documented
requirement-specific contract. This creates unnecessary analyst work and duplicate
findings; it is not evidence that a control failed.

## Proposed correction

When hashing a requirement's annotation context, include only that requirement's
evaluation and screening entries. Keep all shared relationship/intake,
organization methodology, version, policy, threshold, source-bundle, need and
uncertainty context. Do not alter evaluation, citations or human confirmation.
Keep the full-assessment completion fingerprint: any changed evidence still
requires finishing a new report snapshot.

## Acceptance criteria

- Adding/changing evidence for BCP-01 preserves the unchanged ENC-01 annotation,
  original citations and same-context finding deduplication (and vice versa).
- A changed requirement's own evidence, metadata, routing or threshold still
  invalidates its annotation. Relationship and methodology changes remain bound.
- Any changed assessment invalidates its prior completion, even when one
  requirement's annotation remains current; historical findings stay open.
- Both the captured-methodology customer path and legacy upload adapter are
  covered with synthetic regressions, including the actual Streamlit journey.
- Outcomes remain provisional, missing evidence remains distinct from failure,
  facts remain unconfirmed, residual score stays null and vendor approval false.
- Compile `app.py` and changed Python files before focused/full pytest; full
  SQLite and PostgreSQL CI, complete diff review and independent review of the
  final commit must pass. Keep the PR draft and require owner approval to merge.

## Intended affected files

- `src/guided_assessment_demo.py`: requirement-specific annotation fingerprint.
- `tests/test_upload_assessment.py`: synthetic isolation/invalidation regressions.
- `tests/test_e2e_analyst_pilot.py`: preserve TLS finding across DR-only follow-up.
- `.github/workflows/tests.yml`: compile touched modules before both CI suites.
- This document: defect, acceptance and validation/assurance record.

## Existing work checked and preserved

All 17 open PRs were inspected; all were drafts with successful Unit/PostgreSQL
checks at inspection. #21 covers scoped persisted operations; #29–#34 the frozen
M5C/TLS/DR work; #37–#38 narrative recovery review; #45/#47 the upload-retention
and intake changes already integrated by #48. Their branches remain untouched.
In particular #29 also contains upload-metadata/navigation corrections, which
this change does not repeat.

Current M6 materials were read from their existing branches: #39's blind packet,
worksheet/protocol and pre-adjudication warning; #40/#41's AI execution and
coordinator limits; #42's interpretation overlay; #43's retention gate; and #49's
pilot readiness gate. Their inspected heads are respectively `91bfab3`,
`7fd7a24`, `dd10961`, `1b377f2`, `077ecb8`, and `cf660aa`.
No benchmark, provisional label, sealed execution or pilot-study material is
copied or changed. AI agreement and quotation integrity do not establish human
adjudication, assurance accuracy or measured effort savings.

## Assurance boundary

Synthetic session-only draft annotations are not authenticated human control
confirmations. This correction grants no approval, changes no authoritative risk,
and supplies no production evidence custody or independent human quality study.
No live AI, confidential evidence, secrets, external integration, database,
authentication, migration or new form/dashboard is in scope.
