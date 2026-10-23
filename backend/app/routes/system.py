from fastapi import APIRouter, Query

from ..errors import error
from ..modules import MODULES


def create_router(app):
    router = APIRouter()

    @router.get("/api/v1/health")
    def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "read_only": True,
            "settings_writable": True,
            "storage": {"status": "available" if app.state.storage_ready else "unavailable"},
        }

    @router.get("/api/v1/system/metrics")
    def metrics():
        data = app.state.snapshot
        if data is None:
            return error(503, "COLLECTING", "Première collecte en cours")
        return {key: value for key, value in data.items() if key != "processes"}

    @router.get("/api/v1/system/history")
    def history():
        return list(app.state.history)

    @router.get("/api/v1/system/processes")
    def processes(
        q: str = Query("", max_length=100),
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
    ):
        if app.state.snapshot is None:
            return error(503, "COLLECTING", "Première collecte en cours")
        rows = [
            p for p in app.state.snapshot["processes"] if q.lower() in (p["name"] or "").lower()
        ]
        rows.sort(key=lambda p: p["memory_percent"] or 0, reverse=True)
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "collected_at": app.state.snapshot["collected_at"],
        }

    @router.get("/api/v1/system/inspection")
    def inspection():
        return app.state.inspection or error(503, "COLLECTING", "Inspection en cours")

    @router.get("/api/v1/system/trends")
    def trends(hours: int = Query(24, ge=1, le=168)):
        if not app.state.storage_ready:
            return error(503, "STORAGE_UNAVAILABLE", "Stockage local indisponible")
        return {
            "items": app.state.store.metric_history(hours),
            "retention_days": 7,
            "resolution_seconds": 60,
        }

    @router.get("/api/v1/modules")
    def modules():
        return {"items": MODULES}

    return router
