from src.db import MonitoringEvent


def test_event_stores_materiality():
    assert hasattr(
        MonitoringEvent,
        "materiality",
    )


def test_event_stores_decision_impact():
    assert hasattr(
        MonitoringEvent,
        "decision_impact",
    )


def test_event_stores_recommended_action():
    assert hasattr(
        MonitoringEvent,
        "recommended_action",
    )


def test_event_stores_analyst_action():
    assert hasattr(
        MonitoringEvent,
        "analyst_action",
    )


def test_event_tracks_override_rationale():
    assert hasattr(
        MonitoringEvent,
        "analyst_rationale",
    )


def test_event_tracks_human_decision_metadata():
    assert hasattr(
        MonitoringEvent,
        "analyst_followed_recommendation",
    )
    assert hasattr(
        MonitoringEvent,
        "acted_by",
    )
    assert hasattr(
        MonitoringEvent,
        "acted_at",
    )
