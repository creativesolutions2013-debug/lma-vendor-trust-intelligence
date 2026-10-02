from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EvidenceRequestDraft:
    requested_items: tuple[str, ...]
    validation_items: tuple[str, ...]
    avoided_requests: tuple[str, ...]


VALID_TRANSITIONS = {
    "Draft": {"Sent"},
    "Sent": {"Received"},
    "Received": {"Closed"},
    "Closed": set(),
}


def build_evidence_request_draft(
    work_plan_items: Iterable,
) -> EvidenceRequestDraft:
    requested = []
    validate = []
    avoided = []

    for item in work_plan_items:
        action = getattr(
            item,
            "workflow_action",
            "",
        )

        requirement = getattr(
            item,
            "requirement",
            "",
        )

        if action == "Request Vendor":
            requested.append(requirement)

        elif action == "Analyst Validate":
            validate.append(requirement)

        elif action == "Reuse":
            avoided.append(requirement)

    return EvidenceRequestDraft(
        requested_items=tuple(requested),
        validation_items=tuple(validate),
        avoided_requests=tuple(avoided),
    )


def can_transition_request(
    current_status: str,
    next_status: str,
) -> bool:
    return next_status in VALID_TRANSITIONS.get(
        current_status,
        set(),
    )
