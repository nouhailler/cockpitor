"""Authoritative session invalidation in the Unix lab, never system execution."""

import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from app.actions import ActionEngine, ActionRequest, Approval, Simulation
from app.auth import ABSOLUTE_SECONDS, IDLE_SECONDS, Sessions
from app.executor_client import VerificationClient, VerificationError
from app.executor_protocol import ExecutorPolicy
from app.executor_transport import VerificationServer
from app.session_verification import SessionVerificationServer
from app.storage import Store
from test_executor_transport import exchange, issue_frame, verify_frame


@asynccontextmanager
async def scoped_lab(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    now = [0.0]
    sessions = Sessions("bootstrap", clock=lambda: now[0])
    first, _ = sessions.login("bootstrap")
    second, _ = sessions.login("bootstrap")
    owner, other = sessions.digest(first), sessions.digest(second)
    state = {"state": "active", "configuration_fingerprint": "a" * 64}
    calls = []

    async def probe(request):
        calls.append(request.target)
        return dict(state)

    policy = ExecutorPolicy(os.getuid(), frozenset({("service.restart", "fixture.service", None)}))
    server = SessionVerificationServer(private / "scoped.sock", policy, probe, sessions=sessions)
    await server.start()
    h = SimpleNamespace(
        server=server,
        sessions=sessions,
        first=first,
        second=second,
        owner=owner,
        other=other,
        now=now,
        calls=calls,
        state=state,
    )
    try:
        async with asyncio.timeout(5):
            yield h
    finally:
        await server.close()


def scoped_issue(owner, operation="b" * 32):
    return {**issue_frame(operation), "session_scope": owner}


async def wait_revoked(h, identifier):
    async with asyncio.timeout(0.5):
        while identifier not in h.server.policy.revoked:
            await asyncio.sleep(0.005)


def test_one_session_revocation_invalidates_all_its_tickets_only(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            first = await exchange(h.server, scoped_issue(h.owner))
            await exchange(h.server, scoped_issue(h.owner, "c" * 32))
            other = await exchange(h.server, scoped_issue(h.other, "d" * 32))
            h.sessions.revoke(h.first)
            await wait_revoked(h, "b" * 32)
            assert "c" * 32 in h.server.policy.revoked
            assert "d" * 32 in h.server.policy.pending
            assert (await exchange(h.server, verify_frame(first["ticket"])))["status"] == "rejected"
            assert (await exchange(h.server, verify_frame(other["ticket"], "d" * 32)))[
                "status"
            ] == "verified_only"
            assert h.calls == ["fixture.service"] * 4

    asyncio.run(run())


def test_lost_issue_reply_needs_no_ticket_or_request_from_client_for_revocation(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            await exchange(h.server, scoped_issue(h.owner))  # Deliberately discard the secret.
            h.sessions.revoke(h.first)
            await wait_revoked(h, "b" * 32)
            assert not h.server.policy.pending and len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize("expiry", ["idle", "absolute"])
def test_expiration_invalidates_without_any_client_message(tmp_path, expiry):
    async def run():
        async with scoped_lab(tmp_path) as h:
            await exchange(h.server, scoped_issue(h.owner))
            if expiry == "absolute":
                h.now[0] = ABSOLUTE_SECONDS - 1
                with h.sessions.lock:
                    h.sessions.sessions[h.owner].touched = h.now[0]
                h.now[0] = ABSOLUTE_SECONDS
            else:
                h.now[0] = IDLE_SECONDS
            await wait_revoked(h, "b" * 32)
            assert not h.server.policy.pending

    asyncio.run(run())


def test_revocation_during_verification_blocks_final_validation(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            issued = await exchange(h.server, scoped_issue(h.owner))
            entered, release = asyncio.Event(), asyncio.Event()

            async def probe(_):
                entered.set()
                await release.wait()
                return dict(h.state)

            h.server.probe = probe
            task = asyncio.create_task(exchange(h.server, verify_frame(issued["ticket"])))
            try:
                await entered.wait()
                h.sessions.revoke(h.first)
                await wait_revoked(h, "b" * 32)
                assert not task.done()
                release.set()
                assert (await task)["status"] == "rejected"
                assert not h.server.policy.claimed
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


def test_revocation_during_issue_never_allocates_a_ticket(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:

            async def revoke(_):
                h.sessions.revoke(h.first)
                return dict(h.state)

            h.server.probe = revoke
            assert (await exchange(h.server, scoped_issue(h.owner)))["status"] == "rejected"
            assert not h.server.policy.reserved and not h.server.operation_scopes

    asyncio.run(run())


@pytest.mark.parametrize("scope", [None, "0" * 64, "bootstrap", True])
def test_missing_unknown_or_malformed_scope_never_probes(tmp_path, scope):
    async def run():
        async with scoped_lab(tmp_path) as h:
            frame = issue_frame()
            if scope is not None:
                frame["session_scope"] = scope
            assert (await exchange(h.server, frame))["status"] == "rejected"
            assert not h.calls and not h.server.operation_scopes

    asyncio.run(run())


def test_unavailable_authority_fails_closed_and_revokes_all_sessions(tmp_path, monkeypatch):
    async def run():
        async with scoped_lab(tmp_path) as h:
            await exchange(h.server, scoped_issue(h.owner))
            await exchange(h.server, scoped_issue(h.other, "c" * 32))

            def fail(_):
                raise RuntimeError("secret authority error")

            monkeypatch.setattr(h.sessions, "valid_owner", fail)
            await wait_revoked(h, "b" * 32)
            assert "c" * 32 in h.server.policy.revoked
            reply = await exchange(h.server, scoped_issue(h.owner, "d" * 32))
            assert reply == {"status": "rejected", "system_execution_enabled": False}

    asyncio.run(run())


def test_monitor_is_closed_and_scopes_are_not_persisted(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            await exchange(h.server, scoped_issue(h.owner))
            monitor = h.server.monitor
        assert monitor.done() and h.server.monitor is None
        assert not h.server.operation_scopes
        assert not h.server.policy.pending

    asyncio.run(run())


def test_scope_cannot_be_rebound_on_verify_and_bad_frame_does_not_burn_ticket(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            issued = await exchange(h.server, scoped_issue(h.owner))
            bad = {**verify_frame(issued["ticket"]), "session_scope": h.other}
            assert (await exchange(h.server, bad))["status"] == "rejected"
            assert (await exchange(h.server, verify_frame(issued["ticket"])))[
                "status"
            ] == "verified_only"

    asyncio.run(run())


def test_scoped_client_with_real_action_engine_and_audit(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            store = Store(tmp_path / "store")
            store.initialize()

            async def local_probe(_):
                return dict(h.state)

            client = VerificationClient(h.server.path, os.getuid(), session_scope=h.owner)
            engine = ActionEngine(store, local_probe, h.sessions.valid_owner, verifier=client)
            try:
                plan = await engine.prepare(
                    h.owner, ActionRequest(action="service.restart", target="fixture.service")
                )
                approval = await engine.approve(
                    h.owner,
                    Approval(plan_id=plan["id"], fingerprint=plan["fingerprint"], confirmed=True),
                )
                result = await engine.simulate(
                    h.owner,
                    Simulation(plan_id=plan["id"], approval_token=approval["approval_token"]),
                )
                assert result["transport_verified"] is True
                assert result["system_changed"] is False and result["commands_executed"] is False
                events = store.audit_events(50, 0)["items"]
                assert any(event["action"] == "actions.transport_verified" for event in events)
                assert h.owner not in str(events) and h.first not in str(events)
            finally:
                await engine.close()

    asyncio.run(run())


def test_scoped_client_cannot_silently_downgrade_to_unscoped_server(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            plain = VerificationServer(
                h.server.path.parent / "plain.sock",
                ExecutorPolicy(
                    os.getuid(), frozenset({("service.restart", "fixture.service", None)})
                ),
                h.server.probe,
            )
            await plain.start()
            try:
                client = VerificationClient(plain.path, os.getuid(), session_scope=h.owner)
                with pytest.raises(VerificationError):
                    await client.verify(
                        "b" * 32,
                        ActionRequest(action="service.restart", target="fixture.service"),
                        issue_frame()["expected_fingerprint"],
                        lambda: None,
                    )
                assert not plain.policy.reserved
            finally:
                await plain.close()

    asyncio.run(run())


def test_issue_cannot_rebind_an_existing_operation_to_another_session(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            await exchange(h.server, scoped_issue(h.owner))
            assert (await exchange(h.server, scoped_issue(h.other)))["status"] == "rejected"
            assert h.server.operation_scopes["b" * 32] == h.owner
            h.sessions.revoke(h.first)
            await wait_revoked(h, "b" * 32)

    asyncio.run(run())


def test_authority_revocation_works_with_no_connection_slot_available(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            await exchange(h.server, scoped_issue(h.owner))
            connections = []
            try:
                for _ in range(4):
                    connections.append(await asyncio.open_unix_connection(h.server.path))
                async with asyncio.timeout(0.5):
                    while len(h.server.tasks) < 4:
                        await asyncio.sleep(0.005)
                h.sessions.revoke(h.first)
                await wait_revoked(h, "b" * 32)
                assert not h.server.policy.pending
                assert len(h.calls) == 1
            finally:
                for _, writer in connections:
                    writer.close()
                    await writer.wait_closed()

    asyncio.run(run())


@pytest.mark.parametrize("scope", ["owner", True, "a" * 63])
def test_client_rejects_invalid_scope_before_connection(tmp_path, scope):
    with pytest.raises(ValueError):
        VerificationClient(tmp_path / "missing.sock", os.getuid(), session_scope=scope)


def test_client_rejects_action_engine_owner_mismatch_before_transport(tmp_path):
    async def run():
        async with scoped_lab(tmp_path) as h:
            client = VerificationClient(h.server.path, os.getuid(), session_scope=h.owner)
            with pytest.raises(VerificationError):
                await client.verify(
                    "b" * 32,
                    ActionRequest(action="service.restart", target="fixture.service"),
                    issue_frame()["expected_fingerprint"],
                    lambda: None,
                    owner=h.other,
                )
            assert not h.calls and not h.server.operation_scopes

    asyncio.run(run())
