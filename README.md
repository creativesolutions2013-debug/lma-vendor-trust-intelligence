# LMA Vendor Trust Intelligence

[![Run tests](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/workflows/tests.yml/badge.svg)](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/workflows/tests.yml)

**A continuous third-party risk intelligence platform designed to identify which vendors need attention now, why their risk changed, and what action should happen next.**

LMA Vendor Trust Intelligence is a working TPRM platform that combines vendor intake, inherent-risk tiering, security evidence analysis, findings management, remediation, residual-risk decisioning, continuous monitoring, evidence-to-finding traceability, and event-driven reassessment in a single workflow.

---

## Why this matters

Traditional third-party risk management is often calendar-driven:

> Questionnaire → Annual Assessment → Approval → Repeat Next Year

That model creates unnecessary reassessment work while still leaving organizations exposed to material risk changes that occur between scheduled reviews.

LMA Vendor Trust Intelligence is designed around a different operating model:

> Vendor Intake → Risk Tiering → Requirements → Due Diligence → Evidence Validation → Findings → Residual Risk → Risk Decision → Remediation → Continuous Monitoring → Triggered Reassessment

The core principle is simple:

**Do not reassess every vendor simply because twelve months have passed. Reassess when the risk changes.**

The platform is built around one operational question:

**Which vendors need attention right now, why, and what should happen next?**

---

## Target operating model

The platform is evolving toward a policy-driven third-party risk decision engine.

