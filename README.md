# LMA Vendor Trust Intelligence

[![Run tests](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/workflows/tests.yml/badge.svg)](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/workflows/tests.yml)

**Assess the evidence before you ask the questions.**

LMA Vendor Trust Intelligence is an **evidence-first third-party risk assessment platform in development**.

Our goal is to reduce assessment time by analyzing security evidence vendors already maintain, evaluating it against organizational requirements, identifying material risks and gaps, and producing explainable results for analyst review.

The existing application provides a working foundation for vendor risk management. The complete AI-powered assessment experience described below is the product direction, not a claim that every capability is currently implemented.

## Try an assessment with your own synthetic files

Run `AUTH_MODE=development streamlit run app.py`. **New Assessment** opens by default:
About vendor → Upload evidence → Evaluate → Review gaps → Report. Enter your own
synthetic vendor/service context, attach local synthetic PDF/DOCX/TXT documents,
review exact source quotations and gaps, record draft findings, then finish and
export the original uploaded bytes in a source-traceable ZIP.

This local, memory-only first slice uses the existing applicability engine and
source-bound manual review workflow. TLS and DR now have limited source-cited candidate extraction and comparisons
against example customer thresholds; all facts and meanings require human confirmation.
Other technical interpretations remain manual. See [supported syntax and limits](docs/Upload_Threshold_Evaluation.md). No arbitrary
standards assurance, real vendor custody, external AI calls or risk approvals are
provided. See [scope, limits and walkthrough](docs/Upload_Assessment.md).

The old scripted scenarios and legacy global-record pages are available only
under **Show internal development tools**; they are not the primary customer path.

## Official Product Blueprint

[View the LMA End-to-End Product Workflow](docs/LMA_Vendor_Trust_Intelligence_End_to_End_Workflow.md)

This document is the project's primary product guide.

### Guiding Principles

- Evidence first, questions second.
- Evidence availability does not equal evidence sufficiency.
- Missing evidence is not proof of control failure.
- Evaluate evidence against organizational requirements and technical standards.
- Consider the vendor's actual business use case and risk exposure.
- Explain every material conclusion with traceable evidence.
- AI recommends; authorized humans make final decisions.
- Prioritize reducing assessment effort without sacrificing accuracy.

## End-to-End Product Vision

```text
Business requests vendor assessment
    ↓
LMA evaluates inherent risk
    ↓
Applicable assessment requirements selected
    ↓
Vendor receives secure invitation
    ↓
Vendor grants trust-center access
OR uploads supporting documents
    ↓
LMA reads and classifies evidence
    ↓
Evidence evaluated against requirements
    ↓
Standards, freshness, scope and context checked
    ↓
Relevant external intelligence considered
    ↓
AI generates evidence-backed conclusions
    ↓
Targeted questions address remaining gaps
    ↓
Analyst reviews and confirms results
    ↓
Findings and residual risk evaluated
    ↓
Final assessment and reporting
    ↓
Analyst and Executive Dashboards
    ↓
Monitoring and targeted reassessment
```

## What Is Implemented Today

The repository currently includes working application and backend components for:

- Vendor inventory and engagement management
- New vendor intake
- Inherent-risk scoring and vendor tiering
- Assessment creation and control applicability
- Risk-based assessment requirements
- Evidence uploads and storage abstraction
- SOC 2 document text extraction and metadata analysis
- Evidence confidence, provenance, and exception detection
- Evidence-to-control claim candidates and human confirmation
- Control sufficiency and analyst dispositions
- Findings and remediation tracking
- Evidence request and response reconciliation
- Residual-risk calculation and decision guardrails
- Governed residual-risk review and activation controls
- Post-activation validity and revalidation case foundations
- Monitoring events and targeted reassessment logic
- Audit logging and role-based authorization components
- SQLAlchemy database models and Alembic migrations
- SQLite development and PostgreSQL CI compatibility
- Automated regression tests using pytest and GitHub Actions

**Current limitation:** The existing document-analysis capability is primarily deterministic SOC 2 extraction with governed analyst review. It is not yet a production-ready AI agent capable of evaluating arbitrary trust-center evidence and completing assessments autonomously.

