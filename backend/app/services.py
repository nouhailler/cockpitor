"""Read-only systemd/journald adapter with bounded subprocesses and exact unit names."""

import asyncio
import json
import os
import re
import time
from typing import Any

from .system import timestamp

MAX_OUTPUT = 2 * 1024 * 1024
COMMAND_TIMEOUT = 5
UNIT_PATTERN = r"[A-Za-z0-9_](?:[A-Za-z0-9_:@.\-]|\\x[0-9a-fA-F]{2})*\.service"
CURSOR_PATTERN = r"[A-Za-z0-9;=_:\-]{1,1024}"
PROPERTIES = (
    "Id",
    "Description",
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "MainPID",
    "Result",
    "ActiveEnterTimestamp",
    "InactiveEnterTimestamp",
    "Requires",
    "After",
)


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def validate_unit(unit: str) -> str:
    if len(unit) > 200 or not re.fullmatch(UNIT_PATTERN, unit):
        raise ServiceError("INVALID_UNIT", "Nom de service invalide", 422)
    return unit


def redact(text: str) -> str:
    # Best effort: do not claim to discover all application-specific secrets.
    token = os.environ.get("LOCALCOCKPIT_TOKEN")
    if token:
        text = text.replace(token, "[MASQUÉ]")
    text = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|$)",
        "[CLÉ PRIVÉE MASQUÉE]",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]+", r"\1[MASQUÉ]", text)
    return re.sub(
        r"""(?ix)(["']?(?:password|passwd|token|api[_-]?key|secret)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,;]+)""",
        r"\1[MASQUÉ]",
        text,
    )


