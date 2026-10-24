"""Bounded diagnostic built from allowlisted scalars; no raw logs or identity fields."""

import math
import platform
import uuid
from collections import Counter
from typing import Any

from .alerts import fresh
from .storage import StorageError, Store
from .system import timestamp


def number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and 0 <= value <= 10**20 else None
    except OverflowError:
        return None


def counters(rows, key: str, allowed: set[str]):
    counts = Counter(
        row.get(key)
        for row in rows
        if isinstance(row, dict) and isinstance(row.get(key), str) and row.get(key) in allowed
    )
    return {state: counts[state] for state in sorted(allowed)}


def build_report(metrics, ai, services, containers, store: Store, storage_ready: bool):
    operation = str(uuid.uuid4())
    report: dict[str, Any] = {
        "schema_version": 1,
        "application": {"name": "Cockpitor", "version": "0.1.0"},
        "operation_id": operation,
        "status": "completed",
        "generated_at": timestamp(),
        "privacy": {
            "policy": "allowlist-v1",
            "excluded": [
                "hostname",
                "usernames",
                "processes",
                "paths",
                "network_addresses",
                "integration_urls",
                "model_names",
                "service_names",
                "container_names_ids",
                "environment",
                "commands",
                "logs",
                "event_messages",
                "tokens",
                "rule_targets",
            ],
        },
        "runtime": {
            "system": platform.system(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "system_actions_enabled": False,
        },
        "storage": {"status": "unavailable"},
    }
    metrics = metrics or {}
    report["system"] = {
        "status": "available" if fresh(metrics, 15) else "stale" if metrics else "unavailable",
        "cpu_percent": number(metrics.get("cpu_percent")),
        "uptime_seconds": number(metrics.get("uptime_seconds")),
        "memory": {
            key: number(metrics.get("memory", {}).get(key))
            for key in ("total", "used", "available", "percent")
        },
        "swap": {
            key: number(metrics.get("swap", {}).get(key)) for key in ("total", "used", "percent")
        },
        "network": {
            key: number(metrics.get("network", {}).get(key)) for key in ("received_bps", "sent_bps")
        },
        "filesystems": [
            {
                "alias": f"filesystem-{index + 1}",
                **{key: number(disk.get(key)) for key in ("total", "used", "percent")},
            }
            for index, disk in enumerate(metrics.get("disks", [])[:64])
        ],
    }
    report["ai"] = {}
    for name in ("ollama", "openwebui"):
        data = (ai or {}).get(name, {})
        status = data.get("status")
        report["ai"][name] = {
            "status": status if status in {"available", "unavailable", "disabled"} else "unknown"
        }
        if name == "ollama":
            for key in ("models", "loaded"):
                report["ai"][name][key + "_count"] = (
                    len(data[key]) if isinstance(data.get(key), list) else None
                )
    report["ai"]["fresh"] = fresh(ai, 40)
    report["services"] = {
        "fresh": fresh(services, 40),
        "status": "available" if (services or {}).get("status") == "available" else "unavailable",
        "counts": counters(
            (services or {}).get("items", []),
            "active",
            {"active", "inactive", "failed", "activating", "deactivating"},
        ),
    }
    report["containers"] = []
    for engine in (containers or {}).get("engines", [])[:2]:
        if engine.get("name") not in {"docker", "podman"}:
            continue
        report["containers"].append(
            {
                "engine": engine["name"],
                "fresh": fresh(containers, 40),
                "status": engine.get("status")
                if engine.get("status") in {"available", "unavailable", "disabled"}
                else "unknown",
                "counts": counters(
                    engine.get("containers", []),
                    "state",
                    {"running", "exited", "created", "paused", "dead", "restarting", "removing"},
                ),
            }
        )
    if storage_ready:
        try:
            settings = store.preferences()
            summary = store.diagnostic_summary()
            store.audit(operation, "diagnostics.export")
            report["storage"] = {"status": "available", "schema_version": 3, **summary}
            report["preferences"] = {
                key: getattr(settings, key)
                for key in ("theme", "language", "refresh_seconds", "retention_days")
            }
            report["rules"] = [
                {
                    key: getattr(rule, key)
                    for key in ("metric", "enabled", "threshold", "duration_seconds", "severity")
                }
                for rule in settings.rules
            ]
            report["audit_recorded"] = True
        except StorageError:
            report["audit_recorded"] = False
    else:
        report["audit_recorded"] = False
    return report
