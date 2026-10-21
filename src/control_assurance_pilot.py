"""Hand-authored multi-document synthetic TLS/DR packages, never extracted truth."""
from dataclasses import replace
from datetime import date

from src.control_assurance import ControlCase, Observation, RequirementContext
from src.evidence_source_validation import EvidenceInput, bind_evidence, segment_id
from src.tls_assurance import TLS_SIGNALS, TlsThreshold, evaluate_tls, tls_direction
from src.dr_assurance import DR_SIGNALS, DrThreshold, dr_direction, evaluate_dr

AS_OF = date(2026, 10, 21)


def document(key, text, scope, *, kind="test", observed=date(2026, 10, 14), service="Acme Analytics"):
    return EvidenceInput(key, key + ".txt", text.encode(), "synthetic-v1",
                         "Hand-authored synthetic fixture; not an authenticated vendor artifact",
                         AS_OF, service, "production", scope, observed, kind)


def proposal(doc, dimension, line, value, *, fact_id=None, subject="complete scope", active=True):
    bound = bind_evidence(doc)
    segment = bound.document.segments[line - 1]
    return Observation(fact_id or doc.document_id + "-" + dimension, dimension, value,
                       segment_id(doc.document_id, line), bound.fingerprint,
                       segment.location, segment.text, subject, active)


def _tls_case(case_id="tls-strong", *, threshold=None, config=None, scan=None, extra=()):
    t = threshold or TlsThreshold(12)
    scope = "all public and administrative TLS endpoints, including alternate listeners"
    r = RequirementContext("ENC-02.TLS", "synthetic-customer-transport", "2026.1",
                           "Synthetic customer policy owner", date(2026, 10, 1),
                           "Acme Analytics", "production", scope, 90,
                           "RFC 9325 sections 3.1.1 and 3.1.2; customer minimum policy")
    policy = document("tls-customer-policy", f"SYNTHETIC approved policy: minimum enabled TLS {t.minimum_version // 10}.{t.minimum_version % 10}; reject deprecated protocols on every public and administrative listener; configuration and operating scans within 90 days.", scope, kind="policy")
    config = config or document("tls-config", "\n".join((
        "SYNTHETIC production configuration: minimum enabled protocol is TLS 1.2 on all inventoried listeners.",
        "SSL and TLS 1.0/1.1 are disabled on every enabled listener; no legacy fallback listener is enabled.",
        "Configuration inventory reconciles every public, admin and alternate listener for Acme Analytics production; no endpoint is excluded.",
    )), scope, kind="configuration")
    scan = scan or document("tls-scan", "\n".join((
        "SYNTHETIC operating scan executed 2026-10-14: every listener negotiated a minimum of TLS 1.2.",
        "Every endpoint rejected SSL and TLS 1.0/1.1 handshakes, including alternate listeners.",
        "Tester reconciled the complete production public/admin endpoint inventory and tested every listener; none were omitted.",
    )), scope)
    ps = tuple(proposal(d, dim, line, value) for d in (config, scan)
               for dim, line, value in (("minimum_version", 1, 12), ("legacy_rejected", 2, True), ("scope_complete", 3, True)))
    return ControlCase(case_id, "Complete endpoint configuration and operating scans", "Transport encryption (TLS)",
                       r, t,
                       (policy, config, scan) + tuple(extra), ps, AS_OF, evaluate_tls, tls_direction, TLS_SIGNALS, "TLS-1.0")


def _dr_case(case_id="dr-strong", *, threshold=None, report=None, extra=()):
    t = threshold or DrThreshold(365, 240, 60)
    scope = "complete production recovery service: application, database, identity and backup dependencies"
    r = RequirementContext("BCP-01.DR", "synthetic-customer-recovery", "2026.1",
                           "Synthetic customer policy owner", date(2026, 10, 1),
                           "Acme Analytics", "production", scope, 400,
                           "NIST SP 800-34 Rev.1 section 3.6; customer cadence and recovery objectives")
    plan = document("dr-plan", f"SYNTHETIC approved recovery plan: exercise the full production service every {t.max_test_age_days} days; customer RTO {t.max_rto_minutes} minutes and RPO {t.max_rpo_minutes} minutes. Plan targets do not prove achieved results.", scope, kind="policy")
    report = report or document("dr-exercise", "\n".join((
        "SYNTHETIC executed exercise 2026-10-14: production service recovery completed and independently witnessed; not a planned tabletop.",
        "The exercised scope included the complete application, database, identity, backup and restoration dependencies; the inventory was reconciled.",
        "Achieved recovery time (RTO) was 120 minutes from invocation to successful service validation.",
        "Achieved recovery point (RPO) was 15 minutes of data loss, verified by recovered transaction timestamps.",
    )), scope)
    ps = tuple(proposal(report, dim, line, value) for dim, line, value in (
        ("completed", 1, True), ("scope_complete", 2, True),
        ("achieved_rto_minutes", 3, 120), ("achieved_rpo_minutes", 4, 15)))
    return ControlCase(case_id, "Completed full-service exercise with achieved recovery objectives", "Disaster-recovery testing",
                       r, t, (plan, report) + tuple(extra), ps, AS_OF,
                       evaluate_dr, dr_direction, DR_SIGNALS, "DR-1.0")


def control_pilot_cases():
    tls = _tls_case()
    dr = _dr_case()
    cases = [tls, dr, replace(_tls_case("tls-strict", threshold=TlsThreshold(13)), title="Same evidence, stricter customer TLS 1.3 threshold"),
             replace(_dr_case("dr-strict", threshold=DrThreshold(90, 60, 5)), title="Same exercise, stricter customer recovery objectives")]
    for base in (tls, dr):
        family = "tls" if base is tls else "dr"
        scope = base.requirement.scope
        dim, bad = ("minimum_version", 10) if base is tls else ("achieved_rto_minutes", 480)
        text = ("SYNTHETIC current scan: enabled alternate administrative listener negotiates TLS 1.0; this legacy exception remains active."
                if base is tls else "SYNTHETIC completed recovery test: the excluded identity dependency failed; achieved RTO was 480 minutes, an unresolved overrun.")
        for suffix, kind, title in (("exception", "test", "Current technical exception alongside strong evidence"),
                                     ("reported", "assertion", "Vendor-reported exception without operating proof"),
                                     ("conflict", "test", "Opposed current documents for the same subject")):
            d = document(family + "-" + suffix, text, scope, kind=kind)
            p = proposal(d, dim, 1, bad, subject="complete scope" if suffix == "conflict" else "alternate endpoint" if base is tls else "dependency exercise")
            cases.append(replace(base, case_id=family + "-" + suffix, title=title,
                                 documents=base.documents + (d,), proposals=base.proposals + (p,)))
        for suffix, change, title in (
            ("stale", {"observed_on": date(2025, 1, 1)}, "Outdated operating evidence"),
            ("scope", {"service": "Acme Labs"}, "Operating evidence belongs to another service"),
            ("statement", {"evidence_kind": "assertion"}, "Vendor statements only; no operating proof"),
        ):
            docs = tuple(replace(d, **change) if (d.evidence_kind != "policy" if suffix == "statement" else d.evidence_kind == "test") else d
                         for d in base.documents)
            by_id = {d.document_id: d for d in docs}
            ps = tuple(replace(p, source_fingerprint=bind_evidence(by_id[p.source_id.split(":")[0]]).fingerprint)
                       for p in base.proposals)
            cases.append(replace(base, case_id=family + "-" + suffix, title=title, documents=docs, proposals=ps))
    return tuple(cases)
