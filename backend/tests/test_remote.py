import asyncio
import json
import os

import asyncssh
import pytest
from app.auth import Sessions
from app.remote import Host, RemoteHosts, RemoteRequest, client_key
from app.services import ServiceError
from app.storage import StorageError, Store
from test_api import wait_settings

pytest_plugins = ["test_api"]


def configuration(tmp_path):
    private = asyncssh.generate_private_key("ssh-ed25519")
    server = asyncssh.generate_private_key("ssh-ed25519")
    path = tmp_path / "client-key"
    path.write_bytes(private.export_private_key())
    path.chmod(0o600)
    row = {
        "id": "debian",
        "label": "Debian test",
        "group": "Lab",
        "address": "127.0.0.1",
        "port": 2222,
        "username": "tester",
        "server_host_key": server.export_public_key().decode().strip(),
        "client_key": str(path),
        "allow_sftp": True,
    }
    return row, private, server


def manager(tmp_path, row):
    sessions = Sessions("bootstrap")
    token, _ = sessions.login("bootstrap")
    store = Store(tmp_path / "state")
    store.initialize()
    return RemoteHosts(json.dumps([row]), sessions, store), Sessions.digest(token), token


def request(remote):
    return RemoteRequest(
        host_id="debian", configuration_id=remote.configuration_ids["debian"], confirmed=True
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("address", "example.com"),
        ("address", "169.254.169.254"),
        ("address", "0.0.0.0"),
        ("address", "224.0.0.1"),
        ("address", "8.8.8.8"),
        ("address", "fe80::1%eth0"),
        ("address", "::ffff:127.0.0.1"),
        ("port", True),
        ("port", 0),
        ("username", "root"),
        ("username", "-oProxyCommand=x"),
        ("client_key", "relative"),
        ("remote_root", "/a/../b"),
        ("server_host_key", "ssh-ed25519 invalid"),
    ],
)
def test_invalid_host_configuration_is_closed(tmp_path, field, value):
    row, _, _ = configuration(tmp_path)
    row[field] = value
    remote, _, _ = manager(tmp_path, row)
    assert remote.configuration_error and remote.inventory()["items"] == []


def test_no_implicit_hosts_and_no_credential_paths_in_inventory(tmp_path):
    row, _, _ = configuration(tmp_path)
    remote, _, _ = manager(tmp_path, row)
    inventory = remote.inventory()
    assert str(tmp_path) not in json.dumps(inventory)
    assert "BEGIN OPENSSH PRIVATE KEY" not in json.dumps(inventory)
    assert inventory["items"][0]["host_key_fingerprint"].startswith("SHA256:")
    assert inventory["automatic_connections"] is False
    assert RemoteHosts("[]", remote.sessions, remote.store).inventory()["items"] == []
    assert RemoteHosts(json.dumps([row, row]), remote.sessions, remote.store).configuration_error


@pytest.mark.parametrize("mutation", ["mode", "link", "encrypted", "algorithm"])
def test_private_key_policy(tmp_path, mutation):
    row, key, _ = configuration(tmp_path)
    path = tmp_path / "client-key"
    if mutation == "mode":
        path.chmod(0o644)
    if mutation == "link":
        path.rename(tmp_path / "real-key")
        path.symlink_to(tmp_path / "real-key")
    if mutation == "encrypted":
        path.write_bytes(key.export_private_key("pkcs8-pem", passphrase="not-provided"))
    if mutation == "algorithm":
        path.write_bytes(asyncssh.generate_private_key("ecdsa-sha2-nistp256").export_private_key())
    with pytest.raises(ServiceError) as exc:
        client_key(Host.model_validate(row))
    assert exc.value.code == "REMOTE_CREDENTIALS"


def test_pinned_ssh_and_sftp_over_real_local_protocol(tmp_path):
    row, client, server = configuration(tmp_path)
    root = tmp_path / "sftp-root"
    root.mkdir()
    (root / "notes.txt").write_text("not transferred")
    (root / "folder").mkdir()
    (root / "link").symlink_to("notes.txt")
    (root / ".env").write_text("SECRET")
    auth = []

    class Server(asyncssh.SSHServer):
        def begin_auth(self, username):
            auth.append(username)
            return True

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            return username == "tester" and key.export_public_key() == client.export_public_key()

    async def scenario():
        async with asyncssh.create_server(
            Server,
            "127.0.0.1",
            0,
            server_host_keys=[server],
            sftp_factory=lambda chan: asyncssh.SFTPServer(chan, chroot=os.fsencode(root)),
            config=None,
        ) as listener:
            row["port"] = listener.get_port()
            remote, owner, _ = manager(tmp_path, row)
            checked = await remote.run(owner, request(remote), "check")
            assert checked["authenticated"] and checked["host_key_verified"]
            assert checked["commands_executed"] is False and checked["system_changed"] is False
            result = await remote.run(owner, request(remote), "list")
            assert {item["name"] for item in result["items"]} == {"notes.txt", "folder", "link"}
            assert (
                next(item for item in result["items"] if item["name"] == "link")["kind"]
                == "blocked"
            )
            assert "not transferred" not in json.dumps(result) and "SECRET" not in json.dumps(
                result
            )
            assert not remote.jobs
            # A wrong pin must fail before client authentication is attempted.
            auth.clear()
            wrong = dict(
                row,
                server_host_key=asyncssh.generate_private_key("ssh-ed25519")
                .export_public_key()
                .decode()
                .strip(),
            )
            remote, owner, _ = manager(tmp_path, wrong)
            with pytest.raises(ServiceError) as exc:
                await remote.run(owner, request(remote), "check")
            assert exc.value.code == "REMOTE_HOST_KEY" and auth == []

    asyncio.run(scenario())