The [M3B evidence-to-fact validation proof](docs/M3B_Evidence_to_Fact_Validation.md)
adds a backend source/provenance check and explicit analyst semantic-review gate
before the provisional M3A privileged-MFA evaluator. It uses synthetic regressions
and has no automatic approval, scoring, persistence or new application screens.

The [M3C-1 exception-first review pilot](docs/M3C1_Exception_First_Analyst_Review.md)
adds a synthetic privileged-MFA review in the Evidence Center. One explicit action
can confirm displayed supporting interpretations while exception triage and
complete-bundle review remain separate. Every result stays provisional.

### Evidence-Based Control Assurance — implemented proof and platform direction

The intended capability evaluates **every applicable vendor security control**
against customer-defined requirements, applicable technical/industry standards,
actual implementation and operation, service scope, evidence freshness, and
material exceptions. A vendor stating that a control exists, attaching a policy,
or providing a matching quotation does **not** establish its sufficiency.
Privileged MFA is an early **reference scenario**, not a product boundary.
The [M3D bounded proof](docs/M3D_Evidence_Based_Control_Assurance.md) adds a
control-neutral source/review contract and common **Control Assurance Review**
presentation in the Evidence Center. Applicable customer requirements are
represented independently of specialist evaluator availability; registered cases
determine the available families. Tested technical rules cover three synthetic examples:
privileged MFA through the existing M3A/B/C gates; TLS configuration, enabled
minimum, deprecated-protocol rejection and full-endpoint operating scans; and
completed disaster-recovery exercises with customer-specific cadence and achieved
RTO/RPO. TLS and DR use separate typed rules, not MFA substitutions or keywords.

A fourth unrelated vulnerability-remediation requirement demonstrates the safe
fallback without a technical evaluator: usable cited evidence stays **Needs Review**;
absent or unusable evidence stays **Evidence Missing**, with a visible specialist
limitation and focused follow-up. Human semantic confirmation cannot turn either
fallback result into passing or proven failure. This is workflow coverage for
arbitrary applicable requirements, not automated technical coverage of all controls.

Fallback evidence suitability is explicit for each customer requirement: versioned
accepted evidence kinds and a relevance binding to the source, requirement and
threshold. A current approved policy can enter review for a documented-governance
requirement; policy intent cannot substitute for operational remediation records.
Unrelated or unbound sources remain visible with an evidence/relevance gap.
These declarations enable specialist review, not automatic assurance.

