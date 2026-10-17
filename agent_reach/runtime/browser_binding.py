"""Explicit per-channel browser selection; configuration contains IDs, never cookies."""

import hashlib
import os
import sys
from contextlib import contextmanager

from agent_reach.config import Config

from .result import BAD_INPUT, NEED_SETUP, ReachError

KEY = "browser_profiles"


def profile_for(channel: str):
    value = os.environ.get("AGENT_REACH_OPENCLI_PROFILE")
    if value is None:
        profiles = Config(read_only=True).get(KEY, {})
        if not isinstance(profiles, dict):
            raise ReachError(BAD_INPUT, "browser_profiles must be an object")
        value = profiles.get(channel, Config(read_only=True).get("browser_default_profile"))
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ReachError(BAD_INPUT, "browser profile must be a non-empty context ID")
    return value.strip() if value is not None else None


def bind_profile(channel: str, profile: str):
    if not profile.strip():
        raise ReachError(BAD_INPUT, "empty browser profile")
    config = Config()
    profiles = dict(config.get(KEY, {}))
    profiles[channel] = profile.strip()
    config.set(KEY, profiles)
    from . import state

    data = state.load()
    data["checks"].pop(channel, None)
    state.save(data)
    return {
        "channel": channel,
        "profile": profile.strip(),
        "verified": False,
        "next": f"agent-reach check {channel} --search",
    }


def unbind_profile(channel: str):
    config = Config()
    profiles = dict(config.get(KEY, {}))
    removed = profiles.pop(channel, None) is not None
    config.set(KEY, profiles)
    from . import state

    data = state.load()
    data["checks"].pop(channel, None)
    state.save(data)
    return {"channel": channel, "unbound": removed, "browser_cookies_changed": False}


def setup_problems(channel: str):
    return (
        []
        if profile_for(channel)
        else [
            f"Bind an existing Chrome profile: agent-reach browser bind {channel} CONTEXT_ID (list with agent-reach browser profiles; select once with agent-reach browser use CONTEXT_ID)"
        ]
    )


def environment(channel: str):
    profile = profile_for(channel)
    if not profile:
        raise ReachError(NEED_SETUP, setup_problems(channel)[0])
    if profile == "dedicated":
        # Explicit legacy opt-in, never a fallback for a disconnected user profile.
        from . import browser

        context = browser.bound_context()
        if not context or not browser.is_running():
            raise ReachError(
                NEED_SETUP,
                "Dedicated browser is not ready; run agent-reach browser setup explicitly",
            )
        profile = context
        browser.touch()
    return {
        "OPENCLI_PROFILE": profile,
        "OPENCLI_WINDOW": "background",
        "OPENCLI_CDP_ENDPOINT": "",
        "OPENCLI_CDP_TARGET": "",
    }


# ponytail: one nonblocking OS file lock per profile; callers retry BUSY later.
# No daemon, queue, stale-lock cleanup, or guessed browser ownership.


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
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
