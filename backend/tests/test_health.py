import json
from types import SimpleNamespace

import pytest
from app.health import availability, observation_status
from app.system import timestamp


@pytest.mark.parametrize("status", ["available", "unavailable", "disabled"])
def test_status_requires_fresh_observation(status):
    assert observation_status({"collected_at": timestamp(), "status": status}, 40) == status
    assert (
        observation_status({"collected_at": "2000-01-01T00:00:00Z", "status": status}, 40)
        == "stale"
    )


@pytest.mark.parametrize("date", [None, "invalid", "2099-01-01T00:00:00Z"])
def test_unknown_or_future_observations_are_not_available(date):
    assert observation_status({"collected_at": date, "status": "available"}, 40) == "stale"
    assert observation_status(None, 40) == "collecting"


def test_summary_is_allowlisted_and_missing_engine_is_not_disabled(monkeypatch):
    monkeypatch.setattr("app.health.platform.release", lambda: "6.12.113-private-host")
    source = {"collected_at": timestamp(), "status": "available", "secret": "PRIVATE_MARKER"}
    state = SimpleNamespace(
        snapshot=source,
        inspection=source,
        services=source,
        ai={"ollama": source, "openwebui": {**source, "status": "disabled"}},
        containers={
            **source,
            "engines": [
                {"name": "docker", "status": "available", "containers": ["PRIVATE_MARKER"]}
            ],
        },
    )
    result = availability(state)
    assert "PRIVATE_MARKER" not in json.dumps(result)
    assert "private-host" not in json.dumps(result)
    assert result["environment"]["kernel_version"] == "6.12.113"
    statuses = {row["id"]: row["status"] for row in result["modules"]}
    assert statuses == {
        "system": "available",
        "monitoring": "available",
        "services": "available",
        "ollama": "available",
        "openwebui": "disabled",
        "docker": "available",
        "podman": "unavailable",
    }
    assert all(set(row) == {"id", "status"} for row in result["modules"])

    # Use an isolated state so background recovery cannot race this assertion.
    from app.routes.system import create_router

    state.storage_ready = False
    router = create_router(SimpleNamespace(state=state))
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/v1/health")
    assert endpoint()["storage"]["status"] == "unavailable"
