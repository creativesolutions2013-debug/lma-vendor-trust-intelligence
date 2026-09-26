from dataclasses import dataclass
from datetime import date
from typing import Iterable

from src.remediation import evaluate_remediation


@dataclass(frozen=True)
class RemediationPortfolio:
    open_findings: int
    overdue_findings: int
    due_soon_findings: int
    vendors_with_escalations: int
    sla_breach_rate: float
    oldest_overdue_days: int
    aging_1_7: int
    aging_8_30: int
    aging_31_60: int
    aging_61_plus: int


def summarize_remediation(
    findings: Iterable[object],
    *,
    today: date | None = None,
) -> RemediationPortfolio:
    open_findings = 0
    overdue = 0
    due_soon = 0

    escalation_vendors: set[int] = set()

    aging_1_7 = 0
    aging_8_30 = 0
    aging_31_60 = 0
    aging_61_plus = 0

    oldest_overdue_days = 0

    for finding in findings:
        state = evaluate_remediation(
            finding,
            today=today,
        )

        if state.status == "Closed":
            continue

        open_findings += 1

        if state.escalation_required:
            vendor_id = getattr(
                finding,
                "vendor_id",
                None,
            )

            if vendor_id is not None:
                escalation_vendors.add(
                    vendor_id
                )

        if state.status == "Due Soon":
            due_soon += 1

        if state.status != "Overdue":
            continue

        overdue += 1

        overdue_days = abs(
            state.days_remaining or 0
        )

        oldest_overdue_days = max(
            oldest_overdue_days,
            overdue_days,
        )

        if overdue_days <= 7:
            aging_1_7 += 1
        elif overdue_days <= 30:
            aging_8_30 += 1
        elif overdue_days <= 60:
            aging_31_60 += 1
        else:
            aging_61_plus += 1

    sla_breach_rate = (
        round(
            (overdue / open_findings) * 100,
            1,
        )
        if open_findings
        else 0.0
    )

    return RemediationPortfolio(
        open_findings=open_findings,
        overdue_findings=overdue,
        due_soon_findings=due_soon,
        vendors_with_escalations=len(
            escalation_vendors
        ),
        sla_breach_rate=sla_breach_rate,
        oldest_overdue_days=(
            oldest_overdue_days
        ),
        aging_1_7=aging_1_7,
        aging_8_30=aging_8_30,
        aging_31_60=aging_31_60,
        aging_61_plus=aging_61_plus,
    )
