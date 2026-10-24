import asyncio

from fastapi import APIRouter, Query, Request
from pydantic import ValidationError

from ..actions import ACTIONS, ActionRequest, Approval, Reference, Simulation, fail
from ..errors import error
from ..storage import StorageError


def create_router(app):
    router = APIRouter()

    def ready():
        if not app.state.storage_ready:
            raise StorageError(app.state.storage_error)

    def owner(request):
        return app.state.sessions.digest(request.headers["authorization"][7:])

    async def body(request, schema):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 2048:
                fail("BODY_LIMIT", "Plan limité à 2 Kio", 413)
        try:
            return schema.model_validate_json(bytes(data))
        except ValidationError:
            fail("INVALID_PLAN", "Plan ou confirmation invalide", 422)

    @router.get("/api/v1/action-plans/options")
    def options():
        return {
            "actions": ACTIONS,
            "mode": "simulation",
            "system_execution_enabled": False,
            "plan_seconds": 120,
            "approval_seconds": 60,
            "simulation_timeout_seconds": 8,
        }

    @router.get("/api/v1/operations")
    async def operations(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        ready()
        return await asyncio.to_thread(app.state.store.operations, limit, offset)

    @router.get("/api/v1/action-plans")
    async def plans(request: Request):
        ready()
        await app.state.actions.cleanup()
        return {
            "items": [
                app.state.actions.view(plan)
                for plan in app.state.actions.plans.values()
                if plan.owner == owner(request)
            ]
        }

    @router.post("/api/v1/action-plans/prepare")
    async def prepare(request: Request):
        ready()
        return await app.state.actions.prepare(owner(request), await body(request, ActionRequest))

    @router.post("/api/v1/action-plans/approve")
    async def approve(request: Request):
        ready()
        return await app.state.actions.approve(owner(request), await body(request, Approval))

    @router.post("/api/v1/action-plans/cancel")
    async def cancel(request: Request):
        ready()
        payload = await body(request, Reference)
        return await app.state.actions.cancel(owner(request), payload.plan_id)

    @router.post("/api/v1/action-plans/simulate")
    async def simulate(request: Request):
        ready()
        payload = await body(request, Simulation)
        task = asyncio.create_task(app.state.actions.simulate(owner(request), payload))
        try:
            while not task.done():
                await asyncio.sleep(0.05)
                if await request.is_disconnected() or not app.state.sessions.valid_owner(
                    owner(request)
                ):
                    task.cancel()
            return await task
        except asyncio.CancelledError:
            return error(409, "ACTION_CANCELLED", "Simulation annulée")
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return router
