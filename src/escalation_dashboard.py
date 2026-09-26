from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


STATUS_PRIORITY = {
    "Management Review": 5,
    "Risk Acceptance Review": 4,
    "Vendor Action Required": 3,
    "Escalated": 2,
    "Not Escalated": 0,
    "Resolved": 0,
}


ACTIVE_STATUSES = {
    "Escalated",
    "Vendor Action Required",
    "Management Review",
    "Risk Acceptance Review",
}


@dataclass(frozen=True)
class VendorEscalationSummary:
    vendor_id: int
    active_count: int
    highest_status: str
    owner: str
    age_days: int | None
    note: str
    finding_title: str


def _status(value: str | None) -> str:
    return (
        (value or "Not Escalated")
        .strip()
    )


def _age_days(
    escalated_at,
    *,
    now: datetime,
) -> int | None:
    if escalated_at is None:
        return None

    dt = escalated_at

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return max(
        0,
        (now - dt).days,
    )


def summarize_vendor_escalations(
    findings: Iterable[object],
    *,
    now: datetime | None = None,
) -> dict[int, VendorEscalationSummary]:
    current_time = (
        now
        or datetime.now(timezone.utc)
    )

    grouped: dict[int, list[object]] = {}

    for finding in findings:
        status = _status(
            getattr(
                finding,
                "escalation_status",
                None,
            )
        )

        if status not in ACTIVE_STATUSES:
            continue

        vendor_id = getattr(
            finding,
            "vendor_id",
            None,
        )

        if vendor_id is None:
            continue

        grouped.setdefault(
            vendor_id,
            [],
        ).append(finding)

    result = {}

    for vendor_id, items in grouped.items():
        ranked = sorted(
            items,
            key=lambda item: (
                STATUS_PRIORITY.get(
                    _status(
                        getattr(
                            item,
                            "escalation_status",
                            None,
                        )
                    ),
                    0,
                ),
                getattr(
                    item,
                    "escalated_at",
                    None,
                )
                or datetime.min,
            ),
            reverse=True,
        )

        primary = ranked[0]

        status = _status(
            getattr(
                primary,
                "escalation_status",
                None,
            )
        )

        result[vendor_id] = (
            VendorEscalationSummary(
                vendor_id=vendor_id,
                active_count=len(items),
                highest_status=status,
                owner=(
                    getattr(
                        primary,
                        "owner",
                        None,
                    )
                    or "Unassigned"
                ),
                age_days=_age_days(
                    getattr(
                        primary,
                        "escalated_at",
                        None,
                    ),
                    now=current_time,
                ),
                note=(
                    getattr(
                        primary,
                        "escalation_note",
                        None,
                    )
                    or ""
                ),
                finding_title=(
                    getattr(
                        primary,
                        "title",
                        None,
                    )
                    or ""
                ),
            )
        )

    return result
