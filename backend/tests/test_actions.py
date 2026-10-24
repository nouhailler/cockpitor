import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from app.actions import ActionEngine, ActionRequest, Approval, Simulation
from app.containers import Containers
from app.services import ServiceError, Services
from app.storage import StorageError, Store
from app.system import timestamp
from pydantic import ValidationError
from test_api import wait_settings

pytest_plugins = ["test_api"]


@pytest.fixture
def harness(tmp_path):
    store = Store(tmp_path / "state")
    store.initialize()
    now = [0.0]
    allowed = {"owner", "other"}
    snapshot = {
        "Id": "cron.service",
        "ActiveState": "active",
        "configuration_fingerprint": "config-one",
    }
    calls = []

    async def probe(request):
        calls.append(request.action)
        return dict(snapshot)

    engine = ActionEngine(store, probe, lambda owner: owner in allowed, clock=lambda: now[0])
    return SimpleNamespace(
        store=store, engine=engine, now=now, allowed=allowed, snapshot=snapshot, calls=calls
    )


def request():
    return ActionRequest(action="service.restart", target="cron.service")


async def approved(harness, owner="owner"):
    plan = await harness.engine.prepare(owner, request())
    approval = await harness.engine.approve(
        owner, Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True)
    )
    return plan, Simulation(plan_id=plan["id"], approval_token=approval["approval_token"])


def test_lifecycle_consumes_approval_and_persists_only_minimal_audit(harness):
    async def scenario():
        plan, token = await approved(harness)
        result = await harness.engine.simulate("owner", token)
        assert result["plan"]["status"] == "simulated"
        assert result["commands_executed"] is False and result["system_changed"] is False
        assert result["transport_verified"] is False
        assert harness.engine.verifier is None
        assert harness.calls == ["service.restart"] * 4
        with pytest.raises(ServiceError) as exc:
            await harness.engine.simulate("owner", token)
        assert exc.value.code == "APPROVAL_REQUIRED"
        operations = harness.store.operations(50, 0)["items"]
        assert operations[0]["status"] == "simulated"
        audit = harness.store.audit_events(50, 0)
        assert {row["action"] for row in audit["items"]} == {
            "actions.prepared",
            "actions.approved",
            "actions.simulating",
            "actions.simulated",
        }
        assert "cron.service" not in json.dumps(operations)
        assert "owner" not in json.dumps(audit)
        assert token.approval_token.encode() not in harness.store.path.read_bytes()
        assert not harness.engine.plans[plan["id"]].approval_hash

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "service.restart", "target": "--help.service"},
        {"action": "service.stop", "target": "../../cron.service"},
        {"action": "service.restart", "target": "cron.service; reboot"},
        {"action": "service.restart", "target": "cron.service\n"},
        {"action": "service.restart", "target": "ssh.service"},
        {"action": "service.restart", "target": "systemd-logind.service"},
        {"action": "service.restart", "target": "cron.service", "command": "sudo reboot"},
        {"action": "service.restart", "target": "cron.service", "engine": "docker"},
        {"action": "container.restart", "target": "container-name", "engine": "docker"},
        {"action": "container.restart", "target": "a" * 64, "engine": "shell"},
        {"action": "container.restart", "target": "a" * 64},
        {"action": "shell", "target": "reboot"},
        {"action": "service.restart", "target": "cron.service", "mode": "execute"},
    ],
)
def test_request_schema_refuses_injection_critical_targets_and_extra_capabilities(payload):
    with pytest.raises((ValidationError, ServiceError)):
        ActionRequest.model_validate(payload)


@pytest.mark.parametrize("confirmed", [False, 1, "true", None])
def test_confirmation_requires_strict_boolean_true(confirmed):
    with pytest.raises(ValidationError):
        Approval.model_validate(
            {"plan_id": "a" * 32, "fingerprint": "a" * 64, "confirmed": confirmed}
        )


