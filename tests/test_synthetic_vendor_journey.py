"""Actual synthetic HTTPS and browser vendor-to-analyst evidence handoff.

Only disposable databases, independent local fixture identities and test TLS are
used. Vendor delivery remains pending until explicit authorized analyst capture.
"""
from datetime import timedelta
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlsplit
from zipfile import ZipFile

import pytest
from sqlalchemy import func, select, update

from src.db import (Evidence, OrganizationMembership, SyntheticAssessmentRevision,
                    SyntheticEvidenceObject, SyntheticVendorHandoff)
from src.resumable_assessment import SyntheticResumableAssessmentService
from src.resumable_assessment_state import encode_draft
from src.session_identity_source import SessionIdentitySource
from src.synthetic_analyst_pilot import PilotApplication, make_https_server
from src.synthetic_browser_auth import SyntheticPilotIdentity
from src.synthetic_evidence_custody import SyntheticEvidenceCustodyService
from src.upload_assessment import read_upload
from test_resumable_assessment import assessment_ctx
from test_synthetic_analyst_pilot import _Client, _Forms, _certificate, PASSWORD


VENDOR_PASSWORD = "different-synthetic-vendor-password"
VENDOR_SESSION = "__Host-lma_vendor_session"
ANALYST_SESSION = "__Host-lma_session"


