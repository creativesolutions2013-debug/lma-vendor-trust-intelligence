# LMA Vendor Trust Intelligence

[![Run tests](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/workflows/tests.yml/badge.svg)](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/workflows/tests.yml)

**A continuous third-party risk intelligence platform designed to identify which vendors need attention now, why their risk changed, and what action should happen next.**

LMA Vendor Trust Intelligence is a working TPRM MVP that combines vendor intake, inherent-risk scoring, security evidence analysis, findings management, continuous monitoring, evidence-to-finding traceability, and event-driven reassessment into a single workflow.

## Why this matters

Traditional third-party risk management is often calendar-driven:

> Questionnaire → annual assessment → approval → repeat next year.

That model creates unnecessary reassessment work while still leaving security teams exposed to risk changes that occur between review cycles.

LMA Vendor Trust Intelligence is designed around a different operating model:

> Vendor Intake → Risk Tiering → Due Diligence → Evidence Validation → Risk Decision → Remediation → Continuous Monitoring → Triggered Reassessment.

The core principle is simple:

**Do not reassess every vendor simply because twelve months have passed. Reassess when the risk changes.**

The platform is built around one operational question:

**Which vendors need attention right now, why, and what should we do next?**

## AI Evidence Analyst

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

The current public MVP supports deterministic local parsing so the demonstration can operate without paid AI API usage. The architecture also supports an optional AI-assisted extraction path for future production use.

## Continuous risk model

The platform separates three major dimensions of vendor risk:

- **Inherent risk** — what risk exists because of the service, data, access, business criticality, regulatory exposure, geography, fourth parties, and AI usage.
- **Control effectiveness** — how effectively the vendor's security controls reduce that exposure based on available evidence.
- **External risk** — changes in observable security posture, incidents, vulnerabilities, credentials, ratings, and other monitoring signals.

These inputs contribute to an explainable residual-risk score and a prioritized Control Tower attention queue.

The goal is not simply to assign vendors a risk score. The goal is to create an evidence-driven operating system for deciding **where security teams should spend their time next**.

## What makes this different

- **Event-driven reassessment** instead of relying only on annual review cycles
- **Evidence-driven risk decisions** rather than questionnaire responses alone
- **Vendor + engagement modeling** so one supplier can have multiple services and risk profiles
- **Human-in-the-loop evidence analysis** with automated extraction and analyst confirmation
- **Explainable risk scoring** that separates inherent risk, control effectiveness, and external risk
- **Source-to-remediation traceability** from evidence exception to finding and remediation status
- **Prioritized attention queues** designed to show security teams where intervention is needed now

## MVP features

- Vendor inventory
- Vendor/service engagement model
- New vendor intake workflow
- Risk-based assessments
- Evidence Center
- SOC 2 evidence parsing
- Explainable extraction confidence
- Evidence provenance tracking
- Source exception persistence
- Evidence-to-finding traceability
- Findings and remediation tracking
- Continuous monitoring event ingestion
- Dynamic external-risk adjustment
- Control Tower attention queue
- Risk register export
- Alembic database migrations
- Automated regression testing with GitHub Actions

## Demo & local setup

The public MVP is built with Streamlit and uses synthetic data for demonstration purposes.

### Run in GitHub Codespaces

Open the repository in GitHub Codespaces, then run:

```bash
pip install -r requirements.txt
alembic upgrade head
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Codespaces will expose port `8501` and provide a browser preview URL.

### Run locally

Clone the repository:

```bash
git clone https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence.git
cd lma-vendor-trust-intelligence
```

Create a virtual environment:

```bash
python -m venv .venv
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies and initialize the database schema:

```bash
pip install -r requirements.txt
alembic upgrade head
```

Start the application:

```bash
python -m streamlit run app.py
```

### Run the test suite

```bash
pytest -q
```

The regression suite covers multiple synthetic SOC 2 report formats, evidence-state isolation, and evidence-to-finding traceability.

## Database schema and Alembic migrations

Database schema creation and schema evolution are managed with **Alembic**. The application no longer relies on `Base.metadata.create_all()` to modify the persistent application schema.

### Check the current migration version

```bash
alembic current
```

### Apply all pending migrations

```bash
alembic upgrade head
```

### Create a migration after changing SQLAlchemy models

```bash
alembic revision --autogenerate -m "Describe schema change"
```

Review the generated migration before applying it, then run:

```bash
alembic upgrade head
pytest -q
```

### Roll back one migration

```bash
alembic downgrade -1
```

### Important: `stamp` does not create tables

`alembic stamp head` only records a migration version in the database. It does **not** execute migration scripts or create missing tables.

For a new or empty database, use:

```bash
alembic upgrade head
```

Use `alembic stamp ...` only when the physical database schema already matches the revision being stamped.

### Current baseline

The repository currently uses:

```text
0001_baseline (head)
```

Future schema changes should be added as new migration revisions rather than by deleting `/tmp/vendor_trust.db`.

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
- Object storage: S3
- Vector search: pgvector
- Identity: Entra ID / Auth0 / Clerk
- AI assurance: optional production AI service
- Workflow: Temporal or Celery/Redis
- Integrations: BitSight, Black Kite, SecurityScorecard, CISA KEV, NVD, ServiceNow, Jira

## Next product sprint

1. PostgreSQL migration
2. Durable object storage for evidence
3. Authentication and role-based access control
4. Audit logging
5. Configurable reassessment triggers
6. Risk acceptance workflow
7. External security intelligence integrations
8. Fourth-party dependency graph

## Important

The sample vendor data is synthetic and exists only to demonstrate the user experience.

## License

Copyright © 2026 LMA Creative Solutions LLC. All rights reserved.

This repository is provided for demonstration, evaluation, educational, and portfolio purposes. See [LICENSE](LICENSE) for permitted uses.