def test_cross_session_forgery_unknown_plan_and_fingerprint_mismatch(harness):
    async def scenario():
        plan = await harness.engine.prepare("owner", request())
        with pytest.raises(ServiceError) as exc:
            await harness.engine.approve(
                "other",
                Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True),
            )
        assert exc.value.status == 404
        with pytest.raises(ServiceError) as exc:
            await harness.engine.approve(
                "owner", Approval(plan_id=plan["id"], fingerprint="0" * 64, confirmed=True)
            )
        assert exc.value.code == "PLAN_MISMATCH"
        token = await harness.engine.approve(
            "owner", Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True)
        )
        with pytest.raises(ServiceError) as exc:
            await harness.engine.simulate(
                "owner", Simulation(plan_id=plan["id"], approval_token="x" * 43)
            )
        assert exc.value.code == "APPROVAL_INVALID"
        with pytest.raises(ServiceError):
            await harness.engine.simulate(
                "other", Simulation(plan_id=plan["id"], approval_token=token["approval_token"])
            )
        assert harness.engine.plans[plan["id"]].status == "approved"

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["approve", "simulate"])
def test_changed_target_or_configuration_invalidates_plan(harness, phase):
    async def scenario():
        if phase == "approve":
            plan = await harness.engine.prepare("owner", request())
        else:
            plan, token = await approved(harness)
        harness.snapshot["configuration_fingerprint"] = "changed-secret-config"
        with pytest.raises(ServiceError) as exc:
            if phase == "approve":
                await harness.engine.approve(
                    "owner",
                    Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True),
                )
            else:
                await harness.engine.simulate("owner", token)
        assert exc.value.code == "TARGET_CHANGED"
        assert harness.store.operations(50, 0)["items"][0]["status"] == "rejected"

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["prepared", "approved"])
def test_expiry_is_checked_server_side(harness, phase):
    async def scenario():
        if phase == "prepared":
            plan = await harness.engine.prepare("owner", request())
            harness.now[0] = 120
            call = harness.engine.approve(
                "owner",
                Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True),
            )
        else:
            plan, token = await approved(harness)
            harness.now[0] = 60
            call = harness.engine.simulate("owner", token)
        with pytest.raises(ServiceError) as exc:
            await call
        assert exc.value.code == "PLAN_EXPIRED"
        assert harness.engine.plans[plan["id"]].status == "expired"

    asyncio.run(scenario())


def test_expired_or_revoked_session_cannot_simulate_and_cleanup_expires(harness):
    async def scenario():
        plan, token = await approved(harness)
        harness.allowed.remove("owner")
        with pytest.raises(ServiceError) as exc:
            await harness.engine.simulate("owner", token)
        assert exc.value.status == 401
        await harness.engine.cleanup()
        assert harness.engine.plans[plan["id"]].status == "expired"

    asyncio.run(scenario())


def test_audit_failure_before_approval_is_fail_closed(harness, monkeypatch):
    async def scenario():
        plan = await harness.engine.prepare("owner", request())

        def denied(*args):
            raise StorageError("unavailable")

        monkeypatch.setattr(harness.store, "action_transition", denied)
        with pytest.raises(StorageError):
            await harness.engine.approve(
                "owner",
                Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True),
            )
        assert harness.engine.plans[plan["id"]].approval_hash is None
        assert harness.engine.plans[plan["id"]].status == "prepared"

    asyncio.run(scenario())


def test_final_audit_failure_does_not_report_success_and_restart_interrupts(harness, monkeypatch):
    original = harness.store.action_transition

    async def scenario():
        _, token = await approved(harness)

        def denied(op, old, status):
            if status == "simulated":
                raise StorageError("disk full")
            original(op, old, status)

        monkeypatch.setattr(harness.store, "action_transition", denied)
        with pytest.raises(StorageError):
            await harness.engine.simulate("owner", token)
        assert harness.engine.running is None
        assert harness.store.operations(50, 0)["items"][0]["status"] == "simulating"
        Store(harness.store.directory).initialize()
        assert harness.store.operations(50, 0)["items"][0]["status"] == "interrupted"

    asyncio.run(scenario())


