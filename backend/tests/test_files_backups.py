import json
import os

import pytest
from app.backups import Backups, decode, export
from app.files import FileBrowser
from app.preferences import Preferences
from app.services import ServiceError
from app.storage import StorageError, Store
from test_api import wait_settings

pytest_plugins = ["test_api"]


@pytest.fixture
def browser(tmp_path):
    root = tmp_path / "authorized"
    root.mkdir()
    return FileBrowser(json.dumps([{"id": "docs", "label": "Documents", "path": str(root)}])), root


def test_explorer_opt_in_and_all_or_nothing_configuration(tmp_path):
    assert FileBrowser().options()["roots"] == []
    for config in ("null", "{}", "[{}]", '[{"id":"a","label":"x","path":"/"}]'):
        instance = FileBrowser(config)
        assert instance.options()["configuration_error"]
        assert instance.options()["roots"] == []


@pytest.mark.parametrize(
    "path",
    [
        "..",
        "../secret",
        "/etc/passwd",
        "a/../b",
        "a//b",
        "./a",
        "a\\b",
        "a\x00b",
        ".ssh/id_rsa",
        ".env",
        ".env.local",
        ".git/config",
        ".aws/config",
        ".localcockpit/a",
        "a/" * 17,
    ],
)
def test_explorer_rejects_paths(browser, path):
    instance, _ = browser
    with pytest.raises(ServiceError):
        instance.read("docs", path)


def test_listing_preview_redacts_and_download_keeps_original(browser):
    instance, root = browser
    (root / "notes.txt").write_text("password=private-secret\nhello")
    (root / "folder").mkdir()
    # Linux names need not be UTF-8; an invalid name must not break JSON listing.
    raw_fd = os.open(os.fsencode(root) + b"/bad-\xff", os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(raw_fd)
    listing = instance.listing("docs")
    assert listing["items"][0]["kind"] == "directory"
    assert len(listing["items"]) == 2
    preview = instance.read("docs", "notes.txt", True)
    assert "private-secret" not in preview["text"]
    assert instance.read("docs", "notes.txt") == b"password=private-secret\nhello"
    assert instance.listing("docs", query="NOTES")["items"][0]["name"] == "notes.txt"


def test_symlinks_hardlinks_fifo_and_root_replacement_refused(browser, tmp_path):
    instance, root = browser
    (tmp_path / "secret").write_text("SECRET")
    (root / "link").symlink_to(tmp_path / "secret")
    (root / "dirlink").symlink_to(tmp_path, target_is_directory=True)
    os.link(tmp_path / "secret", root / "hardlink")
    os.mkfifo(root / "pipe")
    for name in ("link", "hardlink", "pipe", "dirlink/secret"):
        with pytest.raises(ServiceError):
            instance.read("docs", name)
    assert all(row["kind"] == "blocked" for row in instance.listing("docs")["items"])
    root.rename(tmp_path / "old")
    root.mkdir()
    (root / "replacement").write_text("no")
    with pytest.raises(ServiceError):
        instance.listing("docs")


def test_configured_symlink_ancestor_and_private_storage_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "docs").mkdir()
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    config = lambda path: json.dumps([{"id": "docs", "label": "Docs", "path": str(path)}])
    assert FileBrowser(config(tmp_path / "alias" / "docs")).configuration_error
    private = real / "data"
    private.mkdir()
    (private / "secret").write_text("SECRET")
    instance = FileBrowser(config(real), private)
    assert "data" not in [row["name"] for row in instance.listing("docs")["items"]]
    with pytest.raises(ServiceError):
        instance.read("docs", "data/secret")
    assert FileBrowser(config(private), private).configuration_error


def test_listing_and_file_byte_limits(browser):
    instance, root = browser
    for i in range(505):
        (root / str(i)).touch()
    listing = instance.listing("docs")
    assert listing["truncated"] and len(listing["items"]) == 500
    (root / "large").write_bytes(b"a" * (1024 * 1024 + 1))
    with pytest.raises(ServiceError):
        instance.read("docs", "large")
    (root / "text").write_bytes(b"a" * 16385)
    assert instance.read("docs", "text", True)["truncated"]
    for value in (b"hello\x00world", b"\xff\xfe"):
        (root / "binary").write_bytes(value)
        with pytest.raises(ServiceError):
            instance.read("docs", "binary", True)


def test_file_changed_while_read_is_rejected(browser, monkeypatch):
    instance, root = browser
    (root / "text").write_text("before")
    original = os.read

    def mutate(fd, count):
        result = original(fd, count)
        (root / "text").write_text("after-longer")
        return result

    monkeypatch.setattr("app.files.os.read", mutate)
    with pytest.raises(ServiceError) as exc:
        instance.read("docs", "text")
    assert exc.value.code == "FILE_CHANGED"


