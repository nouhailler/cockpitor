"""Approval lifecycle for simulations only. There is deliberately no command executor."""

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .services import ServiceError, validate_unit
from .storage import StorageError, Store

Action = Literal[
    "service.start", "service.stop", "service.restart", "container.start", "container.restart"
]
ACTIONS = (
    "service.start",
    "service.stop",
    "service.restart",
    "container.start",
    "container.restart",
)
TERMINAL = {"simulated", "cancelled", "expired", "rejected", "failed", "interrupted"}
PLAN_SECONDS = 120
APPROVAL_SECONDS = 60
SIMULATION_SECONDS = 8


def fail(code, message, status=409):
    raise ServiceError(code, message, status)


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Action
    target: str = Field(min_length=1, max_length=200)
    engine: Literal["docker", "podman"] | None = None

    @model_validator(mode="after")
    def target_policy(self):
        if self.action.startswith("service."):
            validate_unit(self.target)
            if self.engine is not None:
                raise ValueError("No engine for services")
            if re.fullmatch(
                r"(?:ssh|sshd|dbus|systemd-.*|NetworkManager|networking|cockpitor|localcockpit|polkit|user@.*)\.service",
                self.target,
            ):
                raise ValueError("Critical service excluded")
        elif not re.fullmatch(r"[a-f0-9]{64}", self.target) or self.engine is None:
            raise ValueError("Exact engine and container required")
        return self


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    plan_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class Approval(Reference):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: bool

    @model_validator(mode="after")
    def explicit(self):
        if self.confirmed is not True:
            raise ValueError("Explicit confirmation required")
        return self


class Simulation(Reference):
    approval_token: str = Field(min_length=32, max_length=128)


def fingerprint(request: ActionRequest, snapshot: dict) -> str:
    payload = {"request": request.model_dump(), "snapshot": snapshot}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass
class Plan:
    id: str
    owner: str
    request: ActionRequest
    snapshot: dict
    fingerprint: str
    deadline: float
    status: str = "prepared"
    approval_hash: str | None = None
    approval_deadline: float = 0
    task: asyncio.Task | None = None


class SimulationVerifier(Protocol):
    async def verify(
        self,
        operation_id: str,
        request: ActionRequest,
        expected_fingerprint: str,
        checkpoint: Callable[[], None],
        *,
        owner: str | None = None,
    ) -> None: ...


