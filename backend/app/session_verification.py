"""Session-aware Unix verification lab, with a trusted in-process authority.

Not installed or instantiated by the web app. Session scopes are identifiers,
not evidence of human approval or a privileged inter-process control channel.
"""

import asyncio
import contextlib

from pydantic import Field

from .auth import Sessions
from .executor_protocol import ProtocolRejected
from .executor_transport import IssueFrame, VerificationServer

SESSION_SWEEP_SECONDS = 0.05


class ScopedIssueFrame(IssueFrame):
    session_scope: str = Field(pattern=r"^[a-f0-9]{64}$")


class SessionVerificationServer(VerificationServer):
    def __init__(self, path, policy, probe, *, sessions: Sessions):
        super().__init__(path, policy, probe)
        self.sessions = sessions
        self.operation_scopes: dict[str, str] = {}
        self.monitor: asyncio.Task | None = None
        self.current_scope: str | None = None

    def _valid(self, scope: str) -> bool:
        try:
            return self.sessions.valid_owner(scope) is True
        except Exception:  # noqa: BLE001 — unavailable authority is never permission
            return False

    def _check(self, scope: str | None) -> None:
        if scope is None or not self._valid(scope):
            raise ProtocolRejected("Session unavailable")

    def sweep_sessions(self) -> None:
        for identifier, scope in self.operation_scopes.items():
            if not self._valid(scope):
                self.policy.invalidate_operation(identifier)

    async def _monitor(self):
        while True:
            self.sweep_sessions()
            await asyncio.sleep(SESSION_SWEEP_SECONDS)

    async def start(self) -> None:
        await super().start()
        self.monitor = asyncio.create_task(self._monitor())

    async def _snapshot(self, request):
        # Normal dispatch is serialized by the parent server, so current_scope
        # cannot be replaced by another issue/verify while this read awaits.
        self._check(self.current_scope)
        snapshot = await super()._snapshot(request)
        self._check(self.current_scope)
        return snapshot

    async def _dispatch(self, uid: int, frame: dict) -> dict:
        self.sweep_sessions()
        scope: str | None
        if frame.get("kind") == "issue":
            scoped = ScopedIssueFrame.model_validate(frame)
            self._check(scoped.session_scope)
            self.policy.check_issue(uid, scoped.operation_id, scoped.request)
            identifier, scope = scoped.operation_id, scoped.session_scope
            self.operation_scopes[identifier] = scope
            frame = scoped.model_dump(exclude={"session_scope"})
        else:
            identifier = frame.get("operation_id", "")
            # Malformed values must not be used as unhashable mapping keys.
            scope = self.operation_scopes.get(identifier) if isinstance(identifier, str) else None
            self._check(scope)
        self.current_scope = scope
        try:
            self._check(scope)
            result = await super()._dispatch(uid, frame)
            self._check(scope)
            return result
        except BaseException:
            if scope is not None and not self._valid(scope):
                self.policy.invalidate_operation(identifier)
            raise
        finally:
            self.current_scope = None
            if identifier not in self.policy.reserved:
                self.operation_scopes.pop(identifier, None)

    async def close(self) -> None:
        if self.monitor is not None:
            self.monitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.monitor
            self.monitor = None
        await super().close()
        self.operation_scopes.clear()
