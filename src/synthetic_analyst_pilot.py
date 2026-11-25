"""Explicit development-only HTTPS pilot; never a production/legacy app login.

Run with ``AUTH_MODE=development python -m src.synthetic_analyst_pilot --directory
/tmp/lma-synthetic-pilot``. Only a dedicated synthetic database is supported.
"""
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import re
import secrets
import ssl
from urllib.parse import parse_qsl, urlsplit


MAX_BODY = 320 * 1024
SESSION_COOKIE = "__Host-lma_session"
BINDING_COOKIE = "__Host-lma_binding"
ANON_COOKIE = "__Host-lma_anon"
_CRITICAL_HEADERS = {"host", "cookie", "origin", "content-length", "content-type"}


def _development():
    if os.environ.get("AUTH_MODE") != "development":
        raise ValueError("Synthetic pilot requires explicit AUTH_MODE=development.")


@dataclass(frozen=True)
class Response:
    status: int
    headers: tuple
    body: bytes


def _cookie(name, value, *, clear=False):
    jar = SimpleCookie()
    jar[name] = value
    jar[name]["path"] = "/"
    jar[name]["secure"] = True
    jar[name]["httponly"] = True
    jar[name]["samesite"] = "Lax"
    if clear:
        jar[name]["max-age"] = 0
    return ("Set-Cookie", jar.output(header="").strip())


def _pairs(text):
    pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True,
                      encoding="utf-8", errors="strict", max_num_fields=30)
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError()
    return dict(pairs)


def _cookies(value):
    if len(value) > 4096:
        raise ValueError()
    result = {}
    if not value:
        return result
    for part in value.split(";"):
        name, separator, item = part.strip().partition("=")
        if (not separator or name in result or not name or len(result) >= 12
                or re.fullmatch(r"[A-Za-z0-9_=-]{1,256}", item) is None):
            raise ValueError()
        result[name] = item
    return result


def _multipart(content_type, body):
    if len(content_type) > 200 or "\r" in content_type or "\n" in content_type:
        raise ValueError()
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    if (message.get_content_type() != "multipart/form-data" or not message.is_multipart()
            or message.defects):
        raise ValueError()
    fields, files = {}, []
    parts = list(message.iter_parts())
    if not 1 <= len(parts) <= 16:
        raise ValueError()
    for part in parts:
        if (part.is_multipart() or part.defects or part.get_content_disposition() != "form-data"
                or part.get("Content-Transfer-Encoding") is not None
                or len(part.get_all("Content-Disposition", [])) != 1
                or len(part.get_all("Content-Type", [])) > 1):
            raise ValueError()
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        data = part.get_payload(decode=True)
        if type(name) is not str or type(data) is not bytes:
            raise ValueError()
        if filename is not None:
            if name != "files" or len(files) >= 4 or not 1 <= len(data) <= 65536:
                raise ValueError()
            files.append((filename, data))
        elif name in fields or len(data) > 4000:
            raise ValueError()
        else:
            fields[name] = data.decode("utf-8", errors="strict")
    return fields, tuple(files)


def _page(body):
    return ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>LMA synthetic analyst</title><link rel='stylesheet' href='/style.css'>"
            "<body><main><h1>LMA synthetic analyst</h1><p>Development-only synthetic pilot. "
            "No confidential evidence, production identity or automatic risk decisions.</p>"
            + body + "</main></body></html>")


