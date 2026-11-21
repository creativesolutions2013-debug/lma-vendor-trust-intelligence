# M6 pilot readiness — evidence-first validation gate

**Status:** Proposed pilot execution gate only. No independent human adjudication, observed efficiency results or verified production control decisions are represented here. This document is intentionally small and **does not** replace the M6 research materials or create another benchmark.

**Baseline:** protected `main` at `53e584454ec04e0b2600ef0a61b02d807290f705` after merged [PR #48](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/pull/48). The integrated synthetic analyst journey supports intake, uploads, provisional source-linked review, draft follow-up/finding and ZIP export. Production authentication, vendor custody, and real vendor delivery remain outside this pilot.

## Reuse rather than rebuild

The ten-case reviewer packet, blank reviewer worksheet, and known scoring limitations already exist on **draft/unmerged [PR #39](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/pull/39)**:
- [Blind packet](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/blob/feature/m6-analyst-quality-baseline/docs/M6_Blind_Reviewer_Packet.md)
- [Independent reviewer/adjudication worksheet](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/blob/feature/m6-analyst-quality-baseline/docs/M6_Adjudication_Worksheet.md)
- [Pre-adjudication methodological warning](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/blob/feature/m6-analyst-quality-baseline/docs/M6_Pre_Adjudication_TPRM_Review.md)

Stacked drafts [#40](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/pull/40)–[#43](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/pull/43) contain AI-only reviewer/coordinator and packaging experiments. They do **not** establish independent qualified human gold labels. Do not merge or duplicate them merely to run the pilot. Existing [PR #45](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/pull/45) and [PR #47](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/pull/47) are superseded in functionality by merged #48; avoid reapplying their diffs.

## Smallest pilot execution sequence

1. **Technical entry gate:** verify the GitHub Actions **push to main** following #48 finishes green (unit and PostgreSQL); review actual-app intake/upload/report behavior using only the synthetic test package. Record exact commit and test run ID. A green PR run alone is not the post-merge gate.
2. **Reference adjudication, before scoring:** independently give two qualified TPRM reviewers only PR #39's ten-case **blind packet**, with separate copies of its blank worksheet. Do not expose provisional labels, scoring code, AI outputs or each other's notes. A third human adjudicator records disagreements, rationale and any unresolved cases. Store signed/dated or pseudonymous reviewer records privately, never in this public repo.
3. **Classify the evidence, not the presumed vendor:** for each case distinguish `demonstrated_exception`, `evidence_insufficient`, `out_of_scope`, `stale_evidence`, `supported_with_limits` and `unresolved_ambiguity`; record source phrase (or 'none'), customer threshold, scope/date, materiality justified by the available evidence, and smallest action: `internal_verification`, `analyst_review`, `vendor_question`, or `no_action`. Never translate missing evidence into technical failure. The no-evidence IR case must receive an explicit Evidence Missing judgment.
4. **Preserve reference integrity:** document reviewer agreement, dissent and limits. If gold labels or necessary-action definitions change, version a **new** adjudicated reference and evaluation contract. Do not overwrite PR #39's original provisional scenario labels or the frozen M5C benchmark. Until this step, combined concern recall/precision **must not** be presented as material-risk detection accuracy.
5. **Observe the analyst journey only after adjudication:** run counterbalanced manual-versus-LMA sessions on the same approved synthetic cases with actual humans; measure per-case elapsed active review time, traceable/correct interpretation, unsupported claims, missed demonstrated exceptions, confusion between gaps and failures, vendor-directed requests that were actually necessary, and export/citation usability. Record session method, interruptions and unknowns; never infer productivity from simulated click counts or fabricated timings.
6. **Publish a compact decision record:** disclose sample size, independently adjudicated case coverage, per-class errors, disagreements, source verifiability, observed time/questions or `not measured`, and prioritized actionable defects. Keep pilot conclusions provisional, and do not allow AI drafts to update governed risk, approve controls or send vendor requests.

## Decision gates

| Gate | Acceptance evidence | Current state |
| --- | --- | --- |
| Merge and post-merge health | #48 merged; exact main push CI completes with both jobs green | **Pending final push CI result when this document was written** |
| Source/decision reference | Two independent blind human worksheets plus separately reconciled reference; unanswered disagreements disclosed | **Not performed / no human gold** |
| Interpretation reliability | Adjudicated exception vs gap vs scope/freshness classification; exact source provenance; errors disclosed | **Not measured against human reference** |
| Effort and question value | Direct observed manual/LMA timings and necessary vendor-question counts, same cases/counterbalanced | **Not observed** |
| Product authorization | Owner reviews pilot results and approves any subsequent code or release change | **Not authorized** |

**Stop conditions:** Any unsupported automatic final approval, altered authoritative score, fabricated source citation, misclassified absence as proven failure, or inadvertent disclosure of nonpublic reviewer/vendor material blocks the pilot claim. A valid finding remains provisional until authorized analyst action.

## Scope and commercial decision

**Build:** perform this bounded human quality study using existing materials. **Simplify:** one pilot decision record, not a new dashboard or intake form. **Defer:** additional evaluator families, AI coordinator expansion, live vendor upload, credentialed trust-center integration and production claims until the study identifies a concrete buyer or assurance need. **Reject:** treating AI-agreement rates or provisional concern-ID recall as trusted risk-detection accuracy.

**Branch boundary:** this page is a release-readiness handoff, not code, a completed study, or permission to merge M6 drafts. No participant worksheets, scenario label changes, database/migration, authentication, production evaluator, API calls or secrets are part of this branch.
