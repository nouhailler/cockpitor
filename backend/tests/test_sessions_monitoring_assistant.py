import asyncio
import json
import sqlite3
import time

import httpx
import pytest
from app import assistant, main, monitoring
from app.assistant import Assistant, Message, safe_context
from app.auth import ABSOLUTE_SECONDS, IDLE_SECONDS, Sessions
from app.storage import Store
from app.system import timestamp
from test_api import wait_settings

pytest_plugins = ["test_api"]
ORIGIN = "http://127.0.0.1:8765"


def safe(client):
    return {"origin": ORIGIN, "x-localcockpit-csrf": client.app.state.csrf}


def test_sessions_expire_revoke_and_hash_tokens():
    now = [0.0]
    sessions = Sessions("bootstrap", clock=lambda: now[0])
    token, code = sessions.login("bootstrap")
    assert not code and token != "bootstrap" and token not in sessions.sessions
    assert not sessions.authorize("bootstrap")
    now[0] = IDLE_SECONDS - 1
    assert sessions.authorize(token)
    now[0] += 1
    assert not sessions.authorize(token), "background API reads must not extend inactivity"
    token, _ = sessions.login("bootstrap")
    for _ in range(40):
        now[0] += 800
        if now[0] < IDLE_SECONDS + ABSOLUTE_SECONDS:
            assert sessions.authorize(token, touch=True)
    assert not sessions.authorize(token)
    token, _ = sessions.login("bootstrap")
    sessions.revoke(token)
    assert not sessions.authorize(token)


def test_login_rate_limit_and_window():
    now = [0]
    sessions = Sessions("bootstrap", clock=lambda: now[0])
    for _ in range(10):
        assert sessions.login("wrong")[1] == "AUTH_REQUIRED"
    assert sessions.login("bootstrap")[1] == "AUTH_RATE_LIMIT"
    now[0] = 60
    assert sessions.login("bootstrap")[0]


def test_bootstrap_exchange_security_logout_and_replay(client):
    assert (
        client.get("/api/v1/health", headers={"authorization": "Bearer " + main.TOKEN}).status_code
        == 401
    )
    assert client.post("/api/v1/auth/sessions", json={"token": main.TOKEN}).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/sessions", json={"token": main.TOKEN, "admin": True}, headers=safe(client)
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/sessions",
            content="x" * 1025,
            headers={**safe(client), "content-type": "application/json"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/v1/auth/sessions", json={"token": "wrong"}, headers=safe(client)
        ).status_code
        == 401
    )
    token = client.headers["authorization"]
    assert client.post("/api/v1/auth/activity", headers=safe(client), json={}).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=safe(client), json={}).status_code == 200
    assert client.get("/api/v1/health", headers={"authorization": token}).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=safe(client), json={}).status_code == 401


def test_api_expiration_and_capability_manifest(client):
    session = next(iter(client.app.state.sessions.sessions.values()))
    session.touched -= IDLE_SECONDS
    assert client.get("/api/v1/system/metrics").status_code == 401
    assert not client.app.state.sessions.sessions


def test_modules_audit_trends_and_storage_failure(client):
    wait_settings(client)
    assert all(
        not module["system_actions"] for module in client.get("/api/v1/modules").json()["items"]
    )
    client.app.state.store.audit("test-operation", "diagnostics.export")
    audit = client.get("/api/v1/audit").json()
    assert audit["total"] <= 1000
    assert set(audit["items"][0]) == {"id", "action", "timestamp"}
    assert client.get("/api/v1/audit?limit=201").json()["error"]["code"] == "INVALID_REQUEST"
    assert client.get("/api/v1/system/trends?hours=169").status_code == 422
    assert client.get("/api/v1/system/trends").json()["resolution_seconds"] == 60
    client.app.state.storage_ready = False
    assert client.get("/api/v1/system/trends").status_code == 503
    assert client.get("/api/v1/health").status_code == 200


def test_schema_v1_upgrade_backup_history_retention_and_reopen(tmp_path, monkeypatch):
    store = Store(tmp_path / "state")
    store.initialize()
    with store.connection() as db:
        db.execute("DROP TABLE metric_history")
        db.execute("DROP TABLE ai_messages")
        db.execute("DROP TABLE ai_threads")
        db.execute("PRAGMA user_version=1")
    store.initialize()
    assert list(store.directory.glob("backup-*.sqlite3"))
    with sqlite3.connect(next(store.directory.glob("backup-*.sqlite3"))) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    sample = {"collected_at": timestamp(), "cpu_percent": 10, "memory": {"percent": 20}}
    store.record_metrics(sample)
    store.record_metrics({**sample, "cpu_percent": 99})
    assert len(store.metric_history(24)) == 1
    assert store.metric_history(24)[0]["cpu_percent"] == 10
    future = time.time() + 8 * 86400
    monkeypatch.setattr("app.storage.time.time", lambda: future)
    store.record_metrics(sample)
    assert len(store.metric_history(168)) == 1
    assert Store(store.directory).initialize()


