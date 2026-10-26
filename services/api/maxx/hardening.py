"""Request-level defences that apply to every route, plus the production configuration guard.

Layers, outermost first:
1. Fetch Metadata: browsers label every request with Sec-Fetch-Site. A state-changing request that
   did not originate from our own site is refused before any route runs (CSRF defence in depth,
   on top of SameSite cookies and the Origin check).
2. Content-Type allow-list and body-size cap for state-changing requests.
3. A global per-address request budget.
4. Security headers on every response, and `no-store` on anything account related.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import re
import secrets
import uuid
from collections import defaultdict
from contextlib import contextmanager
from threading import Lock
from urllib.parse import urlsplit

from fastapi import HTTPException

from maxx.auth import ratelimit
from maxx.config import settings
from maxx.scan import MAX_UPLOAD

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
# The provider (Apple) posts this one from its own site; the relay does nothing but forward.
FORM_POST_CALLBACK = re.compile(r"^/auth/oauth/[a-z]+/callback$")
NO_STORE_PREFIXES = (
    "/auth",
    "/me",
    "/blocs",
    "/demo",
    "/money",
    "/checkout",
    "/crypto",
    "/seller",
    "/orders",
    "/addresses",
    "/cases",
    "/admin",
    "/sellers",
)
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


MIN_PROXY_SECRET = 32


def forwarded_client(forwarded: str) -> str:
    """The rightmost X-Forwarded-For entry: the one our nearest proxy appended. Clients can write
    any entries to the left of it, so trusting the leftmost lets them pick their own address."""
    return forwarded.split(",")[-1].strip()[:64]


def named_client(get) -> str | None:
    """The browser's address as our own web service names it, or None. Trusted only with the
    shared secret (compared in constant time) and only when it parses as an IP address: through a
    public URL the last X-Forwarded-For entry is the web service, not the visitor."""
    secret = settings.proxy_client_ip_secret
    if len(secret) < MIN_PROXY_SECRET:
        return None
    if not hmac.compare_digest(get("x-maxx-proxy-secret").encode(), secret.encode()):
        return None
    try:
        return str(ipaddress.ip_address(get("x-maxx-client-ip").strip()))
    except ValueError:
        return None


def client_ip(headers: dict[bytes, bytes], peer: tuple | None) -> str:
    named = named_client(lambda name: headers.get(name.encode(), b"").decode("latin-1"))
    if named:
        return named
    if settings.trust_proxy_headers:
        forwarded = forwarded_client(headers.get(b"x-forwarded-for", b"").decode("latin-1"))
        if forwarded:
            return forwarded
    return peer[0] if peer else "unknown"


def _is_https() -> bool:
    return settings.public_base_url.startswith("https://")


def allowed_content_types(path: str) -> tuple[str, ...]:
    if path == "/scan":
        return ("image/png", "image/jpeg", "image/webp", "application/octet-stream")
    if FORM_POST_CALLBACK.match(path):
        return ("application/x-www-form-urlencoded",)
    return ("application/json",)


def body_limit(path: str) -> int:
    if path == "/scan":
        return MAX_UPLOAD + 4096
    if path in {"/webhooks/tracking", "/webhooks/identity"}:
        return 256 * 1024  # provider events carry a whole tracker or session
    return settings.max_body_bytes


class RequestTooLarge(Exception):
    pass


class HardeningMiddleware:
    """Pure ASGI, so streaming (SSE) responses are never buffered."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path, method = scope["path"], scope["method"]
        headers = {k.lower(): v for k, v in scope["headers"]}
        request_id = uuid.uuid4().hex
        extra: dict[str, str] = {}

        async def reject(status: int, message: str):
            await self._respond(send, status, {"detail": message}, request_id, path, extra)

        if method in UNSAFE:
            site = headers.get(b"sec-fetch-site", b"").decode()
            if site in {"cross-site", "same-site"} and not FORM_POST_CALLBACK.match(path):
                return await reject(403, "This request came from another site and was blocked.")
            if (
                int(headers.get(b"content-length", b"0") or 0) > 0
                or b"transfer-encoding" in headers
            ):
                kind = headers.get(b"content-type", b"").decode().split(";")[0].strip().lower()
                if kind not in allowed_content_types(path):
                    return await reject(415, "Unsupported content type.")
                declared = headers.get(b"content-length")
                if declared and int(declared) > body_limit(path):
                    return await reject(413, "Request too large.")

        if path != "/health" and not path.startswith("/health/"):
            try:
                ratelimit.hit(
                    f"api:{client_ip(headers, scope.get('client'))}",
                    settings.api_rate_per_minute,
                    60,
                )
            except HTTPException as exc:
                extra.update(exc.headers or {})
                return await reject(429, "Too many requests. Slow down and retry shortly.")

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > body_limit(path):
                    raise RequestTooLarge
            return message

        started = False

        async def secured_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                raw = list(message.get("headers", []))
                present = {k.lower() for k, _ in raw}
                for name, value in self._headers(path, request_id).items():
                    if name.encode() not in present:
                        raw.append((name.encode(), value.encode()))
                message = {**message, "headers": raw}
            await send(message)

        try:
            await self.app(scope, limited_receive, secured_send)
        except RequestTooLarge:
            if not started:
                await reject(413, "Request too large.")

    # ------------------------------------------------------------------------------------------
    def _headers(self, path: str, request_id: str) -> dict[str, str]:
        values = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": API_CSP,
            "X-Request-ID": request_id,
        }
        if any(path == p or path.startswith(p + "/") for p in NO_STORE_PREFIXES):
            values["Cache-Control"] = "no-store"
            values["Pragma"] = "no-cache"
        if _is_https():
            values["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return values

    async def _respond(self, send, status, body, request_id, path, extra):
        payload = json.dumps(body).encode()
        headers = {"content-type": "application/json", "content-length": str(len(payload)), **extra}
        headers.update({k.lower(): v for k, v in self._headers(path, request_id).items()})
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
            }
        )
        await send({"type": "http.response.body", "body": payload})


