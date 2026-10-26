"""Read-only fixture reconciliation and persistent uncertainty fences."""

import asyncio
import json
import sqlite3
import stat

import pytest
from app.actions import ActionRequest
from app.fixture_adapters import FixtureTrialRunner
from app.fixture_journal import FixtureJournal, JournalError
from test_fixture_adapters import container_request, expected, service_request, trial

pytest_plugins = ["test_fixture_adapters"]


async def unknown(h, kind="service", verb="restart"):
    request = (
        service_request(verb)
        if kind == "service"
        else container_request(verb, h.container["engine"])
    )
    state = h.service if kind == "service" else h.container
    before = dict(state)
    adapter = h.service_adapter if kind == "service" else h.container_adapter
    send = adapter.send

    async def lose_ack(operation):
        await send(operation)
        raise OSError("fixture acknowledgement lost")

    adapter.send = lose_ack
    result = await trial(h, request)
    assert result.status == "unknown"
    return request, before


@pytest.mark.parametrize("kind", ["service", "container"])
def test_reconcile_observes_only_and_keeps_unknown_history(lab, kind):
    async def run():
        request, before = await unknown(lab, kind)
        sent, reads = len(lab.sent), lab.reads
        result = await lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None)
        assert result.status == "reconciled" and result.scope == "fixture_only"
        assert len(lab.sent) == sent == 1 and lab.reads == reads + 2
        assert [event["status"] for event in lab.journal.events("d" * 32)] == [
            "prepared",
            "dispatching",
            "unknown",
            "reconciled",
        ]
        with pytest.raises(JournalError):
            await lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None)
        assert len(lab.sent) == 1

    asyncio.run(run())


def test_unknown_target_blocks_all_verbs_after_reopening(lab):
    async def run():
        await unknown(lab)
        journal = FixtureJournal(lab.journal.directory)
        journal.initialize()
        runner = FixtureTrialRunner(
            journal, lab.runner.grants, lab.service_adapter, lab.container_adapter
        )
        reads = lab.reads
        for verb in ("start", "stop", "restart"):
            request = service_request(verb)
            with pytest.raises(JournalError):
                await runner.run_fixture("e" * 32, request, expected(lab, request), lambda: None)
        assert len(lab.sent) == 1 and lab.reads == reads

    asyncio.run(run())


def test_resolved_target_allows_only_a_new_explicit_trial(lab):
    async def run():
        request, before = await unknown(lab)
        assert (
            await lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None)
        ).status == "reconciled"
        request = service_request("stop")
        lab.journal.reserve(
            "e" * 32, request.action, request=request, approved_fingerprint=expected(lab, request)
        )
        assert lab.journal.status("e" * 32) == "prepared"
        assert len(lab.sent) == 1  # Reconciliation never initiates the next trial.
        lab.journal.transition("e" * 32, "prepared", "not_dispatched")
        lab.journal.initialize()
        with pytest.raises(JournalError):
            lab.journal.reserve(
                "d" * 32,
                request.action,
                request=request,
                approved_fingerprint=expected(lab, request),
            )

    asyncio.run(run())


@pytest.mark.parametrize("change", ["baseline", "action", "target"])
def test_wrong_original_binding_never_reads_or_releases(lab, change):
    async def run():
        request, before = await unknown(lab)
        reads = lab.reads
        if change == "baseline":
            before["invocation"] = "f" * 32
        elif change == "action":
            request = service_request("stop")
        else:
            request = ActionRequest(action="service.restart", target="other.service")
        with pytest.raises((JournalError, ValueError)):
            await lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None)
        assert lab.reads == reads and lab.journal.status("d" * 32) == "unknown"

    asyncio.run(run())


