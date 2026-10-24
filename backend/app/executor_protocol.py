"""Unconnected executor protocol prototype. Never performs system operations.

The future Unix transport must obtain peer_uid from SO_PEERCRED, never JSON.
A ticket proves only that this policy accepted an intent, not user approval.
"""

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from .actions import ActionRequest, fingerprint

MAX_FRAME_BYTES = 2048
TICKET_SECONDS = 30
MAX_TICKETS = 256


class ProtocolRejected(ValueError):
    """Deliberately contains no request, ticket or target details."""


class ExecutorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: int = Field(ge=1, le=1)
    operation_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    ticket: str = Field(pattern=r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class Intent:
    """Immutable exact target; contains no executable path or arbitrary arguments."""

    operation_id: str
    action: str
    target: str
    engine: str | None
    fingerprint: str


@dataclass(frozen=True)
class Pending:
    intent: Intent
    ticket_hash: bytes
    deadline: float


class ExecutorPolicy:
    """Single-threaded policy prototype, with no transport or execution backend.

    IDs remain reserved for this instance's lifetime, including failed attempts.
    At capacity replace the instance (and invalidate ALL tickets); never evict IDs.
    """

    def __init__(
        self,
        client_uid: int,
        grants: frozenset[tuple[str, str, str | None]],
        clock: Callable[[], float] = time.monotonic,
    ):
        if type(client_uid) is not int or client_uid < 0:
            raise ValueError("Invalid client UID")
        for action, target, engine in grants:
            ActionRequest.model_validate({"action": action, "target": target, "engine": engine})
        self.client_uid = client_uid
        self.grants = frozenset(grants)
        self.clock = clock
        self.pending: dict[str, Pending] = {}
        self.reserved: set[str] = set()

    def _peer(self, peer_uid: int) -> None:
        if type(peer_uid) is not int or peer_uid != self.client_uid:
            raise ProtocolRejected("Peer rejected")

    def issue(
        self, peer_uid: int, operation_id: str, request: ActionRequest, snapshot: dict
    ) -> str:
        self._peer(peer_uid)
        # Revalidate even if the caller constructed or mutated a Pydantic object.
        request = ActionRequest.model_validate(request.model_dump())
        if (request.action, request.target, request.engine) not in self.grants:
            raise ProtocolRejected("Target/action not granted")
        if len(self.reserved) >= MAX_TICKETS or operation_id in self.reserved:
            raise ProtocolRejected("Operation rejected")
        ticket = secrets.token_hex(32)
        ExecutorEnvelope(version=1, operation_id=operation_id, ticket=ticket)
        intent = Intent(
            operation_id,
            request.action,
            request.target,
            request.engine,
            fingerprint(request, snapshot),
        )
        self.reserved.add(operation_id)
        self.pending[operation_id] = Pending(
            intent, hashlib.sha256(ticket.encode()).digest(), self.clock() + TICKET_SECONDS
        )
        return ticket

    def consume(self, peer_uid: int, frame: bytes, snapshot: dict) -> Intent:
        self._peer(peer_uid)
        if not isinstance(frame, bytes) or not 0 < len(frame) <= MAX_FRAME_BYTES:
            raise ProtocolRejected("Frame rejected")
        try:
            # Decode JSON explicitly: duplicate keys must not have last-value semantics.
            import json

            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate field")
                    result[key] = value
                return result

            payload = json.loads(frame, object_pairs_hook=unique)
            envelope = ExecutorEnvelope.model_validate(payload)
        except (ValueError, UnicodeError):
            raise ProtocolRejected("Frame rejected") from None
        # Consume before any subsequent verification; failures require a new operation.
        pending = self.pending.pop(envelope.operation_id, None)
        if pending is None:
            raise ProtocolRejected("Operation rejected")
        if not hmac.compare_digest(
            pending.ticket_hash, hashlib.sha256(envelope.ticket.encode()).digest()
        ):
            raise ProtocolRejected("Ticket rejected")
        if self.clock() >= pending.deadline:
            raise ProtocolRejected("Ticket expired")
        intent = pending.intent
        request = ActionRequest.model_validate(
            {"action": intent.action, "target": intent.target, "engine": intent.engine}
        )
        if not hmac.compare_digest(intent.fingerprint, fingerprint(request, snapshot)):
            raise ProtocolRejected("Target changed")
        return intent
