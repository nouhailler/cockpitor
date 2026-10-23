import asyncio
import json

import httpx
import pytest
from app import integrations


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://localhost:11434",
        "http://127.0.0.1.evil",
        "http://user:secret@127.0.0.1",
        "http://192.168.1.1",
        "file:///etc/passwd",
        "http://127.0.0.1/path",
        "http://127.0.0.1?key=secret",
    ],
)
def test_only_numeric_loopback_bases(url):
    with pytest.raises(ValueError):
        integrations.local_url(url)


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(**kwargs)

    monkeypatch.setattr(integrations.httpx, "AsyncClient", factory)


def test_ollama_models_and_optional_running_endpoint(monkeypatch):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "local",
                            "size": 1024,
                            "details": {"family": "test", "quantization_level": "Q4"},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    install_transport(monkeypatch, handler)
    monkeypatch.delenv("LOCALCOCKPIT_OPENWEBUI_URL", raising=False)
    data = asyncio.run(integrations.ai_status())
    assert data["ollama"]["status"] == "available"
    assert data["ollama"]["models"][0]["name"] == "local"
    assert "loaded" not in data["ollama"]
    assert data["openwebui"]["status"] == "disabled"


@pytest.mark.parametrize("mode", ["invalid", "slow", "redirect", "oversized"])
def test_ollama_failures_are_isolated_and_redacted(monkeypatch, mode):
    def handler(request):
        if mode == "slow":
            raise httpx.ReadTimeout("SECRET", request=request)
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "http://evil.example"})
        if mode == "oversized":
            return httpx.Response(200, content=b"x" * (integrations.MAX_RESPONSE + 1))
        return httpx.Response(200, json={"models": "SECRET"})

    install_transport(monkeypatch, handler)
    result = asyncio.run(integrations.ai_status())
    assert result["ollama"]["status"] == "unavailable"
    assert "SECRET" not in json.dumps(result)


def test_containers_opt_in_and_field_allowlist(monkeypatch):
    monkeypatch.setenv("LOCALCOCKPIT_DOCKER_SOCKET", "/tmp/test-docker.sock")
    monkeypatch.delenv("LOCALCOCKPIT_PODMAN_SOCKET", raising=False)
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/version":
            return httpx.Response(200, json={"Version": "test", "ApiVersion": "1.47"})
        return httpx.Response(
            200,
            json=[
                {
                    "Id": "abc",
                    "Names": ["/test"],
                    "Image": "local",
                    "State": "running",
                    "Env": ["PASSWORD=secret"],
                    "Ports": [
                        {"PrivatePort": 80, "PublicPort": 8080, "IP": "127.0.0.1", "Type": "tcp"}
                    ],
                }
            ],
        )

    install_transport(monkeypatch, handler)
    result = asyncio.run(integrations.container_status())
    docker = result["engines"][0]
    assert docker["status"] == "available"
    assert docker["containers"][0]["name"] == "test"
    assert "secret" not in json.dumps(result)
    assert all(method == "GET" for method, _ in calls)
    assert len(calls) == 2


def test_container_permissions_failure_is_explicit(monkeypatch):
    monkeypatch.setenv("LOCALCOCKPIT_PODMAN_SOCKET", "/tmp/test-podman.sock")
    monkeypatch.delenv("LOCALCOCKPIT_DOCKER_SOCKET", raising=False)
    install_transport(monkeypatch, lambda request: httpx.Response(403))
    result = asyncio.run(integrations.container_status())
    assert result["engines"][1]["status"] == "unavailable"
    assert "permissions" in result["engines"][1]["message"]
