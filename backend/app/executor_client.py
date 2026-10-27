"""Bounded client for the isolated verification lab; never requests execution."""

import asyncio
import contextlib
import hmac
import re
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .actions import ActionRequest
from .executor_protocol import ProtocolRejected, decode_frame
from .executor_transport import peer_uid, read_frame, write_frame
from .services import ServiceError

CLIENT_SECONDS = 2.5
REVOCATION_CLEANUP_SECONDS = 0.3


class VerificationError(ServiceError):
    def __init__(self):
        super().__init__(
            "ACTION_VERIFICATION_FAILED", "Vérification Unix refusée ou indisponible", 503
        )


class ReplyBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=2, le=2)
    operation_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    system_execution_enabled: bool

    @model_validator(mode="after")
    def never_execution(self):
        if self.system_execution_enabled is not False:
            raise ValueError("Execution must remain disabled")
        return self


class VerifiedReply(ReplyBase):
    status: Literal["verified_only"]


class RevokedReply(ReplyBase):
    status: Literal["revoked"]


class IssuedReply(ReplyBase):
    status: Literal["ticket_issued"]
    ticket: str = Field(pattern=r"^[a-f0-9]{64}$")
    expires_in_seconds: int = Field(ge=1, le=30)


class VerificationClient:
    def __init__(self, path: Path, server_uid: int, *, session_scope: str | None = None):
        if type(server_uid) is not int or server_uid <= 0:
            raise ValueError("Non-root server UID required")
        if session_scope is not None and (
            not isinstance(session_scope, str) or not re.fullmatch(r"[a-f0-9]{64}", session_scope)
        ):
            raise ValueError("Invalid session scope")
        self.path = path
        self.server_uid = server_uid
        self.session_scope = session_scope

    def _private_path(self) -> None:
        parent, entry = self.path.parent.lstat(), self.path.lstat()
        if (
            not self.path.is_absolute()
            or self.path.parent.resolve() != self.path.parent
            or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != self.server_uid
            or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISSOCK(entry.st_mode)
            or entry.st_uid != self.server_uid
            or stat.S_IMODE(entry.st_mode) != 0o600
        ):
            raise ProtocolRejected("Private server required")

    async def _exchange(
        self, payload: dict, checkpoint: Callable[[], None], *, check_after=True
    ) -> dict:
        writer = None
        try:
            async with asyncio.timeout(CLIENT_SECONDS):
                checkpoint()
                self._private_path()
                reader, writer = await asyncio.open_unix_connection(self.path)
                if peer_uid(writer) != self.server_uid:
                    raise ProtocolRejected("Server rejected")
                checkpoint()
                await write_frame(writer, payload)
                reply = decode_frame(await read_frame(reader))
                if check_after:
                    checkpoint()
                return reply
        except (OSError, TimeoutError, ValueError, asyncio.IncompleteReadError):
            raise VerificationError() from None
        finally:
            if writer is not None:
                writer.close()
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(0.1):
                        await writer.wait_closed()

    async def revoke(self, operation_id: str, ticket: str, expected_fingerprint: str) -> None:
        payload = await self._exchange(
            {"version": 2, "kind": "revoke", "operation_id": operation_id, "ticket": ticket},
            lambda: None,  # Revocation reduces capability even after session invalidation.
        )
        try:
            reply = RevokedReply.model_validate(payload)
            if reply.operation_id != operation_id or not hmac.compare_digest(
                reply.fingerprint, expected_fingerprint
            ):
                raise ValueError("Revocation reply mismatch")
        except ValueError:
            raise VerificationError() from None

    async def verify(
        self,
        operation_id: str,
        request: ActionRequest,
        expected_fingerprint: str,
        checkpoint: Callable[[], None],
        *,
        owner: str | None = None,
    ) -> None:
        if (
            self.session_scope is not None
            and owner is not None
            and not hmac.compare_digest(self.session_scope, owner)
        ):
            raise VerificationError()
        # Validate replies and preserve the caller's session/expiry failures unchanged.
        issued = await self._exchange(
            {
                "version": 2,
                "kind": "issue",
                "operation_id": operation_id,
                "request": request.model_dump(),
                "expected_fingerprint": expected_fingerprint,
                **({"session_scope": self.session_scope} if self.session_scope is not None else {}),
            },
            checkpoint,
            check_after=False,
        )
        try:
            ticket = IssuedReply.model_validate(issued)
            if ticket.operation_id != operation_id or not hmac.compare_digest(
                ticket.fingerprint, expected_fingerprint
            ):
                raise ValueError("Reply mismatch")
        except ValueError:
            raise VerificationError() from None
        complete = False
        try:
            checkpoint()
            verified = await self._exchange(
                {
                    "version": 2,
                    "kind": "verify",
                    "operation_id": operation_id,
                    "ticket": ticket.ticket,
                },
                checkpoint,
            )
            try:
                reply = VerifiedReply.model_validate(verified)
                if reply.operation_id != operation_id or not hmac.compare_digest(
                    reply.fingerprint, expected_fingerprint
                ):
                    raise ValueError("Reply mismatch")
            except ValueError:
                raise VerificationError() from None
            checkpoint()
            complete = True
        finally:
            if not complete:
                # Best effort only: preserve the original failure/cancellation, no orphan task.
                with contextlib.suppress(VerificationError, TimeoutError, asyncio.CancelledError):
                    async with asyncio.timeout(REVOCATION_CLEANUP_SECONDS):
                        await self.revoke(operation_id, ticket.ticket, expected_fingerprint)
