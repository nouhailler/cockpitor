import asyncio
import json
import sys

import pytest
from app import services
from app.services import ServiceError, Services, redact, validate_unit


@pytest.mark.parametrize(
    "unit",
    [
        "--help.service",
        "../x.service",
        "x;id.service",
        "*.service",
        "x\n.service",
        "ssh.socket",
        "x/y.service",
    ],
)
def test_units_cannot_inject_options_or_paths(unit):
    with pytest.raises(ServiceError):
        validate_unit(unit)


def test_valid_template_and_escaped_units():
    assert validate_unit("getty@tty1.service") == "getty@tty1.service"
    assert validate_unit(r"test\x20unit.service")


def test_inventory_and_detail_use_allowlisted_fields(monkeypatch):
    adapter = Services()
    calls = []

    async def command(*args):
        calls.append(args)
        if args[1] == "list-units":
            return "ssh.service loaded active running OpenSSH server\n", ""
        return (
            "Id=ssh.service\nLoadState=loaded\nActiveState=active\nEnvironment=PASSWORD=secret\n",
            "",
        )

    monkeypatch.setattr(adapter, "command", command)
    assert asyncio.run(adapter.inventory())["items"][0]["unit"] == "ssh.service"
    detail = asyncio.run(adapter.detail("ssh.service"))
    assert "Environment" not in detail["properties"]
    assert "--" in calls[1]
    assert calls[1][-1] == "ssh.service"
    assert all(call[1] in {"list-units", "show"} for call in calls)


def row(i, message="hello"):
    return {
        "__CURSOR": f"s=abc;i={i}",
        "__REALTIME_TIMESTAMP": "1000000",
        "MESSAGE": message,
        "PRIORITY": "3",
    }


def test_log_cursor_pagination_literal_search_and_redaction(monkeypatch):
    adapter = Services()
    calls = []

    async def command(*args):
        calls.append(args)
        rows = [row(3, "password=secret <script>"), row(2, "plain"), row(1)]
        return "\n".join(json.dumps(r) for r in rows), ""

    monkeypatch.setattr(adapter, "command", command)
    page = asyncio.run(adapter.logs("ssh.service", 1, 3600, 3, "script", None))
    assert page["next_cursor"] == "s=abc;i=3"
    assert "secret" not in str(page)
    assert "<script>" in page["items"][0]["message"]
    next_page = asyncio.run(adapter.logs("ssh.service", 1, 3600, 3, "", page["next_cursor"]))
    assert next_page["items"][0]["message"] == "plain"
    assert next_page["next_cursor"] == "s=abc;i=2"
    empty = asyncio.run(adapter.logs("ssh.service", 1, 3600, 3, "[regex", None))
    assert not empty["items"] and empty["next_cursor"]
    assert not any("--grep" in arg for arg in calls[0])


@pytest.mark.parametrize(
    "stderr", ["Permission denied", "Hint: You are not seeing messages from other users"]
)
def test_journal_visibility_warning_is_not_empty_success(monkeypatch, stderr):
    adapter = Services()

    async def command(*args):
        return "", stderr

    monkeypatch.setattr(adapter, "command", command)
    with pytest.raises(ServiceError, match="droits insuffisants"):
        asyncio.run(adapter.logs("ssh.service", 50, 3600, 7, "", None))


def test_invalid_cursor_never_calls_command(monkeypatch):
    with pytest.raises(ServiceError, match="Curseur invalide"):
        asyncio.run(Services().logs("ssh.service", 50, 3600, 7, "", "../path\n"))


def test_redacts_common_secrets_and_local_token(monkeypatch):
    monkeypatch.setenv("LOCALCOCKPIT_TOKEN", "unique-local-token")
    text = redact(
        'unique-local-token Authorization: Bearer abc.xyz api_key="secret value" password=test'
    )
    assert "unique-local-token" not in text
    assert "abc.xyz" not in text and "secret value" not in text and "password=test" not in text


@pytest.mark.parametrize(
    "mode,expected",
    [("large", "OUTPUT_LIMIT"), ("slow", "COMMAND_TIMEOUT"), ("denied", "PERMISSION_DENIED")],
)
def test_real_subprocess_output_timeout_and_cleanup(monkeypatch, mode, expected):
    original = asyncio.create_subprocess_exec
    captured = []
    code = {
        "large": "print('x'*100000)",
        "slow": "import time; time.sleep(20)",
        "denied": "import sys; print('Permission denied',file=sys.stderr); sys.exit(1)",
    }[mode]

    async def spawn(*args, **kwargs):
        assert args[0] == "/usr/bin/systemctl"
        process = await original(sys.executable, "-c", code, **kwargs)
        captured.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(services, "MAX_OUTPUT", 4096)
    monkeypatch.setattr(services, "COMMAND_TIMEOUT", 0.3)
    adapter = Services()

    async def exercise():
        with pytest.raises(ServiceError) as exc:
            await asyncio.wait_for(adapter.command("/usr/bin/systemctl", "list-units"), 3)
        assert exc.value.code == expected
        assert captured[0].returncode is not None
        assert adapter.slots._value == 2

    asyncio.run(exercise())


def test_concurrency_limit_rejects_without_spawning(monkeypatch):
    async def exercise():
        adapter = Services()
        await adapter.slots.acquire()
        await adapter.slots.acquire()
        with pytest.raises(ServiceError) as exc:
            await adapter.command("/usr/bin/systemctl", "show")
        assert exc.value.code == "BUSY"
        assert adapter.slots._value == 0

    asyncio.run(exercise())


def test_unlisted_executable_is_refused():
    with pytest.raises(ServiceError) as exc:
        asyncio.run(Services().command("/bin/sh", "-c", "anything"))
    assert exc.value.code == "COMMAND_REFUSED"


def test_cancelled_command_is_reaped_and_slot_released(monkeypatch):
    original = asyncio.create_subprocess_exec
    captured = []

    async def spawn(*args, **kwargs):
        process = await original(sys.executable, "-c", "import time; time.sleep(20)", **kwargs)
        captured.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def exercise():
        adapter = Services()
        task = asyncio.create_task(adapter.command("/usr/bin/systemctl", "show"))
        while not captured:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert captured[0].returncode is not None
        assert adapter.slots._value == 2

    asyncio.run(exercise())


def test_expired_cursor_and_invalid_json_fail_explicitly(monkeypatch):
    adapter = Services()

    async def command(*args):
        return json.dumps(row(2)), ""

    monkeypatch.setattr(adapter, "command", command)
    with pytest.raises(ServiceError) as exc:
        asyncio.run(adapter.logs("ssh.service", 50, 3600, 7, "", "s=abc;i=1"))
    assert exc.value.code == "CURSOR_EXPIRED"

    async def malformed(*args):
        return "{invalid-json", ""

    monkeypatch.setattr(adapter, "command", malformed)
    with pytest.raises(ServiceError) as exc:
        asyncio.run(adapter.logs("ssh.service", 50, 3600, 7, "", None))
    assert exc.value.code == "INVALID_RESPONSE"
