from dataclasses import dataclass
from typing import Optional


TRIGGER_NOTE_PREFIX = "Automatically triggered from monitoring event #"


@dataclass(frozen=True)
class ReassessmentTrace:
    triggered: bool
    source: str
    event_id: Optional[int]
    rationale: str


def parse_reassessment_trace(notes: str | None) -> ReassessmentTrace:
    text = (notes or "").strip()

    if not text.startswith(TRIGGER_NOTE_PREFIX):
        return ReassessmentTrace(
            triggered=False,
            source="Manual",
            event_id=None,
            rationale=text,
        )

    remainder = text[len(TRIGGER_NOTE_PREFIX):]
    event_token, separator, rationale = remainder.partition(".")

    try:
        event_id = int(event_token.strip())
    except (TypeError, ValueError):
        return ReassessmentTrace(
            triggered=True,
            source="Monitoring event",
            event_id=None,
            rationale=(rationale.strip() if separator else remainder.strip()),
        )

    return ReassessmentTrace(
        triggered=True,
        source="Monitoring event",
        event_id=event_id,
        rationale=rationale.strip() if separator else "",
    )
