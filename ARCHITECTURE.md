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

### Evidence-Based Control Assurance (bounded M3D proof)

`evidence_source_validation.py` shares M1 parsing and M3B byte/metadata/location
bindings and analyst-review records. M3B re-exports its prior API without changing
fingerprints. `control_assurance.py` supplies the neutral requirement/context,
observation, provisional result and explicit session-review contract. Typed
`tls_assurance.py` and `dr_assurance.py` implement separate technical rules;
they do not import MFA or evaluate policy text. No generic policy DSL is added.

An applicable requirement exists independently of a technical evaluator. The
optional typed evaluator extension supplies domain rules; a supplied customer
threshold can instead be retained as non-executable acceptance text. Without
specialist rules, the common review keeps sources, candidate meanings, concerns,
individual review/challenge events and separate signal/bundle decisions. It
returns only provisional Needs Review with usable evidence or Evidence Missing
without it, with an explicit specialist-review limitation and targeted follow-up.

`control_assurance_presentation.py` supplies one exception-first read-only result
contract and renderer for registered applicable families. `mfa_assurance_adapter.py` presents
unchanged M3A/B/C evaluation and review behavior through that contract. The existing
Evidence Center hosts `control_assurance_ui.py`; MFA retains its specialized safe
review actions as compatibility debt while evaluator-backed and fallback cases
share neutral actions. Family selection derives from registered cases rather than
a three-family whitelist, using `control_assurance_registry.py`. Source checks and review records are reused; MFA-only
semantics are not a base class for other controls. A fourth vulnerability-remediation
example proves evidence-present and evidence-missing fallback behavior, not a new
vulnerability technical evaluator.

The surface accepts only synthetic fixture packages. It has no database handle,
upload ingestion, AI/network call or governed-write integration. Source consistency
is not authenticity and session reviewer labels are not production authorization.
Standard references/editions/mappings are customer-supplied metadata and are not
independently verified. Workflow applicability is extensible to arbitrary customer
requirements; automated technical coverage remains limited to tested evaluators.
See [M3D implementation and limits](docs/M3D_Evidence_Based_Control_Assurance.md).

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

M4B-1 places a pure authentication preflight before all side-effectful app imports,
retains development-only demo seeding, and confines local evidence operations with
canonical keys and directory-relative no-follow descriptors. Production identity
remains unconfigured and fails closed.

`assessment_evidence_access.py` is a future metadata-only read preflight, with an
absent-by-default server-owned identity/relationship authority. Its DTOs are not
credentials; current ORM vendor/assessment IDs do not establish organization or
engagement membership. No authority or live evidence retrieval is registered in
the app. M4A continues to use synthetic fixtures. See [threat model and remaining
prerequisites](docs/M4B1_Secure_Assessment_Boundary.md).

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
