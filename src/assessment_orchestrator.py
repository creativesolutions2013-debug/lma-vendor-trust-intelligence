from dataclasses import dataclass
from typing import Iterable, Tuple

from src.applicability import ApplicabilityResult
from src.control_sufficiency import (
    EvidenceControlClaim,
    evaluate_control_set,
)
from src.targeted_gap import analyze_targeted_evidence_gaps


ORCHESTRATOR_POLICY_VERSION = "AO-1.1"


@dataclass(frozen=True)
class AssessmentQuestion:
    question_id: str
    control_id: str
    question: str


@dataclass(frozen=True)
class ControlWorkItem:
    control_id: str
    domain: str
    requirement: str

    disposition: str
    workflow_action: str
    reason: str

    question_id: str | None = None
    question: str | None = None

    evidence_requirements: Tuple[str, ...] = ()

    sufficiency_status: str | None = None
    supporting_evidence_ids: Tuple[int, ...] = ()
    review_evidence_ids: Tuple[int, ...] = ()


@dataclass(frozen=True)
class AssessmentWorkPlan:
    total_controls: int
    evidence_satisfied_controls: int
    analyst_validation_controls: int
    vendor_input_controls: int

    questions_generated: int
    questions_suppressed: int
    questionnaire_reduction_percent: int

    items: Tuple[ControlWorkItem, ...]

    policy_version: str = ORCHESTRATOR_POLICY_VERSION


QUESTION_LIBRARY = {
    "GOV-01": AssessmentQuestion(
        question_id="Q-GOV-01",
        control_id="GOV-01",
        question=(
            "Describe how responsibility and accountability "
            "for information security are assigned."
        ),
    ),
    "IAM-01": AssessmentQuestion(
        question_id="Q-IAM-01",
        control_id="IAM-01",
        question=(
            "Describe how user access is approved, provisioned, "
            "reviewed, and revoked."
        ),
    ),
    "PAM-01": AssessmentQuestion(
        question_id="Q-PAM-01",
        control_id="PAM-01",
        question=(
            "Describe how privileged access is restricted, "
            "authenticated, monitored, and periodically reviewed."
        ),
    ),
    "ENC-01": AssessmentQuestion(
        question_id="Q-ENC-01",
        control_id="ENC-01",
        question=(
            "Describe how sensitive data is encrypted in transit "
            "and at rest and how encryption keys are managed."
        ),
    ),
    "VM-01": AssessmentQuestion(
        question_id="Q-VM-01",
        control_id="VM-01",
        question=(
            "Describe your vulnerability-management program, "
            "including scanning frequency and remediation SLAs."
        ),
    ),
    "SDLC-01": AssessmentQuestion(
        question_id="Q-SDLC-01",
        control_id="SDLC-01",
        question=(
            "Describe the security controls integrated into your "
            "software-development lifecycle."
        ),
    ),
    "LOG-01": AssessmentQuestion(
        question_id="Q-LOG-01",
        control_id="LOG-01",
        question=(
            "Describe security logging, monitoring, alerting, "
            "and log-retention practices."
        ),
    ),
    "IR-01": AssessmentQuestion(
        question_id="Q-IR-01",
        control_id="IR-01",
        question=(
            "Describe your incident-response process, including "
            "customer notification and escalation procedures."
        ),
    ),
    "BCP-01": AssessmentQuestion(
        question_id="Q-BCP-01",
        control_id="BCP-01",
        question=(
            "Describe your business-continuity and disaster-"
            "recovery capabilities and the latest test performed."
        ),
    ),
    "TPRM-01": AssessmentQuestion(
        question_id="Q-TPRM-01",
        control_id="TPRM-01",
        question=(
            "Describe how security risks from subprocessors and "
            "other critical fourth parties are assessed and monitored."
        ),
    ),
    "DATA-01": AssessmentQuestion(
        question_id="Q-DATA-01",
        control_id="DATA-01",
        question=(
            "Describe data retention, deletion, minimization, "
            "and secure-disposal practices."
        ),
    ),
    "AI-01": AssessmentQuestion(
        question_id="Q-AI-01",
        control_id="AI-01",
        question=(
            "Describe governance and accountability for AI "
            "development, deployment, and acceptable use."
        ),
    ),
    "AI-02": AssessmentQuestion(
        question_id="Q-AI-02",
        control_id="AI-02",
        question=(
            "Describe how customer data, prompts, model inputs, "
            "outputs, and model access are protected."
        ),
    ),
    "AI-03": AssessmentQuestion(
        question_id="Q-AI-03",
        control_id="AI-03",
        question=(
            "Describe how AI model changes, evaluations, "
            "failures, and AI-related incidents are managed."
        ),
    ),
    "REG-01": AssessmentQuestion(
        question_id="Q-REG-01",
        control_id="REG-01",
        question=(
            "Describe controls used to meet the regulatory "
            "requirements applicable to the data you process."
        ),
    ),
}


