"""Hand-authored multi-document synthetic TLS/DR packages, never extracted truth."""
from dataclasses import replace
from datetime import date

from src.control_assurance import (
    ControlCase, CustomerThreshold, DomainEvaluator, EvidenceExpectation, Observation,
    RequirementContext, bind_relevance,
)
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
                       (policy, config, scan) + tuple(extra), ps, AS_OF,
                       DomainEvaluator("TLS-1.0", evaluate_tls, tls_direction, TLS_SIGNALS))


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
                       DomainEvaluator("DR-1.0", evaluate_dr, dr_direction, DR_SIGNALS))


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


def fallback_pilot_cases():
    """An unrelated requirement with supplied criteria and no technical rules.

    Proposed meanings and concern labels are hand-authored draft inputs, never
    inferred from keywords or computed against the acceptance threshold.
    """
    scope = "all production assets in the customer service inventory"
    requirement = RequirementContext(
        "VM-01.REMEDIATION", "synthetic-customer-vulnerability", "2026.1",
        "Synthetic customer policy owner", date(2026, 10, 1),
        "Acme Analytics", "production", scope, 90,
        business_use_case="Customer production data processing on vendor-managed assets",
        required_evidence=("dated critical-vulnerability remediation tickets and independent closure retests for all in-scope assets",),
        assurance_type="Implementation records and independently verified operating closure",
        evidence_expectation=EvidenceExpectation("2026.1", ("configuration", "test", "assertion")),
    )
    threshold = CustomerThreshold(
        "Remediate critical vulnerabilities within 30 calendar days of discovery "
        "on every in-scope production asset; verify closure by independent retest."
    )
    tickets = document("vm-remediation-tickets", (
        "SYNTHETIC vendor ticket export: critical issue CV-SYNTH-01 on the production API was recorded as closed 25 days after discovery.\n"
        "This ticket export does not contain independent closure retests or a reconciliation to the full asset inventory."
    ), scope, kind="configuration")
    exception = document("vm-exception-response", (
        "SYNTHETIC vendor response: one critical issue on a production worker remains unresolved 45 days after discovery; "
        "the vendor reports an exception but has not supplied a retest or a complete asset reconciliation."
    ), scope, kind="assertion")
    candidates = (
        proposal(tickets, "reported_closure_days", 1, 25, fact_id="vm-reported-closure"),
        replace(proposal(exception, "reported_open_days", 1, 45, fact_id="vm-reported-exception"),
                concern="potential_exception"),
    )
    present = ControlCase("vm-present", "Remediation records and a reported unresolved exception",
                          "Vulnerability remediation", requirement, threshold,
                          (tickets, exception), candidates, AS_OF,
                          relevance=(
                              bind_relevance(requirement, threshold, tickets,
                                             rationale="Remediation ticket records address the customer's production critical-vulnerability timeline; closure retests remain missing."),
                              bind_relevance(requirement, threshold, exception,
                                             rationale="The response reports a critical production vulnerability remaining open under the same customer remediation criterion."),
                          ))
    missing = replace(present, case_id="vm-missing", title="No remediation evidence supplied",
                      documents=(), proposals=(), relevance=())
    return present, missing


def suitability_pilot_cases():
    """Requirement-specific documentation versus operational review eligibility."""
    operational = fallback_pilot_cases()[0]
    requirement = replace(
        operational.requirement, requirement_id="GOV-01.POLICY", customer_policy_id="synthetic-customer-governance",
        required_evidence=("current approved information-security policy covering the assessed service",),
        assurance_type="Documented governance; operating effectiveness is not asserted",
        evidence_expectation=EvidenceExpectation("2026.1", ("policy",)),
    )
    threshold = CustomerThreshold("Maintain an approved information-security policy for the assessed service, with an assigned owner and review within the last 90 days.")
    policy = document("approved-security-policy", (
        "SYNTHETIC information-security policy: approved by the Acme Analytics Security Committee on 2026-10-14, "
        "covering Acme Analytics production assets; owner: Security Governance. Review completed 2026-10-14. "
        "This document states governance responsibilities and does not assert technical operating effectiveness."
    ), requirement.scope, kind="policy")
    governance = ControlCase(
        "gov-policy", "Current approved policy for documented governance", "Documented security governance",
        requirement, threshold, (policy,), (proposal(policy, "documented_policy", 1, True),), AS_OF,
        relevance=(bind_relevance(requirement, threshold, policy,
                                 rationale="The document names the assessed production service, owner, approval and review dates required by the documentation criterion."),),
    )
    missing = replace(governance, case_id="gov-missing", title="No governance policy supplied",
                      documents=(), proposals=(), relevance=())
    intent = document("remediation-intent-policy", "SYNTHETIC vulnerability policy requires critical-issue remediation within 30 days and independent closure retests; no executed tickets or retests are supplied.", operational.requirement.scope, kind="policy")
    policy_only = replace(
        operational, case_id="vm-policy-only", title="Related policy intent without operational remediation records",
        documents=(intent,), proposals=(proposal(intent, "documented_remediation_intent", 1, True),),
        relevance=(bind_relevance(operational.requirement, operational.threshold, intent,
                                 rationale="The policy addresses the remediation topic but provides design intent only, not the required operational records."),),
    )
    unrelated = document("clock-configuration", "SYNTHETIC production configuration export: servers use the designated network time source. No vulnerability remediation records are included.", operational.requirement.scope, kind="configuration")
    irrelevant = replace(operational, case_id="vm-unrelated", title="Current configuration unrelated to remediation",
                         documents=(unrelated,), proposals=(), relevance=())
    return governance, missing, policy_only, irrelevant