def test_wrong_engine_cannot_reconcile_but_is_a_distinct_resource(lab):
    async def run():
        _, before = await unknown(lab, "container")
        request = container_request(engine="podman")
        before["engine"] = "podman"
        with pytest.raises(JournalError):
            await lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None)
        lab.container["engine"] = "podman"
        lab.journal.reserve(
            "e" * 32, request.action, request=request, approved_fingerprint=expected(lab, request)
        )
        assert lab.journal.status("d" * 32) == "unknown"
        assert lab.journal.status("e" * 32) == "prepared"

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure", ["configuration", "generation", "changing_reads", "error", "timeout", "revoked"]
)
def test_unconfirmed_reconciliation_preserves_fence(lab, failure):
    async def run():
        request, before = await unknown(lab)
        calls = [0]

        async def read(_):
            calls[0] += 1
            state = dict(lab.service)
            if failure == "configuration":
                state["configuration_fingerprint"] = "f" * 64
            elif failure == "generation":
                state["invocation"] = before["invocation"]
            elif failure == "changing_reads" and calls[0] == 2:
                state["invocation"] = "c" * 32
            elif failure == "error":
                raise OSError("secret read data")
            elif failure == "timeout":
                await asyncio.Event().wait()
            return state

        def checkpoint():
            if failure == "revoked":
                raise ValueError("revoked")

        lab.service_adapter.read = read
        result = await lab.runner.reconcile_fixture("d" * 32, request, before, checkpoint)
        assert result.status == "unconfirmed"
        assert "secret" not in repr(result)
        assert lab.journal.status("d" * 32) == "unknown"
        assert len(lab.sent) == 1
        with pytest.raises(JournalError):
            await lab.runner.run_fixture("e" * 32, request, expected(lab, request), lambda: None)

    asyncio.run(run())


def test_cancelled_reconciliation_never_changes_journal(lab):
    async def run():
        request, before = await unknown(lab)
        entered = asyncio.Event()

        async def read(_):
            entered.set()
            await asyncio.Event().wait()

        lab.service_adapter.read = read
        task = asyncio.create_task(
            lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None)
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert lab.journal.status("d" * 32) == "unknown"
        assert len(lab.sent) == 1

    asyncio.run(run())


def test_failed_reconciliation_audit_rolls_back_release(lab):
    async def run():
        request, before = await unknown(lab)
        with lab.journal.connection() as db:
            db.execute(
                "CREATE TRIGGER reject_reconciliation BEFORE INSERT ON events WHEN NEW.status='reconciled' BEGIN SELECT RAISE(FAIL,'fixture'); END"
            )
        with pytest.raises(JournalError):
            await lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None)
        assert lab.journal.status("d" * 32) == "unknown"
        assert [event["status"] for event in lab.journal.events("d" * 32)][-1] == "unknown"
        with pytest.raises(JournalError):
            lab.journal.reserve(
                "e" * 32,
                request.action,
                request=request,
                approved_fingerprint=expected(lab, request),
            )

    asyncio.run(run())


def test_active_target_fence_is_shared_by_independent_runner_instances(lab):
    request = service_request()
    lab.journal.reserve(
        "d" * 32, request.action, request=request, approved_fingerprint=expected(lab, request)
    )
    other = FixtureJournal(lab.journal.directory)
    # Do not initialize a journal while another trial is alive.
    with pytest.raises(JournalError):
        other.reserve(
            "e" * 32,
            "service.stop",
            request=service_request("stop"),
            approved_fingerprint=expected(lab, service_request("stop")),
        )
    assert not lab.sent


@pytest.mark.parametrize("change", ["missing", "short", "rotated"])
def test_missing_or_corrupt_resource_key_fails_closed(lab, change):
    with lab.journal.connection() as db:
        if change == "missing":
            db.execute("DELETE FROM metadata WHERE name='resource_key'")
        else:
            db.execute(
                "UPDATE metadata SET value=? WHERE name='resource_key'",
                (b"bad" if change == "short" else b"x" * 32,),
            )
    with pytest.raises(JournalError):
        lab.journal.initialize()
    request = service_request()
    with pytest.raises(JournalError):
        lab.journal.reserve(
            "e" * 32, request.action, request=request, approved_fingerprint=expected(lab, request)
        )


def legacy_journal(tmp_path, status):
    directory = tmp_path / "legacy"
    directory.mkdir(mode=0o700)
    journal = FixtureJournal(directory)
    with sqlite3.connect(journal.path) as db:
        db.execute(
            "CREATE TABLE trials(id TEXT PRIMARY KEY,action TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE events(sequence INTEGER PRIMARY KEY,trial_id TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO trials VALUES (?,?,?,?)", ("d" * 32, "service.restart", status, "legacy")
        )
        db.execute("PRAGMA user_version=1")
    journal.path.chmod(0o600)
    return journal


