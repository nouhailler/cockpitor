"""Read-only prerequisite report policy, transport and private report output."""

import asyncio
import json
import stat
import sys

import httpx
import pytest
from app import qualification_preflight as preflight
from app.i18n import language


class Probe(preflight.PreflightProbe):
    def __init__(self):
        self.values = {
            "non_root": True,
            "debian": True,
            "debian_version": "13",
            "systemd_pid1": True,
            "python_supported": True,
            "python": "3.13.5",
            "kernel": "6.12.0",
        }
        self.reads = {
            "vm": (0, "kvm"),
            "container": (1, "none"),
            "state": (0, "running"),
            "systemd": (0, "systemd 257 (private build)"),
            "revision": (0, "a" * 40),
            "clean": (0, ""),
        }
        self.calls = []

    def facts(self):
        return dict(self.values)

    async def command(self, name):
        return self.reads[name]

    async def engine(self, socket_path):
        self.calls.append(socket_path)
        return {"api": "1.47", "version": "28.0.0"}


def test_all_prerequisites_are_not_qualification_or_permission():
    probe = Probe()
    report = asyncio.run(
        preflight.collect(
            docker_socket="/private/docker.sock", podman_socket="/private/podman.sock", probe=probe
        )
    )
    assert report["status"] == "prerequisites_met"
    assert report["qualified"] is False and report["system_execution_enabled"] is False
    assert report["read_only"] is True
    assert all(row["passed"] for row in report["checks"])
    assert len(probe.calls) == 2
    assert "/private" not in json.dumps(report)


@pytest.mark.parametrize("fact", ["non_root", "debian", "systemd_pid1", "python_supported"])
def test_failed_environment_never_contacts_any_engine(fact):
    probe = Probe()
    probe.values[fact] = False
    report = asyncio.run(
        preflight.collect(
            docker_socket="/private/docker.sock", podman_socket="/private/podman.sock", probe=probe
        )
    )
    assert report["status"] == "blocked" and not probe.calls
    assert all(
        row["code"] == "ENVIRONMENT_BLOCKED"
        for row in report["checks"]
        if row["id"] in {"docker", "podman"}
    )


@pytest.mark.parametrize(
    "name,result",
    [
        ("vm", (1, "none")),
        ("vm", (None, "")),
        ("container", (0, "docker")),
        ("container", (None, "")),
        ("state", (1, "degraded")),
        ("systemd", (0, "secret")),
        ("revision", (0, "PRIVATE_REVISION")),
        ("clean", (0, " M PRIVATE_FILE")),
    ],
)
def test_unknown_or_unsuitable_readings_fail_closed(name, result):
    probe = Probe()
    probe.reads[name] = result
    report = asyncio.run(
        preflight.collect(docker_socket="/x.sock", podman_socket="/y.sock", probe=probe)
    )
    assert report["status"] == "blocked" and not probe.calls
    assert "PRIVATE" not in json.dumps(report)
    assert "secret" not in json.dumps(report)


def test_profiles_do_not_imply_unselected_engines_and_no_socket_is_implicit():
    probe = Probe()
    assert asyncio.run(preflight.collect("systemd", probe=probe))["status"] == "prerequisites_met"
    assert not probe.calls
    report = asyncio.run(preflight.collect("docker", probe=probe))
    assert report["checks"][-1]["code"] == "SOCKET_NOT_CONFIGURED"
    assert all(row["id"] != "podman" for row in report["checks"])
    with pytest.raises(ValueError):
        asyncio.run(preflight.collect("shell", probe=probe))


def test_unexpected_version_facts_are_not_exposed():
    probe = Probe()
    probe.values.update(
        python="PRIVATE_PYTHON", kernel="PRIVATE_KERNEL", debian_version="PRIVATE_OS"
    )
    report = asyncio.run(preflight.collect("systemd", probe=probe))
    assert "PRIVATE" not in json.dumps(report)
    assert report["versions"]["kernel"] is None


def test_report_labels_support_english():
    token = language.set("en")
    try:
        report = asyncio.run(preflight.collect("systemd", probe=Probe()))
        assert report["checks"][0]["label"] == "Unprivileged account"
    finally:
        language.reset(token)