class PilotApplication:
    def __init__(self, identity, factory, intake):
        _development()  # Must precede imports that initialize legacy DB dependencies.
        from src.synthetic_browser_auth import SyntheticPilotIdentity
        from src.synthetic_analyst_workspace import PilotWorkspace
        if type(identity) is not SyntheticPilotIdentity:
            raise ValueError("A server-configured synthetic identity is required.")
        self.identity = identity
        self.workspace = PilotWorkspace(factory, intake)
        self.origin = identity.origin
        self.host = urlsplit(self.origin).netloc

    def _response(self, status, body, *, headers=(), content_type="text/html; charset=utf-8"):
        data = body if type(body) is bytes else _page(body).encode("utf-8")
        return Response(status, (
            ("Content-Type", content_type), ("Content-Length", str(len(data))),
            ("Cache-Control", "no-store"), ("Pragma", "no-cache"),
            ("Content-Security-Policy", "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"),
            # Chromium otherwise sends Origin:null for native form POSTs.
            # Origin-only referrers also keep callback code/state out of URLs
            # passed as referrers. Exact POST Origin validation remains required.
            ("Referrer-Policy", "strict-origin"), ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"), *headers,
        ), data)

    def _redirect(self, location, *cookies):
        return self._response(303, "<p>Continue.</p>", headers=(("Location", location), *cookies))

    def handle(self, method, target, headers, body=b""):
        try:
            _development()
            items = list(headers.items()) if hasattr(headers, "items") else list(headers)
            lowered = [str(key).lower() for key, _ in items]
            if (any(lowered.count(key) > 1 for key in _CRITICAL_HEADERS)
                    or any(key in lowered for key in ("transfer-encoding", "forwarded", "x-forwarded-host", "x-forwarded-proto"))
                    or sum(len(str(k)) + len(str(v)) for k, v in items) > 16384):
                raise ValueError()
            header = {str(k).lower(): v for k, v in items}
            if header.get("host") != self.host or len(target) > 8192 or not target.startswith("/"):
                raise ValueError()
            url = urlsplit(target)
            if url.scheme or url.netloc or url.fragment or len(body) > MAX_BODY:
                raise ValueError()
            cookies = _cookies(header.get("cookie", ""))
            handle = cookies.get(SESSION_COOKIE, "")
            if method == "GET":
                if body or header.get("content-length", "0") != "0":
                    raise ValueError()
                query = _pairs(url.query)
                return self._get(url.path, query, cookies, handle)
            if method != "POST":
                return self._response(405, "<p>Method unavailable.</p>")
            if url.query or header.get("origin") != self.origin:
                raise ValueError()
            length = header.get("content-length", "")
            if re.fullmatch(r"0|[1-9][0-9]{0,6}", length) is None or int(length) != len(body):
                raise ValueError()
            content_type = header.get("content-type", "")
            if content_type.startswith("multipart/form-data;") and url.path == "/save":
                fields, files = _multipart(content_type, body)
            elif content_type == "application/x-www-form-urlencoded":
                fields, files = _pairs(body.decode("utf-8", errors="strict")), ()
            else:
                raise ValueError()
            return self._post(url.path, fields, files, cookies, handle)
        except Exception:
            # Do not reflect source, password, code, session or SQL diagnostics.
            return self._response(400, "<p>Request rejected. Reload and sign in again if needed.</p>")

    def _get(self, path, query, cookies, handle):
        if path == "/synthetic-idp/authorize":
            csrf = self.identity.provider_form_token(query, cookies.get(BINDING_COOKIE, ""))
            hidden = "".join(f"<input type='hidden' name='{escape(k, quote=True)}' value='{escape(v, quote=True)}'>"
                             for k, v in query.items())
            return self._response(200, "<h2>Synthetic IdP sign-in</h2><p>Use only the local fixture password chosen in the terminal.</p>"
                "<form method='post' action='/synthetic-idp/authorize'>" + hidden
                + f"<input type='hidden' name='csrf' value='{escape(csrf, quote=True)}'>"
                + "<label>Synthetic password <input type='password' name='password' required autocomplete='off' maxlength='256'></label>"
                "<button>Authenticate synthetic analyst</button></form>")
        if path == "/oidc/callback":
            new_handle = self.identity.finish_login(query, cookies.get(BINDING_COOKIE, ""))
            # Any pre-existing valid session must be revoked, not silently abandoned.
            if handle and self.identity.sessions.authenticate(handle) is not None and not self.identity.logout(handle):
                self.identity.logout(new_handle)
                return self._response(503, "<p>Sign-in could not replace the existing session.</p>")
            return self._redirect("/", _cookie(SESSION_COOKIE, new_handle), _cookie(BINDING_COOKIE, "", clear=True),
                                  _cookie(ANON_COOKIE, "", clear=True))
        if query:
            raise ValueError()
        if path == "/style.css":
            return self._response(200, b"body{font:17px system-ui;margin:2rem auto;max-width:950px;padding:0 1rem;color:#152d3b;background:#f4f7f8}main{background:white;padding:2rem}label{display:block;margin:1rem 0}input,select,textarea,button{font:inherit;max-width:100%;padding:.4rem}textarea{width:95%}section,article{border-top:1px solid #bdcbd2;margin-top:1rem;padding-top:1rem}blockquote{white-space:pre-wrap;border-left:3px solid #58829b;padding-left:1rem}button{cursor:pointer}small{display:block}", content_type="text/css; charset=utf-8")
        if path not in ("/", "/download.zip"):
            return self._response(404, "<p>Page unavailable.</p>")
        if self.identity.sessions.authenticate(handle) is None:
            if path != "/":
                return self._response(401, "<p>Sign in to retrieve the report.</p>")
            binding = secrets.token_urlsafe(32)
            csrf = self.identity.browser_csrf(binding)
            return self._response(200, "<h2>Start or resume your assessment</h2>"
                "<form method='post' action='/login'>"
                + f"<input type='hidden' name='csrf' value='{csrf}'>"
                + "<button>Sign in</button></form>", headers=(_cookie(ANON_COOKIE, binding),))
        if not self.workspace.available(handle, self.identity):
            return self._response(403, "<p>Assessment unavailable for this session.</p>")
        result = self.workspace.resume(handle, self.identity)
        if path == "/download.zip":
            if result is None:
                return self._response(403, "<p>Report unavailable. Resume the current assessment first.</p>")
            return self._response(200, result.package, content_type="application/zip",
                                  headers=(("Content-Disposition", 'attachment; filename="synthetic-assessment.zip"'),))
        from src.synthetic_analyst_workspace import render_workspace
        return self._response(200, render_workspace(self.workspace.intake, result, self.identity.csrf_token(handle)))

    def _post(self, path, fields, files, cookies, handle):
        csrf = fields.pop("csrf", "")
        if path == "/login":
            if fields or files or not self.identity.valid_browser_csrf(cookies.get(ANON_COOKIE, ""), csrf):
                raise ValueError()
            start = self.identity.begin_login()
            return self._redirect(start.authorization_url, _cookie(BINDING_COOKIE, start.browser_binding))
        if path == "/synthetic-idp/authorize":
            password = fields.pop("password", "")
            location = self.identity.authorize(fields, cookies.get(BINDING_COOKIE, ""), password, csrf)
            return self._redirect(location)
        if not self.identity.valid_csrf(handle, csrf):
            return self._response(403, "<p>Session or request verification failed. Sign in and reload.</p>")
        if path == "/logout":
            if fields or files:
                raise ValueError()
            if not self.identity.logout(handle):
                return self._response(503, "<p>Sign out was not confirmed. Retry; the session cookie is retained.</p>")
            return self._redirect("/", _cookie(SESSION_COOKIE, "", clear=True))
        revision = fields.pop("expected_revision", "")
        if re.fullmatch(r"0|[1-9][0-9]{0,9}", revision) is None:
            raise ValueError()
        revision = int(revision)
        if path == "/save":
            success = self.workspace.save(handle, self.identity, revision, fields, files)
        elif path == "/review" and not files:
            success = self.workspace.review(handle, self.identity, revision, fields)
        elif path == "/finish" and not fields and not files:
            success = self.workspace.finish(handle, self.identity, revision)
        else:
            raise ValueError()
        if not success:
            return self._response(409, "<p>Change not confirmed. Authorization, evidence or revision may have changed. "
                "<a href='/'>Resume latest</a> before retrying. A stored revision or unattached original may remain; do not retry blindly.</p>")
        return self._redirect("/")


