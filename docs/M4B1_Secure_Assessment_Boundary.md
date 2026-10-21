# M4B-1 — Secure Assessment Boundary

**Status: bounded implementation on draft PR #10; independent security and product review required.** Acceptance is tracked in [Issue #9](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/9). Production authentication and live M4A evidence access remain disabled.

## Why this milestone

M4A-1's synthetic, read-only worklist now connects applicable requirements, cited assurance, reviewed fact-specific needs and minimal *draft* vendor questions. Its merged commit is `720e50a8d4ac25d6aea921b91791a78521fa7f1a`; the main-branch post-merge Unit and PostgreSQL jobs passed in [run 39686140765](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/actions/runs/39686140765).

**Before wiring it to real evidence we must strengthen the trust boundary.** The pre-M4B app initialized/seeded its database before resolving identity, and local storage accepted unchecked keys. This implementation corrects those two boundaries and defines a deny-first future evidence-read contract. `get_current_principal()` still intentionally rejects production auth; an environment-supplied demo role is **not** a verifiable identity. Existing role permissions do not establish tenant/engagement-level authorization.

## Narrow M4B-1 scope

1. **Fail-closed app startup:** resolve production-mode/identity preflight before database initialization, demo seeding, storage or evidence/assessment actions. Under `AUTH_MODE=production`, abort with no side effects because production identity is not connected. Future production paths must never seed synthetic demo data.
2. **Confined local evidence keys:** enforce validated vendor-scoped object keys and safe root containment across `save`, `exists`, and `delete`. Reject traversal, absolute paths, malformed IDs, symlink escapes, and attempts to operate on unrelated vendor storage.
3. **Small deny-first access contract for future evidence integration:** role permission **plus** independently verified principal/tenant/engagement/assessment/vendor relationships. Fail closed when trusted relationship context is not available from the current model. The contract returns only authorization metadata, not evidence bytes, approvals, or real data. Exercise it on synthetic entities.
4. **Threat model + regression tests:** prove fail-closed order, path confinement, wrong-relationship rejection, and no effect on M4A worklist or governed risk workflows. Document precisely what remains absent.

**Non-goals:** A production IdP or OIDC integration, tenant DB schema migration, user account management, real vendor evidence, live ingestion, signed URLs, storage migration, email, new dashboards, AI calls or changed residual-risk outcomes. These demand a separate approved implementation after identity/tenant design is established.

## Review criteria

