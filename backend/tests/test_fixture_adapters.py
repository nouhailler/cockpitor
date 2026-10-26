"""Controlled fixture trials only. No systemd command or engine socket is opened."""

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from app import fixture_adapters as adapters
from app.actions import ActionRequest, fingerprint
from app.fixture_adapters import (
    ContainerFixtureAdapter,
    ContainerObservation,
    FixtureTrialRunner,
    ServiceFixtureAdapter,
    ServiceObservation,
)
from app.fixture_journal import MAX_TRIALS, FixtureJournal, JournalError
from app.services import ServiceError
from pydantic import ValidationError


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "POST_SECONDS", 0.06)
    monkeypatch.setattr(adapters, "POLL_SECONDS", 0.001)
    monkeypatch.setattr(adapters, "SEND_SECONDS", 0.05)
    monkeypatch.setattr(adapters, "READ_SECONDS", 0.05)
    journal = FixtureJournal(tmp_path / "trials")
    journal.initialize()
    service = {
        "unit": "fixture.service",
        "load": "loaded",
        "active": "active",
        "substate": "running",
        "pid": 123,
        "invocation": "a" * 32,
        "needs_reload": False,
        "configuration_fingerprint": "c" * 64,
    }
    container = {
        "id": "a" * 64,
        "engine": "docker",
        "status": "running",
        "running": True,
        "started_at": "2026-01-01T00:00:00Z",
        "configuration_fingerprint": "c" * 64,
    }
    h = SimpleNamespace(journal=journal, service=service, container=container, sent=[], reads=0)

    async def read_service(_):
        h.reads += 1
        return dict(service)

    async def read_container(engine, target):
        h.reads += 1
        return dict(container)

    async def send_service(command):
        assert journal.status("d" * 32) == "dispatching"
        h.sent.append(command)
        active = command[3] != "stop"
        service.update(
            active="active" if active else "inactive",
            substate="running" if active else "dead",
            pid=124 if active else 0,
            invocation="b" * 32 if active else None,
        )
        return True

    async def send_container(operation):
        assert journal.status("d" * 32) == "dispatching"
        h.sent.append(operation)
        container.update(running=True, status="running", started_at="2026-01-02T00:00:00Z")
        return 204

    h.service_adapter = ServiceFixtureAdapter(read_service, send_service)
    h.container_adapter = ContainerFixtureAdapter(read_container, send_container)
    grants = frozenset(
        {(f"service.{verb}", "fixture.service", None) for verb in ("start", "stop", "restart")}
        | {
            (f"container.{verb}", "a" * 64, engine)
            for verb in ("start", "restart")
            for engine in ("docker", "podman")
        }
    )
    h.runner = FixtureTrialRunner(journal, grants, h.service_adapter, h.container_adapter)
    return h


def service_request(action="restart"):
    return ActionRequest(action="service." + action, target="fixture.service")


def container_request(action="restart", engine="docker"):
    return ActionRequest(action="container." + action, target="a" * 64, engine=engine)


def expected(h, request):
    model = ServiceObservation if request.action.startswith("service.") else ContainerObservation
    state = h.service if request.action.startswith("service.") else h.container
    return fingerprint(request, model.model_validate(state).model_dump())


def trial(h, request, checkpoint=lambda: None):
    return h.runner.run_fixture("d" * 32, request, expected(h, request), checkpoint)


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
def test_fixed_service_command_and_postcondition(lab, action):
    if action == "start":
        lab.service.update(active="inactive", substate="dead", pid=0, invocation=None)
    result = asyncio.run(trial(lab, service_request(action)))
    assert result.status == "verified" and result.scope == "fixture_only"
    assert lab.sent == [
        ("/usr/bin/systemctl", "--no-pager", "--no-ask-password", action, "--", "fixture.service")
    ]
    assert [event["status"] for event in lab.journal.events("d" * 32)] == [
        "prepared",
        "dispatching",
        "verified",
    ]
    assert lab.reads == 3


@pytest.mark.parametrize("engine", ["docker", "podman"])
@pytest.mark.parametrize("action", ["start", "restart"])
def test_fixed_container_request_and_postcondition(lab, engine, action):
    lab.container["engine"] = engine
    if action == "start":
        lab.container.update(status="created", running=False, started_at=None)
    result = asyncio.run(trial(lab, container_request(action, engine)))
    assert result.status == "verified"
    assert len(lab.sent) == 1
    operation = lab.sent[0]
    assert operation.method == "POST" and operation.engine == engine
    assert operation.path == f"/containers/{'a' * 64}/" + (
        "start" if action == "start" else "restart?t=5"
    )


