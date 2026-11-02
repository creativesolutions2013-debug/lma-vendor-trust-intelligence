"""Independent owner acceptance replay for M5B using the supplied Cedarline synthetic files.

No live vendor evidence, external calls, model output, or seeded source fixtures.
Exercises real file uploads via Streamlit's AppTest and inspects exact exported bytes.
"""
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

from test_guided_assessment_demo_ui import no_live_effects, packages, run, shown, widget
from test_upload_assessment_ui import start, stage
from test_upload_evaluation_ui import suggestions

# These are the exact independently supplied synthetic Cedarline acceptance documents.
TLS_SOURCE = (
    "SYNTHETIC TEST FILE — NOT REAL VENDOR EVIDENCE\n"
    "Configuration export\n"
    "Service: Cedarline Data Platform\n"
    "Environment: production\n"
    "Observation date: 2026-10-26\n"
    "Primary listener 443: TLS 1.2 is enabled.\n"
    "Alternate production listener 9443: TLS 1.0 is enabled.\n"
).encode("utf-8")
DR_SOURCE = (
    "SYNTHETIC TEST FILE — NOT REAL VENDOR EVIDENCE\n"
    "DR exercise results\n"
    "Service: Cedarline Data Platform\n"
    "Environment: production\n"
    "Test date: 2026-09-20\n"
    "Recovery exercise completed.\n"
    "Achieved RTO 300 minutes and RPO 90 minutes.\n"
    "Identity provider was excluded from the exercise.\n"
).encode("utf-8")


def test_cedarline_real_upload_one_click_metadata_threshold_and_export(no_live_effects, packages, monkeypatch):
    # The acceptance documents are fixed at 2026-10-26 / 2026-09-20.
    # Freeze only the intake/UI assessment clock: preserve real source dates,
    # and avoid a false stale-evidence failure as wall time advances.
    import src.upload_assessment_ui as upload_ui

    class AcceptanceDate(date):
        @classmethod
        def today(cls):
            return date(2026, 11, 1)

    monkeypatch.setattr(upload_ui, "date", AcceptanceDate)
    at = start()
    widget(at.sidebar.button, "Clear this assessment").click()
    run(at)
    widget(at.text_input, "Synthetic vendor name").set_value("Cedarline Analytics")
    widget(at.text_input, "Service being assessed").set_value("Cedarline Data Platform")
    widget(at.text_area, "Business use case").set_value("Synthetic vendor risk acceptance")
    run(at)
    widget(at.button, "Create assessment").click()
    run(at)

    # Reproduce the owner's two failed manual attempts: wrong declared type/date.
    at.get("file_uploader")[0].upload("Cedarline_M5B_TLS_Configuration.txt", TLS_SOURCE).upload(
        "Cedarline_M5B_DR_Exercise.txt", DR_SOURCE
    )
    run(at)
    assert [w.value for w in at.multiselect] == [["ENC-01"], ["BCP-01"]]
    for w in [x for x in at.selectbox if x.label == "Document kind (your declaration)"]:
        w.set_value("policy")
    for w in at.date_input:
        w.set_value(date(2026, 11, 1))
    run(at)
    assert "Source says: configuration / 2026-10-26" in shown(at)
    assert "Source says: test / 2026-09-20" in shown(at)

    # No silent changes. Explicitly evaluate wrong metadata; it must not qualify.
    widget(at.button, "Evaluate attached evidence").click()
    run(at)
    wrong = at.session_state["customer_assessment:model"]
    assert all(
        not fact["eligible_for_preview"]
        for evaluation in wrong.customer_context["evaluations"]
        for fact in evaluation["facts"]
    )

    stage(at, "Upload evidence")
    suggestions(at)[0].click()
    run(at)
    stage(at, "Report")
    assert not at.get("download_button")  # Must reevaluate, never export stale evidence.
    stage(at, "Upload evidence")
    suggestions(at)[1].click()
    run(at)
    assert [w.value for w in at.date_input] == [date(2026, 10, 26), date(2026, 9, 20)]
    assert [w.value for w in at.selectbox if w.label == "Document kind (your declaration)"] == [
        "configuration", "test"
    ]
    widget(at.button, "Evaluate attached evidence").click()
    run(at)

    model = at.session_state["customer_assessment:model"]
    evaluations = {e["requirement_id"]: e for e in model.customer_context["evaluations"]}
    assert set(evaluations) == {"ENC-01", "BCP-01"}
    assert all(e["preview"]["outcome_if_confirmed"] == "Risk Identified" for e in evaluations.values())
    assert all(f["eligible_for_preview"] and not f["confirmed"]
               for e in evaluations.values() for f in e["facts"])
    # Compare the *parsed technical observations* rather than only line text:
    # a dropped RTO fact or a swapped RTO/RPO value must fail this test.
    tls_facts = evaluations["ENC-01"]["facts"]
    dr_facts = evaluations["BCP-01"]["facts"]
    assert {(f["dimension"], f["value"], f["subject"]) for f in tls_facts} == {
        ("enabled_version", 12, "listener 443"),
        ("enabled_version", 10, "listener 9443"),
    }
    assert {(f["dimension"], f["value"], f["subject"]) for f in dr_facts} == {
        ("completed", True, "exercise for cedarline data platform"),
        ("achieved_rto_minutes", 300, "exercise for cedarline data platform"),
        ("achieved_rpo_minutes", 90, "exercise for cedarline data platform"),
        ("scope_complete", False, "exercise for cedarline data platform"),
    }
    assert next(f for f in tls_facts if f["value"] == 10)["direction"] == "adverse"
    assert all(f["direction"] == "adverse" for f in dr_facts if f["dimension"] in (
        "achieved_rto_minutes", "achieved_rpo_minutes", "scope_complete"))
    assert any("Identity provider was excluded" in f["quote"]
               for f in dr_facts if f["dimension"] == "scope_complete")
    assert all(row.outcome != "Met" for row in model.worklist.rows)
    assert all(not fact.confirmed for row in model.worklist.rows
               if row.review for fact in row.review.facts)

    stage(at, "Report")
    widget(at.button, "Finish assessment review").click()
    run(at)
    assert packages
    with ZipFile(BytesIO(packages[-1])) as package:
        report = json.loads(package.read("report.json"))
        manifest = json.loads(package.read("manifest.json"))
        originals = {
            "Cedarline_M5B_TLS_Configuration.txt": TLS_SOURCE,
            "Cedarline_M5B_DR_Exercise.txt": DR_SOURCE,
        }
        assert len(manifest["artifacts"]) == 2
        for artifact in manifest["artifacts"]:
            content = package.read(artifact["archive_path"])
            assert content == originals[artifact["filename"]]
            assert sha256(content).hexdigest() == artifact["sha256"]
        assert report["risk"]["residual_score"] is None
        assert report["review_completion"]["vendor_approved"] is False
        assert all(not fact["confirmed"]
                   for e in report["assessment_context"]["evaluations"]
                   for fact in e["facts"])
        for e in report["assessment_context"]["evaluations"]:
            assert e["preview"]["outcome_if_confirmed"] == "Risk Identified"
            for fact in e["facts"]:
                original = originals[fact["filename"]].decode("utf-8").splitlines()
                assert fact["quote"] == original[int(fact["location"].split()[-1]) - 1]
