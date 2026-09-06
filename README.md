# LMA Vendor Trust Intelligence

A working MVP for continuous, evidence-driven third-party security lifecycle management.

## Product thesis

Traditional TPRM is often calendar-driven:

> Questionnaire → annual assessment → approval → repeat next year.

This project is designed around a different operating model:

> Intake → risk tiering → assessment → findings → approval → continuous monitoring → event-driven reassessment.

The central question is:

**Which vendors need attention right now, why, and what should we do next?**

## MVP features

- Vendor inventory
- Vendor/service engagement model
- New vendor intake workflow
- Explainable inherent-risk calculation
- Residual-risk calculation
- Vendor 360 view
- Findings and remediation tracking
- Continuous monitoring event ingestion
- Dynamic external-risk adjustment
- Control Tower attention queue
- Risk register export

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

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

A local SQLite database (`vendor_trust.db`) is created automatically.

## Suggested production architecture

For the production version:

- Frontend: Next.js / React
- API: FastAPI
- Database: PostgreSQL
- Object storage: S3
- Vector search: pgvector
- Identity: Entra ID / Auth0 / Clerk
- AI assurance: OpenAI API
- Workflow: Temporal or Celery/Redis
- Integrations: BitSight, Black Kite, SecurityScorecard, CISA KEV, NVD, ServiceNow, Jira

## Next product sprint

1. Assessments module
2. Evidence center
3. SOC 2 / pentest evidence metadata model
4. Common control framework
5. AI-assisted evidence analysis
6. Event-triggered reassessment rules
7. Risk acceptance workflow
8. PostgreSQL migration

## Important

The sample vendor data is synthetic and exists only to demonstrate the user experience.


## MVP v2 — Assessment & Evidence Center

This version adds:

- Risk-based assessment recommendations
- Assessment creation, ownership, due dates, status and approval tracking
- Evidence Center for SOC 2, ISO 27001, PCI AOC, pentest and other artifacts
- Evidence file upload for demo purposes
- Evidence coverage dates, expiration, issuer, opinion and exception counts
- Automatic Valid / Expiring Soon / Expired evidence status
- Assessment and evidence tabs within Vendor 360
- Evidence-expiration signals in the Control Tower attention queue

### Important deployment note

Evidence files are currently stored on the local Streamlit filesystem for MVP demonstration only. Streamlit Community Cloud storage is ephemeral. Before using real vendor documents, migrate evidence storage to durable object storage such as AWS S3 and migrate the SQLite database to PostgreSQL.


## MVP v3 — AI Evidence Analyst

SOC 2 uploads can now be analyzed before evidence is saved.

The first iteration extracts or summarizes:
- Auditor / issuer
- Report date
- Examination period
- Opinion
- Control exceptions
- Complementary User Entity Controls (CUECs)
- Subservice organization information
- Extraction confidence and analyst review notes

Detected SOC 2 exceptions can be converted into open Evidence Review findings after analyst confirmation.

### OpenAI configuration

The application works in demo mode without an API key by using a deterministic local parser. For AI-assisted extraction, add this secret in Streamlit Community Cloud:

```toml
OPENAI_API_KEY = "your-key-here"
```

Never commit API keys to GitHub.

The application uses the OpenAI Responses API when the secret is configured. Analyst confirmation remains required before extracted evidence metadata is saved.

