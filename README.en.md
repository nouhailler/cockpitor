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

379 backend tests and 26 frontend tests pass locally, alongside type checks,
formatting and production build. Real Docker/Podman qualification and a clean
Debian installation test remain pending. Expiring sessions, attempt limits, monitoring probes and a local Ollama advisor are
implemented; sensitive system actions remain disabled.

See the [French README](README.md) for integration configuration, test commands
and documentation links, plus [CONTEXT](CONTEXT.md) and [CHANGELOG](CHANGELOG.md).

![Confirmed diagnostic export](docs/images/diagnostics-en.jpg)

## ◴ Monitoring, sessions and local AI

The launcher token opens an in-memory session: 15 minutes without user interaction,
eight hours maximum, revoked on sign-out or server restart. Automatic polling does
not extend inactivity. Ten sign-in attempts per minute and 32 concurrent sessions.

Monitoring adds CPU/RAM history (one sample/minute, seven days), installed services,
disk topology and SMART, NVIDIA GPU probes, local NUT UPS readings, time, existing
APT cache, interfaces/DNS/IPv4 routes and IPv4/IPv6 listeners. Tools and permission
errors remain explicit. No software or drivers are installed. A listener does not
prove Internet exposure; package-cache data can be outdated.

The AI assistant uses an already installed Ollama model, without tools or execution.
Preview and explicitly include a timestamped CPU/RAM/swap context if desired.
Saving is optional and off by default: 20 conversations, 40 messages each. Up to
eight previous messages are sent as conversation context. Secret masking is partial;
never enter secrets. Saved conversations belong to the single local application user.
SQLite v3 migration creates a private backup. Audit history is available in the UI.

![Local AI assistant](docs/images/assistant-en.jpg)

## ◇ Controlled actions — simulation only

Prepare a plan for an exact target, review its state, approve it, then run a simulation.
Plans last 120 seconds; single-use approvals last up to 60 seconds and are bound to
the session, plan and target/configuration fingerprints. Stale inventory, changed
targets, replay, expired sessions or audit failure block the workflow.

No resource is started, stopped or restarted. There is no system executor or privileged
helper and no switch to enable one. Simulation testing does not qualify real execution.
Pending operations are interrupted after restart; approval tokens are never persisted.
See [the safeguards and remaining activation gate](docs/ACTIONS_SECURITY.md).

![Approved simulation](docs/images/actions-en.jpg)

## 🔌 L5 preparation — verification transport

An isolated Unix lab checks kernel-provided client UIDs, exact target grants and
expiring single-use tickets. Private sockets, bounded frames, deadlines, concurrent
requests and shutdown are covered by local tests. The client is linked to the
approval/audit lifecycle in this lab and requires the approved fingerprint on both
reads. It cannot execute system actions and is not enabled in the regular launcher.
System adapters and disposable-VM qualification remain pending. See [the contract and remaining tests (French)](docs/EXECUTOR_QUALIFICATION.md).

[Fixture adapters and postconditions (French)](docs/ADAPTER_TRIALS.md) now exercise
private test resources with fixed commands/requests, state confirmation and a
durable journal for unknown outcomes. Real system drivers and disposable-VM
qualification remain pending; sensitive actions are still disabled.

[Read-only fixture reconciliation (French)](docs/FIXTURE_RECONCILIATION.md) can now
confirm a fixture's state after interruption. Unknown outcomes block new trials
on the same target across restarts; reconciliation never resends an operation.
