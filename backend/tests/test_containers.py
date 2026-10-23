import asyncio
import json

import httpx
import pytest
from app import containers, integrations
from app.containers import ContainerError, Containers, decode_logs, statistics
from app.integrations import api_prefix

CID = "a" * 64


def inspect_data(tty=False):
    return {
        "Id": CID,
        "Name": "/test",
        "Created": "2026-10-23T00:00:00Z",
        "State": {"Status": "running", "Running": True, "ExitCode": 0},
        "Config": {
            "Image": "local-image",
            "Tty": tty,
            "Env": ["PASSWORD=SECRET"],
            "Cmd": ["SECRET"],
            "Labels": {"key": "SECRET"},
        },
        "Mounts": [{"Source": "/private/SECRET"}],
    }


def install(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(**kwargs)

    monkeypatch.setattr(containers.httpx, "AsyncClient", factory)
    monkeypatch.setenv("LOCALCOCKPIT_DOCKER_SOCKET", "/tmp/mock-docker.sock")
    monkeypatch.setenv("LOCALCOCKPIT_PODMAN_SOCKET", "/tmp/mock-podman.sock")


def version():
    return httpx.Response(
        200, json={"Version": "test", "ApiVersion": "1.47", "MinAPIVersion": "1.24"}
    )


@pytest.mark.parametrize("engine", ["docker", "podman"])
def test_details_are_read_only_and_do_not_expose_secrets(monkeypatch, engine):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return (
            version()
            if request.url.path == "/version"
            else httpx.Response(200, json=inspect_data())
        )

    install(monkeypatch, handler)
    detail = asyncio.run(Containers().detail(engine, CID))
    assert detail["name"] == "test"
    assert "SECRET" not in json.dumps(detail)
    assert calls == [("GET", "/version"), ("GET", f"/v1.47/containers/{CID}/json")]


@pytest.mark.parametrize(
    "identifier", ["../path", "--help", "abc", "a" * 63, "a" * 65, "g" * 64, "a" * 63 + ";"]
)
def test_invalid_ids_fail_before_socket_access(identifier):
    with pytest.raises(ContainerError) as exc:
        asyncio.run(Containers().detail("docker", identifier))
    assert exc.value.code == "INVALID_CONTAINER"


def test_disabled_engine_never_opens_socket(monkeypatch):
    monkeypatch.delenv("LOCALCOCKPIT_DOCKER_SOCKET", raising=False)
    with pytest.raises(ContainerError) as exc:
        asyncio.run(Containers().detail("docker", CID))
    assert exc.value.code == "ENGINE_DISABLED"


def test_cpu_and_memory_units_and_unavailable_baselines():
    sample = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 300},
            "system_cpu_usage": 1000,
            "online_cpus": 4,
        },
        "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 600},
        "memory_stats": {"usage": 2048, "limit": 4096},
    }
    assert statistics(sample)["cpu_percent"] == 200
    assert statistics(sample)["memory_usage_bytes"] == 2048
    assert statistics({})["cpu_percent"] is None
    sample["precpu_stats"] = {}
    assert statistics(sample)["cpu_percent"] is None
    assert statistics({"memory_stats": {"usage": -1}})["memory_usage_bytes"] is None


def frame(stream, text):
    body = text.encode()
    return bytes([stream, 0, 0, 0]) + len(body).to_bytes(4, "big") + body


def test_multiplexed_logs_reassemble_frames_and_redact_secrets():
    body = frame(1, "pass") + frame(2, "<img src=x>\n") + frame(1, "word=SECRET\n")
    rows = decode_logs(body, False, 100)
    assert rows[0]["message"] == "password=[MASQUÉ]"
    assert rows[1] == {"stream": "stderr", "message": "<img src=x>"}
    assert "SECRET" not in str(rows)


def test_tty_logs_are_plain_text_and_have_bounded_line_count():
    assert len(decode_logs(b"one\ntwo\nthree\n", True, 2)) == 2
    assert decode_logs(b"", False, 10) == []


@pytest.mark.parametrize("body", [b"bad", bytes([4, 0, 0, 0, 0, 0, 0, 0]), frame(1, "hello")[:-1]])
def test_malformed_log_frames_are_not_rendered_as_success(body):
    with pytest.raises(ValueError):
        decode_logs(body, False, 100)


@pytest.mark.parametrize("tty", [True, False])
def test_log_endpoint_queries_are_bounded_and_non_streaming(monkeypatch, tty):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/version":
            return version()
        if request.url.path.endswith("/json"):
            return httpx.Response(200, json=inspect_data(tty))
        body = b"api_key=SECRET\n" if tty else frame(1, "api_key=SECRET\n")
        return httpx.Response(200, content=body)

    install(monkeypatch, handler)
    result = asyncio.run(Containers().logs("docker", CID, 50, 3600))
    assert "SECRET" not in str(result)
    assert calls[-1].url.params["follow"] == "false"
    assert calls[-1].url.params["tail"] == "50"
    assert calls[-1].url.params["timestamps"] == "true"
    assert result["ordering"] == "grouped_by_stream"


