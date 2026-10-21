# M4A-1 — Evidence-First Assessment Worklist

**Status: implemented synthetic prototype on draft PR #8; independent review required.** The source of truth for acceptance is [GitHub Issue #7](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/7). This slice adds no production authorization or governed decisions.

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

## Implementation and contract

`src/assessment_worklist.py` is a pure adapter, not a second evaluator. It calls
`build_assessment_work_plan` once for the supplied applicability, retains that
legacy result separately, and freshly inspects explicitly linked M3D cases.
`ApplicabilityResult.controls` defines the row set, including unknown IDs; the
question library is never an eligibility gate. Multiple explicitly mapped
requirements can appear under one control. A control without a definition or
link stays visible as Needs Review; an unlinked result cannot add a guessed row.

`AssessmentScope`, `RequirementMapping` and `AssuranceLink` bind engagement,
service/environment, full versioned customer requirement, threshold and assessment
date. Duplicate applicable IDs/mappings or assurance identities are rejected
before any result is displayed, preventing a positive duplicate from hiding a
failure. Other mismatches get a visible Needs Review row without reusing source
content. Legacy inventory also needs an exact relationship wrapper; its evidence
sufficiency is informational and retains the existing orchestrator policy/clock.

The adapter preserves source-bound facts, review fingerprints, exceptions,
freshness and uncertainty. Its citation presentation filters out unmatched quotes;
source context still shows actual parser text, origin, version, dates and original
content hash. Confirmed current technical failures sort first, then unresolved
conflicts/potential exceptions, missing artifacts, analyst validation and fully
reviewed provisional support. Raw exception signals can include false positives;
they still require separate human triage rather than automatic dismissal.

`EvidenceNeed` supplies a precise fact, acceptable artifact/kinds, period and
question for its exact requirement. Existing `analyze_targeted_evidence_gaps` is
used only after source identity, relevance/context, kind and freshness screening.
Request freshness hints cannot relax the customer's requirement age limit.
Current candidates, including sources needing relevance/meaning review, defer
requests in favor of analyst work. An absent, stale or out-of-scope required
artifact can produce a preview; neither legacy UNSUPPORTED nor unconfirmed M3D
missing checks alone do so. Dimensions describe analyst work, **not** automatic
fact-level gap resolution. An artifact may be present yet insufficient after
review. Requests deduplicate within exact relationship/control/requirement/threshold
and fact/question context, ignoring duplicate request labels; different thresholds
are not merged. Rows reference only their own requests and pending missing facts.

`src/assessment_worklist_pilot.py` reuses existing M3D synthetic cases. The
read-only `src/assessment_worklist_ui.py` renders inside existing Assessments:
one priority-sorted table, selected requirement detail, expandable source context,
and not-sent follow-up previews. No upload, send, confirm or approval control is
introduced. Opening/selecting a package cannot create fact, signal or bundle
reviews. All built-in fixtures start with empty review state; tests explicitly
call the existing review API to model a previously reviewed case when testing
provisional Met/reuse and confirmed failure priority.

## Synthetic results and limitations

Each package has **4 applicable requirements across 4 families**: explicit
ENC-01 → ENC-02.TLS, BCP-01 → BCP-01.DR, CUSTOM-GOV-42 → GOV-01.POLICY, and
CUSTOM-VM-42 → VM-01.REMEDIATION. The last two have no specialist evaluator.

| Package | Distinct vendor-request previews | Ask-everything baseline | Meaning |
| --- | ---: | ---: | --- |
| Initial: recovery plan but no completed exercise | 1 | 4 | Ask only for the scoped completed exercise with achieved RTO/RPO |
| Completed recovery exercise added | 0 | 4 | Only the recovery row/request changes; meanings still need analyst review |
| Additional active alternate-listener TLS exception | 1 | 4 | Retain adverse evidence/triage; unrelated recovery request remains |
| Exact control-ID mapping conflict | 1 | 4 | Surface TLS linkage gap, exclude its unlinked source, retain other rows |

The baseline is one question per applicable requirement, not the legacy question
library's generated count. These four deterministic packages are related examples,
not independent vendor samples. Counts demonstrate request minimization from
candidate inventory, not measured analyst effort, semantic accuracy, technical
compliance, or cycle-time savings. The UI does not invent prior analyst reviews.
Separate tests use explicit review actions to demonstrate provisional support
and a current confirmed failure sorting above support, while governance stays
outside this slice. Closing an artifact request does not prove its facts true.

Regression coverage includes arbitrary/unmapped IDs, exact relationship and
policy/threshold/date mismatches, duplicate positive/adverse inputs, unrelated
results, legacy SUPPORTED, stale/wrong-scope/asserted operating records, invented
citations, review invalidation, precise pending facts, request deduplication and
cross-row isolation. Streamlit AppTest exercises source detail, request changes,
exception-first order, fallback visibility, invalid packages, and inspection with
database/write/network/AI/review calls blocked. This does not validate real app
permissions, external custody, standards mappings, arbitrary document semantics
or the adequacy of customer-supplied definitions/needs. Existing MFA compatibility
and all domain-specific technical rules remain unchanged.

Validation for this implementation: compilation of `app.py`, all three added
modules and their three test modules passed **before** the complete isolated
pytest run: **850 passed, 1 skipped** (PostgreSQL-only smoke test). This adds 51
synthetic backend/integration/UI cases to the 799-test merged baseline. Diff and
security review covered linkage, request/citation isolation, exception priority,
review invalidation and the absence of outbound or governed writes. GitHub
Actions results on the final commit are recorded in draft PR #8; both unit and
PostgreSQL compatibility jobs are required for independent review.
