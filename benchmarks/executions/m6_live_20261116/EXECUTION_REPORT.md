# M6 actual AI execution — November 16, 2026

Two real Codex reviewer sessions completed on the unchanged ten-case synthetic blind packet. These are actual AI outputs, not the hand-constructed simulation. The coordinator ran deterministic comparison only; semantic AI reconciliation and qualified-human adjudication did not run. No control/vendor approval, risk acceptance or authoritative risk change occurred.

## Authentication and execution fixes

The earlier PR records show HTTP 401 with no usable bearer authentication in fresh writable homes. A writable directory alone is insufficient. The operator completed the approved `codex login --device-auth` flow in `/workspace/m6-review-login-20261116`; `codex login status` reported `Logged in using ChatGPT`. Credential files were neither inspected nor copied.

The earlier requested slug `gpt-6.1` was rejected with HTTP 400 and is absent from the authenticated model catalog. The new runs explicitly requested advertised `gpt-6.1-sol`. A subsequent authenticated request exposed a second HTTP 400: strict structured output rejects `classifications.uniqueItems`. Commit `31657b2a9615511ef54ad1c910b1059f3c43e84a` adapts only the provider schema; canonical schema, input hashes and local duplicate-classification rejection remain unchanged. The prior failed attempts are separately retained under `prior_attempts/` and are not counted as completed reviews.

## Provenance and boundaries

- Executed implementation: `31657b2a9615511ef54ad1c910b1059f3c43e84a`; CLI `0.163.0`; requested model `gpt-6.1-sol` for both. Actual serving model remains **null/unverified**; reasoning/sampling defaults are not attested.
- Raw blind packet SHA256: `3cf63d64a0cf0d7de5c36186588f2e93745fcb792052edc9c2c6d9d41e15698b`.
- Canonical input SHA256: `76f3293e7a5c2fd2ecd0bf89bd3648f7aab7c17fab80187ff50e9ac2597fa3e0`.
- Canonical response schema SHA256: `34a40faa939c6b4b2b1fe5ca59096cd9460c525e562c5e821005ee615dfdd578`.
- Provider schema SHA256: `a19b0c44c6e65c32c3acd26d156f0af6d08c469b2a74e49ace57f943f435b69d`.
- A received its own instructions and cases 01–10; B received its own instructions and cases 10–01. Supplied payloads were checked against the exact blind packet; neither contained provisional labels, scorer data, simulations, prior conclusions or the peer instructions. Both were started concurrently before any result was read.
- Fresh temporary working directories, ephemeral sessions, ignored user config/rules, zero project-document bytes and disabled access features were used. Both self-reported clean input boundaries and passed event audits with **zero observed tool calls**.
- These checks do not establish host/provider confinement, absence of hidden context, statistical independence or model diversity. Both used the same requested model.

| Reviewer | Run ID | Session ID | Response SHA256 | Citations |
| --- | --- | --- | --- | --- |
| A | `2b5da31c-8ae9-43b1-ae28-a734eea8176f` | `01a1e5f5-1a5a-72f2-97a1-166b4cea299f` | `0ae609a535d047a4a88c8278036085d04ce6dc730d7e7363ca304475323bd081` | 10 |
| B | `571e4b7e-17c4-427d-b31b-3e0ca16e7bf0` | `01a1e5f5-1a8b-7d21-9e3f-43650afdcdf0` | `b6d8389689137f1b4903baec80ea2848b373817774ceb36ab9460c6925029d8e` | 18 |

Separate `response.json`, `record.json`, `started.json` and SHA256 sidecars are preserved for each reviewer. Both response seals were checked for equality with their embedded records before and after coordination; neither changed. Configuration and prompt hashes are in `manifest.json` and `input_boundary_audit.json`.

Artifacts: [Agent A response](runs/A/response.json), [Agent B response](runs/B/response.json), [full comparison](proposed_reference.json), [input audit](input_boundary_audit.json), and [prior failed attempts](prior_attempts/summary.json).

## Validation and complete comparison

Both reviews contain exactly the original ten cases, all required fields, permitted nonempty classifications, consistent weakness flags and source-attributed exact quotations. **28/28 citations** match their own case evidence; citations on 09 identify package absence, not operating evidence. Exact quote matching does not prove semantic truth or real-world control operation. Unknown structured approval/risk fields are rejected, and application/governance/database code is unchanged.

