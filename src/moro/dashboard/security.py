"""Authentication and request boundaries shared by local web services.

One installation token grants access to this single-project administrative UI.
This is not a multi-tenant authorization system; do not expose it as one.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

from fastapi import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from moro.dashboard.utils import get_project_root

MAX_BODY_BYTES = 16 * 1024 * 1024
SESSION_SECONDS = 8 * 3600
COOKIE = "moro_session"
CSP_NONCE_SCOPE_KEY = "moro_csp_nonce"


def content_security_policy(nonce: str) -> bytes:
    """Build the Content-Security-Policy value for one response.

    Minimal narrowing, documented: ``script-src`` carries a per-request
    ``'nonce-…'`` covering our first-party inline scripts, and ``'unsafe-inline'``
    is intentionally absent so injected ``<script>`` blocks and event handlers
    cannot run. ``'unsafe-eval'`` remains because the vendored Alpine.js 3.14.9
    expression evaluator compiles ``x-data``/``x-on`` expressions through the
    AsyncFunction constructor; removing it renders the dashboard inert.
    ``style-src`` keeps ``'unsafe-inline'`` for Tailwind/Alpine/Dropzone
    runtime-applied styles; styles cannot execute script and all markup is
    first-party. No remote hosts are allowlisted anywhere.
    """
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ).encode()


def csp_nonce(scope_or_request) -> str:
    """Return the per-request CSP nonce set by LocalAccessMiddleware."""
    scope = getattr(scope_or_request, "scope", scope_or_request)
    if not isinstance(scope, dict):
        return ""
    value = scope.get(CSP_NONCE_SCOPE_KEY, "")
    return value if isinstance(value, str) else ""


def access_token() -> str:
    configured = os.environ.get("MORO_API_TOKEN")
    if configured:
        if len(configured) < 32:
            raise RuntimeError("MORO_API_TOKEN must contain at least 32 characters.")
        return configured
    directory = get_project_root() / ".moro"
    if directory.is_symlink():
        raise RuntimeError("Authentication directory must not be a symbolic link.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "web.token"
    # Publish a fully written secret atomically so concurrent service starts never
    # observe an empty token file. A competing publisher keeps its winning token.
    if not path.exists():
        temporary = directory / (".token-" + secrets.token_hex(16))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(secrets.token_urlsafe(32))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                pass
        finally:
            temporary.unlink()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise RuntimeError("Authentication token must be a private regular file (mode 0600).")
        token = stream.read(256).strip()
    if len(token) < 32:
        raise RuntimeError("Authentication token is incomplete or invalid.")
    return token


def session_value(token: str, timestamp: int | None = None) -> str:
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    digest = hmac.new(token.encode(), ("session:" + stamp).encode(), hashlib.sha256).hexdigest()
    return stamp + "." + digest


def valid_session(value: str, token: str) -> bool:
    try:
        stamp = int(value.split(".", 1)[0])
        age = int(time.time()) - stamp
        return 0 <= age < SESSION_SECONDS and hmac.compare_digest(
            value, session_value(token, stamp)
        )
    except (ValueError, TypeError):
        return False


LOGIN = """<!doctype html><html lang="en"><meta charset="utf-8"><title>MoroAI sign in</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<body><main><h1>MoroAI sign in</h1><p>Enter the installation token from
<code>.moro/web.token</code> in the active project, or your configured MORO_API_TOKEN.</p>
<form id="login-form" action="/login" method="post"><label>Access token <input name="token" type="password"
autocomplete="off" required maxlength="256"></label><button type="submit">Sign in</button></form><p id="login-error" role="alert"></p>
<script>
document.getElementById('login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button');
  const error = document.getElementById('login-error');
  button.disabled = true;
  error.textContent = '';
  try {
    const response = await fetch('/login', {method: 'POST',
      body: new URLSearchParams(new FormData(form)), credentials: 'same-origin'});
    if (response.ok) { window.location.assign('/'); return; }
    error.textContent = 'Sign-in failed. Check the installation token and try again.';
  } catch (_) { error.textContent = 'Cannot reach MoroAI. Check that the service is running.'; }
  button.disabled = false;
});
</script></main></body></html>"""


def install_security(app, *, browser_login: bool = False) -> None:
    app.add_middleware(LocalAccessMiddleware, browser_login=browser_login)
    if browser_login:

        @app.get("/login", include_in_schema=False)
        async def login_page(request: Request):
            return HTMLResponse(login_html(csp_nonce(request)))

        @app.post("/login", include_in_schema=False)
        async def login(request: Request):
            body = await request.body()
            if len(body) > 1024:
                return JSONResponse({"detail": "Invalid credentials"}, status_code=401)
            supplied = parse_qs(body.decode("utf-8", errors="replace")).get("token", [""])[0]
            token = access_token()
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                return JSONResponse({"detail": "Invalid credentials"}, status_code=401)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(
                COOKIE,
                session_value(token),
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
                max_age=SESSION_SECONDS,
            )
            return response

        @app.post("/logout", include_in_schema=False)
        async def logout():
            response = RedirectResponse("/login", status_code=303)
            response.delete_cookie(COOKIE)
            return response


def login_html(nonce: str) -> str:
    """Render the sign-in page, tagging its inline script with the CSP nonce."""
    if not nonce:
        return LOGIN
    return LOGIN.replace("<script>", f'<script nonce="{nonce}">', 1)


class LocalAccessMiddleware:
    def __init__(self, app, browser_login: bool = False):
        self.app = app
        self.browser_login = browser_login

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        nonce = secrets.token_urlsafe(16)
        scope[CSP_NONCE_SCOPE_KEY] = nonce
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        host = headers.get("host", "")
        try:
            hostname = urlsplit("http://" + host).hostname
        except ValueError:
            hostname = None
        allowed = os.environ.get("MORO_ALLOWED_HOSTS", "127.0.0.1,localhost,::1").split(",")
        origin = headers.get("origin")
        # Same origin only, including the actual port. Cross-origin cookies/WS are forbidden.
        expected_origin = (
            ("https" if scope.get("scheme") in ("https", "wss") else "http") + "://" + host
        )
        status = (
            403
            if hostname not in allowed or (origin is not None and origin != expected_origin)
            else None
        )
        method = scope.get("method", "GET")
        if method in ("POST", "PUT", "PATCH"):
            try:
                length = int(headers.get("content-length", "-1"))
            except ValueError:
                length = -1
            if length < 0:
                status = status or 411
            elif length > MAX_BODY_BYTES:
                status = status or 413
        token = access_token()
        authorization = headers.get("authorization", "")
        bearer = authorization.startswith("Bearer ") and hmac.compare_digest(
            authorization[7:].encode(), token.encode()
        )
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get("cookie", ""))
            cookie = cookies.get(COOKIE)
            session = bool(cookie and valid_session(cookie.value, token))
        except Exception:
            session = False
        public_login = (
            self.browser_login and scope["path"] == "/login" and method in ("GET", "POST")
        )
        if not bearer and not public_login:
            if not session:
                status = status or 401
            elif method not in ("GET", "HEAD", "OPTIONS") and origin != expected_origin:
                status = status or 403
        if status:
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            if status == 401 and self.browser_login and scope["path"] in ("/", "/dashboard"):
                return await RedirectResponse("/login")(scope, receive, send)
            return await JSONResponse(
                {
                    "detail": {
                        401: "Authentication required",
                        403: "Access denied",
                        411: "Content-Length required",
                        413: "Request too large",
                    }[status]
                },
                status_code=status,
            )(scope, receive, send)
        # Enforce actual size, not just the declared Content-Length.
        received = 0

        class BodyTooLarge(Exception):
            pass

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > MAX_BODY_BYTES:
                raise BodyTooLarge()
            return message

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                        (b"x-frame-options", b"DENY"),
                        (b"content-security-policy", content_security_policy(nonce)),
                    ]
                )
            await send(message)

        try:
            await self.app(scope, bounded_receive, secured_send)
        except BodyTooLarge:
            await JSONResponse({"detail": "Request too large"}, status_code=413)(
                scope, receive, send
            )