def test_backup_roundtrip_and_private_recovery(tmp_path):
    store = Store(tmp_path / "data")
    store.initialize()
    manager = Backups(store)
    previous = store.preferences()
    target = Preferences(language="en", theme="dark")
    assert decode(json.dumps(export(target))) == target
    plan = manager.prepare("owner", json.dumps(export(target)), previous)
    assert {row["field"] for row in plan["changes"]} == {"language", "theme"}
    selected = manager.consume("owner", plan["plan_id"], previous)
    recovery = manager.snapshot(previous)
    operation = store.save(selected, expected=previous, restoring=True)
    assert operation and Store(store.directory).preferences() == target
    assert decode(json.dumps(manager.read_snapshot(recovery))) == previous
    assert manager.snapshots()["items"] == [recovery]
    assert (store.directory / f"preferences-backup-{recovery}.json").stat().st_mode & 0o777 == 0o600
    assert store.audit_events(10, 0)["items"][0]["action"] == "backups.restore"
    with pytest.raises(ServiceError):
        manager.consume("owner", plan["plan_id"], target)


@pytest.mark.parametrize(
    "mutation", ["checksum", "schema", "extra", "privilege", "type", "duplicate", "oversize", "nan"]
)
def test_hostile_backups_rejected(tmp_path, mutation):
    store = Store(tmp_path / "data")
    store.initialize()
    document = export(Preferences())
    if mutation == "checksum":
        document["checksum"] = "0" * 64
    if mutation == "schema":
        document["schema_version"] = 9
    if mutation == "extra":
        document["path"] = "/etc/passwd"
    if mutation == "privilege":
        document["settings"]["sudo"] = True
    if mutation == "type":
        document["schema_version"] = True
    content = json.dumps(document)
    if mutation == "duplicate":
        content = content.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    if mutation == "oversize":
        content += " " * 32769
    if mutation == "nan":
        content = content.replace('"refresh_seconds": 3', '"refresh_seconds": NaN')
    with pytest.raises(ServiceError):
        Backups(store).prepare("owner", content, store.preferences())
    assert store.preferences() == Preferences()


def test_restore_owner_expiry_configuration_change_and_quota(tmp_path):
    store = Store(tmp_path / "data")
    store.initialize()
    now = [0.0]
    manager = Backups(store, clock=lambda: now[0])
    previous = store.preferences()
    content = json.dumps(export(Preferences(language="en")))
    plan = manager.prepare("owner", content, previous)
    with pytest.raises(ServiceError):
        manager.consume("other", plan["plan_id"], previous)
    now[0] = 120
    with pytest.raises(ServiceError):
        manager.consume("owner", plan["plan_id"], previous)
    now[0] = 0
    plan = manager.prepare("owner", content, previous)
    with pytest.raises(ServiceError):
        manager.consume("owner", plan["plan_id"], Preferences(theme="dark"))
    for _ in range(32):
        manager.prepare("owner", content, previous)
    with pytest.raises(ServiceError):
        manager.prepare("owner", content, previous)
    for _ in range(20):
        manager.snapshot(previous)
    with pytest.raises(StorageError):
        manager.snapshot(previous)


def test_snapshot_symlink_and_audit_failure_fail_closed(tmp_path):
    store = Store(tmp_path / "data")
    store.initialize()
    manager = Backups(store)
    key = "a" * 32
    (store.directory / f"preferences-backup-{key}.json").symlink_to(tmp_path / "outside")
    with pytest.raises(StorageError):
        manager.read_snapshot(key)
    before = store.preferences()
    with store.connection() as db:
        db.execute(
            "CREATE TRIGGER reject_restore BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"
        )
    with pytest.raises(StorageError):
        store.save(Preferences(language="en"), expected=before, restoring=True)
    assert store.preferences() == before


def safe(client):
    return {"origin": "http://127.0.0.1:8765", "x-localcockpit-csrf": client.app.state.csrf}


