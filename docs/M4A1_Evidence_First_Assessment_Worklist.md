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

`EvidenceNeed` supplies the exact fact/dimensions, acceptable artifact/kinds,
period and scoped question. The existing orchestrator continues using
`analyze_targeted_evidence_gaps` for its separate inventory work plan. M4A no
longer manufactures inventory records with the requested document label, perfect
confidence or zero exceptions to suggest that a same-kind document covers a need.
Request freshness hints cannot relax the customer's requirement age limit.

Every need has a visible state:

| State | Required basis | Effect |
| --- | --- | --- |
| Supported by reviewed evidence | Explicit `NeedReview`, current exact source/fact fingerprints, all declared dimensions represented by semantically confirmed M3D facts, and existing domain-supported checks (or eligible fallback meaning evidence) | Suppress only this need's request; never approve a control |
| Analyst validation required | Plausible current candidate but no valid specific review, stale/duplicate review, or unresolved linkage | Show the exact question to investigate; defer vendor follow-up without claiming the fact is established |
| Missing or insufficient | No current in-scope candidate, or explicit analyst confirmation that all current candidate sources lack the required fact | Preview this precise missing-fact request; never infer control failure |

`record_need_review` is a pure session-only API for an explicit decision with
`confirms=True`, named analyst, date, rationale and source/fact fingerprints.
It neither authenticates the analyst nor persists a decision. The fingerprint
binds the engagement, full requirement/threshold, exact need definition, date,
complete M3D bundle and review state. Sources, thresholds, scope, semantic
challenges and other review changes invalidate prior matches. Every build checks
the record again; direct record construction cannot bypass the factual gates.
Supported records require every selected fact to belong to its cited sources;
domain rules still decide which technical facts qualify. Policy/assertion or
partial-population interpretations excluded by those rules cannot establish an
operating need. Fallback support requires M3D's accepted-kind/relevance eligibility
and remains limited to the explicitly reviewed meaning, never technical passing.

An insufficient record identifies all current candidate sources so another
plausible report cannot be ignored. Generic relevance or kind is only a cue for
analyst inspection, never proof of support. Need states and requests are computed
even when the row's first action is exception triage, retaining independent gaps.
Requests deduplicate within exact relationship/control/requirement/threshold and
fact/question context; distinct thresholds are not merged. Rows reference only
their own requests and pending missing facts. Review controls were not added to
the inspection-only UI; all product fixtures still start unreviewed.

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

| Package (4 requirements, 5 defined evidence needs) | Vendor-request previews | Ask-everything baseline | Reviewed supporting needs | Needs awaiting validation | Missing/insufficient needs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial: recovery plan but no completed exercise | 1 | 4 | 0 | 4 | 1 |
| Completed recovery exercise added | 0 | 4 | 0 | 5 | 0 |
| Additional active alternate-listener TLS exception | 1 | 4 | 0 | 4 | 1 |
| Exact control-ID mapping conflict | 1 | 4 | 0 | 4 (including 2 linkage gaps) | 1 |

The baseline is one question per applicable requirement, not the legacy question
library's generated count. These four deterministic packages are related examples,
not independent vendor samples. **These are deferred-request counts, not a
verified fact-level question-reduction benchmark.** Zero requests can coexist
with five unresolved needs awaiting analyst validation. They do not measure
analyst effort, semantic accuracy, technical compliance, or cycle-time savings.
The UI reports reviewed support separately and does not invent prior reviews.
Separate tests use explicit review actions to demonstrate provisional support
and a current confirmed failure sorting above support, while governance stays
outside this slice. Adding an artifact does not establish its facts.

A separate adversarial test package has one DR requirement and two specific
needs, achieved RTO and RPO. With only a dated RTO result and no review it has
**0 reviewed supporting needs, 2 awaiting validation, 0 requests**. After explicit
test-only factual confirmation and need review it has **1 reviewed supporting
need, 1 insufficient need, 1 targeted RPO request** (ask-everything baseline: 1
question per requirement). The same report type thus cannot conceal the RPO gap.
Source-reviewed RTO support remains a partial fact, never whole-control approval.

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

The first prototype passed 850 tests with one PostgreSQL-only skip, but independent
review identified that inventory-only matching could suppress a specific fact
request. The correction adds adversarial backend and UI regressions for RTO-only
reports, wrong dimensions/sources, unreviewed candidates, explicit insufficiency,
review invalidation, duplicate records, operational-proof gates and fallback
eligibility. Compile and complete isolated pytest results for the corrected head,
diff/security review, and both GitHub Actions jobs are recorded in draft PR #8.
Independent re-review remains required; no production-readiness claim is made.

Corrected local validation: compilation of `app.py`, both changed modules and all
four M4A test modules passed before full pytest: **887 passed, 1 skipped** in
26.81s. The skip is the PostgreSQL-only smoke test; CI runs the PostgreSQL suite.
The follow-up adds 32 adversarial backend cases and 5 UI cases, including a
confirmed failure and independent missing fact on the same row. Existing M3D,
legacy work-plan and governed-decision regressions pass unchanged.
