import os
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from app.alerts import AlertEngine, observation
from app.preferences import Preferences, Rule
from app.storage import StorageError, Store
from app.system import timestamp
from pydantic import ValidationError


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "private")
    store.initialize()
    return store


def metrics(cpu=95, age=0):
    return {
        "collected_at": (datetime.now(UTC) - timedelta(seconds=age)).isoformat(),
        "cpu_percent": cpu,
        "memory": {"percent": 95},
        "swap": {"total": 0, "percent": 0},
        "disks": [{"mount": "/", "percent": 95, "error": None}],
    }


def test_private_schema_and_settings_survive_reopen(store):
    assert os.stat(store.directory).st_mode & 0o777 == 0o700
    assert os.stat(store.path).st_mode & 0o777 == 0o600
    prefs = Preferences(theme="light", refresh_seconds=10)
    operation = store.save(prefs)
    assert operation
    assert Store(store.directory).initialize() == prefs
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT action FROM audit_events").fetchone()[0] == "settings.update"


def test_future_schema_is_preserved(store):
    with sqlite3.connect(store.path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(StorageError, match="plus récente"):
        store.initialize()
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 99


def test_migration_backs_up_existing_database(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir(mode=0o700)
    path = directory / "cockpitor.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE old_data(value TEXT)")
    path.chmod(0o600)
    Store(directory).initialize()
    backups = list(directory.glob("backup-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0


def test_symlink_and_permissive_directory_rejected(tmp_path):
    directory = tmp_path / "public"
    directory.mkdir(mode=0o755)
    with pytest.raises(StorageError):
        Store(directory).initialize()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = tmp_path / "target"
    target.write_text("private")
    (private / "cockpitor.sqlite3").symlink_to(target)
    with pytest.raises(StorageError):
        Store(private).initialize()
    assert target.read_text() == "private"


def test_locked_database_does_not_report_settings_as_saved(store):
    original = store.preferences()
    with sqlite3.connect(store.path) as db:
        db.execute("BEGIN EXCLUSIVE")
        with pytest.raises(StorageError):
            store.save(Preferences(theme="light"))
    assert store.preferences() == original


@pytest.mark.parametrize(
    "payload",
    [
        {"theme": "invalid"},
        {"refresh_seconds": 1},
        {"retention_days": 999},
        {"listen_address": "0.0.0.0"},
        {
            "rules": [
                {"id": "same", "metric": "cpu_percent"},
                {"id": "same", "metric": "cpu_percent"},
            ]
        },
        {"rules": [{"id": "test", "metric": "service_failed", "target": "--help.service"}]},
        {
            "rules": [
                {"id": "test", "metric": "container_stopped", "target": "abc", "engine": "docker"}
            ]
        },
    ],
)
def test_preferences_reject_unsafe_or_invalid_fields(payload):
    with pytest.raises(ValidationError):
        Preferences.model_validate(payload)


def test_sustained_threshold_dedup_restart_and_resolution(store):
    prefs = Preferences(rules=[Rule(id="cpu", metric="cpu_percent", duration_seconds=10)])
    engine = AlertEngine(store)
    engine.evaluate(prefs, metrics(), None, None, None, now=0)
    assert not store.active()
    engine.evaluate(prefs, metrics(), None, None, None, now=10)
    assert len(store.active()) == 1
    engine.evaluate(prefs, metrics(), None, None, None, now=20)
    restarted = AlertEngine(store)
    restarted.evaluate(prefs, metrics(), None, None, None, now=30)
    assert store.events("all", 50, 0)["total"] == 1
    restarted.evaluate(prefs, metrics(10), None, None, None, now=32)
    assert not store.active()
    assert store.events("resolved", 50, 0)["total"] == 1


def test_same_or_stale_sample_does_not_activate_or_resolve(store):
    prefs = Preferences(rules=[Rule(id="cpu", metric="cpu_percent", duration_seconds=5)])
    engine = AlertEngine(store)
    sample = metrics()
    engine.evaluate(prefs, sample, None, None, None, now=0)
    engine.evaluate(prefs, sample, None, None, None, now=10)
    assert not store.active()
    engine.evaluate(prefs, metrics(), None, None, None, now=12)
    assert store.active()
    engine.evaluate(prefs, metrics(0, age=60), None, None, None, now=20)
    assert store.active()
    assert engine.states[0]["status"] == "unavailable"
    assert engine.states[0]["active"] is True


def test_changed_rules_resolve_but_theme_change_keeps_alert(store):
    prefs = Preferences(rules=[Rule(id="cpu", metric="cpu_percent", duration_seconds=0)])
    store.save(prefs)
    AlertEngine(store).evaluate(prefs, metrics(), None, None, None, now=1)
    assert store.active()
    store.save(prefs.model_copy(update={"theme": "light"}))
    assert store.active()
    store.save(Preferences(rules=[]))
    assert not store.active()


def test_disabled_or_unknown_sources_are_not_failures(store):
    rule = Rule(id="ollama", metric="ollama_unavailable", duration_seconds=0)
    prefs = Preferences(rules=[rule])
    engine = AlertEngine(store)
    engine.evaluate(
        prefs,
        None,
        {"collected_at": timestamp(), "ollama": {"status": "disabled"}},
        None,
        None,
        now=1,
    )
    assert not store.active() and engine.states[0]["status"] == "unavailable"
    engine.evaluate(
        prefs,
        None,
        {"collected_at": timestamp(), "ollama": {"status": "unavailable"}},
        None,
        None,
        now=2,
    )
    assert store.active()
    assert observation(Rule(id="swap", metric="swap_percent"), metrics(), None, None, None) is None


def test_disk_services_and_container_observations():
    assert (
        observation(
            Rule(id="disk", metric="disk_free_percent", target="/"), metrics(), None, None, None
        )
        == 5
    )
    services = {
        "collected_at": timestamp(),
        "status": "available",
        "items": [{"unit": "ssh.service", "active": "failed"}],
    }
    rule = Rule(id="ssh", metric="service_failed", target="ssh.service")
    assert observation(rule, None, None, services, None) == 1
    cid = "a" * 64
    containers = {
        "collected_at": timestamp(),
        "engines": [
            {
                "name": "podman",
                "status": "available",
                "containers": [{"id": cid, "state": "exited"}],
            }
        ],
    }
    rule = Rule(id="container", metric="container_stopped", target=cid, engine="podman")
    assert observation(rule, None, None, None, containers) == 1


def test_retention_keeps_active_events(store):
    active = store.activate("active", "warning", "test")
    resolved = store.activate("resolved", "warning", "test")
    store.resolve(resolved)
    with sqlite3.connect(store.path) as db:
        db.execute(
            "UPDATE alert_events SET created_epoch=0, resolved_at=CASE WHEN status='resolved' THEN '1970-01-01T00:00:00+00:00' ELSE NULL END"
        )
    store.cleanup(1)
    assert store.events("all", 50, 0)["total"] == 1
    assert store.active() == {"active": active}


def test_missing_runtime_database_is_not_recreated_on_read(store):
    store.path.unlink()
    with pytest.raises(StorageError):
        store.preferences()
    assert not store.path.exists()


def test_disabled_rule_does_not_trigger(store):
    prefs = Preferences(
        rules=[Rule(id="cpu", metric="cpu_percent", enabled=False, duration_seconds=0)]
    )
    engine = AlertEngine(store)
    engine.evaluate(prefs, metrics(), None, None, None, now=1)
    assert not store.active() and engine.states[0]["status"] == "disabled"
