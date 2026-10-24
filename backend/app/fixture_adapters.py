"""Adapter qualification lab. IO callbacks are mandatory and supplied by tests.

No default systemctl runner, HTTP client, socket configuration, CLI, environment
switch or web integration exists. These adapters are NOT SimulationVerifiers:
a fixture trial must never be reported as a no-effect application simulation.
"""

import asyncio
import hmac
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .actions import ActionRequest, fingerprint
from .fixture_journal import FixtureJournal, JournalError

READ_SECONDS = 1.0
SEND_SECONDS = 2.0
POST_SECONDS = 2.0
POLL_SECONDS = 0.05


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    configuration_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ServiceObservation(Observation):
    unit: str = Field(min_length=1, max_length=200)
    load: Literal["loaded"]
    active: Literal["active", "inactive", "failed", "activating", "deactivating"]
    substate: str = Field(min_length=1, max_length=50)
    pid: int = Field(ge=0)
    invocation: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    needs_reload: bool

    @field_validator("invocation")
    @classmethod
    def real_invocation(cls, value):
        if value == "0" * 32:
            raise ValueError("Real invocation required")
        return value


class ContainerObservation(Observation):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    engine: Literal["docker", "podman"]
    status: Literal["created", "running", "exited", "paused", "restarting", "dead"]
    running: bool
    started_at: str | None = Field(default=None, max_length=64)

    @field_validator("started_at")
    @classmethod
    def valid_start(cls, value):
        if value is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z", value):
                raise ValueError("UTC timestamp required")
            if datetime.fromisoformat(value).year <= 1:
                raise ValueError("Real start timestamp required")
        return value


@dataclass(frozen=True)
class HTTPMutation:
    engine: Literal["docker", "podman"]
    method: Literal["POST"]
    path: str


class ServiceFixtureAdapter:
    def __init__(
        self,
        read: Callable[[str], Awaitable[dict]],
        send: Callable[[tuple[str, ...]], Awaitable[bool]],
    ):
        self.read, self.send = read, send

    async def observe(self, request: ActionRequest):
        observation = ServiceObservation.model_validate(await self.read(request.target))
        if observation.unit != request.target or observation.needs_reload:
            raise ValueError("Service identity/configuration unavailable")
        return observation

    @staticmethod
    def ready(request, before):
        if request.action == "service.start":
            return before.active == "inactive" and before.substate == "dead" and before.pid == 0
        return (
            before.active == "active"
            and before.substate == "running"
            and before.pid > 0
            and before.invocation is not None
        )

    async def mutate(self, request: ActionRequest):
        # Revalidate inside the adapter; a caller cannot supply arguments or paths.
        request = ActionRequest.model_validate(request.model_dump())
        if not request.action.startswith("service."):
            raise ValueError("Service action required")
        command = (
            "/usr/bin/systemctl",
            "--no-pager",
            "--no-ask-password",
            request.action.split(".")[1],
            "--",
            request.target,
        )
        if await self.send(command) is not True:
            raise ValueError("Dispatch not acknowledged")

    @staticmethod
    def satisfied(request, before, after):
        if not hmac.compare_digest(
            before.configuration_fingerprint, after.configuration_fingerprint
        ):
            return False
        if request.action == "service.stop":
            return after.active == "inactive" and after.substate == "dead" and after.pid == 0
        running = (
            after.active == "active"
            and after.substate == "running"
            and after.pid > 0
            and after.invocation is not None
        )
        return running and after.invocation != before.invocation


class ContainerFixtureAdapter:
    def __init__(
        self,
        read: Callable[[str, str], Awaitable[dict]],
        send: Callable[[HTTPMutation], Awaitable[int]],
    ):
        self.read, self.send = read, send

    async def observe(self, request: ActionRequest):
        if request.engine is None:
            raise ValueError("Engine required")
        observation = ContainerObservation.model_validate(
            await self.read(request.engine, request.target)
        )
        if observation.id != request.target or observation.engine != request.engine:
            raise ValueError("Container identity mismatch")
        return observation

    @staticmethod
    def ready(request, before):
        if request.action == "container.start":
            return not before.running and before.status in {"created", "exited"}
        return before.running and before.status == "running" and before.started_at is not None

    async def mutate(self, request: ActionRequest):
        request = ActionRequest.model_validate(request.model_dump())
        if not request.action.startswith("container.") or request.engine is None:
            raise ValueError("Container action required")
        suffix = "start" if request.action == "container.start" else "restart?t=5"
        operation = HTTPMutation(request.engine, "POST", f"/containers/{request.target}/{suffix}")
        acknowledged = await self.send(operation)
        if type(acknowledged) is not int or acknowledged != 204:
            raise ValueError("Dispatch not acknowledged")

    @staticmethod
    def satisfied(request, before, after):
        if not hmac.compare_digest(
            before.configuration_fingerprint, after.configuration_fingerprint
        ):
            return False
        if not after.running or after.status != "running" or after.started_at is None:
            return False
        later = datetime.fromisoformat(after.started_at)
        if later > datetime.now(UTC):
            return False
        if before.started_at is None:
            return True
        return later > datetime.fromisoformat(before.started_at)


