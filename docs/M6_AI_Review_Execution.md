# M6 AI review execution

This workflow prepares two separate evidence-first AI reviews of the ten synthetic
M6 cases and compares the completed outputs. It is separate from the application,
the M6 provisional scoring reference, the frozen M5C benchmark and the independent
human-review study. No result authorizes a vendor, approves a control, accepts risk
or changes an authoritative decision.

Actual execution on November 16, 2026 completed both reviews using approved
device authentication. See the [live execution report](../benchmarks/executions/m6_live_20261116/EXECUTION_REPORT.md)
for the separate sealed outputs, provenance, all comparison differences and
remaining interpretation limits. The older blocked records and simulation remain
historical artifacts, not substitutes for those actual results.

The separate [third-session AI coordinator workflow](M6_AI_Coordinator_Execution.md)
uses the existing coordinator profile for model-based proposed reconciliation.
It preserves the original A/B outputs and deterministic comparison.

## Roles and input boundary

| Role | Configuration | Initial input | Focus |
| --- | --- | --- | --- |
| Agent A | [Control Assurance Reviewer](../.github/agents/m6-control-assurance.agent.md) | Blind packet, own instructions and response contract | Implementation, thresholds, technical enforcement, operation, scope, freshness and exceptions |
| Agent B | [Evidence Challenge Reviewer](../.github/agents/m6-evidence-challenge.agent.md) | Blind packet, own instructions and response contract | Unsupported conclusions, false-positive findings, source attribution, alternate interpretations and unnecessary questions |
| Coordinator | [AI Review Coordinator](../.github/agents/m6-coordinator.agent.md) | Original packet and both completed, sealed reviews with provenance | Citation verification, comparison, proposed reconciliation and unresolved disagreement |

The custom-agent files use GitHub Copilot's `.github/agents/*.agent.md` convention
and `tools: []`. They describe roles; committing or selecting them does not prove
that independent runs occurred. The reproducible launcher uses fresh Codex CLI
executions instead of assuming Copilot automatically creates isolated contexts.

The source is [M6_Blind_Reviewer_Packet.md](M6_Blind_Reviewer_Packet.md).
The launcher must not obtain reviewer inputs from the JSON with provisional labels,
the scoring module, the pre-adjudication report, prior LMA outputs or another
reviewer's conclusions. Agent A reviews ascending case order; Agent B reviews
descending order. The coordinator becomes eligible only after both outputs exist,
are complete and pass the wrapper's integrity checks.

## Reproduce a run

Use an approved Codex installation and existing environment authentication. Never
paste, copy into a bundle or commit tokens. Only these synthetic inputs are
authorized for this workflow. Use a new output directory for each attempt.

From the repository root:

```bash
python -m py_compile app.py benchmarks/m6_ai_review.py
python benchmarks/m6_ai_review.py prepare --output /tmp/m6-ai-run-001
python benchmarks/m6_ai_review.py run --bundle /tmp/m6-ai-run-001 --agent A --model YOUR_AVAILABLE_MODEL
python benchmarks/m6_ai_review.py run --bundle /tmp/m6-ai-run-001 --agent B --model YOUR_AVAILABLE_MODEL
python benchmarks/m6_ai_review.py coordinate --bundle /tmp/m6-ai-run-001
```

The `run` command also accepts `--codex-home PATH` for an existing approved,
writable Codex home. It must already have approved authentication; the launcher
does not read or copy credentials. Choose a model actually available to the
approved account; record it rather than silently substituting one. Run A and B
as fresh sessions; never use `resume` or
`fork`, a shared conversation, a repository-wide Copilot request, or a prompt
containing the other review. Sequential execution is acceptable when contexts are
separate and B's input is prepared without A's conclusions. Only the coordinator
receives both reviews.

For the authenticated CLI `0.163.0` execution, the advertised model was
`gpt-6.1-sol`; the earlier `gpt-6.1` slug was rejected. A writable home must first
be authenticated through the supported `codex login --device-auth` flow and
verified with `codex login status`. Pass that home with `--codex-home`; never
inspect, transfer or bundle credential files. The live execution used
`--codex-home /workspace/m6-review-login-20261116`.

Strict provider structured output rejects JSON Schema's `uniqueItems` keyword.
The launcher supplies an adapted provider schema without that keyword while
retaining it in the canonical sealed contract and enforcing uniqueness locally.
A duplicate classification still rejects the response; input and canonical
schema hashes are unchanged.

The wrapper uses fresh ephemeral Codex contexts, ignores user configuration,
disables shell/apps/plugins and related data-access capabilities, and supplies a
bounded prompt. Check the actual command and recorded CLI version for the installed
Codex release. Each run records input and configuration hashes, model request,
run/session identifiers, execution status and a sanitized event summary containing
event types and session IDs; raw transport logs and credentials are not retained. The
requested model is recorded as `model_requested`; `model_actual` remains null
when the CLI provides no model attestation. A requested name is not proof of the
provider model that executed. Unsupported flags, unavailable authentication/models, tool use, incomplete output or failed
validation must remain visible failures. Do not hand-write replacement reviews or
mark a failed run completed. Re-run in a new directory after correcting the blocker.

## Integrity and separation claims

