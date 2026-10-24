"""Real Linux sockets, kernel credentials and controlled read-only probes only."""

import asyncio
import json
import os
import stat
from contextlib import asynccontextmanager

import pytest
from app import executor_transport as transport
from app.executor_protocol import MAX_FRAME_BYTES, ExecutorPolicy, ProtocolRejected
from app.executor_transport import VerificationServer, read_frame, write_frame


@asynccontextmanager
async def lab(tmp_path, *, uid=None, probe=None):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    policy = ExecutorPolicy(
        os.getuid() if uid is None else uid,
        frozenset({("service.restart", "fixture.service", None)}),
    )
    calls = []
    state = {"state": "active", "configuration_fingerprint": "a" * 64}

    async def snapshot(request):
        calls.append(request.model_dump())
        return dict(state)

    server = VerificationServer(parent / "lab.sock", policy, probe or snapshot)
    await server.start()
    try:
        async with asyncio.timeout(5):
            yield server, calls, state
    finally:
        await server.close()


def issue_frame(operation="b" * 32):
    return {
        "version": 1,
        "kind": "issue",
        "operation_id": operation,
        "request": {"action": "service.restart", "target": "fixture.service"},
    }


def verify_frame(ticket, operation="b" * 32):
    return {"version": 1, "kind": "verify", "operation_id": operation, "ticket": ticket}


async def exchange(server, payload):
    reader, writer = await asyncio.open_unix_connection(server.path)
    try:
        await write_frame(writer, payload)
        response = json.loads(await read_frame(reader))
        assert response["system_execution_enabled"] is False
        assert await reader.read() == b""  # exactly one request per connection
        return response
    finally:
        writer.close()
        await writer.wait_closed()


def test_real_socket_issue_verify_replay_and_permissions(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, calls, _):
            assert stat.S_IMODE(server.path.stat().st_mode) == 0o600
            issued = await exchange(server, issue_frame())
            assert issued["status"] == "ticket_issued"
            assert issued["expires_in_seconds"] == 30
            assert len(issued["ticket"]) == 64
            verified = await exchange(server, verify_frame(issued["ticket"]))
            assert verified["status"] == "verified_only"
            assert len(calls) == 2
            assert (await exchange(server, verify_frame(issued["ticket"])))["status"] == "rejected"
            assert len(calls) == 2
            assert issued["ticket"] not in repr(server.policy.pending)
        assert not server.path.exists()
        assert server.policy.closed
        assert not server.policy.pending

    asyncio.run(run())


def test_kernel_uid_rejected_before_probe(tmp_path):
    async def run():
        async with lab(tmp_path, uid=os.getuid() + 1) as (server, calls, _):
            # Send no JSON: refusal must happen from kernel credentials alone.
            reader, writer = await asyncio.open_unix_connection(server.path)
            try:
                assert json.loads(await read_frame(reader))["status"] == "rejected"
                assert await reader.read() == b""
                assert not calls
                assert not server.policy.reserved
            finally:
                writer.close()
                await writer.wait_closed()

    asyncio.run(run())


@pytest.mark.parametrize(
    "change", ["snapshot", "peer_uid", "command", "unknown_action", "target", "version"]
)
def test_untrusted_fields_never_reach_probe(tmp_path, change):
    async def run():
        async with lab(tmp_path) as (server, calls, _):
            frame = issue_frame()
            if change in {"snapshot", "peer_uid", "command"}:
                frame[change] = "untrusted"
            elif change == "unknown_action":
                frame["request"]["action"] = "service.execute"
            elif change == "target":
                frame["request"]["target"] = "other.service"
            else:
                frame["version"] = True
            assert (await exchange(server, frame))["status"] == "rejected"
            assert not calls

    asyncio.run(run())


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"[]",
        b"\xff",
        b'{"version":1,"version":1}',
        b'{"value":NaN}',
        b"[" * 1000 + b"]" * 1000,
    ],
)
def test_invalid_json_sanitized(tmp_path, raw):
    async def run():
        async with lab(tmp_path) as (server, calls, _):
            reader, writer = await asyncio.open_unix_connection(server.path)
            try:
                writer.write(len(raw).to_bytes(4, "big") + raw)
                await writer.drain()
                assert json.loads(await read_frame(reader)) == {
                    "status": "rejected",
                    "system_execution_enabled": False,
                }
                assert not calls
            finally:
                writer.close()
                await writer.wait_closed()

    asyncio.run(run())