def test_sftp_permissions_configuration_and_session_are_checked_before_io(tmp_path, monkeypatch):
    row, _, _ = configuration(tmp_path)
    row["allow_sftp"] = False
    remote, owner, token = manager(tmp_path, row)

    async def forbidden(*args):
        pytest.fail("no connection authorized")

    monkeypatch.setattr("app.remote.connect_and_read", forbidden)

    async def scenario():
        with pytest.raises(ServiceError):
            await remote.run(owner, request(remote), "list")
        stale = request(remote).model_copy(update={"configuration_id": "0" * 32})
        with pytest.raises(ServiceError):
            await remote.run(owner, stale, "check")
        remote.sessions.revoke(token)
        with pytest.raises(ServiceError):
            await remote.run(owner, request(remote), "check")

    asyncio.run(scenario())


def test_revocation_and_concurrency_close_active_work(tmp_path, monkeypatch):
    row, _, _ = configuration(tmp_path)
    remote, owner, token = manager(tmp_path, row)
    started = asyncio.Event()
    stopped = []

    async def waiting(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(True)

    monkeypatch.setattr("app.remote.connect_and_read", waiting)

    async def scenario():
        task = asyncio.create_task(remote.run(owner, request(remote), "check"))
        await started.wait()
        with pytest.raises(ServiceError) as exc:
            await remote.run(owner, request(remote), "check")
        assert exc.value.code == "REMOTE_BUSY"
        remote.sessions.revoke(token)
        with pytest.raises(ServiceError) as exc:
            await task
        assert exc.value.code == "AUTH_REQUIRED" and stopped and not remote.jobs

    asyncio.run(scenario())


def test_audit_failure_prevents_network_connection(tmp_path, monkeypatch):
    row, _, _ = configuration(tmp_path)
    remote, owner, _ = manager(tmp_path, row)

    def failed(*args):
        raise StorageError("audit unavailable")

    async def forbidden(*args):
        pytest.fail("connection before durable audit")

    monkeypatch.setattr(remote.store, "audit", failed)
    monkeypatch.setattr("app.remote.connect_and_read", forbidden)
    with pytest.raises(StorageError):
        asyncio.run(remote.run(owner, request(remote), "check"))
    assert not remote.jobs


def test_remote_api_security_and_no_automatic_connection(client, tmp_path, monkeypatch):
    wait_settings(client)
    row, _, _ = configuration(tmp_path)
    remote = RemoteHosts(json.dumps([row]), client.app.state.sessions, client.app.state.store)
    client.app.state.remote = remote
    calls = []

    async def connected(host, kind):
        calls.append(kind)
        return {
            "host_key_verified": True,
            "authenticated": True,
            "checked_at": "2026-11-20T00:00:00Z",
            "commands_executed": False,
            "system_changed": False,
        }

    monkeypatch.setattr("app.remote.connect_and_read", connected)
    manifest = client.get("/api/v1/remote/hosts").json()
    assert not calls and len(manifest["items"]) == 1
    headers = {"origin": "http://127.0.0.1:8765", "x-localcockpit-csrf": client.app.state.csrf}
    body = request(remote).model_dump()
    assert client.post("/api/v1/remote/check", json=body).status_code == 403
    assert (
        client.post(
            "/api/v1/remote/check", headers=headers, json={**body, "confirmed": 1}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/remote/check", headers=headers, json={**body, "command": "whoami"}
        ).status_code
        == 422
    )
    response = client.post("/api/v1/remote/check", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert calls == ["check"]
    assert client.post("/api/v1/remote/exec", headers=headers, json=body).status_code == 405


def test_multiple_hosts_are_independent_and_sftp_listing_is_bounded(tmp_path):
    row, client, server = configuration(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    for index in range(205):
        (root / f"entry-{index}").touch()

    class Server(asyncssh.SSHServer):
        def begin_auth(self, username):
            return True

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            return key.export_public_key() == client.export_public_key()

    async def scenario():
        async with asyncssh.create_server(
            Server,
            "127.0.0.1",
            0,
            server_host_keys=[server],
            sftp_factory=lambda chan: asyncssh.SFTPServer(chan, chroot=os.fsencode(root)),
            config=None,
        ) as listener:
            row["port"] = listener.get_port()
            remote, owner, _ = manager(tmp_path, row)
            other = dict(row, id="other", label="Other host", group="Other")
            remote = RemoteHosts(json.dumps([row, other]), remote.sessions, remote.store)
            result = await remote.run(owner, request(remote), "list")
            assert result["truncated"] and len(result["items"]) <= 200
            inventory = remote.inventory()["items"]
            assert inventory[0]["last_check"]["host_key_verified"]
            assert inventory[1]["last_check"] is None

    asyncio.run(scenario())


def test_failure_and_cancel_release_the_connection_slot(tmp_path, monkeypatch):
    row, _, _ = configuration(tmp_path)
    remote, owner, _ = manager(tmp_path, row)

    async def failed(*args):
        raise TimeoutError("SECRET_PATH")

    monkeypatch.setattr("app.remote.connect_and_read", failed)
    with pytest.raises(ServiceError) as exc:
        asyncio.run(remote.run(owner, request(remote), "check"))
    assert "SECRET" not in exc.value.message and not remote.jobs

    async def scenario():
        started = asyncio.Event()

        async def waiting(*args):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr("app.remote.connect_and_read", waiting)
        task = asyncio.create_task(remote.run(owner, request(remote), "check"))
        await started.wait()
        remote.cancel("unrelated-owner")
        assert not task.done()
        remote.cancel(owner)
        with pytest.raises(ServiceError) as exc:
            await task
        assert exc.value.code == "REMOTE_CANCELLED" and not remote.jobs

    asyncio.run(scenario())
