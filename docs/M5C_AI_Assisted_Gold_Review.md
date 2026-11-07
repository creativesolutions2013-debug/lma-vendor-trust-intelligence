# M5C AI-assisted source and gold review

**Status: proposed review, awaiting human confirmation.** This is not the independent human TPRM validation required by Issue #28. The same assistant has implementation and prior benchmark exposure; it is neither blind nor external.

Reviewed all 16 cases in `M5C-holdout-1.1` at the frozen assessment date `2026-11-01`. Corpus SHA-256: `19b82edbbf93ff2baf975abe4f00307a8b37cf160c62dd3d8eebfb8a9c3607d9`.

## Principal finding

**15 cases agree; 1 case needs a gold-fact qualification.** Existing provisional triage labels are retained as recommendations (8 exception, 2 no_exception, 6 abstain), not independently validated or rescored labels. In `dr-failover-narrative`, “up to ninety minutes of data loss” is an upper bound, not exact achieved RPO=90. The statement alone does not establish a breach of the 60-minute threshold. Five hours equals 300 elapsed minutes; interpreting service-switch time as formal RTO also requires confirming start/stop and recovery-acceptance definitions. Completion itself is explicit. A targeted review concern remains justified; do not silently convert either phrase to a confirmed numeric failure.

Frozen corpus, gold, scoring and extraction rules remain unchanged. No revised benchmark rate is published: any accepted annotation revision needs human review, a new version and a rerun. Previous baseline rates describe only v1.1 and must not be relabelled as validated accuracy after this review.

## Threshold and provenance checks

- Example customer criteria: enabled TLS minimum 1.2; achieved RTO <=240 minutes; achieved RPO <=60 minutes; completed full-service DR test within 365 days. TLS freshness uses the existing pilot 90-day requirement. These are synthetic example criteria, not a customer-approved policy.
- Current source date 2026-10-18 is 14 days old at the frozen assessment date. TLS 2025-01-10 is stale. A 2024 DR measurement is outside 365 days even when a report header says 2026.
- Document-wide production/service labels cannot erase line-specific test scope, a different service, historical years or conditional language. No full endpoint/dependency coverage is inferred from silence.
- Locations below are checked against existing rendered TXT/PDF/DOCX sources. PDF display lines are navigation aids within Page 1, not invented PDF line citations. Source wording remains unverified vendor assertions; no fact/control/vendor/risk approval is created.

## Per-case review

### tls-alt-backdoor — agree

Recommended provisional triage: `exception` (existing label `exception`).

Line 6 · display line 6:

```text
Alternate production endpoint 9443: TLS 1.1 is enabled.
```

TLS 1.1 < 1.2 on the alternate production endpoint. TLS 1.3 on the primary does not offset that statement.

**Gold facts:** The two enabled-version gold facts and endpoint subjects are supported as unconfirmed source assertions. Neither proves fleet coverage.

**Smallest follow-up:** Request dated configuration and a protocol-rejection scan for endpoint 9443; investigate the reported below-minimum listener.

### tls-rejected-legacy — agree

Recommended provisional triage: `no_exception` (existing label `no_exception`).

Page 1 · display line 5:

```text
Listener edge443: TLS 1.0 is disabled.
```

Page 1 · display line 6:

```text
Listener edge443: TLS 1.2 is enabled.
```

No adverse statement in this excerpt: TLS 1.0 is disabled and TLS 1.2 enabled on edge443.

**Gold facts:** Both local protocol-state facts are supported. Do not infer that TLS 1.1 is rejected, that 1.2 is the only enabled version, or that all endpoints were scanned.

**Smallest follow-up:** Request missing legacy-version rejection and endpoint coverage evidence only; do not create a failure finding from absent proof.

### tls-port-prose — agree

Recommended provisional triage: `exception` (existing label `exception`).

Paragraph 5 · display line 5:

```text
Traffic on port 8443 still accepts TLS 1.0 connections.
```

Accepting TLS 1.0 connections on port 8443 is a material below-minimum source assertion despite unfamiliar syntax.

**Gold facts:** enabled_version=10 with subject port 8443 is a defensible unconfirmed candidate. The verb accepts supplies activation meaning here, not mere product support.

**Smallest follow-up:** Request a dated handshake scan and configuration for port 8443; target this port rather than resending a generic encryption questionnaire.

### tls-conditional — agree

Recommended provisional triage: `abstain` (existing label `abstain`).

Line 5 · display line 5:

```text
Listener 443: TLS 1.0 may be enabled during fallback.
```

May be enabled during fallback does not establish current activation; it does raise a fallback-path question.

**Gold facts:** No unconditional enabled-version gold fact is justified. Retain the whole conditional statement as uncertainty, not harmlessness or a confirmed failure.

**Smallest follow-up:** Ask whether production fallback can activate TLS 1.0 and request its guard/configuration and a fallback test if applicable.