def test_replay_concurrency_and_cancellation(harness):
    async def scenario():
        plan, token = await approved(harness)
        second, other_token = await approved(harness)
        entered, release = asyncio.Event(), asyncio.Event()
        original = harness.engine.probe
        calls = [0]

        async def pending(req):
            calls[0] += 1
            if calls[0] == 2:
                entered.set()
                await release.wait()
            return await original(req)

        harness.engine.probe = pending
        task = asyncio.create_task(harness.engine.simulate("owner", token))
        await entered.wait()
        with pytest.raises(ServiceError) as exc:
            await harness.engine.simulate("owner", other_token)
        assert exc.value.code == "ACTION_BUSY"
        result = await harness.engine.cancel("owner", plan["id"])
        assert result["status"] == "cancelled"
        with pytest.raises(ServiceError) as exc:
            await task
        assert exc.value.code == "ACTION_CANCELLED"
        assert harness.engine.running is None
        assert harness.engine.plans[second["id"]].approval_hash

    asyncio.run(scenario())


def test_database_recovers_pending_plans_without_reusing_approval(harness):
    async def scenario():
        plan, token = await approved(harness)
        Store(harness.store.directory).initialize()
        assert harness.store.operations(50, 0)["items"][0]["status"] == "interrupted"
        with pytest.raises(StorageError):
            await harness.engine.simulate("owner", token)
        assert harness.engine.plans[plan["id"]].task is None

    asyncio.run(scenario())


def test_simulation_timeout_is_bounded(harness, monkeypatch):
    async def scenario():
        _, token = await approved(harness)
        original = harness.engine.probe
        calls = [0]

        async def pending(req):
            calls[0] += 1
            if calls[0] == 2:
                await asyncio.Event().wait()
            return await original(req)

        harness.engine.probe = pending
        monkeypatch.setattr("app.actions.SIMULATION_SECONDS", 0.02)
        with pytest.raises(ServiceError) as exc:
            await harness.engine.simulate("owner", token)
        assert exc.value.code == "ACTION_TIMEOUT"
        assert harness.store.operations(50, 0)["items"][0]["status"] == "failed"
        assert harness.engine.running is None

    asyncio.run(scenario())


def test_service_configuration_hash_hides_commands_and_detects_changes(monkeypatch):
    secret = ["PRIVATE_PASSWORD"]

    async def command(self, *args):
        assert args[0:2] == ("/usr/bin/systemctl", "show") and args[-2:] == ("--", "cron.service")
        return (
            "Id=cron.service\nLoadState=loaded\nNeedDaemonReload=no\nActiveState=active\nExecStart="
            + secret[0],
            "",
        )

    monkeypatch.setattr(Services, "command", command)

    async def scenario():
        adapter = Services()
        first = await adapter.action_snapshot("cron.service", b"test-key")
        assert "PRIVATE" not in json.dumps(first)
        secret[0] = "CHANGED_PASSWORD"
        second = await adapter.action_snapshot("cron.service", b"test-key")
        assert first["configuration_fingerprint"] != second["configuration_fingerprint"]

    asyncio.run(scenario())


@pytest.fixture
def action_client(client, monkeypatch):
    wait_settings(client)
    client.app.state.services = {
        "status": "available",
        "collected_at": timestamp(),
        "items": [{"unit": "cron.service"}],
    }

    async def snapshot(self, unit, key):
        return {"Id": unit, "ActiveState": "active", "configuration_fingerprint": "configuration"}

    monkeypatch.setattr(Services, "action_snapshot", snapshot)
    return client


def headers(client):
    return {"origin": "http://127.0.0.1:8765", "x-localcockpit-csrf": client.app.state.csrf}