class _Invitation(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.values = []
        self.feed(body.decode())

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and "readonly" in values:
            self.values.append(values.get("value"))


@pytest.fixture
def vendor_pilot(assessment_ctx, tmp_path, monkeypatch):
    ctx = assessment_ctx
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    analyst = SyntheticPilotIdentity(port, PASSWORD, clock=lambda: ctx.clock[0])
    vendor = SyntheticPilotIdentity(port, VENDOR_PASSWORD, vendor=True, clock=lambda: ctx.clock[0])
    with ctx.factory.begin() as database:
        database.execute(update(OrganizationMembership).where(OrganizationMembership.id == 501)
                         .values(issuer=analyst.config.issuer, subject=analyst.subject))
    monkeypatch.setenv("AUTH_MODE", "development")
    app = PilotApplication(analyst, ctx.factory, ctx.intake, vendor_identity=vendor)
    certificate, key, spki = _certificate(tmp_path)
    server = make_https_server(app, str(certificate), str(key))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(ctx=ctx, app=app, identity=analyst, vendor_identity=vendor,
            origin=analyst.origin, certificate=certificate, spki=spki, port=port,
            client=_Client(port, certificate), vendor=_Client(port, certificate))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _vendor_login(client):
    landing = client.request("GET", "/vendor")
    start = client.request("POST", "/vendor/login", fields=_Forms(landing.body).forms["/vendor/login"])
    provider = client.follow(start)
    assert provider.status == 200
    fields = _Forms(provider.body).forms["/vendor/synthetic-idp/authorize"]
    fields["password"] = VENDOR_PASSWORD
    workspace = client.request("POST", "/vendor/synthetic-idp/authorize", fields=fields, follow=True)
    assert workspace.status == 200 and b"Submit evidence to analyst" in workspace.body
    assert VENDOR_SESSION in client.cookies and ANALYST_SESSION not in client.cookies
    return workspace


def _originals(pilot):
    context = (f"Service: {pilot.ctx.intake.service}\nEnvironment: {pilot.ctx.intake.environment}\n"
               f"Observation date: {pilot.ctx.clock[0].date()}\n")
    return {
        "tls-config.txt": ("Synthetic TLS configuration\n" + context
                           + "Primary listener 443: TLS 1.2 is enabled.\n"
                           + "Alternate production listener 9443: TLS 1.0 is enabled.\n").encode(),
        "dr-plan.txt": ("Synthetic recovery plan\n" + context
                        + "Target RTO 120 minutes and RPO 30 minutes.\n"
                        + "A recovery exercise is scheduled; no completed test result is supplied.\n").encode(),
        "vendor-dr-exercise.txt": ("Synthetic completed recovery record\n" + context
            + "Recovery exercise completed.\nAchieved RTO 210 minutes and RPO 45 minutes.\n"
            + "Identity provider was excluded from the exercise.\n").encode(),
    }


def _seed_typed_originals(pilot, handle):
    """Use real signed-in analyst APIs to prepare two different source kinds.

    Phase 6's upload form declares one kind for an entire batch; native authorized
    intake is used here rather than misdeclaring a DR policy as TLS configuration.
    The actual cross-role journey below uses only real forms and HTTPS.
    """
    source = SessionIdentitySource(pilot.identity.sessions, handle, pilot.ctx.factory,
                                   clock=lambda: pilot.ctx.clock[0])
    custody = SyntheticEvidenceCustodyService(pilot.ctx.factory, identity_source=source)
    uploads, receipts = [], []
    originals = _originals(pilot)
    for name, requirement, kind in (("tls-config.txt", "ENC-01", "configuration"),
                                    ("dr-plan.txt", "BCP-01", "policy")):
        receipt = custody.save(1001, originals[name], document_name=name)
        assert receipt is not None
        receipts.append(receipt)
        uploads.append(read_upload(pilot.ctx.intake, name, originals[name], (requirement,), kind=kind,
            observed_on=pilot.ctx.clock[0].date(), service=pilot.ctx.intake.service,
            environment=pilot.ctx.intake.environment))
    saved = SyntheticResumableAssessmentService(pilot.ctx.factory, identity_source=source).save(
        1001, expected_revision=0, draft=encode_draft(pilot.ctx.intake, tuple(uploads), tuple(receipts)))
    assert saved is not None and saved.revision == 1
    return originals


def _initial(pilot):
    pilot.client.login()
    originals = _seed_typed_originals(pilot, pilot.client.cookies[ANALYST_SESSION])
    page = pilot.client.request("GET", "/")
    assert page.status == 200 and b"Create local vendor invitation" in page.body
    return page, originals


def _review(pilot, page, requirement, action, rationale):
    fields = _Forms(page.body).forms["/review"]
    fields.update(requirement_id=requirement, action=action, rationale=rationale)
    if action == "Request Evidence":
        fields["confirms_insufficiency"] = "yes"
    return pilot.client.request("POST", "/review", fields=fields, follow=True)


def _invite(pilot, page):
    fields = _Forms(page.body).forms["/vendor-invitation/create"]
    fields["requirement_id"] = "BCP-01"
    response = pilot.client.request("POST", "/vendor-invitation/create", fields=fields)
    assert response.status == 200
    token, = _Invitation(response.body).values
    assert len(token) == 43
    assert token not in response.headers.get("location", "")
    assert all(token not in value for value in pilot.client.cookies.values())
    page = pilot.client.request("GET", "/")
    assert token.encode() not in page.body  # displayed exactly once
    return token, page


def _submit(pilot, token, *, page=None, name="vendor-dr-exercise.txt", content=None, fields=None, files=None, headers=None):
    page = page or pilot.vendor.request("GET", "/vendor")
    values = _Forms(page.body).forms["/vendor/submit"]
    values.update(token=token, kind="test", observed_on=pilot.ctx.clock[0].date().isoformat())
    values.update(fields or {})
    content = _originals(pilot)["vendor-dr-exercise.txt"] if content is None else content
    return pilot.vendor.request("POST", "/vendor/submit", fields=values,
        files=files if files is not None else ((name, content),), headers=headers)


def _counts(pilot):
    with pilot.ctx.factory() as database:
        return tuple(database.execute(select(func.count()).select_from(model)).scalar_one()
                     for model in (Evidence, SyntheticEvidenceObject, SyntheticAssessmentRevision, SyntheticVendorHandoff))


def _export(response, originals):
    assert response.status == 200 and response.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(response.body)) as archive:
        report = json.loads(archive.read("report.json"))
        manifest = json.loads(archive.read("manifest.json"))
        files = {item["filename"]: archive.read(item["archive_path"]) for item in manifest["artifacts"]}
        assert files == originals
        for item in manifest["artifacts"]:
            assert sha256(files[item["filename"]]).hexdigest() == item["sha256"]
        assert report["risk"]["residual_score"] is None
        assert report["review_completion"]["vendor_approved"] is False
        assert report["review_completion"]["technical_facts_confirmed_by_completion"] is False
        return report