### tls-old-record — agree

Recommended provisional triage: `abstain` (existing label `abstain`).

Line 4 · display line 4:

```text
Observation date: 2025-01-10
```

Line 5 · display line 5:

```text
Listener 443: TLS 1.0 is enabled.
```

The 2025-01-10 record is outside the pilot TLS freshness window at 2026-11-01. Preserve the adverse historical assertion without calling it a current exception.

**Gold facts:** enabled_version=10/listener 443 is supported only with the historical source date. The bare triple must not be treated as current production proof.

**Smallest follow-up:** Request current dated listener configuration or a rejection scan and any evidence of remediation since this record.

### tls-test-only — agree

Recommended provisional triage: `abstain` (existing label `abstain`).

Page 1 · display line 3:

```text
Environment: production
```

Page 1 · display line 5:

```text
Test endpoint 7001: TLS 1.0 is enabled.
```

The line-specific test endpoint overrides the document-wide production header for this observation; current production comparison must abstain.

**Gold facts:** enabled_version=10/endpoint 7001 is supported as a test-scoped assertion only. Retain the header-versus-line scope discrepancy.

**Smallest follow-up:** Confirm whether endpoint 7001 is isolated test infrastructure; request production endpoint evidence rather than assuming this is a production failure.

### tls-gateway-caption — agree

Recommended provisional triage: `exception` (existing label `exception`).

Line 5 · display line 5:

```text
Client sessions on legacy gateway port 9443 accept TLS 1.0.
```

Client sessions accepting TLS 1.0 on gateway port 9443 warrant a provisional below-minimum concern.

**Gold facts:** enabled_version=10/gateway port 9443 is supported as an unconfirmed candidate. Gateway identity and service mapping still require verification.

**Smallest follow-up:** Request the gateway port 9443 configuration and a dated handshake/rejection scan for that endpoint.

### tls-mixed-enabled — agree

Recommended provisional triage: `exception` (existing label `exception`).

Paragraph 5 · display line 5:

```text
Listener 443: TLS 1.0 and TLS 1.3 are enabled.
```

TLS 1.0 and 1.3 coexist on listener 443; the strong protocol does not eliminate the weak enabled protocol.

**Gold facts:** Both gold enabled-version observations are supported for the same listener. Different enabled versions are not inherently conflicting observations.

**Smallest follow-up:** Investigate removal of TLS 1.0 on listener 443 and request a dated scan confirming rejected legacy handshakes.

### dr-breached-objectives — agree

Recommended provisional triage: `exception` (existing label `exception`).

Line 5 · display line 5:

```text
Recovery exercise completed.
```

Line 6 · display line 6:

```text
Observed RTO 6 hours and RPO 2 hours.
```

Line 7 · display line 7:

```text
The exercise excluded message broker failover.
```

Six hours = 360 minutes > 240; two hours = 120 minutes > 60. The explicit exercise exclusion also contradicts full-service testing.

**Gold facts:** All four gold candidates are supported: completed=True, achieved RTO=360, achieved RPO=120 and scope_complete=False. Observed wording ties the measurements to the test; all remain unconfirmed.

**Smallest follow-up:** Request the executed exercise record and corrective retest covering message-broker failover and the exceeded recovery objectives.

### dr-plan-only — agree

Recommended provisional triage: `abstain` (existing label `abstain`).

Paragraph 1 · display line 1:

```text
Recovery plan objectives
```

Paragraph 5 · display line 5:

```text
Target RTO 60 minutes. Target RPO 15 minutes.
```

Paragraph 6 · display line 6:

```text
Exercises are scheduled for next quarter.
```

Target values and future scheduled exercises are planning intent, not achieved operating results.

**Gold facts:** An empty achieved-fact gold list is appropriate. Do not infer completed=True or actual recovery objectives from plan targets, even though the source labels a Test date.

**Smallest follow-up:** Request the latest completed exercise record with actual achieved timings, recovery point, scope and execution date.

### dr-failover-narrative — revise

Recommended provisional triage: `exception` (existing label `exception`).

Line 5 · display line 5:

```text
Recovery exercise completed.
```

Line 6 · display line 6:

```text
Switching the service took five hours, with up to ninety minutes of data loss.
```

Retain provisional exception/targeted-review attention for the reported five-hour service switch. Do not claim an exact RPO breach from an upper bound; formal RTO measurement semantics also need confirmation.

**Gold facts:** completed=True is supported. Five hours converts to 300 elapsed minutes, but whether switching duration is the defined achieved RTO is not established. Up to ninety minutes denotes <=90, not exact achieved RPO=90; it proves neither >60 nor <=60. Propose qualifying the RTO mapping and replacing the exact RPO gold with an unresolved upper-bound assertion in a separately approved gold version. Do not alter v1.1 now.

