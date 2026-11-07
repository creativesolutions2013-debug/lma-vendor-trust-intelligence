# M5C independent TPRM gold-review packet

**Status: pending human TPRM review.** This packet prepares the prerequisite in Issue #28; it is not a completed independent review or permission to change extraction rules.

Corpus: `M5C-holdout-1.1` · SHA-256 of original JSON bytes: `19b82edbbf93ff2baf975abe4f00307a8b37cf160c62dd3d8eebfb8a9c3607d9`.
Assessment date: `2026-11-01`. 16 synthetic cases: 8 proposed exception, 2 no-exception, 6 abstain.

The corpus and annotations are unchanged. The source author knew product interfaces; this is not an external blind corpus. This packet exposes existing gold labels for expert validation, so it must not be reused as a fresh blind test. Do not consult extractor output until recording the initial review. Human truth labels must follow source meaning and thresholds, not supported parser syntax.

## Review procedure

1. Record reviewer name/role, date, relevant TLS/DR assurance experience, and involvement in writing rules or corpus. Disclose conflicts; an automated code review is not a substitute for TPRM validation.
2. Read each source and the fixed assessment context. Independently judge current scope, date, source type, achieved versus target values, units and qualifications. Decide exception / no_exception / abstain and the smallest justified follow-up.
3. Review the proposed typed facts below. For each fact, verify dimension/value/subject and quote span against the rendered source location. Mark agree, revise or unresolved; explain differences with an exact quote. Missing evidence alone is not a failed control.
4. Freeze the reviewer response with its own version/hash before consulting the baseline output. Reconcile disagreements separately; do not silently rewrite this frozen holdout or tune rules against it. A justified gold correction requires a new corpus version and an explicitly superseded baseline.
5. Only after human validation, decide whether a separate development corpus and a bounded targeted manual-review signal are justified. Such a signal cannot establish eligible technical facts, control failure or approval by itself.

## Common assessment context

```json
{
  "vendor": "Orion Synthetic Services",
  "service": "Orion Ledger Gateway",
  "environment": "production",
  "as_of": "2026-11-01",
  "tls_minimum": "1.2",
  "dr_max_rto_minutes": 240,
  "dr_max_rpo_minutes": 60,
  "dr_max_test_age_days": 365
}
```

For every case: reviewer verdict = **pending**; revised facts = **unreviewed**; smallest next action = **not yet supplied**. Original JSON is the source of truth. TXT locations are Line N; generated DOCX locations are Paragraph N, one paragraph per source line; generated PDFs put these source lines on Page 1. Display line numbers below are an aid, not PDF line citations. Verify actual artifacts using the existing benchmark renderer if needed.

## tls-alt-backdoor · ENC-01 · TXT

Uploader declarations: kind `configuration`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | TLS configuration report
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Observation date: 2026-10-18
05 | Primary endpoint 443: TLS 1.3 is enabled.
06 | Alternate production endpoint 9443: TLS 1.1 is enabled.
```

Proposed gold triage: `exception`. Existing annotation: Weak alternate TLS listener despite strong primary.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "enabled_version",
    "value": 13,
    "subject": "endpoint 443",
    "phrase": "TLS 1.3"
  },
  {
    "dimension": "enabled_version",
    "value": 11,
    "subject": "endpoint 9443",
    "phrase": "TLS 1.1"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## tls-rejected-legacy · ENC-01 · PDF

Uploader declarations: kind `configuration`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Configuration export
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Observation date: 2026-10-18
05 | Listener edge443: TLS 1.0 is disabled.
06 | Listener edge443: TLS 1.2 is enabled.
```