```text
Vendor Intake
    ↓
Inherent Risk Evaluation
    ↓
Calculated Tier
    ↓
Applicability & Requirements
    ↓
Required Controls
    ↓
Required Evidence
    ↓
Assessment
    ↓
Evidence Validation
    ↓
Control Disposition
    ↓
Findings / Remediation
    ↓
Residual Risk
    ↓
Decision Guardrails
    ↓
Approval / Escalation
    ↓
Continuous Monitoring
    ↓
Targeted Reassessment
    ↓
Offboarding

Each major decision stage is intended to follow a consistent pattern:
INPUT
  ↓
EVALUATE
  ↓
CHECKS / GUARDRAILS
  ↓
DECISION
  ↓
OUTPUT
  ↓
STATE TRANSITION
  ↓
AUDIT RECORD

AI Evidence Analyst
The AI Evidence Analyst helps reduce manual security-document review by extracting structured information from vendor evidence such as SOC 2 reports.
Current capabilities include:
- Auditor and report-date extraction
- Audit-period identification
- Opinion detection
- Control-exception detection
- Exception-to-control association
- Evidence confidence and analyst review
- Persistent evidence provenance and extraction rationale
- Persistent source exceptions independent from remediation findings
- Evidence-to-finding traceability by Evidence ID, control ID, and exception number
- Automatic creation of findings from detected exceptions
- Human confirmation before evidence is saved
The current public MVP supports deterministic local parsing so the demonstration can operate without paid AI API usage.
The architecture also supports an optional AI-assisted extraction path for future production use.
Continuous risk model
The platform separates three important dimensions of vendor risk:
- Inherent Risk — risk created by the nature of the vendor relationship, service, data, access, business criticality, regulatory exposure, geography, fourth parties, and AI usage.
- Control Effectiveness — the degree to which validated security controls reduce the underlying exposure.
- External Risk — observable changes in security posture such as incidents, vulnerabilities, security ratings, breach indicators, material service changes, or other monitoring signals.
The objective is not simply to produce a risk score.
The objective is to create an evidence-driven operating system for deciding:
Where should the security team spend its time next?
What makes this different
- Event-driven reassessment instead of relying only on annual review cycles
- Evidence-driven risk decisions instead of questionnaire responses alone
- Vendor + engagement modeling so one supplier can support multiple services with different risk profiles
- Risk-based vendor tiering
- Human-in-the-loop evidence analysis
- Explainable residual-risk scoring
- Policy guardrails that can override mathematical scoring
- Source-to-remediation traceability
- Targeted reassessment when specific risk conditions change
- Prioritized attention queues showing which vendors need intervention
- Audit-oriented decisioning designed to preserve rationale and provenance
MVP capabilities
Current platform capabilities include:
- Vendor inventory
- Vendor/service engagement model
- New vendor intake workflow
- Inherent-risk scoring
- Vendor tiering
- Risk-based assessments
- Evidence Center
- SOC 2 evidence parsing
- Explainable extraction confidence
- Evidence provenance tracking
- Source exception persistence
- Evidence-to-finding traceability
- Evidence response reconciliation
- Findings management
- Remediation tracking
- Continuous monitoring event ingestion
- Dynamic external-risk adjustment
- Event-driven reassessment
- Targeted evidence work plans
- Controlled evidence-request orchestration
- Approval decision support
- Audit logging
- Role-based authorization components
- Control Tower attention queue
- Risk register export
- Durable evidence storage abstraction
- Alembic database migrations
- Configurable database connection through DATABASE_URL
- Database startup health and schema validation
- SQLite development support
- PostgreSQL compatibility validation
- Automated regression testing with GitHub Actions
Risk Engine
Inherent risk
Inherent risk represents exposure before considering vendor controls.
Maximum score: 100 points
Risk factor	Maximum
Data sensitivity	25
System access	20
Business criticality	20
Data volume	10
Regulatory exposure	10
Fourth-party dependency	5
Geographic risk	5
AI / autonomy	5


Inherent-risk tiers
Score	Tier
0–24	Tier 4 — Low
25–49	Tier 3 — Moderate
50–74	Tier 2 — High
75–100	Tier 1 — Critical


Tiering determines the level of due diligence and is intended to drive future control, evidence, assessment, approval, and reassessment requirements.
Residual Risk Policy RR-2.0
The platform uses residual-risk policy RR-2.0.
The model intentionally separates:
1. underlying exposure,
2. control weakness,
3. external risk changes,
4. policy guardrails.
Step 1 — Control deficiency
Control Deficiency =
100 - Control Effectiveness

Example:
Control Effectiveness = 80

Control Deficiency =
100 - 80
= 20

Step 2 — Base residual risk
Base Residual Risk =
(Inherent Risk × 0.60)
+
(Control Deficiency × 0.40)

This keeps inherent exposure as the dominant factor while allowing validated security controls to reduce the resulting risk.
Step 3 — External-risk adjustment
External risk is treated as a bounded adjustment rather than as an independent weighted risk component.
External risk score	Adjustment
0–19	-5
20–49	0
50–64	+5
65–79	+10
80–100	+20


Final Numeric Residual Risk =
Base Residual Risk
+
External Risk Adjustment

The final numeric score is capped between 0 and 100.
Example
Inherent Risk = 80

Control Effectiveness = 70

Control Deficiency =
100 - 70
= 30

Base Residual Risk =
(80 × 0.60)
+
(30 × 0.40)

= 48 + 12
= 60

External Risk = 70
External Adjustment = +10

Final Residual Risk = 70

Residual-risk ratings
Score	Rating
0–24	Low
25–49	Moderate
50–74	High
75–100	Critical


Policy guardrails
The platform intentionally separates the calculated score from the final decision.
A weighted score must not allow a severe control failure or security event to disappear mathematically.
Examples of guardrails include:
Active critical security incident
Condition:
Active critical security incident

Outcome:
Final rating = Critical
Approval blocked = Yes
Escalation required = Yes

Unresolved critical finding
Condition:
Unresolved critical finding

Outcome:
Minimum final rating = High
Approval blocked = Yes
Escalation required = Yes

Privileged access without MFA
Condition:
Privileged production access without MFA

Outcome:
Minimum final rating = High
Approval blocked = Yes
Escalation required = Yes

Expired required evidence
Condition:
Required evidence expired

Outcome:
Approval blocked = Yes

Incomplete assessment
Condition:
Assessment incomplete

Outcome:
Approval blocked = Yes

Expired risk acceptance
Condition:
Previously approved risk acceptance expired

Outcome:
Approval blocked = Yes
Escalation required = Yes

This design allows the platform to distinguish:
Calculated Score
Calculated Rating
Final Rating
Triggered Guardrails
Approval Status
Escalation Requirement
Policy Version

Example decision:
Residual Risk Score: 42
Calculated Rating: Moderate

Guardrail:
Privileged production access without MFA

Final Rating: High
Approval Blocked: Yes
Escalation Required: Yes

Policy Version: RR-2.0

Risk-engine design principle
The platform follows this operating principle:
Facts create risk. Risk determines requirements. Evidence validates requirements. Gaps create findings. Findings influence residual risk. Residual risk and guardrails drive decisions. Material changes restart only the affected parts of the lifecycle.

Demo and local setup
The public MVP is built with Streamlit and uses synthetic data for demonstration purposes.
Run in GitHub Codespaces
pip install -r requirements.txt
alembic upgrade head
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501

Codespaces will expose port 8501 and provide a browser preview URL.
Run locally
Clone the repository:
git clone https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence.git
cd lma-vendor-trust-intelligence

Create a virtual environment:
python -m venv .venv

macOS / Linux
source .venv/bin/activate

Windows PowerShell
.\.venv\Scripts\Activate.ps1

Install dependencies:
pip install -r requirements.txt

Apply database migrations:
alembic upgrade head

Start the application:
python -m streamlit run app.py

Run the test suite
pytest -q

The regression suite covers capabilities including:
- Risk scoring
- Vendor tiering
- Evidence validation
- Evidence reconciliation
- Findings and escalation
- Reassessment
- Decision gates
- Approval decisions
- Audit logging
- Authorization
- Database configuration
- Database health
- Storage
- PostgreSQL compatibility
Database configuration
The application uses SQLite by default for local MVP development.
sqlite:////tmp/vendor_trust.db

A different database can be selected through the DATABASE_URL environment variable.
Example PostgreSQL configuration:
export DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/vendor_trust"

alembic upgrade head

python -m streamlit run app.py

Do not commit production database credentials to the repository.
Use environment variables or a managed secret store.
Database startup health check
Before the application opens a database session or seeds demo data, it validates:
- Database connectivity
- Presence of expected application tables
- Presence of the Alembic version table
If connectivity succeeds but the schema is incomplete, the application stops with guidance to run:
alembic upgrade head

This prevents late SQLAlchemy failures after the application UI has started.
The health-check output intentionally excludes database connection strings and credentials.
Alembic migrations
Database schema creation and evolution are managed with Alembic.
The application does not rely on Base.metadata.create_all() to mutate the persistent production schema.
Check current migration version
alembic current

Apply migrations
alembic upgrade head

Create a migration
alembic revision --autogenerate -m "Describe schema change"

Review the generated migration before applying it.
Then run:
alembic upgrade head
pytest -q

Roll back one migration
alembic downgrade -1

Important
alembic stamp head records a migration revision only.
It does not create tables or execute migration scripts.
For a new database, use:
alembic upgrade head
```

