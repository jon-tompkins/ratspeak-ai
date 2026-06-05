from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class RateDecision:
    allowed: bool
    reason: str = ""
    retry_after_seconds: int = 0


class RateLimiter:
    """Sliding-window per-peer message limiter plus daily-token quota lookup.

    Token quota is enforced against a `Memory`-style usage tracker passed in at decision time;
    this class only holds the message-rate state in memory.
    """

    def __init__(self, messages_per_window: int, window_seconds: int, daily_token_quota: int):
        self._cap = messages_per_window
        self._window = window_seconds
        self._daily_quota = daily_token_quota
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, peer_hash: str, tokens_today: int, *, quota_override: int | None = None) -> RateDecision:
        now = time.monotonic()
        bucket = self._hits[peer_hash]
        cutoff = now - self._window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if self._cap and len(bucket) >= self._cap:
            retry = int(bucket[0] + self._window - now) + 1
            return RateDecision(
                allowed=False,
                reason=f"rate limit: {self._cap} msgs / {self._window}s. Try again in ~{retry}s.",
                retry_after_seconds=retry,
            )

        effective_quota = quota_override if quota_override else self._daily_quota
        if effective_quota and tokens_today >= effective_quota:
            return RateDecision(
                allowed=False,
                reason=(
                    f"daily token quota reached ({tokens_today}/{effective_quota}). "
                    "Resets at 00:00 UTC."
                ),
            )

        bucket.append(now)
        return RateDecision(allowed=True)
