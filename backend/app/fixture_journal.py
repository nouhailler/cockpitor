"""Private, bounded trial ledger. Separate from the application database.

Only the adapter qualification lab creates this ledger. Nothing installs or
connects it to the web app, the verification transport or a privileged helper.
"""

import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

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
                db.execute("BEGIN IMMEDIATE")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, 1}:
                    raise JournalError("Unsupported trial journal")
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

    def reserve(self, trial_id, action):
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
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM trials").fetchone()[0] >= MAX_TRIALS:
                raise JournalError("Trial journal full")
            db.execute(
                "INSERT INTO trials VALUES (?,?,?,?)", (trial_id, action, "prepared", timestamp())
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