- Classification sets agree on **7/10**: 02,03,04,05,06,09,10. They differ on 01,07,08.
- Demonstrated-weakness flags agree on **10/10**: true only on 02,03,05.
- Evidence sufficiency agrees on **10/10**: adequate for the proposed adverse finding on 02,03,05; missing on 09; insufficient on the other six. Adequate adverse evidence is not control approval.
- Minimal action kind agrees on **5/10**: 01,02,03,05,08. It differs on 04,06,07,09,10.
- Full response objects agree exactly on **0/10**. All ten have unresolved textual/content differences, including rationale and question proposals; this does not imply ten contradictory substantive findings. No reconciliation or favorable-label selection was performed.

Classification legend: EX=`demonstrated_exception`, EI=`evidence_insufficient`, OS=`out_of_scope`, ST=`stale_evidence`, SL=`supported_with_limits`, UA=`unresolved_ambiguity`.

| Case | A classes | B classes | Shared weakness / sufficiency | A action | B action |
| --- | --- | --- | --- | --- | --- |
| M6-01 | EI | SL, EI | false / insufficient | vendor_question | vendor_question |
| M6-02 | EX | EX | true / adequate | analyst_review | analyst_review |
| M6-03 | EX | EX | true / adequate | analyst_review | analyst_review |
| M6-04 | SL, EI | SL, EI | false / insufficient | internal_verification | vendor_question |
| M6-05 | EX | EX | true / adequate | analyst_review | analyst_review |
| M6-06 | EI | EI | false / insufficient | internal_verification | vendor_question |
| M6-07 | ST | ST, EI | false / insufficient | internal_verification | vendor_question |
| M6-08 | OS | OS, EI | false / insufficient | internal_verification | internal_verification |
| M6-09 | EI | EI | false / missing | internal_verification | vendor_question |
| M6-10 | SL, EI | SL, EI | false / insufficient | internal_verification | vendor_question |

All field agreements and differences are listed below. The unchanged full A/B values, including every quote, rationale, uncertainty, alternative interpretation and unnecessary-question proposal, are retained together in `proposed_reference.json` and separately in the two original responses.


### M6-01

Identical fields: `case_id`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `classifications`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Provide authentication configuration or equivalent technical evidence identifying the MFA methods and recovery paths enforced for all Cedar Billing API privileged production access. A rationale: The MFA existence claim does not establish the required method or recovery enforcement.

B proposed action: Provide a configuration extract identifying the mandatory MFA method for privileged production access and any recovery or fallback path that can grant that access. B rationale: MFA enrollment does not identify phishing resistance or bypass behavior.

### M6-02

Identical fields: `case_id`, `classifications`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Review the stated TOTP production admin method as a provisional exception to the phishing-resistant MFA criterion. A rationale: The described production authentication method conflicts with the criterion.

B proposed action: Record the provisional exception for the stated TOTP administrator authentication path, preserving uncertainty about any additional mandatory mechanism. B rationale: The documented production administrator mechanism is TOTP, which does not provide phishing resistance.

### M6-03

Identical fields: `case_id`, `classifications`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Review production backup listener 9443 accepting TLS 1.1 as a provisional exception. A rationale: One explicitly production endpoint accepts a prohibited version.

B proposed action: Record the provisional exception for production backup listener 9443 accepting TLS 1.1. B rationale: One explicitly identified production endpoint accepting TLS 1.1 is sufficient to contradict the all-endpoint requirement.

### M6-04

Identical fields: `case_id`, `classifications`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Check an existing Cedar Billing API production endpoint inventory against the listener evidence to establish coverage and identify any endpoints needing protocol rejection evidence. A rationale: The described listener has favorable evidence, but complete population coverage is unestablished.

B proposed action: Provide a current production endpoint inventory with protocol results covering each endpoint; if 443 is the sole endpoint, confirm that scope and its minimum accepted TLS version. B rationale: The unresolved criterion is complete production coverage, not the already stated rejection behavior on 443.

### M6-05

Identical fields: `case_id`, `classifications`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Review the completed production recovery test's RTO 300 minutes and RPO 90 minutes as provisional exceptions to the 240-minute and 60-minute limits. A rationale: Both measured results exceed the explicit thresholds.

