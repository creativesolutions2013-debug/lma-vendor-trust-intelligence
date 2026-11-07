# M5C automated browser diagnostic and small prompt correction

**Status: diagnostic only; formal human analyst study not performed.** Playwright
and Chromium drove the actual Streamlit `app.py` in isolated development mode,
using frozen `tls-port-prose.docx` and `dr-uncovered-idp.txt` source content. The
operator knew the expected quotes. This is not a blind evaluation, human TPRM
validation, independent corpus, usability study or evidence of ROI.

The normal live app captured `scope.as_of=2026-11-07`; the benchmark uses fixed
`2026-11-01`. These runtime fields are recorded rather than silently frozen or
relabeled. Do not pool this rehearsal with the fixed-date benchmark.

## Observed flow

Each completed replay entered vendor/service/use case, attached both real files,
applied source metadata with one click per file, evaluated, expanded both source
citation panels, chose **Request Evidence** for missing-proof-only DATA-01,
recorded a rationale, finished and downloaded the real assessment ZIP.

| Observation | Before | After wording correction |
| --- | --- | --- |
| Explicit scripted clicks | 14 | 14 |
| Programmatic text fills, each committed with Tab | 4 | 4 |
| Native file-list injection batches | 1 | 1 |
| Original artifacts verified byte-for-byte/hash | 2 | 2 |
| Exact fact/context citations verified | 11 | 11 |
| Resolving HTML links | 15 | 15 |
| Request Evidence annotations / findings | 1 / 0 | 1 / 0 |
| Confirmed technical facts / vendor approval | false / false | false / false |
| Numeric residual risk | null | null |

These are explicit automation API calls, excluding implicit focus, auto-scroll,
waits and the native file-picker UI. They are not physical human steps or a
minimum-click path. Quote visibility was observed after logged actions 9 and 10;
that is not time to discover or understand an unfamiliar concern. Human minutes,
clicks, redundant vendor questions and gap-only finding rates remain **unmeasured**.
No action-count reduction or time saving is claimed.

## Specific defect and correction

Both original evaluations had empty source-uncertainty lists and matching source
and declared type/date/service/environment, yet their next action said:

> Resolve source date/type/scope discrepancies and confirm candidate meanings; obtain missing technical coverage or operating proof.

The non-adverse next-action text now uses the existing uncertainty list:

- Empty list: **Confirm candidate meanings; obtain missing technical coverage or operating proof.**
- Nonempty list: **Review the listed source uncertainties and confirm candidate meanings; obtain missing technical coverage or operating proof.**

This does not add a targeted signal, interpret a new phrase, change an adverse
branch or suppress uncertainty. New regressions cover both families, a real date
mismatch, no source input and the actual Streamlit upload/suggestion/reevaluation
flow. All evaluation fields other than `next_action` were identical in the two
successful exported assessments. Both full legacy and candidate benchmark JSON
reports also reproduced unchanged.

## Retained failed preparations and remaining observations

Three failed preparations are retained in the evidence bundle: unavailable
FFmpeg video support before any UI interaction; a native-radio automation locator
intercepted by layout/header (visible-label navigation worked); and an early
unsynchronized after-fix replay where the first file still had assertion/no-date
metadata. That last attempt correctly showed uncertainty rather than approving
facts. Waiting for the visible declaration update before the next click passed.
The product-versus-driver cause is not established; rapid-click behavior is a
follow-up, **not** claimed fixed or excluded as proof of a clean first attempt.
Screenshots are viewport captures of Streamlit's scrolling app, not complete
captures of every offscreen source. Successful browser traces and raw interaction
logs accompany the exported ZIPs and failure records. No video is claimed.

**Recommendation: SIMPLIFY** the inaccurate generic metadata instruction only.
Do not alter parser rules or review-action defaults based on this diagnostic.
Formal human review, analyst effort, independent holdout validation and targeted
manual-signal measurement remain pending under Issue #28.

Machine-readable observations and evidence-bundle SHA-256:
[`m5c_browser_rehearsal_1.json`](../benchmarks/observations/m5c_browser_rehearsal_1.json).
The local evidence bundle is a handoff artifact; binary screenshots, traces and
assessment ZIPs are not committed to the repository.