def make_https_server(app, certfile, keyfile):
    """One local worker, bounded reads, no request/credential/query logging."""
    _development()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile, keyfile)

    class Handler(BaseHTTPRequestHandler):
        server_version = "LMA-synthetic"
        sys_version = ""

        def log_message(self, *args):
            pass

        def do_GET(self):
            self._dispatch()

        def do_POST(self):
            self._dispatch()

        def do_HEAD(self):
            self._dispatch()

        def _dispatch(self):
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if (len(lengths) > 1 or self.headers.get_all("Transfer-Encoding")
                        or (lengths and re.fullmatch(r"0|[1-9][0-9]{0,6}", lengths[0]) is None)):
                    raise ValueError()
                length = int(lengths[0]) if lengths else 0
                if length > MAX_BODY:
                    raise ValueError()
                body = self.rfile.read(length) if length else b""
                result = app.handle(self.command, self.path, self.headers, body)
            except Exception:
                result = app._response(400, "<p>Request rejected.</p>")
            self.send_response(result.status)
            for key, value in result.headers:
                self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(result.body)
            self.close_connection = True

    class LocalHTTPServer(HTTPServer):
        allow_reuse_address = True

        def get_request(self):
            connection, address = self.socket.accept()
            try:
                connection.settimeout(5)
                return context.wrap_socket(connection, server_side=True), address
            except Exception:
                connection.close()
                raise OSError("Synthetic TLS connection rejected.") from None

    return LocalHTTPServer(("127.0.0.1", urlsplit(app.origin).port), Handler)


def main():
    _development()
    if os.getenv("DATABASE_URL"):
        raise ValueError("Unset DATABASE_URL; this pilot uses only its dedicated synthetic directory.")
    import argparse
    from getpass import getpass
    from src.synthetic_browser_auth import SyntheticPilotIdentity
    from src.synthetic_pilot_runtime import prepare_runtime
    parser = argparse.ArgumentParser(description="Loopback HTTPS synthetic analyst pilot only")
    parser.add_argument("--directory", required=True, help="Dedicated private synthetic pilot directory")
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()
    password = getpass("Choose a synthetic-only IdP password (at least 16 characters): ")
    identity = SyntheticPilotIdentity(args.port, password)
    del password
    runtime = prepare_runtime(args.directory, args.port, identity.config.issuer, "synthetic-analyst")
    try:
        app = PilotApplication(identity, runtime.factory, runtime.intake)
        server = make_https_server(app, runtime.certfile, runtime.keyfile)
        print(f"Synthetic-only pilot: {identity.origin}")
        print(f"Explicitly trust this local certificate in your browser: {runtime.certfile}")
        print("Only synthetic TXT evidence, at most four files of 64 KiB each. Ctrl-C stops the pilot.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
