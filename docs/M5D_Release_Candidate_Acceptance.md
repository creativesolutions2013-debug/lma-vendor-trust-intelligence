# M5D evidence-extraction release candidate — acceptance record

**Status:** Draft implementation for synthetic pilot and owner review. **Not merged.**
**Scope:** M5C frozen holdout plus M5D TLS port, DR excluded dependencies, and complete achieved-duration recognition. No new control family, automatic control approval, authentication or governed risk mutation.

## Verified engineering evidence

- Integration source: `feature/m5d-integration-quality-gate` at `b197b6e92127749452fb4e665339d4664aa5f8b5` (PR #33).
- GitHub Actions run [41769396050](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/41769396050): **Unit tests: success; PostgreSQL compatibility: success.** Current release-candidate head must pass its own CI before acceptance.
- Independent Codex code review on that exact integration head reported **no major issues**. Automated review is not an independent security certification or substitute for human review.
- Published immutable-benchmark artifact `m5c-baseline`, artifact ID `13293503131`, for that run. Frozen M5C corpus and scorer blob SHAs: `8caa0d5031ff2b83bd71aa9ec9e89eeb8ffe0c8f` and `98572ab4a3c7ab0664cf09e35470b5fada294abf` respectively. Do not change these to fit a desired score.

| Metric | M5C pre-M5D baseline | M5D integrated result |
| --- | ---: | ---: |
| Material exception cases surfaced | 3/8 (37.5%) | **7/8 (87.5%)** |
| Frozen annotated typed facts matched | 22/29 | **25/29** |
| Typed fact recall | 75.86% | **86.21%** |
| Typed fact precision against annotations | 22/22 (100%) | **25/26 (96.15%)** |
| False adverse alarms in 2 no-exception cases | 0 | **0** |
| Adverse overclaims in 6 abstention cases | 0 | **0** |

The benchmark has 16 synthetic cases (8 ENC-01, 8 BCP-01), with TXT/PDF/DOCX material. Results are bounded to this authored corpus, not unbiased field estimates or evidence of speed/ROI. No observed analyst minutes, click counts, or vendor-question reductions were measured.

## Known exceptions and limits

1. `dr-failover-narrative`: a material exception remains **not surfaced**. This narrative uses nonstandard human recovery phrasing; avoid silently converting the unsupported wording into a passing comparison. Needs analyst interpretation and potentially a future bounded extraction slice.
2. `tls-gateway-caption`: exception **is surfaced**, but the subject `legacy gateway port 9443` differs from annotated `gateway port 9443` (one predicted extra and one gold fact unmatched). Do not rewrite the frozen annotation to improve precision.
3. Four of 29 gold typed facts remain unmatched. Scope, textual attribution, metric ownership and age can be ambiguous; observed and attributed statements are distinct. A cited candidate is not proof of correctness.
4. All extracted candidates and hypothetical threshold comparisons remain **unconfirmed**, with original source, location and fingerprint verifiable. Customer requirements set thresholds. Missing proof is not a control failure, and no AI draft may approve a control or change authoritative risk.
5. No real vendor evidence, confidential documents, AI calls, field precision, production identity, SOC2 assurance or production readiness has been verified by this release candidate.

## Owner quality-control checklist (before any merge)

- [ ] GitHub Actions passes on **exact release-candidate SHA**, including `py_compile app.py src/upload_evaluation.py`, full pytest and PostgreSQL job.
- [ ] Exact-head independent review has no unresolved P1/P2 findings; inspect full changes rather than review receipt alone.
- [ ] Frozen benchmark artifact remains 7/8 or better for exception surfacing, **zero** false adverse in frozen no-exception/abstain cases; review all misses and extras rather than adjusting gold.
- [ ] Confirm an analyst can see requirement, customer threshold, source and citation, reasoned provisional finding, uncertainty and smallest necessary follow-up; no auto-approval or risk-score mutation.
- [ ] Review with a human on synthetic example evidence, including at least one rejected attribution, one stale/test-only context, one weak production TLS listener, and an independent RTO/RPO continuation. Analyst workflow minutes and unnecessary vendor questions remain **unmeasured** until observed.
- [ ] Approve release sequence or request changes **explicitly**. No automation should merge.

## Release/branch decision

PRs #29–#32 are independent review slices; they modify a shared evaluator and may conflict when applied sequentially. PR #33 is **integration-only and must not merge**. This consolidated release candidate is the proposed review surface to avoid manual cherry-pick conflict resolution. No merging of this release candidate, #29–#32, or #33 is authorized merely by passing tests. After explicit owner approval, review GitHub branch protection and the exact combined diff before a controlled merge.

**Product decision:** Simplify and ship a narrow evidence-first synthetic pilot after safety gates; defer broader narrative extraction, dashboards and policy configuration. Prefer calibrated abstention over brittle phrase proliferation.
