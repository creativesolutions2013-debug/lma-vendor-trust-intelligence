from dataclasses import dataclass
from datetime import date

from src.remediation import (
    calculate_target_date,
    evaluate_remediation,
    sla_days_for_severity,
)


@dataclass
class Finding:
    severity: str
    status: str
    target_date: str | None


def test_critical_findings_have_seven_day_sla():
    assert sla_days_for_severity(
        "Critical"
    ) == 7


def test_high_findings_have_thirty_day_sla():
    assert sla_days_for_severity(
        "High"
    ) == 30


def test_default_target_date_uses_severity_sla():
    target = calculate_target_date(
        "High",
        start_date=date(2026, 9, 25),
    )

    assert target == date(
        2026,
        10,
        25,
    )


def test_open_past_due_finding_is_overdue():
    finding = Finding(
        severity="High",
        status="Open",
        target_date="2026-09-20",
    )

    result = evaluate_remediation(
        finding,
        today=date(2026, 9, 25),
    )

    assert result.status == "Overdue"
    assert result.overdue is True
    assert result.escalation_required is True


def test_closed_finding_is_not_overdue():
    finding = Finding(
        severity="Critical",
        status="Closed",
        target_date="2026-09-20",
    )

    result = evaluate_remediation(
        finding,
        today=date(2026, 9, 25),
    )

    assert result.status == "Closed"
    assert result.overdue is False
    assert result.escalation_required is False


def test_high_finding_due_within_seven_days_escalates():
    finding = Finding(
        severity="High",
        status="In Remediation",
        target_date="2026-09-30",
    )

    result = evaluate_remediation(
        finding,
        today=date(2026, 9, 25),
    )

    assert result.status == "Due Soon"
    assert result.days_remaining == 5
    assert result.escalation_required is True


def test_missing_target_date_requires_attention():
    finding = Finding(
        severity="Moderate",
        status="Open",
        target_date=None,
    )

    result = evaluate_remediation(
        finding,
        today=date(2026, 9, 25),
    )

    assert result.status == (
        "Target Date Missing"
    )
    assert (
        result.escalation_required
        is True
    )
