from src.reassessment import evaluate_reassessment_trigger


def test_high_breach_triggers_incident_reassessment():
    decision = evaluate_reassessment_trigger(
        event_type="Breach disclosure",
        severity="High",
        tier_code="T1",
    )

    assert decision.triggered is True
    assert decision.assessment_type == "Incident-Triggered Reassessment"
    assert decision.priority == "P2"


def test_critical_ransomware_is_p1():
    decision = evaluate_reassessment_trigger(
        event_type="Ransomware event",
        severity="Critical",
        tier_code="T2",
    )

    assert decision.triggered is True
    assert decision.priority == "P1"


def test_material_change_triggers_change_reassessment():
    decision = evaluate_reassessment_trigger(
        event_type="Material vendor change",
        severity="Moderate",
        tier_code="T2",
    )

    assert decision.triggered is True
    assert decision.assessment_type == "Material Change Reassessment"


def test_expired_evidence_triggers_for_tier1_and_tier2():
    t1 = evaluate_reassessment_trigger(
        event_type="Expired assurance evidence",
        severity="Moderate",
        tier_code="T1",
    )
    t2 = evaluate_reassessment_trigger(
        event_type="Expired assurance evidence",
        severity="Moderate",
        tier_code="T2",
    )

    assert t1.triggered is True
    assert t2.triggered is True
    assert t1.assessment_type == "Evidence-Triggered Reassessment"


def test_expired_evidence_does_not_trigger_for_tier4():
    decision = evaluate_reassessment_trigger(
        event_type="Expired assurance evidence",
        severity="Moderate",
        tier_code="T4",
    )

    assert decision.triggered is False


def test_low_rating_change_does_not_trigger():
    decision = evaluate_reassessment_trigger(
        event_type="Security rating deterioration",
        severity="Low",
        tier_code="T1",
    )

    assert decision.triggered is False
