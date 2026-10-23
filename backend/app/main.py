import asyncio
import hmac
import json
import logging
import os
import secrets
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .alerts import AlertEngine
from .containers import ContainerError, Containers
from .diagnostics import build_report
from .i18n import language, select_language, translate
from .integrations import ai_status, container_status
from .preferences import Preferences
from .services import ServiceError, Services
from .storage import StorageError, Store
from .system import Collector

TOKEN = os.environ.get("LOCALCOCKPIT_TOKEN") or secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store(
        Path(
            os.environ.get(
                "LOCALCOCKPIT_DATA_DIR", str(Path(__file__).resolve().parents[2] / ".localcockpit")
            )
        )
    )
    app.state.store = store
    app.state.preferences = Preferences()
    app.state.storage_ready = False
    app.state.storage_error = "Initialisation du stockage en cours"
    app.state.csrf = secrets.token_urlsafe(32)
    app.state.diagnostic_lock = asyncio.Lock()
    app.state.last_diagnostic = -10.0
    app.state.preferences_lock = asyncio.Lock()
    app.state.alert_engine = AlertEngine(store)
    collector = Collector()
    collector_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cockpitor-collector")
    app.state.snapshot = None
    app.state.history = deque(maxlen=450)

    async def sample():
        while True:
            try:
                data = await asyncio.get_running_loop().run_in_executor(
                    collector_executor, collector.collect
                )
                app.state.snapshot = data
                app.state.history.append(
                    {
                        "collected_at": data["collected_at"],
                        "cpu_percent": data["cpu_percent"],
                        "memory_percent": data["memory"]["percent"],
                    }
                )
            except Exception:  # noqa: BLE001 — isolate collector failures
                # Preserve timestamp of last successful sample; do not invent current values.
                logging.getLogger("localcockpit").warning("Collecte système indisponible")
            await asyncio.sleep(2)

    app.state.container_adapter = Containers()
    app.state.services_adapter = Services()
    app.state.services = None
    app.state.ai = None
    app.state.containers = None

    async def integrations():
        while True:
            app.state.ai, app.state.containers = await asyncio.gather(
                ai_status(), container_status()
            )
            await asyncio.sleep(10)

    async def service_inventory():
        while True:
            app.state.services = await app.state.services_adapter.inventory()
            await asyncio.sleep(10)

    async def evaluate_alerts():
        while True:
            async with app.state.preferences_lock:
                try:
                    if not app.state.storage_ready:
                        app.state.preferences = await asyncio.to_thread(store.initialize)
                        app.state.alert_engine = AlertEngine(store)
                    await asyncio.to_thread(
                        app.state.alert_engine.evaluate,
                        app.state.preferences,
                        app.state.snapshot,
                        app.state.ai,
                        app.state.services,
                        app.state.containers,
                    )
                    app.state.storage_ready = True
                    app.state.storage_error = ""
                except StorageError as exc:
                    app.state.storage_ready = False
                    app.state.storage_error = str(exc)
            await asyncio.sleep(2)

    alert_task = asyncio.create_task(evaluate_alerts())
    service_task = asyncio.create_task(service_inventory())
    task = asyncio.create_task(sample())
    integration_task = asyncio.create_task(integrations())
    try:
        yield
    finally:
        alert_task.cancel()
        service_task.cancel()
        integration_task.cancel()
        task.cancel()
        try:
            await asyncio.gather(task, integration_task, service_task, alert_task)
        except asyncio.CancelledError:
            pass
        finally:
            collector_executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(
    title="LocalCockpit",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": translate(message),
                "correlation_id": secrets.token_hex(8),
            }
        },
        status_code=status,
    )


@app.middleware("http")
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
        or (request.method == "POST" and request.url.path == "/api/v1/diagnostics")
    ):
        response = error(405, "READ_ONLY", "Cette version est en lecture seule")
    elif request.url.path.startswith("/api/") and not hmac.compare_digest(
        request.headers.get("authorization", "").encode(), ("Bearer " + TOKEN).encode()
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


@app.exception_handler(ContainerError)
@app.exception_handler(ServiceError)
async def service_error(request: Request, exc: ServiceError):
    return error(exc.status, exc.code, exc.message)


@app.exception_handler(StorageError)
async def storage_error(request: Request, exc: StorageError):
    return error(503, "STORAGE_UNAVAILABLE", str(exc))


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    return error(500, "INTERNAL_ERROR", "Erreur interne ; réessayez ultérieurement")


@app.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "read_only": True,
        "settings_writable": True,
        "storage": {"status": "available" if app.state.storage_ready else "unavailable"},
    }


