"""Vendor-only HTML/auth dispatch; the HTTPS adapter is tested separately."""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest

from src.oidc_login import LoginRejected
from src.synthetic_browser_auth import SyntheticPilotIdentity
from src.synthetic_vendor_surface import ANON_COOKIE, BINDING_COOKIE, SESSION_COOKIE, VendorSurface


PASSWORD = "Synthetic-vendor-only-fixture-73"
ANALYST_PASSWORD = "Synthetic-analyst-only-fixture-42"
TOKEN = "a" * 43
NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)


class _App:
    origin = "https://127.0.0.1:8443"

    def _response(self, status, body, *, headers=()):
        return SimpleNamespace(status=status, body=body.encode(), headers=headers)

    def _redirect(self, target, *cookies):
        return self._response(303, "Continue.", headers=(("Location", target), *cookies))


class _Forms(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.forms, self.current = {}, None
        self.feed(body.decode())

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag == "form":
            self.current = values["action"]
            self.forms[self.current] = {}
        elif tag == "input" and self.current and values.get("type") == "hidden":
            self.forms[self.current][values["name"]] = values["value"]

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class _Handoff:
    def __init__(self):
        self.calls, self.accept = [], True

    def submit(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.accept


def _receive(ctx, response):
    for name, value in response.headers:
        if name == "Set-Cookie":
            parsed = SimpleCookie()
            parsed.load(value)
            for key, item in parsed.items():
                assert item["secure"] and item["httponly"] and item["samesite"] == "Lax"
                assert item["path"] == "/" and not item["domain"]
                if item["max-age"] == "0":
                    ctx.cookies.pop(key, None)
                else:
                    ctx.cookies[key] = item.value
    return response


def _get(ctx, target="/vendor"):
    parsed = urlsplit(target)
    assert not parsed.netloc or parsed.scheme + "://" + parsed.netloc == _App.origin
    return _receive(ctx, ctx.surface.get(parsed.path, dict(parse_qsl(parsed.query)), ctx.cookies))


def _post(ctx, target, fields, files=()):
    return _receive(ctx, ctx.surface.post(target, fields, files, ctx.cookies))


def _start(ctx):
    landing = _get(ctx)
    started = _post(ctx, "/vendor/login", _Forms(landing.body).forms["/vendor/login"])
    return _get(ctx, dict(started.headers)["Location"])


def _login(ctx):
    authorization = _start(ctx)
    fields = _Forms(authorization.body).forms["/vendor/synthetic-idp/authorize"]
    fields["password"] = PASSWORD
    response = _post(ctx, "/vendor/synthetic-idp/authorize", fields)
    callback = dict(response.headers)["Location"]
    assert _get(ctx, callback).status == 303
    return _get(ctx), callback


def _submission(ctx, **changes):
    fields = _Forms(_get(ctx).body).forms["/vendor/submit"]
    fields.update(token=TOKEN, kind="test", observed_on=NOW.date().isoformat())
    fields.update(changes)
    return fields


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    clock = [NOW]
    identity = SyntheticPilotIdentity(8443, PASSWORD, vendor=True, clock=lambda: clock[0])
    handoff = _Handoff()
    return SimpleNamespace(identity=identity, handoff=handoff,
        surface=VendorSurface(_App(), identity, handoff), cookies={}, clock=clock)


def test_signed_vendor_login_uses_only_independent_cookies_and_rejects_callback_replay(ctx):
    page, callback = _login(ctx)
    assert page.status == 200 and "/vendor/submit" in _Forms(page.body).forms
    assert set(ctx.cookies) == {SESSION_COOKIE}
    session = ctx.identity.sessions.authenticate(ctx.cookies[SESSION_COOKIE])
    assert session.subject == "synthetic-vendor"
    assert session.audience == "lma-synthetic-vendor"
    with pytest.raises(LoginRejected):
        _get(ctx, callback)


def test_invitation_alone_or_analyst_cookie_cannot_authorize_upload(ctx):
    analyst = SyntheticPilotIdentity(8443, ANALYST_PASSWORD, clock=lambda: NOW)
    begun = analyst.begin_login()
    params = dict(parse_qsl(urlsplit(begun.authorization_url).query))
    callback = analyst.authorize(params, begun.browser_binding, ANALYST_PASSWORD,
                                 analyst.provider_form_token(params, begun.browser_binding))
    handle = analyst.finish_login(dict(parse_qsl(urlsplit(callback).query)), begun.browser_binding)
    ctx.cookies["__Host-lma_session"] = handle
    page = _get(ctx)
    assert "/vendor/login" in _Forms(page.body).forms
    fields = dict(csrf=analyst.csrf_token(handle), token=TOKEN, kind="test", observed_on="")
    assert _post(ctx, "/vendor/submit", fields, (("source.txt", b"synthetic"),)).status == 403
    # Even putting an analyst handle under the vendor cookie name cannot change
    # the independent session store from which vendor authority is obtained.
    ctx.cookies[SESSION_COOKIE] = handle
    assert _post(ctx, "/vendor/submit", fields, (("source.txt", b"synthetic"),)).status == 403
    assert not ctx.handoff.calls


def test_submission_posts_token_only_and_acknowledges_no_source_or_assessment_data(ctx):
    _login(ctx)
    filename, content = "private-synthetic-source.txt", b"Synthetic-only evidence text"
    response = _post(ctx, "/vendor/submit", _submission(ctx), ((filename, content),))
    assert response.status == 303 and dict(response.headers)["Location"] == "/vendor/received"
    page = _get(ctx, "/vendor/received")
    assert page.status == 200 and b"pending analyst capture" in page.body
    assert TOKEN.encode() not in page.body + response.body
    assert filename.encode() not in page.body and content not in page.body
    args, kwargs = ctx.handoff.calls[0]
    assert args == (ctx.cookies[SESSION_COOKIE], ctx.identity, TOKEN, filename, content)
    assert kwargs == dict(kind="test", observed_on=NOW.date())


@pytest.mark.parametrize("extra", ["assessment_id", "organization_id", "requirement_id", "role", "expected_revision"])
def test_vendor_cannot_submit_scope_or_analyst_fields(ctx, extra):
    _login(ctx)
    fields = _submission(ctx, **{extra: "1001"})
    with pytest.raises(ValueError):
        _post(ctx, "/vendor/submit", fields, (("source.txt", b"synthetic"),))
    assert not ctx.handoff.calls


@pytest.mark.parametrize("value", ["2026-11-26", "2026-11-25T00:00:00Z", "2026-2-3", "2026-02-31"])
def test_bad_or_future_observation_dates_deny_before_handoff(ctx, value):
    _login(ctx)
    with pytest.raises(ValueError):
        _post(ctx, "/vendor/submit", _submission(ctx, observed_on=value), (("source.txt", b"synthetic"),))
    assert not ctx.handoff.calls


def test_vendor_accepts_only_one_source_and_current_session_csrf(ctx):
    _login(ctx)
    fields = _submission(ctx)
    files = (("one.txt", b"one"), ("two.txt", b"two"))
    with pytest.raises(ValueError):
        _post(ctx, "/vendor/submit", fields, files)
    fields["csrf"] = "f" * 64
    assert _post(ctx, "/vendor/submit", fields, files[:1]).status == 403
    assert not ctx.handoff.calls


@pytest.mark.parametrize("path", ["/vendor/download.zip", "/vendor/review", "/vendor/finish", "/vendor/save"])
def test_vendor_has_no_analyst_routes_even_when_both_cookies_exist(ctx, path):
    _login(ctx)
    ctx.cookies["__Host-lma_session"] = "a" * 43
    assert _get(ctx, path).status == 404
    assert _post(ctx, path, {}).status == 404
    assert not ctx.handoff.calls


def test_expired_vendor_cannot_submit_even_with_valid_invitation_and_old_csrf(ctx):
    _login(ctx)
    fields = _submission(ctx)
    ctx.clock[0] += timedelta(days=1)
    assert _post(ctx, "/vendor/submit", fields, (("source.txt", b"synthetic"),)).status == 403
    assert not ctx.handoff.calls


def test_logout_clears_only_vendor_cookie_and_preserves_cookie_on_revoke_failure(ctx, monkeypatch):
    page, _ = _login(ctx)
    ctx.cookies["__Host-lma_session"] = "b" * 43
    fields = _Forms(page.body).forms["/vendor/logout"]
    original = ctx.identity.logout
    monkeypatch.setattr(ctx.identity, "logout", lambda handle: False)
    response = _post(ctx, "/vendor/logout", fields)
    assert response.status == 503 and not response.headers
    assert SESSION_COOKIE in ctx.cookies
    monkeypatch.setattr(ctx.identity, "logout", original)
    assert _post(ctx, "/vendor/logout", fields).status == 303
    assert ctx.cookies == {"__Host-lma_session": "b" * 43}


def test_denied_handoff_returns_generic_conflict_without_token_reflection(ctx):
    _login(ctx)
    ctx.handoff.accept = False
    response = _post(ctx, "/vendor/submit", _submission(ctx), (("source.txt", b"synthetic"),))
    assert response.status == 409 and TOKEN.encode() not in response.body
    assert b"Do not resubmit blindly" in response.body


def test_surface_refuses_analyst_identity_as_vendor(ctx):
    analyst = SyntheticPilotIdentity(8443, ANALYST_PASSWORD, clock=lambda: NOW)
    with pytest.raises(ValueError):
        VendorSurface(_App(), analyst, ctx.handoff)
