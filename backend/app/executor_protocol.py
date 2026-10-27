"""Unconnected executor protocol prototype. Never performs system operations.

The Unix lab transport supplies peer_uid from SO_PEERCRED, never JSON.
A ticket proves only that this policy accepted an intent, not user approval.
"""

import hashlib
import hmac
import json
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
        self.claimed: dict[str, Pending] = {}
        self.revoked: dict[str, Pending] = {}
        self.closed = False

    def check_peer(self, peer_uid: int) -> None:
        if self.closed or type(peer_uid) is not int or peer_uid != self.client_uid:
            raise ProtocolRejected("Peer rejected")

    def check_issue(self, peer_uid: int, operation_id: str, request: ActionRequest) -> None:
        self.check_peer(peer_uid)
        request = ActionRequest.model_validate(request.model_dump())
        ExecutorEnvelope(version=1, operation_id=operation_id, ticket="0" * 64)
        if (request.action, request.target, request.engine) not in self.grants:
            raise ProtocolRejected("Target/action not granted")
        if len(self.reserved) >= MAX_TICKETS or operation_id in self.reserved:
            raise ProtocolRejected("Operation rejected")

    def issue(
        self, peer_uid: int, operation_id: str, request: ActionRequest, snapshot: dict
    ) -> str:
        self.check_issue(peer_uid, operation_id, request)
        ticket = secrets.token_hex(32)
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

    def claim(self, peer_uid: int, frame: bytes) -> Pending:
        self.check_peer(peer_uid)
        try:
            envelope = ExecutorEnvelope.model_validate(decode_frame(frame))
        except ValueError:
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
        self.claimed[envelope.operation_id] = pending
        return pending

    def revoke(self, peer_uid: int, frame: bytes) -> Intent:
        self.check_peer(peer_uid)
        try:
            envelope = ExecutorEnvelope.model_validate(decode_frame(frame))
        except ValueError:
            raise ProtocolRejected("Frame rejected") from None
        identifier = envelope.operation_id
        pending = (
            self.pending.get(identifier)
            or self.claimed.get(identifier)
            or self.revoked.get(identifier)
        )
        if pending is None or not hmac.compare_digest(
            pending.ticket_hash, hashlib.sha256(envelope.ticket.encode()).digest()
        ):
            raise ProtocolRejected("Revocation rejected")
        self.pending.pop(identifier, None)
        self.claimed.pop(identifier, None)
        self.revoked[identifier] = pending
        return pending.intent

    def abandon(self, pending: Pending) -> None:
        if self.claimed.get(pending.intent.operation_id) is pending:
            self.claimed.pop(pending.intent.operation_id)

    def verify_snapshot(self, pending: Pending, snapshot: dict) -> Intent:
        if self.claimed.pop(pending.intent.operation_id, None) is not pending:
            raise ProtocolRejected("Ticket no longer active")
        if self.closed or self.clock() >= pending.deadline:
            raise ProtocolRejected("Ticket expired")
        intent = pending.intent
        request = ActionRequest.model_validate(
            {"action": intent.action, "target": intent.target, "engine": intent.engine}
        )
        if not hmac.compare_digest(intent.fingerprint, fingerprint(request, snapshot)):
            raise ProtocolRejected("Target changed")
        return intent

    def consume(self, peer_uid: int, frame: bytes, snapshot: dict) -> Intent:
        return self.verify_snapshot(self.claim(peer_uid, frame), snapshot)

    def invalidate(self) -> None:
        """Closing a lab permanently invalidates its remaining tickets."""
        self.pending.clear()
        self.claimed.clear()
        self.revoked.clear()
        self.closed = True


def decode_frame(frame: bytes) -> dict:
    if not isinstance(frame, bytes) or not 0 < len(frame) <= MAX_FRAME_BYTES:
        raise ProtocolRejected("Frame rejected")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Non-finite value")

    try:
        payload = json.loads(frame, object_pairs_hook=unique, parse_constant=invalid_constant)
        if not isinstance(payload, dict):
            raise TypeError("Object required")
        return payload
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProtocolRejected("Frame rejected") from None