@dataclass(frozen=True)
class TrialResult:
    trial_id: str
    status: Literal["not_dispatched", "verified", "unknown"]
    scope: Literal["fixture_only"] = "fixture_only"


class FixtureTrialRunner:
    """One-shot fixture trials; never connected to the verification wire protocol."""

    def __init__(
        self,
        journal: FixtureJournal,
        grants: frozenset[tuple[str, str, str | None]],
        service: ServiceFixtureAdapter,
        container: ContainerFixtureAdapter,
    ):
        for action, target, engine in grants:
            ActionRequest.model_validate({"action": action, "target": target, "engine": engine})
        self.journal, self.grants = journal, frozenset(grants)
        self.service, self.container = service, container
        self.lock = asyncio.Lock()

    async def run_fixture(
        self,
        trial_id: str,
        request: ActionRequest,
        expected_fingerprint: str,
        checkpoint: Callable[[], None],
    ) -> TrialResult:
        request = ActionRequest.model_validate(request.model_dump())
        if (
            request.action,
            request.target,
            request.engine,
        ) not in self.grants or self.lock.locked():
            raise ValueError("Fixture trial refused")
        if not re.fullmatch(r"[a-f0-9]{64}", expected_fingerprint):
            raise ValueError("Invalid expected fingerprint")
        async with self.lock:
            self.journal.reserve(trial_id, request.action)
            status, attempted = "prepared", False
            adapter = self.service if request.action.startswith("service.") else self.container
            try:
                checkpoint()
                async with asyncio.timeout(READ_SECONDS):
                    before = await adapter.observe(request)
                checkpoint()
                if not hmac.compare_digest(
                    fingerprint(request, before.model_dump()), expected_fingerprint
                ) or not adapter.ready(request, before):
                    raise ValueError("Approved precondition not met")
                self.journal.transition(trial_id, status, "dispatching")
                status = "dispatching"
                checkpoint()
                async with asyncio.timeout(READ_SECONDS):
                    immediate = await adapter.observe(request)
                checkpoint()
                if not hmac.compare_digest(
                    fingerprint(request, immediate.model_dump()), expected_fingerprint
                ):
                    raise ValueError("Target changed before dispatch")
                attempted = True  # Conservatively set BEFORE entering the injected driver.
                async with asyncio.timeout(SEND_SECONDS):
                    await adapter.mutate(request)
                deadline = time.monotonic() + POST_SECONDS
                while time.monotonic() < deadline:
                    checkpoint()
                    async with asyncio.timeout(
                        min(READ_SECONDS, max(0.001, deadline - time.monotonic()))
                    ):
                        after = await adapter.observe(request)
                    checkpoint()
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Postcondition deadline reached")
                    if adapter.satisfied(request, before, after):
                        self.journal.transition(trial_id, status, "verified")
                        return TrialResult(trial_id, "verified")
                    await asyncio.sleep(min(POLL_SECONDS, max(0, deadline - time.monotonic())))
                raise TimeoutError("Postcondition not confirmed")
            except JournalError:
                raise  # Never acknowledge success if any required journal write failed.
            except asyncio.CancelledError:
                self.journal.transition(
                    trial_id, status, "unknown" if attempted else "not_dispatched"
                )
                raise
            except Exception:  # noqa: BLE001 — fixture boundary never exposes driver details
                result: Literal["unknown", "not_dispatched"] = (
                    "unknown" if attempted else "not_dispatched"
                )
                self.journal.transition(trial_id, status, result)
                return TrialResult(trial_id, result)
