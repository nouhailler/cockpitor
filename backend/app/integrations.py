"""Optional HTTP integrations. Fixed read operations, bounded responses, no redirects."""

import asyncio
import ipaddress
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .system import timestamp

MAX_RESPONSE = 2 * 1024 * 1024


class Details(BaseModel):
    model_config = ConfigDict(extra="ignore")
    family: str | None = Field(default=None, max_length=512)
    quantization_level: str | None = Field(default=None, max_length=512)


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(max_length=512)
    size: int | None = Field(default=None, ge=0)
    details: Details = Field(default_factory=Details)
    size_vram: int | None = Field(default=None, ge=0)


class Models(BaseModel):
    models: list[Model] = Field(max_length=10000)


class Container(BaseModel):
    model_config = ConfigDict(extra="ignore")
    Id: str
    Names: list[str]
    Image: str
    State: str
    Status: str = ""
    Ports: list[dict[str, Any]] = Field(default_factory=list)


def local_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("Invalid local URL")
    # Numeric loopback only: no DNS lookup/rebinding, userinfo, path, query or fragment.
    if not parsed.hostname or not ipaddress.ip_address(parsed.hostname).is_loopback:
        raise ValueError("Loopback required")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Base URL required")
    _ = parsed.port
    return value.rstrip("/")


async def read(client: httpx.AsyncClient, url: str, *, as_json: bool = True) -> Any:
    async with asyncio.timeout(4):
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError("Redirect refused")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE:
                    raise ValueError("Response too large")
            return json.loads(body) if as_json else None


async def ai_status() -> dict[str, Any]:
    async def check(name: str, configured: str | None) -> dict[str, Any]:
        result: dict[str, Any] = {"collected_at": timestamp(), "status": "unavailable"}
        if not configured:
            return {**result, "status": "disabled", "message": "URL locale non configurée"}
        try:
            url = local_url(configured)
            start = time.monotonic()
            async with httpx.AsyncClient(
                timeout=2, follow_redirects=False, trust_env=False
            ) as client:
                if name == "ollama":
                    models = Models.model_validate(await read(client, url + "/api/tags"))
                    result["models"] = [
                        {
                            "name": m.name,
                            "size": m.size,
                            "family": m.details.family,
                            "quantization": m.details.quantization_level,
                        }
                        for m in models.models
                    ]
                    try:
                        loaded = Models.model_validate(await read(client, url + "/api/ps"))
                        result["loaded"] = [
                            {"name": m.name, "size_vram": m.size_vram} for m in loaded.models
                        ]
                    except (httpx.HTTPError, ValueError, TimeoutError):
                        result["message"] = "Modèles chargés indisponibles pour cette API"
                else:
                    await read(client, url + "/", as_json=False)
            result.update(status="available", url=url, latency_ms=(time.monotonic() - start) * 1000)
        except (httpx.HTTPError, ValueError, TimeoutError):
            result["message"] = "Service inaccessible, URL refusée ou réponse incompatible"
        return result

    ollama, openwebui = await asyncio.gather(
        check("ollama", os.environ.get("LOCALCOCKPIT_OLLAMA_URL", "http://127.0.0.1:11434")),
        check("openwebui", os.environ.get("LOCALCOCKPIT_OPENWEBUI_URL")),
    )
    return {"collected_at": timestamp(), "status": "ok", "ollama": ollama, "openwebui": openwebui}


async def container_status() -> dict[str, Any]:
    async def engine(name: str, default: str) -> dict[str, Any]:
        result: dict[str, Any] = {"name": name, "status": "disabled", "containers": []}
        configured = os.environ.get(f"LOCALCOCKPIT_{name.upper()}_SOCKET")
        if not configured:
            result["message"] = "Accès au socket non activé ; aucune permission modifiée"
            if not Path(default).exists():
                result.update(status="unavailable", message="Socket non détecté")
            return result
        if not Path(configured).is_absolute():
            return {**result, "message": "Un chemin absolu de socket est requis"}
        try:
            transport = httpx.AsyncHTTPTransport(uds=configured)
            async with httpx.AsyncClient(transport=transport, timeout=2, trust_env=False) as client:
                version = await read(client, "http://localhost/version")
                if not isinstance(version, dict) or not isinstance(version.get("Version"), str):
                    raise ValueError("Invalid version")  # noqa: TRY004 — protocol validation
                rows = await read(client, "http://localhost/containers/json?all=true")
                if not isinstance(rows, list) or len(rows) > 10000:
                    raise ValueError("Invalid container list")
                containers = [Container.model_validate(row) for row in rows]
                result.update(
                    status="available",
                    version=version["Version"],
                    containers=[
                        {
                            "id": c.Id,
                            "name": ", ".join(n.lstrip("/") for n in c.Names),
                            "image": c.Image,
                            "state": c.State,
                            "status": c.Status,
                            "ports": [
                                f"{p.get('IP', '')}:{p['PublicPort']} → "
                                f"{p.get('PrivatePort', '?')}/{p.get('Type', '?')}"
                                for p in c.Ports
                                if "PublicPort" in p
                            ],
                        }
                        for c in containers
                    ],
                )
        except (httpx.HTTPError, ValueError, OSError, TimeoutError):
            result.update(
                status="unavailable",
                message="Socket inaccessible, permissions insuffisantes ou API incompatible",
            )
        return result

    docker, podman = await asyncio.gather(
        engine("docker", "/var/run/docker.sock"),
        engine("podman", f"/run/user/{os.getuid()}/podman/podman.sock"),
    )
    return {"collected_at": timestamp(), "status": "ok", "engines": [docker, podman]}
