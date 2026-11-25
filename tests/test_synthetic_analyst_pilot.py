"""Actual loopback HTTPS/browser journey; synthetic databases and credentials only."""
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
from http.client import HTTPSConnection
from http.cookies import SimpleCookie
from io import BytesIO
import importlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit
from uuid import uuid4
from zipfile import ZipFile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest
from sqlalchemy import func, select, update

from src.db import EngagementAccessGrant, Evidence, OrganizationMembership, SyntheticAssessmentRevision, SyntheticEvidenceObject
from src.synthetic_analyst_pilot import PilotApplication, make_https_server
from src.synthetic_browser_auth import SyntheticPilotIdentity
from src.synthetic_custody_guards import synthetic_custody_guard_statements
from src.synthetic_revision_guards import synthetic_revision_guard_statements
from test_resumable_assessment import assessment_ctx


PASSWORD = "synthetic-test-password-only"


class _Forms(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.forms = {}
        self.current = None
        self.feed(content.decode())

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag == "form":
            self.current = values.get("action", "")
            self.forms[self.current] = {}
        elif tag == "input" and self.current is not None and values.get("type") == "hidden":
            self.forms[self.current][values["name"]] = values.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class _Client:
    """Minimal real HTTPS client with verified test certificate and cookie jar."""
    def __init__(self, port, certificate):
        self.port = port
        self.origin = f"https://127.0.0.1:{port}"
        self.context = ssl.create_default_context(cafile=str(certificate))
        assert self.context.check_hostname and self.context.verify_mode == ssl.CERT_REQUIRED
        self.cookies = {}

    def request(self, method, path, *, fields=None, files=(), headers=None, body=None, follow=False):
        headers = dict(headers or {})
        if self.cookies and "Cookie" not in headers:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        if method == "POST":
            headers.setdefault("Origin", self.origin)
        if fields is not None:
            if files:
                boundary = "synthetic-fixture-" + uuid4().hex
                pieces = []
                for name, value in fields.items():
                    pieces.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                                   f'{value}\r\n').encode())
                for name, content in files:
                    pieces.append((f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                                   f'filename="{name}"\r\nContent-Type: text/plain\r\n\r\n').encode()
                                  + content + b"\r\n")
                body = b"".join(pieces) + f"--{boundary}--\r\n".encode()
                headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
            else:
                body = urlencode(fields).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection = HTTPSConnection("127.0.0.1", self.port, context=self.context, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            pairs, content = tuple(response.getheaders()), response.read()
            for name, value in pairs:
                if name.lower() == "set-cookie":
                    parsed = SimpleCookie()
                    parsed.load(value)
                    for key, item in parsed.items():
                        if item["max-age"] == "0" or not item.value:
                            self.cookies.pop(key, None)
                        else:
                            self.cookies[key] = item.value
            result = SimpleNamespace(status=response.status, headers={k.lower(): v for k, v in pairs},
                                     header_pairs=pairs, body=content)
        finally:
            connection.close()
        return self.follow(result) if follow else result

    def follow(self, response):
        for _ in range(8):
            if response.status not in (302, 303):
                return response
            location = response.headers["location"]
            parsed = urlsplit(location)
            assert not parsed.netloc or f"{parsed.scheme}://{parsed.netloc}" == self.origin
            target = parsed.path + ("?" + parsed.query if parsed.query else "")
            response = self.request("GET", target)
        pytest.fail("synthetic sign-in exceeded bounded redirect chain")

    def login(self):
        landing = self.request("GET", "/")
        assert landing.status == 200
        start = self.request("POST", "/login", fields=_Forms(landing.body).forms["/login"])
        authorization = self.follow(start)
        assert authorization.status == 200
        fields = _Forms(authorization.body).forms["/synthetic-idp/authorize"]
        fields["password"] = PASSWORD
        result = self.request("POST", "/synthetic-idp/authorize", fields=fields, follow=True)
        assert result.status == 200 and b"Save evidence and evaluate" in result.body
        assert "__Host-lma_session" in self.cookies
        return result


def _certificate(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-loopback-test")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256()))
    certfile, keyfile = directory / "synthetic-test-cert.pem", directory / "synthetic-test-key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    keyfile.chmod(0o600)
    spki = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return certfile, keyfile, b64encode(sha256(spki).digest()).decode()


@pytest.fixture
def pilot(assessment_ctx, tmp_path, monkeypatch):
    ctx = assessment_ctx
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    identity = SyntheticPilotIdentity(port, PASSWORD, clock=lambda: ctx.clock[0])
    with ctx.factory.begin() as database:
        database.execute(update(OrganizationMembership).where(OrganizationMembership.id == 501)
            .values(issuer=f"https://127.0.0.1:{port}/synthetic-idp", subject="synthetic-analyst"))
    monkeypatch.setenv("AUTH_MODE", "development")
    app = PilotApplication(identity, ctx.factory, ctx.intake)
    certfile, keyfile, spki = _certificate(tmp_path)
    server = make_https_server(app, str(certfile), str(keyfile))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(ctx=ctx, app=app, identity=identity, port=port,
            origin=f"https://127.0.0.1:{port}", certificate=certfile, spki=spki,
            client=_Client(port, certfile))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _content(pilot):
    return (f"Synthetic recovery plan\nService: {pilot.ctx.intake.service}\nEnvironment: production\n"
            f"Observation date: {pilot.ctx.clock[0].date()}\n"
            "Target RTO 120 minutes and RPO 30 minutes. No completed test result is supplied.\n").encode()


def _save(pilot, page, *, content=None, name="recovery-plan.txt", fields=None):
    form = _Forms(page.body).forms["/save"]
    form.update(use_case=pilot.ctx.intake.use_case, kind="policy", requirement_id="BCP-01",
                observed_on=pilot.ctx.clock[0].date().isoformat())
    form.update(fields or {})
    return pilot.client.request("POST", "/save", fields=form,
        files=((name, _content(pilot) if content is None else content),), follow=True)


def _review(pilot, page, *, rationale="Provide completed recovery results and dependency coverage."):
    fields = _Forms(page.body).forms["/review"]
    fields.update(requirement_id="BCP-01", action="Request Evidence", rationale=rationale,
                  confirms_insufficiency="yes")
    return pilot.client.request("POST", "/review", fields=fields, follow=True)


def _counts(pilot):
    with pilot.ctx.factory() as database:
        return tuple(database.execute(select(func.count()).select_from(model)).scalar_one()
                     for model in (Evidence, SyntheticEvidenceObject, SyntheticAssessmentRevision))


def _package(response, content):
    assert response.status == 200 and response.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(response.body)) as archive:
        report = json.loads(archive.read("report.json"))
        artifact, = json.loads(archive.read("manifest.json"))["artifacts"]
        assert archive.read(artifact["archive_path"]) == content
        assert artifact["sha256"] == sha256(content).hexdigest()
        assert report["session_only"] is False and report["risk"]["residual_score"] is None
        assert report["review_completion"]["vendor_approved"] is False
        assert report["review_completion"]["technical_facts_confirmed_by_completion"] is False
        assert report["evidence_gap_reviews"][0]["status"] == "Current"
        assert report["analyst_actions"][0]["citations"][0]["quote"] in content.decode()
        return report


def test_real_https_sign_in_upload_review_leave_fresh_login_resume_and_intact_report(pilot):
    client = pilot.client
    page = client.login()
    assert client.request("GET", "/download.zip").status in (400, 403, 404)
    page = _save(pilot, page)
    assert page.status == 200 and "BCP-01" in page.body.decode()
    rationale = "Provide completed recovery results and dependency coverage."
    page = _review(pilot, page, rationale=rationale)
    assert page.status == 200 and rationale.encode() in page.body
    old_session = client.cookies["__Host-lma_session"]
    logged_out = client.request("POST", "/logout", fields=_Forms(page.body).forms["/logout"], follow=True)
    assert logged_out.status == 200 and "__Host-lma_session" not in client.cookies
    denied = client.request("GET", "/download.zip", headers={"Cookie": "__Host-lma_session=" + old_session})
    assert denied.status in (400, 401, 403)
    page = client.login()
    assert client.cookies["__Host-lma_session"] != old_session and rationale.encode() in page.body
    finished = client.request("POST", "/finish", fields=_Forms(page.body).forms["/finish"], follow=True)
    assert finished.status == 200 and b"Download assessment package" in finished.body
    report = _package(client.request("GET", "/download.zip"), _content(pilot))
    assert next(request["question"] for request in report["targeted_requests"]
                if "BCP-01" in request["requirement_ids"]) == rationale
    assert _counts(pilot)[2] == 3


def test_https_cookie_transport_and_response_cache_controls(pilot):
    response = pilot.client.request("GET", "/")
    cookies = [value for name, value in response.header_pairs if name.lower() == "set-cookie"]
    assert cookies
    for value in cookies:
        parsed = SimpleCookie()
        parsed.load(value)
        for name, item in parsed.items():
            assert name.startswith("__Host-") and item["secure"] and item["httponly"]
            assert item["path"] == "/" and not item["domain"] and item["samesite"].lower() in ("strict", "lax")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    page = pilot.client.login()
    assert page.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("attack", ["host", "origin", "csrf", "cookie", "unknown_id"])
def test_actual_https_host_origin_csrf_tampered_session_and_browser_ids_deny_without_writes(pilot, attack):
    page = pilot.client.login()
    fields = _Forms(page.body).forms["/save"]
    fields.update(kind="policy", requirement_id="BCP-01", use_case=pilot.ctx.intake.use_case)
    headers = {}
    if attack == "host":
        headers["Host"] = "attacker.invalid"
    elif attack == "origin":
        headers["Origin"] = "https://attacker.invalid"
    elif attack == "csrf":
        fields["csrf"] = "forged-token"
    elif attack == "cookie":
        headers["Cookie"] = "__Host-lma_session=" + "x" * 43
    else:
        fields["assessment_id"] = "2001"
    before = _counts(pilot)
    response = pilot.client.request("POST", "/save", fields=fields,
        files=(("recovery-plan.txt", _content(pilot)),), headers=headers)
    assert response.status in (400, 401, 403, 409)
    assert _counts(pilot) == before
    assert b"B secret" not in response.body and b"hidden-org" not in response.body


@pytest.mark.parametrize("name,content", [("too-large.txt", b"x" * 65537),
    ("../unsafe.txt", b"synthetic"), ("not-supported.pdf", b"%PDF-synthetic")])
def test_https_small_txt_limit_and_path_validation_reject_before_custody(pilot, name, content):
    page = pilot.client.login()
    before = _counts(pilot)
    response = _save(pilot, page, name=name, content=content)
    assert response.status in (400, 403, 409, 413)
    assert _counts(pilot) == before


def test_https_stale_revision_and_revoked_grant_do_not_stage_more_originals(pilot):
    page = pilot.client.login()
    first_form = _Forms(page.body).forms["/save"]
    current = _save(pilot, page)
    assert current.status == 200
    before = _counts(pilot)
    stale = _save(pilot, page, fields=first_form)
    assert stale.status in (400, 403, 409) and _counts(pilot) == before
    with pilot.ctx.factory.begin() as database:
        database.execute(update(EngagementAccessGrant).where(EngagementAccessGrant.id == 701).values(status="revoked"))
    denied = pilot.client.request("GET", "/")
    assert denied.status in (400, 401, 403) and b"Synthetic analytics review" not in denied.body
    assert pilot.client.request("GET", "/download.zip").status in (400, 401, 403)
    assert _counts(pilot) == before


@pytest.mark.parametrize("framing", ["duplicate_host", "duplicate_length", "chunked", "oversized_length"])
def test_real_tls_rejects_duplicate_authority_and_ambiguous_request_framing(pilot, framing):
    before = _counts(pilot)
    headers = [f"Host: 127.0.0.1:{pilot.port}", "Connection: close"]
    if framing == "duplicate_host":
        headers += ["Host: attacker.invalid", "Content-Length: 0"]
    elif framing == "duplicate_length":
        headers += ["Content-Length: 0", "Content-Length: 1"]
    elif framing == "chunked":
        headers += ["Transfer-Encoding: chunked", "Content-Length: 0"]
    else:
        headers += ["Content-Length: 9999999"]
    request = ("POST /save HTTP/1.1\r\n" + "\r\n".join(headers) + "\r\n\r\n").encode()
    context = ssl.create_default_context(cafile=str(pilot.certificate))
    with socket.create_connection(("127.0.0.1", pilot.port), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname="127.0.0.1") as connection:
            connection.sendall(request)
            first = connection.recv(4096).split(b"\r\n", 1)[0]
    assert int(first.split()[1]) in (400, 413)
    assert _counts(pilot) == before


def test_expired_browser_session_cannot_resume_or_download_saved_sources(pilot):
    page = _save(pilot, pilot.client.login())
    assert page.status == 200
    before = _counts(pilot)
    pilot.ctx.clock[0] += timedelta(days=1)
    expired = pilot.client.request("GET", "/")
    assert expired.status == 200 and b"<button>Sign in</button>" in expired.body
    assert b"Save evidence and evaluate" not in expired.body
    assert pilot.client.request("GET", "/download.zip").status == 401
    assert _counts(pilot) == before


@pytest.mark.parametrize("target", ["state", "original_bytes"])
def test_actual_https_withholds_report_for_tampered_persisted_state_or_bytes(pilot, target):
    page = _save(pilot, pilot.client.login())
    assert page.status == 200
    model = SyntheticAssessmentRevision if target == "state" else SyntheticEvidenceObject
    field = model.state_payload if target == "state" else model.payload
    prefix = "m7_revision" if target == "state" else "m7_custody"
    statements = synthetic_revision_guard_statements if target == "state" else synthetic_custody_guard_statements
    quote = pilot.ctx.engine.dialect.identifier_preparer.quote
    relation = (quote(pilot.ctx.schema) + "." if pilot.ctx.schema else "") + quote(model.__tablename__)
    postgres = pilot.ctx.engine.dialect.name == "postgresql"
    trigger = quote(prefix + ("_no_mutation" if postgres else "_no_update"))
    # Deliberate administrator-only corruption in a disposable fixture. Restore
    # guard health before HTTP so the request exercises integrity validation.
    with pilot.ctx.engine.begin() as connection:
        original = connection.execute(select(field)).scalar_one()
        connection.exec_driver_sql(f"ALTER TABLE {relation} DISABLE TRIGGER {trigger}" if postgres else
                                   f"DROP TRIGGER {trigger}")
        connection.execute(update(model).values({field.key: b"X" + original[1:]}))
        if postgres:
            connection.exec_driver_sql(f"ALTER TABLE {relation} ENABLE ALWAYS TRIGGER {trigger}")
        else:
            statement = next(value for value in statements(pilot.ctx.engine.dialect)
                             if value.startswith("CREATE TRIGGER " + prefix + "_no_update "))
            connection.exec_driver_sql(statement)
    before = _counts(pilot)
    unavailable = pilot.client.request("GET", "/download.zip")
    assert unavailable.status in (400, 403)
    assert _content(pilot) not in unavailable.body
    refused = _review(pilot, page)
    assert refused.status in (400, 403, 409) and _counts(pilot) == before


@pytest.mark.parametrize("change", ["rotated_session", "sibling_grant"])
def test_browser_cannot_reuse_session_or_grant_for_another_scope(pilot, change):
    page = _save(pilot, pilot.client.login())
    assert page.status == 200
    if change == "rotated_session":
        assert pilot.identity.sessions.rotate(pilot.client.cookies["__Host-lma_session"])
    else:
        with pilot.ctx.factory.begin() as database:
            database.execute(update(EngagementAccessGrant).where(EngagementAccessGrant.id == 701)
                             .values(engagement_id=102))
    before = _counts(pilot)
    assert pilot.client.request("GET", "/download.zip").status in (400, 401, 403)
    assert _review(pilot, page).status in (400, 403, 409)
    assert _counts(pilot) == before


def test_https_logout_outage_retains_cookie_and_does_not_claim_revocation(pilot, monkeypatch):
    page = pilot.client.login()
    handle = pilot.client.cookies["__Host-lma_session"]
    with monkeypatch.context() as patch:
        patch.setattr(pilot.identity.sessions, "revoke", lambda value: False)
        response = pilot.client.request("POST", "/logout", fields=_Forms(page.body).forms["/logout"])
        assert response.status == 503
        assert pilot.client.cookies["__Host-lma_session"] == handle
        assert not any(name.lower() == "set-cookie" for name, _ in response.header_pairs)
        assert pilot.identity.sessions.authenticate(handle) is not None


@pytest.mark.parametrize("attack", ["duplicate_cookie", "duplicate_form"])
def test_https_duplicate_security_values_are_not_resolved_by_first_or_last_value(pilot, attack):
    page = pilot.client.login()
    csrf = _Forms(page.body).forms["/logout"]["csrf"]
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if attack == "duplicate_cookie":
        handle = pilot.client.cookies["__Host-lma_session"]
        headers["Cookie"] = f"__Host-lma_session={handle}; __Host-lma_session={handle}"
        body = urlencode({"csrf": csrf}).encode()
    else:
        body = urlencode((("csrf", csrf), ("csrf", csrf))).encode()
    before = _counts(pilot)
    denied = pilot.client.request("POST", "/logout", headers=headers, body=body)
    assert denied.status == 400 and _counts(pilot) == before


def test_actual_https_callback_replay_cannot_issue_another_session(pilot):
    client = pilot.client
    landing = client.request("GET", "/")
    provider = client.request("POST", "/login", fields=_Forms(landing.body).forms["/login"], follow=True)
    fields = _Forms(provider.body).forms["/synthetic-idp/authorize"]
    fields["password"] = PASSWORD
    authorized = client.request("POST", "/synthetic-idp/authorize", fields=fields)
    assert authorized.status == 303
    callback = urlsplit(authorized.headers["location"])
    target = callback.path + "?" + callback.query
    signed_in = client.follow(authorized)
    assert signed_in.status == 200
    handle = client.cookies["__Host-lma_session"]
    replay = client.request("GET", target)
    assert replay.status == 400 and client.cookies["__Host-lma_session"] == handle
    assert client.request("GET", "/").status == 200


def test_chromium_actual_forms_fresh_login_resume_and_download(pilot, tmp_path, monkeypatch):
    required = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("LMA_REQUIRE_BROWSER_TESTS") == "1"
    try:
        playwright = importlib.import_module("playwright.sync_api")
    except ImportError:
        if required:
            pytest.fail("CI must install Playwright for the actual browser journey")
        pytest.skip("install Playwright to run the actual browser journey")
    executable = (os.getenv("LMA_BROWSER_EXECUTABLE") or shutil.which("chromium")
                  or shutil.which("google-chrome") or shutil.which("chromium-browser"))
    with playwright.sync_playwright() as runtime:
        if executable is None and not Path(runtime.chromium.executable_path).is_file():
            if required:
                pytest.fail("CI must install Chromium for the actual browser journey")
            pytest.skip("install Chromium to run the actual browser journey")
        # Trust only this disposable certificate's SPKI. Never set a global
        # --ignore-certificate-errors flag or ignore_https_errors context option.
        browser = runtime.chromium.launch(executable_path=executable, headless=True,
            args=["--ignore-certificate-errors-spki-list=" + pilot.spki, "--no-sandbox"])
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        requests = []
        original_handle = pilot.app.handle
        def observed(method, target, headers, body=b""):
            result = original_handle(method, target, headers, body)
            requests.append((method, urlsplit(target).path, headers.get("Origin"),
                             headers.get("Cookie") is not None, result.status))
            return result
        monkeypatch.setattr(pilot.app, "handle", observed)
        try:
            page.goto(pilot.origin)
            page.get_by_role("button", name="Sign in", exact=True).click()
            try:
                page.locator('input[type="password"]').wait_for(timeout=5000)
            except playwright.TimeoutError:
                pytest.fail(f"Browser sign-in did not reach the provider; sanitized HTTP trace: {requests}")
            page.locator('input[type="password"]').fill(PASSWORD)
            page.locator('form[action="/synthetic-idp/authorize"] button').click()
            upload = page.locator('form[action="/save"]')
            upload.locator('input[type="file"]').set_input_files({
                "name": "recovery-plan.txt", "mimeType": "text/plain", "buffer": _content(pilot)})
            upload.locator('select[name="kind"]').select_option("policy")
            upload.locator('select[name="requirement_id"]').select_option("BCP-01")
            upload.locator('input[name="observed_on"]').fill(pilot.ctx.clock[0].date().isoformat())
            upload.get_by_role("button", name="Save evidence and evaluate", exact=True).click()
            page.get_by_text("recovery-plan.txt · Line 1", exact=True).click()
            page.locator("blockquote pre").filter(has_text="Synthetic recovery plan").wait_for(state="visible")
            review = page.locator('form[action="/review"]')
            review.locator('select[name="requirement_id"]').select_option("BCP-01")
            review.locator('select[name="action"]').select_option("Request Evidence")
            rationale = "Provide actual completed recovery results."
            review.locator('textarea[name="rationale"]').fill(rationale)
            review.locator('input[name="confirms_insufficiency"]').check()
            review.get_by_role("button", name="Record and save review", exact=True).click()
            history = page.locator("p").filter(has_text="BCP-01").filter(
                has_text="Request Evidence").filter(has_text=rationale).first
            history.wait_for(state="visible")
            page.get_by_role("button", name="Sign out", exact=True).click()
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.locator('input[type="password"]').fill(PASSWORD)
            page.locator('form[action="/synthetic-idp/authorize"] button').click()
            history.wait_for(state="visible")
            page.get_by_role("button", name="Finish review", exact=True).click()
            with page.expect_download() as downloading:
                page.get_by_role("link", name="Download assessment package", exact=True).click()
            download = downloading.value
            packaged = tmp_path / "browser-assessment.zip"
            download.save_as(str(packaged))
            response = SimpleNamespace(status=200, headers={"content-type": "application/zip"}, body=packaged.read_bytes())
            report = _package(response, _content(pilot))
            assert report["analyst_actions"][0]["rationale"] == rationale
            posts = [(path, origin, status) for method, path, origin, _, status in requests if method == "POST"]
            assert {path for path, _, _ in posts} >= {"/login", "/synthetic-idp/authorize", "/save", "/review", "/logout", "/finish"}
            assert all(origin == pilot.origin and status == 303 for _, origin, status in posts)
            screenshot = os.getenv("LMA_PILOT_BROWSER_SCREENSHOT")
            if screenshot:
                page.screenshot(path=screenshot, full_page=True)
        finally:
            context.close()
            browser.close()
