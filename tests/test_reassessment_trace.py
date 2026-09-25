from src.reassessment_trace import parse_reassessment_trace


def test_parses_monitoring_event_id_and_rationale():
    trace = parse_reassessment_trace(
        "Automatically triggered from monitoring event #12. "
        "Breach disclosure materially changes vendor risk."
    )

    assert trace.triggered is True
    assert trace.source == "Monitoring event"
    assert trace.event_id == 12
    assert "Breach disclosure" in trace.rationale


def test_manual_assessment_is_not_marked_triggered():
    trace = parse_reassessment_trace("Annual review scope.")

    assert trace.triggered is False
    assert trace.source == "Manual"
    assert trace.event_id is None


def test_empty_notes_are_manual():
    trace = parse_reassessment_trace(None)

    assert trace.triggered is False
    assert trace.event_id is None


def test_malformed_trigger_note_is_safe():
    trace = parse_reassessment_trace(
        "Automatically triggered from monitoring event #unknown. Review manually."
    )

    assert trace.triggered is True
    assert trace.event_id is None
    assert trace.rationale == "Review manually."