def _assert_targeted_staleness(report, before):
    tls = next(a for a in report["analyst_actions"] if a["requirement_id"] == "ENC-01")
    assert tls["status"] == "Current"
    assert tls["citations"] == next(a for a in before["analyst_actions"] if a["requirement_id"] == "ENC-01")["citations"]
    assert any(a["requirement_id"] == "BCP-01" and a["status"] == "Stale context" for a in report["analyst_actions"])
    assert report["persistence"]["completion_stale"] is True
    assert any(review["requirement_id"] == "BCP-01" and review["status"] == "Stale context"
               for review in report["evidence_gap_reviews"])
    assert not any("BCP-01" in request["requirement_ids"] for request in report["targeted_requests"])


def test_actual_https_distinct_vendor_delivery_capture_targeted_review_resume_and_intact_zip(vendor_pilot):
    pilot = vendor_pilot
    page, originals = _initial(pilot)
    page = _review(pilot, page, "ENC-01", "Create Finding", "Validate cited TLS 1.0 listener and remediation.")
    page = _review(pilot, page, "BCP-01", "Request Evidence", "Provide completed recovery results and dependency coverage.")
    page = pilot.client.request("POST", "/finish", fields=_Forms(page.body).forms["/finish"], follow=True)
    before = _export(pilot.client.request("GET", "/download.zip"), {key: value for key, value in originals.items() if key != "vendor-dr-exercise.txt"})
    assert any("BCP-01" in request["requirement_ids"] for request in before["targeted_requests"])
    token, page = _invite(pilot, page)
    _vendor_login(pilot.vendor)
    counts = _counts(pilot)
    response = _submit(pilot, token)
    assert response.status == 303 and response.headers["location"] == "/vendor/received"
    received = pilot.vendor.follow(response)
    assert received.status == 200 and b"pending analyst capture" in received.body
    assert all(item not in received.body for item in (b"tls-config", b"BCP-01", token.encode(), b"Vendor A", b"1001"))
    assert _counts(pilot) == counts  # delivery itself confers no SQL write authority
    capture = _Forms(pilot.client.request("GET", "/").body).forms["/vendor-invitation/capture"]
    result = pilot.client.request("POST", "/vendor-invitation/capture", fields=capture, follow=True)
    assert result.status == 200 and b"vendor-dr-exercise.txt" in result.body
    assert _counts(pilot) == tuple(value + increment for value, increment in zip(counts, (1, 1, 1, 1)))
    revised = _export(pilot.client.request("GET", "/download.zip"), originals)
    _assert_targeted_staleness(revised, before)
    source = next(source for source in revised["persistence"]["source_custody"] if source["filename"] == "vendor-dr-exercise.txt")
    delivery = source["vendor_delivery"]
    assert source["capture_actor"]["subject"] == "synthetic-analyst"
    assert delivery["vendor_subject"] == "synthetic-vendor" and delivery["vendor_issuer"] == pilot.vendor_identity.config.issuer
    assert delivery["vendor_session_id"] != delivery["inviter_session_id"]
    assert delivery["kind"] == "test" and source["sha256"] == sha256(originals["vendor-dr-exercise.txt"]).hexdigest()
    assert token.encode() not in json.dumps(revised).encode()
    assert any(citation["filename"] == "vendor-dr-exercise.txt" and citation["quote"] in originals["vendor-dr-exercise.txt"].decode()
               for row in revised["requirements"] for citation in row["citations"])
    result = _review(pilot, result, "BCP-01", "Challenge", "Validate new achieved objectives and excluded dependency; facts remain unconfirmed.")
    result = pilot.client.request("POST", "/finish", fields=_Forms(result.body).forms["/finish"], follow=True)
    prior_handle = pilot.client.cookies[ANALYST_SESSION]
    result = pilot.client.request("POST", "/logout", fields=_Forms(result.body).forms["/logout"], follow=True)
    pilot.client.login()
    assert pilot.client.cookies[ANALYST_SESSION] != prior_handle
    resumed = _export(pilot.client.request("GET", "/download.zip"), originals)
    assert resumed["persistence"]["completion_stale"] is False
    assert next(source for source in resumed["persistence"]["source_custody"] if source["filename"] == "vendor-dr-exercise.txt")["vendor_delivery"] == delivery