@pytest.mark.parametrize("change", ["pid", "invocation", "configuration", "failed"])
def test_acknowledgement_without_service_postcondition_is_unknown(lab, change):
    async def send(command):
        lab.sent.append(command)
        if change == "pid":
            lab.service.update(pid=0, invocation="b" * 32)
        elif change == "configuration":
            lab.service.update(configuration_fingerprint="f" * 64, invocation="b" * 32)
        elif change == "failed":
            lab.service.update(active="failed", substate="failed", pid=0)
        return True

    lab.service_adapter.send = send
    result = asyncio.run(trial(lab, service_request()))
    assert result.status == "unknown" and len(lab.sent) == 1
    assert lab.journal.status("d" * 32) == "unknown"


@pytest.mark.parametrize(
    "change",
    [
        "same_generation",
        "older_generation",
        "future_generation",
        "configuration",
        "paused",
        "not_running",
    ],
)
def test_container_restart_requires_new_running_generation(lab, change):
    async def send(operation):
        lab.sent.append(operation)
        if change == "older_generation":
            lab.container["started_at"] = "2025-01-01T00:00:00Z"
        elif change == "future_generation":
            lab.container["started_at"] = "9999-01-01T00:00:00Z"
        elif change == "configuration":
            lab.container.update(
                started_at="2026-01-02T00:00:00Z", configuration_fingerprint="e" * 64
            )
        elif change == "paused":
            lab.container.update(started_at="2026-01-02T00:00:00Z", status="paused")
        elif change == "not_running":
            lab.container.update(started_at="2026-01-02T00:00:00Z", running=False)
        return 204

    lab.container_adapter.send = send
    result = asyncio.run(trial(lab, container_request()))
    assert result.status == "unknown" and len(lab.sent) == 1


@pytest.mark.parametrize("phase", [1, 2])
def test_changed_preflight_never_dispatches(lab, phase):
    async def read(_):
        lab.reads += 1
        state = dict(lab.service)
        if lab.reads == phase:
            state["configuration_fingerprint"] = "e" * 64
        return state

    lab.service_adapter.read = read
    result = asyncio.run(trial(lab, service_request()))
    assert result.status == "not_dispatched" and not lab.sent


@pytest.mark.parametrize("change", ["unit", "reload", "load", "invocation", "extra"])
def test_invalid_service_identity_or_shape_never_dispatches(lab, change):
    async def read(_):
        state = dict(lab.service)
        state[
            {
                "unit": "unit",
                "reload": "needs_reload",
                "load": "load",
                "invocation": "invocation",
                "extra": "command",
            }[change]
        ] = {
            "unit": "other.service",
            "reload": True,
            "load": "not-found",
            "invocation": "0" * 32,
            "extra": "secret",
        }[change]
        return state

    lab.service_adapter.read = read
    assert asyncio.run(trial(lab, service_request())).status == "not_dispatched"
    assert not lab.sent


@pytest.mark.parametrize("state", ["active", "failed", "activating"])
def test_service_start_only_from_stable_inactive_state(lab, state):
    lab.service["active"] = state
    assert asyncio.run(trial(lab, service_request("start"))).status == "not_dispatched"
    assert not lab.sent


@pytest.mark.parametrize("cause", ["error", "timeout", "negative_ack"])
def test_dispatch_failure_is_unknown_without_retry(lab, cause):
    async def send(command):
        lab.sent.append(command)
        if cause == "error":
            raise OSError("secret driver error")
        if cause == "timeout":
            await asyncio.Event().wait()
        return False

    lab.service_adapter.send = send
    result = asyncio.run(trial(lab, service_request()))
    assert result.status == "unknown" and len(lab.sent) == 1
    assert "secret" not in repr(result)


@pytest.mark.parametrize("status", [200, 304, 403, 404, 409, 500, 204.0, True])
def test_container_ack_is_strict_and_never_retried(lab, status):
    async def send(operation):
        lab.sent.append(operation)
        return status

    lab.container_adapter.send = send
    assert asyncio.run(trial(lab, container_request())).status == "unknown"
    assert len(lab.sent) == 1


