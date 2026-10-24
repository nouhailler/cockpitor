import hmac
from urllib.parse import urlsplit

from fastapi import Request

from .errors import error
from .i18n import language, select_language


async def security(request: Request, call_next):
    selected = select_language(request.headers.get("accept-language", "fr"))
    reset_token = language.set(selected)
    try:
        response = await secure_response(request, call_next)
        response.headers["Content-Language"] = selected
        response.headers["Vary"] = "Accept-Language"
        return response
    finally:
        language.reset(reset_token)


async def secure_response(request: Request, call_next):
    try:
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
    except ValueError:
        host = None
    origin = request.headers.get("origin")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        response = error(400, "HOST_REJECTED", "Hôte non autorisé")
    elif origin and origin != str(request.base_url).rstrip("/"):
        response = error(403, "ORIGIN_REJECTED", "Origine non autorisée")
    elif request.method not in {"GET", "HEAD"} and not (
        (request.method == "PUT" and request.url.path == "/api/v1/settings")
        or (
            request.method == "POST"
            and request.url.path
            in {
                "/api/v1/action-plans/prepare",
                "/api/v1/action-plans/approve",
                "/api/v1/action-plans/simulate",
                "/api/v1/action-plans/cancel",
                "/api/v1/diagnostics",
                "/api/v1/auth/sessions",
                "/api/v1/auth/logout",
                "/api/v1/auth/activity",
                "/api/v1/ai/context",
                "/api/v1/ai/chat",
                "/api/v1/ai/cancel",
            }
        )
    ):
        response = error(405, "READ_ONLY", "Cette version est en lecture seule")
    elif (
        request.url.path.startswith("/api/")
        and request.url.path not in {"/api/v1/auth/options", "/api/v1/auth/sessions"}
        and not (
            request.headers.get("authorization", "").startswith("Bearer ")
            and request.app.state.sessions.authorize(request.headers["authorization"][7:])
        )
    ):
        response = error(401, "AUTH_REQUIRED", "Jeton local requis")
    elif request.method in {"PUT", "POST"} and (
        origin != str(request.base_url).rstrip("/")
        or not hmac.compare_digest(
            request.headers.get("x-localcockpit-csrf", "").encode(), request.app.state.csrf.encode()
        )
    ):
        response = error(403, "CSRF_REJECTED", "Origine locale et protection CSRF requises")
    elif (
        request.method in {"PUT", "POST"}
        and request.headers.get("content-type", "").split(";")[0].strip().lower()
        != "application/json"
    ):
        response = error(415, "JSON_REQUIRED", "Contenu JSON requis")
    else:
        response = await call_next(request)
    response.headers.update(
        {
            "Content-Security-Policy": "default-src 'self'; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        }
    )
    return response