@pytest.mark.parametrize("path", ["/download.zip", "/review", "/finish", "/save", "/vendor-invitation/create", "/vendor-invitation/capture"])
def test_vendor_cookie_cannot_read_or_mutate_analyst_endpoints(vendor_pilot, path):
    pilot = vendor_pilot
    page, _ = _initial(pilot)
    vendor_page = _vendor_login(pilot.vendor)
    assert all(secret not in vendor_page.body for secret in (b"tls-config", b"Vendor A", b"Synthetic analytics review", b"BCP-01"))
    before = _counts(pilot)
    if path == "/download.zip":
        result = pilot.vendor.request("GET", path)
    else:
        fields = {"csrf": _Forms(vendor_page.body).forms["/vendor/submit"]["csrf"], "expected_revision": "1"}
        result = pilot.vendor.request("POST", path, fields=fields)
    assert result.status in (401, 403)
    assert _counts(pilot) == before
    # Naming a vendor bearer as the analyst cookie does not change its authority.
    result = pilot.vendor.request("GET", "/download.zip", headers={"Cookie": ANALYST_SESSION + "=" + pilot.vendor.cookies[VENDOR_SESSION]})
    assert result.status == 401


def test_invitation_alone_and_analyst_cookie_do_not_authenticate_vendor(vendor_pilot):
    pilot = vendor_pilot
    page, _ = _initial(pilot)
    token, _ = _invite(pilot, page)
    before = _counts(pilot)
    for client in (pilot.vendor, pilot.client):
        landing = client.request("GET", "/vendor")
        assert b"Sign in as synthetic vendor" in landing.body and b"Submit evidence to analyst" not in landing.body
        result = client.request("POST", "/vendor/submit", fields=dict(csrf="0" * 64, token=token, kind="test", observed_on=""),
                                files=(("synthetic.txt", b"Synthetic vendor response"),))
        assert result.status == 403
    assert _counts(pilot) == before


@pytest.mark.parametrize("attack", ["revoke", "expire", "sponsor_logout", "vendor_logout", "restart"])
def test_invitation_lifecycle_denies_delivery_without_sql_writes(vendor_pilot, attack):
    pilot = vendor_pilot
    page, _ = _initial(pilot)
    token, page = _invite(pilot, page)
    vendor_page = _vendor_login(pilot.vendor)
    before = _counts(pilot)
    if attack == "revoke":
        fields = _Forms(page.body).forms["/vendor-invitation/revoke"]
        assert pilot.client.request("POST", "/vendor-invitation/revoke", fields=fields).status == 303
    elif attack == "expire":
        # Keep both sessions current so this specifically reaches invitation TTL.
        for delta in (240, 240, 120):
            pilot.ctx.clock[0] += timedelta(seconds=delta)
            assert pilot.client.request("GET", "/").status == 200
            vendor_page = pilot.vendor.request("GET", "/vendor")
    elif attack == "sponsor_logout":
        assert pilot.client.request("POST", "/logout", fields=_Forms(page.body).forms["/logout"]).status == 303
    elif attack == "vendor_logout":
        assert pilot.vendor.request("POST", "/vendor/logout", fields=_Forms(vendor_page.body).forms["/vendor/logout"]).status == 303
    elif attack == "restart":
        replacement = PilotApplication(pilot.identity, pilot.ctx.factory, pilot.ctx.intake, vendor_identity=pilot.vendor_identity)
        pilot.app.handoff = replacement.handoff
        pilot.app.vendor_surface = replacement.vendor_surface
    result = _submit(pilot, token, page=vendor_page)
    assert result.status in (403, 409)
    assert _counts(pilot) == before


