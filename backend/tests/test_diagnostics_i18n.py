import json

import pytest
from app.diagnostics import build_report
from app.i18n import CATALOGS, select_language
from app.storage import Store
from app.system import timestamp

# Reuse the isolated API fixture, without depending on any live engine or database.
from test_api import wait_settings

pytest_plugins = ["test_api"]


def test_diagnostic_allowlist_excludes_nested_secrets_and_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALCOCKPIT_TOKEN", "PRIVATE_TOKEN")
    store = Store(tmp_path / "state")
    store.initialize()
    store.activate("SECRET_RULE", "warning", "PRIVATE_MESSAGE")
    metrics = {
        "collected_at": timestamp(),
        "hostname": "PRIVATE_HOST",
        "processes": [{"name": "PRIVATE_PROCESS"}],
        "os": "PRIVATE_OS",
        "cpu_percent": 12.5,
        "uptime_seconds": 100,
        "memory": {"total": 1024, "used": 512, "password": "PRIVATE_PASSWORD"},
        "swap": {},
        "network": {"received_bps": 100, "address": "PRIVATE_IP"},
        "disks": [
            {
                "mount": "/private/path",
                "device": "PRIVATE_DEVICE",
                "total": 100,
                "used": 50,
                "percent": 50,
            }
        ],
    }
    ai = {
        "ollama": {
            "status": "available",
            "models": [{"name": "PRIVATE_MODEL"}],
            "url": "http://PRIVATE_URL",
        },
        "openwebui": {"status": "available", "token": "PRIVATE_TOKEN"},
    }
    services = {
        "status": "available",
        "items": [
            {"unit": "PRIVATE_SERVICE", "active": "failed", "description": "PRIVATE_DESCRIPTION"}
        ],
    }
    containers = {
        "engines": [
            {
                "name": "docker",
                "status": "available",
                "containers": [
                    {
                        "id": "PRIVATE_ID",
                        "name": "PRIVATE_CONTAINER",
                        "state": "running",
                        "Env": ["PRIVATE_ENV"],
                    }
                ],
            }
        ]
    }
    report = build_report(metrics, ai, services, containers, store, True)
    text = json.dumps(report)
    assert "PRIVATE_" not in text and "SECRET_RULE" not in text
    assert "/private/path" not in text
    assert report["system"]["cpu_percent"] == 12.5
    assert report["ai"]["ollama"]["models_count"] == 1
    assert report["services"]["counts"]["failed"] == 1
    assert report["audit_recorded"] is True
    assert len(text) < 65536
    assert store.diagnostic_summary()["alerts"]["active"] == 1


def test_diagnostic_works_without_storage_or_sources(tmp_path):
    report = build_report(None, None, None, None, Store(tmp_path / "absent"), False)
    assert report["system"]["status"] == "unavailable"
    assert report["audit_recorded"] is False
    assert report["storage"]["status"] == "unavailable"


def test_old_preferences_gain_french_default(tmp_path):
    store = Store(tmp_path / "state")
    store.initialize()
    with store.connection() as db:
        value = json.loads(db.execute("SELECT value FROM settings").fetchone()[0])
        value.pop("language")
        db.execute("UPDATE settings SET value=?", (json.dumps(value),))
    assert store.preferences().language == "fr"
    assert Store(store.directory).initialize().language == "fr"


@pytest.mark.parametrize(
    "header,expected",
    [
        ("en-US,en;q=0.8", "en"),
        ("en;q=0,fr;q=.5", "fr"),
        ("fr;q=.2,en;q=.9", "en"),
        ("de-DE", "fr"),
        ("en;q=invalid", "fr"),
    ],
)
def test_language_negotiation(header, expected):
    assert select_language(header) == expected


def test_catalogs_have_identical_nonempty_keys_and_placeholders():
    import re

    assert set(CATALOGS["fr"]) == set(CATALOGS["en"])
    for key, value in CATALOGS["en"].items():
        assert value.strip()
        assert sorted(re.findall(r"\{\d+\}", key)) == sorted(re.findall(r"\{\d+\}", value)), key


def test_english_api_errors_keep_stable_codes(client):
    response = client.get(
        "/api/v1/health", headers={"authorization": "", "accept-language": "en-GB"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.json()["error"]["message"] == "Local token required"
    assert response.headers["content-language"] == "en"
    response = client.get("/api/v1/health", headers={"authorization": "", "accept-language": "fr"})
    assert response.json()["error"]["message"] == "Jeton local requis"


def test_diagnostic_requires_auth_origin_csrf_confirmation_and_rate_limit(client):
    wait_settings(client)
    options = client.get("/api/v1/diagnostics/options").json()
    headers = {"origin": "http://127.0.0.1:8765", "x-localcockpit-csrf": options["csrf_token"]}
    path = "/api/v1/diagnostics"
    assert client.post(path, json={"confirmed": True}).status_code == 403
    assert (
        client.post(
            path, json={"confirmed": True}, headers={**headers, "authorization": ""}
        ).status_code
        == 401
    )
    assert (
        client.post(
            path, json={"confirmed": True}, headers={**headers, "origin": "http://evil.example"}
        ).status_code
        == 403
    )
    assert client.post(path, json={"confirmed": False}, headers=headers).status_code == 422
    assert client.post(path, json={"confirmed": 1}, headers=headers).status_code == 422
    assert (
        client.post(
            path, json={"confirmed": True, "path": "/etc/passwd"}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            path, content="x" * 1025, headers={**headers, "content-type": "application/json"}
        ).status_code
        == 413
    )
    assert client.get(path).status_code in {404, 405}
    response = client.post(path, json={"confirmed": True}, headers=headers)
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.json()["operation_id"] and response.json()["audit_recorded"]
    assert "csrf_token" not in response.text
    assert client.post(path, json={"confirmed": True}, headers=headers).status_code == 429
    assert client.post("/api/v1/actions/restart").status_code == 405


def test_language_is_persisted_and_unsupported_languages_refused(client):
    data = wait_settings(client)
    headers = {"origin": "http://127.0.0.1:8765", "x-localcockpit-csrf": data["csrf_token"]}
    settings = {**data["settings"], "language": "en"}
    assert client.put("/api/v1/settings", json=settings, headers=headers).status_code == 200
    assert client.get("/api/v1/settings").json()["settings"]["language"] == "en"
    assert (
        client.put(
            "/api/v1/settings", json={**settings, "language": "de"}, headers=headers
        ).status_code
        == 422
    )
