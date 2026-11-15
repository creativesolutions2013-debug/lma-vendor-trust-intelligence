# M6 Phase 1 — Pre-adjudication TPRM quality review

**Status:** Technical review of the provisional reference cases; **not** an independent human adjudication, benchmark acceptance, or field accuracy result. This document records review questions without changing the scenario seeds, gold labels, M5C holdout, or production evaluation.

## Blocking measurement interpretation issue

The current `reference_concerns` field groups **demonstrated technical exceptions**, **insufficient implementation evidence**, **scope/freshness gaps**, and **absence of operating proof**. The scorer produces aggregate concern recall/precision from IDs without distinguishing these categories. Such a metric **must not** be published as control-failure detection accuracy, material-risk recall, or a standards assurance rate.

The `no-evidence` case has an empty concern list despite a requirement whose evidence is absent. A reviewer who reports no concern scores no missed concerns, even if they fail to recognize the evidence gap. The question metric partly captures the issue but does not demonstrate accurate evidence-versus-control classification. **Do not count an empty concern reference as evidence of a met control.**

Necessary questions are provisional author judgments, not an objective optimum. Matching an ID is not proof a vendor contact is necessary; an analyst might obtain scoped internal evidence without contacting the vendor. Ask adjudicators to classify each proposed request as *vendor request*, *internal verification*, *review only*, or *unnecessary*, and capture alternative acceptable requests. Do not edit the source seed to force preferred scores.

## Case-by-case adjudication prompts

| Scenario | Provisional issue to review | Required adjudicator decision |
| --- | --- | --- |
| `mfa-method-unknown` | MFA existence claim with unspecified method and recovery route | Is this evidence insufficient for phishing-resistant privileged MFA, rather than proof of failure? Is the smallest question limited to method, privileged scope, enforcement and fallback? |
| `mfa-totp-not-phishing-resistant` | Reported TOTP method does not establish phishing resistance | Separate claimed implemented method from a customer threshold exception; confirm whether bypasses or alternate authentication are evidenced |
| `tls-weak-secondary` | Production TLS 1.1 listener despite stronger primary | Is the listener in assessed scope and is remediation evidence the right follow-up rather than redundant broad configuration questions? |
| `tls-disabled-legacy` | One scoped good listener, incomplete population coverage | Do not infer that an unmentioned listener is weak. Is an inventory request needed under this customer's all-endpoints threshold, and can existing internal records suffice? |
| `dr-over-target` | Stated achieved RTO/RPO exceed customer objectives | Distinguish measured result, scope, currency, and whether an explicit exception or corrective action already exists; do not auto-approve risk |
| `dr-plan-not-operation` | Policy objective and future schedule, no achieved test result | Classify as operating-proof gap, **not** demonstrated DR control failure |
| `dr-stale-report` | Fresh report cover date with historical exercise | Assess using exercise date, not document issuance date; identify smallest current-test proof needed |
| `dr-other-service` | Test of Cedar Warehouse instead of Cedar Billing API | Evidence may be valid but out of scope; no finding of a failed Cedar Billing API control without further evidence |
| `no-evidence` | No IR documentation or exercise was submitted | Explicitly record `Evidence Missing` and a targeted evidence request; review whether `reference_concerns: []` creates a misleading perfect omission score |
| `documented-ir-only` | Approved plan but no operational exercise | Treat governance documentation as distinct from exercise operating proof; avoid inferring a missed exercise solely from an absent attachment |

## Independent human adjudication record — required before benchmark claims

Use **two independent qualified reviewers**, blinded to LMA suggestions and provisional author labels where feasible. For each scenario, record:

1. **Customer requirement:** requirement ID, specific criterion, customer threshold and assessed service.
2. **Source interpretation:** exact quotation, source identifier, evidence scope, time, operating-vs-policy type and any qualifiers.
3. **Classification:** `demonstrated_exception`, `evidence_insufficient`, `out_of_scope`, `stale_evidence`, `supported_with_limits`, or `unresolved_ambiguity` (multiple may apply). **Do not treat these as equivalent risk outcomes.**
4. **Potential materiality:** independently justified `material_concern`, `not_established`, or `not_applicable`; missing evidence is never automatically a failed control.
5. **Smallest next action:** verify existing internal records first, seek specific vendor evidence only if necessary; state whether an action is internal, vendor-directed or analyst-only.
6. **Review outcome:** independent reviewer agreement/disagreement, rationale, escalation, and final adjudicator decision. Any approved reference revision must be a **new version**; preserve the original seed and reasons for changes.

No fabricated human annotations or timings should be committed. If reviewers disagree, report disagreement and unresolved semantics rather than silently selecting a favorable label.

## Study readiness gate

- [x] Ten provisional synthetic cases and standalone scorer exist.
- [x] Exact-head SQLite and PostgreSQL CI passed for commit `1beecd0f90b242796a1ed890dadfdb6042f66441`.
- [x] Missing observation fields and duplicate/malformed reference annotations fail closed.
- [ ] Two independent human reviews collected.
- [ ] The gap/exception/outcome distinction adjudicated and reflected in a **new version** of the scoring contract, with appropriate tests.
- [ ] Necessary questions independently categorized and adjudicated.
- [ ] Actual manual-versus-LMA sessions observed with counterbalanced order.
- [ ] Evidence-verifiability and reviewer-effort limitations published with sample size and errors.

**Recommendation:** Keep PR #39 draft and do not report aggregate concern recall as material-exception detection. Independent adjudication must happen before comparing products or claiming time/question savings. Implement a narrowly scoped typed classification scoring change only after human reference definitions are approved; avoid increasing production feature scope.

PR #38 and protected `main` remain out of scope; no merges are authorized.
