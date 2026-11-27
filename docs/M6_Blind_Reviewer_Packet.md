# M6 — Blind reviewer packet (synthetic cases)

**Purpose:** Independently establish source-grounded customer-requirement judgments before viewing the author's proposed labels. **Synthetic exercises only.** This packet intentionally omits the provisional concern IDs, gold annotations, suggested follow-up questions and LMA outputs.

**Instructions:** Review each numbered case independently. For each, record (1) what the evidence actually demonstrates; (2) whether the requirement is supported, a control weakness is demonstrated, available evidence is insufficient, or the relationship is uncertain; (3) exact supporting quote; (4) service/population/environment scope, evidence kind and time constraints; (5) any material exception; and (6) the **single smallest justified next action**, distinguishing internal verification, analyst interpretation and a vendor-directed question. Missing evidence alone is **not** proof that a control fails. Do not infer an authoritative approval from these excerpts.

Do not open `benchmarks/m6_analyst_scenarios_v1.json`, the M6 scoring module, the pre-adjudication report or LMA evaluation outputs **until your independent decisions are submitted**. Reviewers should receive a standalone copy of this packet without repository access, where feasible. Case order should be counterbalanced across reviewers.

---

## Case M6-01 — Privileged MFA method

**Customer requirement:** Privileged production access requires phishing-resistant MFA.

**Evidence:** Service: Cedar Billing API. Privileged MFA is enabled for all administrator accounts. Authentication method and recovery path not specified.

## Case M6-02 — Privileged MFA TOTP

**Customer requirement:** Privileged production access requires phishing-resistant MFA.

**Evidence:** Service: Cedar Billing API. Production admin authentication uses TOTP authenticator codes. No alternative phishing-resistant mechanism documented.

## Case M6-03 — TLS secondary listener

**Customer requirement:** All production endpoints must reject TLS versions older than 1.2.

**Evidence:** Service: Cedar Billing API. Primary listener 443 accepts TLS 1.3. Production backup listener 9443 accepts TLS 1.1.

## Case M6-04 — TLS partial coverage

**Customer requirement:** All production endpoints must reject TLS versions older than 1.2.

**Evidence:** Service: Cedar Billing API. Production listener 443 rejects TLS 1.0 and TLS 1.1. TLS 1.3 is accepted. No other listeners are described.

## Case M6-05 — Achieved recovery objectives

**Customer requirement:** Current annual production DR test must demonstrate RTO <=240 minutes and RPO <=60 minutes.

**Evidence:** Service: Cedar Billing API. Production recovery test completed 2026-10-18. Measured RTO 300 minutes and RPO 90 minutes.

## Case M6-06 — DR policy versus exercise

**Customer requirement:** Annual executed production DR test with achieved RTO <=240 minutes and RPO <=60 minutes.

**Evidence:** Service: Cedar Billing API. DR policy targets RTO 120 minutes and RPO 30 minutes. Next exercise is scheduled for December 2026.

## Case M6-07 — DR report timing

**Customer requirement:** Production DR exercise must be within 365 days of 2026-11-01.

**Evidence:** Service: Cedar Billing API. Recovery report issued 2026-10-18. The measured RTO 180 minutes relates to the exercise completed 2024-04-11.

## Case M6-08 — DR service scope

**Customer requirement:** Annual production recovery test required for Cedar Billing API.

**Evidence:** Service: Cedar Warehouse. Annual recovery exercise completed 2026-10-18 and achieved RTO 90 minutes.

## Case M6-09 — Missing incident-response evidence

**Customer requirement:** Documented and exercised incident response process for Cedar Billing API.

**Evidence:** No incident response evidence was provided with the synthetic package.

## Case M6-10 — Incident-response plan versus exercise

**Customer requirement:** Incident response procedure must be documented and exercised in the past 12 months.

**Evidence:** Service: Cedar Billing API. Incident response plan v4 was approved 2026-08-01. No tabletop or incident exercise results are included.

---

**Review boundary:** This exercise does not provide verified vendor evidence, document provenance, real technical logs or full historical context. Distinguish what the statement says from what is independently proven. Record uncertainty, not invented assurance.
