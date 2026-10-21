# M3C-1: exception-first analyst review

The Evidence Center now includes one privileged-MFA review pilot using eight
hand-authored synthetic packages. It presents the customer threshold, a provisional
outcome, prioritized exceptions and gaps, supporting citations, uncertainty and one
recommended next action. Full document context is expandable. This is a development
prototype, not production assurance or authorization.

## Analyst interaction

The default view creates no analyst reviews. Open **Record a session-only analyst
review** to record a reason and explicit decisions:

1. **Confirm displayed supporting interpretations** records one deliberate human
   confirmation of the entire displayed eligible group. All interpretations are
   presented together, including complete-population coverage and method/path
   properties. It retains a separate M3B fingerprint and `FactReview` for each
   interpretation. It does not confirm omitted, invalid, uncertain, contested or
   adverse facts, triage lexical signals, or acknowledge the complete bundle.
2. **Challenge a supporting interpretation** selects one fact and records an
   unsupported/ambiguous disposition with a reason. It can supersede an earlier
   grouped confirmation, including after provisional `Met`, while retaining all
   prior decision events. The challenged fact leaves the supporting group and
   complete-bundle acknowledgment is invalidated. A fresh bundle acknowledgment
   cannot override the challenge. Exact quotations and source locations are shown
   alongside each grouped interpretation and the selected challenge target.
3. **Confirm this exception's meaning** separately checks an adverse interpretation.
   A human-confirmed configuration/test statement can produce a provisional
   evidence-backed failure. A vendor assertion stays an unverified reported
   exception; confirming what the vendor said does not verify its implementation.
4. **Record this signal triage** separately records material/nonmaterial judgment
   with a reason for each current source signal. The default retains potential
   materiality. Supporting confirmation never dismisses signals. A mistaken
   nonmaterial signal disposition cannot erase a separately proposed adverse fact.
5. **Record complete-bundle review** explicitly acknowledges all supplied documents,
   including uncited documents, disagreements, scope, dates and alternate paths.
   Outstanding M3B limitations still block a positive recommendation.

All decisions remain in the Streamlit session. Their internal records preserve
actor, simulated review date, reason, bundle binding, targets and individual fact
fingerprints; the analyst sees a readable history. No database or governed record
is written. Switching the package or changing sources, fact fields, policy or
assessment date invalidates earlier confirmation. A package switch requires fresh
explicit checkbox confirmation rather than carrying a checked box forward.

The fixed synthetic assessment date is **2026-10-21**. Review dates and identity
represent a simulated development session, not authenticated production audit
records. The pilot accepts no uploaded documents or vendor/assessment context and
does not use the existing Evidence Center AI action.

## Safety boundaries

`src/mfa_analyst_review.py` composes the existing M3B gate and M3A evaluator;
neither module is changed. Inspection never manufactures reviewer truth. Grouping
is batching an explicit human semantic judgment, not automatically validating
meaning from quotation matches or content hashes. Complete source context remains
available and account, fallback and recovery coverage must be established
explicitly. Missing facts, unknown/disabled methods and stale assurance are gaps,
not affirmative control failures.

Method-based current failures require affirmative evidence that the authentication
path is active. Unknown activation remains a source-linked activation gap; an
explicitly disabled path remains disabled, rather than a current failure. The
adapter also withholds old supported method reviews with unknown activation, so
restoring a pre-correction session cannot retain a verified-risk conclusion. The
original source and review history remain available.

Adverse/conflicting statements, unverified vendor admissions, material signals,
uncited provenance problems, stale evidence and service/population/path scope gaps
are retained ahead of supporting evidence. Rejected or ungrouped interpretations
remain reviewable. A material exception cannot be cleared through supporting
confirmation. Every outcome, including `Met`, remains provisional and requires
separate independent governance. This does not approve `PAM-01` or change historical
`IAM-01` / `PAM-01` meanings.

There are no migrations, navigation changes, dashboards, authentication changes,
live AI calls, automatic control dispositions or authoritative risk-score updates.

## Measured review decisions

The tests exercise explicit state-changing decision submissions. The baseline is
the review-object acknowledgments required by M3B: one per supporting fact, one per
adverse fact, one per source signal, plus one complete-bundle acknowledgment.
M3B had no analyst forms; this is a modeled API baseline, not a measured old UI or
a manual-assessment study.

| Synthetic case | Supporting facts | Separate exception confirmations | Signal triage decisions | Bundle acknowledgment | M3B baseline submissions | M3C submissions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Complete current FIDO2 implementation and tests | 7 | 0 | 2 | 1 | 10 | 4 |
| Configuration-backed emergency MFA bypass | 1 | 1 | 1 | 1 | 4 | 4 |
| Unverified vendor-reported emergency bypass | 1 | 1 | 1 | 1 | 4 | 4 |

The strong case saves six **decision submissions** by grouping seven semantic
confirmations into one. The two material-exception cases deliberately retain all
four decisions. One stays a provisional `Risk Identified`; the vendor assertion
stays `Needs Review`. Both remain visible after supporting confirmation and
complete-bundle acknowledgment.

Challenges are additional deliberate decisions, not automatic savings. Challenging
one fact before grouping adds one submission (five for that synthetic path).
Correcting the strong case after `Met` preserves its four original events and adds
a fifth challenge event; a fresh bundle acknowledgment is a sixth submission and
the result still remains `Needs Review`. The unchanged straightforward positive
case still takes four submissions. These correction paths do not imply a measured
time reduction.

`tests/test_mfa_analyst_review.py` prints the reproducible count report and checks
the per-fact records. `tests/test_mfa_review_ui.py` drives the actual Streamlit
widgets, including the strong four-submission path, separate exception handling
and invalidation when changing cases. The eight pilot packages also cover
contradictory configuration/test statements, historical operating tests, sampled
accounts/untested recovery, service mismatch and unknown methods.

These tests do **not** measure all checkbox/select/text-entry clicks, document
opens, reading effort, active analyst time, comprehension, real-vendor accuracy,
or missed exceptions in unseen language. No human timing study was performed.
Fewer submissions do not establish faster or better assessment. A later pilot
must compare actual analysts reviewing the same evidence manually, record time,
source openings, corrections, missed exceptions and incorrect positives, and
counterbalance the comparison where practical.

M3B's disclosed lexical-scanner blind spots, source-authenticity limitations and
reliance on correct human judgment remain. An analyst can still confirm an
incorrect interpretation or misclassify an uncited material signal. Only supplied
documents are considered. The synthetic cases provide regression evidence, not a
general semantic-understanding benchmark or a production authorization claim.

## Reproduction and independent review

Compile before running tests:

```bash
python -m py_compile app.py src/mfa_analyst_review.py \
  src/mfa_review_pilot.py src/mfa_review_ui.py \
  tests/test_mfa_analyst_review.py tests/test_mfa_review_ui.py
DATABASE_URL=sqlite:///:memory: python -m pytest -q
git diff --check
```

Independent acceptance requires the exact grouped fact bindings, separate
exception/signal/bundle decisions, visible material disagreements and scope gaps,
state invalidation, provisional outcomes, and the absence of governed writes.
Stop at a draft PR; do not merge without independent GitHub review.
