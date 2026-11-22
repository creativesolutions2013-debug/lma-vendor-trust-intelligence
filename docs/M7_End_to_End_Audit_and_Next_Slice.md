# M7: connect reviewed evidence gaps to follow-up

## Evidence and authority

Audited protected main `5a76854140a953c6865efd9bfb5cdc2c12bc16ec` before planning.
[Post-merge CI 44975149290](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/44975149290)
passed Unit tests and PostgreSQL compatibility. The original working checkouts
were preserved; implementation starts on `feature/m7-reviewed-evidence-followup`.

Read `AGENTS.md`, `README.md`, the official end-to-end workflow, and the owner’s
uploaded **LMA Project Context & Development Handoff**, prepared October 20, 2026.
The handoff’s M1/M2 counts and “M3 not implemented” checkpoint are historical;
the live repository establishes current implementation. No handoff instructions
override the current owner request. Qualified independent TPRM professional
validation is **deferred until the end-to-end application is completed**. It does
not block M7 engineering. No human-validation result or efficiency measurement is
invented; independent code review and the existing approval boundaries remain.

## Actual application audit

“Implemented” below means present in the running synthetic customer path, not
production readiness. Source and real-app AppTest coverage were inspected.

| Journey | Current state | Evidence and practical limit |
| --- | --- | --- |
| Assessment initiation | Implemented / partial | `upload_assessment_ui._about` uses `Intake`, existing scoring and applicability. Unknown scope stays provisional. Contact, owner, due date and multi-user handoff are missing. |
| Customer requirements and thresholds | Implemented / partial | Captured organization/version, configurable TLS/DR thresholds, criteria/kinds/freshness and policy JSON export. This is session configuration, not authenticated tenant policy administration. |
| Evidence acquisition | Implemented / missing | Real local synthetic PDF/DOCX/TXT selection, routing, explicit metadata suggestions and original bytes. Vendor invitation, vendor portal and authorized trust-center ingestion are missing. |
| Secure custody | Unwired / missing | Startup fails closed in production; customer path stops before DB/storage imports (`app.py`). Size/type/expansion limits and bounded PDF parsing are wired. Backend identity/session/tenant/evidence preflight foundations exist, but authenticated byte custody, encrypted storage, quarantine/malware scan, retention and durable save/resume are missing from this path. |
| Source-grounded standards evaluation | Partial / unwired | `upload_evaluation` extracts unconfirmed TLS/DR candidates and hypothetical customer-threshold comparisons with exact citations and metadata/phrase restrictions. Uploaded control cases remain manual fallback. General technical meaning, full scope and normative standards editions are not automatically established. Existing fact/signal/bundle review contracts are not wired here. |
| Minimal targeted gaps | Partial / unwired | Worklist can distinguish missing evidence from candidates awaiting review. Uploaded requirements have one broad evidence need. A current policy can defer a request, and the UI’s Request Evidence action currently changes only the annotation ledger. |
| Analyst control decisions | Partial / unwired | Source-bound Accept/Challenge/Request Evidence/Create Finding annotations, deduplication and stale history exist. They cannot confirm facts, satisfy a need, approve a control or authorize risk. Backend governed services are separate from this path. |
| Findings and final report | Implemented / partial | Draft findings retain citations and stale context. Immutable synthetic completion, HTML/JSON/manifest/methodology and original-byte ZIP export exist. Remediation ownership, authenticated final decisions and authorized residual-risk inputs are not connected; score remains null and vendor decision pending. |

The legacy pages are global-record development tools, not a secure fallback.
OIDC/session/membership/scoped-read code must be reused when identity is wired.
Legacy storage also persists absolute paths/S3 URIs where the secure authority
expects a canonical object key; wiring without reconciliation would be unsafe.

## Ranked gaps and scope decision

High/medium/low describe impact, not measured ROI. Complexity includes integration
and security review, not just code size.

| Rank | Gap | Commercial | Correctness | Security | Friction | Complexity | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Authenticated relationship ownership and evidence custody | High | High | High | High | High | Required before real sensitive-data pilot; separate provider/session/storage work, not a quick connection to legacy pages. |
| 2 | Analyst-reviewed insufficiency produces no actual follow-up | High | High | Medium | High | Low | **Build this slice now** with existing need-review service and controls. |
| 3 | Source-safe semantic confirmation and dimension-specific evidence needs | High | High | Medium | High | Medium/high | Next evaluation slice. Preserve extractor eligibility before exposing confirmation; do not attach an evaluator blindly. |
| 4 | Durable assessment save/resume and multi-user handoff | High | Medium | High | High | High | Integrate after ownership/custody; do not persist this session model into global legacy records. |
| 5 | Final requirement decisions, remediation and governed report | High | High | High | Medium | High | Reuse existing governance services after source/identity boundaries; no automatic approvals. |
| 6 | Traceable customer standards editions and broader evaluators | Medium/high | High | Medium | Medium | Medium/high | Extend from customer evidence needs; defer a generic framework engine or benchmark expansion. |