class Services:
    def __init__(self) -> None:
        self.slots = asyncio.Semaphore(2)

    async def command(self, *args: str) -> tuple[str, str]:
        if args[0] not in {"/usr/bin/systemctl", "/usr/bin/journalctl"}:
            raise ServiceError("COMMAND_REFUSED", "Commande non autorisée", 403)
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=0.25)
        except TimeoutError as exc:
            raise ServiceError("BUSY", "Trop de lectures simultanées ; réessayez", 429) from exc
        process = None
        try:
            async with asyncio.timeout(COMMAND_TIMEOUT):
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={
                        "PATH": "/usr/bin:/bin",
                        "LANG": "C",
                        "LC_ALL": "C",
                        "SYSTEMD_COLORS": "0",
                        "SYSTEMD_PAGERSECURE": "1",
                    },
                )

                async def bounded(stream, size):
                    data = bytearray()
                    while chunk := await stream.read(65536):
                        data.extend(chunk)
                        if len(data) > size:
                            raise ServiceError("OUTPUT_LIMIT", "Volume de lecture dépassé")
                    return data.decode("utf-8", errors="replace")

                out_task = asyncio.create_task(bounded(process.stdout, MAX_OUTPUT))
                err_task = asyncio.create_task(bounded(process.stderr, 8192))
                try:
                    out, err = await asyncio.gather(out_task, err_task)
                    await process.wait()
                finally:
                    for task in (out_task, err_task):
                        task.cancel()
                    await asyncio.gather(out_task, err_task, return_exceptions=True)
                if process.returncode:
                    if "permission" in err.lower() or "access denied" in err.lower():
                        raise ServiceError(
                            "PERMISSION_DENIED", "Droits de lecture insuffisants", 403
                        )
                    raise ServiceError(
                        "SYSTEMD_UNAVAILABLE", "systemd/journald inaccessible ou unité inconnue"
                    )
                return out, err
        except TimeoutError as exc:
            raise ServiceError("COMMAND_TIMEOUT", "Délai de lecture dépassé") from exc
        except OSError as exc:
            raise ServiceError(
                "SYSTEMD_UNAVAILABLE", "Outil système absent ou inaccessible"
            ) from exc
        finally:
            if process and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.communicate()
            self.slots.release()

    async def inventory(self) -> dict[str, Any]:
        try:
            out, _ = await self.command(
                "/usr/bin/systemctl",
                "list-units",
                "--type=service",
                "--all",
                "--plain",
                "--no-legend",
                "--no-pager",
                "--full",
                "--no-ask-password",
            )
            items = []
            for line in out.splitlines():
                if not line.strip():
                    continue
                fields = line.split(None, 4)
                if len(fields) != 5:
                    raise ServiceError("INVALID_RESPONSE", "Inventaire systemd incompatible")
                unit, load, active, sub, description = fields
                validate_unit(unit)
                items.append(
                    {
                        "unit": unit,
                        "description": redact(description),
                        "load": load,
                        "active": active,
                        "sub": sub,
                    }
                )
            return {"status": "available", "items": items, "collected_at": timestamp()}
        except ServiceError as exc:
            return {
                "status": "unavailable",
                "items": [],
                "collected_at": timestamp(),
                "code": exc.code,
                "message": exc.message,
            }

    async def detail(self, unit: str) -> dict[str, Any]:
        validate_unit(unit)
        out, _ = await self.command(
            "/usr/bin/systemctl",
            "show",
            "--no-pager",
            "--no-ask-password",
            "--property=" + ",".join(PROPERTIES),
            "--",
            unit,
        )
        properties = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        if properties.get("LoadState") == "not-found":
            raise ServiceError("UNIT_NOT_FOUND", "Service introuvable", 404)
        if properties.get("Id") != unit:
            raise ServiceError("INVALID_RESPONSE", "Identité du service non confirmée")
        return {
            "unit": unit,
            "collected_at": timestamp(),
            "properties": {k: redact(v) for k, v in properties.items() if k in PROPERTIES},
        }

    async def logs(
        self, unit: str, limit: int, period: int, priority: int, q: str, cursor: str | None
    ) -> dict[str, Any]:
        validate_unit(unit)
        if cursor and not re.fullmatch(CURSOR_PATTERN, cursor):
            raise ServiceError("INVALID_CURSOR", "Curseur invalide", 422)
        args = [
            "/usr/bin/journalctl",
            "--system",
            "--no-pager",
            "--output=json",
            "--output-fields=MESSAGE,PRIORITY",
            "--reverse",
            f"--unit={unit}",
            f"--lines={limit + 2}",
            f"--since=@{int(time.time()) - period}",
            f"--priority={priority}",
        ]
        if cursor:
            args.append(f"--cursor={cursor}")
        out, err = await self.command(*args)
        # Do not suppress journalctl's visibility warnings with --quiet.
        if err.strip():
            raise ServiceError(
                "JOURNAL_ACCESS_UNCERTAIN",
                "Journaux incomplets ou droits insuffisants ; lecture non confirmée",
                403,
            )
        try:
            rows = [json.loads(line) for line in out.splitlines() if line.strip()]
            if any(not isinstance(row, dict) for row in rows):
                raise ValueError("Invalid entry")
            if cursor:
                if not rows or rows[0].get("__CURSOR") != cursor:
                    raise ServiceError(
                        "CURSOR_EXPIRED", "Curseur indisponible ; actualisez les journaux", 409
                    )
                rows = rows[1:]
            page = rows[:limit]
            items = []
            for row in page:
                entry_cursor = row.get("__CURSOR")
                if not isinstance(entry_cursor, str) or not re.fullmatch(
                    CURSOR_PATTERN, entry_cursor
                ):
                    raise ValueError("Missing cursor")
                message = row.get("MESSAGE")
                message = (
                    redact(message)
                    if isinstance(message, str)
                    else "[Message binaire ou indisponible]"
                )
                if q.lower() not in message.lower():
                    continue
                items.append(
                    {
                        "message": message,
                        "priority": str(row.get("PRIORITY", "?")),
                        "timestamp_us": str(row.get("__REALTIME_TIMESTAMP", "")),
                    }
                )
            return {
                "unit": unit,
                "items": items,
                "scanned": len(page),
                "next_cursor": page[-1]["__CURSOR"] if len(rows) > limit and page else None,
                "collected_at": timestamp(),
                "text_filter_scope": "page",
            }
        except (ValueError, TypeError, KeyError) as exc:
            raise ServiceError("INVALID_RESPONSE", "Réponse journald incompatible") from exc
