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

    async def offline_services(self):
        return {
            "status": "available",
            "collected_at": "2026-10-23T00:00:00Z",
            "items": [
                {
                    "unit": "ssh.service",
                    "description": "OpenSSH",
                    "active": "active",
                    "load": "loaded",
                    "sub": "running",
                },
                {
                    "unit": "failed.service",
                    "description": "Failed",
                    "active": "failed",
                    "load": "loaded",
                    "sub": "failed",
                },
            ],
        }

    monkeypatch.setattr(main.Services, "inventory", offline_services)
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


def test_services_filters_validation_auth_and_read_only(client, monkeypatch):
    for _ in range(100):
        response = client.get("/api/v1/services?state=failed&limit=1")
        if response.status_code == 200:
            break
        time.sleep(0.01)
    assert response.json()["items"][0]["unit"] == "failed.service"
    assert client.get("/api/v1/services?q=OpenSSH").json()["total"] == 1
    assert client.get("/api/v1/services?state=invalid").status_code == 422
    assert client.get("/api/v1/services?limit=10000").status_code == 422
    assert client.get("/api/v1/services/ssh.service/logs?period=week").status_code == 422
    assert client.get("/api/v1/services/ssh.service/logs?priority=8").status_code == 422
    assert client.get("/api/v1/services/ssh.service/logs?limit=999").status_code == 422
    assert client.get("/api/v1/services/--help.service").status_code == 422
    assert (
        client.get("/api/v1/services/ssh.service/logs", headers={"authorization": ""}).status_code
        == 401
    )
    assert client.post("/api/v1/services/ssh.service/restart").status_code == 405

    async def fake_logs(self, unit, limit, period, priority, q, cursor):
        assert period == 3600
        return {"unit": unit, "items": [], "scanned": 0, "next_cursor": None}

    monkeypatch.setattr(main.Services, "logs", fake_logs)
    assert client.get("/api/v1/services/ssh.service/logs?period=hour").status_code == 200

    async def denied(self, unit):
        raise main.ServiceError("PERMISSION_DENIED", "Droits de lecture insuffisants", 403)

    monkeypatch.setattr(main.Services, "detail", denied)
    response = client.get("/api/v1/services/ssh.service")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