**Smallest follow-up:** Request the failover start/service-restoration acceptance timestamps and actual recovered data-point timestamps; clarify whether the ninety-minute phrase is an observed maximum or a hypothetical bound.

### dr-compliant-sample — agree

Recommended provisional triage: `no_exception` (existing label `no_exception`).

Page 1 · display line 5:

```text
Recovery exercise completed.
```

Page 1 · display line 6:

```text
Achieved RTO 90 minutes and RPO 15 minutes.
```

The reported achieved 90-minute RTO and 15-minute RPO are within the example limits, but full-service coverage is not established.

**Gold facts:** All three gold facts are supported as unconfirmed results. No scope_complete=True fact is justified, and no whole-control Met follows.

**Smallest follow-up:** Request only the missing dependency/coverage record and verify that completion and both measurements belong to the same exercise.

### dr-uncovered-idp — agree

Recommended provisional triage: `exception` (existing label `exception`).

Line 5 · display line 5:

```text
Recovery exercise completed.
```

Line 6 · display line 6:

```text
Identity federation was not tested in this exercise.
```

Not testing identity federation is an explicit exercise scope limitation, warranting review against full-service recovery requirements.

**Gold facts:** completed=True and scope_complete=False are supported as provisional candidates. Confirm that identity federation is a required recovery dependency; the excerpt does not prove the dependency failed.

**Smallest follow-up:** Confirm the identity dependency map and request an identity-federation-inclusive exercise result or a justified scope exception for human review.

### dr-compound-duration — agree

Recommended provisional triage: `exception` (existing label `exception`).

Paragraph 5 · display line 5:

```text
Recovery exercise completed.
```

Paragraph 6 · display line 6:

```text
Measured RTO 4 hours 30 minutes.
```

Four hours thirty minutes = 270 minutes, exceeding 240 by 30 minutes. Unsupported parser grammar does not make this an abstention in human gold.

**Gold facts:** Both completed=True and achieved_rto_minutes=270 are supported as unconfirmed measured exercise results. RPO and full-service scope are absent, not passing or failed.

**Smallest follow-up:** Request the executed timing record and corrective RTO retest; ask for missing RPO/coverage evidence only if not already in that record.

### dr-unrelated-service — agree

Recommended provisional triage: `abstain` (existing label `abstain`).

Line 2 · display line 2:

```text
Service: Orion Data Warehouse
```

Line 5 · display line 5:

```text
Recovery exercise completed.
```

Line 6 · display line 6:

```text
Achieved RTO 300 minutes and RPO 90 minutes.
```

The results concern Orion Data Warehouse, not the assessed Orion Ledger Gateway. They cannot become Gateway exceptions or coverage proof.

**Gold facts:** All three result triples are supported for the Data Warehouse subject only. Their adverse values must stay bound to that different service.

**Smallest follow-up:** Request the Gateway exercise record; clarify shared-dependency relevance only if a service mapping supports it.

### dr-year-qualified — agree

Recommended provisional triage: `abstain` (existing label `abstain`).

Line 4 · display line 4:

```text
Test date: 2026-10-18
```

Line 5 · display line 5:

```text
Recovery exercise completed.
```

Line 6 · display line 6:

```text
Achieved RTO 300 minutes in 2024.
```

The 2024 result is historical despite the 2026 Test date header. No day in 2024 falls within the 365-day interval at 2026-11-01.

**Gold facts:** The 300-minute result is a historical assertion; retain its 2024 qualification and contradictory source context. Completed=True is a separate source assertion, not proof that this metric belongs to a current completed exercise.

**Smallest follow-up:** Request the current exercise record and reconcile the metric year with the header before relying on the 2026 date.

## Recommendation and remaining gates

**SIMPLIFY:** prepare source-cited targeted manual-review prompts for unsupported material statements only after human validation and a separate development corpus. Do not use this reviewed/exposed holdout to tune syntax, promote unresolved concerns into eligible technical facts or claim broad intelligence.

The five previously reported missed case classes still merit attention, but correctness comes before increasing numeric extraction: port/gateway phrasing, recovery-duration narrative, untested identity dependency and compound duration. The narrative RPO gold needs qualification before anyone treats the typed-fact denominator as a trustworthy human baseline.

All 29 existing gold entries were inspected; this does not assert that the annotated fact list is exhaustive for every control dimension. The current exact-triple/phrase score also cannot validate operator, fact-local environment, historical timing or exercise identity on its own. Retain these in the review rubric rather than treating a matched triple as assurance.

Human TPRM validation remains pending. Observed analyst minutes, clicks, unnecessary questions, field accuracy, external holdout validation and ROI remain unmeasured. No merge or parser change is authorized by this report.

Machine-readable companion: [M5C_AI_Assisted_Gold_Review.json](M5C_AI_Assisted_Gold_Review.json).
