"""Per-caller request ceilings (AUR-21).

In memory, per process: a second replica doubles every ceiling, because neither
knows about the other's counter.
"""

import time
from collections import deque

from fastapi import HTTPException, Request

HOUR = 3600.0

MAX_KEYS = 10_000


class Window:
    """A sliding window: at most `limit` hits per `seconds`, per key."""

    def __init__(self, limit: int, seconds: float = HOUR) -> None:
        self.limit = limit
        self.seconds = seconds
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> float:
        """Record a hit. Returns 0.0 when allowed, else seconds until it would be.

        Only allowed requests are recorded.
        """
        now = time.monotonic()
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= MAX_KEYS:
                self._prune(now)
            hits = self._hits.setdefault(key, deque())
        cutoff = now - self.seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return max(1.0, hits[0] - cutoff)
        hits.append(now)
        return 0.0

    def _prune(self, now: float) -> None:
        """Drop expired entries, then evict the least recently seen down to the cap."""
        cutoff = now - self.seconds
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[key]
        if len(self._hits) >= MAX_KEYS:
            oldest = sorted(self._hits.items(), key=lambda kv: kv[1][-1])
            for key, _ in oldest[: MAX_KEYS // 2]:
                del self._hits[key]


def client_ip(request: Request) -> str:
    """The caller's address: the LAST X-Forwarded-For entry, not the first.

    Assumes exactly one trusted hop in front of us.
    """
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def refuse(retry_after: float) -> HTTPException:
    """429 with the header a well-behaved client already knows how to read."""
    return HTTPException(
        status_code=429,
        detail="too many requests -- try again shortly",
        headers={"Retry-After": str(int(retry_after) + 1)},
    )


class Limits:
    """The three ceilings, on app.state so each test gets its own counters."""

    def __init__(self, *, chat: int, login: int, doctor: int) -> None:
        self.chat = Window(chat)
        self.login = Window(login)
        self.doctor = Window(doctor)


def check(request: Request, which: str, key: str) -> None:
    """Raise 429 if this caller is over the named ceiling.

    Unlimited when no Limits was attached, rather than broken.
    """
    limits = getattr(request.app.state, "limits", None)
    if limits is None:
        return
    wait = getattr(limits, which).check(key)
    if wait:
        raise refuse(wait)
