"""Minimal availability summary from cached observations; never triggers probes."""

import platform
import re

from .alerts import fresh


def observation_status(source, max_age, status=None):
    if not source:
        return "collecting"
    if not fresh(source, max_age):
        return "stale"
    value = source.get("status") if status is None else status
    return value if value in {"available", "unavailable", "disabled"} else "unavailable"


def availability(state):
    ai = state.ai or {}
    containers = state.containers or {}
    engines = {
        engine.get("name"): engine.get("status")
        for engine in containers.get("engines", [])
        if engine.get("name") in {"docker", "podman"}
    }
    modules = [
        ("system", observation_status(state.snapshot, 15, "available")),
        ("monitoring", observation_status(state.inspection, 90, "available")),
        ("services", observation_status(state.services, 40)),
    ]
    for name in ("ollama", "openwebui"):
        source = ai.get(name)
        modules.append((name, observation_status(source, 40)))
    for name in ("docker", "podman"):
        modules.append((name, observation_status(containers, 40, engines.get(name, "unavailable"))))
    # No hostname, paths, addresses, model/service/container identities or raw errors.
    kernel = re.match(r"\d+(?:\.\d+){0,3}", platform.release())
    return {
        "environment": {
            "os": platform.system()[:32],
            "kernel_version": kernel.group() if kernel else None,
            "python_version": platform.python_version(),
        },
        "modules": [{"id": name, "status": status} for name, status in modules],
    }
