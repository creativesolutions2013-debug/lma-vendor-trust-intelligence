# Architecture

## Functional layers

1. UI Layer
2. Workflow Engine
3. Risk Decision Engine
4. AI Assurance Layer
5. External Intelligence Layer
6. Data Layer
7. Integration Layer

## Core domain

The product distinguishes a **vendor** from a **service engagement**.

A single vendor may have several engagements with different data access, criticality, and risk.

```text
Organization
  └── Vendor
      ├── Engagements
      ├── Assessments
      ├── Evidence
      ├── Findings
      ├── Risk Acceptances
      ├── Monitoring Events
      └── Fourth-Party Dependencies
```

## MVP data entities

- Vendor
- Engagement
- Finding
- MonitoringEvent

## Planned entities

- Organization
- User
- Assessment
- Question
- AssessmentResponse
- Evidence
- EvidenceFinding
- Control
- ControlMapping
- RemediationAction
- RiskAcceptance
- ExternalSignal
- VendorDependency
- AuditLog

## Security design considerations for production

- Multi-tenant organization scoping
- Role-based access control
- Immutable audit logs
- Encryption in transit and at rest
- Secret management outside application code
- Malware scanning for uploaded evidence
- Signed URLs for document access
- Data-retention rules
- AI prompt/data isolation
- Human approval for consequential risk decisions