@app.get("/api/v1/system/metrics")
def metrics():
    data = app.state.snapshot
    if data is None:
        return error(503, "COLLECTING", "Première collecte en cours")
    return {key: value for key, value in data.items() if key != "processes"}


@app.get("/api/v1/system/history")
def history():
    return list(app.state.history)


@app.get("/api/v1/system/processes")
def processes(
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    if app.state.snapshot is None:
        return error(503, "COLLECTING", "Première collecte en cours")
    rows = [p for p in app.state.snapshot["processes"] if q.lower() in (p["name"] or "").lower()]
    rows.sort(key=lambda p: p["memory_percent"] or 0, reverse=True)
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "collected_at": app.state.snapshot["collected_at"],
    }


@app.get("/api/v1/ai/status")
def ai():
    return app.state.ai or error(503, "CHECKING", "Vérification IA en cours")


@app.get("/api/v1/containers")
def containers():
    return app.state.containers or error(503, "CHECKING", "Vérification des moteurs en cours")


@app.get("/api/v1/services")
def services(
    q: str = Query("", max_length=100),
    state: Literal["all", "active", "inactive", "failed"] = "all",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    data = app.state.services
    if data is None:
        return error(503, "COLLECTING", "Inventaire des services en cours")
    if data["status"] != "available":
        return error(503, data["code"], data["message"])
    rows = [
        row
        for row in data["items"]
        if (state == "all" or row["active"] == state)
        and q.lower() in (row["unit"] + " " + row["description"]).lower()
    ]
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "collected_at": data["collected_at"],
        "scope": "loaded_system_services",
    }


@app.get("/api/v1/services/{unit}")
async def service_detail(unit: str):
    return await app.state.services_adapter.detail(unit)


@app.get("/api/v1/services/{unit}/logs")
async def service_logs(
    unit: str,
    limit: int = Query(50, ge=1, le=200),
    period: Literal["hour", "day"] = "hour",
    priority: int = Query(7, ge=0, le=7),
    q: str = Query("", max_length=100),
    cursor: str | None = Query(None, max_length=1024),
):
    return await app.state.services_adapter.logs(
        unit, limit, 3600 if period == "hour" else 86400, priority, q, cursor
    )


@app.get("/api/v1/containers/{engine}/{container_id}")
async def container_detail(engine: Literal["docker", "podman"], container_id: str):
    return await app.state.container_adapter.detail(engine, container_id)


@app.get("/api/v1/containers/{engine}/{container_id}/stats")
async def container_stats(engine: Literal["docker", "podman"], container_id: str):
    return await app.state.container_adapter.stats(engine, container_id)


@app.get("/api/v1/containers/{engine}/{container_id}/logs")
async def container_logs(
    engine: Literal["docker", "podman"],
    container_id: str,
    tail: int = Query(100, ge=1, le=200),
    period: Literal["hour", "day"] = "hour",
):
    return await app.state.container_adapter.logs(
        engine, container_id, tail, 3600 if period == "hour" else 86400
    )


@app.get("/api/v1/settings")
async def settings():
    if not app.state.storage_ready:
        raise StorageError(app.state.storage_error)
    preferences = await asyncio.to_thread(app.state.store.preferences)
    return {
        "settings": preferences.model_dump(),
        "csrf_token": app.state.csrf,
        "storage": {"status": "available", "schema_version": 1},
    }


@app.put("/api/v1/settings")
async def save_settings(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            return error(413, "BODY_LIMIT", "Configuration limitée à 16 Kio")
    try:
        preferences = Preferences.model_validate_json(bytes(body))
    except ValidationError:
        return error(422, "INVALID_SETTINGS", "Paramètres invalides ou champs non autorisés")
    async with app.state.preferences_lock:
        if not app.state.storage_ready:
            raise StorageError(app.state.storage_error)
        operation = await asyncio.to_thread(app.state.store.save, preferences)
        app.state.preferences = preferences
    return {"operation_id": operation, "status": "completed", "settings": preferences.model_dump()}


@app.get("/api/v1/alerts")
async def alerts(
    status: Literal["all", "active", "resolved"] = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if not app.state.storage_ready:
        raise StorageError(app.state.storage_error)
    events = await asyncio.to_thread(app.state.store.events, status, limit, offset)
    return {
        **events,
        "rules": app.state.alert_engine.states,
        "evaluated_at": getattr(app.state.alert_engine, "evaluated_at", None),
    }


@app.get("/api/v1/diagnostics/options")
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


@app.post("/api/v1/diagnostics")
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


DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
