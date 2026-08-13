# -*- coding: utf-8 -*-
"""
Channel base class — platform availability checking.

Each channel represents a platform (YouTube, Twitter, GitHub, etc.)
and provides:
  - can_handle(url) → does this URL belong to this platform?
  - check(config) → is the upstream tool installed and configured?

After installation, agents call upstream tools directly.

Backend routing semantics:
  - `backends` is an ORDERED candidate list: backends[0] is the preferred
    backend, the rest are fallbacks. "Switching backends" for a platform
    means reordering this list (or a user override) — not rewriting code.
  - check() must set `self.active_backend` to the backend that is actually
    serving the channel right now (None when nothing usable is found).
    shutil.which() alone is NOT proof of health — a stale venv shim passes
    which() but cannot execute (see agent_reach.probe). Channels should
    really execute a lightweight command before claiming a backend active.
  - Users can force a backend with config key `<channel>_backend`
    (or env var `<CHANNEL>_BACKEND`); ordered_backends() applies it.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple


class Channel(ABC):
    """Base class for all channels."""

    name: str = ""                    # e.g. "youtube"
    description: str = ""             # e.g. "YouTube 视频和字幕"
    backends: List[str] = []          # ordered candidates — backends[0] = preferred
    tier: int = 0                     # 0=zero-config, 1=needs free key, 2=needs setup

    #: Backend currently serving this channel; set by check(), None = unavailable.
    active_backend: Optional[str] = None

    #: Skill reference doc covering this platform, e.g. "social" →
    #: agent_reach/skill/references/social.md. Used by `agent-reach route`.
    reference: str = ""

    #: backend name → command template for reading ONE URL, `{url}` substituted.
    #: Only backends whose upstream CLI documents accepting a URL/ID belong
    #: here: `route` prints these verbatim for an agent to run, so an invented
    #: flag would be worse than no entry at all. Backends absent from this map
    #: still route correctly — the agent is sent to the reference doc instead.
    url_commands: Dict[str, str] = {}

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this channel can handle this URL."""
        ...

    def ordered_backends(self, config=None) -> List[str]:
        """Candidate backends in probe order, honoring the user override.

        The config key `<channel>_backend` (env `<CHANNEL>_BACKEND`) moves the
        named backend to the front of the list; unknown values are ignored so
        a stale override can never hide working backends.
        """
        candidates = list(self.backends)
        override = config.get(f"{self.name}_backend") if config else None
        if override:
            for i, b in enumerate(candidates):
                if b == override or b.startswith(override):
                    candidates.insert(0, candidates.pop(i))
                    break
        return candidates

    def commands_for_url(self, url: str, config=None) -> List[Tuple[str, str]]:
        """(backend, command) pairs for reading `url`, in probe order.

        Backends without a documented URL-accepting command are skipped, so an
        empty list means "read the reference doc", never "this URL is
        unsupported".
        """
        return [
            (backend, self.url_commands[backend].replace("{url}", url))
            for backend in self.ordered_backends(config)
            if backend in self.url_commands
        ]

    def check(self, config=None) -> Tuple[str, str]:
        """
        Check if this channel's upstream tool is available.
        Returns (status, message) where status is 'ok'/'warn'/'off'/'error'.

        Subclasses with external backends must really probe them (see
        agent_reach.probe.probe_command) and set self.active_backend.
        """
        self.active_backend = self.backends[0] if self.backends else "内置"
        return "ok", f"{'、'.join(self.backends) if self.backends else '内置'}"
