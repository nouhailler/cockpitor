"""Linux Unix-socket verification lab. No system execution or application wiring.

Replies describe tickets, verifications or revocations. Probe is a trusted,
read-only dependency; callers cannot supply snapshots over the wire.
"""

import asyncio
import contextlib
import hmac
import json
import os
import socket
import stat
import struct
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .actions import ActionRequest, fingerprint
from .executor_protocol import (
    MAX_FRAME_BYTES,
    TICKET_SECONDS,
    ExecutorEnvelope,
    ExecutorPolicy,
    ProtocolRejected,
    decode_frame,
)

MAX_CONNECTIONS = 4
REQUEST_SECONDS = 2.0
PROBE_SECONDS = 1.0


class IssueFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=2, le=2)
    kind: Literal["issue"]
    operation_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    request: ActionRequest
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class VerifyFrame(ExecutorEnvelope):
    version: int = Field(ge=2, le=2)
    kind: Literal["verify"]


class RevokeFrame(ExecutorEnvelope):
    version: int = Field(ge=2, le=2)
    kind: Literal["revoke"]


def peer_uid(writer: asyncio.StreamWriter) -> int:
    """Linux kernel credentials, never a field controlled by JSON."""
    connection = writer.get_extra_info("socket")
    if connection is None or not hasattr(socket, "SO_PEERCRED"):
        raise ProtocolRejected("Peer unavailable")
    raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    _, uid, _ = struct.unpack("3i", raw)
    return uid


async def read_frame(reader: asyncio.StreamReader) -> bytes:
    length = int.from_bytes(await reader.readexactly(4), "big")
    if not 0 < length <= MAX_FRAME_BYTES:
        raise ProtocolRejected("Frame rejected")
    return await reader.readexactly(length)


async def write_frame(writer: asyncio.StreamWriter, payload: dict) -> None:
    frame = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
    if len(frame) > MAX_FRAME_BYTES:
        raise ProtocolRejected("Reply rejected")
    writer.write(len(frame).to_bytes(4, "big") + frame)
    await writer.drain()


class VerificationServer:
    """One request per connection, bounded admission and serialized policy/probes.

    This lab refuses root, keeps all tickets in memory, and has no executable
    entry point. A new instance is required after close or failed start.
    """

    def __init__(
        self,
        path: Path,
        policy: ExecutorPolicy,
        probe: Callable[[ActionRequest], Awaitable[dict]],
    ):
        self.path = path
        self.policy = policy
        self.probe = probe
        self.server: asyncio.Server | None = None
        self.tasks: set[asyncio.Task] = set()
        self.lock = asyncio.Lock()
        self.identity: tuple[int, int] | None = None
        self.started = False
        self.closing = False

    async def start(self) -> None:
        if self.started or self.closing or os.geteuid() == 0:
            raise ProtocolRejected("Lab start rejected")
        self.started = True
        if not self.path.is_absolute() or not hasattr(socket, "SO_PEERCRED"):
            raise ProtocolRejected("Linux private socket required")
        parent = self.path.parent
        info = parent.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or parent.resolve() != parent
        ):
            raise ProtocolRejected("Private directory required")
        # Never unlink/reuse an existing entry, including a dangling symlink.
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.path))
            bound = self.path.lstat()
            self.identity = (bound.st_dev, bound.st_ino)
            self.path.chmod(0o600)
            listener.setblocking(False)
            self.server = await asyncio.start_unix_server(
                self._accept, sock=listener, limit=MAX_FRAME_BYTES + 4, backlog=MAX_CONNECTIONS
            )
        except BaseException:
            listener.close()
            self._unlink_owned()
            raise

    def _unlink_owned(self) -> None:
        if self.identity is None:
            return
        try:
            info = self.path.lstat()
            if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == self.identity:
                self.path.unlink()
        except FileNotFoundError:
            pass
        self.identity = None

    def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.closing or len(self.tasks) >= MAX_CONNECTIONS:
            writer.close()
            return
        task = asyncio.create_task(self._serve(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(REQUEST_SECONDS):
                uid = peer_uid(writer)
                self.policy.check_peer(uid)
                frame = decode_frame(await read_frame(reader))
                if frame.get("kind") == "revoke":
                    # Synchronous policy update must not wait behind a slow probe.
                    reply = self._revoke(uid, frame)
                else:
                    async with self.lock:
                        reply = await self._dispatch(uid, frame)
                await write_frame(writer, reply)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — transport boundary must sanitize probe failures
            # No input, token, target, snapshot or exception detail crosses the socket.
            with contextlib.suppress(Exception):
                async with asyncio.timeout(0.1):
                    await write_frame(
                        writer, {"status": "rejected", "system_execution_enabled": False}
                    )
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                async with asyncio.timeout(0.1):
                    await writer.wait_closed()

    async def _snapshot(self, request: ActionRequest) -> dict:
        async with asyncio.timeout(PROBE_SECONDS):
            return await self.probe(request)

    def _revoke(self, uid: int, frame: dict) -> dict:
        revoke = RevokeFrame.model_validate(frame)
        envelope = revoke.model_dump(exclude={"kind"})
        envelope["version"] = 1
        intent = self.policy.revoke(uid, json.dumps(envelope).encode())
        return {
            "version": 2,
            "operation_id": intent.operation_id,
            "fingerprint": intent.fingerprint,
            "status": "revoked",
            "system_execution_enabled": False,
        }

    async def _dispatch(self, uid: int, frame: dict) -> dict:
        if frame.get("kind") == "issue":
            issue = IssueFrame.model_validate(frame)
            self.policy.check_issue(uid, issue.operation_id, issue.request)
            snapshot = await self._snapshot(issue.request)
            if not hmac.compare_digest(
                issue.expected_fingerprint, fingerprint(issue.request, snapshot)
            ):
                raise ProtocolRejected("Approved target changed")
            ticket = self.policy.issue(uid, issue.operation_id, issue.request, snapshot)
            return {
                "version": 2,
                "operation_id": issue.operation_id,
                "fingerprint": issue.expected_fingerprint,
                "status": "ticket_issued",
                "ticket": ticket,
                "expires_in_seconds": TICKET_SECONDS,
                "system_execution_enabled": False,
            }
        verify = VerifyFrame.model_validate(frame)
        envelope = verify.model_dump(exclude={"kind"})
        envelope["version"] = 1  # Internal policy envelope; the wire protocol is v2.
        claimed = self.policy.claim(uid, json.dumps(envelope).encode())
        request = ActionRequest.model_validate(
            {
                "action": claimed.intent.action,
                "target": claimed.intent.target,
                "engine": claimed.intent.engine,
            }
        )
        try:
            snapshot = await self._snapshot(request)
            self.policy.verify_snapshot(claimed, snapshot)
            return {
                "version": 2,
                "operation_id": verify.operation_id,
                "fingerprint": claimed.intent.fingerprint,
                "status": "verified_only",
                "system_execution_enabled": False,
            }
        finally:
            self.policy.abandon(claimed)

    async def close(self) -> None:
        self.closing = True
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.difference_update(tasks)
        self.policy.invalidate()
        self._unlink_owned()