def test_private_report_is_new_private_file_and_never_overwrites(tmp_path):
    private = tmp_path / "reports"
    private.mkdir(mode=0o700)
    path = private / "preflight.json"
    report = asyncio.run(preflight.collect("systemd", probe=Probe()))
    preflight.save_report(path, report)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == report
    with pytest.raises(FileExistsError):
        preflight.save_report(path, report)
    symlink = private / "alias.json"
    symlink.symlink_to(path)
    with pytest.raises(FileExistsError):
        preflight.save_report(symlink, report)
    private.chmod(0o755)
    with pytest.raises(ValueError):
        preflight.save_report(private / "unsafe.json", report)


def test_unknown_command_never_starts_a_process(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No command may start")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    with pytest.raises(ValueError):
        asyncio.run(preflight.command("restart"))


@pytest.mark.parametrize("mode", ["timeout", "overflow"])
def test_read_command_limit_kills_only_its_fixture_process(monkeypatch, mode):
    original = asyncio.create_subprocess_exec
    children = []

    async def fixture(*args, **kwargs):
        assert args == preflight.COMMANDS["vm"]
        assert kwargs["start_new_session"] is True
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        code = (
            "import time; time.sleep(10)"
            if mode == "timeout"
            else "import sys,time; sys.stdout.write('x'*8192); sys.stdout.flush(); time.sleep(10)"
        )
        child = await original(sys.executable, "-c", code, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fixture)
    monkeypatch.setattr(preflight, "COMMAND_SECONDS", 0.15)
    assert asyncio.run(preflight.command("vm")) == (None, "")
    assert children[0].returncode is not None


@pytest.mark.parametrize("version", ["PRIVATE_VERSION", "9" * 200, "28.0.0-secret"])
def test_engine_version_is_bounded_and_filtered(tmp_path, monkeypatch, version):
    import socket

    path = tmp_path / "engine.sock"
    sock = socket.socket(socket.AF_UNIX)
    try:
        sock.bind(str(path))
        original = httpx.AsyncClient
        seen = []

        async def response(request):
            seen.append((request.method, request.url.path))
            return httpx.Response(
                200, json={"ApiVersion": "1.47", "MinAPIVersion": "1.24", "Version": version}
            )

        def client(**kwargs):
            assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
            return original(transport=httpx.MockTransport(response), timeout=1, trust_env=False)

        monkeypatch.setattr(httpx, "AsyncClient", client)
        result = asyncio.run(preflight.PreflightProbe().engine(str(path)))
        assert seen == [("GET", "/version")]
        assert result == (
            {"api": "1.47", "version": "28.0.0"} if version.endswith("-secret") else None
        )
    finally:
        sock.close()


def test_real_unix_engine_version_probe_only_sends_get(tmp_path):
    async def run():
        path = tmp_path / "engine.sock"
        calls, tasks = [], set()

        async def serve(reader, writer):
            task = asyncio.current_task()
            tasks.add(task)
            try:
                async with asyncio.timeout(1):
                    line = (await reader.readline()).decode()
                    calls.append(line)
                    while await reader.readline() not in {b"\r\n", b""}:
                        pass
                    body = json.dumps(
                        {"ApiVersion": "1.47", "Version": "28.0.0", "PRIVATE_ENV": "SECRET"}
                    ).encode()
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Length: "
                        + str(len(body)).encode()
                        + b"\r\nConnection: close\r\n\r\n"
                        + body
                    )
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                tasks.discard(task)

        server = await asyncio.start_unix_server(serve, path=path)
        try:
            result = await preflight.PreflightProbe().engine(str(path))
            assert result == {"api": "1.47", "version": "28.0.0"}
            assert calls == ["GET /version HTTP/1.1\r\n"]
        finally:
            server.close()
            await server.wait_closed()
            await asyncio.gather(*tuple(tasks))

    asyncio.run(run())


def test_read_timeout_cleans_descendant_even_if_parent_has_exited(tmp_path, monkeypatch):
    import psutil

    original = asyncio.create_subprocess_exec
    pid_file = tmp_path / "descendant.pid"

    async def fixture(*args, **kwargs):
        code = (
            "import subprocess,sys; from pathlib import Path; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
            "Path(sys.argv[1]).write_text(str(child.pid))"
        )
        return await original(sys.executable, "-c", code, str(pid_file), **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fixture)
    monkeypatch.setattr(preflight, "COMMAND_SECONDS", 0.3)
    assert asyncio.run(preflight.command("vm")) == (None, "")
    descendant = int(pid_file.read_text())
    try:
        assert psutil.Process(descendant).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        pass
