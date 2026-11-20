"""Opt-in local reads anchored to directory descriptors. No file writes or shell."""

import codecs
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path

from .redaction import redact
from .services import ServiceError

MAX_FILE = 1024 * 1024
MAX_SCAN = 500
DENIED = {".git", ".ssh", ".aws", ".codex", ".agents", ".localcockpit", ".env"}
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def refused(code="FILE_ACCESS_DENIED", status=403):
    return ServiceError(code, "Lecture refusée ou fichier indisponible", status)


def parts(value):
    if not isinstance(value, str) or len(value) > 1024 or value.startswith("/"):
        raise refused()
    result = value.split("/") if value else []
    if len(result) > 16 or any(
        p in {"", ".", ".."}
        or p in DENIED
        or p.startswith(".env.")
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in p)
        or len(p.encode()) > 255
        or "\\" in p
        for p in result
    ):
        raise refused()
    return result


@contextmanager
def absolute_directory(path):
    """Reject symlinks in every ancestor, not just in the last component."""
    path = Path(path)
    if not path.is_absolute() or str(path) != os.path.normpath(str(path)):
        raise refused()
    fd = os.open("/", DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            child = os.open(component, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


class FileBrowser:
    def __init__(self, configuration="[]", private_directory=None):
        self.roots = {}
        self.private_directory = None
        self.configuration_error = False
        try:
            self.private_directory = (
                Path(private_directory).resolve() if private_directory else None
            )
            rows = json.loads(configuration)
            if not isinstance(rows, list) or len(rows) > 8:
                raise ValueError()
            for row in rows:
                if not isinstance(row, dict) or set(row) != {"id", "label", "path"}:
                    raise ValueError()
                key, label, path = row["id"], row["label"], Path(row["path"])
                if (
                    not isinstance(key, str)
                    or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", key)
                    or key in self.roots
                    or not isinstance(label, str)
                    or not 1 <= len(label) <= 60
                    or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in label)
                    or path == Path("/")
                    or any(
                        path == Path(prefix) or Path(prefix) in path.parents
                        for prefix in ("/proc", "/sys", "/dev")
                    )
                ):
                    raise ValueError()
                if self.private_directory and (
                    path == self.private_directory or self.private_directory in path.parents
                ):
                    raise ValueError()
                with absolute_directory(path) as fd:
                    info = os.fstat(fd)
                    self.roots[key] = {
                        "label": label,
                        "path": path,
                        "identity": (info.st_dev, info.st_ino),
                    }
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            RuntimeError,
            RecursionError,
            ServiceError,
        ):
            self.roots.clear()
            self.configuration_error = True

    def options(self):
        return {
            "roots": [{"id": key, "label": row["label"]} for key, row in self.roots.items()],
            "configured": bool(self.roots),
            "configuration_error": self.configuration_error,
            "read_only": True,
            "max_file_bytes": MAX_FILE,
            "max_scanned_entries": MAX_SCAN,
        }

    @contextmanager
    def directory(self, root, path):
        row = self.roots.get(root)
        if row is None:
            raise refused()
        components = parts(path)
        target = row["path"].joinpath(*components)
        if self.private_directory and (
            target == self.private_directory or self.private_directory in target.parents
        ):
            raise refused()
        try:
            with absolute_directory(row["path"]) as anchor:
                info = os.fstat(anchor)
                if (info.st_dev, info.st_ino) != row["identity"]:
                    raise refused()
                fd = os.dup(anchor)
                try:
                    for component in components:
                        child = os.open(component, DIRECTORY_FLAGS, dir_fd=fd)
                        os.close(fd)
                        fd = child
                        if os.fstat(fd).st_dev != info.st_dev:
                            raise refused()
                    yield fd, info.st_dev
                finally:
                    os.close(fd)
        except OSError as exc:
            raise refused() from exc

    def listing(self, root, path="", query=""):
        if len(query) > 100:
            raise refused()
        rows = []
        scanned = 0
        truncated = False
        with self.directory(root, path) as (fd, device), os.scandir(fd) as entries:
            for entry in entries:
                scanned += 1
                if scanned > MAX_SCAN:
                    truncated = True
                    break
                try:
                    parts(entry.name)
                    if query.casefold() not in entry.name.casefold():
                        continue
                    info = entry.stat(follow_symlinks=False)
                    kind = (
                        "directory"
                        if stat.S_ISDIR(info.st_mode)
                        else "file"
                        if stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                        else "blocked"
                    )
                    if info.st_dev != device:
                        kind = "blocked"
                    if (
                        self.private_directory
                        and self.roots[root]["path"].joinpath(path, entry.name)
                        == self.private_directory
                    ):
                        continue
                    rows.append(
                        {
                            "name": entry.name,
                            "kind": kind,
                            "size": info.st_size if kind == "file" else None,
                        }
                    )
                except (OSError, ServiceError):
                    continue
        rows.sort(key=lambda row: (row["kind"] != "directory", row["name"].casefold()))
        return {"items": rows, "truncated": truncated, "scanned_entries": min(scanned, MAX_SCAN)}

    def read(self, root, path, preview=False):
        components = parts(path)
        if not components:
            raise refused()
        with self.directory(root, "/".join(components[:-1])) as (parent, device):
            try:
                fd = os.open(
                    components[-1],
                    os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=parent,
                )
                try:
                    before = os.fstat(fd)
                    if (
                        not stat.S_ISREG(before.st_mode)
                        or before.st_nlink != 1
                        or before.st_dev != device
                        or before.st_size > MAX_FILE
                    ):
                        raise refused("FILE_UNSUPPORTED", 422)
                    maximum = 16384 if preview else MAX_FILE
                    content = bytearray()
                    while len(content) <= maximum:
                        chunk = os.read(fd, min(65536, maximum + 1 - len(content)))
                        if not chunk:
                            break
                        content.extend(chunk)
                    after = os.fstat(fd)
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ctime_ns,
                    ):
                        raise refused("FILE_CHANGED", 409)
                    if not preview and len(content) > maximum:
                        raise refused("FILE_UNSUPPORTED", 422)
                finally:
                    os.close(fd)
            except OSError as exc:
                raise refused() from exc
        if preview:
            if b"\x00" in content:
                raise refused("FILE_UNSUPPORTED", 422)
            try:
                text = codecs.getincrementaldecoder("utf-8")(errors="strict").decode(
                    bytes(content[:maximum]), final=len(content) <= maximum
                )
            except UnicodeError as exc:
                raise refused("FILE_UNSUPPORTED", 422) from exc
            return {"text": redact(text), "truncated": len(content) > maximum, "redacted": True}
        return bytes(content)
