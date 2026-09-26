from src.db import Finding


def test_finding_has_escalation_status():
    assert hasattr(
        Finding,
        "escalation_status",
    )


def test_finding_has_escalation_note():
    assert hasattr(
        Finding,
        "escalation_note",
    )


def test_finding_tracks_escalation_actor():
    assert hasattr(
        Finding,
        "escalated_by",
    )


def test_finding_tracks_escalation_time():
    assert hasattr(
        Finding,
        "escalated_at",
    )
