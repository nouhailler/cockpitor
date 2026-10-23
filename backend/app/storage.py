"""Small SQLite store with versioned schema, private files and bounded histories."""

import os
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .preferences import Preferences
from .system import timestamp


class StorageError(Exception):
    pass


class Store:
    def __init__(self, directory: Path):
        self.directory = directory.absolute()
        self.path = self.directory / "cockpitor.sqlite3"

    @contextmanager
    def connection(self):
        connection = None
        try:
            connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=0.25)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA temp_store=MEMORY")
            with connection:
                yield connection
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise StorageError("Stockage local indisponible, verrouillé ou incompatible") from exc
        finally:
            if connection:
                connection.close()

    def initialize(self):
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = self.directory.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise StorageError(
                    "Le dossier de données doit appartenir au compte et avoir le mode 0700"
                )
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                ):
                    raise StorageError("La base doit appartenir au compte et avoir le mode 0600")
            finally:
                os.close(fd)
            with self.connection() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version > 1:
                    raise StorageError("Version de base plus récente ; aucune migration effectuée")
                if version == 0:
                    tables = db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    if tables:
                        backup = self.directory / f"backup-{uuid.uuid4().hex}.sqlite3"
                        backup_fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                        os.close(backup_fd)
                        with sqlite3.connect(backup) as copy:
                            started = time.monotonic()

                            def check_backup(status, remaining, total):
                                if time.monotonic() - started > 1:
                                    raise StorageError(
                                        "Sauvegarde du stockage trop lente ; migration annulée"
                                    )

                            db.backup(copy, pages=64, progress=check_backup, sleep=0.05)
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"
                    )
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS alert_events (id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT, created_epoch REAL NOT NULL)"
                    )
                    db.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS one_active_rule ON alert_events(rule_id) WHERE status='active'"
                    )
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS audit_events (id TEXT PRIMARY KEY, action TEXT NOT NULL, timestamp TEXT NOT NULL)"
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO settings VALUES (1, ?)",
                        (Preferences().model_dump_json(),),
                    )
                    db.execute("PRAGMA user_version=1")
        except OSError as exc:
            raise StorageError("Impossible de créer le stockage local privé") from exc
        return self.preferences()

    def preferences(self) -> Preferences:
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE id=1").fetchone()
            if row is None:
                raise StorageError("Configuration absente")
            return Preferences.model_validate_json(row[0])

    def save(self, preferences: Preferences) -> str:
        operation = str(uuid.uuid4())
        with self.connection() as db:
            previous = Preferences.model_validate_json(
                db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0]
            )
            new_rules = {r.id: r for r in preferences.rules}
            changed = [r.id for r in previous.rules if new_rules.get(r.id) != r]
            for rule_id in changed:
                db.execute(
                    "UPDATE alert_events SET status='resolved', resolved_at=? WHERE rule_id=? AND status='active'",
                    (timestamp(), rule_id),
                )
            db.execute("UPDATE settings SET value=? WHERE id=1", (preferences.model_dump_json(),))
            db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?)",
                (operation, "settings.update", timestamp()),
            )
            db.execute(
                "DELETE FROM audit_events WHERE id NOT IN (SELECT id FROM audit_events ORDER BY rowid DESC LIMIT 1000)"
            )
        return operation

    def active(self) -> dict[str, str]:
        with self.connection() as db:
            return {
                row["rule_id"]: row["id"]
                for row in db.execute("SELECT id, rule_id FROM alert_events WHERE status='active'")
            }

    def activate(self, rule_id: str, severity: str, message: str) -> str:
        event_id = str(uuid.uuid4())
        with self.connection() as db:
            db.execute(
                "INSERT INTO alert_events VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
                (event_id, rule_id, severity, message, "active", timestamp(), time.time()),
            )
        return event_id

    def resolve(self, event_id: str):
        with self.connection() as db:
            db.execute(
                "UPDATE alert_events SET status='resolved', resolved_at=? WHERE id=? AND status='active'",
                (timestamp(), event_id),
            )

    def events(self, status: str, limit: int, offset: int):
        with self.connection() as db:
            rows = db.execute(
                "SELECT id,rule_id,severity,message,status,created_at,resolved_at FROM alert_events WHERE (?='all' OR status=?) ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (status, status, limit, offset),
            ).fetchall()
            count = db.execute(
                "SELECT count(*) FROM alert_events WHERE (?='all' OR status=?)", (status, status)
            ).fetchone()[0]
        return {"items": [dict(row) for row in rows], "total": count}

    def cleanup(self, retention_days: int):
        with self.connection() as db:
            db.execute(
                "DELETE FROM alert_events WHERE status='resolved' AND CAST(strftime('%s', resolved_at) AS INTEGER) < ?",
                (time.time() - retention_days * 86400,),
            )
            db.execute(
                "DELETE FROM alert_events WHERE status='resolved' AND id NOT IN (SELECT id FROM alert_events WHERE status='resolved' ORDER BY rowid DESC LIMIT 1000)"
            )

    def diagnostic_summary(self):
        with self.connection() as db:
            rows = db.execute(
                "SELECT status, count(*) AS count FROM alert_events GROUP BY status"
            ).fetchall()
            return {
                "alerts": {
                    row["status"]: row["count"]
                    for row in rows
                    if row["status"] in {"active", "resolved"}
                }
            }

    def audit(self, operation_id: str, action: str):
        if action != "diagnostics.export":
            raise StorageError("Action audit non autorisée")
        with self.connection() as db:
            db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?)", (operation_id, action, timestamp())
            )
            db.execute(
                "DELETE FROM audit_events WHERE id NOT IN (SELECT id FROM audit_events ORDER BY rowid DESC LIMIT 1000)"
            )
