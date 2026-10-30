# -*- coding: utf-8 -*-
"""
Channel base class.

Each channel represents a platform (YouTube, GitHub, V2EX, ...) and declares:
  - can_handle(url) → does this URL belong to this platform? (used by `read`)
  - level → "default" / "optional" / "experimental"
  - actions → unified actions (`agent-reach <channel> <action>`), each with an
    ordered list of (backend label, method name); the dispatcher tries them in
    order and falls back on retryable errors.
  - tools / prereqs / session / login_* → what `add`, `login` and `doctor` need.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Param:
    """One argument of a unified action."""

    name: str
    help: str
    required: bool = True
    type: type = str
    default: object = None


@dataclass(frozen=True)
class Action:
    """A unified action (`agent-reach <channel> <action>`).

    `backends` is ordered: (backend label, channel method name). The
    dispatcher tries them in order and falls back on retryable errors.
    `live_test` holds params for `agent-reach check`; a backend passes when
    the call succeeds and returns at least one item.
    """

    name: str
    help: str
    params: Tuple[Param, ...]
    backends: Tuple[Tuple[str, str], ...]
    live_test: Optional[Dict[str, object]] = None
    #: Default timeout in seconds for slow actions (e.g. transcription); None = global default.
    timeout: Optional[float] = None
    #: Public URL scopes tried through the existing Web channel before site tools.
    #: Search results/page text are labelled separately from authenticated site data.
    public_web: Tuple[str, ...] = ()


class Channel(ABC):
    """Base class for all channels."""

    name: str = ""                    # e.g. "youtube"
    description: str = ""             # e.g. "YouTube 视频和字幕"

    #: "default" / "optional" / "experimental".
    level: str = ""
    #: Unified actions this channel exposes.
    actions: Tuple[Action, ...] = ()
    #: Tool whose login lives in ~/.agent-reach/sessions/<session>/ ("" = none).
    session: str = ""
    #: Interactive command the user runs to log in (run with HOME = session dir).
    login_argv: Tuple[str, ...] = ()
    #: Directories under the real home where the tool used to keep its login,
    #: copied into the session only when the user asks (`login --import-existing`).
    legacy_state: Tuple[str, ...] = ()
    #: Page the user logs in on, opened in the Agent Reach browser by `agent-reach login`.
    #: A login_url makes the channel need Chrome (installed by `add` when missing).
    login_url: str = ""
    #: Cookie domains `agent-reach remove` clears in the Agent Reach browser
    #: (empty = the login_url host without "www.").
    domains: Tuple[str, ...] = ()
    #: Upstream tools (keys of runtime.tools.TOOLS) `agent-reach add` installs.
    tools: Tuple[str, ...] = ()
    #: Machine prerequisites (node, uv, ffmpeg, chrome; keys of runtime.tools.TOOLS)
    #: that `agent-reach add` installs when the machine has none.
    prereqs: Tuple[str, ...] = ()
    #: Config keys `agent-reach logout` clears.
    logout_keys: Tuple[str, ...] = ()
    #: `agent-reach configure` key the user must provide before the channel works ("" = none).
    needs_key: str = ""
    #: Run login_argv / tool calls with HOME = the session dir. False when the tool
    #: takes an explicit path instead (login_argv may use the `{session}` placeholder).
    session_home: bool = True

    def setup_problems(self) -> List[str]:
        """What still blocks this channel after its tools are installed (keys, browser...)."""
        return []

    def validate_params(self, action: str, params: dict) -> None:
        """Reject site-specific invalid input before installation or session setup."""

    def on_add(self) -> None:
        """Extra setup after tools are installed (e.g. register an MCP server)."""

    def on_remove(self) -> None:
        """Undo on_add."""

    def sync_login(self) -> Optional[dict]:
        """Pull login state from the Agent Reach browser after the user logged in there.

        Return a result dict, or None to fall back to running `login_argv`.
        """
        return None

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this channel can handle this URL."""
        ...
