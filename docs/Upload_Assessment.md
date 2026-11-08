# Local upload-to-assessment slice (Issue #24)

M5B extends this workflow with [unconfirmed TLS/DR threshold candidates](Upload_Threshold_Evaluation.md).
The limits below describe the original M5A slice; the linked document specifies current evaluation coverage.

Install the repository requirements (Streamlit 1.66+), then run
`AUTH_MODE=development streamlit run app.py`. The primary customer entry is
**New Assessment** with no scenario selector and no preloaded vendor documents.
This is isolated session-memory development, for synthetic/nonconfidential files
only. Production authentication still refuses startup. PR #21 is not included.

## Five stages

1. **About vendor:** Enter a synthetic vendor, service and business use case, then
   select all **Data types in scope** (or Unknown), then choose declared data sensitivity, system access and criticality. The existing inherent
   risk engine and tier/applicability services select all baseline/contextual
   requirements. Volume, regulation, fourth parties, geography and AI use are not
   collected in this slice and have explicitly disclosed zero illustrative points.
2. **Upload evidence:** Select your own UTF-8 TXT, PDF or DOCX files. No fixtures
   enter this path. The file details expose parse result, role, declared scope,
   SHA-256 and suggested requirement routing, which you can correct. Supply an
   observation/test date if known; upload date is never substituted for it.
   Accepted and pending files and unsaved routing/date/kind/scope edits survive
   navigation; only Evaluate attached evidence applies those edits. New selections add files.
   Discard pending selections if a file is invalid. Clear the assessment to remove
   accepted files and start over. Reusing a filename for different content requires
   renaming the new version to avoid ambiguous screening citations.
3. **Evaluate:** Read the applicability-selected requirements, explicit synthetic
   example thresholds, exact quotes and true line/page/paragraph locations.
   Existing TLS screening flags reported legacy protocol text as an **unverified
   concern**, retained in the existing exception-first worklist. No technical
   facts or source relevance are confirmed automatically. Recovery documents are
   routed to the recovery threshold for manual scope/RTO/RPO review; the adapter
   does not extract achieved objectives or run technical DR assurance from prose.
   Other applicable requirements remain in the same source-bound manual workflow.
   Empty, unrelated, stale, different-scope and unsupported inputs never become
   passing controls. Scans without text are rejected with an OCR/reupload message.
4. **Review gaps:** Select the requirement, inspect its threshold/sources, record
   Accept-draft/Challenge/Request Evidence/Create Finding with a rationale. The
   shared source-bound annotation service rejects identical same-context findings.
   These annotations cannot confirm facts, close a need, approve a control or
   accept vendor risk. Previous findings remain open and historical annotations
   remain traceable after additional evidence invalidates their context.
5. **Report:** Finish the review and download the existing snapshot-driven ZIP.
   It contains a printable HTML summary, report, hashed manifest and exact accepted
   uploaded originals in vendor-evidence/ or vendor-context/. Example criteria are
   metadata, not fabricated original customer-policy artifacts. Inherent risk uses
   the existing engine; residual numeric score remains null, vendor decision pending.
   Changed/pending uploads block completion/export until evaluated. Reopen for
   corrections, or clear/start another assessment. Browser sessions do not share
   assessment state or raw file bytes.

## What was reused and what is not implemented

- Existing PDF/DOCX/TXT parser and `bind_evidence`, preserving original bytes and
  bound source hashes; no surrogate original artifacts are generated. Assessment
  construction reuses the exact bounded bindings through relevance and worklist
  services, scoped to that build rather than a shared or persistent cache.
- Existing tier/applicability and TLS/DR threshold descriptions; no second policy
  or risk engine. Requirements are predefined synthetic examples, not a claim of
  approval by a real organization or complete standards mapping.
- Existing deterministic pilot text screening and M3D/worklist fallback/relevance
  contracts. Routing is uploader-declared, not semantic entailment. Without
  specialist fact extraction/confirmation, outcomes stay Needs Review or Evidence
  Missing. Date/scope are declarations and their limitations remain visible.
