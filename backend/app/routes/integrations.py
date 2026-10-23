from typing import Literal

from fastapi import APIRouter, Query

from ..errors import error


def create_router(app):
    router = APIRouter()

    @router.get("/api/v1/ai/status")
    def ai():
        return app.state.ai or error(503, "CHECKING", "Vérification IA en cours")

    @router.get("/api/v1/containers")
    def containers():
        return app.state.containers or error(503, "CHECKING", "Vérification des moteurs en cours")

    @router.get("/api/v1/services")
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

    @router.get("/api/v1/services/{unit}")
    async def service_detail(unit: str):
        return await app.state.services_adapter.detail(unit)

    @router.get("/api/v1/services/{unit}/logs")
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

    @router.get("/api/v1/containers/{engine}/{container_id}")
    async def container_detail(engine: Literal["docker", "podman"], container_id: str):
        return await app.state.container_adapter.detail(engine, container_id)

    @router.get("/api/v1/containers/{engine}/{container_id}/stats")
    async def container_stats(engine: Literal["docker", "podman"], container_id: str):
        return await app.state.container_adapter.stats(engine, container_id)

    @router.get("/api/v1/containers/{engine}/{container_id}/logs")
    async def container_logs(
        engine: Literal["docker", "podman"],
        container_id: str,
        tail: int = Query(100, ge=1, le=200),
        period: Literal["hour", "day"] = "hour",
    ):
        return await app.state.container_adapter.logs(
            engine, container_id, tail, 3600 if period == "hour" else 86400
        )

    return router
