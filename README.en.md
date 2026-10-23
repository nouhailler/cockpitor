# ◈ Cockpitor

[🇫🇷 Français](README.md) · 🇬🇧 English

Your Linux machine, at a glance. A local React/TypeScript and FastAPI dashboard
for Debian. Prototype 0.1.0; Debian packaging remains pending.

![English dashboard](docs/images/dashboard-en.jpg)

## ✨ Features

- 📊 CPU, RAM, swap, disks, network, processes and in-memory history.
- ⚙️ Loaded systemd services and bounded logs.
- 🧠 Ollama models and optional OpenWebUI HTTP status.
- 📦 Optional Docker/Podman inventory, details, statistics and bounded logs.
- ⚑ Persistent local alert rules, events, retention and preferences in private SQLite.
- 🌍 French/English interface, regional dates/numbers and persistent language.
- ⇩ Confirmed, redacted JSON diagnostics using an explicit field allowlist.

## 🚀 Quick start

Requires Linux, Python 3.11+, Node.js 22.12+, npm and Git.

```bash
git clone https://github.com/nouhailler/cockpitor.git
cd cockpitor
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/python scripts/serve.py
```

Open [the local cockpit](http://127.0.0.1:8765), enter the token printed by the
launcher, then choose English. Save Language in Settings to restore it after login.
The sidebar picker changes the current session immediately. External names and logs
retain their original text. Stop the launcher with Ctrl+C; do not run as root.

## 🔒 Boundaries

Loopback only, bearer authentication, exact origin checks and CSRF for settings
and diagnostic exports. No service stops, container restarts, shell or privileged
agent. Engine sockets require explicit configuration and existing permissions;
Docker socket access itself grants root-equivalent powers.

The diagnostic export excludes names, IDs, paths, addresses, logs, environment
variables and tokens. It is limited to 64 KiB, uses existing snapshots and never
sends data to an external service. Review aggregate machine data before sharing.
If SQLite is unavailable, export still works and reports missing audit storage.

## 🧪 Validation and documentation

109 backend tests and 18 frontend tests pass locally, alongside type checks,
formatting and production build. Real Docker/Podman qualification and a clean
Debian installation test remain pending. Authentication sessions with expiration
and attempt limits are the next step; sensitive system actions remain disabled.

See the [French README](README.md) for integration configuration, test commands
and documentation links, plus [CONTEXT](CONTEXT.md) and [CHANGELOG](CHANGELOG.md).

![Confirmed diagnostic export](docs/images/diagnostics-en.jpg)