Every interpretation still requires explicit human semantic confirmation, separate
exception triage and complete-bundle review. Customer policy, threshold, context,
document and interpretation changes invalidate active review. Results remain
source-linked, provisional and session-only; the pilot neither authenticates
production reviewers nor changes governed decisions. Customer-supplied standard
references, editions and mappings are displayed metadata, not independently
verified normative-compliance proof. MFA retains its original specialized review
actions behind a compatibility adapter. The pilot does **not** technically evaluate
all control families or understand arbitrary documents. M1 TLS and M2 encryption/DR/IR
screening drafts remain earlier, separate capabilities. See [Issue #5](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/5).

### Evidence-first assessment worklist — synthetic integration

The Assessments screen includes a small read-only [M4A-1 preview](docs/M4A1_Evidence_First_Assessment_Worklist.md).
It composes the existing assessment work plan, targeted-gap logic and M3D review;
every supplied applicable requirement remains visible, including custom IDs with
no specialist evaluator. Explicit relationship, policy, threshold and exact-ID
links prevent document-type or name-based reuse across requirements. Exceptions
come before supporting evidence; legacy `SUPPORTED` remains separate from
provisional technical assurance. Targeted follow-ups are previews only.

Four-requirement synthetic packages propose one vendor request initially and zero
after a completed recovery record is supplied, against an ask-everything baseline
of four questions per package. These are **deferred-request counts**, not resolved
facts: both packages have zero reviewed supporting needs, and respectively four
and five needs awaiting analyst validation. Need-specific review binds exact
sources and confirmed M3D facts to the customer threshold; kind or general
relevance cannot establish support. A reviewed insufficient fact produces a
targeted follow-up even when a same-kind document is present. Pilot states start
unreviewed, and inspection records no review or governed decision. These counts
do not measure real analyst time, vendor accuracy or production readiness.

## Planned Industry-Pilot Capabilities

### 1. Business Assessment Intake

Business requesters will provide vendor information, business purpose, service details, data classification, access requirements, criticality, and vendor contact information.

LMA will evaluate inherent risk and determine applicable assessment requirements.

### 2. Vendor Evidence Portal

Vendors will receive secure assessment invitations.

They will be able to:

- Provide authorized access to their trust center
- Upload security documents and artifacts
- Submit supporting information
- Respond to targeted follow-up questions

A full security questionnaire should not be required when available evidence already answers the requirements.

### 3. AI Evidence Intelligence

LMA will analyze vendor evidence such as:

- SOC 2 Type II reports
- ISO 27001 certificates
- Penetration-test reports
- Security and privacy policies
- Identity and access management documentation
- Architecture diagrams
- Incident-response plans
- Business continuity and disaster recovery evidence
- Subprocessor information
- Other relevant security artifacts

For each requirement, LMA should identify relevant evidence, explain its meaning, assess sufficiency, and identify unresolved information.

### 4. Standards and Context Evaluation

LMA should not mark a requirement as met merely because a document mentions the relevant control.

The engine should evaluate:

- Evidence relevance
- Service and environment scope
- Document freshness
- Control implementation and testing
- Technical standards and customer policy thresholds
- Business criticality and use-case exposure
- Material findings and control weaknesses

For example, evidence describing TLS 1.0 support must be evaluated against the organization's minimum TLS requirements.

A penetration-test finding rated Low by the testing firm may require additional attention when the affected system provides privileged production access.

### 5. Explainable Assessment Outcomes

Proposed user-facing outcomes:

| Result | Meaning |
|---|---|
| Met | Sufficient current evidence supports the requirement |
| Partially Met | Some requirement elements remain unresolved |
| Needs Review | Analyst judgment is required |
| Evidence Missing | Available evidence cannot establish the requirement |
| Risk Identified | Evidence demonstrates a material weakness |

Each AI recommendation should identify the requirement, source evidence, document location, relevant facts, reasoning, uncertainty, and recommended next action.

### 6. Targeted Vendor Follow-Up

LMA will generate additional vendor questions only when necessary to address evidence gaps or conflicting information.

New responses and documents will pass through the same evidence evaluation process.

### 7. Analyst Review

Analysts will be able to:

- Accept an evidence-backed recommendation
- Challenge an AI conclusion
- Request additional evidence
- Create a finding
- Document judgment and rationale
- Finalize assessment results

Material decisions will remain human-controlled and auditable.

### 8. External Intelligence

Planned enrichment includes relevant public vendor security information, disclosed incidents, regulatory actions, service disruptions, and licensed cyber-risk signals.

Future integrations may include BitSight, Black Kite, and other security-rating providers.

External intelligence will inform the analyst's evaluation rather than automatically determine vendor risk.

### 9. Analyst Dashboard

The Analyst Dashboard will emphasize daily assessment work.

Important information includes:

- Assigned and active assessments
- Assessment status and aging
- Upcoming due dates
- Vendor responses pending
- Evidence analysis progress
- AI reviews awaiting confirmation
- Gaps and unresolved findings
- High-priority actions

### 10. Executive Dashboard

The Executive Dashboard will present the organization's third-party risk landscape.

Important information includes:

- Total active vendors
- Critical business relationships
- High and Critical residual-risk vendors
- Inherent versus residual risk
- Persistent high-risk vendors
- Effectively mitigated critical relationships
- Vendors with deteriorating risk
- Common security weaknesses
- Risk concentration
- Open critical findings
- Overdue assessments
- Assessment efficiency and program performance

Both inherent and residual risk should be visible so executives can understand the exposure created by a vendor relationship and the remaining exposure after evaluating controls.

## Current Risk Model

### Inherent Risk

Maximum score: 100.

| Score | Risk Tier |
|---|---|
| 0–24 | Tier 4 — Low |
| 25–49 | Tier 3 — Moderate |
| 50–74 | Tier 2 — High |
| 75–100 | Tier 1 — Critical |

Inherent-risk factors include data sensitivity, system access, business criticality, data volume, regulatory exposure, fourth-party dependency, geography, and AI autonomy.

### Residual Risk — RR-2.0

The implemented numeric model is:

```text
Control Deficiency = 100 - Control Effectiveness

Base Residual Risk =
(Inherent Risk × 0.60)
+
(Control Deficiency × 0.40)

Numeric Residual Risk =
Base Residual Risk + External Risk Adjustment
```

The bounded external-risk adjustment ranges from -5 to +20 depending on the external-risk score band.

Separate policy guardrails may raise the final risk rating, block approval, or require escalation.

A numeric risk score alone does not establish approval.

## Run the Application

### GitHub Codespaces

Activate the existing virtual environment:

```bash
source .venv/bin/activate
```

Install dependencies if needed:

```bash
python -m pip install -r requirements.txt
```

Apply database migrations:

```bash
python -m alembic upgrade head
```

Start Streamlit:

```bash
python -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port 8501
```

Open the forwarded application URL from the Codespaces Ports tab.

### Local Development

```bash
git clone https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence.git
cd lma-vendor-trust-intelligence

python -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m streamlit run app.py
```

On Windows, activate the virtual environment using:

```powershell
.venv\Scripts\Activate.ps1
```

### Run Tests

```bash
python -m py_compile app.py
pytest -q
python -m alembic current
```

GitHub Actions runs automated tests and PostgreSQL compatibility checks.

## Database and Security

SQLite is used by default for local development.

Database connectivity can be configured using the `DATABASE_URL` environment variable.

Alembic manages persistent schema evolution.

The current public demonstration is intended for synthetic or explicitly approved test data.

**Do not upload confidential vendor evidence to an unsecured public demonstration.**

Production deployment requires appropriate authentication, tenant isolation, encrypted storage, malware scanning, secure vendor invitation links, access control, retention policies, and authorized trust-center connectivity.

Production authentication is not yet configured.

The [M4B-1 security boundary](docs/M4B1_Secure_Assessment_Boundary.md) rejects
production/invalid authentication modes before database, storage or UI imports;
demo seeding remains development-only. Local evidence operations enforce canonical
vendor-scoped keys and POSIX no-follow path confinement. A separate read-only
evidence-access preflight requires server-verified identity and exact relationship
authorization plus RBAC; with no configured authority it denies. It is not wired
to live evidence. M4A remains synthetic and read-only. These protections do not
provide an IdP, tenant isolation, encrypted custody or production readiness.

The [M4C-1 database authorization prototype](docs/M4C1_Organization_Engagement_Authorization.md)
adds explicit organizations, issuer/subject memberships, per-engagement entitlements
and nullable legacy ownership/assessment links. A read-only M4B-compatible resolver
derives roles and relationship metadata from current database rows; missing legacy
links, revoked grants and sibling/cross-organization access deny. Its identity
source remains unconfigured, production login is disabled, and no evidence bytes
are retrieved. Legacy global queries and uploads remain production blockers.
The additive migration performs no backfill; automatic destructive downgrade is
refused pending a separate reviewed rollback/retention plan.

Never commit production credentials, access tokens, or confidential vendor documents to the repository.

## MVP Priorities

The immediate priority is completing one functional assessment journey:

1. Business intake and assessment setup
2. Secure vendor evidence collection
3. AI-assisted document parsing
4. Evidence-to-requirement mapping
5. Standards and contextual validation
6. Explainable conclusions and citations
7. Targeted vendor follow-up
8. Analyst review
9. Final assessment and risk reporting
10. Analyst and executive dashboards
11. Authorized trust-center ingestion

Advanced workflow orchestration, extensive rating integrations, sophisticated remediation management, and complex revalidation interfaces can follow after industry pilot validation.

## Project Documentation

- [Product Blueprint](docs/LMA_Vendor_Trust_Intelligence_End_to_End_Workflow.md)
- [Technical Architecture](ARCHITECTURE.md)
- [Development Backlog](BACKLOG.md)
- [GitHub Actions](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions)

## License

Copyright © 2026 LMA Creative Solutions LLC.

All rights reserved.

This repository is provided for demonstration, evaluation, educational, and portfolio purposes.

See [LICENSE](LICENSE) for permitted uses.
