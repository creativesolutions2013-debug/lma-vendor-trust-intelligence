from src.material_change import (
    evaluate_material_change,
)


def test_expired_evidence_requests_evidence_not_full_reassessment():
    result = evaluate_material_change(
        event_type="Expired assurance evidence",
        severity="High",
        tier_code="T1",
        has_current_approval=True,
    )

    assert result.recommended_action == "Request Evidence"
    assert result.decision_impact == "Decision Review Required"


def test_critical_incident_with_high_context_challenges_decision():
    result = evaluate_material_change(
        event_type="Breach disclosure",
        severity="Critical",
        tier_code="T1",
        business_criticality="Critical",
        data_classification="Restricted",
        production_access=True,
        privileged_access=True,
        has_current_approval=True,
    )

    assert result.materiality == "Critical"
    assert result.decision_impact == "Decision Challenged"
    assert result.recommended_action == "Escalate"


def test_high_incident_with_lower_context_uses_targeted_review():
    result = evaluate_material_change(
        event_type="Credential exposure",
        severity="High",
        tier_code="T3",
    )

    assert result.recommended_action == "Targeted Review"
    assert result.decision_impact == "Decision Review Required"


def test_ai_material_change_uses_targeted_review():
    result = evaluate_material_change(
        event_type="Material vendor change",
        severity="Moderate",
        tier_code="T2",
        ai_enabled=True,
        has_current_approval=True,
    )

    assert result.affected_domain == "AI / Service Change"
    assert result.recommended_action == "Targeted Review"
    assert result.decision_impact == "Decision Challenged"


def test_low_context_material_change_is_monitored():
    result = evaluate_material_change(
        event_type="Material vendor change",
        severity="Moderate",
        tier_code="T4",
    )

    assert result.materiality == "Moderate"
    assert result.recommended_action == "Monitor"


def test_rating_decline_for_critical_relationship_is_targeted():
    result = evaluate_material_change(
        event_type="Security rating deterioration",
        severity="High",
        tier_code="T1",
        business_criticality="Critical",
        production_access=True,
    )

    assert result.recommended_action == "Targeted Review"
    assert result.affected_domain == "External Security Posture"


def test_rating_decline_for_low_context_vendor_is_monitor_only():
    result = evaluate_material_change(
        event_type="Security rating deterioration",
        severity="Moderate",
        tier_code="T4",
    )

    assert result.recommended_action == "Monitor"
    assert result.decision_impact == "Monitor"


def test_low_severity_unknown_event_requires_no_action():
    result = evaluate_material_change(
        event_type="Minor informational change",
        severity="Low",
        tier_code="T4",
    )

    assert result.materiality == "Low"
    assert result.recommended_action == "No Action"
    assert result.decision_impact == "No Impact"