@pytest.mark.parametrize("phase", ["before", "after"])
def test_cancel_never_claims_to_undo_a_dispatched_effect(lab, phase):
    async def run():
        entered = asyncio.Event()
        if phase == "before":

            async def read(_):
                entered.set()
                await asyncio.Event().wait()

            lab.service_adapter.read = read
        else:

            async def send(command):
                lab.sent.append(command)
                entered.set()
                await asyncio.Event().wait()

            lab.service_adapter.send = send
        task = asyncio.create_task(trial(lab, service_request()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert lab.journal.status("d" * 32) == (
            "not_dispatched" if phase == "before" else "unknown"
        )
        assert bool(lab.sent) is (phase == "after")

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["dispatching", "verified"])
def test_required_journal_failure_never_reports_success(lab, monkeypatch, phase):
    original = lab.journal.transition

    def fail(trial_id, previous, status):
        if status == phase:
            raise JournalError("fixture")
        return original(trial_id, previous, status)

    monkeypatch.setattr(lab.journal, "transition", fail)
    with pytest.raises(JournalError):
        asyncio.run(trial(lab, service_request()))
    assert len(lab.sent) == (0 if phase == "dispatching" else 1)
    lab.journal.initialize()
    assert lab.journal.status("d" * 32) == (
        "not_dispatched" if phase == "dispatching" else "unknown"
    )


def test_trial_ids_survive_restart_and_journal_is_minimal(lab):
    request = service_request()
    baseline = expected(lab, request)
    assert asyncio.run(trial(lab, request)).status == "verified"
    lab.journal.initialize()
    with pytest.raises(JournalError):
        asyncio.run(lab.runner.run_fixture("d" * 32, request, baseline, lambda: None))
    assert len(lab.sent) == 1
    assert "fixture.service" not in lab.journal.path.read_bytes().decode(errors="ignore")
    assert "configuration_fingerprint" not in lab.journal.path.read_bytes().decode(errors="ignore")


def test_no_grant_or_foreign_target_never_reads_or_dispatches(lab):
    with pytest.raises(ValueError):
        asyncio.run(trial(lab, ActionRequest(action="service.restart", target="other.service")))
    assert not lab.sent and lab.reads == 0


def test_real_private_fixture_process_exercises_service_adapter(tmp_path):
    async def run():
        journal = FixtureJournal(tmp_path / "trial-db")
        journal.initialize()
        state = {
            "unit": "fixture.service",
            "load": "loaded",
            "active": "active",
            "substate": "running",
            "pid": 123,
            "invocation": "a" * 32,
            "needs_reload": False,
            "configuration_fingerprint": "c" * 64,
        }
        state_file = tmp_path / "fixture-state.json"
        state_file.write_text(json.dumps(state))
        fixture = Path(__file__).parent / "fixtures" / "service_fixture.py"
        sent = []

        async def process(verb):
            child = await asyncio.create_subprocess_exec(
                sys.executable,
                str(fixture),
                str(state_file),
                verb,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                output, error = await asyncio.wait_for(child.communicate(), 2)
                assert child.returncode == 0 and not error
                return output
            finally:
                if child.returncode is None:
                    child.kill()
                    await child.communicate()

        async def read(unit):
            assert unit == "fixture.service"
            return json.loads(await process("read"))

        async def send(command):
            assert command == (
                "/usr/bin/systemctl",
                "--no-pager",
                "--no-ask-password",
                "restart",
                "--",
                "fixture.service",
            )
            assert journal.status("d" * 32) == "dispatching"
            sent.append(command)
            await process("restart")  # ONLY the Python fixture is executed.
            return True

        async def forbidden(*args):
            raise AssertionError("No container access")

        runner = FixtureTrialRunner(
            journal,
            frozenset({("service.restart", "fixture.service", None)}),
            ServiceFixtureAdapter(read, send),
            ContainerFixtureAdapter(forbidden, forbidden),
        )
        request = service_request()
        result = await runner.run_fixture(
            "d" * 32, request, fingerprint(request, state), lambda: None
        )
        assert result.status == "verified" and len(sent) == 1
        assert json.loads(state_file.read_text())["invocation"] == "b" * 32

    asyncio.run(run())


@pytest.mark.parametrize("engine", ["docker", "podman"])
@pytest.mark.parametrize("verb", ["start", "restart"])
def test_real_unix_http_fixture_exercises_container_adapter(tmp_path, engine, verb):
    async def run():
        private = tmp_path / "private"
        private.mkdir(mode=0o700)
        socket_path = private / "engine.sock"
        journal = FixtureJournal(tmp_path / "journal")
        journal.initialize()
        state = {
            "id": "a" * 64,
            "engine": engine,
            "status": "created" if verb == "start" else "running",
            "running": verb != "start",
            "started_at": None if verb == "start" else "2026-01-01T00:00:00Z",
            "configuration_fingerprint": "c" * 64,
        }
        before = dict(state)
        seen, tasks = [], set()

        async def handler(reader, writer):
            task = asyncio.current_task()
            tasks.add(task)
            try:
                async with asyncio.timeout(1):
                    method, path, _ = (await reader.readline()).decode().strip().split(" ")
                    while await reader.readline() not in {b"\r\n", b""}:
                        pass
                    seen.append((method, path))
                    if method == "POST":
                        assert journal.status("d" * 32) == "dispatching"
                        assert path == f"/v1.47/containers/{'a' * 64}/" + (
                            "start" if verb == "start" else "restart?t=5"
                        )
                        state.update(
                            status="running", running=True, started_at="2026-01-02T00:00:00Z"
                        )
                        writer.write(
                            b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                        )
                    else:
                        assert method == "GET" and path == f"/v1.47/containers/{'a' * 64}/json"
                        body = json.dumps(state).encode()
                        writer.write(
                            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                            + str(len(body)).encode()
                            + b"\r\nConnection: close\r\n\r\n"
                            + body
                        )
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                tasks.discard(task)

        server = await asyncio.start_unix_server(handler, path=socket_path)
        socket_path.chmod(0o600)
        try:
            async with httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(uds=str(socket_path)),
                timeout=1,
                trust_env=False,
                follow_redirects=False,
            ) as client:

                async def read(selected_engine, target):
                    assert selected_engine == engine and target == "a" * 64
                    reply = await client.get(f"http://fixture/v1.47/containers/{target}/json")
                    reply.raise_for_status()
                    return reply.json()

                async def send(operation):
                    assert operation.engine == engine
                    reply = await client.request(
                        operation.method, "http://fixture/v1.47" + operation.path
                    )
                    return reply.status_code

                async def forbidden(*args):
                    raise AssertionError("No service access")

                request = container_request(verb, engine)
                runner = FixtureTrialRunner(
                    journal,
                    frozenset({(request.action, request.target, request.engine)}),
                    ServiceFixtureAdapter(forbidden, forbidden),
                    ContainerFixtureAdapter(read, send),
                )
                result = await runner.run_fixture(
                    "d" * 32, request, fingerprint(request, before), lambda: None
                )
                assert result.status == "verified"
                assert sum(method == "POST" for method, _ in seen) == 1
                assert sum(method == "GET" for method, _ in seen) == 3
        finally:
            server.close()
            await server.wait_closed()
            await asyncio.gather(*tuple(tasks), return_exceptions=False)

    asyncio.run(run())


def test_journal_quota_never_evicts_trial_ids(lab):
    for index in range(MAX_TRIALS):
        trial_id = f"{index:032x}"
        lab.journal.reserve(trial_id, "service.start")
        lab.journal.transition(trial_id, "prepared", "not_dispatched")
    with pytest.raises(JournalError):
        lab.journal.reserve("f" * 32, "service.start")
    lab.journal.initialize()
    assert lab.journal.status("0" * 32) == "not_dispatched"
    with pytest.raises(JournalError):
        lab.journal.reserve("0" * 32, "service.start")


@pytest.mark.parametrize(
    "kind",
    ["directory_mode", "directory_symlink", "database_symlink", "database_mode", "future_schema"],
)
def test_private_journal_rejects_unsafe_paths_or_schema(tmp_path, kind):
    directory = tmp_path / "journal"
    journal = FixtureJournal(directory)
    journal.initialize()
    if kind == "directory_mode":
        directory.chmod(0o755)
    elif kind == "directory_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        journal = FixtureJournal(alias)
    elif kind == "database_symlink":
        journal.path.unlink()
        journal.path.symlink_to(tmp_path / "missing")
    elif kind == "database_mode":
        journal.path.chmod(0o644)
    else:
        with journal.connection() as db:
            db.execute("PRAGMA user_version=3")
    with pytest.raises(JournalError):
        journal.initialize()
    if kind == "future_schema":
        with journal.connection() as db:
            assert db.execute("PRAGMA user_version").fetchone()[0] == 3


def test_journal_state_and_audit_rollback_together(lab):
    lab.journal.reserve("d" * 32, "service.restart")
    with lab.journal.connection() as db:
        db.execute(
            "CREATE TRIGGER reject_dispatch BEFORE INSERT ON events WHEN NEW.status='dispatching' BEGIN SELECT RAISE(FAIL,'fixture'); END"
        )
    with pytest.raises(JournalError):
        asyncio.run(trial(lab, service_request()))
    # The replay above is refused before dispatch; exercise the transition transaction itself.
    with pytest.raises(JournalError):
        lab.journal.transition("d" * 32, "prepared", "dispatching")
    assert lab.journal.status("d" * 32) == "prepared"
    assert [event["status"] for event in lab.journal.events("d" * 32)] == ["prepared"]
    assert not lab.sent


def test_root_fixture_journal_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(JournalError):
        FixtureJournal(tmp_path / "journal").initialize()
    assert not (tmp_path / "journal").exists()


def test_invalid_post_read_is_unknown_and_not_retried(lab):
    async def read(_):
        lab.reads += 1
        if lab.reads >= 3:
            raise OSError("secret read error")
        return dict(lab.service)

    lab.service_adapter.read = read
    assert asyncio.run(trial(lab, service_request())).status == "unknown"
    assert len(lab.sent) == 1


@pytest.mark.parametrize("phase", ["preflight", "dispatch", "postcondition"])
def test_revocation_checkpoint_prevents_success(lab, phase):
    def checkpoint():
        count = lab.reads
        if (
            (phase == "preflight" and count == 0)
            or (phase == "dispatch" and count == 2)
            or (phase == "postcondition" and lab.sent)
        ):
            raise ValueError("revoked")

    result = asyncio.run(trial(lab, service_request(), checkpoint))
    assert result.status == ("unknown" if phase == "postcondition" else "not_dispatched")
    assert bool(lab.sent) is (phase == "postcondition")


def test_concurrent_fixture_trial_is_refused_without_second_dispatch(lab):
    async def run():
        entered = asyncio.Event()

        async def blocked(command):
            lab.sent.append(command)
            entered.set()
            await asyncio.Event().wait()

        lab.service_adapter.send = blocked
        first = asyncio.create_task(trial(lab, service_request()))
        await entered.wait()
        with pytest.raises(ValueError):
            await lab.runner.run_fixture(
                "e" * 32, service_request(), expected(lab, service_request()), lambda: None
            )
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert len(lab.sent) == 1

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["preflight", "postcondition"])
@pytest.mark.parametrize("field", ["id", "engine"])
def test_container_identity_is_rechecked_on_both_sides_of_dispatch(lab, phase, field):
    async def read(engine, target):
        lab.reads += 1
        state = dict(lab.container)
        if (phase == "preflight" and lab.reads == 1) or (
            phase == "postcondition" and lab.reads == 3
        ):
            state[field] = "b" * 64 if field == "id" else "podman"
        return state

    lab.container_adapter.read = read
    result = asyncio.run(trial(lab, container_request()))
    assert result.status == ("not_dispatched" if phase == "preflight" else "unknown")
    assert len(lab.sent) == (0 if phase == "preflight" else 1)


