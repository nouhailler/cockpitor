"""Versioned preference-only exports and single-use, session-bound restore reviews."""

import hashlib
import json
import os
import re
import secrets
import stat
import time
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .files import absolute_directory
from .preferences import Preferences
from .services import ServiceError
from .storage import StorageError
from .system import timestamp

MAX_BACKUP_BYTES = 32768
MAX_SNAPSHOTS = 20


class Backup(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["cockpitor.preferences"]
    schema_version: Literal[1]
    created_at: str
    settings: Preferences
    checksum: str

    @field_validator("created_at")
    @classmethod
    def valid_date(cls, value):
        if len(value) > 64 or datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("UTC date required")
        return value


def fingerprint(preferences):
    return hashlib.sha256(preferences.model_dump_json().encode()).hexdigest()


def export(preferences):
    return {
        "kind": "cockpitor.preferences",
        "schema_version": 1,
        "created_at": timestamp(),
        "settings": preferences.model_dump(),
        "checksum": fingerprint(preferences),
    }


def decode(value):
    if not isinstance(value, str) or len(value.encode()) > MAX_BACKUP_BYTES:
        raise ValueError("backup size")

    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = item
        return result

    def invalid(value):
        raise ValueError("non-finite number")

    raw = json.loads(value, object_pairs_hook=unique, parse_constant=invalid)
    if raw.get("schema_version") is not None and type(raw["schema_version"]) is not int:
        raise ValueError("integer schema required")
    data = Backup.model_validate(raw)
    if not secrets.compare_digest(data.checksum, fingerprint(data.settings)):
        raise ValueError("checksum mismatch")
    return data.settings


class Backups:
    def __init__(self, store, clock=time.monotonic):
        self.store = store
        self.clock = clock
        self.plans = {}

    def prepare(self, owner, content, previous):
        now = self.clock()
        self.plans = {key: row for key, row in self.plans.items() if row[3] > now}
        if len(self.plans) >= 32:
            raise ServiceError("BACKUP_BUSY", "Trop de restaurations en attente", 429)
        try:
            target = decode(content)
        except (ValueError, TypeError, AttributeError, RecursionError) as exc:
            raise ServiceError(
                "BACKUP_INVALID", "Sauvegarde invalide ou incompatible", 422
            ) from exc
        key = secrets.token_hex(32)
        self.plans[key] = (owner, fingerprint(previous), target, now + 120)
        before, after = previous.model_dump(), target.model_dump()
        return {
            "plan_id": key,
            "expires_seconds": 120,
            "changes": [
                {"field": field, "before": before[field], "after": after[field]}
                for field in before
                if before[field] != after[field]
            ],
            "scope": "application_preferences_only",
        }

    def consume(self, owner, key, previous):
        row = self.plans.get(key)
        if not row or row[0] != owner:
            raise ServiceError(
                "BACKUP_PLAN_INVALID", "Aperçu de restauration expiré ou modifié", 409
            )
        del self.plans[key]
        if row[3] <= self.clock() or row[1] != fingerprint(previous):
            raise ServiceError(
                "BACKUP_PLAN_INVALID", "Aperçu de restauration expiré ou modifié", 409
            )
        return row[2]

    def snapshot(self, preferences):
        """Durable recovery copy before restore. Never overwrites or silently rotates."""
        content = json.dumps(export(preferences), ensure_ascii=False, allow_nan=False).encode()
        if len(content) > MAX_BACKUP_BYTES:
            raise StorageError("Sauvegarde locale indisponible")
        name = "preferences-backup-" + secrets.token_hex(16) + ".json"
        try:
            with absolute_directory(self.store.directory) as parent:
                info = os.fstat(parent)
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise StorageError("Sauvegarde locale indisponible")
                with os.scandir(parent) as entries:
                    entries_count = 0
                    for count, entry in enumerate(entries, 1):
                        if count > 512:
                            raise StorageError("Sauvegarde locale indisponible")
                        if entry.name.startswith("preferences-backup-"):
                            entries_count += 1
                if entries_count >= MAX_SNAPSHOTS:
                    raise StorageError(
                        "Limite de sauvegardes atteinte ; conservez puis archivez les anciennes copies"
                    )
                fd = os.open(
                    name,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=parent,
                )
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.fsync(parent)
                except BaseException:
                    os.unlink(name, dir_fd=parent)
                    raise
        except OSError as exc:
            raise StorageError("Sauvegarde locale indisponible") from exc
        return name.removeprefix("preferences-backup-").removesuffix(".json")

    def snapshots(self):
        result = []
        try:
            with absolute_directory(self.store.directory) as parent, os.scandir(parent) as entries:
                for index, entry in enumerate(entries):
                    if index >= 512:
                        raise StorageError("Sauvegarde locale indisponible")
                    match = re.fullmatch(r"preferences-backup-([a-f0-9]{32})\.json", entry.name)
                    if match:
                        result.append(match[1])
                        if len(result) > MAX_SNAPSHOTS:
                            raise StorageError("Sauvegarde locale indisponible")
        except OSError as exc:
            raise StorageError("Sauvegarde locale indisponible") from exc
        return {"items": sorted(result), "limit": MAX_SNAPSHOTS}

    def read_snapshot(self, key):
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise ServiceError("BACKUP_INVALID", "Sauvegarde invalide ou incompatible", 422)
        try:
            with absolute_directory(self.store.directory) as parent:
                fd = os.open(
                    f"preferences-backup-{key}.json",
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=parent,
                )
                try:
                    info = os.fstat(fd)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_uid != os.getuid()
                        or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_size > MAX_BACKUP_BYTES
                    ):
                        raise StorageError("Sauvegarde locale indisponible")
                    content = os.read(fd, MAX_BACKUP_BYTES + 1)
                    decode(content.decode())
                finally:
                    os.close(fd)
        except (OSError, ValueError, TypeError, AttributeError, RecursionError) as exc:
            raise StorageError("Sauvegarde locale indisponible") from exc
        return json.loads(content)
