import asyncio
import logging
import os
import secrets
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from .alerts import AlertEngine
from .assistant import Assistant
from .auth import Sessions
from .containers import ContainerError, Containers
from .errors import error
from .integrations import ai_status, container_status
from .monitoring import inspect
from .preferences import Preferences
from .routes import register_routes
from .security import security
from .services import ServiceError, Services
from .storage import StorageError, Store
from .system import Collector

TOKEN = os.environ.get("LOCALCOCKPIT_TOKEN") or secrets.token_urlsafe(32)


async def refresh_integrations(app):
    results = await asyncio.gather(ai_status(), container_status(), return_exceptions=True)
    for name, result in zip(("ai", "containers"), results, strict=True):
        if isinstance(result, BaseException):
            logging.getLogger("localcockpit").warning("Intégration indisponible : %s", name)
        else:
            setattr(app.state, name, result)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store(
        Path(
            os.environ.get(
                "LOCALCOCKPIT_DATA_DIR", str(Path(__file__).resolve().parents[2] / ".localcockpit")
            )
        )
    )
    app.state.sessions = Sessions(TOKEN)
    app.state.assistant = Assistant()
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
    app.state.inspection = None
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
            await refresh_integrations(app)
            await asyncio.sleep(10)

    async def service_inventory():
        while True:
            try:
                app.state.services = await app.state.services_adapter.inventory()
            except Exception:  # noqa: BLE001 — preserve other collectors on module failure
                logging.getLogger("localcockpit").warning("Inventaire des services indisponible")
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
                    if app.state.snapshot is not None:
                        await asyncio.to_thread(store.record_metrics, app.state.snapshot)
                    app.state.storage_ready = True
                    app.state.storage_error = ""
                except StorageError as exc:
                    app.state.storage_ready = False
                    app.state.storage_error = str(exc)
            await asyncio.sleep(2)

    async def inspect_system():
        while True:
            try:
                app.state.inspection = await inspect()
            except Exception:  # noqa: BLE001 — isolate optional inspection failures
                logging.getLogger("localcockpit").warning("Inspection complémentaire indisponible")
            await asyncio.sleep(60)

    inspection_task = asyncio.create_task(inspect_system())
    alert_task = asyncio.create_task(evaluate_alerts())
    service_task = asyncio.create_task(service_inventory())
    task = asyncio.create_task(sample())
    integration_task = asyncio.create_task(integrations())
    try:
        yield
    finally:
        inspection_task.cancel()
        alert_task.cancel()
        service_task.cancel()
        integration_task.cancel()
        task.cancel()
        try:
            await asyncio.gather(task, integration_task, service_task, alert_task, inspection_task)
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


app.middleware("http")(security)


@app.exception_handler(ContainerError)
@app.exception_handler(ServiceError)
async def service_error(request: Request, exc: ServiceError):
    return error(exc.status, exc.code, exc.message)


@app.exception_handler(StorageError)
async def storage_error(request: Request, exc: StorageError):
    return error(503, "STORAGE_UNAVAILABLE", str(exc))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return error(422, "INVALID_REQUEST", "Paramètres invalides ou champs non autorisés")


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    return error(500, "INTERNAL_ERROR", "Erreur interne ; réessayez ultérieurement")


register_routes(app)


DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