@pytest.mark.parametrize("attack", ["csrf", "origin", "host", "filename", "oversize", "invalid_utf8", "two_files", "unknown_field", "future_date"])
def test_hostile_vendor_inputs_fail_without_custody_or_revision_changes(vendor_pilot, attack):
    pilot = vendor_pilot
    page, _ = _initial(pilot)
    token, _ = _invite(pilot, page)
    vendor_page = _vendor_login(pilot.vendor)
    before = _counts(pilot)
    options = {}
    if attack == "csrf":
        options["fields"] = {"csrf": "0" * 64}
    elif attack == "origin":
        options["headers"] = {"Origin": "https://attacker.invalid"}
    elif attack == "host":
        options["headers"] = {"Host": "attacker.invalid"}
    elif attack == "filename":
        options["name"] = "../internal.txt"
    elif attack == "oversize":
        options["content"] = b"x" * 65537
    elif attack == "invalid_utf8":
        options["content"] = b"\xff\xfe\x00malformed"
    elif attack == "two_files":
        options["files"] = (("one.txt", b"one"), ("two.txt", b"two"))
    elif attack == "unknown_field":
        options["fields"] = {"assessment_id": "2001"}
    elif attack == "future_date":
        options["fields"] = {"observed_on": (pilot.ctx.clock[0].date() + timedelta(days=1)).isoformat()}
    result = _submit(pilot, token, page=vendor_page, **options)
    assert result.status in (400, 403, 409)
    assert _counts(pilot) == before
    assert token.encode() not in result.body


def test_replay_and_stale_capture_do_not_duplicate_or_overwrite_originals(vendor_pilot):
    pilot = vendor_pilot
    page, _ = _initial(pilot)
    token, _ = _invite(pilot, page)
    vendor_page = _vendor_login(pilot.vendor)
    assert _submit(pilot, token, page=vendor_page).status == 303
    stale = _Forms(pilot.client.request("GET", "/").body).forms["/vendor-invitation/capture"]
    before = _counts(pilot)
    assert _submit(pilot, token, page=vendor_page).status == 409
    assert _counts(pilot) == before
    page = _review(pilot, pilot.client.request("GET", "/"), "ENC-01", "Challenge", "Review unrelated source before intake.")
    before = _counts(pilot)
    assert pilot.client.request("POST", "/vendor-invitation/capture", fields=stale).status == 409
    assert _counts(pilot) == before
    fresh = _Forms(page.body).forms["/vendor-invitation/capture"]
    assert pilot.client.request("POST", "/vendor-invitation/capture", fields=fresh).status == 303
    after = _counts(pilot)
    assert after == tuple(value + increment for value, increment in zip(before, (1, 1, 1, 1)))
    assert pilot.client.request("POST", "/vendor-invitation/capture", fields=fresh).status == 409
    assert _counts(pilot) == after



def test_pending_delivery_can_be_captured_after_analyst_fresh_login(vendor_pilot):
    pilot = vendor_pilot
    page, _ = _initial(pilot)
    token, _ = _invite(pilot, page)
    _vendor_login(pilot.vendor)
    assert _submit(pilot, token).status == 303
    page = pilot.client.request("GET", "/")
    previous = pilot.client.cookies[ANALYST_SESSION]
    assert pilot.client.request("POST", "/logout", fields=_Forms(page.body).forms["/logout"]).status == 303
    page = pilot.client.login()
    assert pilot.client.cookies[ANALYST_SESSION] != previous
    capture = _Forms(page.body).forms["/vendor-invitation/capture"]
    assert pilot.client.request("POST", "/vendor-invitation/capture", fields=capture).status == 303
    report = _export(pilot.client.request("GET", "/download.zip"), _originals(pilot))
    delivery = next(source["vendor_delivery"] for source in report["persistence"]["source_custody"] if source["vendor_delivery"])
    assert delivery["inviter_session_id"] != delivery["vendor_session_id"]