- Existing annotation/deduplication, stale fingerprints, immutable completion,
  dual risk presentation, safe ZIP/HTML export and original-byte manifest services.
- No AI is enabled, no external APIs receive documents, no real vendor invitation,
  trust-center access, secure custody, malware scan, OCR, semantic DR extraction,
  database writes, migrations or authorization changes are claimed.

Application-held uploads are capped at 10 files, 2 MB/file and 10 MB total.
Extracted text is capped during parsing at 250,000 characters/2,000 sections per
file, before source fingerprinting. DOCX XML/expansion are bounded before parsing;
encrypted, corrupt or unsupported ZIP entries are rejected with a re-save message.
PDF parsing runs in a disposable process with a 384 MB address-space limit,
3 CPU seconds and 10 seconds wall time, plus the existing 300-page limit. PDF
uploads require a host with POSIX resource limits (the Linux development host);
unavailable limits fail closed. These are local resource guards, not malware
scanning or a production document security review.
Legacy global-record pages and the scripted fixture demo are hidden behind the
internal-development checkbox and receive no uploaded assessment data.

## Validation and reproducible UX proof

Pure tests cover actual PDF/DOCX/TXT bytes, exact citations and ZIP hashes,
missing/unrelated/stale/different-scope evidence, limits and stale annotations.
Actual `app.py` AppTests use Streamlit's real file-uploader simulation, not seeded
session fixtures. They create a vendor, upload TLS and recovery files, evaluate,
record a correctly mapped finding, add evidence without manual reupload, finish,
inspect the ZIP, reopen/reset and check separate-session isolation. Database,
storage, network, AI and governed-write tripwires stay active throughout.

Measurements are fixture-level proof only: complete all five stages with zero
code changes or external/manual storage steps; every exported artifact must match
its selected original bytes and digest; every displayed citation must match an
actual parsed location. No measured reviewer time savings or generic compliance
accuracy is claimed. Owner hands-on UX acceptance and an independent code review
remain necessary before merge or broader pilot claims.

## Dataset scope and tier determination

The requester selects public/internal/confidential business data, PII, sensitive personal data, PHI, payment-card data, credentials, financial records, Other/not yet classified and/or Unknown. These are use-case data categories, separate from sensitivity and uncollected volume. They do not describe uploaded evidence files. Empty selections are rejected; Unknown can accompany known categories when the scope is partial.

The adapter reuses the existing legacy-intake sensitivity weights: Public=0, Internal=5, Confidential=10, PII=15, Sensitive PII=20, PHI/PCI/Credentials=25. Dataset mappings are synthetic example policy: financial records map to Confidential unless a higher selected category applies. The effective sensitivity contribution is the maximum of the declared sensitivity (the existing customer-path Public=5, Confidential=10, Restricted=20) and the highest known category, never the sum of categories. This preserves a higher declaration and avoids double counting. It does not assign regulatory-exposure points or infer jurisdiction. The existing PHI/PCI/credentials grouping enables the existing regulated-data requirement review; a full regulatory determination remains unassessed.

For the default Production/Important relationship, Confidential business data yields 41/Tier 3; Personal data yields 46/Tier 3; PHI yields 56/Tier 2. Public declaration with PHI still yields 56. Other/Unknown has no invented numeric weight: known contributions remain and the score/tier is explicitly provisional pending clarification. Sensitive-data requirements are retained for unknown scope. No low-risk conclusion follows from unknown types.

Selections, declared and effective points, mapping basis and uncertainty appear in report.json; the HTML summary and UI show selections, risk drivers and provisional warnings. Changes are included in existing review/completion fingerprints, even when scores are equal. Existing reset clears the selection. All scoring is illustrative; evidence review never approves a vendor or changes authoritative risk. The field is limited to the session-memory customer intake; legacy persistence, production authentication, extraction rules and PR #21 are unchanged.
