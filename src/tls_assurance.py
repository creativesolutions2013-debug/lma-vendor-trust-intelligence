"""Typed TLS rules: configuration and operating scans, never marketing support."""
from dataclasses import dataclass
import re

from src.control_assurance import Check, TechnicalResult

TLS_SIGNALS = re.compile(r"\b(?:except\w*|legacy|TLS\s*1\.[01]|SSL|fallback|unsupported)\b", re.I)


@dataclass(frozen=True)
class TlsThreshold:
    minimum_version: int  # 12 = TLS 1.2; 13 = TLS 1.3 (explicit supported policy range)

    def __post_init__(self):
        if type(self.minimum_version) is not int or self.minimum_version not in {12, 13}:
            raise ValueError("This bounded pilot supports TLS 1.2 or 1.3 minimum policies.")

    def describe(self):
        return (f"Minimum enabled TLS {self.minimum_version // 10}.{self.minimum_version % 10}; "
                "deprecated protocols rejected; full endpoint inventory in configuration and operating scans.")


def tls_direction(threshold, fact, source):
    if not isinstance(threshold, TlsThreshold):
        raise ValueError("A typed TLS threshold is required.")
    if type(fact.active) is not bool or not isinstance(fact.subject, str) or not fact.subject.strip():
        return "unknown"
    if source.evidence_kind not in {"configuration", "test", "assertion", "policy"}:
        return "unknown"
    if fact.dimension == "minimum_version" and type(fact.value) is int and fact.value in {10, 11, 12, 13}:
        return "support" if fact.value >= threshold.minimum_version else "adverse"
    if fact.dimension in {"legacy_rejected", "scope_complete"} and type(fact.value) is bool:
        return "support" if fact.value else "adverse"
    return "unknown"


def evaluate_tls(threshold, observations, as_of):
    """A fleet claim needs config + dated scan of the complete declared scope.

    Additional active endpoints remain visible even alongside fleet-level support.
    Opposed statements for one subject are conflicts, not a majority vote.
    """
    if not isinstance(threshold, TlsThreshold):
        raise ValueError("A typed TLS threshold is required.")
    checks = []
    current = [(f, s) for f, s in observations if f.active is True]
    groups = {}
    for f, s in current:
        if tls_direction(threshold, f, s) != "unknown":
            groups.setdefault((f.dimension, f.subject), []).append((f, s))
    for (dimension, subject), rows in groups.items():
        if len({f.value for f, _ in rows}) > 1:
            checks.append(Check(dimension, "conflict", f"Conflicting TLS statements for {subject}; retain both sources.",
                                tuple(f.fact_id for f, _ in rows)))
    for f, s in current:
        if tls_direction(threshold, f, s) == "adverse":
            verified = s.evidence_kind in {"configuration", "test"}
            checks.append(Check(f.dimension, "failed" if verified else "reported",
                                f"{'Current technical' if verified else 'Unverified vendor/policy'} exception: "
                                f"{f.subject}: {f.dimension}={f.value}.", (f.fact_id,)))
    for dimension in ("minimum_version", "legacy_rejected", "scope_complete"):
        for kind in ("configuration", "test"):
            rows = [(f, s) for f, s in current if f.dimension == dimension
                    and f.subject == "complete scope" and s.evidence_kind == kind
                    and tls_direction(threshold, f, s) == "support"]
            checks.append(Check(dimension + ":" + kind, "supported" if rows else "missing",
                                f"{'Confirmed' if rows else 'Need'} {kind} evidence for {dimension} "
                                "across all in-scope endpoints, including alternate listeners.",
                                tuple(f.fact_id for f, _ in rows)))
    statuses = {c.status for c in checks}
    if "conflict" in statuses:
        outcome, action = "Needs Review", "Reconcile the conflicting endpoint configuration and scan results."
    elif "failed" in statuses:
        outcome, action = "Risk Identified", "Investigate the enabled noncompliant endpoint; confirm remediation with a fresh scan."
    elif "reported" in statuses:
        outcome, action = "Needs Review", "Obtain configuration and a scan for the vendor-reported TLS exception."
    elif "missing" in statuses:
        outcome = "Partially Met" if "supported" in statuses else "Evidence Missing"
        action = "Request the missing complete-endpoint configuration or dated protocol-rejection scan."
    else:
        outcome, action = "Met", "Submit this provisional interpretation for independent governed review."
    return TechnicalResult(outcome, tuple(checks), action)
