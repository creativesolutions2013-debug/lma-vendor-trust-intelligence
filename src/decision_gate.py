from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DecisionReason:
    code: str
    message: str
    blocking: bool


@dataclass(frozen=True)
class VendorDecision:
    outcome: str
    reasons: tuple[DecisionReason, ...]


OPEN_STATUSES = {
    "open",
    "in remediation",
    "not started",
    "in progress",
    "vendor responding",
    "analyst review",
}


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def evaluate_vendor_decision(
    *,
    evidence_completion_percent: float,
    findings: Iterable[object],
    assessments: Iterable[object],
    residual_risk: float,
) -> VendorDecision:
    reasons: list[DecisionReason] = []

    if evidence_completion_percent < 100:
        reasons.append(
            DecisionReason(
                code="evidence_incomplete",
                message=(
                    f"Required evidence coverage is only "
                    f"{evidence_completion_percent:.0f}%."
                ),
                blocking=True,
            )
        )

    for finding in findings:
        severity = _norm(getattr(finding, "severity", None))
        status = _norm(getattr(finding, "status", None))

        if (
            severity in {"critical", "high"}
            and status not in {"closed", "risk accepted"}
        ):
            reasons.append(
                DecisionReason(
                    code="high_risk_finding",
                    message=(
                        f"Open {severity} finding: "
                        f"{getattr(finding, 'title', 'Untitled finding')}."
                    ),
                    blocking=True,
                )
            )

    for assessment in assessments:
        assessment_type = _norm(
            getattr(assessment, "assessment_type", None)
        )
        status = _norm(getattr(assessment, "status", None))

        if (
            "reassessment" in assessment_type
            and status in OPEN_STATUSES
        ):
            reasons.append(
                DecisionReason(
                    code="open_reassessment",
                    message=(
                        "Triggered reassessment remains unresolved: "
                        f"{getattr(assessment, 'assessment_type', 'Reassessment')}."
                    ),
                    blocking=True,
                )
            )

    if residual_risk >= 75:
        reasons.append(
            DecisionReason(
                code="critical_residual_risk",
                message=(
                    f"Residual risk is critical at "
                    f"{residual_risk:.1f}."
                ),
                blocking=True,
            )
        )
    elif residual_risk >= 50:
        reasons.append(
            DecisionReason(
                code="high_residual_risk",
                message=(
                    f"Residual risk is high at "
                    f"{residual_risk:.1f}."
                ),
                blocking=False,
            )
        )

    if any(reason.blocking for reason in reasons):
        outcome = "Further Review Required"
    elif reasons:
        outcome = "Approve with Conditions"
    else:
        outcome = "Approve"

    return VendorDecision(
        outcome=outcome,
        reasons=tuple(reasons),
    )
