"""Explicit, pinned-key SSH authentication and bounded SFTP root listings only."""

import asyncio
import ipaddress
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Literal

import asyncssh
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .files import absolute_directory, parts
from .services import ServiceError
from .system import timestamp

NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "fc00::/7",
        "::1/128",
    )
)


class Host(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    label: str = Field(min_length=1, max_length=60)
    group: str = Field(default="", max_length=40)
    address: str = Field(max_length=64)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    server_host_key: str = Field(max_length=256)
    client_key: str = Field(min_length=1, max_length=1024)
    allow_sftp: bool = False
    remote_root: str = Field(default="/", min_length=1, max_length=512)

    @field_validator("label", "group")
    @classmethod
    def safe_text(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("invalid text")
        return value

    @field_validator("address")
    @classmethod
    def private_numeric_address(cls, value):
        address = ipaddress.ip_address(value)
        if (
            "%" in value
            or address.is_multicast
            or address.is_unspecified
            or not any(
                address in network for network in NETWORKS if address.version == network.version
            )
        ):
            raise ValueError("explicit private numeric address required")
        return str(address)

    @field_validator("username")
    @classmethod
    def unprivileged_account(cls, value):
        if value == "root":
            raise ValueError("root account refused")
        return value

    @field_validator("client_key")
    @classmethod
    def explicit_key_path(cls, value):
        path = Path(value)
        if not path.is_absolute() or value != os.path.normpath(value) or "\x00" in value:
            raise ValueError("absolute key path required")
        return value

    @field_validator("remote_root")
    @classmethod
    def explicit_root(cls, value):
        if not value.startswith("/"):
            raise ValueError("absolute remote root required")
        try:
            parts(value[1:]) if value != "/" else None
        except ServiceError as exc:
            raise ValueError("invalid remote root") from exc
        return value

    @field_validator("server_host_key")
    @classmethod
    def ed25519_pin(cls, value):
        if len(value.split()) != 2 or not value.startswith("ssh-ed25519 "):
            raise ValueError("ed25519 public key required")
        key = asyncssh.import_public_key(value)
        if key.get_algorithm() != "ssh-ed25519":
            raise ValueError("ed25519 required")
        return key.export_public_key().decode().strip()


class RemoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    host_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    configuration_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def exact_confirmation(cls, value):
        if value is not True:
            raise ValueError("confirmation required")
        return value


def client_key(host):
    """Do not pass a filename to the SSH library (no implicit .pub/cert/agent loads)."""
    try:
        path = Path(host.client_key)
        with absolute_directory(path.parent) as parent:
            fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > 8192
                ):
                    raise ValueError("private key rejected")
                content = os.read(fd, 8193)
                if len(content) > 8192:
                    raise ValueError("key limit")
            finally:
                os.close(fd)
        key = asyncssh.import_private_key(content)
        if key.get_algorithm() != "ssh-ed25519":
            raise ValueError("ed25519 required")
        return key
    except (OSError, ValueError, asyncssh.KeyImportError, ServiceError) as exc:
        raise ServiceError(
            "REMOTE_CREDENTIALS", "Clé cliente indisponible ou non conforme", 422
        ) from exc


async def connect_and_read(host, kind):
    key_task = asyncio.create_task(asyncio.to_thread(client_key, host))
    try:
        key = await asyncio.shield(key_task)
    except asyncio.CancelledError:
        # Keep admission occupied until the local credential read has ended.
        await key_task
        raise
    pin = asyncssh.import_public_key(host.server_host_key)
    async with asyncssh.connect(
        host.address,
        host.port,
        username=host.username,
        known_hosts=([pin], [], []),
        client_keys=[key],
        client_certs=[],
        agent_path=None,
        agent_forwarding=False,
        password=None,
        password_auth=False,
        kbdint_auth=False,
        host_based_auth=False,
        gss_auth=False,
        gss_kex=False,
        preferred_auth=["publickey"],
        server_host_key_algs=["ssh-ed25519"],
        config=None,
        tunnel=None,
        proxy_command=None,
        connect_timeout=4,
        login_timeout=4,
        keepalive_interval=0,
    ) as connection:
        result = {
            "host_key_verified": True,
            "authenticated": True,
            "commands_executed": False,
            "system_changed": False,
            "checked_at": timestamp(),
        }
        if kind == "check":
            return result
        async with connection.start_sftp_client() as sftp:
            # Listing only; no user-supplied remote path, open/read/exec/terminal or writes.
            canonical = await sftp.realpath(host.remote_root)
            if canonical != host.remote_root:
                raise ServiceError(
                    "REMOTE_ROOT_CHANGED", "Racine SFTP non canonique ou modifiée", 409
                )
            attrs = await sftp.lstat(host.remote_root)
            if attrs.permissions is None or not stat.S_ISDIR(attrs.permissions):
                raise ServiceError(
                    "REMOTE_ROOT_CHANGED", "Racine SFTP non canonique ou modifiée", 409
                )
            rows = []
            seen = set()
            scanned = 0
            truncated = False
            async for entry in sftp.scandir(host.remote_root):
                scanned += 1
                if scanned > 200:
                    truncated = True
                    break
                try:
                    if (
                        len(parts(entry.filename)) != 1
                        or "/" in entry.filename
                        or entry.filename in seen
                    ):
                        continue
                except ServiceError:
                    continue
                seen.add(entry.filename)
                mode = entry.attrs.permissions
                kind = (
                    "directory"
                    if mode is not None and stat.S_ISDIR(mode)
                    else "file"
                    if mode is not None and stat.S_ISREG(mode)
                    else "blocked"
                )
                size = entry.attrs.size
                rows.append(
                    {
                        "name": entry.filename,
                        "kind": kind,
                        "size": size
                        if kind == "file" and isinstance(size, int) and 0 <= size <= 2**63 - 1
                        else None,
                    }
                )
            rows.sort(key=lambda row: (row["kind"] != "directory", row["name"].casefold()))
            return {
                **result,
                "items": rows,
                "truncated": truncated,
                "scope": "configured_root_listing_only",
            }


class RemoteHosts:
    def __init__(self, configuration, sessions, store):
        self.hosts = {}
        self.configuration_ids = {}
        self.configuration_error = False
        self.sessions, self.store = sessions, store
        self.jobs = {}
        self.last_checks = {}
        try:
            rows = json.loads(configuration)
            if not isinstance(rows, list) or len(rows) > 8:
                raise ValueError("host limit")
            for row in rows:
                host = Host.model_validate(row)
                if host.id in self.hosts:
                    raise ValueError("duplicate host")
                self.hosts[host.id] = host
                self.configuration_ids[host.id] = secrets.token_hex(16)
        except (ValueError, TypeError, asyncssh.KeyImportError, RecursionError):
            self.hosts.clear()
            self.configuration_ids.clear()
            self.configuration_error = True

    def inventory(self):
        return {
            "items": [
                {
                    "id": host.id,
                    "label": host.label,
                    "group": host.group,
                    "address": host.address,
                    "port": host.port,
                    "username": host.username,
                    "host_key_fingerprint": asyncssh.import_public_key(
                        host.server_host_key
                    ).get_fingerprint(),
                    "configuration_id": self.configuration_ids[host.id],
                    "allow_sftp": host.allow_sftp,
                    "remote_root": host.remote_root if host.allow_sftp else None,
                    "last_check": self.last_checks.get(host.id),
                }
                for host in self.hosts.values()
            ],
            "configuration_error": self.configuration_error,
            "automatic_connections": False,
            "system_actions_enabled": False,
        }

    def cancel(self, owner):
        row = self.jobs.get(owner)
        if row:
            row[1].cancel()

    async def close(self):
        tasks = [row[1] for row in self.jobs.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, owner, request, kind):
        host = self.hosts.get(request.host_id)
        if not host or self.configuration_ids.get(host.id) != request.configuration_id:
            raise ServiceError("REMOTE_HOST_CHANGED", "Hôte inconnu ou configuration modifiée", 409)
        if kind not in {"check", "list"} or (kind == "list" and not host.allow_sftp):
            raise ServiceError(
                "REMOTE_NOT_ALLOWED", "Lecture SFTP non autorisée pour cet hôte", 403
            )
        if not self.sessions.valid_owner(owner):
            raise ServiceError("AUTH_REQUIRED", "Session expirée", 401)
        if (
            owner in self.jobs
            or len(self.jobs) >= 2
            or any(row[0] == host.id for row in self.jobs.values())
        ):
            raise ServiceError("REMOTE_BUSY", "Connexion distante occupée ; réessayez", 429)

        async def operation():
            async with asyncio.timeout(8):
                await asyncio.to_thread(
                    self.store.audit,
                    secrets.token_hex(16),
                    "remote.ssh.check" if kind == "check" else "remote.sftp.list",
                )
                if not self.sessions.valid_owner(owner):
                    raise ServiceError("AUTH_REQUIRED", "Session expirée", 401)
                return await connect_and_read(host, kind)

        task = asyncio.create_task(operation())
        self.jobs[owner] = (host.id, task)
        try:
            while not task.done():
                await asyncio.sleep(0.05)
                if not self.sessions.valid_owner(owner):
                    task.cancel()
                    raise ServiceError("AUTH_REQUIRED", "Session expirée", 401)
            result = await task
            if not self.sessions.valid_owner(owner):
                raise ServiceError("AUTH_REQUIRED", "Session expirée", 401)
            await asyncio.to_thread(self.store.audit, secrets.token_hex(16), "remote.completed")
            if not self.sessions.valid_owner(owner):
                raise ServiceError("AUTH_REQUIRED", "Session expirée", 401)
            self.last_checks[host.id] = {
                "checked_at": result["checked_at"],
                "status": "available",
                "host_key_verified": True,
            }
            return result
        except asyncssh.HostKeyNotVerifiable as exc:
            self.last_checks[host.id] = {
                "checked_at": timestamp(),
                "status": "host_key_rejected",
                "host_key_verified": False,
            }
            await asyncio.to_thread(self.store.audit, secrets.token_hex(16), "remote.failed")
            raise ServiceError(
                "REMOTE_HOST_KEY", "Clé d’hôte refusée ; vérifiez-la hors bande", 409
            ) from exc
        except asyncssh.PermissionDenied as exc:
            self.last_checks[host.id] = {
                "checked_at": timestamp(),
                "status": "authentication_failed",
                "host_key_verified": False,
            }
            await asyncio.to_thread(self.store.audit, secrets.token_hex(16), "remote.failed")
            raise ServiceError("REMOTE_AUTH", "Authentification distante refusée", 403) from exc
        except (asyncssh.Error, OSError, TimeoutError, UnicodeError) as exc:
            self.last_checks[host.id] = {
                "checked_at": timestamp(),
                "status": "unavailable",
                "host_key_verified": False,
            }
            await asyncio.to_thread(self.store.audit, secrets.token_hex(16), "remote.failed")
            raise ServiceError(
                "REMOTE_UNAVAILABLE", "Connexion SSH/SFTP indisponible ou réponse incompatible"
            ) from exc
        except ServiceError:
            self.last_checks[host.id] = {
                "checked_at": timestamp(),
                "status": "unavailable",
                "host_key_verified": False,
            }
            await asyncio.to_thread(self.store.audit, secrets.token_hex(16), "remote.failed")
            raise
        except asyncio.CancelledError as exc:
            raise ServiceError("REMOTE_CANCELLED", "Connexion distante annulée", 409) from exc
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.jobs.pop(owner, None)