def test_api_full_simulation_and_no_system_execution(action_client):
    c = action_client
    safe = headers(c)
    assert c.get("/api/v1/action-plans/options").json()["system_execution_enabled"] is False
    plan = c.post("/api/v1/action-plans/prepare", json=request().model_dump(), headers=safe).json()
    assert plan["mode"] == "simulation"
    approval = c.post(
        "/api/v1/action-plans/approve",
        json={"plan_id": plan["id"], "fingerprint": plan["fingerprint"], "confirmed": True},
        headers=safe,
    ).json()
    assert "approval_token" not in json.dumps(c.get("/api/v1/action-plans").json())
    result = c.post(
        "/api/v1/action-plans/simulate",
        json={"plan_id": plan["id"], "approval_token": approval["approval_token"]},
        headers=safe,
    )
    assert result.status_code == 200 and result.json()["system_changed"] is False
    assert c.get("/api/v1/operations").json()["items"][0]["status"] == "simulated"
    for path in [
        "/api/v1/action-plans/execute",
        "/api/v1/actions/run",
        "/api/v1/services/cron.service/restart",
    ]:
        assert c.post(path, json={}, headers=safe).status_code == 405


def test_api_auth_csrf_size_schema_inventory_and_storage(action_client):
    c = action_client
    path = "/api/v1/action-plans/prepare"
    payload = request().model_dump()
    assert c.post(path, json=payload).status_code == 403
    assert (
        c.post(path, json=payload, headers={**headers(c), "authorization": ""}).status_code == 401
    )
    assert (
        c.post(
            path, json=payload, headers={**headers(c), "origin": "http://evil.example"}
        ).status_code
        == 403
    )
    assert (
        c.post(
            path, content="x" * 2049, headers={**headers(c), "content-type": "application/json"}
        ).status_code
        == 413
    )
    assert (
        c.post(path, json={**payload, "command": "reboot"}, headers=headers(c)).status_code == 422
    )
    assert (
        c.post(path, json={**payload, "target": "unknown.service"}, headers=headers(c)).status_code
        == 422
    )
    c.app.state.services["collected_at"] = "2020-01-01T00:00:00Z"
    assert c.post(path, json=payload, headers=headers(c)).status_code == 503
    c.app.state.storage_ready = False
    assert c.post(path, json=payload, headers=headers(c)).status_code == 503
    assert c.get("/api/v1/health").status_code == 200


def test_v2_migration_is_backed_up_and_recovery_is_audited(tmp_path):
    store = Store(tmp_path / "state")
    store.initialize()
    with store.connection() as db:
        db.execute("DROP TABLE action_operations")
        db.execute("PRAGMA user_version=2")
    store.initialize()
    backup = next(store.directory.glob("backup-*.sqlite3"))
    with sqlite3.connect(backup) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    store.action_create("id", "service.restart")
    store.initialize()
    assert store.operations(50, 0)["items"][0]["status"] == "interrupted"
    assert any(row["action"] == "actions.interrupted" for row in store.audit_events(50, 0)["items"])


def test_audit_sql_failure_rolls_back_state_and_prevents_approval(harness):
    async def scenario():
        plan = await harness.engine.prepare("owner", request())
        with harness.store.connection() as db:
            db.execute(
                "CREATE TRIGGER deny_approval BEFORE INSERT ON audit_events WHEN NEW.action='actions.approved' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"
            )
        with pytest.raises(StorageError):
            await harness.engine.approve(
                "owner",
                Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True),
            )
        assert harness.store.operations(50, 0)["items"][0]["status"] == "prepared"
        assert not harness.engine.plans[plan["id"]].approval_hash
        assert not any(
            row["action"] == "actions.approved"
            for row in harness.store.audit_events(50, 0)["items"]
        )

    asyncio.run(scenario())


def test_expiry_during_preflight_is_rechecked(harness):
    async def scenario():
        plan = await harness.engine.prepare("owner", request())
        original = harness.engine.probe

        async def delayed(req):
            harness.now[0] = 121
            return await original(req)

        harness.engine.probe = delayed
        with pytest.raises(ServiceError) as exc:
            await harness.engine.approve(
                "owner",
                Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True),
            )
        assert exc.value.code == "PLAN_EXPIRED"
        assert not harness.engine.plans[plan["id"]].approval_hash

    asyncio.run(scenario())