@pytest.mark.parametrize(
    "address,scope",
    [
        ("127.0.0.1", "loopback"),
        ("::1", "loopback"),
        ("0.0.0.0", "all_interfaces"),
        ("::", "all_interfaces"),
        ("192.168.1.2", "private"),
        ("8.8.8.8", "public_address"),
        ("invalid", "unknown"),
    ],
)
def test_listener_scopes(address, scope):
    assert monitoring.exposure(address) == scope


def test_monitoring_tools_absent_and_no_install(monkeypatch):
    calls = []

    async def absent(*args):
        calls.append(args)
        return {"status": "unavailable"}

    monkeypatch.setattr(monitoring, "command", absent)
    monkeypatch.setattr(monitoring, "network", lambda: {"status": "unavailable"})
    monkeypatch.setattr(monitoring, "power", lambda: {"status": "unavailable"})
    result = asyncio.run(monitoring.inspect())
    assert all(
        result[key]["status"] == "unavailable" for key in ("gpu", "updates", "time", "disks")
    )
    assert not any("install" in call or "sudo" in call or "update" in call for call in calls)
    assert ("/usr/bin/apt", "list", "--upgradable") in calls


def test_monitoring_parses_only_read_commands(monkeypatch):
    async def mocked(*args):
        if args[0] == "/usr/bin/upsc":
            return {"status": "unavailable"}
        output = {
            "/usr/bin/lsblk": '{"blockdevices": [{"name":"sda", "type":"disk"}]}',
            "/usr/sbin/smartctl": '{"smart_status":{"passed":true}}',
            "/usr/bin/systemctl": "ssh.service enabled enabled\n",
            "/usr/bin/apt": "Listing...\nhello/stable 1.2 amd64 [upgradable from: 1.1]\n",
            "/usr/bin/nvidia-smi": "GPU, 10, 100, 1000\n",
            "/usr/bin/timedatectl": "NTPSynchronized=yes\n",
        }[args[0]]
        return {"status": "available", "output": output}

    monkeypatch.setattr(monitoring, "command", mocked)
    result = asyncio.run(monitoring.inspect())
    assert result["smart"][0]["passed"] is True
    assert result["updates"]["data"][0]["package"] == "hello"
    assert result["gpu"]["data"][0]["utilization"] == 10


def test_assistant_context_excludes_identity_and_binds_owner():
    advisor = Assistant()
    metrics = {
        "collected_at": timestamp(),
        "hostname": "SECRET_HOST",
        "cpu_percent": 1,
        "memory": {"percent": 20},
        "logs": "SECRET_LOG",
    }
    preview = advisor.preview("owner", metrics)
    assert "SECRET" not in json.dumps(preview)
    assert advisor.context("owner", preview["context_id"]) == safe_context(metrics)
    with pytest.raises(main.ServiceError):
        advisor.context("other", preview["context_id"])
    owner, context, _ = advisor.contexts[preview["context_id"]]
    advisor.contexts[preview["context_id"]] = (owner, context, 0)
    with pytest.raises(main.ServiceError):
        advisor.context("owner", preview["context_id"])


def test_assistant_generation_no_tools_redaction_and_bounds(monkeypatch):
    async def fake(model, messages):
        assert model == "local-model"
        assert messages[0]["role"] == "system"
        assert "French" in messages[0]["content"]
        assert "secret123" not in json.dumps(messages)
        assert messages[-1]["content"] == "password=[MASQUÉ]"
        return "Diagnostic only"

    monkeypatch.setattr(assistant, "generate", fake)
    result = asyncio.run(
        Assistant().chat(
            "owner", Message(model="local-model", prompt="password=secret123"), [], "fr"
        )
    )
    assert result[1] == "Diagnostic only"


def test_assistant_api_consent_retention_and_failures(client, monkeypatch):
    wait_settings(client)
    client.app.state.ai = {"ollama": {"status": "available", "models": [{"name": "local"}]}}

    async def fake(model, messages):
        return "<script>not executable</script>"

    monkeypatch.setattr(assistant, "generate", fake)
    payload = {"model": "local", "prompt": "Explain memory"}
    assert client.post("/api/v1/ai/chat", json=payload).status_code == 403
    assert (
        client.post(
            "/api/v1/ai/chat", json={**payload, "url": "http://evil"}, headers=safe(client)
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/ai/chat", json={**payload, "model": "unknown"}, headers=safe(client)
        ).status_code
        == 422
    )
    response = client.post("/api/v1/ai/chat", json=payload, headers=safe(client))
    assert response.status_code == 200
    assert response.json()["thread_id"] is None
    assert client.get("/api/v1/ai/threads").json()["items"] == []
    assert client.post("/api/v1/ai/chat", json=payload, headers=safe(client)).status_code == 429
    client.app.state.assistant.last_request = -10
    response = client.post(
        "/api/v1/ai/chat", json={**payload, "retain": True}, headers=safe(client)
    )
    thread = response.json()["thread_id"]
    assert (
        thread
        and client.get("/api/v1/ai/thread?id=" + thread).json()["items"][0]["content"]
        == payload["prompt"]
    )
    assert client.post("/api/v1/ai/cancel", json={}, headers=safe(client)).status_code == 200
    assert client.post("/api/v1/actions/run", json=payload, headers=safe(client)).status_code == 405


