"""Read-only VM prerequisites. A passing report NEVER enables system actions."""

import asyncio
import json
import os
import platform
import re
import signal
import stat
import sys
from pathlib import Path

import httpx

from .i18n import translate
from .integrations import api_prefix
from .system import timestamp

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = {
    "vm": ("/usr/bin/systemd-detect-virt", "--vm"),
    "container": ("/usr/bin/systemd-detect-virt", "--container"),
    "state": ("/usr/bin/systemctl", "is-system-running", "--no-pager", "--no-ask-password"),
    "systemd": ("/usr/bin/systemctl", "--version"),
    "revision": ("/usr/bin/git", "--no-pager", "rev-parse", "--verify", "HEAD"),
    "clean": (
        "/usr/bin/git",
        "--no-pager",
        "-c",
        "core.fsmonitor=false",
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
    ),
}
COMMAND_SECONDS = 2.0
OUTPUT_LIMIT = 4096
PROFILES = {
    "systemd": (),
    "docker": ("docker",),
    "podman": ("podman",),
    "all": ("docker", "podman"),
}


async def command(name: str):
    if name not in COMMANDS:
        raise ValueError("Read command not permitted")
    process, readers = None, []
    completed = False
    try:
        async with asyncio.timeout(COMMAND_SECONDS):
            process = await asyncio.create_subprocess_exec(
                *COMMANDS[name],
                cwd=ROOT,
                start_new_session=True,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "SYSTEMD_COLORS": "0",
                    "GIT_OPTIONAL_LOCKS": "0",
                },
            )

            async def bounded(stream):
                body = bytearray()
                while chunk := await stream.read(1024):
                    body.extend(chunk)
                    if len(body) > OUTPUT_LIMIT:
                        raise ValueError("Read output limit")
                return body.decode("utf-8", errors="replace").strip()

            readers = [
                asyncio.create_task(bounded(process.stdout)),
                asyncio.create_task(bounded(process.stderr)),
            ]
            output, _ = await asyncio.gather(*readers)
            await process.wait()
            completed = True
            return process.returncode, output
    except (OSError, ValueError, TimeoutError):
        return None, ""
    finally:
        for reader in readers:
            reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        if process is not None and not completed:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                async with asyncio.timeout(0.5):
                    await process.communicate()
            except TimeoutError:
                pass


def small_file(path: Path, maximum=4096):
    try:
        with path.open("rb") as stream:
            data = stream.read(maximum + 1)
        return data.decode() if len(data) <= maximum else ""
    except (OSError, UnicodeError):
        return ""


class PreflightProbe:
    async def command(self, name):
        return await command(name)

    def facts(self):
        fields = {}
        for line in small_file(Path("/etc/os-release")).splitlines():
            key, _, value = line.partition("=")
            if key in {"ID", "VERSION_ID"}:
                fields[key] = value.strip('"')
        release = re.match(r"[0-9]+(?:\.[0-9]+){1,2}", platform.release())
        return {
            "non_root": os.geteuid() != 0,
            "debian": fields.get("ID") == "debian",
            "debian_version": fields.get("VERSION_ID", ""),
            "systemd_pid1": small_file(Path("/proc/1/comm"), 64).strip() == "systemd",
            "python_supported": sys.version_info >= (3, 11),
            "python": platform.python_version(),
            "kernel": release[0] if release else None,
        }

    async def engine(self, socket_path):
        if socket_path is None:
            return None
        try:
            path = Path(socket_path)
            if not path.is_absolute() or not stat.S_ISSOCK(path.lstat().st_mode):
                return None
            async with asyncio.timeout(2):
                async with httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport(uds=str(path)),
                    timeout=1,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    prefix, raw_version = await api_prefix(client)  # GET /version only.
            version = (
                re.match(r"^[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}(?:$|[-+])", raw_version)
                if len(raw_version) <= 128
                else None
            )
            if version is None:
                return None
            return {"api": prefix.removeprefix("/v"), "version": version[0].rstrip("-+")}
        except (OSError, ValueError, TypeError, httpx.HTTPError, TimeoutError):
            return None