Review outputs are separately sealed with content hashes and are not overwritten
by coordination. Retain the run records and original outputs alongside the proposed
reference so subsequent changes are detectable. Hashes and file permissions provide
local tamper evidence, not a trusted timestamp, digital signature, external
write-once storage or protection from the workspace owner. Use controlled artifact
storage for stronger retention requirements.

A clean prompt, a fresh session ID and an observed event summary with no tool
calls support a bounded claim about review context. They do not establish operating-system
confinement, hidden provider state, absence of prior model familiarity, independent
training data or statistically independent errors. If the runtime cannot verify a
boundary, record that limitation. Do not report full isolation merely because the
prompts, names or case order differ. The agent files alone enforce no host boundary.

Reviewers must also self-report `input_boundary` as `clean`, `contaminated` or
`unknown`; only a clean declaration can pass the wrapper. This declaration cannot
verify hidden provider context or replace independent isolation controls.

The reviewers receive only short synthetic evidence statements, not authenticated
vendor documents, logs, inventories or full testing records. Original-source quote
verification proves that cited text occurs in the corresponding case; it does not
prove the interpretation, completeness, operating effectiveness or real-world truth.

## Historical execution blocker

This section describes the initial failed attempts at `f405119`, not the later
completed execution linked above. Approved device authentication resolved HTTP
401; the provider-schema adapter then resolved a separate HTTP 400 blocker.

In this implementation environment, the default Codex home is read-only, so the
CLI could not initialize there. A fresh writable home allowed a fresh thread to
initialize, then the model request failed with HTTP 401 because bearer
authentication was unavailable. No completed Agent A or Agent B review resulted.
Shared-history implementation agents are not substitutes for blind reviewers.

To perform live reviews, an operator must provision approved authentication in a
writable Codex home through the established environment mechanism and run both
commands in fresh contexts. Do not inspect or copy existing credential files,
commit tokens, or fabricate reviews to bypass this blocker. Until both runs
complete and their outputs pass verification, AI adjudication remains unexecuted.
Synthetic examples exercise the workflow as simulations, not completed model runs.

The actual failed launch records are preserved separately in
[`m6_blocked_attempt_v1`](../benchmarks/examples/m6_blocked_attempt_v1/), with
distinct run and session IDs, requested model, null serving-model attestation,
input/configuration hashes and blocked status. No review payload was produced.
Runtime-default reasoning and sampling settings are not attested by the CLI.

## Proposed reference and disagreement

The `coordinate` command performs deterministic, conservative comparison after
both successful sealed reviews are available. The separate
[`m6_ai_coordinator.py` workflow](M6_AI_Coordinator_Execution.md) executes the
coordinator profile for model-based proposed reconciliation. Its actual execution
records, rather than this configuration or the deterministic comparison, establish
whether a third model session completed.

Coordination compares both submitted assessments against the original case sources,
separates technical exceptions from evidence insufficiency, and retains differences
in classification, interpretation and next action. Unnecessary-question assessments
are proposals with rationale, not measured vendor effort reductions. A coordinator
must preserve uncertain differences instead of averaging labels or overwriting either
review. The result is a new proposed AI-only reference; the original M6 labels and
M5C benchmark remain unchanged.

Distinguish deterministic wrapper checks/comparison from any actual model-based
reconciliation. A configured coordinator is not evidence of a coordinator model
execution. Report which occurred. No AI-only reference satisfies the independent
qualified-human adjudication requirements in
[M6_Adjudication_Worksheet.md](M6_Adjudication_Worksheet.md), and it must not be used
to claim trusted material-risk recall, field accuracy, time savings or human assurance.

## Hand-constructed example

[The workflow simulation](../benchmarks/examples/m6_ai_review_simulation.json)
contains two manually constructed ten-case review fixtures and a concise
`comparison_summary` derived from `compare_reviews`. Recompute the full comparison
from `reviews.A` and `reviews.B` rather than duplicating the review bodies. It includes exact source quotations,
three declared technical exceptions, explicit evidence gaps, and a preserved
case M6-04 disagreement about the smallest next action. `input_boundary` values
illustrate the response contract; they are not declarations from actual reviewers.
The artifact explicitly records `actual_model_execution: false` and
`human_validated: false`. It is not a completed blind review, proposed reference
dataset, semantic AI adjudication or performance measurement. No run IDs,
completed execution statuses or model identities are fabricated.

## Validation and release record

Before pytest, compile `app.py` and all affected Python modules and tests. Run the
complete suite with `DATABASE_URL=sqlite:///:memory:` and the complete PostgreSQL
suite against an isolated synthetic test database. Verify the full diff, run
`git diff --check`, and inspect GitHub Actions for the exact PR head. Tests mock
model execution; synthetic examples are fixtures unless their provenance explicitly
records an actual successful model run.

The validation report must identify the tested commit, exact commands, suite counts,
failures/skips, source and configuration versions, actual execution results and
remaining isolation limitations. Keep these distinctions explicit:

| Claim | Evidence required |
| --- | --- |
| Agent configuration exists | Reviewed configuration files |
| Agent A/B actually executed | Separate completed run records and sealed outputs |
| Automated comparison ran | Coordinator output with verified input hashes |
| AI model adjudication ran | Actual coordinator-model execution record, when used |
| Independent human assurance | Qualified human reviews and explicit adjudication record |

Open a draft pull request only. Do not merge PR #38, PR #39 or the new PR; do not
push to protected `main` or change authoritative risk decisions.