class ActionEngine:
    def __init__(
        self,
        store: Store,
        probe: Callable[[ActionRequest], Awaitable[dict]],
        valid: Callable[[str], bool],
        clock=time.monotonic,
        verifier: SimulationVerifier | None = None,
    ):
        self.verifier = verifier
        self.store, self.probe, self.valid, self.clock = store, probe, valid, clock
        self.plans: dict[str, Plan] = {}
        self.lock = asyncio.Lock()
        self.running: str | None = None

    def policy(self, owner):
        if not self.valid(owner):
            fail("SESSION_EXPIRED", "Session expirée", 401)

    def get(self, owner, plan_id):
        self.policy(owner)
        plan = self.plans.get(plan_id)
        if plan is None or not hmac.compare_digest(plan.owner, owner):
            fail("PLAN_NOT_FOUND", "Plan introuvable pour cette session", 404)
        return plan

    async def transition(self, plan, status):
        await asyncio.to_thread(self.store.action_transition, plan.id, plan.status, status)
        plan.status = status
        if status != "approved":
            plan.approval_hash = None

    async def snapshot(self, request):
        try:
            return await asyncio.wait_for(self.probe(request), timeout=SIMULATION_SECONDS)
        except TimeoutError as exc:
            raise ServiceError("ACTION_TIMEOUT", "Délai des contrôles dépassé", 504) from exc

    async def check(self, plan):
        self.policy(plan.owner)
        if self.clock() >= plan.deadline or (
            plan.status == "approved" and self.clock() >= plan.approval_deadline
        ):
            await self.transition(plan, "expired")
            fail("PLAN_EXPIRED", "Plan ou approbation expiré")
        snapshot = await self.snapshot(plan.request)
        self.policy(plan.owner)
        if fingerprint(plan.request, snapshot) != plan.fingerprint:
            await self.transition(plan, "rejected")
            fail("TARGET_CHANGED", "La cible a changé ; préparez un nouveau plan")
        if self.clock() >= plan.deadline or (
            plan.status == "approved" and self.clock() >= plan.approval_deadline
        ):
            await self.transition(plan, "expired")
            fail("PLAN_EXPIRED", "Plan ou approbation expiré")

    def view(self, plan):
        return {
            "id": plan.id,
            "action": plan.request.action,
            "target": plan.request.target,
            "engine": plan.request.engine,
            "status": plan.status,
            "fingerprint": plan.fingerprint,
            "snapshot": plan.snapshot,
            "expires_seconds": max(0, int(plan.deadline - self.clock())),
            "approval_expires_seconds": max(0, int(plan.approval_deadline - self.clock()))
            if plan.status == "approved"
            else 0,
            "mode": "simulation",
            "system_execution_enabled": False,
        }

    async def prepare(self, owner, request):
        self.policy(owner)
        snapshot = await self.snapshot(request)
        async with self.lock:
            self.policy(owner)
            # Bounded memory: old terminal plans can be forgotten, never active approvals.
            self.plans = {
                key: value for key, value in self.plans.items() if value.status not in TERMINAL
            }
            if len(self.plans) >= 64:
                fail("PLAN_LIMIT", "Trop de plans en attente", 429)
            plan = Plan(
                uuid.uuid4().hex,
                owner,
                request,
                snapshot,
                fingerprint(request, snapshot),
                self.clock() + PLAN_SECONDS,
            )
            await asyncio.to_thread(self.store.action_create, plan.id, request.action)
            self.plans[plan.id] = plan
            return self.view(plan)

    async def approve(self, owner, payload):
        async with self.lock:
            plan = self.get(owner, payload.plan_id)
            if plan.status != "prepared":
                fail("PLAN_STATE", "Ce plan ne peut plus être approuvé")
            if not hmac.compare_digest(plan.fingerprint, payload.fingerprint):
                fail("PLAN_MISMATCH", "Empreinte du plan invalide", 422)
            await self.check(plan)
            token = secrets.token_urlsafe(32)
            await self.transition(plan, "approved")
            plan.approval_hash = hashlib.sha256(token.encode()).hexdigest()
            plan.approval_deadline = min(plan.deadline, self.clock() + APPROVAL_SECONDS)
            return {"plan": self.view(plan), "approval_token": token}

    async def simulate(self, owner, payload):
        async with self.lock:
            plan = self.get(owner, payload.plan_id)
            if plan.status != "approved" or not plan.approval_hash:
                fail("APPROVAL_REQUIRED", "Approbation ponctuelle requise")
            if not hmac.compare_digest(
                plan.approval_hash, hashlib.sha256(payload.approval_token.encode()).hexdigest()
            ):
                fail("APPROVAL_INVALID", "Approbation invalide", 403)
            if self.running:
                fail("ACTION_BUSY", "Une simulation est déjà en cours", 429)
            await self.check(plan)
            # Persist the consumed approval and start event before entering the simulation.
            await self.transition(plan, "simulating")
            self.running = plan.id
            plan.task = asyncio.create_task(self.run(plan))
        try:
            return await plan.task
        finally:
            plan.task = None
            self.running = None

    def checkpoint(self, plan):
        self.policy(plan.owner)
        if self.clock() >= plan.deadline:
            fail("PLAN_EXPIRED", "Plan ou approbation expiré")

    async def run(self, plan):
        try:
            async with asyncio.timeout(SIMULATION_SECONDS):
                await self.check(plan)
                await asyncio.sleep(0)  # Cancellation checkpoint; deliberately no executor.
                if self.verifier is not None:
                    await self.verifier.verify(
                        plan.id,
                        plan.request,
                        plan.fingerprint,
                        lambda: self.checkpoint(plan),
                        owner=plan.owner,
                    )
                    self.checkpoint(plan)
                    await asyncio.to_thread(self.store.action_verification, plan.id)
                self.checkpoint(plan)
                await self.transition(plan, "simulated")
                self.policy(plan.owner)
                return {
                    "plan": self.view(plan),
                    "commands_executed": False,
                    "system_changed": False,
                    "transport_verified": self.verifier is not None,
                }
        except asyncio.CancelledError as exc:
            if plan.status not in TERMINAL:
                await self.transition(plan, "cancelled")
            raise ServiceError("ACTION_CANCELLED", "Simulation annulée", 409) from exc
        except TimeoutError as exc:
            if plan.status not in TERMINAL:
                await self.transition(plan, "failed")
            raise ServiceError("ACTION_TIMEOUT", "Délai des contrôles dépassé", 504) from exc
        except ServiceError as exc:
            if plan.status not in TERMINAL:
                await self.transition(plan, "expired" if exc.code == "PLAN_EXPIRED" else "failed")
            raise
        except StorageError:
            plan.approval_hash = None
            raise  # No success without a committed final audit; recovered as interrupted.

        except Exception as exc:
            if plan.status not in TERMINAL:
                await self.transition(plan, "failed")
            raise ServiceError(
                "ACTION_FAILED", "Simulation échouée ; consultez l’historique", 503
            ) from exc

    async def cancel(self, owner, plan_id):
        async with self.lock:
            plan = self.get(owner, plan_id)
            task = plan.task
            if task:
                task.cancel()
            else:
                if plan.status in TERMINAL:
                    fail("PLAN_STATE", "Ce plan est déjà terminé")
                await self.transition(plan, "cancelled")
        if task:
            results = await asyncio.gather(task, return_exceptions=True)
            if isinstance(results[0], StorageError):
                raise results[0]
            if plan.status != "cancelled":
                fail(
                    "ACTION_CANCEL_NOT_CONFIRMED",
                    "Annulation non confirmée ; consultez l’historique",
                    409,
                )
        return self.view(plan)

    async def cleanup(self):
        async with self.lock:
            for plan in self.plans.values():
                if plan.status in TERMINAL:
                    continue
                if (
                    not self.valid(plan.owner)
                    or self.clock() >= plan.deadline
                    or (plan.status == "approved" and self.clock() >= plan.approval_deadline)
                ):
                    if plan.task:
                        plan.task.cancel()
                    else:
                        await self.transition(plan, "expired")

    async def close(self):
        tasks = [plan.task for plan in self.plans.values() if plan.task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
