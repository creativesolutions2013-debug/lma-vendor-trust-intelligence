from src.tiering import (
    get_tier_profile,
    tier_code_from_score,
    tier_label,
)


def control_ids(profile):
    return {
        control.control_id
        for control in profile.required_controls
    }


def evidence_ids(profile):
    return {
        evidence.evidence_id
        for evidence in profile.required_evidence
    }


def test_tier_boundaries():
    assert tier_code_from_score(24) == "T4"
    assert tier_code_from_score(25) == "T3"
    assert tier_code_from_score(50) == "T2"
    assert tier_code_from_score(75) == "T1"


def test_t1_profile_drives_full_assessment():
    profile = get_tier_profile(82)

    assert profile.tier == "T1"
    assert profile.assessment_type == "Full Security Assessment"

    assert "PAM-01" in control_ids(profile)
    assert "EVID-PENTEST" in evidence_ids(profile)

    assert (
        "Continuous external security monitoring"
        in profile.monitoring_rules
    )


def test_t4_profile_is_lightweight():
    profile = get_tier_profile(10)

    assert profile.tier == "T4"
    assert profile.assessment_type == "Basic Security Screening"

    assert "EVID-BASIC" in evidence_ids(profile)


def test_ai_enabled_vendor_adds_ai_requirements():
    profile = get_tier_profile(
        64,
        ai_enabled=True,
    )

    assert "AI-01" in control_ids(profile)
    assert "AI-02" in control_ids(profile)
    assert "AI-03" in control_ids(profile)

    assert "EVID-AI-GOV" in evidence_ids(profile)
    assert "EVID-AI-ARCH" in evidence_ids(profile)


def test_regulated_data_adds_regulatory_requirements():
    profile = get_tier_profile(
        40,
        regulated_data=True,
    )

    assert "REG-01" in control_ids(profile)
    assert "DATA-01" in control_ids(profile)
    assert "EVID-REG" in evidence_ids(profile)


def test_privileged_access_adds_pam_requirement():
    profile = get_tier_profile(
        30,
        privileged_access=True,
    )

    assert "PAM-01" in control_ids(profile)
    assert "IAM-01" in control_ids(profile)


def test_requirements_have_stable_ids():
    profile = get_tier_profile(80)

    for control in profile.required_controls:
        assert control.control_id
        assert control.domain
        assert control.requirement

    for evidence in profile.required_evidence:
        assert evidence.evidence_id
        assert evidence.evidence_type


def test_policy_version_is_exposed():
    profile = get_tier_profile(80)

    assert profile.policy_version == "TP-2.0"


def test_tier_label_is_human_readable():
    assert (
        tier_label(get_tier_profile(80))
        == "Tier 1 — Critical"
    )