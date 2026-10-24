import asyncio
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..auth import ABSOLUTE_SECONDS, IDLE_SECONDS
from ..errors import error
from ..storage import StorageError


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    token: str = Field(min_length=1, max_length=256)


async def record(app, action):
    if app.state.storage_ready:
        try:
            await asyncio.to_thread(app.state.store.audit, str(uuid.uuid4()), action)
        except StorageError:
            pass  # Local observation remains available when SQLite is unavailable.


def create_router(app):
    router = APIRouter()

    @router.get("/api/v1/auth/options")
    def options():
        return {
            "csrf_token": app.state.csrf,
            "idle_seconds": IDLE_SECONDS,
            "absolute_seconds": ABSOLUTE_SECONDS,
        }

    @router.post("/api/v1/auth/sessions")
    async def login(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1024:
                return error(413, "BODY_LIMIT", "Requête limitée à 1 Kio")
        try:
            payload = Login.model_validate_json(bytes(body))
        except ValidationError:
            return error(422, "INVALID_LOGIN", "Demande de connexion invalide")
        token, code = app.state.sessions.login(payload.token)
        if code:
            return error(
                429 if code != "AUTH_REQUIRED" else 401,
                code,
                "Connexion refusée ; vérifiez le jeton ou réessayez dans une minute",
            )
        await record(app, "session.login")
        return {
            "token": token,
            "csrf_token": app.state.csrf,
            "idle_seconds": IDLE_SECONDS,
            "absolute_seconds": ABSOLUTE_SECONDS,
        }

    @router.post("/api/v1/auth/logout")
    async def logout(request: Request):
        app.state.assistant.cancel(
            app.state.sessions.digest(
                request.headers.get("authorization", "").removeprefix("Bearer ")
            )
        )
        app.state.sessions.revoke(request.headers.get("authorization", "").removeprefix("Bearer "))
        try:
            await app.state.actions.cleanup()
        except StorageError:
            pass  # Revocation must still succeed when audit storage is unavailable.
        await record(app, "session.logout")
        return {"status": "completed"}

    @router.post("/api/v1/auth/activity")
    def activity(request: Request):
        if not app.state.sessions.authorize(request.headers["authorization"][7:], touch=True):
            return error(401, "AUTH_REQUIRED", "Session expirée")
        return {"status": "completed"}

    return router