@pytest.mark.parametrize(
    "target", ["../../fixture.service", "ssh.service", "fixture.service; reboot"]
)
def test_service_adapter_revalidates_even_constructed_models(lab, target):
    request = ActionRequest.model_construct(action="service.restart", target=target, engine=None)
    with pytest.raises((ValidationError, ServiceError)):
        asyncio.run(lab.service_adapter.mutate(request))
    assert not lab.sent


def test_committed_dispatch_intent_is_unknown_after_child_process_exit(tmp_path):
    async def run():
        directory = tmp_path / "journal"
        code = (
            "import os,sys; from pathlib import Path; "
            "from app.fixture_journal import FixtureJournal; "
            "j=FixtureJournal(Path(sys.argv[1])); j.initialize(); "
            "j.reserve('d'*32,'service.restart'); "
            "j.transition('d'*32,'prepared','dispatching'); os._exit(0)"
        )
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            str(directory),
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            output, error = await asyncio.wait_for(child.communicate(), 3)
            assert child.returncode == 0 and not output and not error
        finally:
            if child.returncode is None:
                child.kill()
                await child.communicate()
        journal = FixtureJournal(directory)
        journal.initialize()
        assert journal.status("d" * 32) == "unknown"
        assert [event["status"] for event in journal.events("d" * 32)] == [
            "prepared",
            "dispatching",
            "unknown",
        ]
        with pytest.raises(JournalError):
            journal.reserve("d" * 32, "service.restart")

    asyncio.run(run())