@pytest.mark.parametrize("size", [0, MAX_FRAME_BYTES + 1, 2**32 - 1])
def test_announced_size_rejected_before_body(tmp_path, size):
    async def run():
        async with lab(tmp_path) as (server, calls, _):
            reader, writer = await asyncio.open_unix_connection(server.path)
            try:
                writer.write(size.to_bytes(4, "big"))
                await writer.drain()
                assert json.loads(await read_frame(reader))["status"] == "rejected"
                assert not calls
            finally:
                writer.close()
                await writer.wait_closed()

    asyncio.run(run())


def test_changed_configuration_burns_ticket(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, calls, state):
            ticket = (await exchange(server, issue_frame()))["ticket"]
            state["configuration_fingerprint"] = "changed"
            assert (await exchange(server, verify_frame(ticket)))["status"] == "rejected"
            state["configuration_fingerprint"] = "a" * 64
            assert (await exchange(server, verify_frame(ticket)))["status"] == "rejected"
            assert len(calls) == 2

    asyncio.run(run())


def test_probe_failure_burns_ticket_and_never_leaks_details(tmp_path):
    fail = [False]

    async def snapshot(_):
        if fail[0]:
            raise RuntimeError("secret fixture data")
        return {"state": "active"}

    async def run():
        async with lab(tmp_path, probe=snapshot) as (server, _, _):
            ticket = (await exchange(server, issue_frame()))["ticket"]
            fail[0] = True
            reply = await exchange(server, verify_frame(ticket))
            assert reply == {"status": "rejected", "system_execution_enabled": False}
            fail[0] = False
            assert (await exchange(server, verify_frame(ticket)))["status"] == "rejected"

    asyncio.run(run())


def test_slow_probe_and_expiry_during_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, "PROBE_SECONDS", 0.03)
    delay = [False]
    now = [0.0]

    async def snapshot(_):
        if delay[0]:
            await asyncio.sleep(1)
        return {"state": "active"}

    async def run():
        async with lab(tmp_path, probe=snapshot) as (server, _, _):
            server.policy.clock = lambda: now[0]
            ticket = (await exchange(server, issue_frame()))["ticket"]
            delay[0] = True
            assert (await exchange(server, verify_frame(ticket)))["status"] == "rejected"
            delay[0] = False
            assert (await exchange(server, verify_frame(ticket)))["status"] == "rejected"
            ticket = (await exchange(server, issue_frame("c" * 32)))["ticket"]

            async def expire(_):
                now[0] = 30
                return {"state": "active"}

            server.probe = expire
            assert (await exchange(server, verify_frame(ticket, "c" * 32)))["status"] == "rejected"

    asyncio.run(run())


def test_slow_client_deadline_and_truncated_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, "REQUEST_SECONDS", 0.04)

    async def run():
        async with lab(tmp_path) as (server, calls, _):
            for truncate in (False, True):
                reader, writer = await asyncio.open_unix_connection(server.path)
                try:
                    writer.write(b"\x00")
                    await writer.drain()
                    if truncate:
                        writer.write_eof()
                    assert json.loads(await read_frame(reader))["status"] == "rejected"
                    assert await reader.read() == b""
                finally:
                    writer.close()
                    await writer.wait_closed()
            assert not calls

    asyncio.run(run())


def test_concurrent_replay_only_probes_once(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, calls, _):
            ticket = (await exchange(server, issue_frame()))["ticket"]
            replies = await asyncio.gather(
                *(exchange(server, verify_frame(ticket)) for _ in range(4))
            )
            assert sorted(reply["status"] for reply in replies) == ["rejected"] * 3 + [
                "verified_only"
            ]
            assert len(calls) == 2

    asyncio.run(run())


