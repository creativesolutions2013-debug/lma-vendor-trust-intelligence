# M6 AI review validation — 2026-11-16

The initial implementation validation at `f405119` is retained below as a
historical record. A subsequent execution completed two actual AI reviews and
deterministic coordinator comparison; see the [live execution report](../benchmarks/executions/m6_live_20261116/EXECUTION_REPORT.md).
Semantic model adjudication and independent qualified-human assurance remain
unexecuted. The separate hand-constructed simulation is not an actual review.

## Live execution follow-up

Approved Codex device authentication in the existing writable home resolved the
initial HTTP 401. The earlier `gpt-6.1` model name was rejected; both completed
runs explicitly requested advertised `gpt-6.1-sol` with CLI `0.163.0`.
Actual serving-model identity remains unverified/null. A second HTTP 400 exposed
the provider's rejection of `uniqueItems`; executed commit
`31657b2a9615511ef54ad1c910b1059f3c43e84a` adapts only the provider schema and
preserves canonical/local uniqueness validation. Compilation and all **52**
mocked workflow regressions passed before the completed runs.

Fresh complete suites on that unchanged Python source passed: **2,129 SQLite
tests / 65 PostgreSQL-only skips**, and **2,194 PostgreSQL tests / no skips**.
PostgreSQL migrations/schema checks and full diff/whitespace review passed.
The six tested source hashes remained unchanged. Existing Alembic warnings
remain (6 SQLite / 12 PostgreSQL). No real AI calls occurred in the regression
tests; the isolated disposable PostgreSQL container was removed. Exact commands,
hashes and separate logs are in the [local validation record](../benchmarks/executions/m6_live_20261116/validation/summary.json).

Both actual responses passed ten-case completeness and source checks (28 exact
own-case citations), distinct-session/no-tool audits, and sealed response/record
integrity checks before and after coordination. Classification sets agree on 7/10;
weakness flags and evidence sufficiency on 10/10; action kinds on 5/10. All ten
retain full-response differences. The linked report lists every agreement and
difference and preserves both original outputs, hashes and run identifiers.
No approval, authoritative risk change, time-saving measurement or human
validation is claimed. Full-suite and hosted CI evidence for the final PR head
is reported in PR #40 Checks and the final execution report returned to the
operator; the older counts below describe the initial implementation only.

## Historical implementation validation

## Scope and provenance

Feature branch `feature/m6-independent-ai-review` is based on PR #39 head
`91bfab325dd848cc61c38be02df1ca4919ed7d86`; the draft PR targets its branch
`feature/m6-analyst-quality-baseline` to keep this change separate. Latest `main`
was inspected at `fff3903660cdd162108047f82110ef8283b2d56e`. Neither branch was
changed. PR #38 and PR #39 remain unmerged.

Input: M6 blind reviewer packet v1; raw packet SHA256
`3cf63d64a0cf0d7de5c36186588f2e93745fcb792052edc9c2c6d9d41e15698b`.
The [attempt manifest](../benchmarks/examples/m6_blocked_attempt_v1/manifest.json)
records canonical input, response schema and both instruction digests.

## What ran

| Check | Observed result |
| --- | --- |
| Python 3.12.14 compile before pytest | All six affected/application modules below passed |
| Complete SQLite suite | **2,127 passed, 65 PostgreSQL-only skipped**, 6 existing Alembic deprecation warnings |
| Complete PostgreSQL suite | **2,192 passed, no skips**, 12 existing Alembic deprecation warnings |
| New workflow tests | **50 passed**, all CLI/model responses mocked |
| Isolated PostgreSQL 16.16 | Alembic upgrade and expected schema verification passed |
| Synthetic example validation | Both ten-case fixtures passed schema/source checks; M6-04 action disagreement preserved |
| Live launcher A / B | Separate fresh session IDs; both **blocked by authentication_unavailable (HTTP 401)** |
| Coordination of actual attempts | Rejected both blocked runs; no proposed reference written |
| Whitespace, complete change review, frozen-file comparison | Passed; original M6 labels/scorer/packet/worksheet and M5C benchmark unchanged |

Commands (using the isolated test virtualenv):

```bash
python -m py_compile app.py src/upload_evaluation.py benchmarks/m6_analyst_quality.py benchmarks/m6_ai_review.py tests/test_m6_analyst_quality.py tests/test_m6_ai_review.py
DATABASE_URL=sqlite:///:memory: python -m pytest -q
# Isolated disposable PostgreSQL only; never point these tests at customer data.
DATABASE_URL=postgresql+psycopg://lma:lma_test_password@127.0.0.1:55432/vendor_trust python -m alembic upgrade head
GITHUB_ACTIONS=true DATABASE_URL=postgresql+psycopg://lma:lma_test_password@127.0.0.1:55432/vendor_trust python -m pytest -q
git diff --check
git diff --cached --check
```

`GITHUB_ACTIONS=true` activates existing PostgreSQL regression fixtures locally;
this is not a claim that the local run was hosted by GitHub. No real model calls
occurred in pytest. Hosted Actions for the resulting commit are recorded in the
draft PR Checks and PR validation notes after publication. CI now compiles both
M6 modules/tests before each full suite and triggers for this stacked PR base.

Tested implementation SHA256:

- `benchmarks/m6_ai_review.py`: `540c384b44622a19221c41efde0a1cc3a0adfe2beba4ea6b08b30518fd20278b`
- `tests/test_m6_ai_review.py`: `690d90ec88601cb8252e1f6cfb18362a2d06646f8527f16a6a47804ddbfb2f89`

Tests cover role-specific blind input, shared session rejection, tool/unknown-event
rejection, contamination/unknown context, malformed responses, missing evidence,
source attribution, artifact tampering, input drift, retained disagreements,
authentication failures, timeouts and exclusion of automatic approval fields.

## Execution and assurance limits

Codex CLI `0.167.0-alpha.4` could not initialize in its default read-only home.
Fresh writable homes started sessions but had no usable bearer authentication.
Actual [A](../benchmarks/examples/m6_blocked_attempt_v1/A/record.json) and
[B](../benchmarks/examples/m6_blocked_attempt_v1/B/record.json) failure records
are separately hashed. Requested model: `gpt-6.1`; serving model: **unverified/null**.
No model response was accepted. Raw transport logs, tokens and confidential evidence
were not committed. Approved authentication must be provisioned through the existing
environment mechanism before rerunning the [execution instructions](M6_AI_Review_Execution.md).

The [hand-constructed simulation](../benchmarks/examples/m6_ai_review_simulation.json)
is contract/example data, not two independent reviews or gold labels. Deterministic
comparison and citation substring checks were exercised on constructed responses;
model-based semantic adjudication remains configured only. No actual AI-adjudicated
reference dataset was produced, and no observation supports accuracy or efficiency
claims. The original human adjudication protocol remains unsatisfied.

Fresh contexts, bounded prompts, model self-declaration and no-tool event audits
support limited context separation. Host filesystem confinement, hidden provider
state, serving-model identity and statistical independence remain unverified.
Hashes and read-only files provide local tamper evidence, not signed write-once
storage. These limitations are recorded rather than treated as independent assurance.
No application approvals, authoritative risk decisions, database/authentication
implementation or production evaluators were changed.
