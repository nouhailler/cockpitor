import asyncio
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..diagnostics import build_report
from ..errors import error


def create_router(app):
    router = APIRouter()

    @router.get("/api/v1/diagnostics/options")
    def diagnostic_options():
        return {
            "csrf_token": app.state.csrf,
            "schema_version": 1,
            "includes": ["aggregate_metrics", "module_status_counts", "safe_preferences"],
            "excludes": [
                "identity",
                "paths",
                "addresses",
                "names_ids",
                "logs",
                "environment",
                "tokens",
            ],
        }

    @router.post("/api/v1/diagnostics")
    async def diagnostics(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1024:
                return error(413, "BODY_LIMIT", "Requête de diagnostic limitée à 1 Kio")
        try:
            payload = json.loads(body)
            if (
                not isinstance(payload, dict)
                or set(payload) != {"confirmed"}
                or payload["confirmed"] is not True
            ):
                return error(422, "CONFIRMATION_REQUIRED", "Confirmation explicite requise")
        except (ValueError, UnicodeError):
            return error(422, "CONFIRMATION_REQUIRED", "Confirmation explicite requise")
        if app.state.diagnostic_lock.locked() or time.monotonic() - app.state.last_diagnostic < 5:
            return error(429, "DIAGNOSTIC_BUSY", "Attendez cinq secondes avant un nouvel export")
        async with app.state.diagnostic_lock:
            app.state.last_diagnostic = time.monotonic()
            report = await asyncio.to_thread(
                build_report,
                app.state.snapshot,
                app.state.ai,
                app.state.services,
                app.state.containers,
                app.state.store,
                app.state.storage_ready,
            )
            content = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode()
            if len(content) > 65536:
                return error(503, "DIAGNOSTIC_LIMIT", "Diagnostic trop volumineux")
            return Response(
                content,
                media_type="application/json",
                headers={
                    "Content-Disposition": 'attachment; filename="cockpitor-diagnostic.json"',
                    "X-Diagnostic-Audit": "recorded" if report["audit_recorded"] else "unavailable",
                },
            )

    return router
