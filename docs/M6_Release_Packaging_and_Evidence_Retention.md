# M6 release packaging and evidence-retention decision

**Decision:** simplify packaging; retain all previously sealed execution artifacts in place for this release. Do not move, rewrite, delete, squash, or re-seal them as a cleanup. This is a documentation-only retention gate for the synthetic M6 development workflow, not a new runtime feature or a retention guarantee.

**Scope and baseline:** reviewed stacked PRs #39 → #40 → #41 → #42 at final head `1b377f216003bf55f1e4ef0c740de01493f1dd90`, relative to main `fff3903660cdd162108047f82110ef8283b2d56e`. GitHub compare reports 22 commits, 141 changed files, and **no changes to `app.py`, `src/`, application migrations, or dependencies**. At that snapshot, the execution directories contain 112 files:

| Execution directory | All | Historical prior attempts | Local validation logs | Inputs | Other primary records |
| --- | ---: | ---: | ---: | ---: | ---: |
| `benchmarks/executions/m6_live_20261116/` | 56 | 18 | 7 | 8 | 23 |
| `benchmarks/executions/m6_ai_adjudication_20261116_v1/` | 56 | 22 | 7 | 8 | 19 |
| **Total** | **112** | **40** | **14** | **16** | **42** |

The categories above are **file counts**, not sizes or value judgments. An additional seven files under `benchmarks/examples/` document blocked attempts and an explicitly hand-constructed simulation. The exact GitHub compare and PR diffs, not this point-in-time table, determine the live scope if heads change.

## Essential for the reproducible synthetic acceptance record

Preserve and cite:
- The blind packet and canonical requirements/thresholds, reviewer and coordinator agent instructions, output contracts, and runnable benchmark scripts.
- **Completed A/B and coordinator** raw response, run, session and provenance records; inputs/manifests, source-Git anchors, SHA256 sidecars, and original quotations.
- The deterministic comparison and `m6-ai-proposed-reference-v1` including the 72 original field dispositions; the separate `m6-ai-owner-quality-proposal-v2` (an interpretation overlay, **not** a new model run).
- Execution reports and validation summaries tying together code SHA, run IDs, exact-input hashes, and CI. Retain failed attempts necessary to explain authentication/schema/boundary rejection and prove that rejected output was not treated as a valid completed review.

Do **not** conflate a SHA256 file with immutable or signed retention. Git history is tamper-evident in normal practice but is not WORM storage or an independent custody attestation. Nothing here establishes provider isolation, serving-model identity, model independence, human-validated reference labels, measured time saved, question reduction, or production control assurance.

## Historical diagnostics and prospective archival candidates

The 40 `prior_attempts/` files, 14 `validation/` files, and seven synthetic example/blocked-attempt files are reasonable candidates for **future** archival packaging to reduce long-term source-tree growth. They are **not disposable** now: existing manifests, source-Git anchors, paths, sidecars, tests, and cross-references could depend on their exact bytes.

A future change may propose an immutable-by-policy, access-controlled archival store with content-addressed digests and an index in the source repository, but only after:
1. Define authorization, access-control, retention period, deletion/hold policy and a reproducible restore procedure suitable for *synthetic* artifacts. Do not introduce vendor-confidential evidence into this archive by default.
2. Produce a manifest listing every original path, byte count, SHA256, originating PR/commit, run ID and archive URI. Verify each byte-for-byte before and after transfer.
3. Test restoring the *complete* original layout and rerunning source sealing, citation and benchmark validation without network/model dependence.
4. Identify and repair affected scripts and references deliberately, with synthetic regressions and GitHub Actions. Preserve the original Git history and original rejected attempts.
5. Seek explicit authorization before deleting any source-tree artifact or changing retention policy. Archive location and external retention controls are **not selected** in this milestone.

Do not create an external archive, download sensitive evidence or add a storage service as part of M6. Minimize ongoing repository growth by defaulting **future** routine runs to temporary ignored output directories and explicitly publishing only reviewed release-evidence bundles. The existing standalone scripts and historical sealed directories remain unchanged.

## Release and governance decision

- **Build/keep:** reproducible AI-only synthetic benchmark, code tests, source-cited reports and versioned provisional interpretation overlay.
- **Simplify:** make new runs' archival/publication an explicit step; avoid committing repeated full debug runs by habit.
- **Defer:** external archival store, WORM claims, automatic pruning, production retention orchestration, and any new UI.
- **Reject:** using two AI reviewers and a coordinator as verified real-world accuracy, independent qualified-human gold, evidence of control approval, or quantified vendor-question reduction.

This review does not approve any vendor/control, accept risk or mutate authoritative risk calculations. User-authorized governed decisions remain separate. The next meaningful product milestone after packaging is a *small, representative, evidence-first pilot measurement protocol*, with correct handling of demonstrated exceptions vs missing evidence, source-verifiable interpretations and actual analyst/vendor-effort measurement when such data exists.

**Release gate:** keep this PR and #38–#42 in draft until owner authorizes a separate integration decision. Before any merge, verify branch stack/base targets, original-artifact hashes, compile before full SQLite/PostgreSQL pytest and exact-head CI, and inspect the complete diff. Do not change protected `main` without explicit approval.
