# -*- coding: utf-8 -*-
"""Least-privilege cookie extraction from local browsers.

Supports: Chrome, Firefox, Edge, Brave, Opera
Extracts one explicitly requested platform at a time.

Usage:
    agent-reach configure --from-browser chrome --platform xueqiu
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple, TypedDict

from agent_reach.utils.text import scrub_url_credentials
from agent_reach.utils.url import domain_matches


class PlatformSpec(TypedDict):
    name: str
    domains: Tuple[str, ...]
    cookies: Optional[Tuple[str, ...]]
    config_key: str


class ChromiumPaths(TypedDict):
    darwin: str
    linux: str
    win32: Tuple[str, ...]


PLATFORM_SPECS: Tuple[PlatformSpec, ...] = (
    {
        "name": "Twitter/X",
        "domains": (".x.com", ".twitter.com"),
        "cookies": ("auth_token", "ct0"),
        "config_key": "twitter",
    },
    {
        "name": "XiaoHongShu",
        "domains": (".xiaohongshu.com",),
        "cookies": None,  # manual Cookie-Editor export only
        "config_key": "xhs",
    },
    {
        "name": "Bilibili",
        "domains": (".bilibili.com",),
        "cookies": ("SESSDATA", "bili_jct"),
        "config_key": "bilibili",
    },
    {
        "name": "Xueqiu",
        "domains": (".xueqiu.com",),
        "cookies": ("xq_a_token",),
        "config_key": "xueqiu",
    },
)

_PLATFORM_SPECS_BY_KEY: Dict[str, PlatformSpec] = {
    spec["config_key"]: spec for spec in PLATFORM_SPECS
}
SUPPORTED_BROWSERS = ("chrome", "firefox", "edge", "brave", "opera")
PROFILE_SELECTABLE_BROWSERS = ("chrome", "edge", "brave")
_MAX_XFETCH_SESSION_BYTES = 64 * 1024
_COOKIE_EDITOR_ONLY = {
    "twitter": "twitter-cookies",
    "xhs": "xhs-cookies",
}

_CHROMIUM_USER_DATA_DIRS: Dict[str, ChromiumPaths] = {
    "chrome": {
        "darwin": "~/Library/Application Support/Google/Chrome",
        "linux": "~/.config/google-chrome",
        "win32": ("Google", "Chrome", "User Data"),
    },
    "edge": {
        "darwin": "~/Library/Application Support/Microsoft Edge",
        "linux": "~/.config/microsoft-edge",
        "win32": ("Microsoft", "Edge", "User Data"),
    },
    "brave": {
        "darwin": "~/Library/Application Support/BraveSoftware/Brave-Browser",
        "linux": "~/.config/BraveSoftware/Brave-Browser",
        "win32": ("BraveSoftware", "Brave-Browser", "User Data"),
    },
}


@dataclass(frozen=True)
class BrowserConfigResult:
    """One browser configuration outcome with non-secret write targets."""

    platform: str
    success: bool
    message: str
    targets: Tuple[str, ...] = ()

    def __iter__(self) -> Iterator[object]:
        """Preserve the historical three-value unpacking API."""
        yield self.platform
        yield self.success
        yield self.message


def _chromium_user_data_dir(browser: str) -> Optional[Path]:
    """Return the browser's profile root on the current operating system."""
    import os
    import sys

    paths = _CHROMIUM_USER_DATA_DIRS.get(browser)
    if paths is None:
        return None
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None
        return Path(local_appdata).joinpath(*paths["win32"])
    path = paths["darwin"] if sys.platform == "darwin" else paths["linux"]
    return Path(os.path.expanduser(path))


def list_browser_profiles(browser: str = "chrome") -> List[Dict[str, str]]:
    """List named Chromium profiles that contain a cookie database."""
    browser = browser.lower()
    root = _chromium_user_data_dir(browser)
    if root is None:
        return []
    root = Path(root)
    if not root.is_dir():
        return []

    profiles = []
    for profile_dir in root.iterdir():
        if not profile_dir.is_dir():
            continue
        cookie_file = profile_dir / "Network" / "Cookies"
        if not cookie_file.is_file():
            cookie_file = profile_dir / "Cookies"
        if cookie_file.is_file():
            profiles.append(
                {
                    "folder": profile_dir.name,
                    "cookies_path": str(cookie_file),
                }
            )

    def sort_key(item):
        folder = item["folder"]
        suffix = folder.rsplit(" ", 1)[-1]
        number = int(suffix) if suffix.isdigit() else 0
        return (folder != "Default", number, folder)

    profiles.sort(key=sort_key)
    return profiles


def _profile_cookie_file(browser: str, profile: str) -> str:
    """Resolve an explicit profile or fail without falling back to Default."""
    if browser not in PROFILE_SELECTABLE_BROWSERS:
        raise ValueError(
            "Profile selection is supported only for "
            f"{', '.join(PROFILE_SELECTABLE_BROWSERS)}, "
            f"not {scrub_url_credentials(browser)}."
        )

    profiles = list_browser_profiles(browser)
    for candidate in profiles:
        if candidate["folder"] == profile:
            return candidate["cookies_path"]

    available = ", ".join(
        scrub_url_credentials(item["folder"]) for item in profiles
    )
    hint = f" Available profiles: {available}." if available else ""
    raise ValueError(
        f"Profile '{scrub_url_credentials(profile)}' not found for "
        f"{scrub_url_credentials(browser)}.{hint}"
    )