def test_vendor_source_html_is_escaped_but_original_bytes_remain_intact(vendor_pilot):
    pilot = vendor_pilot
    page, originals = _initial(pilot)
    token, _ = _invite(pilot, page)
    _vendor_login(pilot.vendor)
    content = originals["vendor-dr-exercise.txt"] + b"<script>document.title='injected'</script>\n"
    assert _submit(pilot, token, content=content).status == 303
    capture = _Forms(pilot.client.request("GET", "/").body).forms["/vendor-invitation/capture"]
    result = pilot.client.request("POST", "/vendor-invitation/capture", fields=capture, follow=True)
    assert result.status == 200 and b"<script>" not in result.body and b"&lt;script&gt;" in result.body
    originals["vendor-dr-exercise.txt"] = content
    _export(pilot.client.request("GET", "/download.zip"), originals)


def test_lost_vendor_http_ack_keeps_pending_delivery_and_replay_does_not_duplicate(vendor_pilot, monkeypatch):
    pilot = vendor_pilot
    page, _ = _initial(pilot)
    token, _ = _invite(pilot, page)
    _vendor_login(pilot.vendor)
    redirect = pilot.app.vendor_surface._redirect
    def lost_ack(target, *cookies):
        if target == "/vendor/received":
            raise RuntimeError("Synthetic lost HTTP acknowledgment")
        return redirect(target, *cookies)
    monkeypatch.setattr(pilot.app.vendor_surface, "_redirect", lost_ack)
    before = _counts(pilot)
    assert _submit(pilot, token).status == 400
    assert _submit(pilot, token).status == 409
    assert _counts(pilot) == before
    capture = _Forms(pilot.client.request("GET", "/").body).forms["/vendor-invitation/capture"]
    assert pilot.client.request("POST", "/vendor-invitation/capture", fields=capture).status == 303
    assert _counts(pilot) == tuple(value + increment for value, increment in zip(before, (1, 1, 1, 1)))


def _browser_login(page, pilot, *, vendor=False):
    page.goto(pilot.origin + ("/vendor" if vendor else "/"))
    page.get_by_role("button", name="Sign in as synthetic vendor" if vendor else "Sign in", exact=True).click()
    page.locator('input[type="password"]').fill(VENDOR_PASSWORD if vendor else PASSWORD)
    page.locator('form[action="' + ("/vendor/synthetic-idp/authorize" if vendor else "/synthetic-idp/authorize") + '"] button').click()