def numeric_version(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}", value)
        else None
    )


async def collect(profile="all", *, docker_socket=None, podman_socket=None, probe=None):
    if profile not in PROFILES:
        raise ValueError("Unknown preflight profile")
    probe = probe or PreflightProbe()
    facts = probe.facts()
    outputs = await asyncio.gather(*(probe.command(key) for key in COMMANDS))
    reads = dict(zip(COMMANDS, outputs, strict=True))
    checks = []

    def add(identifier, passed, label, code):
        checks.append(
            {
                "id": identifier,
                "passed": passed is True,
                "label": translate(label),
                "code": "OK" if passed else code,
            }
        )

    add("non_root", facts["non_root"], "Compte non privilégié", "ROOT_REFUSED")
    add("debian", facts["debian"], "Distribution Debian", "DEBIAN_REQUIRED")
    vm_code, vm = reads["vm"]
    add(
        "virtual_machine",
        vm_code == 0 and bool(re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", vm)) and vm != "none",
        "Machine virtuelle détectée",
        "VM_NOT_CONFIRMED",
    )
    container_code, container = reads["container"]
    add(
        "not_container",
        container_code == 1 and container == "none",
        "Hors conteneur",
        "CONTAINER_OR_UNKNOWN",
    )
    add("systemd_pid1", facts["systemd_pid1"], "systemd comme PID 1", "SYSTEMD_PID1_REQUIRED")
    add(
        "systemd_running",
        reads["state"] == (0, "running"),
        "Gestionnaire systemd disponible",
        "SYSTEMD_NOT_RUNNING",
    )
    version = (
        re.match(r"^systemd ([0-9]{1,4})(?:\s|$)", reads["systemd"][1])
        if reads["systemd"][0] == 0
        else None
    )
    add(
        "systemd_version", version is not None, "Version systemd lisible", "SYSTEMD_VERSION_UNKNOWN"
    )
    add("python", facts["python_supported"], "Version Python compatible", "PYTHON_UNSUPPORTED")
    revision_code, revision = reads["revision"]
    revision_ok = revision_code == 0 and bool(re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", revision))
    add("revision", revision_ok, "Révision Git identifiable", "REVISION_UNKNOWN")
    add(
        "clean_checkout",
        reads["clean"] == (0, ""),
        "Sources sans modification locale",
        "CHECKOUT_DIRTY_OR_UNKNOWN",
    )
    environment_ok = all(row["passed"] for row in checks)
    engines = {}
    for engine in PROFILES[profile]:
        configured = {"docker": docker_socket, "podman": podman_socket}[engine]
        result = await probe.engine(configured) if configured and environment_ok else None
        if result is not None:
            engines[engine] = result
        add(
            engine,
            result is not None,
            "API moteur accessible" + " · " + engine,
            "SOCKET_NOT_CONFIGURED"
            if not configured
            else "ENVIRONMENT_BLOCKED"
            if not environment_ok
            else "ENGINE_UNAVAILABLE",
        )
    return {
        "schema_version": 1,
        "kind": "vm_prerequisites",
        "profile": profile,
        "collected_at": timestamp(),
        "status": "prerequisites_met" if all(row["passed"] for row in checks) else "blocked",
        "read_only": True,
        "qualified": False,
        "system_execution_enabled": False,
        "revision": revision if revision_ok else None,
        "versions": {
            "python": numeric_version(facts["python"]),
            "kernel": numeric_version(facts["kernel"]),
            "debian": facts["debian_version"]
            if re.fullmatch(r"[0-9]{1,2}", facts["debian_version"])
            else None,
            "systemd": version[1] if version else None,
            "engines": engines,
        },
        "checks": checks,
    }


def save_report(path: Path, report: dict):
    directory = path.parent
    info = directory.lstat()
    if (
        not path.is_absolute()
        or directory.resolve() != directory
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("Private report directory required")
    payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    if len(payload) > 16384:
        raise ValueError("Preflight report too large")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
