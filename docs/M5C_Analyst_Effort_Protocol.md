# M5C analyst-effort measurement protocol

**Status: prepared, not executed.** Human minutes, clicks, unnecessary questions,
preferences and savings remain unmeasured. This is a synthetic pilot protocol,
not a new application workflow or evidence of production readiness.

## Setup and comparability

Record the app commit, corpus version/hash, document format, fixed assessment date,
reviewer experience and session method (observed human, shared-browser agent, or
AppTest). Keep these methods separate: automated steps are not human effort.
Use an isolated synthetic session and the benchmark's fixed assessment date. A
live session on a later date changes freshness; record that deviation and do not
pool it with the fixed-date baseline. Do not change production authentication.

First obtain independent TPRM gold review using the companion packet. Preserve the
frozen holdout; use it to measure the existing experience, not to tune extraction.
A later intervention needs a separate development corpus and fresh independently
authored evaluation material before claiming improvement.

Use the same documents and questions for an app-assisted review and a manual
source review. Counterbalance order across reviewers/cases; record previous
exposure. A reviewer seeing the same source twice is no longer blind, so report
learning effects rather than asserting a causal time saving. Do not set a success
threshold after looking at observations.

## Tasks per case

1. Identify assessed requirement and example threshold, source service/environment,
   type/date and any contradiction. In the app, use source-metadata suggestions
   only after checking the cited wording; record any corrections and reasons.
2. Locate the decisive original quotation and its physical source location.
   Distinguish current adverse evidence, uncertainty and missing proof. Record
   whether the app surfaced the decisive material statement or the reviewer had
   to find it manually.
3. Choose the smallest justified next action. Separate an evidence request from
   an intentional finding for a substantive concern; an evidence gap does not
   automatically establish a deficiency. Preserve the ability to justify a
   material evidence deficiency as a finding.
4. Record a draft action if appropriate, explicitly evaluate metadata changes,
   finish the synthetic review and inspect source-linked export. Check original
   bytes, unconfirmed facts, pending vendor decision and null residual score.

## Observation record

Capture one row per case and method, with raw interaction notes retained locally:

| Field | Definition |
| --- | --- |
| case_id / method / reviewer | Corpus case, method and pseudonymous reviewer ID |
| app_commit / corpus_hash / as_of | Reproducible runtime and source context |
| prior_exposure / order | Learning and sequence confounders |
| elapsed_seconds | Observed start-to-completion time; null if not measured |
| decisive_quote_seconds | Time until exact decisive quote/location found; null if unavailable |
| clicks / text_edits | Count actual user interactions under a declared counting rule |
| metadata_corrections | Fields changed, previous/suggested/final values and reason |
| unnecessary_questions | Questions independently judged redundant given the same source; include quote/rationale |
| gap_only_finding | Whether a finding was created solely for absent proof, with reviewer justification |
| source_discovery | App surfaced / manually found / missed / ambiguous |
| final_action | Request Evidence / intentional finding / other, with rationale |
| completion / errors | Completed, blocked or abandoned; retain navigation/rework details |
| safety_checks | Citations/originals verified; no fact/control/vendor/risk approval |

Never substitute zero for an unobserved value. Retain failed/abandoned tasks and
report denominators and exclusions. Define a click consistently (one deliberate
activation; typing counted separately), and record whether expansion/navigation
and downloads are included. Redundancy of questions requires independent source
review, not the application's own opinion.

## Output and decision

Report case-level observations plus distributions by method, control family and
format. Publish sample sizes and disagreements; do not extrapolate to real vendor
accuracy or ROI. Compare raw outcomes before proposing a small UX change. Consider
Request Evidence defaults only if observed gap-only findings or unnecessary
questions support it. Keep review history, deliberate findings and provisional
risk safeguards intact.

End with one justified recommendation: build, simplify, defer or reject, listing
remaining assurance and measurement limitations. Owner review is required before
broader product claims; PR #29 is still draft and merge authorization is separate.

## Preparatory automated diagnostic

A [browser rehearsal](M5C_Browser_Rehearsal.md) has now exercised two known sources
and led to a small correction of inaccurate metadata advice. This was not an
execution of the formal human protocol: gold validation remains incomplete,
source quotes were known, and the live assessment date differed from the frozen
benchmark. Human measures and ROI remain null. The rehearsal must not be cited
as evidence for default-action changes or broad parser improvements.
