"""Memory-only, hashed, revocable sessions. Bootstrap token never authorizes data reads."""

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass

IDLE_SECONDS = 15 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60
MAX_SESSIONS = 32


@dataclass
class Session:
    created: float
    touched: float


class Sessions:
    def __init__(self, bootstrap: str, clock=time.monotonic):
        self.bootstrap = bootstrap
        self.clock = clock
        self.sessions: dict[str, Session] = {}
        self.attempts: deque[float] = deque()
        self.lock = threading.Lock()

    @staticmethod
    def digest(token: str):
        return hashlib.sha256(token.encode()).hexdigest()

    def prune(self, now):
        self.sessions = {
            key: value
            for key, value in self.sessions.items()
            if now - value.created < ABSOLUTE_SECONDS and now - value.touched < IDLE_SECONDS
        }

    def login(self, candidate: str):
        with self.lock:
            now = self.clock()
            while self.attempts and now - self.attempts[0] >= 60:
                self.attempts.popleft()
            if len(self.attempts) >= 10:
                return None, "AUTH_RATE_LIMIT"
            self.attempts.append(now)
            if not hmac.compare_digest(candidate.encode(), self.bootstrap.encode()):
                return None, "AUTH_REQUIRED"
            self.prune(now)
            if len(self.sessions) >= MAX_SESSIONS:
                return None, "SESSION_LIMIT"
            token = secrets.token_urlsafe(32)
            self.sessions[self.digest(token)] = Session(now, now)
            return token, None

    def authorize(self, token: str, *, touch=False):
        if not token or len(token) > 256:
            return False
        with self.lock:
            now = self.clock()
            self.prune(now)
            session = self.sessions.get(self.digest(token))
            if session is None:
                return False
            if touch:
                session.touched = now
            return True

    def revoke(self, token: str):
        with self.lock:
            self.sessions.pop(self.digest(token), None)
