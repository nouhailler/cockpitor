"""Read-only authority RPC, including an actual independent Python process."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.auth import Sessions
from app.executor_protocol import ExecutorPolicy
from app.executor_transport import read_frame, write_frame
from app.session_authority import (
    AuthorityUnavailable,
    RemoteSessionVerificationServer,
    SessionAuthorityClient,
    SessionAuthorityServer,
)
from test_executor_transport import exchange, verify_frame
from test_session_verification import scoped_issue


@asynccontextmanager
async def remote_lab(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    path = private / "auth.sock"
    fixture = Path(__file__).parent / "fixtures" / "session_authority_fixture.py"
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        str(fixture),
        str(path),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    verifier = None
    try:
        async with asyncio.timeout(10):
            info = json.loads(await child.stdout.readline())
            assert info["pid"] == child.pid and child.pid != os.getpid()
            authority = SessionAuthorityClient(path, os.getuid())
            state = {"state": "active", "configuration_fingerprint": "a" * 64}
            calls = []

            async def probe(_):
                calls.append("read")
                return dict(state)

            verifier = RemoteSessionVerificationServer(
                private / "verify.sock",
                ExecutorPolicy(
                    os.getuid(), frozenset({("service.restart", "fixture.service", None)})
                ),
                probe,
                authority=authority,
            )
            await verifier.start()

            async def control(command, **extra):
                child.stdin.write((json.dumps({"command": command, **extra}) + "\n").encode())
                await child.stdin.drain()
                assert json.loads(await child.stdout.readline()) == {"ok": True}

            yield SimpleNamespace(
                child=child,
                info=info,
                authority=authority,
                verifier=verifier,
                state=state,
                calls=calls,
                control=control,
            )
    finally:
        if verifier is not None:
            await verifier.close()
        if child.returncode is None:
            child.stdin.write(b'{"command":"stop"}\n')
            try:
                await child.stdin.drain()
                _, error = await asyncio.wait_for(child.communicate(), 3)
                assert child.returncode == 0 and not error
            except (TimeoutError, BrokenPipeError, ConnectionResetError):
                if child.returncode is None:
                    child.kill()
                await child.communicate()


async def wait_invalidated(h, identifier):
    async with asyncio.timeout(1):
        while identifier not in h.verifier.policy.revoked:
            await asyncio.sleep(0.005)


def test_two_real_processes_query_revoke_and_keep_other_session_valid(tmp_path):
    async def run():
        async with remote_lab(tmp_path) as h:
            owner, other = h.info["first_scope"], h.info["second_scope"]
            assert await h.authority.valid_many([owner, other]) == {owner: True, other: True}
            issued = await exchange(h.verifier, scoped_issue(owner))
            second = await exchange(h.verifier, scoped_issue(other, "c" * 32))
            await h.control("revoke_first")
            await wait_invalidated(h, "b" * 32)
            assert (await exchange(h.verifier, verify_frame(issued["ticket"])))[
                "status"
            ] == "rejected"
            assert (await exchange(h.verifier, verify_frame(second["ticket"], "c" * 32)))[
                "status"
            ] == "verified_only"
            assert await h.authority.valid_many([owner, other]) == {owner: False, other: True}

    asyncio.run(run())


def test_authority_process_crash_invalidates_pending_tickets_without_client(tmp_path):
    async def run():
        async with remote_lab(tmp_path) as h:
            await exchange(h.verifier, scoped_issue(h.info["first_scope"]))
            await exchange(h.verifier, scoped_issue(h.info["second_scope"], "c" * 32))
            h.child.kill()
            await h.child.wait()
            await wait_invalidated(h, "b" * 32)
            assert "c" * 32 in h.verifier.policy.revoked
            assert not h.verifier.policy.pending
            assert (await exchange(h.verifier, scoped_issue(h.info["first_scope"], "d" * 32)))[
                "status"
            ] == "rejected"
            assert len(h.calls) == 2

    asyncio.run(run())


def test_separate_authority_expiration_does_not_require_a_client_ticket(tmp_path):
    async def run():
        async with remote_lab(tmp_path) as h:
            await exchange(h.verifier, scoped_issue(h.info["first_scope"]))
            await h.control("advance", seconds=900)
            await wait_invalidated(h, "b" * 32)
            assert not h.verifier.policy.pending

    asyncio.run(run())


def test_authority_loss_during_probe_cannot_produce_verified_reply(tmp_path):
    async def run():
        async with remote_lab(tmp_path) as h:
            ticket = (await exchange(h.verifier, scoped_issue(h.info["first_scope"])))["ticket"]
            entered, release = asyncio.Event(), asyncio.Event()

            async def probe(_):
                entered.set()
                await release.wait()
                return dict(h.state)

            h.verifier.probe = probe
            task = asyncio.create_task(exchange(h.verifier, verify_frame(ticket)))
            try:
                await entered.wait()
                h.child.kill()
                await h.child.wait()
                await wait_invalidated(h, "b" * 32)
                release.set()
                assert (await task)["status"] == "rejected"
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


@asynccontextmanager
async def authority_lab(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    sessions = Sessions("fixture")
    token, _ = sessions.login("fixture")
    server = SessionAuthorityServer(
        private / "auth.sock", client_uid=os.getuid(), sessions=sessions
    )
    await server.start()
    try:
        async with asyncio.timeout(5):
            yield (
                server,
                SessionAuthorityClient(server.path, os.getuid()),
                sessions,
                sessions.digest(token),
            )
    finally:
        await server.close()


@pytest.mark.parametrize("change", ["nonce", "version", "extra", "truthy", "length"])
def test_authority_client_rejects_forged_or_coerced_reply(tmp_path, monkeypatch, change):
    async def run():
        async with authority_lab(tmp_path) as (server, client, _, owner):

            async def fake(uid, frame):
                reply = {"version": 1, "nonce": frame["nonce"], "states": [True]}
                if change == "nonce":
                    reply["nonce"] = "0" * 32
                elif change == "version":
                    reply["version"] = 2
                elif change == "extra":
                    reply["session"] = "secret"
                elif change == "truthy":
                    reply["states"] = [1]
                else:
                    reply["states"] = [True, True]
                return reply

            monkeypatch.setattr(server, "_dispatch", fake)
            with pytest.raises(AuthorityUnavailable) as exc:
                await client.valid_many([owner])
            assert "secret" not in str(exc.value)

    asyncio.run(run())


@pytest.mark.parametrize("change", ["duplicates", "too_many", "bad_scope", "extra", "mutation"])
def test_authority_wire_refuses_non_readonly_or_invalid_requests(tmp_path, change):
    async def run():
        async with authority_lab(tmp_path) as (server, _, _, owner):
            frame = {"version": 1, "kind": "check_sessions", "nonce": "a" * 32, "scopes": [owner]}
            if change == "duplicates":
                frame["scopes"] = [owner, owner]
            elif change == "too_many":
                frame["scopes"] = [f"{i:064x}" for i in range(17)]
            elif change == "bad_scope":
                frame["scopes"] = ["token"]
            elif change == "extra":
                frame["peer_uid"] = os.getuid()
            else:
                frame["kind"] = "revoke_session"
            reader, writer = await asyncio.open_unix_connection(server.path)
            try:
                await write_frame(writer, frame)
                assert json.loads(await read_frame(reader)) == {
                    "status": "rejected",
                    "system_execution_enabled": False,
                }
            finally:
                writer.close()
                await writer.wait_closed()

    asyncio.run(run())


def test_batching_and_empty_request_never_return_partial_permission(tmp_path, monkeypatch):
    async def run():
        async with authority_lab(tmp_path) as (server, client, _, owner):
            observed = []
            original = server._dispatch

            async def fail_second(uid, frame):
                observed.append(len(frame["scopes"]))
                if len(observed) == 2:
                    raise RuntimeError("secret authority failure")
                return await original(uid, frame)

            monkeypatch.setattr(server, "_dispatch", fail_second)
            scopes = [owner] + [f"{i:064x}" for i in range(17)]
            with pytest.raises(AuthorityUnavailable):
                await client.valid_many(scopes)
            assert observed == [16, 2]
            assert await client.valid_many([]) == {}
            with pytest.raises(AuthorityUnavailable):
                await client.valid_many([f"{i:064x}" for i in range(257)])

    asyncio.run(run())


def test_slow_authority_times_out_without_cached_permission(tmp_path, monkeypatch):
    async def run():
        async with authority_lab(tmp_path) as (server, client, _, owner):
            assert (await client.valid_many([owner]))[owner] is True

            async def blocked(uid, frame):
                await asyncio.Event().wait()

            monkeypatch.setattr(server, "_dispatch", blocked)
            async with asyncio.timeout(1):
                with pytest.raises(AuthorityUnavailable):
                    await client.valid_many([owner])

    asyncio.run(run())


def test_authority_unavailable_path_is_never_permission(tmp_path):
    async def run():
        client = SessionAuthorityClient(tmp_path / "missing.sock", os.getuid())
        with pytest.raises(AuthorityUnavailable):
            await client.valid_many(["a" * 64])

    asyncio.run(run())


def test_previous_positive_reply_cannot_be_replayed_as_current_permission(tmp_path, monkeypatch):
    async def run():
        async with authority_lab(tmp_path) as (server, client, sessions, owner):
            original = server._dispatch
            saved = []

            async def capture(uid, frame):
                reply = await original(uid, frame)
                saved.append(reply)
                return reply

            monkeypatch.setattr(server, "_dispatch", capture)
            assert (await client.valid_many([owner]))[owner] is True
            with sessions.lock:
                sessions.sessions.clear()

            async def replay(uid, frame):
                return saved[0]

            monkeypatch.setattr(server, "_dispatch", replay)
            with pytest.raises(AuthorityUnavailable):
                await client.valid_many([owner])

    asyncio.run(run())


@pytest.mark.parametrize("peer", ["client", "server"])
def test_uid_mismatch_is_never_authority_permission(tmp_path, peer):
    async def run():
        async with authority_lab(tmp_path) as (server, client, sessions, owner):
            if peer == "client":
                server.policy.client_uid += 1
            else:
                client.transport.server_uid += 1
            with pytest.raises(AuthorityUnavailable):
                await client.valid_many([owner])
            assert sessions.valid_owner(owner) is True

    asyncio.run(run())
