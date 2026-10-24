"""Shared owned-browser environment and cross-process action locks."""

import hashlib
import sys
import time
from contextlib import ExitStack, contextmanager
from typing import Iterator, List, Optional

from .result import NEED_SETUP, ReachError

#: Reads of one site that may run at once in the shared browser (same account; keeps risk control calm).
SITE_SLOTS = 2
#: Browser queries of all sites that may run at once.
BROWSER_SLOTS = 4
#: Seconds a query waits in line for a free slot before reporting BUSY.
QUEUE_WAIT = 120.0
_POLL = 0.2


def profile_for(channel: str):
    """All browser channels use the same Reach-owned destination profile."""
    return "dedicated"






def setup_problems(channel: str):
    return []  # add/first use prepare and reopen the owned browser automatically


def environment(channel: str):
    from . import browser, session_reuse
    session_reuse.prepare(channel)
    profile = browser.bound_context()
    if not profile:
        raise ReachError(NEED_SETUP, "OpenCLI has not connected to the dedicated browser")
    from . import bridge
    if not bridge.require_compatible():
        raise ReachError(NEED_SETUP, "The dedicated browser Bridge disconnected; reopen the Reach browser")
    browser.touch()
    return {"OPENCLI_PROFILE": profile, "OPENCLI_WINDOW": "background",
            "OPENCLI_CDP_ENDPOINT": "", "OPENCLI_CDP_TARGET": ""}


# One OS file lock per name: nonblocking `execution_lock`, or `wait_lock` that
# polls until a deadline. Slots are N such locks; no daemon or stale-lock cleanup.


@contextmanager
def execution_lock(profile: str):
    from agent_reach.utils.paths import ensure_no_symlink_path, make_private_dir

    from . import state

    folder = state.root() / "browser-locks"
    make_private_dir(folder)
    path = folder / (hashlib.sha256(profile.encode()).hexdigest() + ".lock")
    ensure_no_symlink_path(path, "browser lock")
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ReachError("BUSY", "Another Reach command is using this Chrome profile") from None
        try:
            if profile != "reach-state-write":
                state.remember_path(path, "execution lock")
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _try_any(names: List[str]) -> Optional[ExitStack]:
    """Hold the first free lock among `names`, or None if all are taken."""
    for name in names:
        stack = ExitStack()
        try:
            stack.enter_context(execution_lock(name))
            return stack
        except ReachError as exc:
            stack.close()
            if exc.code != "BUSY":
                raise
    return None


def _wait_any(names: List[str], wait: float, message: str) -> ExitStack:
    deadline = time.monotonic() + max(0.0, wait)
    while True:
        held = _try_any(names)
        if held is not None:
            return held
        if time.monotonic() >= deadline:
            raise ReachError("BUSY", message, hint=(
                "The shared browser stayed full while this command waited in line; retry in a minute. "
                "Do not switch accounts or browsers."))
        time.sleep(_POLL)


@contextmanager
def wait_lock(name: str, wait: Optional[float] = None) -> Iterator[None]:
    """Exclusive lock on `name`, waiting up to `wait` seconds (default QUEUE_WAIT)."""
    with _wait_any([name], QUEUE_WAIT if wait is None else wait, f"Waited too long for {name}"):
        yield


def _browser_slots() -> List[str]:
    return [f"browser:slot:{i}" for i in range(BROWSER_SLOTS)]


@contextmanager
def query_slot(site: str, clock=None) -> Iterator[None]:
    """A place in line for one browser query: at most SITE_SLOTS per site, BROWSER_SLOTS overall.

    Time spent waiting in line does not count against `clock` (the action's --timeout).
    """
    with ExitStack() as stack:
        if clock is not None:
            clock.pause()
        try:
            stack.enter_context(_wait_any([f"site:{site}:{i}" for i in range(SITE_SLOTS)], QUEUE_WAIT,
                                          f"{site} already has {SITE_SLOTS} queries running in the shared browser"))
            stack.enter_context(_wait_any(_browser_slots(), QUEUE_WAIT, "The shared browser is full"))
        finally:
            if clock is not None:
                clock.resume()
        yield


@contextmanager
def exclusive_browser() -> Iterator[None]:
    """Wait for running queries to finish and hold off new ones (login window, restart, clearing a site)."""
    with ExitStack() as stack:
        deadline = time.monotonic() + QUEUE_WAIT
        for name in _browser_slots():
            stack.enter_context(_wait_any([name], deadline - time.monotonic(),
                                          "Browser queries are still running; try again shortly"))
        yield
