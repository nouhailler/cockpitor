import time

import pytest
from app import main
from app.main import TOKEN, app
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    async def offline_ai():
        return {"status": "ok", "ollama": {"status": "unavailable"}}

    async def offline_containers():
        return {"status": "ok", "engines": []}

    monkeypatch.setattr(main, "ai_status", offline_ai)
    monkeypatch.setattr(main, "container_status", offline_containers)
    with TestClient(
        app, base_url="http://127.0.0.1:8765", headers={"Authorization": "Bearer " + TOKEN}
    ) as client:
        yield client


def test_auth_host_origin_and_no_mutations(client):
    assert client.get("/api/v1/health", headers={"authorization": ""}).status_code == 401
    assert client.get("/api/v1/health", headers={"host": "evil.example"}).status_code == 400
    assert (
        client.get("/api/v1/health", headers={"origin": "http://evil.example"}).status_code == 403
    )
    for method in ["post", "put", "patch", "delete"]:
        assert getattr(client, method)("/api/v1/actions/restart").status_code == 405
    response = client.get("/api/v1/health")
    assert response.json()["read_only"] is True
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "access-control-allow-origin" not in response.headers


def test_metrics_processes_and_validation(client):
    for _ in range(100):
        response = client.get("/api/v1/system/metrics")
        if response.status_code == 200:
            break
        time.sleep(0.02)
    assert response.status_code == 200
    assert "processes" not in response.json()
    assert "collected_at" in response.json()
    data = client.get("/api/v1/system/processes?limit=1").json()
    assert len(data["items"]) <= 1
    assert data["total"] >= len(data["items"])
    assert client.get("/api/v1/system/processes?limit=10000").status_code == 422
    assert client.get("/api/v1/system/processes?offset=-1").status_code == 422
    assert client.get("/api/v1/system/processes?q=unlikely_process_938471").json()["items"] == []
    assert len(client.get("/api/v1/system/history").json()) <= 450


def test_optional_routes_return_independent_cached_results(client):
    client.app.state.ai = {"status": "ok", "ollama": {"status": "unavailable"}}
    client.app.state.containers = {"status": "ok", "engines": []}
    assert client.get("/api/v1/ai/status").json()["ollama"]["status"] == "unavailable"
    assert client.get("/api/v1/containers").json()["engines"] == []
    assert client.get("/api/v1/health").status_code == 200