B proposed action: Record the provisional exception for analyst review: RTO exceeds the limit by 60 minutes and RPO by 30 minutes. B rationale: The supplied measurements directly exceed both customer thresholds.

### M6-06

Identical fields: `case_id`, `classifications`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Check existing records for an executed annual Cedar Billing API production DR report showing the exercise date and achieved RTO and RPO. A rationale: Targets and a schedule cannot establish executed production recovery performance.

B proposed action: Provide the most recent completed annual Billing API production DR test record showing its execution date and measured RTO and RPO. B rationale: Targets and future scheduling do not establish executed production results.

### M6-07

Identical fields: `case_id`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `classifications`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Check existing exercise records for a Cedar Billing API production DR exercise within 365 days of 2026-11-01, with its actual completion date and production scope. A rationale: The exercise date, rather than report issuance, determines freshness.

B proposed action: Provide a Billing API production DR exercise record with an execution date within 365 days of 2026-11-01. B rationale: The operating date falls outside the required window; report issuance cannot refresh it.

### M6-08

Identical fields: `case_id`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `classifications`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Check existing records for the Cedar Billing API annual production recovery test, including service scope and completion date. A rationale: The provided exercise concerns a different service.

B proposed action: Check whether the supplied artifact was misassigned or explicitly includes Billing API production recovery; if neither can be established, request the Billing API test record. B rationale: Confirming artifact scope is the narrowest first step before seeking further vendor evidence.

### M6-09

Identical fields: `case_id`, `citations`, `classifications`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Check existing internal evidence holdings for a Cedar Billing API incident response procedure and a completed exercise record before requesting them from the vendor. A rationale: The package absence statement establishes no technical or operational facts.

B proposed action: Provide the Cedar Billing API incident response procedure and a dated exercise summary identifying the procedure and service exercised. B rationale: Neither documentation nor exercise execution can be assessed from the absence marker.

### M6-10

Identical fields: `case_id`, `classifications`, `demonstrated_weakness`, `evidence_sufficiency`. Differing fields: `alternative_interpretation`, `citations`, `minimal_action`, `reasoning`, `scope_and_freshness`, `uncertainty`, `unnecessary_questions`.

A proposed action: Check existing records for a completed Cedar Billing API incident response exercise report with its execution date and scope, and establish the reference date for the past-12-month window. A rationale: The approved-plan statement supports documentation, while exercise evidence is absent from the package.

B proposed action: Provide a dated exercise summary for Cedar Billing API within the applicable past-12-month window, identifying the incident response procedure exercised. B rationale: Plan approval supports documentation, but exercise execution and timing remain unsupported.

## Interpretation and release limits

A post-run audit of the actual outputs used the blind packet and both sealed reviews, without opening provisional labels or simulations. It identified these limits:

- On02, both call the stated TOTP path a provisional exception while allowing a possible additional mandatory phishing-resistant factor. This is not independently proven failure of every privileged access route.
- On03 and05, the stated TLS1.1 listener and measured 300>240 / 90>60 directly support provisional threshold exceptions.
- A starts with internal verification on 04/06/07/09/10, while B requests vendor evidence. The packet does not establish whether usable internal holdings exist; question necessity remains unresolved.
- On05, B describes the exercise as recent relative to review context, but the packet supplies no explicit assessment date for that case. The numerical threshold misses remain clear.
- Stale07, wrong-service08, missing09 and unproven exercises06/10 do not alone establish implementation failure.

The comparison sets `semantic_ai_adjudication_executed=false`, `human_validated=false`, `authoritative_decision=null`, and leaves time saved and question reduction null. The earlier `benchmarks/examples/m6_ai_review_simulation.json` remains an explicitly hand-constructed simulation and was not used for these reviews.

The code fix compiled and **52 mocked workflow tests passed** before the live runs. Full SQLite/PostgreSQL validation and required hosted checks must be assessed at the final PR head; see PR #40 Checks and the final execution report returned to the operator. The exact commands are in `docs/M6_AI_Review_Execution.md`.

**Recommendation: keep PR #40 draft and do not release or merge.** The authentication and live-execution blockers are resolved, but these synthetic AI-only proposals require owner/qualified-human adjudication of interpretations and necessary follow-up before assurance or performance claims. PRs #38/#39 and main remain unchanged.
