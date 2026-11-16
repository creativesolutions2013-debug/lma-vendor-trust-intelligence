# M6 AI coordinator execution

This standalone synthetic workflow executes the existing
[AI Review Coordinator](../.github/agents/m6-coordinator.agent.md) as a third,
fresh Codex session after the two original blind reviewers have completed. It
does not replace the deterministic `m6_ai_review.py coordinate` command or
overwrite its comparison. Model-based reconciliation, structural validation and
qualified-human adjudication are separate activities.

The starting point is PR #40 head
`7fd7a2406976c1b526b59c16226f892c0644210a` and its
[completed A/B execution](../benchmarks/executions/m6_live_20261116/EXECUTION_REPORT.md).
The original packet, reviews, run records, provisional labels, scorer and frozen
M5C benchmark must remain unchanged.

## Inputs and provenance

Before execution, verify the source bundle's seals, exact blind packet, reviewer
configurations, complete own-case quotations, clean context records, completed
statuses, matching response-versus-record bodies and distinct run/session IDs.
Snapshot the original artifacts and verify them again after the coordinator runs.

The coordinator receives only its existing instructions, the output contract,
the original synthetic packet, both unchanged reviewer reports and their
provenance. Case hashes, original field differences and question identifiers
are derived from those reports. These are provenance aids, not suggested answers.
Do not supply the deterministic proposal, provisional gold labels, scorer,
simulations, helper audits, execution-report conclusions or unrelated repository
context. Do not use `resume`, `fork` or a shared implementation conversation.

Use an approved Codex home that is already authenticated. The operator's approved
device-authenticated home is `/workspace/m6-review-login-20261116`;
`codex login status` verifies it without exposing credential contents. Never
inspect, copy or commit credential files. Explicitly select an advertised model;
the completed A/B runs requested `gpt-6.1-sol`. A requested name is not a verified
serving-model identity.

## Reproduction

From the repository root, use a new output directory for each attempt:

```bash
python -m py_compile app.py benchmarks/m6_ai_review.py benchmarks/m6_ai_coordinator.py
python benchmarks/m6_ai_coordinator.py prepare --source-bundle benchmarks/executions/m6_live_20261116 --output /tmp/m6-coordinator-001
python benchmarks/m6_ai_coordinator.py run --bundle /tmp/m6-coordinator-001 --model gpt-6.1-sol --codex-home /workspace/m6-review-login-20261116 --timeout 600
```

Unsupported authentication, model, CLI or output schema must remain recorded
failures. Never hand-write a replacement for an actual failed coordinator result.
Regression fixtures exercise contracts with mocked model calls; they are not
adjudicated references or completed AI executions.

## Proposed reference and validation limits

The new versioned reference is **AI-only and provisional**. It preserves both
original reviews and every original disagreement, records proposed assessments
against exact customer requirements, and retains source quotations, uncertainty,
reconciliation rationales and the smallest proposed next action. A coordinator
may challenge an originally shared judgment, but that change also needs an
explicit reconciliation basis. Choosing a reviewer field means preserving its
literal value; rewritten conclusions are synthesis, not unchanged reviewer text.

Every vendor-question candidate must be examined, including candidates listed
as unnecessary. Prefer an authorized internal evidence check when justified;
unknown internal holdings cannot be treated as existing or sufficient evidence.
Missing, stale, incorrectly scoped or incomplete operating proof must not alone
become a demonstrated technical exception.

Strict structural checks require ten complete cases, exact customer requirements,
own-case quotations, original judgment hashes, complete disagreement/question
coverage and consistent reconciliations. Governance flags must remain false;
extra approval, risk or decision fields are rejected. Structural checks cannot
prove citation interpretation, question necessity or real-world control truth.

Fresh ephemeral contexts, bounded supplied inputs, ignored user/project context,
disabled access features and no-tool event audits support limited context
separation. They do not establish host/provider confinement, hidden-state absence,
statistical independence or diverse model errors. Local seals are tamper evidence,
not signed external retention. Record unknown serving-model identity as null.

No output approves a control/vendor, accepts risk, changes production decisions
or mutates authoritative risk records. Human adjudication is still required
before assurance, field-accuracy, time-saving or vendor-question-reduction claims.

## Regression and release checks

Compile before pytest, then run full SQLite and isolated PostgreSQL suites:

```bash
python -m py_compile app.py src/upload_evaluation.py benchmarks/m6_analyst_quality.py benchmarks/m6_ai_review.py benchmarks/m6_ai_coordinator.py tests/test_m6_analyst_quality.py tests/test_m6_ai_review.py tests/test_m6_ai_coordinator.py
DATABASE_URL=sqlite:///:memory: python -m pytest -q
```

Use only a disposable synthetic PostgreSQL database for migrations, expected-table
verification and the complete PostgreSQL suite. Verify source hashes after tests,
the complete diff, `git diff --check`, preserved original artifacts and required
GitHub Actions on the final candidate head. Keep the new PR draft and stacked
on PR #40; do not modify main, PR #38, PR #39 or any original reviewer outputs,
and do not merge anything.