def test_pending_plan_limit_and_cleanup(harness):
    async def scenario():
        for _ in range(64):
            await harness.engine.prepare("owner", request())
        with pytest.raises(ServiceError) as exc:
            await harness.engine.prepare("owner", request())
        assert exc.value.code == "PLAN_LIMIT"
        harness.now[0] = 121
        await harness.engine.cleanup()
        await harness.engine.prepare("owner", request())
        assert len(harness.engine.plans) == 1

    asyncio.run(scenario())


def test_no_environment_switch_can_enable_system_execution(action_client, monkeypatch):
    monkeypatch.setenv("LOCALCOCKPIT_ACTIONS_ENABLED", "1")
    assert (
        action_client.get("/api/v1/action-plans/options").json()["system_execution_enabled"]
        is False
    )
    assert (
        action_client.post(
            "/api/v1/action-plans/execute", json={}, headers=headers(action_client)
        ).status_code
        == 405
    )


def test_cancel_does_not_claim_success_if_final_audit_is_unavailable(harness, monkeypatch):
    async def scenario():
        plan, token = await approved(harness)
        entered = asyncio.Event()
        calls = [0]
        original_probe = harness.engine.probe
        original_transition = harness.store.action_transition

        async def pending(req):
            calls[0] += 1
            if calls[0] == 2:
                entered.set()
                await asyncio.Event().wait()
            return await original_probe(req)

        def denied(op, previous, status):
            if status == "cancelled":
                raise StorageError("audit unavailable")
            original_transition(op, previous, status)

        harness.engine.probe = pending
        monkeypatch.setattr(harness.store, "action_transition", denied)
        running = asyncio.create_task(harness.engine.simulate("owner", token))
        await entered.wait()
        with pytest.raises(StorageError):
            await harness.engine.cancel("owner", plan["id"])
        with pytest.raises(StorageError):
            await running
        assert harness.store.operations(50, 0)["items"][0]["status"] == "simulating"
        assert harness.engine.running is None

    asyncio.run(scenario())


def test_container_preflight_uses_only_get_and_hides_configuration_secrets(monkeypatch):
    cid = "a" * 64
    data = {
        "Id": cid,
        "Name": "/example",
        "Created": "2026-10-24",
        "State": {"Status": "running", "Running": True},
        "Config": {"Image": "image", "Tty": False, "Env": ["password=PRIVATE_SECRET"]},
        "HostConfig": {"Privileged": False},
        "Mounts": [],
    }
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json=data)

    @asynccontextmanager
    async def connection(self, engine, container_id):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield client, "http://localhost/containers/" + container_id

    monkeypatch.setattr(Containers, "connection", connection)

    async def scenario():
        adapter = Containers()
        first = await adapter.action_snapshot("docker", cid, b"private-key")
        assert "PRIVATE_SECRET" not in json.dumps(first)
        data["Config"]["Env"] = ["password=CHANGED_SECRET"]
        second = await adapter.action_snapshot("docker", cid, b"private-key")
        assert first["configuration_fingerprint"] != second["configuration_fingerprint"]
        assert calls == ["GET", "GET"]
        data["Id"] = "b" * 64
        with pytest.raises(ValueError, match="identity"):
            await adapter.action_snapshot("docker", cid, b"private-key")

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "exception", [RuntimeError("PRIVATE_ERROR"), ServiceError("READ_DENIED", "read refused", 403)]
)
def test_failed_read_is_audited_without_reporting_success(harness, exception):
    async def scenario():
        _, token = await approved(harness)
        original = harness.engine.probe
        calls = [0]

        async def failed(req):
            calls[0] += 1
            if calls[0] == 2:
                raise exception
            return await original(req)

        harness.engine.probe = failed
        with pytest.raises(ServiceError) as exc:
            await harness.engine.simulate("owner", token)
        assert "PRIVATE_ERROR" not in exc.value.message
        assert harness.store.operations(50, 0)["items"][0]["status"] == "failed"
        assert harness.engine.running is None

    asyncio.run(scenario())
