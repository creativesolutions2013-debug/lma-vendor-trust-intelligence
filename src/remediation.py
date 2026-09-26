from dataclasses import dataclass
from datetime import date, datetime, timedelta


SLA_DAYS = {
    "critical": 7,
    "high": 30,
    "moderate": 60,
    "medium": 60,
    "low": 90,
}

CLOSED_STATUSES = {
    "closed",
    "resolved",
    "risk accepted",
}


@dataclass(frozen=True)
class RemediationState:
    severity: str
    sla_days: int
    target_date: date | None
    days_remaining: int | None
    status: str
    overdue: bool
    escalation_required: bool


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def sla_days_for_severity(
    severity: str | None,
) -> int:
    return SLA_DAYS.get(
        _norm(severity),
        60,
    )


def calculate_target_date(
    severity: str | None,
    *,
    start_date: date | None = None,
) -> date:
    start = start_date or date.today()

    return start + timedelta(
        days=sla_days_for_severity(severity)
    )


def _parse_date(
    value,
) -> date | None:
    if value is None:
        return None

    if isinstance(value, date):
        return value

    text = str(value).strip()

    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(
                text,
                fmt,
            ).date()
        except ValueError:
            continue

    return None


def evaluate_remediation(
    finding,
    *,
    today: date | None = None,
) -> RemediationState:
    current_date = today or date.today()

    severity = (
        getattr(finding, "severity", None)
        or "Moderate"
    )

    finding_status = _norm(
        getattr(finding, "status", None)
    )

    target_date = _parse_date(
        getattr(finding, "target_date", None)
    )

    sla_days = sla_days_for_severity(
        severity
    )

    if finding_status in CLOSED_STATUSES:
        return RemediationState(
            severity=severity,
            sla_days=sla_days,
            target_date=target_date,
            days_remaining=None,
            status="Closed",
            overdue=False,
            escalation_required=False,
        )

    if target_date is None:
        return RemediationState(
            severity=severity,
            sla_days=sla_days,
            target_date=None,
            days_remaining=None,
            status="Target Date Missing",
            overdue=False,
            escalation_required=True,
        )

    days_remaining = (
        target_date - current_date
    ).days

    if days_remaining < 0:
        return RemediationState(
            severity=severity,
            sla_days=sla_days,
            target_date=target_date,
            days_remaining=days_remaining,
            status="Overdue",
            overdue=True,
            escalation_required=True,
        )

    if days_remaining <= 7:
        return RemediationState(
            severity=severity,
            sla_days=sla_days,
            target_date=target_date,
            days_remaining=days_remaining,
            status="Due Soon",
            overdue=False,
            escalation_required=(
                _norm(severity)
                in {"critical", "high"}
            ),
        )

    return RemediationState(
        severity=severity,
        sla_days=sla_days,
        target_date=target_date,
        days_remaining=days_remaining,
        status="On Track",
        overdue=False,
        escalation_required=False,
    )
