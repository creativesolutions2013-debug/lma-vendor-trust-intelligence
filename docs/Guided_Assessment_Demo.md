# Guided Assessment Demo — industry-feedback runbook

Implements [Issue #22](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/22)
as a working, session-only journey in the existing Streamlit app. Every vendor,
document, proposed interpretation and reviewer action in this journey is synthetic.
Results remain provisional and independently governed decisions are not created.

## Run locally or in Codespaces

Install the repository requirements in your Python environment, then run:

```bash
AUTH_MODE=development streamlit run app.py
```

Open the local Streamlit address (normally port 8501), or the Codespaces forwarded
port. **Guided Assessment Demo** is the default navigation entry. It runs before
database initialization, seeding, storage or legacy service imports. No hosting
service, IdP, API key, external evidence access or database setup is needed for
the journey. `AUTH_MODE=production` retains its existing startup refusal.

The other navigation entries retain their legacy development behavior and global
data access. They are outside this isolated demo and are not tenant-safe routes.

## A short reviewer walkthrough

1. **Start:** Select **Evidence gap**. Inspect Acme Analytics Cloud's production
   use case, the customer policy versions and four applicable requirements.
   **Risk context** switches between two bounded exposure assumptions. Existing
   inherent-risk calculations produce 58/High or 36/Moderate, with all point
   drivers shown. These inputs do not rewrite requirement or evidence scope.
2. **Evidence:** Inspect the simulated vendor submission. Expand a source to
   see its actual parsed text, location, scope, observed/capture dates, provenance
   and fingerprint. SOC 2 and IAM/MFA background are explicitly context-only;
   this four-requirement walkthrough produces no MFA or audit-opinion assurance.
3. **Assess:** Review the single exception-first worklist. Select a requirement
   to see the actual M3D outcome, customer threshold, adverse statements, strongest
   proposed support, uncertainty and one next action. Source detail is expandable.
   Customer-specific governance and remediation requirements remain visible even
   without specialist evaluators. Policy suitability for governance does not
   establish technical operation.
4. **Questions:** Inspect the generated missing-fact request for a completed,
   full-service recovery exercise and achieved RTO/RPO. Click **Replay new evidence
   received**. Only that request disappears; the new candidate requires analyst
   validation and the existing exceptions remain. No invitation or vendor message
   is sent and there is no real-file upload.
5. **Analyst Review:** Choose a requirement and simulate **Accept**, **Challenge**,
   **Request Evidence** or **Create Finding**, with an explicit rationale.
   Accept records discussion of the draft; it does not confirm factual meaning or
   approve a control. Source/threshold changes invalidate current annotations.
   Earlier actions and original cited context remain in the session history.
   Draft findings require explicit re-review and cannot disappear behind a later
   Accept annotation or changed evidence.
6. **Results:** Inspect all requirement outcomes, simulated actions and draft
   findings, then download the clearly marked synthetic JSON assessment report.
   The report includes source quotations, thresholds, uncertainty, gap previews
   and historical annotations. The illustrative residual recommendation retains
   the inherent rating pending governance; no residual score or approved control
   effectiveness is manufactured. Use the closing discussion guide for feedback.

Use **Continue**, **Back**, or the step selector without leaving the session.
**Reset demo** restores the initial scenario and clears only this demo's state.
Changing scenarios starts a fresh walkthrough; independent browser sessions do
not share review state.

For the second walkthrough, choose **Material TLS exception**, open **Assess**,
and select **ENC-02.TLS** under **Requirement detail**. Inspect the current
alternate-listener exception alongside strong primary-listener evidence. It stays
visible after DR replay and simulated Accept actions. Its meaning remains
unconfirmed; the demo does not fabricate a verified failure. The remediation
fallback also retains a vendor-reported unresolved exception in both scenarios.

## Exact synthetic counts and their limits

Both walkthroughs use the same four applicable requirements and five distinct
evidence needs. The baseline is **one broad question per requirement**, not five
need-specific questions and not a measured manual assessment.

| Package state | Broad baseline | Targeted vendor requests | Needs awaiting validation | Reviewed support |
| --- | ---: | ---: | ---: | ---: |
| Initial package | 4 | 1 | 4 | 0 |
| Recovery exercise received | 4 | 0 | 5 | 0 |

These counts describe both the gap and TLS-exception packages. Three, then four
broad questions are deferred while evidence is inspected. They are not proven
questions avoided or real-world time savings. A candidate document is not a
supported fact. The missing completed-exercise need is **Evidence Missing**;
because a recovery policy is present, the existing whole-control evaluator
conservatively returns **Needs Review**. Neither state establishes control failure.
All default whole-requirement outcomes remain Needs Review until the established
factual-confirmation and governance processes are performed outside this demo.

The initial gap package has seven requirement-linked documents and two context
documents; replay adds one exercise document. The exception package adds the
actual synthetic TLS-exception source, giving eight linked documents initially
and nine after replay. Document counts establish inventory, not sufficiency.

## Reused implementation and boundaries

- `assessment_worklist_pilot` supplies the existing scoped requirement packages;
  `assessment_worklist` composes actual applicability, assessment orchestration,
  targeted gaps and M3D evaluation. No second evaluator/orchestrator is added.
- Source parsing/binding, domain rules, requirement suitability and common
  source/threshold presentation retain their existing behavior. Historical
  IAM/PAM/transport-control meanings are unchanged.
- `guided_assessment_demo` composes those outputs with pure inherent-risk
  calculations and a separate immutable demo-annotation ledger. Actions never
  create FactReview, NeedReview, dispositions, DB findings or risk activations.
- The existing Reports page depends on global records and commits an export audit
  event. The demo instead exports the existing worklist/presentation data through
  a small pure JSON serializer, without calling that page or copying PR #21's
  unmerged export/note services. No CSV formulas or executable HTML are generated.

The four selected requirements demonstrate a bounded assessment, not all possible
vendor controls or complete standards coverage. Hand-authored interpretations,
source authenticity, real vendor accuracy, semantic judgment, real time savings,
customer/standards mapping and production authorization remain unverified.
Industry reviewers should identify missing requirements and evaluate clarity and
usefulness before broader implementation. No confidential customer data, external
AI calls, real SSO, invitations, evidence custody or authoritative decisions are
enabled. Production readiness remains a separate workstream.

## Validation and reviewer discussion

Compile `app.py` and touched Python modules before full isolated SQLite and
synthetic PostgreSQL pytest. Verify both GitHub Actions jobs on the draft PR.
Integration tests exercise actual Streamlit navigation, replay, source detail,
all four simulated actions, reset, session isolation, stale-state handling and
download bytes, with database/network/governance tripwires. These tests prove
repeatable fixture behavior, not industry demand or production multi-tenancy.
Exact results and remaining review findings are recorded in the PR.

Suggested discussion prompts:

1. Which vendor questions would you defer after seeing this evidence?
2. Are source scope, thresholds and unresolved uncertainty clear enough to review?
3. Which material risk or requirement is missing from this walkthrough?
4. Where would vendor or analyst friction remain?
5. What evidence would you need before agreeing to a bounded pilot?
