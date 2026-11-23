import asyncio

from fastapi import APIRouter, Request
from pydantic import ValidationError

from ..auth import Sessions
from ..errors import error
from ..remote import RemoteRequest
from ..storage import StorageError


def create_router(app):
    router = APIRouter()

    @router.get("/api/v1/remote/hosts")
    def inventory():
        return app.state.remote.inventory()

    async def run(request, kind):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2048:
                return error(413, "BODY_LIMIT", "Demande distante limitée à 2 Kio")
        try:
            payload = RemoteRequest.model_validate_json(bytes(body))
        except ValidationError:
            return error(422, "INVALID_REMOTE_REQUEST", "Demande distante invalide")
        if not app.state.storage_ready:
            raise StorageError(app.state.storage_error)
        owner = Sessions.digest(request.headers["authorization"][7:])
        task = asyncio.create_task(app.state.remote.run(owner, payload, kind))
        try:
            while not task.done():
                await asyncio.sleep(0.05)
                if await request.is_disconnected():
                    task.cancel()
                    break
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    @router.post("/api/v1/remote/check")
    async def check(request: Request):
        return await run(request, "check")

    @router.post("/api/v1/remote/list")
    async def listing(request: Request):
        return await run(request, "list")

    @router.post("/api/v1/remote/cancel")
    async def cancel(request: Request):
        app.state.remote.cancel(Sessions.digest(request.headers["authorization"][7:]))
        return {"status": "completed"}

    return router
