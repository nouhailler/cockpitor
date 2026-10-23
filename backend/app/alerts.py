"""Sustained local thresholds. Unknown observations never resolve active alerts."""

import math
import time
from datetime import datetime
from typing import Any

from .preferences import Preferences, Rule
from .storage import Store
from .system import timestamp


def fresh(source: dict | None, max_age: int) -> bool:
    if not source or not source.get("collected_at"):
        return False
    try:
        age = time.time() - datetime.fromisoformat(source["collected_at"]).timestamp()
        return -5 <= age <= max_age
    except (ValueError, TypeError):
        return False


def observation(rule: Rule, metrics, ai, services, containers) -> float | None:
    value = None
    if rule.metric in {"cpu_percent", "memory_percent", "swap_percent", "disk_free_percent"}:
        if not fresh(metrics, 15):
            return None
        if rule.metric == "cpu_percent":
            value = metrics.get("cpu_percent")
        elif rule.metric == "memory_percent":
            value = metrics.get("memory", {}).get("percent")
        elif rule.metric == "swap_percent":
            if metrics.get("swap", {}).get("total", 0) > 0:
                value = metrics["swap"].get("percent")
        else:
            for disk in metrics.get("disks", []):
                if (
                    disk["mount"] == rule.target
                    and not disk.get("error")
                    and disk.get("percent") is not None
                ):
                    value = 100 - disk["percent"]
    elif rule.metric == "ollama_unavailable":
        if fresh(ai, 40):
            status = ai.get("ollama", {}).get("status")
            value = 1 if status == "unavailable" else 0 if status == "available" else None
    elif rule.metric == "service_failed":
        if fresh(services, 40) and services.get("status") == "available":
            for service in services.get("items", []):
                if service["unit"] == rule.target:
                    value = int(service["active"] == "failed")
    elif rule.metric == "container_stopped" and fresh(containers, 40):
        for engine in containers.get("engines", []):
            if engine["name"] == rule.engine and engine["status"] == "available":
                for container in engine["containers"]:
                    if container["id"] == rule.target:
                        state = container["state"]
                        value = (
                            0
                            if state == "running"
                            else 1
                            if state in {"exited", "dead", "created", "paused"}
                            else None
                        )
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


class AlertEngine:
    def __init__(self, store: Store):
        self.store = store
        self.pending: dict[str, float] = {}
        self.rules: dict[str, Rule] = {}
        self.last_sample: dict[str, str] = {}
        self.states: list[dict[str, Any]] = []
        self.last_cleanup = 0.0

    def evaluate(
        self, preferences: Preferences, metrics, ai, services, containers, now: float | None = None
    ):
        current = time.monotonic() if now is None else now
        active = self.store.active()
        states = []
        for rule in preferences.rules:
            if self.rules.get(rule.id) != rule:
                self.pending.pop(rule.id, None)
                self.last_sample.pop(rule.id, None)
            value = observation(rule, metrics, ai, services, containers) if rule.enabled else None
            source = (
                ai
                if rule.metric == "ollama_unavailable"
                else services
                if rule.metric == "service_failed"
                else containers
                if rule.metric == "container_stopped"
                else metrics
            )
            sample_id = (source or {}).get("collected_at", "")
            new_sample = self.last_sample.get(rule.id) != sample_id
            status = "unavailable" if rule.enabled else "disabled"
            if value is None:
                self.pending.pop(rule.id, None)
            else:
                boolean = rule.metric in {
                    "ollama_unavailable",
                    "service_failed",
                    "container_stopped",
                }
                triggered = (
                    value == 1
                    if boolean
                    else value < rule.threshold
                    if rule.metric == "disk_free_percent"
                    else value > rule.threshold
                )
                if triggered:
                    start = self.pending.setdefault(rule.id, current)
                    status = "pending"
                    if rule.id in active or (
                        new_sample and current - start >= rule.duration_seconds
                    ):
                        if rule.id not in active:
                            description = (
                                "Condition indisponibilité/état détectée"
                                if boolean
                                else f"Seuil {rule.threshold:g} % franchi ({value:.1f} %)"
                            )
                            self.store.activate(rule.id, rule.severity, description)
                        status = "active"
                else:
                    self.pending.pop(rule.id, None)
                    if rule.id in active:
                        self.store.resolve(active[rule.id])
                    status = "healthy"
            self.last_sample[rule.id] = sample_id
            states.append(
                {
                    "rule_id": rule.id,
                    "metric": rule.metric,
                    "status": status,
                    "value": value,
                    "message": "Source absente, périmée ou non observable"
                    if status == "unavailable"
                    else "",
                    "active": status == "active" or (rule.id in active and value is None),
                }
            )
        self.rules = {r.id: r for r in preferences.rules}
        self.pending = {key: value for key, value in self.pending.items() if key in self.rules}
        self.states = states
        self.evaluated_at = timestamp()
        if current - self.last_cleanup >= 60:
            self.store.cleanup(preferences.retention_days)
            self.last_cleanup = current
