# M3B evidence-to-fact validation

This is a small backend proof for `PAM-01.MFA`. It reuses the M1 PDF/DOCX/TXT
parser and unchanged M3A evaluator. It adds no UI, persistence, AI calls, scoring,
control approval or governed-risk updates. Every result remains provisional and
requires independent analyst review. It does not approve the parent `PAM-01`.

## Validation boundary

`src/evidence_fact_validation.py` exposes `validate_and_evaluate_mfa`:

1. Supply `EvidenceInput` records containing original bytes and a declared source
   inventory: unique document ID, version, origin, capture date, observation date,
   service, environment, administrator population and evidence kind. The existing
   parser supplies real locations. Segment IDs use document ID plus ordinal, so
   duplicate filenames do not alias sources.
2. Bind each `ProposedFact` to the complete source fingerprint, parser location
   and exact quotation. The fingerprint includes original-byte SHA-256, parsed
   content and all inventory metadata. Source scope/date/kind must match the
   proposal and customer requirement; stale, future, missing or mismatched
   metadata requires review.
3. A matching quotation establishes **citation integrity only**. No automatic
   semantic inference is attempted. Every proposal needs a separate `FactReview`
   with an authorized analyst's identity, date, rationale, disposition and
   classification. Its fingerprint covers every fact property, including method,
   origin/verifier binding, multiple factors, active path, scope and uncertainty.
   Unsupported and ambiguous proposals remain visible and do not reach M3A.
4. Classifications distinguish policy assertions, implementation evidence,
   operating tests, explicit exceptions, conflicting statements and unsupported
   interpretations. Classification cannot upgrade a policy into configuration or
   tests. Analyst-identified conflicts and exceptions block a positive result even
   if their proposed value is positive or the lexical scan finds nothing.
5. Review the **whole supplied bundle**, including uncited documents. A
   `BundleReview` binds the exact document/proposal inventory, requirement and
   customer policy version, evaluation date and validator version. Adding or
   changing a document or fact invalidates it. Each lexical exception signal
   needs an explicit bundle-bound material/nonmaterial disposition with a reason.
   Material and unresolved signals remain visible and prevent a positive result.
6. Only reviewed, mechanically valid facts reach M3A. M3A still distinguishes
   policy intent, unknown methods, operating tests, active weak paths and opposed
   facts. Its existing method thresholds apply; FIDO2/MFA text alone establishes
   none of phishing resistance, full administrator coverage, enforcement or safe
   recovery. The wrapper suppresses `Met`/`Partially Met` when validation issues
   remain. Missing/uncertain evidence does not become a confirmed control failure.

The wrapper returns all sources, rejected/unreviewed proposals, exact citations,
classifications, exception signals, follow-up reasons and the provisional M3A
evaluation. The existing M1/M2/M3A entrypoints remain compatible; callers choosing
this gate must call the wrapper. There is no automatic application integration.

For an executable usage example, see `strong_package`, `semantic_reviews` and
`bundle_acknowledgment` in `tests/test_evidence_fact_validation.py`. These helpers
simulate explicit analyst input; production callers must obtain actual authorized
review, rather than generate dispositions from the extraction itself.

## Synthetic regression results

`tests/fixtures/m3b_scenarios.json` contains 12 manually authored English scenarios
with 31 documents. Expectations and material-exception locations were authored
separately from the validator. Cases cover a fully evidenced FIDO2 deployment,
active SMS and TOTP, unknown methods, optional FIDO2 branding, omitted emergency
bypasses, contradictory documents, historical tests, similarly named services,
unsafe recovery, sampled administrator testing and policy/assertion-only evidence.

| Measure | Result | Meaning |
| --- | --- | --- |
| Unreviewed overclaim packages yielding `Met` | 0 / 12 | All exact-quote overclaims remain in review; zero proposed facts accepted |
| Incorrect reviewed positive assurance recommendations | 0 / 11 negative scenarios | Positive means provisional requirement-level `Met` |
| Missed enumerated material exceptions | 0 / 5 | Required source ID/location surfaced as a specific retained signal, including uncited runbooks |
| Reviewed strong positive controls retained | 1 / 1 | Avoids claiming success by rejecting every package |
| Reviewed strong facts retained | 7 / 7 | All required M3A dimensions survive the gate |
| Nonmaterial lexical signals requiring analyst triage | 8 | Conservative scan also flags negated/no-exception statements |

Six material source-location signals cover the five distinct exceptions: a second
SMS configuration statement corroborates the same active-method exception. It is
classified as material and excluded from the nonmaterial/noise count.

The reviewed measurements include manually supplied semantic dispositions and
signal triage. They measure the gate/evaluator behavior under those dispositions,
not automated semantic correctness. The unreviewed measurement demonstrates a
mandatory human gate, not extraction accuracy or time savings.

A separate blind-spot regression uses “The emergency route grants access after a
single secret.” The lexical scan misses this **1 / 1 deliberately adversarial
wording**. It remains blocked by absent bundle review; an analyst must recognize
the meaning. This case is outside the five enumerated marker-bearing exceptions
and is explicitly not included in the zero-miss denominator.

Reproduce the scenario report without network/AI or a persistent database:

```bash
DATABASE_URL=sqlite:///:memory: python -m pytest -q tests/test_evidence_fact_scenarios.py
DATABASE_URL=sqlite:///:memory: python -m pytest -q
python -m py_compile app.py src/evidence_fact_validation.py \
  tests/test_evidence_fact_validation.py tests/test_evidence_fact_scenarios.py
git diff --check
```

## Limits and acceptance criteria

This small synthetic corpus cannot estimate real-vendor accuracy, recall,
precision, analyst effort or production performance. It has one reviewed positive
case and a narrow English MFA vocabulary; lexical signals are noisy and miss
euphemisms, other languages and some contradictions. Full bundle review is
mandatory precisely because scanning is not document understanding. No OCR or
generic extraction engine is added; inherited parser limitations still apply.

Hashes establish supplied-content consistency, **not vendor/auditor authenticity,
chain of custody or truth of declared metadata**. Caller authorization and analyst
identity are trusted inputs to this pure backend API, not authenticated here.
An incorrect analyst disposition can still yield an incorrect recommendation.
Only supplied documents can be reviewed; missing documents are not discovered.
No real confidential vendor documents or live AI calls were used.

Independent review should confirm:

- Exact source/version/location/provenance bindings and all-field review replay
  protection hold; duplicate identities fail closed.
- Exact quotes alone cannot establish a semantic fact, policy assertions cannot
  become implementation/tests, and method branding cannot imply missing properties.
- Uncited exceptions, conflicts, stale evidence and scope mismatches stay visible
  and prevent positive assurance; scanner limitations are reported honestly.
- The reviewed positive control and separately enumerated adverse cases pass;
  the full pytest suite and application/module compilation succeed.
- M3A compatibility is preserved and no database/authentication, authoritative
  scoring, control approval, or governed-risk write path was introduced.

Stop at a draft pull request for independent GitHub review; do not merge.
