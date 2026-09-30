from src.targeted_scope import (
    build_targeted_review_scope,
)


def test_external_posture_scope_focuses_on_vulnerability():
    scope = build_targeted_review_scope(
        affected_domain="External Security Posture",
        event_type="Security rating deterioration",
        tier_code="T1",
    )

    assert (
        "Vulnerability and patch management"
        in scope.review_controls
    )
    assert (
        "Business continuity and disaster recovery"
        in scope.excluded_domains
    )


def test_kev_requests_specific_remediation_evidence():
    scope = build_targeted_review_scope(
        affected_domain="External Security Posture",
        event_type="Critical KEV exposure",
        tier_code="T1",
    )

    assert any(
        "KEV" in item
        for item in scope.request_evidence
    )


def test_incident_scope_does_not_trigger_full_review():
    scope = build_targeted_review_scope(
        affected_domain="Security Incident",
        event_type="Breach disclosure",
        tier_code="T1",
    )

    assert "Incident response" in scope.review_controls
    assert "Physical security" in scope.excluded_domains


def test_ransomware_adds_recovery_scope():
    scope = build_targeted_review_scope(
        affected_domain="Security Incident",
        event_type="Ransomware event",
        tier_code="T1",
    )

    assert "Backup and recovery" in scope.review_controls
    assert any(
        "Recovery" in item
        for item in scope.request_evidence
    )


def test_ai_change_focuses_on_ai_controls():
    scope = build_targeted_review_scope(
        affected_domain="AI / Service Change",
        event_type="Material vendor change",
        tier_code="T2",
        ai_enabled=True,
    )

    assert (
        "AI governance and model accountability"
        in scope.review_controls
    )
    assert any(
        "AI architecture" in item
        for item in scope.request_evidence
    )


def test_regulated_ai_change_adds_regulatory_scope():
    scope = build_targeted_review_scope(
        affected_domain="AI / Service Change",
        event_type="Material vendor change",
        tier_code="T1",
        ai_enabled=True,
        regulated_data=True,
    )

    assert (
        "Regulated data handling and minimization"
        in scope.review_controls
    )


def test_expired_evidence_only_requests_replacement():
    scope = build_targeted_review_scope(
        affected_domain="Assurance Evidence",
        event_type="Expired assurance evidence",
        tier_code="T1",
    )

    assert scope.review_controls == ()
    assert scope.request_evidence == (
        "Replacement or renewed assurance evidence",
    )


def test_unknown_domain_falls_back_to_narrow_review():
    scope = build_targeted_review_scope(
        affected_domain="Unknown Change",
        event_type="Material vendor change",
        tier_code="T1",
    )

    assert (
        "Relevant changed control area"
        in scope.review_controls
    )
    assert "Physical security" in scope.excluded_domains