The strongest counterargument is that custody is the commercial launch blocker.
It is, but a small UI change cannot supply authenticated ownership, secure byte
operations and lifecycle controls. The chosen slice improves the product’s core
evidence-first loop using synthetic files while preserving production denial.
It does **not** complete M7 or authorize real vendor custody.

## Exact defect, proposed correction and acceptance (before coding)

Reproduction on main: attach a current in-scope DR policy with planned objectives;
evaluate; select BCP-01 → Request Evidence and enter a rationale. BCP-01 remains
Needs Review, and its need remains Analyst validation required. The exported
annotation says Request Evidence, but there is **no BCP-01 targeted request**.
The returned typed evaluator is deliberately not used by the fallback, and UI
actions never call the already-implemented `record_need_review` service.

Connect the existing action/rationale to an explicit **insufficient** need review
covering every current candidate, then rebuild the same worklist and export the
source-bound gap-review record. Reuse the current action controls; no new form,
dashboard, AI workflow, policy/risk engine or external message. Do not offer
“supported” need reviews or semantic fact confirmation in this slice.

Acceptance:

- Policy-only DR starts awaiting analyst validation. Explicit Request Evidence
  creates a current need-specific insufficiency record and a draft request in the
  same UI, report JSON and printable HTML. Retain threshold, rationale, exact
  source fingerprints/citations and the applicable service/policy/version.
- No evidence, stale/out-of-scope/unaccepted evidence still produces an evidence
  gap. An insufficiency review cannot infer control failure, confirm technical
  facts, close a need, approve a vendor or change numerical risk.
- Re-evaluating changed evidence/metadata/routing/threshold/context invalidates
  prior review and completion. Old annotations remain traceable; another control’s
  unchanged review remains current. New candidate evidence requires review before
  a prior insufficiency judgment is reused.
- Record review and annotation atomically in session memory; reject missing
  confirmation, invalid rationale and inconsistent inputs without partial state.
- Reuse bounded original bindings during review/rebuild; never reparse retained
  untrusted originals through an unbounded parser. Dirty uploads still block review
  and report. Preserve no-op discard and all prior citation/security safeguards.
- Prove the source → review → actual request → added evidence → stale/review →
  report loop with synthetic unit and actual `app.py` AppTests. Compile app and
  touched modules before pytest; full SQLite/PostgreSQL CI, complete diff review
  and independent exact-head code review. Draft PR only; no merge/main changes.

Intended files: upload assessment builder/action adapter and UI; existing worklist
review validation/presentation; report/HTML adapter; focused synthetic unit and
actual-app regressions; CI compilation list; this audit. Evaluator extraction,
authentication, storage, DB models/migrations and standards/risk rules are excluded.

## Open work verified before planning

All 16 open PRs were drafts with successful Unit/PostgreSQL checks at inspection.
Actual application diffs were checked in addition to their descriptions:

| PRs and inspected heads | Overlap retained |
| --- | --- |
| #21 `6514991` | Unwired tenant metadata export/notes and migrations; no evidence-byte custody or app wiring. #19 foundations are already merged despite stale #21 prose. |
| #29 `0adbaa8`, #30 `5bddfa6`, #31 `407a44f`, #32 `2663765`, #33 `7f962db`, #34 `27992ca` | Frozen M5C and TLS/DR extractor/integration work, including metadata/navigation changes understated in #29’s body. No extractor or frozen benchmark changes here. |
| #37 `6026779`, #38 `0dde7f8` | Narrative recovery cues, not semantic review or need-review wiring. Preserve their separate branches. |
| #39 `91bfab3`, #40 `7fd7a24`, #41 `dd10961`, #42 `1b377f2`, #43 `077ecb8` | M6 study/scorer, AI-only historical experiments, interpretation overlay and retention materials. No duplication, execution or mutation. |
| #45 `47ef81e`, #47 `d18afa4` | Upload preservation and intake simplification already integrated by #48. Main additionally contains merged #50 and #51; retain their safeguards. |

Older PR checks do not prove integration against today’s main. No existing PR is
merged, rebased or overwritten by this work.
