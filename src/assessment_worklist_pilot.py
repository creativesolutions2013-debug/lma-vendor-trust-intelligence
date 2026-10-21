"""Synthetic packages for the read-only M4A-1 integration preview.

Every proposed interpretation starts unreviewed. These fixtures do not create
FactReviews, dispositions or governed decisions. Existing M3D source packages are
reused rather than duplicating parsing or technical evaluation.
"""
from dataclasses import dataclass, replace

from src.applicability import ApplicabilityResult
from src.assessment_worklist import (
    AssessmentScope, AssuranceLink, EvidenceNeed, RequirementMapping,
    ScopedLegacyEvidence,
)
from src.control_assurance_pilot import (
    AS_OF, control_pilot_cases, fallback_pilot_cases, suitability_pilot_cases,
)
from src.control_sufficiency import EvidenceControlClaim
from src.tiering import ControlRequirement, EvidenceRequirement


@dataclass(frozen=True)
class LegacyEvidenceMetadata:
    """Inventory-only inputs to the existing orchestrator, never source proof."""

    id: int
    document_type: str
    document_name: str
    status: str = "Current"
    expiration_date: str | None = None
    exceptions_count: int = 0
    detected_exceptions: str = ""
    extraction_confidence: float = 0.95


@dataclass(frozen=True)
class WorklistScenario:
    scenario_id: str
    title: str
    scope: AssessmentScope
    applicability: ApplicabilityResult
    requirements: tuple[RequirementMapping, ...]
    assurance_links: tuple[AssuranceLink, ...]
    legacy_evidence: tuple[ScopedLegacyEvidence, ...] = ()
    control_claims: tuple[EvidenceControlClaim, ...] = ()