CONTROL_EVIDENCE_MAP = {
    "GOV-01": (
        "SOC 2 Type II or equivalent assurance report",
        "Security Policy",
    ),
    "IAM-01": (
        "SOC 2 Type II or equivalent assurance report",
        "Security Policy",
    ),
    "PAM-01": (
        "SOC 2 Type II or equivalent assurance report",
        "Security Policy",
    ),
    "ENC-01": (
        "SOC 2 Type II or equivalent assurance report",
        "Architecture Diagram",
    ),
    "VM-01": (
        "Penetration Test",
        "SOC 2 Type II or equivalent assurance report",
    ),
    "SDLC-01": (
        "SOC 2 Type II or equivalent assurance report",
        "Penetration Test",
    ),
    "LOG-01": (
        "SOC 2 Type II or equivalent assurance report",
    ),
    "IR-01": (
        "Incident Response Plan",
        "SOC 2 Type II or equivalent assurance report",
    ),
    "BCP-01": (
        "BCP / DR Test",
        "SOC 2 Type II or equivalent assurance report",
    ),
    "TPRM-01": (
        "SOC 2 Type II or equivalent assurance report",
        "Security Policy",
    ),
    "DATA-01": (
        "SOC 2 Type II or equivalent assurance report",
        "Security Policy",
    ),
    "AI-01": (
        "AI governance / acceptable use documentation",
    ),
    "AI-02": (
        "AI architecture or data-flow documentation",
    ),
    "AI-03": (
        "AI governance / acceptable use documentation",
        "AI architecture or data-flow documentation",
    ),
    "REG-01": (
        "Applicable regulatory assurance evidence",
    ),
}


def _required_evidence_names(
    applicability: ApplicabilityResult,
) -> set[str]:
    return {
        evidence.evidence_type
        for evidence in applicability.evidence
    }


def _question_for_control(
    control_id: str,
) -> AssessmentQuestion | None:
    return QUESTION_LIBRARY.get(control_id)


