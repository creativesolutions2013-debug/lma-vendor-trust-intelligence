# M4C-2B-2 — Scoped operations, first slice

**Status:** Draft implementation stacked on M4C-2B-1 PR #19. The new services are NOT wired into app.py and do not provide production authentication or complete tenant isolation. Track Issue #20.

## Why this is smaller than rewriting every page

The current Streamlit application uses global ORM queries and writes in Control Tower, Vendors, Intake, Assessments, Evidence Center, Findings, Monitoring, Reports and Audit Log. Those paths cannot safely become available to authenticated customers simply because OIDC sessions were verified. Role-based menu visibility does not prevent record-level access.

M4C-2B-1 introduces the test-only tenant-scoped read contract. M4C-2B-2 first extends that contract where a real disclosure would otherwise occur: CSV report export. Safe mutation integration requires separate, reviewed server-authorized business services and is NOT achieved by wrapping Streamlit forms in conditionals.

## Added contracts

- `src/tenant_report_export.py`: metadata-only report with one row per *explicitly granted* engagement and assessment/evidence counts. It reuses M4C-2B-1 `TenantReadService` current identity, membership, exact grant and role checks. It performs an independent `report.export` permission check; a claimed global Admin role is ignored. Queries validate organization/vendor/engagement/assessment/evidence parent links. It rechecks identity and entitlement after data selection and CSV construction. No storage paths, source quotations, evidence bytes, risk scores or governed approvals appear in the CSV.
- `src/production_route_policy.py`: an inventory and deny-first classification for every existing legacy navigation page and common operation, plus unknown paths. Even named scoped capability routes require a separate source-authorized service; **classification never authorizes**.
- `tests/test_tenant_report_export.py`: synthetic authorization, tenant and sibling suppression, role, revocation, expiry, race, CSV injection, and route-coverage regressions.

## Critical limitations

The route policy is NOT connected to Streamlit/HTTP and is NOT sufficient to protect existing pages. Production startup in `src/auth_context.py` remains disabled before side effects; no IdP or cookies are wired. The existing global `render_reports` CSV and other legacy read/write/upload services remain unchanged and MUST remain blocked in any real authenticated deployment.

The export consistency rechecks are a defensive proof rather than a substitute for server-side access transactions, durable revocation semantics, concurrent change handling, source-custody protections or independent security review. The future production export endpoint must reauthorize itself and audit completed exports.

`main` contains neither this work nor PR #19. Another open draft PR #18 overlaps earlier milestone planning and must be reconciled to avoid parallel authorization designs.

## Next implementation gates

1. Review/merge the tenant read foundation (PR #19) after direct isolated PostgreSQL evaluation, compile and independent review. Resolve overlap with PR #18, do not auto-merge.
2. Treat each existing page as blocked for authenticated production; migrate its **underlying data services**, including writes, approval and risk governance, before enabling the corresponding route. Test new selectors, IDOR, exports, audit, stale sessions, cross-tenant joins and adversarial forged role/org inputs.
3. Evidence upload/download needs safe storage authorization, malware scanning, encryption, retention, file size/type and access audit before real evidence.
4. Actual IdP client, browser callback, cookie/CSRF/reverse-proxy and distributed session/replay stores are a later reviewed M4C-2B-3 gate.

## Acceptance protocol

Compile app.py and touched code before isolated full pytest, review complete diff/whitespace and run Unit + PostgreSQL CI on exact head. Since base PR #19 is not yet merged, M4C-2B-2 must remain draft. Synthetic CI does NOT prove live enterprise multi-tenancy or readiness for customer evidence.
