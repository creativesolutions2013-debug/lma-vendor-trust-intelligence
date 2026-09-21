from src.tiering import get_tier_profile, tier_code_from_score, tier_label


def test_tier_boundaries():
    assert tier_code_from_score(24) == "T4"
    assert tier_code_from_score(25) == "T3"
    assert tier_code_from_score(50) == "T2"
    assert tier_code_from_score(75) == "T1"


def test_t1_profile_drives_full_assessment_and_evidence():
    profile = get_tier_profile(82)
    assert profile.assessment_type == "Full Security Assessment"
    assert "Penetration Test" in profile.required_evidence
    assert "Continuous external security monitoring" in profile.monitoring_rules


def test_ai_enabled_vendor_adds_ai_requirements():
    profile = get_tier_profile(64, ai_enabled=True)
    assert "AI governance and model accountability" in profile.required_controls
    assert "AI governance / acceptable use documentation" in profile.required_evidence


def test_regulated_data_adds_regulatory_requirements():
    profile = get_tier_profile(40, regulated_data=True)
    assert "Regulated data handling and minimization" in profile.required_controls
    assert "Applicable regulatory assurance evidence" in profile.required_evidence


def test_tier_label_is_human_readable():
    assert tier_label(get_tier_profile(80)) == "Tier 1 — Critical"
