from dataclasses import dataclass
from datetime import datetime, timezone

from src.escalation_dashboard import (
    summarize_vendor_escalations,
)


@dataclass
class Finding:
    vendor_id: int
    title: str
    escalation_status: str | None
    escalation_note: str | None
    escalated_at: datetime | None
    owner: str | None


NOW = datetime(
    2026,
    9,
    26,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_non_escalated_findings_are_excluded():
    findings = [
        Finding(
            1,
            "Test",
            "Not Escalated",
            None,
            None,
            None,
        )
    ]

    result = summarize_vendor_escalations(
        findings,
        now=NOW,
    )

    assert result == {}


def test_active_escalation_is_counted():
    findings = [
        Finding(
            1,
            "Test",
            "Vendor Action Required",
            "Follow up",
            NOW,
            "Security Assurance",
        )
    ]

    result = summarize_vendor_escalations(
        findings,
        now=NOW,
    )

    assert result[1].active_count == 1


def test_highest_status_is_selected():
    findings = [
        Finding(
            1,
            "Vendor item",
            "Vendor Action Required",
            "Vendor follow-up",
            NOW,
            "Analyst",
        ),
        Finding(
            1,
            "Management item",
            "Management Review",
            "Escalate to leadership",
            NOW,
            "Manager",
        ),
    ]

    result = summarize_vendor_escalations(
        findings,
        now=NOW,
    )

    assert (
        result[1].highest_status
        == "Management Review"
    )
    assert (
        result[1].finding_title
        == "Management item"
    )


def test_escalation_age_is_calculated():
    findings = [
        Finding(
            1,
            "Test",
            "Escalated",
            "Follow up",
            datetime(
                2026,
                9,
                20,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            "Owner",
        )
    ]

    result = summarize_vendor_escalations(
        findings,
        now=NOW,
    )

    assert result[1].age_days == 6


def test_owner_and_note_are_exposed():
    findings = [
        Finding(
            2,
            "Control weakness",
            "Risk Acceptance Review",
            "Awaiting risk owner decision",
            NOW,
            "Risk Management",
        )
    ]

    result = summarize_vendor_escalations(
        findings,
        now=NOW,
    )

    assert (
        result[2].owner
        == "Risk Management"
    )
    assert (
        result[2].note
        == "Awaiting risk owner decision"
    )


def test_resolved_escalation_is_excluded():
    findings = [
        Finding(
            1,
            "Resolved item",
            "Resolved",
            "Done",
            NOW,
            "Owner",
        )
    ]

    result = summarize_vendor_escalations(
        findings,
        now=NOW,
    )

    assert result == {}