def build_assessment_work_plan(
    applicability: ApplicabilityResult,
    evidence_records: Iterable,
    control_claims: Iterable[EvidenceControlClaim] = (),
) -> AssessmentWorkPlan:

    evidence_records = tuple(evidence_records)
    control_claims = tuple(control_claims)

    required_evidence_names = _required_evidence_names(
        applicability
    )

    # -------------------------------------------------
    # AO-1.1 control-level sufficiency path
    # -------------------------------------------------

    sufficiency_by_control = {}

    if control_claims:
        control_ids = [
            control.control_id
            for control in applicability.controls
        ]

        sufficiency_decisions = evaluate_control_set(
            control_ids,
            evidence_records,
            control_claims,
        )

        sufficiency_by_control = {
            decision.control_id: decision
            for decision in sufficiency_decisions
        }

    # -------------------------------------------------
    # Document-level fallback
    # -------------------------------------------------

    gap_analysis = analyze_targeted_evidence_gaps(
        sorted(required_evidence_names),
        evidence_records,
    )

    gap_by_requirement = {
        item.requirement: item
        for item in gap_analysis.items
    }

    work_items = []

    for control in applicability.controls:

        mapped = CONTROL_EVIDENCE_MAP.get(
            control.control_id,
            (),
        )

        relevant_evidence = tuple(
            requirement
            for requirement in mapped
            if requirement in required_evidence_names
        )

        sufficiency = sufficiency_by_control.get(
            control.control_id
        )

        # =================================================
        # CONTROL-LEVEL SUFFICIENCY PATH
        # =================================================

        if sufficiency is not None:

            reason = " ".join(
                sufficiency.reasons
            )

            if sufficiency.status == "SUPPORTED":
                work_items.append(
                    ControlWorkItem(
                        control_id=control.control_id,
                        domain=control.domain,
                        requirement=control.requirement,
                        disposition="Evidence Supported",
                        workflow_action="Reuse Evidence",
                        reason=reason,
                        evidence_requirements=relevant_evidence,
                        sufficiency_status="SUPPORTED",
                        supporting_evidence_ids=(
                            sufficiency.supporting_evidence_ids
                        ),
                        review_evidence_ids=(
                            sufficiency.evidence_review_ids
                        ),
                    )
                )
                continue

            if sufficiency.status == "PARTIAL":
                work_items.append(
                    ControlWorkItem(
                        control_id=control.control_id,
                        domain=control.domain,
                        requirement=control.requirement,
                        disposition="Partial Evidence",
                        workflow_action="Analyst Validate",
                        reason=reason,
                        evidence_requirements=relevant_evidence,
                        sufficiency_status="PARTIAL",
                        supporting_evidence_ids=(
                            sufficiency.supporting_evidence_ids
                        ),
                        review_evidence_ids=(
                            sufficiency.evidence_review_ids
                        ),
                    )
                )
                continue

            if sufficiency.status == "REVIEW":
                work_items.append(
                    ControlWorkItem(
                        control_id=control.control_id,
                        domain=control.domain,
                        requirement=control.requirement,
                        disposition="Pending Validation",
                        workflow_action="Analyst Validate",
                        reason=reason,
                        evidence_requirements=relevant_evidence,
                        sufficiency_status="REVIEW",
                        supporting_evidence_ids=(
                            sufficiency.supporting_evidence_ids
                        ),
                        review_evidence_ids=(
                            sufficiency.evidence_review_ids
                        ),
                    )
                )
                continue

            if sufficiency.status == "UNSUPPORTED":
                question = _question_for_control(
                    control.control_id
                )

                work_items.append(
                    ControlWorkItem(
                        control_id=control.control_id,
                        domain=control.domain,
                        requirement=control.requirement,
                        disposition="Control Unproven",
                        workflow_action="Ask Vendor",
                        reason=reason,
                        question_id=(
                            question.question_id
                            if question
                            else None
                        ),
                        question=(
                            question.question
                            if question
                            else None
                        ),
                        evidence_requirements=relevant_evidence,
                        sufficiency_status="UNSUPPORTED",
                        supporting_evidence_ids=(),
                        review_evidence_ids=(),
                    )
                )
                continue

        # =================================================
        # DOCUMENT-LEVEL FALLBACK
        # =================================================

        evidence_states = [
            gap_by_requirement[requirement]
            for requirement in relevant_evidence
            if requirement in gap_by_requirement
        ]

        if not evidence_states:
            question = _question_for_control(
                control.control_id
            )

            work_items.append(
                ControlWorkItem(
                    control_id=control.control_id,
                    domain=control.domain,
                    requirement=control.requirement,
                    disposition="Unresolved",
                    workflow_action="Ask Vendor",
                    reason=(
                        "No reusable required evidence currently "
                        "supports this control; targeted vendor "
                        "input is required."
                    ),
                    question_id=(
                        question.question_id
                        if question
                        else None
                    ),
                    question=(
                        question.question
                        if question
                        else None
                    ),
                    evidence_requirements=(),
                )
            )
            continue

        actions = {
            item.workflow_action
            for item in evidence_states
        }

        if "Request Vendor" in actions:
            question = _question_for_control(
                control.control_id
            )

            work_items.append(
                ControlWorkItem(
                    control_id=control.control_id,
                    domain=control.domain,
                    requirement=control.requirement,
                    disposition="Evidence Gap",
                    workflow_action="Ask Vendor",
                    reason=(
                        "One or more required evidence items are "
                        "missing or expired. Request only the "
                        "unresolved information."
                    ),
                    question_id=(
                        question.question_id
                        if question
                        else None
                    ),
                    question=(
                        question.question
                        if question
                        else None
                    ),
                    evidence_requirements=tuple(
                        item.requirement
                        for item in evidence_states
                        if item.workflow_action
                        == "Request Vendor"
                    ),
                )
            )
            continue

        if "Analyst Validate" in actions:
            work_items.append(
                ControlWorkItem(
                    control_id=control.control_id,
                    domain=control.domain,
                    requirement=control.requirement,
                    disposition="Pending Validation",
                    workflow_action="Analyst Validate",
                    reason=(
                        "Relevant evidence exists but requires "
                        "analyst validation before it can be "
                        "relied upon."
                    ),
                    evidence_requirements=relevant_evidence,
                )
            )
            continue

        work_items.append(
            ControlWorkItem(
                control_id=control.control_id,
                domain=control.domain,
                requirement=control.requirement,
                disposition="Evidence Supported",
                workflow_action="Reuse Evidence",
                reason=(
                    "Current evidence supports the control and "
                    "has no identified reuse blocker. Vendor "
                    "questioning is suppressed."
                ),
                evidence_requirements=relevant_evidence,
            )
        )

    total_controls = len(work_items)

    evidence_satisfied = sum(
        1
        for item in work_items
        if item.workflow_action == "Reuse Evidence"
    )

    analyst_validation = sum(
        1
        for item in work_items
        if item.workflow_action == "Analyst Validate"
    )

    vendor_input = sum(
        1
        for item in work_items
        if item.workflow_action == "Ask Vendor"
    )

    generated = sum(
        1
        for item in work_items
        if item.question
    )

    suppressed = (
        evidence_satisfied
        + analyst_validation
    )

    reduction_percent = (
        round(
            (suppressed / total_controls) * 100
        )
        if total_controls
        else 100
    )

    return AssessmentWorkPlan(
        total_controls=total_controls,
        evidence_satisfied_controls=evidence_satisfied,
        analyst_validation_controls=analyst_validation,
        vendor_input_controls=vendor_input,
        questions_generated=generated,
        questions_suppressed=suppressed,
        questionnaire_reduction_percent=reduction_percent,
        items=tuple(work_items),
    )