from src.applicability import (
    APPLICABILITY_POLICY_VERSION,
    VendorRiskContext,
    evaluate_applicability,
)

from src.tiering import get_tier_profile


def control_ids(result):
    return {
        control.control_id
        for control in result.controls
    }


def evidence_ids(result):
    return {
        evidence.evidence_id
        for evidence in result.evidence
    }


def rule_ids(result):
    return {
        decision.rule_id
        for decision in result.decisions
    }


def test_tier_baseline_is_preserved():
    profile = get_tier_profile(80)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(),
    )

    assert "GOV-01" in control_ids(result)
    assert "PAM-01" in control_ids(result)
    assert "EVID-SOC2" in evidence_ids(result)


def test_sensitive_data_adds_data_controls():
    profile = get_tier_profile(10)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            sensitive_data=True,
        ),
    )

    assert "ENC-01" in control_ids(result)
    assert "DATA-01" in control_ids(result)
    assert "AP-001" in rule_ids(result)


def test_regulated_data_adds_regulatory_requirements():
    profile = get_tier_profile(10)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            sensitive_data=True,
            regulated_data=True,
        ),
    )

    assert "REG-01" in control_ids(result)
    assert "EVID-REG" in evidence_ids(result)
    assert "AP-002" in rule_ids(result)


def test_privileged_access_adds_pam():
    profile = get_tier_profile(10)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            system_access=True,
            privileged_access=True,
        ),
    )

    assert "IAM-01" in control_ids(result)
    assert "PAM-01" in control_ids(result)
    assert "AP-004" in rule_ids(result)
    assert result.review_required is True


def test_internet_facing_requires_pen_test():
    profile = get_tier_profile(30)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            internet_facing=True,
        ),
    )

    assert "VM-01" in control_ids(result)
    assert "EVID-PENTEST" in evidence_ids(result)
    assert "AP-005" in rule_ids(result)


def test_business_critical_requires_bcp():
    profile = get_tier_profile(20)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            business_critical=True,
        ),
    )

    assert "BCP-01" in control_ids(result)
    assert "EVID-BCP" in evidence_ids(result)
    assert "AP-006" in rule_ids(result)


def test_ai_enabled_adds_ai_requirements():
    profile = get_tier_profile(30)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            ai_enabled=True,
        ),
    )

    assert "AI-01" in control_ids(result)
    assert "AI-02" in control_ids(result)
    assert "AI-03" in control_ids(result)

    assert "EVID-AI-GOV" in evidence_ids(result)
    assert "EVID-AI-ARCH" in evidence_ids(result)

    assert "AP-007" in rule_ids(result)


def test_fourth_party_dependency_adds_tprm():
    profile = get_tier_profile(30)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            fourth_party_dependency=True,
        ),
    )

    assert "TPRM-01" in control_ids(result)
    assert "AP-008" in rule_ids(result)


def test_privileged_access_without_system_access_requires_review():
    profile = get_tier_profile(30)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            system_access=False,
            privileged_access=True,
        ),
    )

    assert result.review_required is True

    assert any(
        "system access is false" in reason.lower()
        for reason in result.review_reasons
    )


def test_regulated_data_without_sensitive_data_requires_review():
    profile = get_tier_profile(30)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            sensitive_data=False,
            regulated_data=True,
        ),
    )

    assert result.review_required is True

    assert any(
        "data classification" in reason.lower()
        for reason in result.review_reasons
    )


def test_duplicate_requirements_are_removed():
    profile = get_tier_profile(
        80,
        ai_enabled=True,
        regulated_data=True,
        privileged_access=True,
    )

    result = evaluate_applicability(
        profile,
        VendorRiskContext(
            sensitive_data=True,
            regulated_data=True,
            system_access=True,
            privileged_access=True,
            internet_facing=True,
            business_critical=True,
            ai_enabled=True,
            fourth_party_dependency=True,
        ),
    )

    ids = [
        control.control_id
        for control in result.controls
    ]

    assert len(ids) == len(set(ids))


def test_policy_version_is_exposed():
    profile = get_tier_profile(30)

    result = evaluate_applicability(
        profile,
        VendorRiskContext(),
    )

    assert (
        result.policy_version
        == APPLICABILITY_POLICY_VERSION
    )

    assert result.policy_version == "AP-1.0"