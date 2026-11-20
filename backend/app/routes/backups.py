import asyncio
import json
import secrets

from fastapi import APIRouter, Query, Request

from ..auth import Sessions
from ..backups import export
from ..errors import error
from ..services import ServiceError
from ..storage import StorageError


def create_router(app):
    router = APIRouter()

    def check_storage():
        if not app.state.storage_ready:
            raise StorageError(app.state.storage_error)

    async def body(request):
        value = bytearray()
        async for chunk in request.stream():
            value.extend(chunk)
            if len(value) > 65536:
                raise ServiceError("BODY_LIMIT", "Sauvegarde limitée à 64 Kio par requête", 413)
        try:

            def unique(pairs):
                result = {}
                for key, item in pairs:
                    if key in result:
                        raise ValueError()
                    result[key] = item
                return result

            payload = json.loads(value, object_pairs_hook=unique)
            if not isinstance(payload, dict):
                raise TypeError()
            return payload
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise ServiceError(
                "BACKUP_INVALID", "Sauvegarde invalide ou incompatible", 422
            ) from exc

    @router.post("/api/v1/backups/export")
    async def download(request: Request):
        payload = await body(request)
        if payload != {"confirmed": True} or payload.get("confirmed") is not True:
            return error(422, "CONFIRMATION_REQUIRED", "Confirmation explicite requise")
        async with app.state.preferences_lock:
            check_storage()
            preferences = await asyncio.to_thread(app.state.store.preferences)
            await asyncio.to_thread(app.state.store.audit, secrets.token_hex(16), "backups.export")
            return export(preferences)

    @router.get("/api/v1/backups")
    async def listing():
        check_storage()
        return await asyncio.to_thread(app.state.backups.snapshots)

    @router.get("/api/v1/backups/snapshot")
    async def snapshot(id: str = Query(pattern=r"^[a-f0-9]{32}$")):
        check_storage()
        return await asyncio.to_thread(app.state.backups.read_snapshot, id)

    @router.post("/api/v1/backups/prepare")
    async def prepare(request: Request):
        payload = await body(request)
        if set(payload) != {"backup"}:
            return error(422, "BACKUP_INVALID", "Sauvegarde invalide ou incompatible")
        async with app.state.preferences_lock:
            check_storage()
            previous = await asyncio.to_thread(app.state.store.preferences)
            return app.state.backups.prepare(
                Sessions.digest(request.headers["authorization"][7:]), payload["backup"], previous
            )

    @router.post("/api/v1/backups/restore")
    async def restore(request: Request):
        payload = await body(request)
        if (
            set(payload) != {"plan_id", "confirmed"}
            or payload["confirmed"] is not True
            or not isinstance(payload["plan_id"], str)
            or len(payload["plan_id"]) != 64
        ):
            return error(422, "CONFIRMATION_REQUIRED", "Confirmation explicite requise")
        async with app.state.preferences_lock:

            async def apply():
                check_storage()
                if not app.state.sessions.authorize(request.headers["authorization"][7:]):
                    return error(401, "AUTH_REQUIRED", "Jeton local requis")
                previous = await asyncio.to_thread(app.state.store.preferences)
                target = app.state.backups.consume(
                    Sessions.digest(request.headers["authorization"][7:]),
                    payload["plan_id"],
                    previous,
                )
                backup_id = await asyncio.to_thread(app.state.backups.snapshot, previous)
                if not app.state.sessions.authorize(request.headers["authorization"][7:]):
                    return error(401, "AUTH_REQUIRED", "Jeton local requis")
                operation = await asyncio.to_thread(
                    app.state.store.save, target, expected=previous, restoring=True
                )
                app.state.preferences = target
                return {
                    "operation_id": operation,
                    "status": "completed",
                    "recovery_backup_id": backup_id,
                    "settings": target.model_dump(),
                    "system_changed": False,
                }

            task = asyncio.create_task(apply())
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Complete an entered local transaction before releasing the settings lock.
                await task
                raise

    return router