def _platform_spec(platform: Optional[str]) -> PlatformSpec:
    """Return the one explicitly requested platform specification."""
    if not platform:
        raise ValueError(
            "platform is required for browser-cookie extraction; "
            f"choose one of: {', '.join(_PLATFORM_SPECS_BY_KEY)}"
        )
    key = platform.lower()
    try:
        return _PLATFORM_SPECS_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported platform: {scrub_url_credentials(platform)}. "
            f"Supported: {', '.join(_PLATFORM_SPECS_BY_KEY)}"
        ) from exc


def _require_browser_extractable(spec: PlatformSpec) -> None:
    """Reject platforms whose project policy requires a manual cookie export."""
    manual_key = _COOKIE_EDITOR_ONLY.get(spec["config_key"])
    if manual_key:
        raise ValueError(
            f"Automatic browser extraction is disabled for {spec['name']}. "
            "Export the required cookies with Cookie-Editor, then use "
            f"`agent-reach configure {manual_key}`."
        )


def extract_all(
    browser: str = "chrome",
    *,
    platform: Optional[str] = None,
    profile: Optional[str] = None,
) -> Dict[str, dict]:
    """
    Extract cookies for one explicitly requested platform.

    The legacy function name is retained for API compatibility, but an
    all-platform read is intentionally no longer supported.

    Returns:
        {"xueqiu": {"xq_a_token": "xxx"}}
    """
    spec = _platform_spec(platform)
    _require_browser_extractable(spec)
    browser = browser.lower()
    if browser not in SUPPORTED_BROWSERS:
        raise ValueError(
            f"Unsupported browser: {scrub_url_credentials(browser)}. "
            f"Supported: {', '.join(SUPPORTED_BROWSERS)}"
        )
    cookie_file = _profile_cookie_file(browser, profile) if profile else None
    needed_cookies = spec["cookies"]
    if needed_cookies is None:
        raise ValueError(
            f"Automatic full-domain extraction is disabled for {spec['name']}."
        )

    # Try rookiepy first (Rust-based, more stable), fallback to browser_cookie3
    use_rookiepy = False
    if cookie_file is None:
        try:
            import rookiepy
            use_rookiepy = True
        except ImportError:
            pass
    if not use_rookiepy:
        try:
            import browser_cookie3
        except ImportError:
            profile_hint = (
                f" for profile '{scrub_url_credentials(profile)}'"
                if profile is not None
                else ""
            )
            raise RuntimeError(
                f"Cookie extraction{profile_hint} requires browser_cookie3"
                " (or rookiepy when no profile is selected).\n"
                "Install: pip install browser-cookie3"
            )

    if use_rookiepy:
        # rookiepy returns list of dicts with name/value/domain/path keys
        try:
            browser_funcs = {
                "chrome": rookiepy.chrome,
                "firefox": rookiepy.firefox,
                "edge": rookiepy.edge,
                "brave": rookiepy.brave,
                "opera": rookiepy.opera,
            }
            raw_cookies = browser_funcs[browser](list(spec["domains"]))
            # Wrap into objects with .name, .value, .domain for compatibility
            class _Cookie:
                def __init__(self, d):
                    self.name = d.get("name", "")
                    self.value = d.get("value", "")
                    self.domain = d.get("domain", "")
            cookie_jar = [_Cookie(c) for c in raw_cookies]
        except Exception as e:
            raise RuntimeError(
                f"Could not read {browser} cookies via rookiepy: "
                f"{scrub_url_credentials(e)}\n"
                f"Make sure {browser} is closed and you have permission."
            )
    else:
        browser_funcs = {
            "chrome": browser_cookie3.chrome,
            "firefox": browser_cookie3.firefox,
            "edge": browser_cookie3.edge,
            "brave": browser_cookie3.brave,
            "opera": browser_cookie3.opera,
        }
        try:
            cookie_jar = []
            seen = set()
            for domain in spec["domains"]:
                kwargs = {"domain_name": domain}
                if cookie_file is not None:
                    kwargs["cookie_file"] = cookie_file
                for cookie in browser_funcs[browser](**kwargs):
                    identity = (
                        getattr(cookie, "name", ""),
                        getattr(cookie, "domain", ""),
                        getattr(cookie, "path", ""),
                        getattr(cookie, "value", ""),
                    )
                    if identity not in seen:
                        seen.add(identity)
                        cookie_jar.append(cookie)
        except Exception as e:
            raise RuntimeError(
                f"Could not read {browser} cookies: {scrub_url_credentials(e)}\n"
                f"Make sure {browser} is closed and you have permission."
            )

    results = {}

    platform_cookies = {}
    for cookie in cookie_jar:
        # Re-check returned cookies instead of trusting the backend filter.
        if not domain_matches(cookie.domain, *spec["domains"]):
            continue

        if cookie.name in needed_cookies:
            platform_cookies[cookie.name] = cookie.value

    if platform_cookies:
        results[spec["config_key"]] = platform_cookies

    return results