def test_chromium_two_independent_profiles_vendor_to_analyst_reassessment_and_zip(vendor_pilot, tmp_path, monkeypatch):
    pilot = vendor_pilot
    required = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("LMA_REQUIRE_BROWSER_TESTS") == "1"
    try:
        playwright = importlib.import_module("playwright.sync_api")
    except ImportError:
        if required:
            pytest.fail("CI must install Playwright for the cross-role browser journey")
        pytest.skip("Install Playwright to run the cross-role browser journey")
    executable = os.getenv("LMA_BROWSER_EXECUTABLE") or shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("chromium-browser")
    trace = []
    original_handle = pilot.app.handle
    def observed(method, target, headers, body=b""):
        result = original_handle(method, target, headers, body)
        trace.append((method, urlsplit(target).path, headers.get("Origin"), result.status))
        return result
    monkeypatch.setattr(pilot.app, "handle", observed)
    with playwright.sync_playwright() as runtime:
        if executable is None and not Path(runtime.chromium.executable_path).is_file():
            if required:
                pytest.fail("CI must install Chromium for the cross-role browser journey")
            pytest.skip("Install Chromium to run the cross-role browser journey")
        browser = runtime.chromium.launch(executable_path=executable, headless=True,
            args=["--ignore-certificate-errors-spki-list=" + pilot.spki, "--no-sandbox"])
        analyst_context = browser.new_context(accept_downloads=True)
        vendor_context = browser.new_context()
        analyst, vendor = analyst_context.new_page(), vendor_context.new_page()
        try:
            _browser_login(analyst, pilot)
            handle = next(item["value"] for item in analyst_context.cookies() if item["name"] == ANALYST_SESSION)
            originals = _seed_typed_originals(pilot, handle)
            analyst.goto(pilot.origin)
            for requirement, action, rationale in (("ENC-01", "Create Finding", "Validate cited TLS alternate listener."),
                    ("BCP-01", "Request Evidence", "Provide completed recovery exercise results.")):
                form = analyst.locator('form[action="/review"]')
                form.locator('select[name="requirement_id"]').select_option(requirement)
                form.locator('select[name="action"]').select_option(action)
                form.locator('textarea[name="rationale"]').fill(rationale)
                if action == "Request Evidence":
                    form.locator('input[name="confirms_insufficiency"]').check()
                form.get_by_role("button", name="Record and save review", exact=True).click()
            analyst.get_by_role("button", name="Finish review", exact=True).click()
            invitation = analyst.locator('form[action="/vendor-invitation/create"]')
            invitation.locator('select[name="requirement_id"]').select_option("BCP-01")
            invitation.get_by_role("button", name="Create local vendor invitation", exact=True).click()
            token = analyst.locator('input[readonly]').input_value()
            assert len(token) == 43
            _browser_login(vendor, pilot, vendor=True)
            assert ANALYST_SESSION not in {item["name"] for item in vendor_context.cookies()}
            assert VENDOR_SESSION not in {item["name"] for item in analyst_context.cookies()}
            form = vendor.locator('form[action="/vendor/submit"]')
            form.locator('input[name="token"]').fill(token)
            form.locator('input[type="file"]').set_input_files({"name": "vendor-dr-exercise.txt", "mimeType": "text/plain", "buffer": originals["vendor-dr-exercise.txt"]})
            form.locator('select[name="kind"]').select_option("test")
            form.locator('input[name="observed_on"]').fill(pilot.ctx.clock[0].date().isoformat())
            form.get_by_role("button", name="Submit evidence to analyst", exact=True).click()
            vendor.get_by_role("heading", name="Submission received", exact=True).wait_for()
            assert "Vendor A" not in vendor.locator("body").inner_text()
            analyst.goto(pilot.origin)
            analyst.get_by_role("button", name="Capture vendor evidence and reassess", exact=True).click()
            analyst.get_by_text("Earlier completion is stale. Review the changed context and explicitly finish again.", exact=True).wait_for()
            analyst.locator("blockquote pre").filter(has_text="Synthetic completed recovery record").first.wait_for(state="attached")
            analyst.get_by_role("button", name="Finish review", exact=True).click()
            analyst.get_by_role("button", name="Sign out", exact=True).click()
            _browser_login(analyst, pilot)
            with analyst.expect_download() as downloading:
                analyst.get_by_role("link", name="Download assessment package", exact=True).click()
            destination = tmp_path / "cross-role-assessment.zip"
            downloading.value.save_as(str(destination))
            report = _export(SimpleNamespace(status=200, headers={"content-type": "application/zip"}, body=destination.read_bytes()), originals)
            custody = next(source for source in report["persistence"]["source_custody"] if source["filename"] == "vendor-dr-exercise.txt")
            assert custody["capture_actor"]["subject"] == "synthetic-analyst"
            assert custody["vendor_delivery"]["vendor_subject"] == "synthetic-vendor"
            assert token not in json.dumps(report)
            posts = [(path, origin, status) for method, path, origin, status in trace if method == "POST"]
            assert {path for path, _, _ in posts} >= {"/login", "/synthetic-idp/authorize", "/review", "/finish", "/vendor-invitation/create",
                "/vendor/login", "/vendor/synthetic-idp/authorize", "/vendor/submit", "/vendor-invitation/capture", "/logout"}
            assert all(origin == pilot.origin and status in (200, 303) for _, origin, status in posts), trace
        finally:
            vendor_context.close()
            analyst_context.close()
            browser.close()