Use `alembic stamp ...` only when the physical database schema already matches the revision being stamped.

### Current baseline

The repository currently uses:

```text
0001_baseline (head)
```

Future schema changes should be added as new migration revisions rather than by deleting `/tmp/vendor_trust.db`.

## PostgreSQL CI validation

GitHub Actions runs two independent jobs on pushes and pull requests to `main`.

### Unit tests

The standard job runs the regression suite with the default application configuration.

### PostgreSQL compatibility

The PostgreSQL job starts an ephemeral PostgreSQL 16 service and then:

1. Installs the application dependencies.
2. Sets `DATABASE_URL` to the CI PostgreSQL service.
3. Applies the Alembic migration chain with `alembic upgrade head`.
4. Verifies that the expected tables exist.
5. Runs the complete pytest suite against the PostgreSQL configuration.
6. Executes a PostgreSQL-specific seed/query smoke test that writes demo records, reads them back, verifies expected relationships and risk values, and cleans the records afterward.

This provides automated validation that the application models, Alembic schema, seed logic, and basic read/write behavior work with PostgreSQL rather than only SQLite.

## Demo data and security note

The current public deployment uses synthetic vendor and evidence data only.

SQLite and locally uploaded evidence files are used for MVP demonstration purposes and may be ephemeral in hosted Streamlit environments. Real or confidential vendor evidence should not be uploaded to the public demo.

A production deployment should use persistent PostgreSQL storage, secure object storage, authentication, role-based access control, audit logging, encryption, and malware scanning for uploaded evidence.

## Current scoring model

### Inherent risk

Maximum 100 points:

- Data sensitivity: 25
- System access: 20
- Business criticality: 20
- Data volume: 10
- Regulatory exposure: 10
- Fourth-party dependency: 5
- Geographic risk: 5
- AI/autonomy: 5

Risk tiers:

- 0–24: Tier 4 — Low
- 25–49: Tier 3 — Moderate
- 50–74: Tier 2 — High
- 75–100: Tier 1 — Critical

### Residual risk

```text
Residual Risk =
(Inherent Risk × 0.40)
+ ((100 - Control Effectiveness) × 0.35)
+ (External Risk × 0.25)
```

This is intentionally transparent and should become configurable in later versions.

## Suggested production architecture

For the production version:

- Frontend: Next.js / React
- API: FastAPI
- Database: PostgreSQL
- Object storage: S3-compatible storage
- Vector search: pgvector
- Identity: Entra ID / Auth0 / Clerk
- AI assurance: optional production AI service
- Workflow: Temporal or Celery / Redis
- Monitoring integrations: BitSight, Black Kite, SecurityScorecard
- Security intelligence: CISA KEV, NVD
- Enterprise workflow integrations: ServiceNow, Jira
Product roadmap
Priority engine capabilities include:
1. Tier-to-control requirement mapping
2. Tier-to-evidence requirement mapping
3. Dynamic applicability engine
4. Assessment-template orchestration
5. Formal control disposition workflow
6. Risk-acceptance and exception management
7. Approval-authority workflow
8. Expanded evidence parsing beyond SOC 2
9. Cross-document contradiction detection
10. Continuous external-security intelligence integrations
11. Trigger-specific reassessment
12. Full offboarding lifecycle
13. Production authentication and tenant isolation
14. Production evidence-storage hardening
15. Policy-version and decision traceability
Current development status
The project currently includes a substantial automated regression suite and is actively evolving from a TPRM assessment application into a policy-driven vendor-risk decision and orchestration engine.
The current architectural direction is:
Vendor Intake
    ↓
Calculated Tier
    ↓
Applicable Requirements
    ↓
Control & Evidence Requirements
    ↓
Assessment
    ↓
Evidence Validation
    ↓
Findings
    ↓
Residual Risk
    ↓
Decision Guardrails
    ↓
Approval / Escalation
    ↓
Continuous Monitoring
    ↓
Targeted Reassessment

Important
All sample vendor data is synthetic and exists only to demonstrate the user experience.
License
Copyright © 2026 LMA Creative Solutions LLC.
All rights reserved.
This repository is provided for demonstration, evaluation, educational, and portfolio purposes.
See LICENSE for permitted uses.