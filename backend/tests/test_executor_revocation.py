"""Ticket revocation only: controlled probes and real private Unix sockets."""

import asyncio
import json
import os

import pytest
from app.actions import ActionRequest, fingerprint
from app.executor_client import VerificationClient, VerificationError
from app.executor_protocol import ExecutorPolicy, ProtocolRejected
from test_executor_transport import exchange, issue_frame, lab, verify_frame


def policy_ticket():
    policy = ExecutorPolicy(1000, frozenset({("service.restart", "fixture.service", None)}))
    request = ActionRequest(action="service.restart", target="fixture.service")
    snapshot = {"state": "active"}
    ticket = policy.issue(1000, "b" * 32, request, snapshot)
    frame = json.dumps({"version": 1, "operation_id": "b" * 32, "ticket": ticket}).encode()
    return policy, request, snapshot, frame


def test_pending_revocation_is_idempotent_and_id_remains_reserved():
    policy, request, snapshot, frame = policy_ticket()
    first = policy.revoke(1000, frame)
    assert policy.revoke(1000, frame) == first
    assert not policy.pending and not policy.claimed
    assert len(policy.revoked) == 1
    with pytest.raises(ProtocolRejected):
        policy.consume(1000, frame, snapshot)
    with pytest.raises(ProtocolRejected):
        policy.issue(1000, "b" * 32, request, snapshot)


@pytest.mark.parametrize("uid", [0, 1001, True, "1000"])
def test_foreign_peer_cannot_revoke(uid):
    policy, _, snapshot, frame = policy_ticket()
    with pytest.raises(ProtocolRejected):
        policy.revoke(uid, frame)
    assert policy.consume(1000, frame, snapshot)


def test_bad_revoke_secret_does_not_burn_valid_ticket():
    policy, _, snapshot, frame = policy_ticket()
    payload = json.loads(frame)
    payload["ticket"] = "0" * 64
    with pytest.raises(ProtocolRejected):
        policy.revoke(1000, json.dumps(payload).encode())
    assert policy.consume(1000, frame, snapshot)


def test_revocation_invalidates_already_claimed_snapshot():
    policy, _, snapshot, frame = policy_ticket()
    claimed = policy.claim(1000, frame)
    policy.revoke(1000, frame)
    with pytest.raises(ProtocolRejected):
        policy.verify_snapshot(claimed, snapshot)
    assert not policy.claimed


def test_a_claimed_snapshot_can_be_verified_only_once():
    policy, _, snapshot, frame = policy_ticket()
    claimed = policy.claim(1000, frame)
    policy.verify_snapshot(claimed, snapshot)
    with pytest.raises(ProtocolRejected):
        policy.verify_snapshot(claimed, snapshot)
    with pytest.raises(ProtocolRejected):
        policy.revoke(1000, frame)  # A completed verification cannot be undone.


def test_close_clears_revocation_records():
    policy, _, _, frame = policy_ticket()
    policy.revoke(1000, frame)
    policy.invalidate()
    assert not policy.pending and not policy.claimed and not policy.revoked
    with pytest.raises(ProtocolRejected):
        policy.revoke(1000, frame)


def revoke_frame(ticket):
    return {**verify_frame(ticket), "kind": "revoke"}


def test_wire_revoke_prevents_verification_without_another_probe(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, calls, _):
            ticket = (await exchange(server, issue_frame()))["ticket"]
            reply = await exchange(server, revoke_frame(ticket))
            assert reply["status"] == "revoked"
            assert (await exchange(server, revoke_frame(ticket))) == reply
            assert (await exchange(server, verify_frame(ticket)))["status"] == "rejected"
            assert len(calls) == 1

    asyncio.run(run())


