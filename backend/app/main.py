import asyncio
import hmac
import logging
import os
import secrets
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .containers import ContainerError, Containers
from .integrations import ai_status, container_status
from .services import ServiceError, Services
from .system import Collector

TOKEN = os.environ.get("LOCALCOCKPIT_TOKEN") or secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(app: FastAPI):
    collector = Collector()
    app.state.snapshot = None
    app.state.history = deque(maxlen=450)

    async def sample():
        while True:
            try:
                data = await asyncio.to_thread(collector.collect)
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

    service_task = asyncio.create_task(service_inventory())
    task = asyncio.create_task(sample())
    integration_task = asyncio.create_task(integrations())
    try:
        yield
    finally:
        service_task.cancel()
        integration_task.cancel()
        task.cancel()
        try:
            await asyncio.gather(task, integration_task, service_task)
        except asyncio.CancelledError:
            pass


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
        {"error": {"code": code, "message": message, "correlation_id": secrets.token_hex(8)}},
        status_code=status,
    )


@app.middleware("http")
async def security(request: Request, call_next):
    try:
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
    except ValueError:
        host = None
    origin = request.headers.get("origin")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        response = error(400, "HOST_REJECTED", "Hôte non autorisé")
    elif origin and origin != str(request.base_url).rstrip("/"):
        response = error(403, "ORIGIN_REJECTED", "Origine non autorisée")
    elif request.method not in {"GET", "HEAD"}:
        response = error(405, "READ_ONLY", "Cette version est en lecture seule")
    elif request.url.path.startswith("/api/") and not hmac.compare_digest(
        request.headers.get("authorization", "").encode(), ("Bearer " + TOKEN).encode()
    ):
        response = error(401, "AUTH_REQUIRED", "Jeton local requis")
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


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    return error(500, "INTERNAL_ERROR", "Erreur interne ; réessayez ultérieurement")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "0.1.0", "read_only": True}


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


DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
