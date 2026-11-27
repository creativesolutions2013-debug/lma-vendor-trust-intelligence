"""Small upload-only HTTPS subtree for the independently signed vendor fixture.

The parent adapter enforces HTTPS, exact Host/Origin, request framing/body bounds
and response policy before dispatch. This surface never reads analyst cookies,
SQL rows, workspace objects or reports. Invitation tokens enter only POST bodies.
"""
from datetime import date, datetime, timezone
from html import escape
import re
import secrets

from src.server_sessions import ServerSession
from src.synthetic_browser_auth import SyntheticPilotIdentity


SESSION_COOKIE = "__Host-lma_vendor_session"
BINDING_COOKIE = "__Host-lma_vendor_binding"
ANON_COOKIE = "__Host-lma_vendor_anon"
_KINDS = ("assertion", "policy", "configuration", "test")
_SUBMIT_FIELDS = {"csrf", "token", "kind", "observed_on"}


class VendorSurface:
    """Fixed vendor account and one delivery command, with no read capability."""

    def __init__(self, app, identity, handoff):
        from src.synthetic_analyst_pilot import _development
        _development()
        if (type(identity) is not SyntheticPilotIdentity
                or identity.subject != "synthetic-vendor"
                or identity.origin != app.origin
                or identity.config.issuer != app.origin + "/vendor/synthetic-idp"
                or identity.config.client_id != "lma-synthetic-vendor"
                or not callable(getattr(handoff, "submit", None))):
            raise ValueError("Use an independent fixed synthetic vendor identity.")
        self._app, self._identity, self._handoff = app, identity, handoff

    def _session(self, handle):
        session = self._identity.sessions.authenticate(handle)
        return (type(session) is ServerSession
                and session.issuer == self._identity.config.issuer
                and session.subject == "synthetic-vendor"
                and session.audience == self._identity.config.client_id)

    def _response(self, status, body, **kwargs):
        return self._app._response(status, body, **kwargs)

    def _redirect(self, target, *cookies):
        return self._app._redirect(target, *cookies)

    def get(self, path, query, cookies):
        from src.synthetic_analyst_pilot import _cookie
        identity = self._identity
        # Analyst cookies are deliberately never inspected, even when the same
        # browser has authenticated to both independent fixture accounts.
        handle = cookies.get(SESSION_COOKIE, "")
        if path == "/vendor/synthetic-idp/authorize":
            csrf = identity.provider_form_token(query, cookies.get(BINDING_COOKIE, ""))
            hidden = "".join(f'<input type="hidden" name="{escape(k, quote=True)}" '
                f'value="{escape(v, quote=True)}">' for k, v in query.items())
            return self._response(200, '<h2>Synthetic vendor sign-in</h2>'
                '<p>Use the separate vendor fixture password chosen in the terminal.</p>'
                '<form method="post" action="/vendor/synthetic-idp/authorize">' + hidden
                + f'<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
                '<label>Synthetic vendor password <input type="password" name="password" '
                'required autocomplete="off" maxlength="256"></label>'
                '<button>Authenticate synthetic vendor</button></form>')
        if path == "/vendor/oidc/callback":
            new_handle = identity.finish_login(query, cookies.get(BINDING_COOKIE, ""))
            if handle and identity.sessions.authenticate(handle) is not None and not identity.logout(handle):
                identity.logout(new_handle)
                return self._response(503, '<p>Sign-in could not replace the existing vendor session.</p>')
            return self._redirect("/vendor", _cookie(SESSION_COOKIE, new_handle),
                _cookie(BINDING_COOKIE, "", clear=True), _cookie(ANON_COOKIE, "", clear=True))
        if query:
            raise ValueError("Vendor query fields are unavailable.")
        if path not in ("/vendor", "/vendor/received"):
            return self._response(404, '<p>Page unavailable.</p>')
        if not self._session(handle):
            if path != "/vendor":
                return self._response(401, '<p>Sign in as the synthetic vendor.</p>')
            binding = secrets.token_urlsafe(32)
            csrf = identity.browser_csrf(binding)
            return self._response(200, '<h2>Submit synthetic evidence</h2>'
                '<p>Sign in with the vendor fixture account. An invitation alone does not authorize upload.</p>'
                '<form method="post" action="/vendor/login">'
                + f'<input type="hidden" name="csrf" value="{csrf}">'
                '<button>Sign in as synthetic vendor</button></form>',
                headers=(_cookie(ANON_COOKIE, binding),))
        csrf = escape(identity.csrf_token(handle), quote=True)
        logout = ('<form method="post" action="/vendor/logout">'
                  f'<input type="hidden" name="csrf" value="{csrf}">'
                  '<button>Sign out vendor</button></form>')
        if path == "/vendor/received":
            # No assessment ID, source metadata, analyst data or retained token
            # is needed to acknowledge this process-local delivery.
            return self._response(200, '<h2>Submission received</h2>'
                '<p>Your synthetic evidence is pending analyst capture and review. '
                'Receipt does not confirm a control or approve a vendor.</p>' + logout)
        options = "".join(f'<option value="{kind}">{kind}</option>' for kind in _KINDS)
        return self._response(200, '<h2>Submit synthetic evidence</h2>'
            '<p>Use the one-use invitation shared locally by the analyst. '
            'Submit one nonconfidential UTF-8 TXT file, at most 64 KiB. '
            'Document kind and observation date are unverified declarations. '
            'No analyst analysis, notes or reports are available to this account.</p>'
            '<form method="post" action="/vendor/submit" enctype="multipart/form-data">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            '<label>One-use invitation <input type="password" name="token" required '
            'autocomplete="off" minlength="43" maxlength="43"></label>'
            '<label>Synthetic source <input type="file" name="files" accept=".txt,text/plain" required></label>'
            f'<label>Document kind <select name="kind">{options}</select></label>'
            '<label>Observation or test date, if known <input type="date" name="observed_on"></label>'
            '<button>Submit evidence to analyst</button></form>' + logout)

    def post(self, path, fields, files, cookies):
        from src.synthetic_analyst_pilot import _cookie
        if type(fields) is not dict or any(type(k) is not str or type(v) is not str for k, v in fields.items()):
            raise ValueError("Unsupported vendor fields.")
        values = dict(fields)
        csrf = values.pop("csrf", "")
        identity = self._identity
        handle = cookies.get(SESSION_COOKIE, "")
        if path == "/vendor/login":
            if values or files or not identity.valid_browser_csrf(cookies.get(ANON_COOKIE, ""), csrf):
                raise ValueError("Vendor login verification failed.")
            start = identity.begin_login()
            return self._redirect(start.authorization_url, _cookie(BINDING_COOKIE, start.browser_binding))
        if path == "/vendor/synthetic-idp/authorize":
            if files:
                raise ValueError("Vendor authentication cannot accept files.")
            password = values.pop("password", "")
            location = identity.authorize(values, cookies.get(BINDING_COOKIE, ""), password, csrf)
            return self._redirect(location)
        if path not in ("/vendor/logout", "/vendor/submit"):
            return self._response(404, '<p>Page unavailable.</p>')
        if not self._session(handle) or not identity.valid_csrf(handle, csrf):
            return self._response(403, '<p>Vendor session or request verification failed. Sign in and reload.</p>')
        if path == "/vendor/logout":
            if values or files:
                raise ValueError("Unsupported vendor sign-out fields.")
            if not identity.logout(handle):
                return self._response(503, '<p>Sign out was not confirmed. Retry; the vendor session cookie is retained.</p>')
            return self._redirect("/vendor", _cookie(SESSION_COOKIE, "", clear=True))
        if set(fields) != _SUBMIT_FIELDS or type(files) is not tuple or len(files) != 1:
            raise ValueError("Supply one synthetic source and its permitted declarations.")
        item = files[0]
        if type(item) is not tuple or len(item) != 2 or values["kind"] not in _KINDS:
            raise ValueError("Unsupported vendor source.")
        raw_date = values["observed_on"]
        observed_on = None
        if raw_date:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_date) is None:
                raise ValueError("Use a canonical observation date.")
            observed_on = date.fromisoformat(raw_date)
            now = identity.clock()
            if (type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None
                    or observed_on > now.astimezone(timezone.utc).date()):
                raise ValueError("Observation date cannot be in the future.")
        if not self._handoff.submit(handle, identity, values["token"], item[0], item[1],
                                   kind=values["kind"], observed_on=observed_on):
            return self._response(409, '<p>Submission not confirmed. The invitation or authorization may have changed. '
                'Do not resubmit blindly; ask the local analyst to check the handoff.</p>')
        return self._redirect("/vendor/received")