def test_ollama_http_uses_fixed_local_url_and_no_tools(monkeypatch):
    original = httpx.AsyncClient

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"model_info": {"general.architecture": "test"}})
        assert request.url == "http://127.0.0.1:11434/api/chat"
        payload = json.loads(request.content)
        assert payload["stream"] is False and "tools" not in payload
        assert payload["options"]["num_predict"] == 1024
        return httpx.Response(200, json={"done": True, "message": {"content": "Answer"}})

    monkeypatch.setattr(
        assistant.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert asyncio.run(assistant.generate("model", [])) == "Answer"
    monkeypatch.setenv("LOCALCOCKPIT_OLLAMA_URL", "http://192.168.1.10")
    with pytest.raises(ValueError):
        asyncio.run(assistant.generate("model", []))


def test_chat_store_is_bounded_and_persistent(tmp_path):
    store = Store(tmp_path / "state")
    store.initialize()
    thread = None
    for i in range(25):
        thread = store.save_chat(thread, str(i), "answer")
    assert len(store.messages(thread)) == 40
    for _ in range(25):
        store.save_chat(None, "prompt", "answer")
    assert len(store.threads()["items"]) == 20
    assert Store(store.directory).initialize()


def test_optional_module_failure_keeps_other_collectors(client, monkeypatch):
    async def failed():
        raise RuntimeError("untrusted-secret-error")

    async def containers():
        return {"status": "ok", "engines": []}

    monkeypatch.setattr(main, "ai_status", failed)
    monkeypatch.setattr(main, "container_status", containers)
    previous = client.app.state.ai
    asyncio.run(main.refresh_integrations(client.app))
    assert client.app.state.ai == previous
    assert client.app.state.containers == {"status": "ok", "engines": []}
    assert client.get("/api/v1/health").status_code == 200


def test_cancellation_and_concurrent_generation_release_slot(monkeypatch):
    started = asyncio.Event()

    async def pending(*args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(assistant, "generate", pending)

    async def scenario():
        advisor = Assistant()
        task = asyncio.create_task(
            advisor.chat("owner", Message(model="local", prompt="explain"), [], "fr")
        )
        await started.wait()
        with pytest.raises(main.ServiceError) as exc:
            await advisor.chat("other", Message(model="local", prompt="other"), [], "fr")
        assert exc.value.status == 429
        advisor.cancel("other")
        assert not task.done()
        advisor.cancel("owner")
        with pytest.raises(main.ServiceError) as exc:
            await task
        assert exc.value.code == "AI_CANCELLED"
        assert advisor.jobs == {}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(302, headers={"location": "https://evil.example"}),
        httpx.Response(200, content=b"x" * 65537),
        httpx.Response(200, json={"done": False, "message": {"content": "partial"}}),
    ],
)
def test_ollama_rejects_redirect_oversize_and_incomplete(monkeypatch, reply):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        assistant.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda request: (
                    httpx.Response(200, json={"model_info": {"general.architecture": "test"}})
                    if request.url.path == "/api/show"
                    else reply
                )
            ),
            **kwargs,
        ),
    )
    with pytest.raises((ValueError, httpx.HTTPError)):
        asyncio.run(assistant.generate("local", []))


@pytest.mark.parametrize(
    "address,scope",
    [("224.0.0.251", "multicast"), ("ff02::1", "multicast"), ("fe80::1", "link_local")],
)
def test_multicast_is_not_a_public_service(address, scope):
    assert monitoring.exposure(address) == scope


def test_cloud_model_is_refused_before_prompt_transmission(monkeypatch):
    calls = []
    original = httpx.AsyncClient

    def handler(request):
        calls.append(request.url.path)
        assert "PRIVATE_PROMPT" not in request.content.decode()
        return httpx.Response(
            200, json={"remote_model": "remote", "remote_host": "https://ollama.com"}
        )

    monkeypatch.setattr(
        assistant.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(ValueError, match="local model"):
        asyncio.run(
            assistant.generate("cloud-alias", [{"role": "user", "content": "PRIVATE_PROMPT"}])
        )
    assert calls == ["/api/show"]