def worklist_scenarios() -> tuple[WorklistScenario, ...]:
    """One relationship and four explicit requirement mappings, recomputed fresh."""
    technical = {case.case_id: case for case in control_pilot_cases()}
    documentation = {case.case_id: case for case in suitability_pilot_cases()}
    tls = technical["tls-strong"]
    dr_complete = technical["dr-strong"]
    # A plan is supplied; the completed exercise itself is genuinely absent.
    dr_plan_only = replace(
        dr_complete, case_id="m4a-dr-plan-only", title="Plan supplied; completed exercise missing",
        documents=tuple(d for d in dr_complete.documents if d.evidence_kind == "policy"),
        proposals=(),
    )
    governance = documentation["gov-policy"]
    remediation = next(c for c in fallback_pilot_cases() if c.case_id == "vm-present")
    scope = AssessmentScope("synthetic-engagement-acme-production", "Acme Analytics", "production", AS_OF)
    controls = (
        ControlRequirement("ENC-01", "Data protection", "Customer transport encryption requirement"),
        ControlRequirement("BCP-01", "Recovery", "Customer completed recovery exercise requirement"),
        ControlRequirement("CUSTOM-GOV-42", "Documented governance", "Customer approved service security policy"),
        ControlRequirement("CUSTOM-VM-42", "Vulnerability remediation", "Customer remediation and exception review"),
    )
    applicability = ApplicabilityResult(
        controls,
        (
            EvidenceRequirement("M4A-SOC", "SOC 2 Type II or equivalent assurance report"),
            EvidenceRequirement("M4A-ARCH", "Architecture Diagram"),
            EvidenceRequirement("M4A-DR", "BCP / DR Test"),
            EvidenceRequirement("M4A-POLICY", "Security Policy"),
        ),
        (), True, ("Synthetic applicable customer requirements; independent governance remains required.",),
    )
    tls_configuration = EvidenceNeed(
        "enabled-tls-configuration",
        "Enabled protocol minimum, deprecated-protocol rejection and full listener coverage.",
        "Current production configuration export covering every public/admin/alternate listener.",
        "Provide the current production listener configuration showing enabled minimum, deprecated-protocol rejection and the reconciled endpoint inventory.",
        ("configuration",), ("minimum_version", "legacy_rejected", "scope_complete"), 90,
    )
    tls_scan = EvidenceNeed(
        "operating-tls-scan",
        "Actual protocol negotiation and rejection across the full listener inventory.",
        "Dated full-endpoint protocol-negotiation and rejection scan within 90 days.",
        "Provide the dated production scan covering every listener and showing actual negotiated minimum and rejection of deprecated protocols.",
        ("test",), ("minimum_version", "legacy_rejected", "scope_complete"), 90,
    )
    dr_exercise = EvidenceNeed(
        "completed-recovery-exercise",
        "Completed full-service exercise and achieved RTO/RPO against the customer's annual 240/60-minute objectives.",
        "One dated completed full-service recovery exercise record, including dependency coverage and achieved RTO/RPO, within 365 days.",
        "Provide the most recent completed Acme Analytics production recovery exercise record, including application/database/identity/backup coverage and achieved RTO ≤ 240 minutes and RPO ≤ 60 minutes.",
        ("test",), ("completed", "scope_complete", "achieved_rto_minutes", "achieved_rpo_minutes"), 365,
    )
    governance_policy = EvidenceNeed(
        "approved-service-policy",
        "Current approved security policy covering the assessed service, owner and review date.",
        "Approved service-specific security policy reviewed within 90 days.",
        "Provide the current approved Acme Analytics production security policy with its owner, approval and review dates.",
        ("policy",), ("documented_policy",), 90,
    )
    remediation_records = EvidenceNeed(
        "remediation-record-context",
        "Meaning and scope of the supplied remediation and unresolved-exception records; independent closure remains unverified.",
        "Dated in-scope remediation records, explicit exceptions and independent closure retests.",
        "Provide the specific missing scoped remediation or closure record identified after analyst review of the supplied exception.",
        ("configuration", "test", "assertion"), ("reported_closure_days", "reported_open_days"), 90,
    )
    requirements = (
        RequirementMapping("ENC-01", tls.requirement, tls.threshold, (tls_configuration, tls_scan)),
        RequirementMapping("BCP-01", dr_complete.requirement, dr_complete.threshold, (dr_exercise,)),
        RequirementMapping("CUSTOM-GOV-42", governance.requirement, governance.threshold, (governance_policy,)),
        RequirementMapping("CUSTOM-VM-42", remediation.requirement, remediation.threshold, (remediation_records,)),
    )
    initial_links = (
        AssuranceLink(scope.engagement_id, "ENC-01", tls),
        AssuranceLink(scope.engagement_id, "BCP-01", dr_plan_only),
        AssuranceLink(scope.engagement_id, "CUSTOM-GOV-42", governance),
        AssuranceLink(scope.engagement_id, "CUSTOM-VM-42", remediation),
    )
    legacy_evidence = tuple(
        ScopedLegacyEvidence(scope.engagement_id, scope.service, scope.environment, record)
        for record in (
            LegacyEvidenceMetadata(901, "SOC 2 Type II", "synthetic-legacy-assurance-inventory.txt"),
            LegacyEvidenceMetadata(902, "Architecture Diagram", "synthetic-legacy-architecture-inventory.txt"),
            LegacyEvidenceMetadata(903, "Security Policy", "synthetic-legacy-policy-inventory.txt"),
        )
    )
    initial = WorklistScenario(
        "initial", "Initial evidence: recovery plan supplied, executed exercise missing",
        scope, applicability, requirements, initial_links, legacy_evidence,
    )
    closed = replace(
        initial, scenario_id="gap-closed", title="Completed recovery exercise added — meanings still require analyst review",
        assurance_links=tuple(replace(link, case=dr_complete) if link.control_id == "BCP-01" else link for link in initial_links),
    )
    adverse = replace(
        initial, scenario_id="adverse", title="Active alternate TLS exception reported in current technical evidence — interpretation unconfirmed",
        assurance_links=tuple(replace(link, case=technical["tls-exception"]) if link.control_id == "ENC-01" else link for link in initial_links),
    )
    conflict = replace(
        initial, scenario_id="mapping-conflict", title="Explicit ID mismatch: TLS subrequirement cannot replace the legacy control ID",
        assurance_links=tuple(replace(link, control_id="ENC-02.TLS") if link.control_id == "ENC-01" else link for link in initial_links),
    )
    return initial, closed, adverse, conflict
