"""Control-neutral source bindings and explicit analyst-review records.

M1 parsing and the original M3B fingerprint format are shared unchanged. A
matching quote proves citation integrity only; these helpers neither infer
semantics nor authenticate a document, analyst or caller. Domain evaluators
remain responsible for technical rules and governed approval stays separate.
"""
from dataclasses import asdict, dataclass, field
from datetime import date
from hashlib import sha256
import json
import re

from src.evidence_intelligence_mvp import EvidenceDocument, read_evidence_document


CLASSIFICATIONS = frozenset({
    "policy_assertion", "implementation_evidence", "operating_test",
    "explicit_exception", "conflicting_statement", "unsupported_interpretation",
})


@dataclass(frozen=True)
class EvidenceInput:
    document_id: str
    filename: str
    content: bytes = field(repr=False)
    version: str | None
    origin: str | None
    captured_on: date | None
    service: str | None
    environment: str | None
    account_scope: str | None
    observed_on: date | None
    evidence_kind: str  # policy, assertion, configuration, test


@dataclass(frozen=True)
class BoundEvidence:
    source: EvidenceInput
    document: EvidenceDocument
    content_sha256: str
    fingerprint: str


def _digest(value) -> str:
    def encode(item):
        if type(item) is date:
            return item.isoformat()
        raise ValueError("Fingerprint input contains an unsupported type.")
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), default=encode).encode()).hexdigest()


def bind_evidence(source: EvidenceInput, *, bounded_upload=False) -> BoundEvidence:
    """Reuse M1 parsing; source IDs do not depend on potentially duplicate names."""
    if not isinstance(source.document_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source.document_id):
        raise ValueError("A unique, simple document ID is required.")
    if not isinstance(source.content, bytes):
        raise ValueError("Original document bytes are required.")
    for value in (source.captured_on, source.observed_on):
        if value is not None and type(value) is not date:
            raise ValueError("Source dates must be dates or None.")
    if bounded_upload:
        from src.bounded_document_parser import read_bounded_document
        document = read_bounded_document(source.filename, source.content)
    else:
        document = read_evidence_document(source.filename, source.content)
    metadata = {key: value for key, value in asdict(source).items() if key != "content"}
    content_hash = sha256(source.content).hexdigest()
    fingerprint = _digest({"metadata": metadata, "content_sha256": content_hash,
                           "parsed_document": asdict(document)})
    return BoundEvidence(source, document, content_hash, fingerprint)


def segment_id(document_id: str, ordinal: int) -> str:
    """Ordinal is one-based in the parser's retained segments, not a page number."""
    return f"{document_id}:{ordinal}"


@dataclass(frozen=True)
class FactReview:
    fact_fingerprint: str
    decision: str  # supported, unsupported, ambiguous
    classification: str
    analyst: str
    reviewed_on: date
    rationale: str


@dataclass(frozen=True)
class SignalDisposition:
    signal_id: str
    material: bool
    rationale: str


@dataclass(frozen=True)
class BundleReview:
    bundle_fingerprint: str
    analyst: str
    reviewed_on: date
    rationale: str
    signal_dispositions: tuple[SignalDisposition, ...] = ()


@dataclass(frozen=True)
class ExceptionSignal:
    signal_id: str
    source_id: str
    filename: str
    location: str
    quote: str
    status: str = "needs_review"  # needs_review, material, dismissed_by_analyst
    rationale: str = "Potential exception marker; inspect full source context."


def _review_valid(review, as_of, earliest=None):
    return (isinstance(review.analyst, str) and bool(review.analyst.strip())
            and isinstance(review.rationale, str) and bool(review.rationale.strip())
            and type(review.reviewed_on) is date and review.reviewed_on <= as_of
            and (earliest is None or review.reviewed_on >= earliest))


def source_issues(source, *, service, environment, scope, max_age_days, as_of):
    """Check inventory limits without assigning technical control meaning.

    ``scope`` is an exact inventory label (accounts, endpoints or recovery assets).
    Hash and inventory checks establish consistency, never source authenticity.
    """
    issues = []
    if any(not isinstance(value, str) or not value.strip()
           for value in (source.version, source.origin)):
        issues.append("Document version or evidence origin is missing.")
    if source.captured_on is None or source.captured_on > as_of:
        issues.append("Capture date is missing or in the future.")
    if source.observed_on is None or not 0 <= (as_of - source.observed_on).days <= max_age_days:
        issues.append("Evidence observation date is missing, future or stale.")
    if (source.captured_on is not None and source.observed_on is not None
            and source.observed_on > source.captured_on):
        issues.append("Observation postdates evidence capture.")
    if (source.service, source.environment, source.account_scope) != (
            service, environment, scope):
        issues.append("Declared source scope is incomplete or differs from the assessed scope.")
    if source.evidence_kind not in {"policy", "assertion", "configuration", "test"}:
        issues.append("Evidence kind is unknown.")
    return issues
