# M4C-2B-1 — Tenant-scoped read proof

**Status:** New opt-in read service and synthetic tests on feature branch. Not connected to app.py or real authentication. Production remains disabled. Tracks Issue #16.

## Boundary

The read-only TenantReadService returns immutable vendor, engagement, assessment, evidence metadata and scoped counts. It requires an injected trusted identity source, database-verified current membership, role permission and explicit current engagement grants. All read queries constrain organization and matching vendor/engagement/assessment/evidence relationships. Sibling engagements without grants and legacy null links are not returned. Storage paths, bytes, tokens, risk scores and governed actions are never returned.

Identity providers, cookies, callbacks, distributed session storage and deployed tenant protections are **not implemented** by this slice. Caller-created identity objects are not authentication; the source must be secured by separately reviewed server integration. Session and grants are rechecked after read queries. This is a synthetic proof, not a production guarantee.

## Legacy route inventory: all remain blocked for production

| Source location | Gap |
| --- | --- |
| app.py:440 Control Tower | Global vendor, finding, event, evidence and assessment reads |
| app.py:868 Vendors | Global vendor selection and related detail reads |
| app.py:4891 Intake | Writes and links require organization ownership and permission enforcement |
| app.py:5095 Assessments | Global vendor/assessment selectors, downstream reads and updates |
| app.py:6661 Evidence Center | Global vendor/evidence listing |
| app.py:7252 Evidence upload | Direct stored byte write based on selected vendor |
| app.py:7498 Evidence review | Global evidence selection and related records |
| app.py:7781 Findings | Global vendor/finding reads and update paths |
| app.py:8200 Monitoring | Global vendor/event reads and writes |
| app.py:9048 Reports | Global aggregate/CSV export |
| app.py:9135 Audit | Global log reads |
| Other existing services | Complete tenant isolation not verified |

The service does **not** make these paths safe; no route was wired in this milestone. Streamlit role checks are insufficient for relationship-scoped authorization.

## Acceptance and limitations

Synthetic tests cover two organizations, different roles, siblings, null/inconsistent parent links, expired/revoked grants/memberships and sessions, forged roles and selectors, changed relationships during I/O, source outages, and counts. Recheck session and database authority before releasing rows; any invalidity fails closed. No real secrets or evidence are involved.

Before merge compile app.py and touched Python files, run full pytest, check diff and both GitHub Actions jobs, and obtain independent security/product review and explicit owner approval.

**Next:** M4C-2B-2 scopes all legacy reads, writes, uploads and exports. M4C-2B-3 integrates an explicitly selected IdP and secure browser/session deployment. Evidence-byte storage/audit/encryption/retention controls and external review remain separate launch gates.