def test_files_api_and_preference_restore_end_to_end(client, tmp_path):
    wait_settings(client)
    root = tmp_path / "files"
    root.mkdir()
    (root / "hello.txt").write_text("hello")
    client.app.state.files = FileBrowser(
        json.dumps([{"id": "docs", "label": "Docs", "path": str(root)}])
    )
    assert client.get("/api/v1/files/options", headers={"authorization": ""}).status_code == 401
    assert client.get("/api/v1/files?root=docs").json()["items"][0]["name"] == "hello.txt"
    assert client.get("/api/v1/files/preview?root=docs&path=hello.txt").json()["text"] == "hello"
    response = client.get("/api/v1/files/download?root=docs&path=hello.txt")
    assert response.content == b"hello" and response.headers["content-disposition"].startswith(
        "attachment;"
    )
    assert client.get("/api/v1/files?root=docs&path=..").status_code == 403
    assert client.post("/api/v1/backups/export", json={"confirmed": True}).status_code == 403
    assert (
        client.post(
            "/api/v1/backups/export", headers=safe(client), json={"confirmed": 1}
        ).status_code
        == 422
    )
    exported = client.post("/api/v1/backups/export", headers=safe(client), json={"confirmed": True})
    assert exported.status_code == 200, exported.text
    assert decode(json.dumps(exported.json())) == client.app.state.store.preferences()
    assert any(
        event["action"] == "backups.export"
        for event in client.app.state.store.audit_events(10, 0)["items"]
    )
    target = Preferences(language="en")
    document = export(target)
    plan = client.post(
        "/api/v1/backups/prepare", headers=safe(client), json={"backup": json.dumps(document)}
    ).json()
    response = client.post(
        "/api/v1/backups/restore",
        headers=safe(client),
        json={"plan_id": plan["plan_id"], "confirmed": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["system_changed"] is False
    assert client.get("/api/v1/settings").json()["settings"]["language"] == "en"
    items = client.get("/api/v1/backups").json()["items"]
    assert len(items) == 1
    old = client.get("/api/v1/backups/snapshot?id=" + items[0]).json()
    assert old["settings"]["language"] == "fr"
    assert (
        client.post(
            "/api/v1/backups/restore",
            headers=safe(client),
            json={"plan_id": plan["plan_id"], "confirmed": True},
        ).status_code
        == 409
    )
    assert client.post("/api/v1/files/delete", headers=safe(client), json={}).status_code == 405


def test_restore_snapshot_failure_leaves_preferences_unchanged(client, monkeypatch):
    wait_settings(client)
    previous = client.app.state.store.preferences()
    plan = client.post(
        "/api/v1/backups/prepare",
        headers=safe(client),
        json={"backup": json.dumps(export(Preferences(language="en")))},
    ).json()

    def failed(*args):
        raise StorageError("Sauvegarde locale indisponible")

    monkeypatch.setattr(client.app.state.backups, "snapshot", failed)
    response = client.post(
        "/api/v1/backups/restore",
        headers=safe(client),
        json={"plan_id": plan["plan_id"], "confirmed": True},
    )
    assert response.status_code == 503
    assert client.app.state.store.preferences() == previous


def test_revoked_session_during_snapshot_cannot_restore(client, monkeypatch):
    wait_settings(client)
    previous = client.app.state.store.preferences()
    plan = client.post(
        "/api/v1/backups/prepare",
        headers=safe(client),
        json={"backup": json.dumps(export(Preferences(language="en")))},
    ).json()
    original = client.app.state.backups.snapshot

    def revoke(preferences):
        value = original(preferences)
        client.app.state.sessions.revoke(client.headers["authorization"][7:])
        return value

    monkeypatch.setattr(client.app.state.backups, "snapshot", revoke)
    response = client.post(
        "/api/v1/backups/restore",
        headers=safe(client),
        json={"plan_id": plan["plan_id"], "confirmed": True},
    )
    assert response.status_code == 401
    assert client.app.state.store.preferences() == previous


def test_restore_compare_and_swap_rejects_another_store_change(tmp_path):
    store = Store(tmp_path / "data")
    previous = store.initialize()
    other = Store(store.directory)
    changed = Preferences(theme="dark")
    other.save(changed)
    with pytest.raises(StorageError):
        store.save(Preferences(language="en"), expected=previous, restoring=True)
    assert other.preferences() == changed
    assert not any(row["action"] == "backups.restore" for row in other.audit_events(10, 0)["items"])


def test_cancelled_restore_holds_lock_until_transaction_finishes(tmp_path):
    import asyncio
    import threading
    from types import SimpleNamespace

    from app.auth import Sessions
    from app.routes.backups import create_router

    store = Store(tmp_path / "state")
    previous = store.initialize()
    sessions = Sessions("bootstrap")
    token, _ = sessions.login("bootstrap")
    manager = Backups(store)
    plan = manager.prepare(
        Sessions.digest(token), json.dumps(export(Preferences(language="en"))), previous
    )
    entered, release = threading.Event(), threading.Event()
    original = manager.snapshot

    def snapshot(preferences):
        entered.set()
        assert release.wait(2)
        return original(preferences)

    manager.snapshot = snapshot

    async def scenario():
        state = SimpleNamespace(
            store=store,
            backups=manager,
            sessions=sessions,
            storage_ready=True,
            preferences=previous,
            preferences_lock=asyncio.Lock(),
        )
        router = create_router(SimpleNamespace(state=state))
        endpoint = next(
            route.endpoint for route in router.routes if route.path.endswith("/restore")
        )

        async def stream():
            yield json.dumps({"plan_id": plan["plan_id"], "confirmed": True}).encode()

        request = SimpleNamespace(headers={"authorization": "Bearer " + token}, stream=stream)
        task = asyncio.create_task(endpoint(request))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            await asyncio.sleep(0)
            assert state.preferences_lock.locked()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not state.preferences_lock.locked()
        assert state.preferences.language == "en"
        assert store.preferences() == state.preferences

    asyncio.run(scenario())
