from dataclasses import dataclass

from src.evidence_request import (
    build_evidence_request_draft,
    can_transition_request,
)


@dataclass
class FakeItem:
    requirement: str
    workflow_action: str


def test_request_items_are_vendor_requests():
    draft = build_evidence_request_draft(
        [
            FakeItem(
                "Penetration Test",
                "Request Vendor",
            ),
        ]
    )

    assert draft.requested_items == (
        "Penetration Test",
    )


def test_reuse_becomes_avoided_request():
    draft = build_evidence_request_draft(
        [
            FakeItem(
                "Security Policy",
                "Reuse",
            ),
        ]
    )

    assert draft.avoided_requests == (
        "Security Policy",
    )


def test_validation_is_not_sent_to_vendor():
    draft = build_evidence_request_draft(
        [
            FakeItem(
                "SOC 2 Type II",
                "Analyst Validate",
            ),
        ]
    )

    assert draft.validation_items == (
        "SOC 2 Type II",
    )
    assert draft.requested_items == ()


def test_valid_request_lifecycle():
    assert can_transition_request(
        "Draft",
        "Sent",
    )
    assert can_transition_request(
        "Sent",
        "Received",
    )
    assert can_transition_request(
        "Received",
        "Closed",
    )


def test_invalid_request_lifecycle_jump():
    assert not can_transition_request(
        "Draft",
        "Closed",
    )