@pytest.mark.parametrize(
    "status,code",
    [
        (403, "PERMISSION_DENIED"),
        (404, "CONTAINER_NOT_FOUND"),
        (409, "CONTAINER_CONFLICT"),
        (501, "CAPABILITY_UNAVAILABLE"),
    ],
)
def test_engine_errors_are_explicit_and_redacted(monkeypatch, status, code):
    def handler(request):
        return (
            version()
            if request.url.path == "/version"
            else httpx.Response(status, json={"message": "SECRET"})
        )

    install(monkeypatch, handler)
    with pytest.raises(ContainerError) as exc:
        asyncio.run(Containers().stats("docker", CID))
    assert exc.value.code == code
    assert "SECRET" not in str(exc.value)


@pytest.mark.parametrize("mode", ["oversized", "redirect", "slow", "invalid", "identity"])
def test_bad_engine_responses_do_not_leak_or_hang(monkeypatch, mode):
    def handler(request):
        if request.url.path == "/version":
            return version()
        if mode == "oversized":
            return httpx.Response(200, content=b"x" * (integrations.MAX_RESPONSE + 1))
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "http://external.example"})
        if mode == "slow":
            raise httpx.ReadTimeout("SECRET", request=request)
        if mode == "invalid":
            return httpx.Response(200, content=b"not json SECRET")
        data = inspect_data()
        data["Id"] = "b" * 64
        return httpx.Response(200, json=data)

    install(monkeypatch, handler)
    with pytest.raises(ContainerError) as exc:
        asyncio.run(Containers().detail("docker", CID))
    assert "SECRET" not in str(exc.value)


@pytest.mark.parametrize(
    "api,minimum,expected",
    [("1.55", "1.44", "/v1.47"), ("1.40", "1.24", "/v1.40"), ("1.55", "1.50", None)],
)
def test_version_negotiation(monkeypatch, api, minimum, expected):
    install(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"Version": "test", "ApiVersion": api, "MinAPIVersion": minimum}
        ),
    )

    async def check():
        async with httpx.AsyncClient() as client:
            if expected is None:
                with pytest.raises(ValueError):
                    await api_prefix(client)
            else:
                assert (await api_prefix(client))[0] == expected

    asyncio.run(check())


def test_real_unix_socket_transport_uses_only_fixed_read_endpoints(monkeypatch):
    import tempfile
    from pathlib import Path

    async def exercise(socket):
        calls = []

        async def handler(reader, writer):
            try:
                request = await reader.readuntil(b"\r\n\r\n")
                first = request.split(b"\r\n", 1)[0].decode()
                calls.append(first)
                path = first.split(" ")[1]
                if path == "/version":
                    body = json.dumps({"Version": "fixture", "ApiVersion": "1.47"}).encode()
                elif path.endswith("/json"):
                    body = json.dumps(inspect_data(True)).encode()
                else:
                    body = b"password=SECRET\n"
                writer.write(
                    b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(handler, path=socket)
        try:
            adapter = Containers()
            result = await adapter.logs("docker", CID, 50, 3600)
            assert result["items"][0]["message"] == "password=[MASQUÉ]"
            assert len(calls) == 3 and all(call.startswith("GET ") for call in calls)
            assert calls[1] == f"GET /v1.47/containers/{CID}/json HTTP/1.1"
            assert "follow=false" in calls[2]
        finally:
            server.close()
            await server.wait_closed()

    with tempfile.TemporaryDirectory(prefix="lc-", dir="/tmp") as directory:
        socket = str(Path(directory) / "engine.sock")
        monkeypatch.setenv("LOCALCOCKPIT_DOCKER_SOCKET", socket)
        asyncio.run(exercise(socket))


def test_detailed_read_concurrency_limit(monkeypatch):
    monkeypatch.setenv("LOCALCOCKPIT_DOCKER_SOCKET", "/tmp/not-opened.sock")

    async def exercise():
        adapter = Containers()
        await adapter.slots.acquire()
        await adapter.slots.acquire()
        with pytest.raises(ContainerError) as exc:
            await adapter.stats("docker", CID)
        assert exc.value.code == "BUSY"
        assert adapter.slots._value == 0

    asyncio.run(exercise())


def test_failed_read_releases_slot(monkeypatch):
    install(monkeypatch, lambda request: httpx.Response(403))

    async def exercise():
        adapter = Containers()
        with pytest.raises(ContainerError):
            await adapter.detail("docker", CID)
        assert adapter.slots._value == 2

    asyncio.run(exercise())
