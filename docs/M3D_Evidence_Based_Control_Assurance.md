# M3D: Evidence-Based Control Assurance

This is the bounded architectural correction in [Issue #5](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/5),
implemented on `feature/m3d-cross-control-assurance` for draft PR #6. Privileged MFA
is a demanding reference scenario, not the product boundary. The Evidence Center
provides a **Control Assurance Review** whose applicable requirements are
independent of specialist evaluator availability. MFA, transport encryption (TLS),
and disaster-recovery testing have technical proof cases. A fourth unrelated
vulnerability-remediation requirement demonstrates the common analyst-review
fallback with evidence present and missing. Families come from registered cases,
not an allowed-domain list. This extends workflow coverage to arbitrary applicable
customer requirements; technical automation remains limited to tested evaluators.

The fallback correction addresses the [independent architecture review on PR #6](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/pull/6#pullrequestreview-5604185352)
and the updated Issue #5 universal-scope acceptance criteria. It does not add a
generic document-understanding engine or automate all customer requirements.

## Reused boundaries and small shared contracts

The live-main baseline was `0300404b20da48bc516c2e2f1e49bb7366ea0f45` (merged PR #4).
M1's deterministic TLS screening and M2's DR draft capability were inspected; their
heuristic/AI drafts cannot establish enabled protocols or completed exercises.
The new proof reuses M1 parsing, not those drafts as verified facts.

- `evidence_source_validation.py` extracts M3B's neutral evidence inputs, binding,
  hashes, segment IDs and explicit review records. M3B imports/re-exports the same
  API and preserves its fingerprint format and behavior.
- `control_assurance.py` defines a versioned customer requirement/context,
  source-bound observation, technical result and session review contract. It has
  no MFA dependency. A requirement can retain supplied acceptance text without
  an evaluator through `CustomerThreshold`. `DomainEvaluator` is the optional
  typed extension for domain rules, direction and triage signals with a version;
  their thresholds remain frozen records. Neither supplied acceptance text nor
  standard references are executable policy. A proposal inherits its declared
  source inventory scope, date and kind; it cannot silently broaden them through
  a separate fact scope.
- `tls_assurance.py` and `dr_assurance.py` apply genuinely different technical
  rules to explicitly reviewed observations. They do not parse prose into truth.
- `control_assurance_presentation.py` is the common exception-first read-only
  presentation contract and renderer. `mfa_assurance_adapter.py` maps existing
  M3A/B/C results into it without changing their technical semantics or review
  APIs. MFA's specialized review actions remain separate compatibility debt;
  evaluator-backed and fallback requirements share neutral actions.
- `control_assurance_ui.py` occupies the existing Evidence Center pilot location.
  `control_assurance_registry.py` derives its families from registered applicable
  review cases. Adding a
  case in a new family does not require a domain branch in the common renderer.
  This is not a dashboard or broad navigation redesign.

Requirements carry ID, customer policy ID/version, declared approving owner/date,
service, environment, population/asset scope, freshness window and standard
reference, with supplied business-use/evidence expectations and standard source
and edition where available. TLS cites RFC 9325's protocol-version guidance; DR cites NIST SP 800-34
Rev.1's testing/exercise guidance. The numerical acceptance bounds are the
customer's synthetic policy, not a claim that a framework mandates those numbers.
References, editions and mappings are customer-supplied metadata: this pilot does
not independently validate authoritative editions, control mappings or normative
conformance. An omitted mapping stays omitted; no standard is invented.
Historical `IAM-01`/`PAM-01` and all governed control meanings remain unchanged.

## Technical proof

| Family | Required technical support | Customer threshold examples | What cannot establish Met |
| --- | --- | --- | --- |
| Privileged MFA | Existing M3A/B/C implementation, method, enforcement, complete population, operating tests, fallback and recovery safeguards | Allowed methods, phishing resistance, age | FIDO2/MFA mention, unknown activation, sampled administrators, unsafe alternate path |
| TLS | Enabled minimum, deprecated-protocol rejection and complete endpoint coverage in both configuration and dated operating scans | TLS ≥ 1.2 versus ≥ 1.3; current within 90 days | Supported-protocol marketing, configuration without scans, scans without configuration, omitted alternate listener |
| DR | Completed dated full-service exercise; achieved RTO/RPO where applicable, tied to the same exercise record | Annual versus quarterly; RTO ≤ 240/60 minutes, RPO ≤ 60/5 minutes | Plan targets, unexecuted statements, unrelated good metrics combined across different exercises, stale or incomplete scope |

All five outcomes are provisional: `Met`, `Partially Met`, `Needs Review`,
`Evidence Missing`, `Risk Identified`. Reviewed configuration/test failures remain
distinct from vendor assertions or plan admissions. Opposed current facts retain
both accounts and require reconciliation. Missing operation is not a failure;
stale reports and service/dependency scope gaps remain explicit limitations.
An active weak alternate TLS endpoint cannot disappear behind good primary scans.

## Requirements without specialist rules

An applicable requirement keeps its identity, versioned customer threshold,
business/service/asset scope, required evidence, freshness and assessment date even
when its technical evaluator is unavailable. The same source binding, exact
citations, inventory, interpretation fingerprints, analyst rationale/history and
separate exception/signal/bundle actions remain available.

The conservative fallback explicitly displays **Specialist evaluation unavailable;
analyst review required.** It returns provisional **Needs Review** when a current,
in-scope, provenance-complete source matches the requirement's explicit review
expectations and relevance binding, or **Evidence Missing** when none does. A
stale/out-of-scope report or deficient source inventory cannot establish eligibility.
A suitably bound source can still be reviewed directly when it has no
candidate facts, or when an individual candidate's citation/meaning is invalid;
that invalid candidate remains unconfirmed and challengeable.

`EvidenceExpectation` carries the customer's accepted source kinds and an explicit
version. `RelevanceBinding` snapshots the supplied relevance rationale against the
source fingerprint and the complete requirement/threshold fingerprint. Exactly one
current, nonempty binding is required per eligible source. Missing, stale or
duplicate bindings create a visible gap. These records are also included in the
bundle fingerprint, so changing expectations, relevance, policy or thresholds
invalidates active review. Missing metadata never defaults to inferred relevance.

This is eligibility for specialist review, not semantic or operational proof.
A policy can be relevant to a documented-governance requirement that explicitly
accepts policies. The operational remediation example accepts configuration,
test and assertion records for review; a related policy alone still leaves the
required operational evidence missing. A current configuration file without a
relevance binding also stays Evidence Missing. Kind, matching words, candidate
presence and scope alone never determine relevance. Customer-supplied declarations
can still be wrong and require human judgment; they cannot establish a passing or
failed control. Specialist technical evaluators retain their existing rules.

Additional synthetic packages demonstrate an approved service-specific security
policy for a documented-governance criterion (`gov-policy`), its absence
(`gov-missing`), policy intent for operational remediation (`vm-policy-only`) and
unrelated configuration (`vm-unrelated`). The UI retains every source and quotation
and distinguishes declared review eligibility from sources retained for context.

Fallback evidence is cited as material **for specialist review**, never as support
for meeting the requirement. Individual explicit meaning confirmation records only
what the source says. It does not evaluate the supplied threshold or manufacture
implementation, coverage or operating assurance. There is no grouped supporting-
fact approval for an unavailable evaluator. Caller-supplied adverse/conflicting
interpretations and lexical concerns remain visible and separately reviewable;
neither a keyword nor human confirmation turns them into verified technical failure.
Even after every meaning, signal and complete-bundle decision, the fallback can
never return `Met`, `Partially Met` or `Risk Identified`, and never silently skips
the requirement. Its next action identifies the required specialist evaluation or
the smallest missing evidence package against the supplied customer criterion.

The fourth fixture concerns **vulnerability remediation**: the customer supplies
critical-issue remediation within 30 calendar days on every in-scope production
asset, independent closure retesting and expected dated inventory/closure evidence, while
no vulnerability technical evaluator exists. `vm-present` retains cited vendor
evidence and a separately presented concern; `vm-missing` keeps the same requirement
visible with its evidence gap. Neither fixture proves vulnerability compliance or
failure. A future independently tested evaluator can be attached through the typed
extension without changing the common review/result interface or adding a family
branch to the UI. The retained MFA-specific review actions are a separate legacy
adapter, explicitly not a requirement for adding another family.

These are code-supplied synthetic requirement packages. This milestone does not add
a policy editor, live customer-requirement ingestion or confidential evidence flow.

## Human review and safety

Default inspection creates no semantic reviews. The analyst sees the requirement,
threshold, outcome, prioritized exceptions/conflicts/gaps, cited strongest support,
uncertainty and one next action. Full source text, location, date, provenance,
SHA-256 and individual fact fingerprints remain expandable. Every grouped meaning
is displayed with its own quote, location, subject and activation field.

Explicit grouped confirmation records individual fact dispositions. It cannot
include an adverse/unknown interpretation, dismiss a source signal or acknowledge
the complete bundle. Each adverse interpretation is confirmed separately. Each
lexical signal requires a separate material/nonmaterial disposition; defaults retain
potential materiality. Dismissing a signal cannot suppress a distinct adverse fact.
Complete-bundle review is a separate deliberate action. Source/fact problems,
untested operation and unresolved/material exceptions still prevent positive
assurance after acknowledgment.

An analyst can challenge an individual meaning as unsupported or ambiguous,
including after provisional `Met`. This preserves other fact dispositions,
original evidence and earlier events, while clearing bundle acknowledgment.
Re-acknowledging cannot override a challenge. A corrected interpretation/source
creates a new bundle and requires fresh confirmation. Customer policy/threshold,
source bytes/metadata, fact properties, scope, date or evaluator version changes
invalidate all active neutral-contract review. MFA retains its existing M3B/C
bindings. Backend event history is retained when a new bundle is reviewed; the UI
discards active state on package/family changes and does not restore old approvals.

Only synthetic packages are accepted by this surface. No confidential evidence,
AI API, database migration, authentication change, automatic disposition,
authoritative score or governed record write is added. Reviewer labels and fixed
dates model authorized human input; they do not implement production authorization.
Hashes prove supplied-byte/metadata consistency, not source authenticity or truth.

## Regression corpus and measured interactions

The TLS/DR corpus has **16 multi-document scenarios, 46 document instances and
9 distinct content hashes**. Each family includes a complete positive, stricter
customer threshold, current technical exception beside strong support,
vendor-reported exception, contradictory documents, stale operation, another
service's report and statement-only evidence. The existing eight MFA pilot cases
and the M3B adversarial corpus continue to run. Additional mutations test exact
quote/location/source integrity, unknown activation/types, stale customer test
cadence, incomplete source inventories, independent challenge, and invalidation.

Within the 16 TLS/DR scenarios, tests require **zero incorrect Met recommendations
among 14 negative/uncertain scenarios** and **zero missed verified material
exceptions among four designated current failure/stricter-threshold cases**.
Conflicts and vendor admissions are separately required to stay `Needs Review`.
These denominators describe this hand-authored corpus, not estimated real-world
error rates. Unreviewed packages can never produce `Met`.

The fallback fixtures and regressions are additional to those original TLS/DR
denominators. Backend and Streamlit tests cover evidence present/missing, arbitrary
family registration, individual meaning confirmation and challenge history,
retained adverse evidence, source limitations, and changed customer policy,
threshold, date and source invalidation. They demonstrate safe workflow inclusion
without technical automation. They do not estimate expert judgment quality or
real-world completeness for vulnerability management or future domains.

Streamlit AppTest drives the actual widgets and records the following scripted
paths. A widget interaction is one family/package selection, text entry, checkbox
change, radio selection or button click. The paths use one common rationale and
dismiss lexical signals only after context review (deliberately wrong dismissals
in adverse tests prove a separate fact still survives).

| Synthetic path | Actual widget interactions | Recorded decisions | Modeled M3B per-fact submissions |
| --- | ---: | ---: | ---: |
| MFA positive | 12 | 4 | 10 |
| TLS positive | 12 | 4 | 9 |
| DR positive | 6 | 2 | 5 |
| TLS current exception / vendor report | 18 each | 6 each | 11 each |
| DR current exception / vendor report | 12 each | 4 each | 7 each |

The per-fact baseline is number of interpretations + source-signal dispositions
+ complete-bundle review; M3B had no corresponding UI. It is **not** an observed
old-widget baseline. Grouping reduces positive fact submissions while preserving
separate adverse decisions. Real reading time, document opens, additional rationale
editing, expanded-source reading, reviewer comprehension and assessment accuracy
are not measured. No human timing study or productivity claim is made.

## Limitations and independent review

Facts and source inventories are hand-authored. A correct quotation can still
carry a wrong human interpretation; the gate requires explicit review, not machine
entailment. An analyst can confirm a wrong meaning, misstate a source's scope/date,
or dismiss an uncited exception incorrectly. Lexical exception scanning is only a
triage aid and misses unseen/euphemistic language; it never verifies failure.
Only supplied documents are considered. These tests cannot establish general
document understanding, real-vendor false-positive/miss rates, authenticated
custody, production authorization, encryption configuration completeness or
actual disaster-recovery capability. TLS 1.2/1.3 and a few DR dimensions are a
deliberately narrow proof, not complete protocol/cipher or resilience assessment.

Compilation precedes the full isolated pytest suite. GitHub Actions must verify
both Unit tests and PostgreSQL compatibility on the PR head. Draft PR #6 remains
unmerged for independent review of technical rules, evidence bindings, adversarial
coverage and governance boundaries.

Prior three-evaluator baseline verification: `app.py` and all touched Python modules compiled; full
`DATABASE_URL=sqlite:///:memory: .venv/bin/python -m pytest -q` completed with
**708 passed, 1 skipped**. The skipped test requires PostgreSQL and is covered by
the separate PostgreSQL compatibility job. Diff/compatibility/security review
confirmed that changes stay within synthetic review, parsing bindings, technical
rules and documentation, with no governed-write integration.

Fallback-correction verification: `app.py` and all touched Python modules compiled
before the full isolated suite, which completed with **756 passed, 1 skipped**.
The correction adds 35 backend and 13 Streamlit regressions, including arbitrary
family registration and the typed evaluator extension. The remaining local skip is
the PostgreSQL-only smoke check. Both GitHub Actions job results on the final head
are recorded on draft PR #6 for independent re-review.

Requirement-specific suitability amendment: compilation preceded the full isolated
suite, which completed with **799 passed, 1 skipped**. Thirty backend and thirteen
Streamlit regressions cover policy-documentation requirements, operational
policy-only and unrelated-source gaps, malformed metadata, retained citations and
review invalidation. Existing specialist and human-review regressions remain green.
The skip still requires PostgreSQL; final-head CI results are recorded on PR #6.
