# -*- coding: utf-8 -*-
"""Auto-extract cookies from local browsers for all supported platforms.

Supports: Chrome, Firefox, Edge, Brave, Opera
Extracts: Twitter, XiaoHongShu, Bilibili cookies in one shot.

Usage:
    agent-reach configure --from-browser chrome
"""

from typing import Dict, List, Optional, Tuple, TypedDict


class PlatformSpec(TypedDict):
    name: str
    domains: List[str]
    cookies: Optional[List[str]]
    config_key: str


# Platform cookie specs: (platform_name, domain_pattern, needed_cookies)
PLATFORM_SPECS: List[PlatformSpec] = [
    {
        "name": "Twitter/X",
        "domains": [".x.com", ".twitter.com"],
        "cookies": ["auth_token", "ct0"],
        "config_key": "twitter",
    },
    {
        "name": "XiaoHongShu",
        "domains": [".xiaohongshu.com"],
        "cookies": None,  # None = grab all cookies as header string
        "config_key": "xhs",
    },
    {
        "name": "Bilibili",
        "domains": [".bilibili.com"],
        "cookies": ["SESSDATA", "bili_jct"],
        "config_key": "bilibili",
    },
]


def extract_all(browser: str = "chrome") -> Dict[str, dict]:
    """
    Extract cookies for all supported platforms from the specified browser.
    
    Returns:
        {
            "twitter": {"auth_token": "xxx", "ct0": "yyy"},
            "xhs": {"cookie_string": "a=1; b=2; ..."},
            "bilibili": {"SESSDATA": "xxx", "bili_jct": "yyy"},
        }
    """
    try:
        import browser_cookie3
    except ImportError:
        raise RuntimeError(
            "browser_cookie3 not installed. Run: pip install browser-cookie3"
        )

    # Get browser cookie jar
    browser_funcs = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "edge": browser_cookie3.edge,
        "brave": browser_cookie3.brave,
        "opera": browser_cookie3.opera,
    }

    browser = browser.lower()
    if browser not in browser_funcs:
        raise ValueError(
            f"Unsupported browser: {browser}. "
            f"Supported: {', '.join(browser_funcs.keys())}"
        )

    try:
        cookie_jar = browser_funcs[browser]()
    except Exception as e:
        raise RuntimeError(
            f"Could not read {browser} cookies: {e}\n"
            f"Make sure {browser} is closed and you have permission to read its data."
        )

    results = {}

    for spec in PLATFORM_SPECS:
        platform_cookies = {}
        all_cookies_for_domain = []

        for cookie in cookie_jar:
            # Check if cookie belongs to this platform
            domain_match = any(
                cookie.domain.endswith(d) or cookie.domain == d.lstrip(".")
                for d in spec["domains"]
            )
            if not domain_match:
                continue

            all_cookies_for_domain.append(cookie)

            if spec["cookies"] is not None:
                if cookie.name in spec["cookies"]:
                    platform_cookies[cookie.name] = cookie.value

        if spec["cookies"] is None:
            # Grab all as header string
            if all_cookies_for_domain:
                cookie_str = "; ".join(
                    f"{c.name}={c.value}" for c in all_cookies_for_domain
                )
                results[spec["config_key"]] = {"cookie_string": cookie_str}
        else:
            if platform_cookies:
                results[spec["config_key"]] = platform_cookies

    return results


def configure_from_browser(browser: str, config) -> List[Tuple[str, bool, str]]:
    """
    Extract cookies and configure all found platforms.
    
    Returns list of (platform_name, success, message) tuples.
    """
    results_list = []

    try:
        extracted = extract_all(browser)
    except Exception as e:
        return [("Browser", False, str(e))]

    if not extracted:
        return [("All platforms", False,
                 f"No platform cookies found in {browser}. "
                 f"Make sure you're logged into Twitter, XiaoHongShu, etc. in {browser}.")]

    # Configure each found platform
    if "twitter" in extracted:
        tc = extracted["twitter"]
        if "auth_token" in tc and "ct0" in tc:
            config.set("twitter_auth_token", tc["auth_token"])
            config.set("twitter_ct0", tc["ct0"])
            results_list.append(("Twitter/X", True, "auth_token + ct0"))
        else:
            found = ", ".join(tc.keys())
            missing = [k for k in ["auth_token", "ct0"] if k not in tc]
            results_list.append(("Twitter/X", False,
                                 f"Found {found}, but missing: {', '.join(missing)}. "
                                 f"Make sure you're logged into x.com in {browser}."))

    if "xhs" in extracted:
        cookie_str = extracted["xhs"].get("cookie_string", "")
        if cookie_str:
            config.set("xhs_cookie", cookie_str)
            n_cookies = len(cookie_str.split(";"))
            results_list.append(("XiaoHongShu", True, f"{n_cookies} cookies"))

    if "bilibili" in extracted:
        bc = extracted["bilibili"]
        if "SESSDATA" in bc:
            config.set("bilibili_sessdata", bc["SESSDATA"])
            if "bili_jct" in bc:
                config.set("bilibili_csrf", bc["bili_jct"])
            results_list.append(("Bilibili", True, "SESSDATA" +
                                 (" + bili_jct" if "bili_jct" in bc else "")))
        else:
            results_list.append(("Bilibili", False,
                                 f"No SESSDATA found. Make sure you're logged into bilibili.com in {browser}."))

    return results_list
