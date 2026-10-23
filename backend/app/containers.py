"""Docker-compatible read API over explicitly configured Unix sockets only."""

import asyncio
import math
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .integrations import api_prefix, read
from .redaction import redact
from .system import timestamp

ID_PATTERN = r"[a-f0-9]{64}"


class ContainerError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class SafeModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class State(SafeModel):
    Status: str = Field(max_length=100)
    Running: bool
    ExitCode: int | None = None
    OOMKilled: bool | None = None
    StartedAt: str | None = None
    FinishedAt: str | None = None


class Config(SafeModel):
    Image: str = Field(max_length=2048)
    Tty: bool


class Inspect(SafeModel):
    Id: str = Field(pattern="^" + ID_PATTERN + "$")
    Name: str = Field(max_length=2048)
    Created: str | None = None
    State: State
    Config: Config


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if math.isfinite(result) and result >= 0 else None


def statistics(data: dict[str, Any]) -> dict[str, Any]:
    cpu = None
    try:
        current, previous = data["cpu_stats"], data["precpu_stats"]
        total = number(current["cpu_usage"]["total_usage"])
        prev = number(previous["cpu_usage"]["total_usage"])
        system = number(current["system_cpu_usage"])
        prev_system = number(previous["system_cpu_usage"])
        count = number(current.get("online_cpus"))
        if not count and isinstance(current["cpu_usage"].get("percpu_usage"), list):
            count = len(current["cpu_usage"]["percpu_usage"])
        if (
            total is not None
            and prev is not None
            and system is not None
            and prev_system is not None
            and count is not None
            and system > prev_system
            and total >= prev
            and count > 0
        ):
            value = (total - prev) / (system - prev_system) * count * 100
            cpu = value if math.isfinite(value) else None
    except (KeyError, TypeError):
        pass
    memory = data.get("memory_stats")
    memory = memory if isinstance(memory, dict) else {}
    return {
        "cpu_percent": cpu,
        "memory_usage_bytes": number(memory.get("usage")),
        "memory_limit_bytes": number(memory.get("limit")),
        "sample_at": data.get("read") if isinstance(data.get("read"), str) else None,
        "note": "Instantané CPU par cœur (peut dépasser 100 %) ; mémoire brute, cache inclus",
    }


def decode_logs(body: bytes, tty: bool, tail: int) -> list[dict[str, str]]:
    # Reassemble per stream before splitting lines: a frame is not necessarily a line.
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    if tty:
        streams["stdout"].extend(body)
    else:
        offset = 0
        while offset < len(body):
            if len(body) - offset < 8:
                raise ValueError("Truncated frame")
            header = body[offset : offset + 8]
            length = int.from_bytes(header[4:8], "big")
            if header[0] not in {1, 2} or header[1:4] != b"\0\0\0":
                raise ValueError("Unknown log framing")
            offset += 8
            if length > len(body) - offset:
                raise ValueError("Truncated log body")
            streams["stdout" if header[0] == 1 else "stderr"].extend(body[offset : offset + length])
            offset += length
    rows = []
    for stream, buffer in streams.items():
        # Redact complete text before splitting (handles multi-line credentials).
        for line in redact(buffer.decode("utf-8", errors="replace")).splitlines()[-tail:]:
            rows.append({"stream": stream, "message": line})
    # stdout/stderr grouping is deliberate: never pretend to reconstruct a global order.
    return rows


class Containers:
    def __init__(self) -> None:
        self.slots = asyncio.Semaphore(2)

    @asynccontextmanager
    async def connection(self, engine: str, container_id: str):
        if engine not in {"docker", "podman"} or not re.fullmatch(ID_PATTERN, container_id):
            raise ContainerError(
                "INVALID_CONTAINER", "Moteur ou identifiant de conteneur invalide", 422
            )
        socket = os.environ.get(f"LOCALCOCKPIT_{engine.upper()}_SOCKET")
        if not socket:
            raise ContainerError("ENGINE_DISABLED", "Accès au moteur non activé", 409)
        if not Path(socket).is_absolute():
            raise ContainerError("INVALID_SOCKET", "Configuration du socket invalide", 503)
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=0.25)
        except TimeoutError as exc:
            raise ContainerError("BUSY", "Trop de lectures de conteneurs simultanées", 429) from exc
        try:
            async with asyncio.timeout(6):
                async with httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport(uds=socket),
                    timeout=2,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    prefix, _ = await api_prefix(client)
                    yield client, f"http://localhost{prefix}/containers/{container_id}"
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            codes = {
                403: ("PERMISSION_DENIED", "Droits de lecture du moteur insuffisants", 403),
                404: ("CONTAINER_NOT_FOUND", "Conteneur ou fonction API introuvable", 404),
                409: ("CONTAINER_CONFLICT", "Statistiques indisponibles dans cet état", 409),
                501: ("CAPABILITY_UNAVAILABLE", "Fonction non prise en charge par le moteur", 503),
            }
            code, message, public_status = codes.get(
                status, ("ENGINE_ERROR", "Lecture du moteur refusée", 503)
            )
            raise ContainerError(code, message, public_status) from exc
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            raise ContainerError(
                "ENGINE_UNAVAILABLE", "Moteur inaccessible ou délai dépassé"
            ) from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise ContainerError(
                "INVALID_RESPONSE", "Réponse moteur incompatible ou trop volumineuse"
            ) from exc
        finally:
            self.slots.release()

    async def inspect(self, client: httpx.AsyncClient, url: str, container_id: str) -> Inspect:
        data = Inspect.model_validate(await read(client, url + "/json"))
        if data.Id != container_id:
            raise ValueError("Container identity mismatch")
        return data

    async def detail(self, engine: str, container_id: str) -> dict[str, Any]:
        async with self.connection(engine, container_id) as (client, url):
            data = await self.inspect(client, url, container_id)
            return {
                "id": data.Id,
                "engine": engine,
                "name": redact(data.Name.lstrip("/")),
                "image": redact(data.Config.Image),
                "created": data.Created,
                "state": data.State.model_dump(),
                "tty": data.Config.Tty,
                "collected_at": timestamp(),
            }

    async def stats(self, engine: str, container_id: str) -> dict[str, Any]:
        async with self.connection(engine, container_id) as (client, url):
            data = await read(client, url + "/stats?stream=false")
            if not isinstance(data, dict):
                raise TypeError("Invalid statistics")
            return {
                "id": container_id,
                "engine": engine,
                "collected_at": timestamp(),
                **statistics(data),
            }

    async def logs(self, engine: str, container_id: str, tail: int, period: int) -> dict[str, Any]:
        async with self.connection(engine, container_id) as (client, url):
            data = await self.inspect(client, url, container_id)
            body = await read(
                client,
                url + f"/logs?stdout=true&stderr=true&follow=false&"
                f"timestamps=true&tail={tail}&since={int(time.time()) - period}",
                raw=True,
            )
            rows = decode_logs(body, data.Config.Tty, tail)
            return {
                "id": container_id,
                "engine": engine,
                "items": rows,
                "tail_per_stream": tail,
                "collected_at": timestamp(),
                "ordering": "grouped_by_stream",
                "tty": data.Config.Tty,
            }