def csp_nonce() -> str:
    return secrets.token_urlsafe(16)


# --- live-stream connection caps ---


class StreamLimiter:
    """Each SSE connection polls the database, so unbounded connections are a cheap DoS."""

    def __init__(self):
        self.by_ip: dict[str, int] = defaultdict(int)
        self.by_bloc: dict[str, int] = defaultdict(int)
        self.lock = Lock()

    @contextmanager
    def slot(self, ip: str, bloc: str):
        with self.lock:
            if (
                self.by_ip[ip] >= settings.stream_connections_per_ip
                or self.by_bloc[bloc] >= settings.stream_connections_per_bloc
            ):
                raise HTTPException(429, "Too many live connections. Close other tabs and retry.")
            self.by_ip[ip] += 1
            self.by_bloc[bloc] += 1
        try:
            yield
        finally:
            with self.lock:
                self.by_ip[ip] -= 1
                self.by_bloc[bloc] -= 1
                if self.by_ip[ip] <= 0:
                    self.by_ip.pop(ip, None)
                if self.by_bloc[bloc] <= 0:
                    self.by_bloc.pop(bloc, None)


streams = StreamLimiter()


# --- production configuration guard ---


def configuration_problems() -> list[str]:
    """Insecure settings that must never reach production. Empty outside production."""
    if settings.environment not in {"development", "production", "test"}:
        return ["ENVIRONMENT must be development, production or test."]
    problems = []
    if settings.paypal_mode not in {"off", "simulator", "sandbox"}:
        problems.append("PAYPAL_MODE must be off, simulator or sandbox.")
    if settings.paypal_mode == "sandbox" and urlsplit(settings.paypal_base_url).hostname not in {
        "api-m.sandbox.paypal.com",
        "api.sandbox.paypal.com",
    }:
        problems.append(
            "PAYPAL_BASE_URL must be PayPal's sandbox; live payments are not supported."
        )
    if settings.tracking_mode not in {"off", "simulator", "easypost"}:
        problems.append("TRACKING_MODE must be off, simulator or easypost.")
    if settings.tracking_mode == "easypost" and not settings.easypost_api_key:
        problems.append("TRACKING_MODE=easypost needs EASYPOST_API_KEY.")
    if settings.verify_mode not in {"off", "simulator", "stripe"}:
        problems.append("VERIFY_MODE must be off, simulator or stripe.")
    if settings.verify_mode == "stripe" and not (
        settings.stripe_secret_key and settings.stripe_webhook_secret
    ):
        problems.append("VERIFY_MODE=stripe needs STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET.")
    if settings.verify_mode == "off" and settings.seller_identity_required:
        problems.append("SELLER_IDENTITY_REQUIRED needs VERIFY_MODE simulator or stripe.")
    if 0 < len(settings.proxy_client_ip_secret) < MIN_PROXY_SECRET:
        problems.append(f"PROXY_CLIENT_IP_SECRET must be at least {MIN_PROXY_SECRET} characters.")
    if settings.environment != "production":
        return problems
    if settings.tracking_mode == "easypost" and not settings.easypost_webhook_secret:
        problems.append("EASYPOST_WEBHOOK_SECRET is required so tracking webhooks are signed.")
    if settings.demo_tools and settings.paypal_mode != "simulator":
        problems.append(
            "DEMO_TOOLS creates demo sellers and buyers; it needs PAYPAL_MODE=simulator."
        )
    if settings.seller_review != "manual":
        problems.append("SELLER_REVIEW must be manual in production; sellers need approval.")
    if settings.paypal_mode == "sandbox" and not settings.paypal_webhook_id:
        problems.append("PAYPAL_WEBHOOK_ID is required so webhook signatures can be verified.")
    if settings.paypal_mode == "simulator" and (
        settings.simulator_webhook_secret == "maxx-simulator-signing-secret"  # noqa: S105
    ):
        problems.append("SIMULATOR_WEBHOOK_SECRET must be changed from its published default.")
    if urlsplit(settings.public_base_url).scheme != "https":
        problems.append("PUBLIC_BASE_URL must be an https:// address (cookies and OAuth need it).")
    try:
        from maxx import secrets as vault

        vault._master_key()
    except Exception as exc:  # noqa: BLE001 - reported verbatim, never swallowed
        problems.append(str(exc))
    if "maxx_local" in settings.database_url:
        problems.append("DATABASE_URL still uses the disposable local password.")
    if settings.email_mode != "smtp" or not settings.smtp_host:
        problems.append(
            "EMAIL_MODE must be smtp with SMTP_HOST set; log mode prints sign-in links."
        )
    if settings.allowed_hosts.strip() in {"", "*"}:
        problems.append("ALLOWED_HOSTS must list the API's real host names, not *.")
    if settings.docs_enabled:
        problems.append("DOCS_ENABLED must be off; it publishes the full API surface.")
    return problems


def enforce_configuration() -> None:
    problems = configuration_problems()
    if problems:
        raise RuntimeError(
            "Refusing to start with insecure configuration:\n - " + "\n - ".join(problems)
        )


# --- keep credentials out of logs ---


class SecretFilter(logging.Filter):
    """Replace configured credentials, bearer tokens and card-like strings in every log line."""

    BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}")

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        for secret in (
            settings.paypal_client_secret,
            settings.nebius_api_key,
            settings.tavily_api_key,
            settings.secret_key,
            settings.turnstile_secret,
            settings.simulator_webhook_secret,
            settings.easypost_api_key,
            settings.easypost_webhook_secret,
            settings.stripe_secret_key,
            settings.stripe_webhook_secret,
            settings.proxy_client_ip_secret,
        ):
            if secret and len(secret) >= 8 and secret in text:
                text = text.replace(secret, "[redacted]")
        text = self.BEARER.sub(r"\1[redacted]", text)
        record.msg, record.args = text, ()
        return True


def install_log_redaction() -> None:
    root = logging.getLogger()
    if not any(isinstance(f, SecretFilter) for f in root.filters):
        root.addFilter(SecretFilter())
        for handler in root.handlers:
            handler.addFilter(SecretFilter())
