"""An action's --timeout budget that setup waits (browser cold start) can pause."""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Iterator, Optional


class Clock:
    """Seconds left for one action; paused time is added back on resume."""

    def __init__(self, budget: float) -> None:
        self._lock = threading.Lock()
        self._deadline = time.monotonic() + budget
        self._paused_at: Optional[float] = None
        self._depth = 0

    def remaining(self) -> float:
        with self._lock:
            return self._deadline - (self._paused_at or time.monotonic())

    def paused(self) -> bool:
        with self._lock:
            return self._depth > 0

    def pause(self) -> None:
        with self._lock:
            if self._depth == 0:
                self._paused_at = time.monotonic()
            self._depth += 1

    def resume(self) -> None:
        with self._lock:
            self._depth -= 1
            if self._depth == 0 and self._paused_at is not None:
                self._deadline += time.monotonic() - self._paused_at
                self._paused_at = None


_current = threading.local()


def bind(clock: Clock) -> None:
    """Make `clock` the running action's clock in this thread."""
    _current.clock = clock


@contextlib.contextmanager
def off_the_clock() -> Iterator[None]:
    """Time spent inside does not count against the running action's --timeout."""
    clock: Optional[Clock] = getattr(_current, "clock", None)
    if clock is None:
        yield
        return
    clock.pause()
    try:
        yield
    finally:
        clock.resume()
