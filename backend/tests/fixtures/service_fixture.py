"""Private JSON fixture process. Does not import or invoke systemctl."""

import json
import sys
from pathlib import Path

state_file = Path(sys.argv[1])
verb = sys.argv[2]
state = json.loads(state_file.read_text())
if verb == "read":
    print(json.dumps(state))
elif verb in {"start", "stop", "restart"}:
    active = verb != "stop"
    state.update(
        active="active" if active else "inactive",
        substate="running" if active else "dead",
        pid=123 if active else 0,
        invocation="b" * 32 if active else None,
    )
    state_file.write_text(json.dumps(state))
else:
    raise SystemExit(2)
