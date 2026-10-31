# M5B: source-cited candidates from uploaded synthetic evidence

The five-stage **New Assessment** journey now adds a bounded deterministic
TLS/DR candidate comparison to Evaluate and the exported report. Main CI at
`770746fb53fa5bf052cd333f473ffc7b42e8d952` passed both jobs before implementation.
This extends M5A's real upload workflow, not its internal scripted scenarios.

The adapter reads only existing bounded bindings. It creates `Observation`
candidates with exact document/segment IDs, location, quotation and source
fingerprint. `TlsThreshold`/`DrThreshold` and the existing typed evaluators own
comparisons; there is no second risk/policy engine. TLS gained an explicit
`enabled_version` dimension: below-policy enabled protocols are adverse, but an
above-policy enabled protocol cannot establish an endpoint minimum or coverage.
Enabled/disabled statements for the same endpoint/protocol conflict rather than
cancel. Different simultaneously enabled protocols are not inherently conflicts.

All candidates remain **unconfirmed**. A separate hypothetical comparison uses
only candidates without detected context/type/date discrepancies. It is not a
control result. The existing manual `ControlReview` remains Needs Review or
Evidence Missing; no FactReviews, whole-control confirmations, governed records,
risk reductions or vendor decisions are created. No complete-scope interpretation
is inferred, even when a document claims full coverage. Other applicable controls
remain in the existing worklist. ENC-01's encryption-at-rest/key-management aspects
are not evaluated by this TLS slice.

## Explicit supported syntax and limits

Actual UTF-8 TXT, text PDF and DOCX use the existing resource-limited parser and
binding lifecycle. Scans still need local OCR; PDF resource limits require the
POSIX/Linux host. Nothing is sent to AI, a trust center or another service.

Recognized source context is deliberately narrow, on separate lines:

```text
Configuration export
Service: Cedarline Analytics
Environment: production
Observation date: 2026-10-20
Primary listener 443: TLS 1.2 is enabled.
Alternate production listener 9443: TLS 1.0 is enabled.
```

`Service:` and `Environment: production/test` must agree with the assessed and
declared context. ISO dates use Observation/Observed/Test/Exercise/Scan/Configuration
`date:` labels. Multiple different values, invalid/future/old dates and disagreements
with uploader declarations remain visible with exact source context quotations.
Upload date is never substituted for observation date. TLS uses 90 days; recovery
uses the typed customer test interval. Source type uses explicit configuration,
scan/test/exercise-results and policy/plan wording; unknown/mixed types or mismatch
with the uploader label block eligibility. These are textual candidates, not
verified artifact authenticity or semantic classification.

TLS recognizes explicit `listener/endpoint <identity>`, TLS 1.0–1.3 and
`enabled/allowed/accepted` versus `disabled/rejected/blocked/prohibited/not enabled`
wording, including a shared enabled or disabled state on a bare protocol list.
Clause-local non-production environment qualifiers block production comparisons.
Support-only statements are not enabled protocols. Historical,
hypothetical, negated or ambiguous clauses, multiple endpoints in one clause and
missing identity stay uncertain. Unseen grammar, cipher suites, deployment
verification, complete inventory and real protocol testing remain unsupported.

```text
DR exercise results
Service: Cedarline Analytics
Environment: production
Test date: 2026-10-20
Recovery exercise completed.
Achieved RTO 300 minutes and RPO 90 minutes.
Identity provider was excluded from the exercise.
```

DR recognizes achieved/actual/measured/observed RTO/RPO with explicit minutes/mins
or hours/hrs; hours convert to exact whole minutes (including fractional hours).
Compound durations (such as 4 hours 30 minutes), plan targets, mixed objective
wording, unspecified/unsupported units or fractional minutes require manual
interpretation; a first component is never compared as the whole duration.
Only simple scalar/coordinated clauses are accepted; unrecognized trailing
modifiers (for example, “or more” or “rounded”) stay unresolved.
Achievement qualifiers are bound to each metric clause; an unmeasured RPO cannot
inherit another clause’s achieved RTO. Completed-exercise phrases and explicit
excluded/untested/incomplete statements are candidates, never proof that excluded
dependencies were covered. Default synthetic example policy: test within 365 days,
RTO ≤240 minutes and RPO ≤60 minutes. The typed thresholds can vary in backend
regressions; this change adds no policy editor or claim of organizational approval.

Candidate extraction is capped per source/requirement at 2,000 lines, 2,000
characters per line and 128 facts/context citations. Exhaustion is disclosed as
incomplete extraction, removes that source from hypothetical evaluation, and
retains full original text/bytes for manual review. These budgets are in addition
to existing upload/parser limits, not malware scanning or production custody.

## Review, export and validation

Evaluate shows requirement/threshold, compact candidate comparisons, uncertainty
and one next action. One expander reveals deduplicated quotes and source-stated
versus declared metadata. Draft Accept/Challenge/Request Evidence/Create Finding
remain annotations; they do not confirm candidate facts. Individual semantic
confirmation remains a separate existing control-assurance service boundary,
not a new confirmation/approval form in this customer slice.

Reclassification, scope/date changes, changed originals or threshold changes
regenerate the candidate context, stale prior annotations/completion, and preserve
historical citations/findings. Challenge invalidates completion but does not
silently edit the original fact or promote any other interpretation. ZIP export
retains exact original uploaded bytes, hashes/manifest, unconfirmed candidates,
open findings, provisional risk and pending vendor decision in JSON/escaped HTML.

Regressions include independently authored synthetic TLS and DR texts (including
Cedarline-style acceptance examples), real PDF/DOCX/TXT parsing/citations/ZIPs,
healthy-primary plus weak-alternate, disabled/negated/ambiguous/conflicting TLS,
stricter thresholds, stale/out-of-scope/type/date mismatches, DR exceeded/within
objectives, exclusions, policy-only/ambiguous units, reclassification/challenge,
no unbounded reparsing and actual-app upload/review/export/reevaluation. No real
vendor corpus, external AI, estimated accuracy or time-savings claims are used.
Owner hands-on acceptance and separate merge authorization remain required.