def test_wire_revoke_does_not_wait_for_inflight_probe(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, _, snapshot):
            ticket = (await exchange(server, issue_frame()))["ticket"]
            entered, release = asyncio.Event(), asyncio.Event()

            async def blocked(_):
                entered.set()
                await release.wait()
                return dict(snapshot)

            server.probe = blocked
            verification = asyncio.create_task(exchange(server, verify_frame(ticket)))
            try:
                await entered.wait()
                async with asyncio.timeout(0.5):
                    reply = await exchange(server, revoke_frame(ticket))
                assert reply["status"] == "revoked"
                assert not verification.done()
                release.set()
                assert (await verification)["status"] == "rejected"
                assert not server.policy.claimed
            finally:
                release.set()
                await asyncio.gather(verification, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize("change", ["ticket", "version", "extra"])
def test_invalid_wire_revocation_leaves_ticket_valid(tmp_path, change):
    async def run():
        async with lab(tmp_path) as (server, _, _):
            ticket = (await exchange(server, issue_frame()))["ticket"]
            frame = revoke_frame(ticket)
            if change == "ticket":
                frame["ticket"] = "0" * 64
            elif change == "version":
                frame["version"] = 1
            else:
                frame["peer_uid"] = os.getuid()
            assert (await exchange(server, frame))["status"] == "rejected"
            assert (await exchange(server, verify_frame(ticket)))["status"] == "verified_only"

    asyncio.run(run())


def test_client_can_revoke_and_requires_confirmed_reply(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, _, _):
            issued = await exchange(server, issue_frame())
            client = VerificationClient(server.path, os.getuid())
            await client.revoke("b" * 32, issued["ticket"], issued["fingerprint"])
            with pytest.raises(VerificationError):
                await client.revoke("b" * 32, issued["ticket"], "f" * 64)
            assert (await exchange(server, verify_frame(issued["ticket"])))["status"] == "rejected"

    asyncio.run(run())


def test_client_revokes_received_ticket_when_session_checkpoint_fails(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, _, snapshot):
            client = VerificationClient(server.path, os.getuid())
            request = ActionRequest(action="service.restart", target="fixture.service")

            def checkpoint():
                if server.policy.pending:
                    raise RuntimeError("session revoked")

            with pytest.raises(RuntimeError, match="session revoked"):
                await client.verify("b" * 32, request, fingerprint(request, snapshot), checkpoint)
            assert not server.policy.pending
            assert "b" * 32 in server.policy.revoked

    asyncio.run(run())


def test_cancelled_client_revokes_claimed_ticket_while_remote_probe_is_running(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, _, snapshot):
            client = VerificationClient(server.path, os.getuid())
            entered, release = asyncio.Event(), asyncio.Event()
            count = [0]

            async def probe(_):
                count[0] += 1
                if count[0] == 2:
                    entered.set()
                    await release.wait()
                return dict(snapshot)

            server.probe = probe
            request = ActionRequest(action="service.restart", target="fixture.service")
            task = asyncio.create_task(
                client.verify("b" * 32, request, fingerprint(request, snapshot), lambda: None)
            )
            try:
                await entered.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert "b" * 32 in server.policy.revoked
                assert not server.policy.pending and not server.policy.claimed
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["unavailable", "timeout"])
def test_cleanup_failure_preserves_primary_error_and_leaves_no_task(tmp_path, monkeypatch, failure):
    from app import executor_client

    async def run():
        async with lab(tmp_path) as (server, _, snapshot):
            client = VerificationClient(server.path, os.getuid())
            finished = asyncio.Event()

            async def fail(*args):
                try:
                    if failure == "unavailable":
                        raise VerificationError()
                    await asyncio.Event().wait()
                finally:
                    finished.set()

            monkeypatch.setattr(client, "revoke", fail)
            monkeypatch.setattr(executor_client, "REVOCATION_CLEANUP_SECONDS", 0.01)

            def checkpoint():
                if server.policy.pending:
                    raise RuntimeError("primary session failure")

            request = ActionRequest(action="service.restart", target="fixture.service")
            async with asyncio.timeout(1):
                with pytest.raises(RuntimeError, match="primary session failure"):
                    await client.verify(
                        "b" * 32, request, fingerprint(request, snapshot), checkpoint
                    )
            assert finished.is_set()
            assert "b" * 32 not in server.policy.revoked
            assert "b" * 32 in server.policy.pending

    asyncio.run(run())


def test_late_revoke_does_not_claim_to_undo_completed_verification(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, calls, _):
            ticket = (await exchange(server, issue_frame()))["ticket"]
            assert (await exchange(server, verify_frame(ticket)))["status"] == "verified_only"
            assert (await exchange(server, revoke_frame(ticket)))["status"] == "rejected"
            assert len(calls) == 2

    asyncio.run(run())