def test_v1_migration_backs_up_and_legacy_unknown_blocks_all_targets(tmp_path):
    journal = legacy_journal(tmp_path, "dispatching")
    journal.initialize()
    backups = list(journal.directory.glob("backup-trials-v1-*.sqlite3"))
    assert len(backups) == 1 and stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT status FROM trials").fetchone()[0] == "dispatching"
    with journal.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert journal.status("d" * 32) == "unknown"
    request = ActionRequest(action="service.start", target="other.service")
    with pytest.raises(JournalError):
        journal.reserve("e" * 32, request.action, request=request, approved_fingerprint="a" * 64)
    with pytest.raises(JournalError):
        journal.require_unknown("d" * 32, request, "a" * 64)
    journal.initialize()
    assert len(list(journal.directory.glob("backup-trials-v1-*.sqlite3"))) == 1


def test_v1_non_dispatched_recovery_does_not_fence_unrelated_targets(tmp_path):
    journal = legacy_journal(tmp_path, "prepared")
    journal.initialize()
    assert journal.status("d" * 32) == "not_dispatched"
    request = service_request()
    journal.reserve("e" * 32, request.action, request=request, approved_fingerprint="a" * 64)
    assert journal.status("e" * 32) == "prepared"


def test_resource_bindings_are_opaque_and_not_baseline_snapshots(lab):
    async def run():
        await unknown(lab)
        serialized = lab.journal.path.read_bytes()
        for forbidden in (b"fixture.service", b"configuration_fingerprint", b"invocation"):
            assert forbidden not in serialized
        with lab.journal.connection() as db:
            row = dict(db.execute("SELECT * FROM trials").fetchone())
            assert len(row["resource_digest"]) == 64
            assert len(row["approved_fingerprint"]) == 64
        assert "resource_digest" not in json.dumps(lab.journal.events("d" * 32))

    asyncio.run(run())


def test_two_reconcilers_cannot_both_release_the_same_fence(lab):
    async def run():
        request, before = await unknown(lab)
        other = FixtureTrialRunner(
            FixtureJournal(lab.journal.directory),
            lab.runner.grants,
            lab.service_adapter,
            lab.container_adapter,
        )
        barrier = asyncio.Event()
        count = [0]

        async def read(_):
            count[0] += 1
            if count[0] <= 2:
                if count[0] == 2:
                    barrier.set()
                await barrier.wait()
            return dict(lab.service)

        lab.service_adapter.read = read
        results = await asyncio.gather(
            lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None),
            other.reconcile_fixture("d" * 32, request, before, lambda: None),
            return_exceptions=True,
        )
        assert sum(isinstance(result, JournalError) for result in results) == 1
        assert sum(getattr(result, "status", None) == "reconciled" for result in results) == 1
        assert len(lab.journal.events("d" * 32)) == 4
        assert len(lab.sent) == 1

    asyncio.run(run())


def test_resource_reservation_is_atomic_across_threads(lab):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)
    request = service_request()
    approved = expected(lab, request)

    def reserve(identifier):
        barrier.wait(timeout=2)
        try:
            lab.journal.reserve(
                identifier, request.action, request=request, approved_fingerprint=approved
            )
            return True
        except JournalError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, ["a" * 32, "b" * 32]))
    assert sum(results) == 1
    with lab.journal.connection() as db:
        assert db.execute("SELECT count(*) FROM trials").fetchone()[0] == 1


def test_migration_failure_keeps_v1_schema_and_private_backup(tmp_path):
    journal = legacy_journal(tmp_path, "dispatching")
    with journal.connection() as db:
        db.execute("CREATE TABLE metadata(unexpected TEXT)")
    with pytest.raises(JournalError):
        journal.initialize()
    with journal.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert "resource_digest" not in [row[1] for row in db.execute("PRAGMA table_info(trials)")]
        assert db.execute("SELECT status FROM trials").fetchone()[0] == "dispatching"
    assert len(list(journal.directory.glob("backup-trials-v1-*.sqlite3"))) == 1


@pytest.mark.parametrize(
    "kind,verb,engine",
    [
        ("service", "start", None),
        ("service", "stop", None),
        ("container", "start", "docker"),
        ("container", "restart", "podman"),
    ],
)
def test_reconciliation_respects_each_action_postcondition(lab, kind, verb, engine):
    async def run():
        if kind == "service" and verb == "start":
            lab.service.update(active="inactive", substate="dead", pid=0, invocation=None)
        if kind == "container":
            lab.container["engine"] = engine
            if verb == "start":
                lab.container.update(status="created", running=False, started_at=None)
        request, before = await unknown(lab, kind, verb)
        result = await lab.runner.reconcile_fixture("d" * 32, request, before, lambda: None)
        assert result.status == "reconciled"
        assert len(lab.sent) == 1

    asyncio.run(run())
