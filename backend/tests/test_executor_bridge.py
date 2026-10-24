"""Approval/audit to real Unix transport, controlled probes, no system mutations."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from app import executor_client
from app.actions import ActionEngine, ActionRequest, Approval, Simulation, fingerprint
from app.executor_client import VerificationClient, VerificationError
from app.executor_protocol import ExecutorPolicy
from app.executor_transport import VerificationServer
from app.services import ServiceError
from app.storage import StorageError, Store


@asynccontextmanager
async def integrated(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    store = Store(tmp_path / "state")
    store.initialize()
    allowed = {"owner", "other"}
    now = [0.0]
    snapshot = {"state": "active", "configuration_fingerprint": "config"}
    calls = []
    h = SimpleNamespace(store=store, allowed=allowed, now=now, snapshot=snapshot, calls=calls)

    async def local_probe(_):
        return dict(snapshot)

    async def remote_probe(request):
        # A start audit MUST precede every exchange with the remote policy.
        assert store.operations(50, 0)["items"][0]["status"] == "simulating"
        assert "actions.simulating" in {
            event["action"] for event in store.audit_events(50, 0)["items"]
        }
        calls.append(request.model_dump())
        return await h.probe(request)

    h.probe = local_probe
    policy = ExecutorPolicy(os.getuid(), frozenset({("service.restart", "fixture.service", None)}))
    server = VerificationServer(directory / "lab.sock", policy, remote_probe)
    await server.start()
    client = VerificationClient(server.path, os.getuid())
    engine = ActionEngine(
        store, local_probe, lambda owner: owner in allowed, clock=lambda: now[0], verifier=client
    )
    h.server, h.client, h.engine = server, client, engine
    h.request = ActionRequest(action="service.restart", target="fixture.service")
    try:
        async with asyncio.timeout(5):
            yield h
    finally:
        await engine.close()
        await server.close()


async def approved(h):
    plan = await h.engine.prepare("owner", h.request)
    approval = await h.engine.approve(
        "owner", Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True)
    )
    return plan, Simulation(plan_id=plan["id"], approval_token=approval["approval_token"])


def events(h):
    return [row["action"] for row in reversed(h.store.audit_events(50, 0)["items"])]


def test_approved_plan_is_bound_to_unix_verification_and_audit(tmp_path):
    async def run():
        async with integrated(tmp_path) as h:
            plan, approval = await approved(h)
            result = await h.engine.simulate("owner", approval)
            assert result["transport_verified"] is True
            assert result["commands_executed"] is False
            assert result["system_changed"] is False
            assert result["plan"]["mode"] == "simulation"
            assert result["plan"]["system_execution_enabled"] is False
            assert len(h.calls) == 2
            assert events(h) == [
                "actions.prepared",
                "actions.approved",
                "actions.simulating",
                "actions.transport_verified",
                "actions.simulated",
            ]
            audit = h.store.audit_events(50, 0)["items"]
            assert all(row["id"].startswith(plan["id"] + ":") for row in audit)
            serialized = json.dumps(audit) + json.dumps(h.store.operations(50, 0))
            assert "fixture.service" not in serialized and "owner" not in serialized
            assert approval.approval_token.encode() not in h.store.path.read_bytes()
            assert not h.server.policy.pending
            with pytest.raises(ServiceError):
                await h.engine.simulate("owner", approval)
            assert len(h.calls) == 2

    asyncio.run(run())


@pytest.mark.parametrize("invalid", ["approval", "owner", "missing_approval"])
def test_no_transport_before_approval_and_ownership_checks(tmp_path, invalid):
    async def run():
        async with integrated(tmp_path) as h:
            plan, approval = await approved(h)
            owner = "owner"
            if invalid == "approval":
                approval.approval_token = "x" * 43
            elif invalid == "owner":
                owner = "other"
            else:
                h.engine.plans[plan["id"]].approval_hash = None
            with pytest.raises(ServiceError):
                await h.engine.simulate(owner, approval)
            assert not h.calls
            assert not h.server.policy.reserved

    asyncio.run(run())


def test_start_audit_failure_prevents_transport(tmp_path, monkeypatch):
    async def run():
        async with integrated(tmp_path) as h:
            _, approval = await approved(h)
            original = h.store.action_transition

            def fail(operation, previous, status):
                if status == "simulating":
                    raise StorageError("fixture")
                return original(operation, previous, status)

            monkeypatch.setattr(h.store, "action_transition", fail)
            with pytest.raises(StorageError):
                await h.engine.simulate("owner", approval)
            assert not h.calls
            assert "actions.simulating" not in events(h)

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["verification", "final"])
def test_audit_failure_after_remote_verification_never_reports_success(
    tmp_path, monkeypatch, phase
):
    async def run():
        async with integrated(tmp_path) as h:
            plan, approval = await approved(h)
            original = h.store.action_transition

            def fail(*args):
                raise StorageError("fixture")

            if phase == "verification":
                monkeypatch.setattr(h.store, "action_verification", fail)
            else:

                def final(operation, previous, status):
                    if status == "simulated":
                        raise StorageError("fixture")
                    return original(operation, previous, status)

                monkeypatch.setattr(h.store, "action_transition", final)
            with pytest.raises(StorageError):
                await h.engine.simulate("owner", approval)
            assert len(h.calls) == 2
            assert h.engine.plans[plan["id"]].approval_hash is None
            assert h.store.operations(50, 0)["items"][0]["status"] == "simulating"
            assert "actions.simulated" not in events(h)
            assert ("actions.transport_verified" in events(h)) is (phase == "final")
            h.store.initialize()
            assert h.store.operations(50, 0)["items"][0]["status"] == "interrupted"

    asyncio.run(run())


@pytest.mark.parametrize("phase", [1, 2])
@pytest.mark.parametrize("cause", ["revoke", "expire"])
def test_session_and_expiry_rechecked_after_each_remote_read(tmp_path, phase, cause):
    async def run():
        async with integrated(tmp_path) as h:
            _, approval = await approved(h)

            async def change(_):
                if len(h.calls) == phase:
                    if cause == "revoke":
                        h.allowed.discard("owner")
                    else:
                        h.now[0] = 120
                return dict(h.snapshot)

            h.probe = change
            with pytest.raises(ServiceError) as exc:
                await h.engine.simulate("owner", approval)
            assert exc.value.code == ("SESSION_EXPIRED" if cause == "revoke" else "PLAN_EXPIRED")
            assert len(h.calls) == phase
            assert "actions.transport_verified" not in events(h)
            assert "actions.simulated" not in events(h)
            assert h.store.operations(50, 0)["items"][0]["status"] == (
                "failed" if cause == "revoke" else "expired"
            )

    asyncio.run(run())


@pytest.mark.parametrize("phase", [1, 2])
def test_remote_snapshot_must_match_approved_plan_on_both_reads(tmp_path, phase):
    async def run():
        async with integrated(tmp_path) as h:
            _, approval = await approved(h)

            async def change(_):
                return dict(h.snapshot) if len(h.calls) != phase else {"state": "changed"}

            h.probe = change
            with pytest.raises(VerificationError) as exc:
                await h.engine.simulate("owner", approval)
            assert "changed" not in str(exc.value)
            assert len(h.calls) == phase
            assert not h.server.policy.pending
            assert "actions.transport_verified" not in events(h)
            assert h.store.operations(50, 0)["items"][0]["status"] == "failed"

    asyncio.run(run())


def test_cancel_during_remote_probe_invalidates_approval(tmp_path):
    async def run():
        async with integrated(tmp_path) as h:
            plan, approval = await approved(h)
            entered = asyncio.Event()

            async def blocked(_):
                entered.set()
                await asyncio.Event().wait()

            h.probe = blocked
            task = asyncio.create_task(h.engine.simulate("owner", approval))
            await entered.wait()
            cancelled = await h.engine.cancel("owner", plan["id"])
            assert cancelled["status"] == "cancelled"
            with pytest.raises(ServiceError) as exc:
                await task
            assert exc.value.code == "ACTION_CANCELLED"
            assert "actions.transport_verified" not in events(h)
            assert len(h.calls) == 1

    asyncio.run(run())


def test_client_deadline_and_missing_socket_fail_closed(tmp_path, monkeypatch):
    async def run():
        async with integrated(tmp_path) as h:
            _, approval = await approved(h)

            async def blocked(_):
                await asyncio.Event().wait()

            h.probe = blocked
            monkeypatch.setattr(executor_client, "CLIENT_SECONDS", 0.03)
            with pytest.raises(VerificationError):
                await h.engine.simulate("owner", approval)
            assert "actions.transport_verified" not in events(h)
            h.client.path = h.server.path.parent / "missing.sock"
            _, approval = await approved(h)
            with pytest.raises(VerificationError):
                await h.engine.simulate("owner", approval)

    asyncio.run(run())


@pytest.mark.parametrize("change", ["socket_mode", "directory_mode", "uid", "symlink"])
def test_client_rejects_untrusted_socket_before_probe(tmp_path, change):
    async def run():
        async with integrated(tmp_path) as h:
            _, approval = await approved(h)
            if change == "socket_mode":
                h.server.path.chmod(0o666)
            elif change == "directory_mode":
                h.server.path.parent.chmod(0o755)
            elif change == "uid":
                h.client.server_uid += 1
            else:
                alias = h.server.path.parent / "alias.sock"
                alias.symlink_to(h.server.path)
                h.client.path = alias
            with pytest.raises(VerificationError):
                await h.engine.simulate("owner", approval)
            assert not h.calls

    asyncio.run(run())


def test_verification_audit_requires_current_simulating_state_and_rolls_back(tmp_path):
    store = Store(tmp_path / "state")
    store.initialize()
    operation = "a" * 32
    store.action_create(operation, "service.restart")
    with pytest.raises(StorageError):
        store.action_verification(operation)
    store.action_transition(operation, "prepared", "approved")
    store.action_transition(operation, "approved", "simulating")
    before = store.audit_events(50, 0)["total"]
    with store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_verify BEFORE INSERT ON audit_events WHEN NEW.action='actions.transport_verified' BEGIN SELECT RAISE(FAIL, 'fixture'); END"
        )
    with pytest.raises(StorageError):
        store.action_verification(operation)
    assert store.audit_events(50, 0)["total"] == before
    store.action_transition(operation, "simulating", "cancelled")
    with pytest.raises(StorageError):
        store.action_verification(operation)


@pytest.mark.parametrize("phase", ["issue", "verify"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("system_execution_enabled", True),
        ("system_execution_enabled", 0),
        ("operation_id", "c" * 32),
        ("fingerprint", "f" * 64),
        ("version", 1),
        ("status", "executed"),
        ("extra", "secret data"),
    ],
)
def test_client_rejects_mismatched_or_unsafe_server_replies(
    tmp_path, monkeypatch, phase, field, value
):
    async def run():
        async with integrated(tmp_path) as h:
            calls = []
            operation = "b" * 32
            expected = fingerprint(h.request, h.snapshot)

            async def fake(uid, frame):
                calls.append(frame["kind"])
                reply = {
                    "version": 2,
                    "operation_id": operation,
                    "fingerprint": expected,
                    "system_execution_enabled": False,
                    "status": "ticket_issued" if frame["kind"] == "issue" else "verified_only",
                }
                if frame["kind"] == "issue":
                    reply.update(ticket="a" * 64, expires_in_seconds=30)
                if frame["kind"] == phase:
                    reply[field] = value
                return reply

            monkeypatch.setattr(h.server, "_dispatch", fake)
            with pytest.raises(VerificationError) as exc:
                await h.client.verify(operation, h.request, expected, lambda: None)
            assert "secret" not in str(exc.value)
            assert calls == (["issue"] if phase == "issue" else ["issue", "verify"])

    asyncio.run(run())


@pytest.mark.parametrize(
    "field,value", [("ticket", "bad"), ("expires_in_seconds", 31), ("expires_in_seconds", True)]
)
def test_client_rejects_unbounded_or_invalid_tickets(tmp_path, monkeypatch, field, value):
    async def run():
        async with integrated(tmp_path) as h:
            expected = fingerprint(h.request, h.snapshot)

            async def fake(uid, frame):
                assert frame["kind"] == "issue"
                reply = {
                    "version": 2,
                    "operation_id": "b" * 32,
                    "fingerprint": expected,
                    "system_execution_enabled": False,
                    "status": "ticket_issued",
                    "ticket": "a" * 64,
                    "expires_in_seconds": 30,
                }
                reply[field] = value
                return reply

            monkeypatch.setattr(h.server, "_dispatch", fake)
            with pytest.raises(VerificationError):
                await h.client.verify("b" * 32, h.request, expected, lambda: None)

    asyncio.run(run())


def test_client_checks_kernel_server_uid_after_connection(tmp_path, monkeypatch):
    async def run():
        async with integrated(tmp_path) as h:
            _, approval = await approved(h)
            monkeypatch.setattr(executor_client, "peer_uid", lambda _: os.getuid() + 1)
            with pytest.raises(VerificationError):
                await h.engine.simulate("owner", approval)
            assert not h.calls

    asyncio.run(run())


@pytest.mark.parametrize("cause", ["revoke", "expire"])
def test_checkpoint_after_verification_audit_prevents_success(tmp_path, monkeypatch, cause):
    async def run():
        async with integrated(tmp_path) as h:
            _, approval = await approved(h)
            original = h.store.action_verification

            def interrupt(operation):
                original(operation)
                if cause == "revoke":
                    h.allowed.discard("owner")
                else:
                    h.now[0] = 120

            monkeypatch.setattr(h.store, "action_verification", interrupt)
            with pytest.raises(ServiceError) as exc:
                await h.engine.simulate("owner", approval)
            assert exc.value.code == ("SESSION_EXPIRED" if cause == "revoke" else "PLAN_EXPIRED")
            assert "actions.transport_verified" in events(h)
            assert "actions.simulated" not in events(h)

    asyncio.run(run())
