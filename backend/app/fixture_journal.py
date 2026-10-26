"""Private, bounded trial ledger. Separate from the application database.

Only the adapter qualification lab creates this ledger. Nothing installs or
connects it to the web app, the verification transport or a privileged helper.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

from .actions import ActionRequest
from .system import timestamp

MAX_TRIALS = 256


class JournalError(Exception):
    pass


class FixtureJournal:
    def __init__(self, directory: Path):
        self.directory = directory.absolute()
        self.path = self.directory / "fixture-trials.sqlite3"

    @contextmanager
    def connection(self):
        db = None
        try:
            db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=0.25)
            db.row_factory = sqlite3.Row
            with db:
                yield db
        except (sqlite3.Error, OSError, ValueError):
            raise JournalError("Trial journal unavailable") from None
        finally:
            if db is not None:
                db.close()

    def initialize(self):
        if os.geteuid() == 0:
            raise JournalError("Non-root fixture lab required")
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = self.directory.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
                or self.directory.resolve() != self.directory
            ):
                raise JournalError("Private trial directory required")
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                ):
                    raise JournalError("Private trial database required")
            finally:
                os.close(fd)
            with self.connection() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, 1, 2}:
                    raise JournalError("Unsupported trial journal")
                if version == 1:
                    backup = self.directory / f"backup-trials-v1-{uuid.uuid4().hex}.sqlite3"
                    backup_fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                    os.close(backup_fd)
                    with sqlite3.connect(backup) as copy:
                        db.backup(copy)
                db.execute("BEGIN IMMEDIATE")
                if db.execute("PRAGMA user_version").fetchone()[0] != version:
                    raise JournalError("Trial journal changed during startup")
                if version == 0:
                    if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                        raise JournalError("Not an empty trial journal")
                    db.execute(
                        "CREATE TABLE trials(id TEXT PRIMARY KEY, action TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL)"
                    )
                    db.execute(
                        "CREATE TABLE events(sequence INTEGER PRIMARY KEY, trial_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)"
                    )
                    db.execute("PRAGMA user_version=1")
                if version in {0, 1}:
                    db.execute("ALTER TABLE trials ADD COLUMN resource_digest TEXT")
                    db.execute("ALTER TABLE trials ADD COLUMN approved_fingerprint TEXT")
                    db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY, value BLOB NOT NULL)")
                    resource_key = secrets.token_bytes(32)
                    db.execute("INSERT INTO metadata VALUES ('resource_key', ?)", (resource_key,))
                    db.execute(
                        "INSERT INTO metadata VALUES ('key_digest', ?)",
                        (hashlib.sha256(resource_key).digest(),),
                    )
                    db.execute("PRAGMA user_version=2")
                self._resource_key(db)
                rows = db.execute(
                    "SELECT id,status FROM trials WHERE status IN ('prepared','dispatching')"
                ).fetchall()
                for row in rows:
                    status = "unknown" if row["status"] == "dispatching" else "not_dispatched"
                    db.execute(
                        "UPDATE trials SET status=?,updated_at=? WHERE id=?",
                        (status, timestamp(), row["id"]),
                    )
                    self._event(db, row["id"], status)
        except (OSError, sqlite3.Error, ValueError):
            raise JournalError("Trial journal unavailable") from None

    @staticmethod
    def _event(db, trial_id, status):
        db.execute(
            "INSERT INTO events(trial_id,status,created_at) VALUES (?,?,?)",
            (trial_id, status, timestamp()),
        )

    @staticmethod
    def _resource_key(db):
        row = db.execute("SELECT value FROM metadata WHERE name='resource_key'").fetchone()
        if row is None or not isinstance(row[0], bytes) or len(row[0]) != 32:
            raise JournalError("Resource key unavailable")
        digest = db.execute("SELECT value FROM metadata WHERE name='key_digest'").fetchone()
        if (
            digest is None
            or not isinstance(digest[0], bytes)
            or not hmac.compare_digest(digest[0], hashlib.sha256(row[0]).digest())
        ):
            raise JournalError("Resource key integrity not confirmed")
        return row[0]

    def _resource(self, db, request):
        payload = json.dumps(
            [request.action.split(".")[0], request.target, request.engine],
            separators=(",", ":"),
        ).encode()
        return hmac.new(self._resource_key(db), payload, hashlib.sha256).hexdigest()

    def reserve(self, trial_id, action, *, request=None, approved_fingerprint=None):
        if not isinstance(trial_id, str) or not re.fullmatch(r"[a-f0-9]{32}", trial_id):
            raise JournalError("Invalid trial identifier")
        if action not in {
            "service.start",
            "service.stop",
            "service.restart",
            "container.start",
            "container.restart",
        }:
            raise JournalError("Invalid trial action")
        if request is not None:
            request = ActionRequest.model_validate(request.model_dump())
            if (
                request.action != action
                or not isinstance(approved_fingerprint, str)
                or not re.fullmatch(r"[a-f0-9]{64}", approved_fingerprint)
            ):
                raise JournalError("Invalid trial binding")
        elif approved_fingerprint is not None:
            raise JournalError("Request required for binding")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._resource_key(db)
            resource = self._resource(db, request) if request is not None else None
            blocked = db.execute(
                "SELECT 1 FROM trials WHERE status IN ('prepared','dispatching','unknown') AND (resource_digest IS NULL OR resource_digest=? OR ? IS NULL) LIMIT 1",
                (resource, resource),
            ).fetchone()
            if blocked:
                raise JournalError("Resource has an unresolved trial")
            if db.execute("SELECT count(*) FROM trials").fetchone()[0] >= MAX_TRIALS:
                raise JournalError("Trial journal full")
            db.execute(
                "INSERT INTO trials VALUES (?,?,?,?,?,?)",
                (trial_id, action, "prepared", timestamp(), resource, approved_fingerprint),
            )
            self._event(db, trial_id, "prepared")

    def transition(self, trial_id, previous, status):
        allowed = {
            "prepared": {"dispatching", "not_dispatched"},
            "dispatching": {"verified", "unknown", "not_dispatched"},
        }
        if status not in allowed.get(previous, set()):
            raise JournalError("Trial transition refused")
        with self.connection() as db:
            changed = db.execute(
                "UPDATE trials SET status=?,updated_at=? WHERE id=? AND status=?",
                (status, timestamp(), trial_id, previous),
            ).rowcount
            if changed != 1:
                raise JournalError("Trial already changed")
            self._event(db, trial_id, status)

    def status(self, trial_id):
        with self.connection() as db:
            row = db.execute("SELECT status FROM trials WHERE id=?", (trial_id,)).fetchone()
            if row is None:
                raise JournalError("Unknown trial")
            return row["status"]

    def events(self, trial_id):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT trial_id,status,created_at FROM events WHERE trial_id=? ORDER BY sequence",
                    (trial_id,),
                ).fetchall()
            ]

    def require_unknown(self, trial_id, request, approved_fingerprint):
        request = ActionRequest.model_validate(request.model_dump())
        with self.connection() as db:
            self._bound_unknown(db, trial_id, request, approved_fingerprint)

    def _bound_unknown(self, db, trial_id, request, approved_fingerprint):
        row = db.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
        if (
            row is None
            or row["status"] != "unknown"
            or row["action"] != request.action
            or row["resource_digest"] != self._resource(db, request)
            or not isinstance(approved_fingerprint, str)
            or row["approved_fingerprint"] != approved_fingerprint
        ):
            raise JournalError("Unknown trial binding not confirmed")

    def reconcile(self, trial_id, request, approved_fingerprint):
        # The fixture controller must first confirm the postcondition using reads only.
        request = ActionRequest.model_validate(request.model_dump())
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._bound_unknown(db, trial_id, request, approved_fingerprint)
            db.execute(
                "UPDATE trials SET status='reconciled',updated_at=? WHERE id=?",
                (timestamp(), trial_id),
            )
            self._event(db, trial_id, "reconciled")