def test_connection_limit_and_close_cancel_pending_probe(tmp_path):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def snapshot(_):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def run():
        async with lab(tmp_path, probe=snapshot) as (server, _, _):
            connections = []
            try:
                first = await asyncio.open_unix_connection(server.path)
                connections.append(first)
                await write_frame(first[1], issue_frame())
                await entered.wait()
                for _ in range(transport.MAX_CONNECTIONS - 1):
                    connections.append(await asyncio.open_unix_connection(server.path))
                reader, writer = await asyncio.open_unix_connection(server.path)
                connections.append((reader, writer))
                assert await reader.read() == b""
                assert len(server.tasks) == transport.MAX_CONNECTIONS
                await server.close()
                assert cancelled.is_set()
                assert not server.tasks
                assert not server.path.exists()
            finally:
                for _, writer in connections:
                    writer.close()
                    await writer.wait_closed()

    asyncio.run(run())


@pytest.mark.parametrize(
    "kind", ["permissions", "symlink_parent", "file", "symlink_socket", "existing_socket"]
)
def test_unsafe_paths_and_existing_entries_are_preserved(tmp_path, kind):
    async def run():
        directory = tmp_path / "private"
        directory.mkdir(mode=0o700)
        path = directory / "lab.sock"
        original = None
        if kind == "permissions":
            directory.chmod(0o755)
        elif kind == "symlink_parent":
            alias = tmp_path / "alias"
            alias.symlink_to(directory, target_is_directory=True)
            path = alias / "lab.sock"
        elif kind == "file":
            path.write_text("keep")
        elif kind == "symlink_socket":
            path.symlink_to(directory / "missing")
        else:
            import socket

            original = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            original.bind(str(path))
        policy = ExecutorPolicy(os.getuid(), frozenset())

        async def snapshot(_):
            raise AssertionError("No probe")

        server = VerificationServer(path, policy, snapshot)
        try:
            with pytest.raises((ProtocolRejected, OSError)):
                await server.start()
            await server.close()
            if kind == "file":
                assert path.read_text() == "keep"
            elif kind == "symlink_socket":
                assert path.is_symlink()
            elif kind == "existing_socket":
                assert stat.S_ISSOCK(path.lstat().st_mode)
        finally:
            if original:
                original.close()

    asyncio.run(run())


def test_close_never_unlinks_replacement_and_refuses_restart(tmp_path):
    async def run():
        async with lab(tmp_path) as (server, _, _):
            server.path.unlink()
            server.path.write_text("replacement")
            await server.close()
            assert server.path.read_text() == "replacement"
            with pytest.raises(ProtocolRejected):
                await server.start()

    asyncio.run(run())


def test_root_lab_is_refused_before_binding(tmp_path, monkeypatch):
    async def run():
        async with lab(tmp_path) as (server, _, _):
            path = server.path.parent / "root.sock"
            other = VerificationServer(path, server.policy, server.probe)
            with monkeypatch.context() as patch:
                patch.setattr(os, "geteuid", lambda: 0)
                with pytest.raises(ProtocolRejected):
                    await other.start()
            assert not path.exists()

    asyncio.run(run())


def test_missing_kernel_credentials_fail_closed(tmp_path, monkeypatch):
    async def run():
        async with lab(tmp_path) as (server, _, _):
            path = server.path.parent / "unsupported.sock"
            other = VerificationServer(path, server.policy, server.probe)
            with monkeypatch.context() as patch:
                patch.delattr(transport.socket, "SO_PEERCRED")
                with pytest.raises(ProtocolRejected):
                    await other.start()
            assert not path.exists()

    asyncio.run(run())


def test_failed_start_cleans_only_its_own_socket(tmp_path, monkeypatch):
    async def run():
        async with lab(tmp_path) as (server, _, _):
            path = server.path.parent / "failed.sock"
            other = VerificationServer(path, server.policy, server.probe)

            async def fail(*args, **kwargs):
                raise OSError("fixture startup error")

            with monkeypatch.context() as patch:
                patch.setattr(asyncio, "start_unix_server", fail)
                with pytest.raises(OSError):
                    await other.start()
            assert not path.exists()
            assert server.path.exists()
            with pytest.raises(ProtocolRejected):
                await other.start()

    asyncio.run(run())
