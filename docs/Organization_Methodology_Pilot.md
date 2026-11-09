# Organization methodology configuration — synthetic pilot

The New Assessment journey has a ready-to-use, versioned default methodology. Open **Organization methodology** in the sidebar to select/create a **pilot organization**, edit common settings, or export/import the full JSON configuration. The requester still uses the existing five-stage assessment journey.

This configuration is **session memory only**, not production tenant administration, durable storage or an authorization boundary. Export JSON to retain/reuse settings across sessions. Production organization identity, administrator authorization, database persistence and audit retention are not implemented by this feature. No production authentication/database or PR #21 changes are included. Use synthetic/nonconfidential data only.

## Out-of-box scale methodology

The default strategy is `scale_uplift`:

- Active/expected **client users** are people using the vendor product, not vendor administrators or the population represented by records. Observed counts use 30 days; expected rollout counts are explicitly labeled estimates.
- Adoption is Low below 100 users **and** below 10% of the defined workforce; High at 1,000 users **or** 50%; otherwise Moderate. Zero known users is zero adoption. Unknown numerator, or a missing denominator that could change the classification, remains unassessed. A high absolute count already establishes High without claiming a known percentage. A department denominator must not be represented as enterprise-wide adoption.
- Record bands are 0, 1–1,000, 1,001–100,000 and over 100,000 records. Count the maximum service-scope records accessible/processed/stored; storage bytes, movie size and repeatedly counted transactions are not the measure.
- High record volume qualifies only for nonpublic data with material sensitivity. High adoption qualifies only with material business exposure. Default material thresholds are 10 sensitivity points and 15 business points. These are configurable pilot definitions, not industry standards.
- The baseline excludes additive user/volume scale points. One qualifying scale exposure can uplift T4→T3 or T3→T2, provided scale was not already represented in the baseline. Both high adoption and high records still produce **one** adjustment. The overlap answer and explanation are retained.
- T2→T1 requires a declared critical consequence by default; counts alone cannot establish Critical. A critical consequence must have an explanation under the organization methodology. The default critical override can independently require T1 from any baseline, representing reassessment for a critical consequence rather than multiple scale uplifts. This remains a requester declaration, not approval.
- Baseline T1 receives no additional scale increase; scale information remains available for assessment depth and monitoring. Public record volume alone receives no confidentiality uplift. Few users never reduce exposure established by data, critical-system access or dependency.

The alternative `weighted` strategy uses the highest eligible user/record scale contribution, not their sum, and never also applies a scale uplift. Default scale weights are 0/2/5/10. Scale already represented in the baseline is not charged again. The default critical-consequence guard also prevents weighted scale alone establishing T1: the numeric subtotal is preserved while the final tier is capped at T2 until the condition is established. Reports distinguish core baseline score/tier, scored subtotal and final tier; consumers must use the captured tier decision rather than infer the classification from a number alone.

Unknown inputs are explicit null/unassessed values. Unknown critical-consequence or relevant overlap determinations keep results provisional. No method confirms technical evidence, approves vendors or calculates authoritative residual risk.

## What each organization can configure

Common settings have native controls. Full JSON export/import also supports:

| Area | Settings |
| --- | --- |
| Identity | Pilot organization ID, stable methodology version and display name |
| Data | Categories and weights, declared sensitivity weights, nonpublic/regulated category groups |
| Exposure | System/network access weights, criticality and service-dependency weights |
| Scale | Record bands, user counts, workforce percentages, observation days and scale weights |
| Tiering | Four existing tier boundaries/names, weighted versus scale strategy, uplift switches, material-impact thresholds and critical-condition rules |
| Requirements | Default/custom requirement IDs, titles, domains, tier applicability and manual acceptance/evidence criteria |
| Evidence | Accepted kinds and freshness per requirement |
| Typed assurance | Existing TLS 1.2/1.3 minimum service and DR test interval/RTO/RPO thresholds |

All built-in contextual families retain definitions so the shared applicability engine can add necessary reviews. Custom requirements use the existing manual fallback: Evidence Missing without evidence, provisional Needs Review with usable evidence. Changing criteria text does not create a specialist evaluator or standards certification. Typed TLS/DR criteria remain explicitly described beside supplied manual expectations; broader control meanings stay manual.

Critical-system qualification remains required for system-access points: only systems declared to host/process critical data count; noncritical systems contribute zero, unknown scope stays unassessed, and actual access-related review obligations remain. Unknown classifications cannot be configured as numeric zero. These and the no-approval/source-integrity safeguards are invariants, not organization switches.

## Versions and snapshots

A changed configuration requires a new version; an existing organization/version cannot be rewritten with different content. Selecting another profile or editing settings never changes the active assessment's captured policy. New assessments use the selected profile's active version. Existing assessment review/completion fingerprints include the complete configuration and hash, even when a change leaves the numeric score unchanged.

The downloaded package contains `methodology.json`: the exact canonical configuration snapshot, SHA-256-bound to `report.json`. This is configuration metadata, not a vendor-evidence artifact or proof of organizational approval. Original vendor evidence bytes and their manifest remain separate. JSON and HTML report the organization/version, method, inputs, baseline, adjustment, reasons, uncertainty and final tier. Import/export canonicalizes JSON formatting, not its validated settings.

The pilot has one active assessment per browser session; explicitly starting another clears that active session assessment. Export a completed package to retain it. This is not a persistent production assessment-history store.

## Validation and limits

Imports are capped at 128 KB before parsing, reject duplicate/unknown fields and invalid shapes, and cannot execute expressions or code. Counts are bounded whole numbers; percentages are whole percentages; weights are 0–100, tier thresholds must increase from T4=0, and unknowns remain null. The supported framework currently has four tier levels. TLS remains bounded to the existing supported versions. BCP freshness must agree with the configured exercise interval. Full validation occurs before a profile becomes active; failed edits/imports leave the previous profile intact.

Legacy internal callers without an organization snapshot retain their previous pilot behavior for compatibility. New customer assessments always capture a profile. Default source extraction grammar, fact confirmation, authoritative risk and authentication behavior are unchanged. Organization-specific evidence kinds/freshness and typed thresholds are passed through existing assurance services, not inferred from documents.
