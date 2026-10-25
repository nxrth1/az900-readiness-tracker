"""One small ASGI middleware: request ids, access log, security headers, request-size limit.

Written as plain ASGI (not ``BaseHTTPMiddleware``) so it never buffers responses and keeps the
request-id contextvar intact for threadpool endpoints.
"""
from __future__ import annotations

import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import get_settings
from .errors import internal_error_body
from .logging_config import get_logger, request_id_var

log = get_logger("access")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{6,64}$")
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")  # Swagger UI needs CDN scripts, so no CSP there

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        headers = Headers(scope=scope)
        incoming = headers.get("x-request-id", "")
        rid = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        path = scope["path"]
        started = time.perf_counter()
        state = {"status": 500, "started": False, "responded": False}
        https = scope.get("scheme") == "https" or (
            settings.trusted_proxy_hops > 0 and headers.get("x-forwarded-proto", "") == "https"
        )

        async def emit(message: Message) -> None:
            """Decorate and forward a response message."""
            if message["type"] == "http.response.start":
                state["started"] = True
                state["status"] = message["status"]
                out = MutableHeaders(scope=message)
                out["X-Request-ID"] = rid
                for name, value in SECURITY_HEADERS.items():
                    out.setdefault(name, value)
                if not path.startswith(_DOC_PATHS):
                    out.setdefault("Content-Security-Policy", CSP)
                if path.startswith("/api"):
                    out["Cache-Control"] = "no-store"
                if https:
                    out.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            await send(message)

        async def send_wrapper(message: Message) -> None:
            if not state["responded"]:  # after we answered ourselves, drop whatever the app tries to send
                await emit(message)

        async def respond(status: int, body: bytes) -> None:
            await emit({"type": "http.response.start", "status": status, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await emit({"type": "http.response.body", "body": body})
            state["responded"] = True

        limit_bytes = settings.max_body_bytes
        too_large = b'{"detail":"Request body too large."}'
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request" and not state["responded"]:
                received += len(message.get("body", b""))
                if received > limit_bytes:  # chunked upload that lied about (or omitted) its length
                    await respond(413, too_large)
                    return {"type": "http.disconnect"}
            return message

        declared = headers.get("content-length", "")
        try:
            if declared.isdigit() and int(declared) > limit_bytes:
                await respond(413, too_large)
            else:
                await self.app(scope, limited_receive, send_wrapper)
        except Exception as exc:  # last resort: never leak internals, always return a correlatable error
            log.error("unhandled %s", type(exc).__name__, exc_info=exc)
            if state["started"]:
                raise  # too late to change the response; let the server close the connection
            await respond(500, internal_error_body(rid))
        finally:
            # Path only: query strings carry the learner id, which acts as a bearer secret.
            log.info(
                "%s %s -> %s", scope["method"], path, state["status"],
                extra={
                    "method": scope["method"], "path": path, "status": state["status"],
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)