Preserve the product North Star (**assess the evidence before asking questions**) and M3D/M4A source-binding semantics. Follow repository `AGENTS.md`, official product blueprint, and [Issue #9](https://github.com/creativesolutions2013-debug/lma-vendor-trust-intelligence/issues/9). Check current working tree; implement on the existing feature branch and draft PR, never directly on `main`. Use only synthetic fixtures. Compile `app.py` and touched modules **before** isolated full pytest; run `git diff --check`, review the full change set, and require GitHub Actions Unit + PostgreSQL compatibility. Stop for independent security/TPRM review; do not auto-merge.

## Real-data pilot prerequisites still open

- Select and configure an external IdP: verify signatures, issuer, audience and session; map roles on the server and enforce expiry/revocation. `AUTH_MODE` remains trusted deployment configuration; its development default is not production protection.
- Establish verified organization membership, engagement grants, assessment/evidence linkage and row isolation. The present schema cannot establish all these associations; vendor IDs, filenames and browser selectors cannot substitute.
- Implement authorized evidence byte reads and custody, rechecking current identity/relationship and confined storage at read time. The preflight result is not a reusable bearer capability, download URL or file handle.
- Configure a private encrypted object store, signed/scoped access and key management. Vendor prefixes and the existing S3 storage abstraction do not establish application authorization.
- Validate malware, file type and size; define retention/deletion controls and independently test ingestion/retrieval.
- Audit successful and denied access, actor/session, custody and governed decisions; no access audit persistence is introduced here.
- Validate provenance/authenticity, customer/standards mappings, semantic accuracy, reviewer authority and real analyst usability on approved data.

M4B-1 is a **protective foundation only** and must not be represented as production authorization or secure real-vendor processing.

## Implemented startup boundary

The first app import is the side-effect-free authentication context. The app calls
`get_startup_context()` before pandas, Streamlit, database, storage or workflow
imports. This matters because importing `src.db` itself creates the data directory
and constructs an engine. Production and invalid modes therefore refuse before
those imports, `init_db`, health checks, session creation, seeding or storage selection.

`StartupContext` captures the explicit mode and demo principal together. Demo
seeding requires its development-only property, including on any hypothetical
future production path after a real identity integration. No provider is enabled:
the real production principal resolver still raises. Development defaults and
existing RBAC meanings remain compatible; a mode string does not authenticate.

## Implemented local storage boundary

`validate_evidence_key` is a pure validator for canonical
`vendors/<positive integer>/evidence/<safe single leaf>` object keys. It rejects
absolute/relative traversal, alternate separators, encoded tricks, control
characters, malformed IDs and invalid prefixes without normalization or decoding.
The optional expected vendor must match exactly. Existing generated opaque keys
and legacy single-leaf keys such as `vendors/7/evidence/test.txt` remain valid;
the builder also validates vendor IDs and opaque tokens.

Local `save`, `exists` and `delete` share descriptor-relative traversal from the
filesystem anchor using `O_DIRECTORY` and `O_NOFOLLOW`. Every configured-root/key
ancestor is checked without following links. Leaf operations reject symlinks,
hardlinks and nonregular files; save rechecks the opened descriptor before
truncation. An opened parent remains anchored during tested symlink substitutions.
Read-side absence and invalid keys create no directories. New directories/files
use private modes; existing permissions are not retroactively repaired.

POSIX no-follow and directory-descriptor support is required; unsupported
platforms fail closed. The storage tree must be private to the application OS
account. These checks do not isolate a hostile process with the same filesystem
privileges, provide encryption or authorize users. The S3 backend is unchanged.
Legacy absolute `storage_path` values are not accepted as object keys by the new
preflight and are not made retrievable through M4A.

## Deny-first future evidence access contract

`src/assessment_evidence_access.py` accepts request selectors and an optional
**server-owned** `EvidenceAccessAuthority`. With no authority it returns an
explicit blocker. No authority is implemented, registered or wired into the app.
Existing ORM data cannot be silently converted to the missing tenant/engagement
proof, and the development principal is not used as this authority.

A future reviewed adapter must independently verify identity and relationship
permission before returning its typed identity/grant/linkage snapshots. The
protocol, DTO constructors and matching fields **do not authenticate credentials**.
The injectable test authority is a synthetic trust assumption, not an IdP or a
client-selectable verifier. Deployment must never deserialize request data into
trusted snapshots or choose this dependency from browser/customer input.

The guard checks current timezone-aware session/grant windows, exact issuer,
audience, subject, session and organization binding; RBAC `evidence.read`; exact
organization/engagement/vendor/assessment/evidence authorization; one unique
typed linkage per entity with no null/duplicate/cross-relationship IDs; and the
vendor-bound canonical storage key. IDs must be positive integers, not bools or
strings. Resolver failures deny with static messages, without echoing credentials
or provider exceptions. A Viewer has broad read permission today but still needs
verified relationship permission.

A successful synthetic check returns only bounded read-authorization metadata,
not bytes, a raw filesystem path, signed access or a governed decision. Lexical
key validation here performs no filesystem I/O; a future actual read must recheck
authority and enforce physical confinement through storage. The current M4A
worklist stays fixture-only, read-only and unchanged, including need-specific
source/fact review, exception priority and provisional results.

## Threat model and acceptance evidence

| Threat | Current protection | Remaining boundary |
| --- | --- | --- |
| Production/invalid auth starts DB or storage before refusal | Actual entry-point tests block all side-effectful imports; early preflight aborts | Production identity integration is absent; development configuration remains demo-only |
| Caller key traverses, follows links or crosses a vendor prefix | Canonical syntax plus expected-vendor check and no-follow descriptor operations | Private OS-owned directories required; storage prefixes are not tenancy |
| Viewer/Admin role or selected vendor ID grants another relationship's evidence | Absent verifier denies; independent identity, relationship and unique metadata checks required | No live authority, verified tenant schema/linkage, or retrieval integration exists |
| Resolver error exposes credentials or a stale grant is replayed | Static denial reasons, current session-bound grant checks | A future read must reverify authority, revocation and byte custody |
| Security plumbing changes analyst outcomes or enables real evidence | No M4A/M3D/governed logic changes or live wiring | Independent security/product review and real-data pilot prerequisites remain mandatory |

Synthetic regressions cover production/invalid mode before any database import,
development/future-production seed order, valid storage overwrite/round-trip,
all three operations against malformed keys and link attacks, simulated path
swaps, spoofed identity/grants, strict IDs, permission conjunction, absent and
duplicate linkage, expired/mismatched context, unsafe references and metadata-only
success with filesystem operations blocked. These tests exercise this bounded
contract, not provider security, real tenant isolation or confidential-data safety.

Compile/full-suite results and both required GitHub Actions jobs on the final
feature head are recorded in draft PR #10. No merge or production-readiness claim
is authorized by this milestone.

Security acceptance checklist for the implemented slice:

- [x] Production/invalid-mode startup refuses before side-effectful dependencies; development behavior and future-production no-demo-seeding are tested.
- [x] Valid local keys remain compatible; malformed keys, cross-vendor associations and link attacks are tested for save/exists/delete.
- [x] Missing/fake verification, wrong/ambiguous relationship context and unsafe keys deny; synthetic success returns metadata only.
- [x] Compiled `app.py`, all three changed/added modules and three new test modules before full isolated pytest: **1,138 passed, 1 skipped** in 26.56s. The skip is the PostgreSQL-only smoke test.
- [x] Added **251 adversarial cases**: 9 startup, 163 storage and 79 access-preflight cases. Existing M4A/M3D and governed-decision regressions pass.
- [ ] Independent security/TPRM/product review, including final Unit and PostgreSQL CI evidence in PR #10.
- [ ] Real-data pilot prerequisites above remain unimplemented and block live integration.
