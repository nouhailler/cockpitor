"""Read-only preflight. Reuses bounded adapters and never constructs a mutation command."""

from .actions import ActionRequest, fail
from .alerts import fresh


async def probe_target(app, request: ActionRequest):
    if request.action.startswith("service."):
        inventory = app.state.services
        if not fresh(inventory, 40) or inventory.get("status") != "available":
            fail("TARGET_UNAVAILABLE", "Inventaire de la cible indisponible ou ancien", 503)
        if not any(row.get("unit") == request.target for row in inventory.get("items", [])):
            fail("TARGET_UNKNOWN", "Cible exacte absente de l’inventaire", 422)
        return await app.state.services_adapter.action_snapshot(
            request.target, app.state.action_key
        )
    inventory = app.state.containers
    if not fresh(inventory, 40):
        fail("TARGET_UNAVAILABLE", "Inventaire de la cible indisponible ou ancien", 503)
    engine = next(
        (row for row in inventory.get("engines", []) if row.get("name") == request.engine), None
    )
    if (
        not engine
        or engine.get("status") != "available"
        or not any(row.get("id") == request.target for row in engine.get("containers", []))
    ):
        fail("TARGET_UNKNOWN", "Cible exacte absente de l’inventaire", 422)
    return await app.state.container_adapter.action_snapshot(
        request.engine, request.target, app.state.action_key
    )
