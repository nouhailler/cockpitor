import asyncio
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import ValidationError

from ..errors import error
from ..preferences import Preferences
from ..storage import StorageError


def create_router(app):
    router = APIRouter()

    @router.get("/api/v1/settings")
    async def settings():
        if not app.state.storage_ready:
            raise StorageError(app.state.storage_error)
        preferences = await asyncio.to_thread(app.state.store.preferences)
        return {
            "settings": preferences.model_dump(),
            "csrf_token": app.state.csrf,
            "storage": {"status": "available", "schema_version": 2},
        }

    @router.put("/api/v1/settings")
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
        return {
            "operation_id": operation,
            "status": "completed",
            "settings": preferences.model_dump(),
        }

    @router.get("/api/v1/alerts")
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

    @router.get("/api/v1/audit")
    async def audit(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        if not app.state.storage_ready:
            raise StorageError(app.state.storage_error)
        return await asyncio.to_thread(app.state.store.audit_events, limit, offset)

    return router
