# -*- coding: utf-8 -*-
"""Browser cookie import helpers for the supported Windows/Codex fork."""

from __future__ import annotations

from collections.abc import Iterable
from http.cookiejar import Cookie

TWITTER_DOMAINS = (".x.com", ".twitter.com", "x.com", "twitter.com")
SUPPORTED_BROWSERS = ("chrome", "firefox", "edge", "brave", "opera")


def extract_all(browser: str = "chrome") -> dict[str, dict[str, str]]:
    """Extract supported platform credentials from a local browser."""

    cookie_jar = _load_browser_cookies(browser)
    twitter = _extract_twitter_tokens(cookie_jar)
    if not twitter:
        return {}
    return {"twitter": twitter}


def _load_browser_cookies(browser: str) -> Iterable[Cookie]:
    browser_name = browser.lower()
    if browser_name not in SUPPORTED_BROWSERS:
        supported = ", ".join(SUPPORTED_BROWSERS)
        raise ValueError(f"Unsupported browser: {browser}. Supported: {supported}")

    try:
        import browser_cookie3
    except ImportError as exc:
        raise RuntimeError(
            "Browser import requires browser-cookie3. Install it with `pip install browser-cookie3`."
        ) from exc

    loaders = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "edge": browser_cookie3.edge,
        "brave": browser_cookie3.brave,
        "opera": browser_cookie3.opera,
    }
    try:
        return loaders[browser_name]()
    except Exception as exc:  # pragma: no cover - browser-specific failures
        raise RuntimeError(
            f"Could not read {browser_name} cookies. "
            f"Close the browser and confirm you are logged into x.com first. ({exc})"
        ) from exc


def _extract_twitter_tokens(cookie_jar: Iterable[Cookie]) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for cookie in cookie_jar:
        domain = (cookie.domain or "").lower()
        if not any(domain.endswith(candidate) or domain == candidate for candidate in TWITTER_DOMAINS):
            continue
        if cookie.name in {"auth_token", "ct0"} and cookie.value:
            tokens[cookie.name] = cookie.value
    return tokens
