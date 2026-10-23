import asyncio
import json

from fastapi import APIRouter, Query, Request
from pydantic import ValidationError

from ..assistant import Message
from ..auth import Sessions
from ..errors import error
from ..i18n import language
from ..services import ServiceError
from ..storage import StorageError


def create_router(app):
    router = APIRouter()

    def owner(request):
        return Sessions.digest(request.headers.get("authorization", "")[7:])

    @router.post("/api/v1/ai/context")
    def context(request: Request):
        return app.state.assistant.preview(owner(request), app.state.snapshot)

    @router.post("/api/v1/ai/cancel")
    def cancel(request: Request):
        app.state.assistant.cancel(owner(request))
        return {"status": "completed"}

    @router.get("/api/v1/ai/threads")
    def threads():
        if not app.state.storage_ready:
            raise StorageError(app.state.storage_error)
        return app.state.store.threads()

    @router.get("/api/v1/ai/thread")
    def thread(id: str = Query(pattern=r"^[a-f0-9]{32}$")):
        return {"items": app.state.store.messages(id)}

    @router.post("/api/v1/ai/chat")
    async def chat(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                return error(413, "BODY_LIMIT", "Requête IA limitée à 64 Kio")
        try:
            payload = Message.model_validate_json(bytes(body))
        except ValidationError:
            return error(422, "INVALID_AI_REQUEST", "Demande IA invalide")
        available = (app.state.ai or {}).get("ollama", {})
        if available.get("status") != "available" or not any(
            m.get("name") == payload.model and m.get("local", True)
            for m in available.get("models", [])
        ):
            return error(422, "AI_MODEL_UNKNOWN", "Choisissez un modèle local disponible")
        previous = [message.model_dump() for message in payload.history]
        if payload.thread_id:
            previous = await asyncio.to_thread(app.state.store.messages, payload.thread_id)
        if payload.retain and not app.state.storage_ready:
            raise StorageError(app.state.storage_error)
        # One local user, with shared saved conversations; tokens never identify separate accounts.
        task = asyncio.create_task(
            app.state.assistant.chat(
                owner(request),
                payload,
                [{"role": m["role"], "content": m["content"]} for m in previous[-8:]],
                language.get(),
            )
        )
        try:
            while not task.done():
                await asyncio.sleep(0.2)
                if await request.is_disconnected() or not app.state.sessions.authorize(
                    request.headers["authorization"][7:]
                ):
                    task.cancel()
                    raise ServiceError("AI_CANCELLED", "Génération annulée", 409)
            prompt, answer, context_data = await task
            thread_id = None
            if payload.retain:
                stored_answer = (
                    answer
                    if context_data is None
                    else answer + "\n\n[system/metrics]\n" + json.dumps(context_data)
                )
                thread_id = await asyncio.to_thread(
                    app.state.store.save_chat, payload.thread_id, prompt, stored_answer
                )
            return {
                "answer": answer,
                "thread_id": thread_id,
                "context": context_data,
                "system_actions_enabled": False,
            }
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return router
