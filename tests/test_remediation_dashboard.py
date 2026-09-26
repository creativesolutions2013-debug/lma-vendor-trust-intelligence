from dataclasses import dataclass
from datetime import date

from src.remediation_dashboard import (
    summarize_remediation,
)


@dataclass
class Finding:
    vendor_id: int
    severity: str
    status: str
    target_date: str | None


TODAY = date(2026, 9, 25)


def test_empty_portfolio_has_zero_metrics():
    result = summarize_remediation(
        [],
        today=TODAY,
    )

    assert result.open_findings == 0
    assert result.overdue_findings == 0
    assert result.sla_breach_rate == 0


def test_counts_overdue_and_due_soon():
    findings = [
        Finding(
            1,
            "High",
            "Open",
            "2026-09-20",
        ),
        Finding(
            2,
            "High",
            "In Remediation",
            "2026-09-30",
        ),
    ]

    result = summarize_remediation(
        findings,
        today=TODAY,
    )

    assert result.overdue_findings == 1
    assert result.due_soon_findings == 1


def test_counts_unique_vendors_with_escalations():
    findings = [
        Finding(
            1,
            "High",
            "Open",
            "2026-09-20",
        ),
        Finding(
            1,
            "Critical",
            "Open",
            "2026-09-24",
        ),
        Finding(
            2,
            "Moderate",
            "Open",
            None,
        ),
    ]

    result = summarize_remediation(
        findings,
        today=TODAY,
    )

    assert (
        result.vendors_with_escalations
        == 2
    )


def test_sla_breach_rate_uses_open_findings():
    findings = [
        Finding(
            1,
            "High",
            "Open",
            "2026-09-20",
        ),
        Finding(
            2,
            "Low",
            "Open",
            "2026-12-01",
        ),
        Finding(
            3,
            "High",
            "Closed",
            "2026-09-01",
        ),
    ]

    result = summarize_remediation(
        findings,
        today=TODAY,
    )

    assert result.open_findings == 2
    assert result.sla_breach_rate == 50.0


def test_oldest_overdue_days_is_reported():
    findings = [
        Finding(
            1,
            "High",
            "Open",
            "2026-09-20",
        ),
        Finding(
            2,
            "High",
            "Open",
            "2026-08-01",
        ),
    ]

    result = summarize_remediation(
        findings,
        today=TODAY,
    )

    assert result.oldest_overdue_days == 55


def test_overdue_findings_are_aged_into_buckets():
    findings = [
        Finding(
            1,
            "High",
            "Open",
            "2026-09-22",
        ),
        Finding(
            2,
            "High",
            "Open",
            "2026-09-10",
        ),
        Finding(
            3,
            "High",
            "Open",
            "2026-08-10",
        ),
        Finding(
            4,
            "High",
            "Open",
            "2026-07-01",
        ),
    ]

    result = summarize_remediation(
        findings,
        today=TODAY,
    )

    assert result.aging_1_7 == 1
    assert result.aging_8_30 == 1
    assert result.aging_31_60 == 1
    assert result.aging_61_plus == 1


def test_closed_findings_do_not_affect_portfolio():
    findings = [
        Finding(
            1,
            "Critical",
            "Closed",
            "2026-01-01",
        ),
    ]

    result = summarize_remediation(
        findings,
        today=TODAY,
    )

    assert result.open_findings == 0
    assert result.overdue_findings == 0
    assert result.oldest_overdue_days == 0
