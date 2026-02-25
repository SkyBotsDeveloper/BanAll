"""Security and throttling helpers for privileged commands."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class PendingOperation:
    token: str
    operation: str
    chat_id: int
    requester_id: int
    created_at: float
    preview_target_count: int


class ConfirmationManager:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._tokens: Dict[str, PendingOperation] = {}

    def create(
        self,
        *,
        operation: str,
        chat_id: int,
        requester_id: int,
        preview_target_count: int,
    ) -> PendingOperation:
        self.cleanup()

        token = secrets.token_hex(4)
        pending = PendingOperation(
            token=token,
            operation=operation,
            chat_id=chat_id,
            requester_id=requester_id,
            created_at=time.time(),
            preview_target_count=preview_target_count,
        )
        self._tokens[token] = pending
        return pending

    def consume(self, token: str, *, chat_id: int, requester_id: int) -> PendingOperation | None:
        self.cleanup()

        pending = self._tokens.get(token)
        if pending is None:
            return None

        if pending.chat_id != chat_id or pending.requester_id != requester_id:
            return None

        self._tokens.pop(token, None)
        return pending

    def cleanup(self) -> None:
        if not self._tokens:
            return

        now = time.time()
        expired = [
            token
            for token, pending in self._tokens.items()
            if now - pending.created_at > self.ttl_seconds
        ]
        for token in expired:
            self._tokens.pop(token, None)


class CooldownLimiter:
    """Simple fixed-window limiter keyed by arbitrary strings."""

    def __init__(self, cooldown_seconds: float) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._last_seen: Dict[str, float] = {}

    def allow(self, key: str) -> tuple[bool, float]:
        now = time.time()
        last = self._last_seen.get(key)
        if last is not None:
            remaining = self.cooldown_seconds - (now - last)
            if remaining > 0:
                return False, remaining

        self._last_seen[key] = now
        return True, 0.0

    def cleanup(self, max_age_multiplier: float = 3.0) -> None:
        if not self._last_seen:
            return

        now = time.time()
        max_age = self.cooldown_seconds * max_age_multiplier
        stale = [key for key, ts in self._last_seen.items() if now - ts > max_age]
        for key in stale:
            self._last_seen.pop(key, None)
