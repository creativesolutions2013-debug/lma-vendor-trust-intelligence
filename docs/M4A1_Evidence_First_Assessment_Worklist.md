# M4A-1 — Evidence-First Assessment Worklist

**Status: implementation handoff only.** This document does not claim M4A code exists. The source of truth for this slice's acceptance criteria is [GitHub Issue #7](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/7). M3D remains the merged, synthetic evidence-to-control assurance foundation.

## Product objective

**Assess the evidence before you ask the questions.**

Turn the existing assessment applicability/work planning, M3D evidence-backed control-review outputs, and targeted evidence gaps into **one concise, source-verifiable assessment worklist**. Show each applicable requirement, customer threshold, evidence and exceptions, uncertainty, and exactly one next action. Minimize unnecessary vendor requests; analysts remain accountable for decisions.

## Reuse existing components

| Existing component | Reuse for | Boundary |
| --- | --- | --- |
| `src/assessment_orchestrator.py` | Applicability, existing evidence work plan, question candidates | Its `SUPPORTED` means evidence support under that subsystem, **not** technical `Met` |
| `src/control_assurance.py`, source validation and registered reviewers | Customer requirement/threshold, verified source and provisional control assessment | M3D outputs remain **provisional and review-required**, even when labeled `Met` |
| `src/targeted_gap.py` and existing question patterns | Missing evidence / possible targeted follow-ups | Never produce a generic questionnaire when a precise, grounded fact request suffices |
| Existing Assessment Workspace in `app.py` | One small read-only review surface | No new dashboard, forms, stored approvals, messages to vendors or real evidence upload |

Do **not** build a second assessment engine or silently join by similar control names, evidence filenames, control-family labels or broad document-type mappings. Historical requirement IDs can have different meanings (e.g., `IAM-01`, `PAM-01`, `PAM-01.MFA`, `ENC-01`, `ENC-02.TLS`); explicit matching is required.

## Small worklist contract

For each **applicable** requirement:
- Exact engagement/service, environment and customer-approved requirement ID/policy version/threshold and scope; assessment date.
- Original orchestrator evidence state **separate** from M3D provisional technical result; specialist evaluator coverage disclosed, never inferred.
- Actual supporting/contrary source location and quote (or an explicit absence of usable source), provenance, freshness and evidence kind. Do not invent citations.
- Top exception, contradiction, scope mismatch or operating-proof gap. An apparent source quotation is not a verified interpretation.
- A single prioritized workflow intent: **Review exception**, **Validate evidence**, **Request a specific missing fact/evidence**, or **Reuse evidence — governance review still required**.
- Draft vendor follow-up containing only the minimum unanswered question, clearly labeled **not sent**.
- All actions read-only proposals, not confirmation, authorization, risk-score writes, approved control results, or outbound messages.

## Synthetic pilot cases

Use one realistic assessment with >=4 distinct applicable requirements including:
1. Sufficient, source-reviewed technical evidence under a customer-specific threshold; avoid an unnecessary new vendor question, but retain authorized analyst governance.
2. An active, source-confirmed technical exception alongside otherwise positive evidence; **exception first**, not concealed by strong support.
3. A specific missing or stale operating result: ask only for the missing scoped record, without declaring a failed control.
4. A relevant customer-defined control **without** a specialist evaluator: keep it on the worklist with cited evidence or a gap and explicit specialist review.

Exercise an explicit ID/scope mapping conflict, missing citations, and evidence newly supplied for one gap. When the gap closes, only its source-grounded work item/question should change; preserve existing exceptions. Show the number of targeted vendor requests against a defined ask-everything baseline; this does **not** measure real cycle-time savings.

## Execution and security gates

- Work on `feature/m4a-evidence-first-worklist` and continue the existing **draft** PR associated with Issue #7. Do not open a duplicate PR or push to `main`.
- Read repository `AGENTS.md`, `README.md`, the end-to-end workflow blueprint and Issue #7. Inspect actual interfaces; do not infer from this brief.
- Keep adapter pure and narrow. Prefer a small read-only preview in the existing assessment screen, only if it does not disrupt existing flows.
- No migrations, tenant/auth changes, storage changes, confidential vendor evidence, AI calls, emails or automated governed decisions.
- Build synthetic backend and Streamlit AppTest regressions for every negative boundary above; compile touched modules and `app.py` before full isolated pytest; run `git diff --check`, inspect full diff, require both GitHub Actions jobs on the new head.
- Stop for independent TPRM, product, architecture, security and UX review; do not merge.

**Not production-ready:** source authenticity, actual end-user permissions, customer/standards mapping verification, semantic accuracy, real vendor document processing, and measured analyst effort remain separate future milestones.
