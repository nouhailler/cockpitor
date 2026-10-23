import time

import pytest
from app import main
from app.main import TOKEN, app
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALCOCKPIT_DATA_DIR", str(tmp_path / "state"))

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

    async def offline_inspect():
        return {"collected_at": "2026-10-23T00:00:00Z"}

    monkeypatch.setattr(main, "inspect", offline_inspect)
    monkeypatch.setattr(main.Services, "inventory", offline_services)
    monkeypatch.setattr(main, "ai_status", offline_ai)
    monkeypatch.setattr(main, "container_status", offline_containers)
    with TestClient(
        app, base_url="http://127.0.0.1:8765", headers={"Authorization": "Bearer " + TOKEN}
    ) as client:
        options = client.get("/api/v1/auth/options").json()
        session = client.post(
            "/api/v1/auth/sessions",
            json={"token": TOKEN},
            headers={
                "origin": "http://127.0.0.1:8765",
                "x-localcockpit-csrf": options["csrf_token"],
            },
        ).json()
        client.headers["Authorization"] = "Bearer " + session["token"]
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


def test_container_detail_routes_validate_and_refuse_mutations(client, monkeypatch):
    cid = "a" * 64
    path = f"/api/v1/containers/docker/{cid}"
    monkeypatch.delenv("LOCALCOCKPIT_DOCKER_SOCKET", raising=False)
    assert client.get(path).json()["error"]["code"] == "ENGINE_DISABLED"
    assert client.get("/api/v1/containers/docker/not-an-id").status_code == 422
    assert client.get(f"/api/v1/containers/shell/{cid}").status_code == 422
    assert client.get(path + "/logs?tail=201").status_code == 422
    assert client.get(path + "/logs?tail=0").status_code == 422
    assert client.get(path + "/logs?period=week").status_code == 422
    assert client.get(path + "/stats", headers={"authorization": ""}).status_code == 401
    assert client.post(path + "/restart").status_code == 405

    async def detail(self, engine, container_id):
        return {"id": container_id, "engine": engine, "name": "test"}

    async def stats(self, engine, container_id):
        return {"cpu_percent": None, "memory_usage_bytes": 1234}

    async def logs(self, engine, container_id, tail, period):
        assert tail == 50 and period == 86400
        return {"items": [{"stream": "stdout", "message": "<img src=x>"}]}

    monkeypatch.setattr(main.Containers, "detail", detail)
    monkeypatch.setattr(main.Containers, "stats", stats)
    monkeypatch.setattr(main.Containers, "logs", logs)
    assert client.get(path).json()["id"] == cid
    assert client.get(path + "/stats").json()["memory_usage_bytes"] == 1234
    assert (
        client.get(path + "/logs?tail=50&period=day").json()["items"][0]["message"] == "<img src=x>"
    )


def wait_settings(client):
    for _ in range(100):
        response = client.get("/api/v1/settings")
        if response.status_code == 200:
            return response.json()
        time.sleep(0.02)
    raise AssertionError(response.json())


def test_settings_save_requires_auth_origin_csrf_json_and_bounds(client):
    envelope = wait_settings(client)
    settings = envelope["settings"]
    path = "/api/v1/settings"
    safe = {"origin": "http://127.0.0.1:8765", "x-localcockpit-csrf": envelope["csrf_token"]}
    assert client.put(path, json=settings).status_code == 403
    assert (
        client.put(path, json=settings, headers={"origin": "http://evil.example"}).status_code
        == 403
    )
    assert (
        client.put(path, json=settings, headers={"origin": "http://127.0.0.1:8765"}).status_code
        == 403
    )
    assert client.put(path, json=settings, headers={**safe, "authorization": ""}).status_code == 401
    assert (
        client.put(path, content="{}", headers={**safe, "content-type": "text/plain"}).status_code
        == 415
    )
    assert (
        client.put(
            path, content="x" * 16385, headers={**safe, "content-type": "application/json"}
        ).status_code
        == 413
    )
    assert (
        client.put(path, json={**settings, "listen_address": "0.0.0.0"}, headers=safe).status_code
        == 422
    )
    assert (
        client.put(path, json={**settings, "refresh_seconds": 1}, headers=safe).status_code == 422
    )
    response = client.put(
        path, json={**settings, "theme": "light", "refresh_seconds": 10}, headers=safe
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed" and response.json()["operation_id"]
    assert client.get(path).json()["settings"]["theme"] == "light"
    assert client.post("/api/v1/actions/restart").status_code == 405


def test_alerts_filters_and_storage_failure_do_not_break_system(client, monkeypatch):
    wait_settings(client)
    event = client.app.state.store.activate("test", "warning", "Seuil franchi")
    assert client.get("/api/v1/alerts?status=active").json()["items"][0]["id"] == event
    assert client.get("/api/v1/alerts?limit=999").status_code == 422
    assert client.get("/api/v1/alerts?status=arbitrary").status_code == 422
    assert client.get("/api/v1/alerts", headers={"authorization": ""}).status_code == 401
    client.app.state.store.resolve(event)
    assert client.get("/api/v1/alerts?status=resolved").json()["total"] == 1

    def unavailable():
        raise main.StorageError("Stockage local indisponible")

    monkeypatch.setattr(client.app.state.store, "preferences", unavailable)
    assert client.get("/api/v1/settings").status_code == 503
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health").json()["read_only"] is True
