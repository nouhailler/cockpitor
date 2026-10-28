"""Read-only session authority RPC for a separate, non-root laboratory process.

No login/revoke commands, privileged execution, public launcher or app wiring.
The private Unix peer boundary is the local UID; it does not isolate hostile
programs running under the same account.
"""

import asyncio
import hmac
import secrets
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .auth import Sessions
from .executor_client import VerificationClient, VerificationError
from .executor_protocol import ExecutorPolicy
from .executor_transport import VerificationServer
from .session_verification import SessionVerificationServer

BATCH_SIZE = 16
AUTHORITY_SECONDS = 0.2
AUTHORITY_BATCH_SECONDS = 0.4
Scope = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class AuthorityUnavailable(Exception):
    pass


class AuthorityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=1, le=1)
    kind: Literal["check_sessions"]
    nonce: str = Field(pattern=r"^[a-f0-9]{32}$")
    scopes: list[Scope] = Field(min_length=1, max_length=BATCH_SIZE)

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError("Distinct scopes required")
        return self


class AuthorityReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=1, le=1)
    nonce: str = Field(pattern=r"^[a-f0-9]{32}$")
    states: list[bool] = Field(min_length=1, max_length=BATCH_SIZE)


class SessionAuthorityServer(VerificationServer):
    def __init__(self, path: Path, *, client_uid: int, sessions: Sessions):
        async def no_probe(_):
            raise RuntimeError("No resource probe on authority")

        super().__init__(path, ExecutorPolicy(client_uid, frozenset()), no_probe)
        self.sessions = sessions

    async def _dispatch(self, uid: int, frame: dict) -> dict:
        request = AuthorityRequest.model_validate(frame)
        return {
            "version": 1,
            "nonce": request.nonce,
            "states": [self.sessions.valid_owner(scope) is True for scope in request.scopes],
        }


class SessionAuthorityClient:
    def __init__(self, path: Path, server_uid: int):
        # Reuse bounded framing, private-path checks and Linux peer credentials.
        self.transport = VerificationClient(path, server_uid)

    async def valid_many(self, scopes: list[str]) -> dict[str, bool]:
        result: dict[str, bool] = {}
        try:
            unique = sorted(set(scopes))
            if len(unique) > 256:
                raise ValueError("Authority request refused")
            async with asyncio.timeout(AUTHORITY_BATCH_SECONDS):
                for offset in range(0, len(unique), BATCH_SIZE):
                    batch = unique[offset : offset + BATCH_SIZE]
                    nonce = secrets.token_hex(16)
                    request = AuthorityRequest(
                        version=1, kind="check_sessions", nonce=nonce, scopes=batch
                    )
                    async with asyncio.timeout(AUTHORITY_SECONDS):
                        payload = await self.transport._exchange(request.model_dump(), lambda: None)
                    reply = AuthorityReply.model_validate(payload)
                    if not hmac.compare_digest(reply.nonce, nonce) or len(reply.states) != len(
                        batch
                    ):
                        raise ValueError("Authority reply mismatch")
                    result.update(zip(batch, reply.states, strict=True))
            return result  # No positive cache; partial batches are never permission.
        except (VerificationError, ValueError, TypeError, TimeoutError):
            raise AuthorityUnavailable("Session authority unavailable") from None


class RemoteSessionVerificationServer(SessionVerificationServer):
    def __init__(self, path, policy, probe, *, authority: SessionAuthorityClient):
        super().__init__(path, policy, probe, sessions=None)
        self.authority = authority

    async def _valid(self, scope: str) -> bool:
        try:
            return (await self.authority.valid_many([scope])).get(scope) is True
        except AuthorityUnavailable:
            return False

    async def sweep_sessions(self) -> None:
        bindings = dict(self.operation_scopes)
        if not bindings:
            return
        try:
            states = await self.authority.valid_many(list(bindings.values()))
        except AuthorityUnavailable:
            # Include operations registered while the authority call was pending.
            for identifier in tuple(self.operation_scopes):
                self.policy.invalidate_operation(identifier)
            return
        for identifier, scope in bindings.items():
            if states.get(scope) is not True:
                self.policy.invalidate_operation(identifier)
