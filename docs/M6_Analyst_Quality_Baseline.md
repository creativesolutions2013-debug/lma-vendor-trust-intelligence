# M6 Phase 1 — Independent analyst-quality measurement baseline

**Status:** Proposed synthetic evaluation infrastructure on a feature branch; not a validated product-quality claim.

## Goal
Measure whether an analyst using LMA finds material concerns with verifiable citations, requests only necessary vendor clarification, and completes a defensible review more efficiently than a comparable manual process. **Decision accuracy and safety take priority over speed.** No change to production evaluators, governance, policies, databases or authentication.

## Materials and independence
- `benchmarks/m6_analyst_scenarios_v1.json`: ten **AI-authored, provisional** synthetic scenario seeds across PAM/MFA, TLS, DR and IR. They are not a fully blinded independent holdout. The named expected concerns and vendor questions are working hypotheses, not approved ground truth.
- `benchmarks/m6_analyst_quality.py`: standalone scoring of explicitly recorded reviewer actions, separate from product code. Each reported concern must cite an **exact source quote** to be marked citation-verifiable. Quote match does not establish interpretation correctness.
- `tests/test_m6_analyst_quality.py`: deterministic input validation, citation, question and abstention checks.
- Frozen M5C benchmark files/scorer are **unchanged**.

## Study protocol, before any efficiency claims
1. Have at least two qualified reviewers **independently** annotate the source evidence before seeing LMA suggestions. Review differences and record an adjudicated reference version in a new file; do not rewrite existing seed expectations to fit LMA outputs.
2. Prepare two similarly difficult, independently reviewed case sets. Counterbalance review order and manual/LMA modes between analysts to reduce case familiarity. Record whether the same scenario was seen twice.
3. For each reviewer/mode/scenario, collect only anonymous reviewer ID, case ID, observed start/finish duration, concern IDs, exact quotes used to support them, question IDs sent or proposed, and reasons for overrides. Record completion time from actual observation, not estimated labor.
4. Keep the manual evidence package and customer requirements available to both modes. LMA mode may show provisional evidence hints but never records authoritative approvals. Do not send actual vendor evidence, secrets or private identities to public CI.
5. Judge true material misses, unsupported assertions, relevance/scope/freshness errors and needless questions **before** comparing speed. Review false or noisy neutral alerts separately.
6. Publish per-case errors, adjudicator disagreement, sample size, coverage gaps and confidence limitations. Report minutes saved or question reduction **only after** matched observed sessions and controlled comparison; scorer intentionally returns `null` for those metrics in Phase 1.

## Observation file
Do not commit real analyst information. An example *structure*, not a completed measurement:

```json
{
  "sessions": [
    {
      "reviewer_id": "anonymous-01",
      "case_id": "tls-weak-secondary",
      "mode": "manual",
      "concern_ids": ["weak-listener"],
      "question_ids": ["tls-remediation"],
      "citations": [{"concern_id": "weak-listener", "quote": "Production backup listener 9443 accepts TLS 1.1."}],
      "elapsed_seconds": null
    }
  ]
}
```

Run locally after human observations are captured:

```bash
python -m py_compile app.py benchmarks/m6_analyst_quality.py tests/test_m6_analyst_quality.py
pytest -q tests/test_m6_analyst_quality.py
python benchmarks/m6_analyst_quality.py --observations /path/to/anonymous-observations.json --output /path/to/private-report.json
```

All Python/pytest checks should also be run in existing SQLite and PostgreSQL CI before acceptance. These scripts are not a replacement for the observed analyst protocol. No automatic scoring of LMA decisions has yet been implemented.

## M6 Phase 1 acceptance
- Scenarios reviewed/adjudicated by independent TPRM reviewers; mark seed annotations provisional until then.
- No unsupported authoritative approvals or source-identity violations.
- All relied-upon quotations verified and all unsupported or misattributed judgments reported, not suppressed.
- Missing evidence not misclassified as failed implementation; policy statements not treated as operating proof.
- Necessary versus unnecessary vendor requests scored per scenario, preserving uncertain facts.
- Actual elapsed time reported only for observed runs; insufficient observations remain `null`.
- Every proposed quality improvement tied to a measured miss, safety issue or user-friction finding.

**Out of scope:** new UI widgets, production parser changes, a generic questionnaire, risk scoring, tenancy/auth, new dashboards, external AI calls and any merge of PR #38.