Proposed gold triage: `no_exception`. Existing annotation: Disabled legacy does not establish failure or full coverage.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "disabled_version",
    "value": 10,
    "subject": "listener edge443",
    "phrase": "TLS 1.0"
  },
  {
    "dimension": "enabled_version",
    "value": 12,
    "subject": "listener edge443",
    "phrase": "TLS 1.2"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## tls-port-prose · ENC-01 · DOCX

Uploader declarations: kind `configuration`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Configuration export
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Observation date: 2026-10-18
05 | Traffic on port 8443 still accepts TLS 1.0 connections.
```

Proposed gold triage: `exception`. Existing annotation: Clear human-read protocol exception in unfamiliar port phrasing; count as missed if no eligible comparison.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "enabled_version",
    "value": 10,
    "subject": "port 8443",
    "phrase": "TLS 1.0"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## tls-conditional · ENC-01 · TXT

Uploader declarations: kind `configuration`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Configuration export
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Observation date: 2026-10-18
05 | Listener 443: TLS 1.0 may be enabled during fallback.
```

Proposed gold triage: `abstain`. Existing annotation: Conditional fallback statement is not current operating proof.

Proposed typed gold (not confirmed vendor facts):

```json
[]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## tls-old-record · ENC-01 · TXT

Uploader declarations: kind `configuration`, service `Orion Ledger Gateway`, environment `production`, observed `2025-01-10`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Configuration export
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Observation date: 2025-01-10
05 | Listener 443: TLS 1.0 is enabled.
```

Proposed gold triage: `abstain`. Existing annotation: Stale configuration cannot prove current production failure.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "enabled_version",
    "value": 10,
    "subject": "listener 443",
    "phrase": "TLS 1.0"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## tls-test-only · ENC-01 · PDF

Uploader declarations: kind `configuration`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Configuration export
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Observation date: 2026-10-18
05 | Test endpoint 7001: TLS 1.0 is enabled.
```

Proposed gold triage: `abstain`. Existing annotation: Test-only listener should not be compared as production.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "enabled_version",
    "value": 10,
    "subject": "endpoint 7001",
    "phrase": "TLS 1.0"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## tls-gateway-caption · ENC-01 · TXT

Uploader declarations: kind `configuration`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Configuration export
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Observation date: 2026-10-18
05 | Client sessions on legacy gateway port 9443 accept TLS 1.0.
```

Proposed gold triage: `exception`. Existing annotation: Alternate material endpoint written as network narrative.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "enabled_version",
    "value": 10,
    "subject": "gateway port 9443",
    "phrase": "TLS 1.0"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## tls-mixed-enabled · ENC-01 · DOCX

Uploader declarations: kind `configuration`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Configuration export
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Observation date: 2026-10-18
05 | Listener 443: TLS 1.0 and TLS 1.3 are enabled.
```

Proposed gold triage: `exception`. Existing annotation: Healthy and weak protocols coexist on same listener.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "enabled_version",
    "value": 10,
    "subject": "listener 443",
    "phrase": "TLS 1.0"
  },
  {
    "dimension": "enabled_version",
    "value": 13,
    "subject": "listener 443",
    "phrase": "TLS 1.3"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## dr-breached-objectives · BCP-01 · TXT

Uploader declarations: kind `test`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Disaster recovery test report
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Test date: 2026-10-18
05 | Recovery exercise completed.
06 | Observed RTO 6 hours and RPO 2 hours.
07 | The exercise excluded message broker failover.
```

Proposed gold triage: `exception`. Existing annotation: Measured overrun and incomplete service scope.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "completed",
    "value": true,
    "subject": "exercise for orion ledger gateway",
    "phrase": "Recovery exercise completed"
  },
  {
    "dimension": "achieved_rto_minutes",
    "value": 360,
    "subject": "exercise for orion ledger gateway",
    "phrase": "RTO 6 hours"
  },
  {
    "dimension": "achieved_rpo_minutes",
    "value": 120,
    "subject": "exercise for orion ledger gateway",
    "phrase": "RPO 2 hours"
  },
  {
    "dimension": "scope_complete",
    "value": false,
    "subject": "exercise for orion ledger gateway",
    "phrase": "excluded message broker"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## dr-plan-only · BCP-01 · DOCX

Uploader declarations: kind `policy`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Recovery plan objectives
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Test date: 2026-10-18
05 | Target RTO 60 minutes. Target RPO 15 minutes.
06 | Exercises are scheduled for next quarter.
```

Proposed gold triage: `abstain`. Existing annotation: Policy intent is not achieved recovery evidence.

Proposed typed gold (not confirmed vendor facts):

```json
[]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## dr-failover-narrative · BCP-01 · TXT

Uploader declarations: kind `test`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | Disaster recovery exercise results
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Test date: 2026-10-18
05 | Recovery exercise completed.
06 | Switching the service took five hours, with up to ninety minutes of data loss.
```

Proposed gold triage: `exception`. Existing annotation: Human-readable RTO/RPO equivalents without formal acronyms; likely outside supported grammar.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "achieved_rto_minutes",
    "value": 300,
    "subject": "exercise for orion ledger gateway",
    "phrase": "five hours"
  },
  {
    "dimension": "achieved_rpo_minutes",
    "value": 90,
    "subject": "exercise for orion ledger gateway",
    "phrase": "ninety minutes"
  },
  {
    "dimension": "completed",
    "value": true,
    "subject": "exercise for orion ledger gateway",
    "phrase": "completed"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## dr-compliant-sample · BCP-01 · PDF

Uploader declarations: kind `test`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | DR exercise results
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Test date: 2026-10-18
05 | Recovery exercise completed.
06 | Achieved RTO 90 minutes and RPO 15 minutes.
```

Proposed gold triage: `no_exception`. Existing annotation: Within example objectives but coverage remains unproven.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "completed",
    "value": true,
    "subject": "exercise for orion ledger gateway",
    "phrase": "completed"
  },
  {
    "dimension": "achieved_rto_minutes",
    "value": 90,
    "subject": "exercise for orion ledger gateway",
    "phrase": "RTO 90"
  },
  {
    "dimension": "achieved_rpo_minutes",
    "value": 15,
    "subject": "exercise for orion ledger gateway",
    "phrase": "RPO 15"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## dr-uncovered-idp · BCP-01 · TXT

Uploader declarations: kind `test`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | DR test results
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Test date: 2026-10-18
05 | Recovery exercise completed.
06 | Identity federation was not tested in this exercise.
```

Proposed gold triage: `exception`. Existing annotation: Identity dependency untested; material scope limitation.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "scope_complete",
    "value": false,
    "subject": "exercise for orion ledger gateway",
    "phrase": "not tested"
  },
  {
    "dimension": "completed",
    "value": true,
    "subject": "exercise for orion ledger gateway",
    "phrase": "completed"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## dr-compound-duration · BCP-01 · DOCX

Uploader declarations: kind `test`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | DR exercise report
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Test date: 2026-10-18
05 | Recovery exercise completed.
06 | Measured RTO 4 hours 30 minutes.
```

Proposed gold triage: `exception`. Existing annotation: Human-read achieved RTO 4 hours 30 minutes = 270 minutes exceeds the 240-minute threshold; supported/unsupported parser grammar must not change the gold label. Missing this material case is counted, while fact approval remains manual.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "achieved_rto_minutes",
    "value": 270,
    "subject": "exercise for orion ledger gateway",
    "phrase": "4 hours 30 minutes"
  },
  {
    "dimension": "completed",
    "value": true,
    "subject": "exercise for orion ledger gateway",
    "phrase": "completed"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## dr-unrelated-service · BCP-01 · TXT

Uploader declarations: kind `test`, service `Orion Data Warehouse`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | DR exercise results
02 | Service: Orion Data Warehouse
03 | Environment: production
04 | Test date: 2026-10-18
05 | Recovery exercise completed.
06 | Achieved RTO 300 minutes and RPO 90 minutes.
```

Proposed gold triage: `abstain`. Existing annotation: Evidence belongs to different assessed service.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "achieved_rto_minutes",
    "value": 300,
    "subject": "exercise for orion data warehouse",
    "phrase": "RTO 300"
  },
  {
    "dimension": "completed",
    "value": true,
    "subject": "exercise for orion data warehouse",
    "phrase": "completed"
  },
  {
    "dimension": "achieved_rpo_minutes",
    "value": 90,
    "subject": "exercise for orion data warehouse",
    "phrase": "RPO 90"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## dr-year-qualified · BCP-01 · TXT

Uploader declarations: kind `test`, service `Orion Ledger Gateway`, environment `production`, observed `2026-10-18`.

Exact source text (display line numbers are not part of the original bytes):

```text
01 | DR exercise results
02 | Service: Orion Ledger Gateway
03 | Environment: production
04 | Test date: 2026-10-18
05 | Recovery exercise completed.
06 | Achieved RTO 300 minutes in 2024.
```

Proposed gold triage: `abstain`. Existing annotation: Historical result cannot be relabeled with a current report date.

Proposed typed gold (not confirmed vendor facts):

```json
[
  {
    "dimension": "achieved_rto_minutes",
    "value": 300,
    "subject": "exercise for orion ledger gateway",
    "phrase": "RTO 300"
  },
  {
    "dimension": "completed",
    "value": true,
    "subject": "exercise for orion ledger gateway",
    "phrase": "completed"
  }
]
```

Reviewer response: **pending**. Record verdict, exact decisive quote/location, any fact correction, scope/date/type uncertainty and smallest follow-up.

## AI-assisted review supplement

An [AI-assisted source review](M5C_AI_Assisted_Gold_Review.md) now records
15 agreements and one proposed gold-fact qualification, with exact citations.
It is not independent human TPRM validation, does not change this frozen corpus
and does not authorize parser changes. The owner has since accepted the two qualifications for the narrative case;
see the [scoped decision and versioned proposal](M5C_Gold_Qualification_Decision.md).
Broader human TPRM validation remains pending. No active gold revision or rescoring
has occurred.
