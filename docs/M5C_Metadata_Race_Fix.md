# Source-metadata stale-snapshot correction

The rapid-click observation from the browser rehearsal is now reproduced as
application draft-state loss, not just a slow visual update. This does not change
parser rules, thresholds, gold, factual confirmation or risk governance.

## Reproduction and cause

Real Chromium uploaded two synthetic PDFs and clicked each file's source-metadata
button without waiting for the first declaration to visibly update. Both button
triggers appeared in the outgoing Streamlit widget messages. The second message
still carried the first file's old assertion/no-date fields. Changed-widget
callbacks treated those obsolete fields as new manual edits and rewrote the
durable draft. The downloaded assessment retained the wrong first declaration.

| Diagnostic path | Completed trials | Both declarations preserved |
| --- | --- | --- |
| Before: rapid PDF pair | 4 | 0 |
| Before: rapid TXT/DOCX pair | 4 | 4 |
| Before: TXT/DOCX with visible-update acknowledgement | 2 | 2 |
| After: same rapid PDF pair | 4 | 4 |
| After: rapid TXT/DOCX pair | 2 | 2 |

These are bounded diagnostic trials on known synthetic documents, not population
failure rates or human latency measurements. PDF extraction latency exposed the
interleaving; parser bounds and the parsing implementation were not changed.
Browser widget messages and downloaded report declarations were checked together,
so the diagnosis is not based only on screenshots or an assumed successful click.

## Correction

Applying a source suggestion changes durable logical metadata and increments that
file's UI-control revision. Fresh controls are mounted from the durable draft;
callbacks from an older revision cannot overwrite it. The five existing fields
retain the same labels and behavior. Current-revision manual edits, including
clearing a date or routing list, still work. Other pending scope/routing edits
survive source application. Revision state is per file and per session and is
cleared by the existing assessment reset.

Every source action still invalidates completion and requires explicit evaluation,
even if values already match. UI revisions do not become document versions,
source IDs, policy versions or assurance facts. Original bytes/hashes and
historical citations remain unchanged; no control/vendor approval or numerical
risk reduction follows from applying metadata.

## Regression and evidence

An actual-app regression replays the same old browser widget snapshot for the
second source action. It failed before the fix (first file returned to assertion)
and passes after. Further regressions cover obsolete callbacks for all five
fields, current manual edits, simultaneous pending edits/source action, navigation,
completion/export blocking, stale finding history and exact originals. Tests use
native file upload rather than seeded file objects; the snapshot replay uses
Streamlit's AppTest transport to exercise the real callback lifecycle.

All 16 exported replay assessments whose packages were inspected retain exact
original artifact hashes, unconfirmed facts, null residual score and vendor
approval=false. The complete before/after experiment covered 16 browser trials. Raw evidence is
in a local handoff ZIP, with its digest and results recorded in
[`m5c_metadata_race_1.json`](../benchmarks/observations/m5c_metadata_race_1.json).
Earlier failed-rehearsal records are preserved as historical observations.

This fixes the reproduced stale-snapshot interleaving in these trials. It does
not establish human usability, arbitrary concurrency correctness, external
holdout accuracy or completion of independent human TPRM validation. No parser
expansion, review default changes, authentication or merge is included.