def _read_xfetch_session(path: Path) -> dict:
    """Read a small regular legacy session file without following symlinks."""
    import json

    from agent_reach.utils.paths import read_small_text_no_follow

    payload = read_small_text_no_follow(
        path,
        max_bytes=_MAX_XFETCH_SESSION_BYTES,
    )
    if payload is None:
        return {}
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        raise ValueError("xfetch 会话文件必须是 JSON object")
    return loaded


def _sync_xfetch_session(auth_token: str, ct0: str) -> bool:
    """Sync Twitter credentials to ~/.config/xfetch/session.json (legacy xreach compat)."""
    import json
    import os

    try:
        from agent_reach.utils.paths import (
            atomic_write_private_text,
            make_private_dir,
        )

        xfetch_dir = os.path.join(os.path.expanduser("~"), ".config", "xfetch")
        make_private_dir(xfetch_dir)
        session_path = Path(xfetch_dir) / "session.json"
        session_data = _read_xfetch_session(session_path)
        session_data["authToken"] = auth_token
        session_data["ct0"] = ct0
        atomic_write_private_text(
            session_path,
            json.dumps(session_data, indent=2),
        )
        return True
    except Exception:
        # Non-fatal: agent-reach config is the source of truth, xfetch sync is best-effort
        return False


def _sync_bird_env(auth_token: str, ct0: str) -> bool:
    """Write Twitter credentials to ~/.config/bird/credentials.env for bird CLI.

    bird reads AUTH_TOKEN and CT0 from environment variables. This writes a
    shell-sourceable file so users can `source ~/.config/bird/credentials.env`.
    Values are passed through shlex.quote so a token containing a quote, $, or
    backtick cannot break out into shell syntax when the file is sourced.
    """
    import os
    import shlex

    try:
        from agent_reach.utils.paths import (
            atomic_write_private_text,
            make_private_dir,
        )

        bird_dir = os.path.join(os.path.expanduser("~"), ".config", "bird")
        make_private_dir(bird_dir)
        env_path = os.path.join(bird_dir, "credentials.env")
        atomic_write_private_text(
            env_path,
            f"AUTH_TOKEN={shlex.quote(auth_token)}\n"
            f"CT0={shlex.quote(ct0)}\n",
        )
        return True
    except Exception:
        # Non-fatal: agent-reach config is the source of truth, bird env sync is best-effort
        return False


# Alias for callers expecting the name _sync_bird_credentials
_sync_bird_credentials = _sync_bird_env


def configure_from_browser(
    browser: str,
    config,
    *,
    platform: Optional[str] = None,
    profile: Optional[str] = None,
) -> List[BrowserConfigResult]:
    """
    Extract and configure exactly one explicitly selected platform.

    Result objects still unpack as ``(platform, success, message)`` and expose
    a ``targets`` attribute so the CLI can disclose every non-secret config key
    or legacy path written.
    """
    spec = _platform_spec(platform)
    _require_browser_extractable(spec)
    results_list: List[BrowserConfigResult] = []

    try:
        extracted = extract_all(
            browser,
            platform=spec["config_key"],
            profile=profile,
        )
    except ValueError:
        raise
    except Exception as e:
        return [
            BrowserConfigResult(
                "Browser", False, scrub_url_credentials(e)
            )
        ]

    config_key = spec["config_key"]
    if config_key not in extracted:
        return [
            BrowserConfigResult(
                spec["name"],
                False,
                f"No {spec['name']} cookies found in {browser}. "
                f"Make sure you're logged into the selected platform.",
            )
        ]

    if config_key == "bilibili":
        bc = extracted["bilibili"]
        if "SESSDATA" in bc:
            config.set("bilibili_sessdata", bc["SESSDATA"])
            targets = ["bilibili_sessdata"]
            if "bili_jct" in bc:
                config.set("bilibili_csrf", bc["bili_jct"])
                targets.append("bilibili_csrf")
            results_list.append(
                BrowserConfigResult(
                    "Bilibili",
                    True,
                    "SESSDATA" + (" + bili_jct" if "bili_jct" in bc else ""),
                    tuple(targets),
                )
            )
        else:
            results_list.append(
                BrowserConfigResult(
                    "Bilibili",
                    False,
                    f"No SESSDATA found. "
                    f"Make sure you're logged into bilibili.com in {browser}.",
                )
            )

    elif config_key == "xueqiu":
        token = extracted["xueqiu"].get("xq_a_token", "")
        if token:
            cookie_str = f"xq_a_token={token}"
            config.set("xueqiu_cookie", cookie_str)
            results_list.append(
                BrowserConfigResult(
                    "Xueqiu",
                    True,
                    "xq_a_token",
                    ("xueqiu_cookie",),
                )
            )
        else:
            results_list.append(
                BrowserConfigResult(
                    "Xueqiu",
                    False,
                    f"未找到 xq_a_token，请先在 {browser} 中登录 xueqiu.com",
                )
            )

    return results_list
