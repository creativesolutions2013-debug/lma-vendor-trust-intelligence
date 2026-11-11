# M5C 1.2 candidate rubric: qualified meaning before numeric comparison

**Status: candidate_not_active.** This is a separately invoked diagnostic based
on the two owner-accepted narrative qualifications. It is not an adopted corpus,
independent human TPRM validation, external blind study or extractor improvement.
The application and frozen v1.1 corpus remain unchanged. The v1.1 default report
and historical results remain reproducible; candidate artifacts have a separate
name and schema.

## Executable rubric

The candidate reads the frozen corpus and inactive correction proposal, checks
parent/source hashes and constructs a temporary in-memory copy. All sources and
15 other cases remain unchanged. In `dr-failover-narrative`, only completed=True
is exact typed gold. Literal switch duration=300 minutes and data-loss bound <=90
are preserved as qualified source assertions; neither is an exact achieved RTO/RPO
without the accepted semantic clarification.

| Layer | Candidate treatment |
| --- | --- |
| Exact typed facts | Match dimension/value/subject/quote using the existing provenance-checked scorer; do not match either qualified narrative value as an exact achieved metric |
| Technical exception triage | Seven cases retain a current technical-exception expectation; report eligible adverse comparisons separately |
| Manual interpretation | One narrative case requires clarification, not an eligible exact-metric adverse comparison; retain its source and smallest follow-up |
| Non-exception / abstain | Two no-exception cases and six out-of-scope/stale/qualified cases; report eligible adverse overclaims |
| Qualified-metric safety | Record any exact achieved-metric proposal on the narrative source, including ineligible proposals; separately report eligible adverse metric overclaims |
| Targeted manual signal | **Not instrumented / null**; source visibility, completion facts and generic Needs Review are not credited as targeted signal recall |

Accuracy/abstention observations remain descriptive, not pass targets. Exact
source/fingerprint/citation and unconfirmed/unauthorized-outcome guards remain
hard checks in the reused scorer. The narrow operator tests inject exact 300/90
predictions to verify that the candidate records them as unsupported point
interpretations rather than converting them into matches.

Run independently:

```bash
python -m py_compile app.py tests/test_m5c_benchmark.py tests/test_m5c_candidate_benchmark.py
M5C_CANDIDATE_REPORT_PATH=/tmp/m5c-candidate.json python -m pytest -q -s tests/test_m5c_candidate_benchmark.py
```

The existing v1.1 command and `M5C_REPORT_PATH` retain their original meaning.
CI runs both, publishing `m5c-baseline` and a separate
`m5c-candidate-not-active` artifact. Running the candidate in tests does not make
it the adopted baseline or load its annotations into the application.

## First diagnostic result with unchanged extraction

The candidate has 16 cases and 27 exact gold facts: 22 matched, five missed, no
extra typed predictions in this sample. Three of seven technical exception cases
surface. Four remain missed: port prose, gateway narrative, untested identity
federation and the compound 270-minute RTO. The narrative case is a separate
manual-interpretation expectation; targeted manual-signal success is unmeasured.
No eligible adverse metric overclaim occurred on that source. No eligible adverse
overclaims occurred in the two no-exception or six abstain cases in this sample.

These are **changed annotations and denominators**, not improved extraction or
new field-accuracy evidence. Do not compare 22/27 or 3/7 with historical v1.1's
22/29 or 3/8 as a model gain, or combine the two rubric versions in one rate.
The narrative concern remains unresolved; moving it into its own category does
not mean it was fixed, harmless or successfully surfaced.

## Remaining work

The current candidate rubric needs broader human TPRM review before adoption.
Human effort, generic-question reduction and external holdout validation remain
unmeasured. A separately specified, source-cited targeted-signal contract and
independent development corpus are needed before signal implementation can be
justified under Issue #28. No parser, confirmation, risk, authentication or
vendor-decision changes are included. PR #29 remains draft; merge is separate.
