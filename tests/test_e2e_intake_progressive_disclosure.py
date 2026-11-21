"""Quick-start intake remains honest while optional tier inputs stay available.

These actual-app Streamlit tests deny live network, AI, DB and governed writes.
No production onboarding or real third-party evidence is exercised.
"""
from test_guided_assessment_demo_ui import no_live_effects, run, widget
from test_organization_methodology_ui import start, fill


LABEL = "Optional: adoption, scale and critical consequences"


def _advanced(at):
    return next(e for e in at.get("expander") if e.label == LABEL)


def test_short_intake_keeps_unknown_scale_inputs_unknown_and_review_provisional(no_live_effects):
    at = start()
    assert _advanced(at).label == LABEL  # Open/closed is not exposed on AppTest's Expander.
    assert "optional details below can affect the assessed risk tier" in "\n".join(
        c.value for c in at.caption
    )
    # Optional details are still supplied by the same tracked widgets; no
    # synthetic "no", false or zero is silently substituted for Unknown.
    assert widget(at.number_input, "Active or expected client users").value is None
    assert widget(at.number_input, "Defined workforce population").value is None
    assert widget(at.selectbox, "Is scale already included in the baseline assessment?").value == "Unknown"
    assert widget(at.selectbox, "Critical consequence under organization methodology").value == "Unknown"

    widget(at.text_input, "Synthetic vendor name").set_value("Short Intake Synthetic")
    widget(at.text_input, "Service being assessed").set_value("Proofless Service")
    widget(at.text_area, "Business use case").set_value("Only initial relationship context supplied")
    run(at)
    widget(at.button, "Create assessment").click()
    run(at)

    intake = at.session_state["customer_assessment:intake"]
    model = at.session_state["customer_assessment:model"]
    assert intake.active_client_users is None
    assert intake.workforce_size is None
    assert intake.scale_already_counted is None
    assert intake.critical_consequence is None
    assert intake.data_types == ("Unknown",)
    assert intake.network_access == "Unknown"
    assert intake.data_volume_records is None
    assert not any(row.outcome == "Met" for row in model.worklist.rows)
    assert "provisional" in model.customer_context["tier_status"].lower()


def test_optional_inputs_preserve_existing_policy_scoring_and_validation(no_live_effects):
    at = start()
    assert _advanced(at).label == LABEL  # Open/closed is not exposed on AppTest's Expander.
    fill(at)  # Reuse the established organization-methodology acceptance case.
    assert widget(at.number_input, "Active or expected client users").value == 1000
    assert widget(at.number_input, "Defined workforce population").value == 2000
    widget(at.button, "Create assessment").click()
    run(at)
    intake = at.session_state["customer_assessment:intake"]
    model = at.session_state["customer_assessment:model"]
    assert intake.active_client_users == 1000
    assert intake.workforce_size == 2000
    assert intake.scale_already_counted is False
    assert intake.critical_consequence is False
    assert model.inherent_score == 41
    assert model.inherent_tier == "Tier 2 — High"
    assert model.customer_context["methodology_snapshot"]["version"] == "1"
    assert all(row.outcome not in ("Met", "Risk Identified") for row in model.worklist.rows)


def test_optional_scale_validation_rejects_inconsistent_workforce(no_live_effects):
    at = start()
    widget(at.text_input, "Synthetic vendor name").set_value("Synthetic Validation Vendor")
    widget(at.text_input, "Service being assessed").set_value("Synthetic Scope")
    widget(at.text_area, "Business use case").set_value("Verify existing scale validation")
    widget(at.number_input, "Active or expected client users").set_value(100)
    widget(at.number_input, "Defined workforce population").set_value(20)
    run(at)
    widget(at.button, "Create assessment").click()
    run(at)
    assert at.error
    assert any("cannot exceed" in e.value for e in at.error)
    assert "customer_assessment:intake" not in at.session_state
