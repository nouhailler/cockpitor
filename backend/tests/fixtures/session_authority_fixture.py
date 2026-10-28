"""Separate authority process for tests; stdin control is not a product protocol."""

import asyncio
import json
import os
import sys
from pathlib import Path

from app.auth import Sessions
from app.session_authority import SessionAuthorityServer


async def main():
    now = [0.0]
    sessions = Sessions("fixture-only", clock=lambda: now[0])
    first, _ = sessions.login("fixture-only")
    second, _ = sessions.login("fixture-only")
    server = SessionAuthorityServer(Path(sys.argv[1]), client_uid=os.getuid(), sessions=sessions)
    await server.start()
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "first_scope": sessions.digest(first),
                "second_scope": sessions.digest(second),
            }
        ),
        flush=True,
    )
    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            control = json.loads(line)
            if control["command"] == "stop":
                break
            if control["command"] == "revoke_first":
                sessions.revoke(first)
            elif control["command"] == "advance":
                now[0] += control["seconds"]
            else:
                raise ValueError("Unknown fixture control")
            print(json.dumps({"ok": True}), flush=True)
    finally:
        await server.close()


asyncio.run(main())
