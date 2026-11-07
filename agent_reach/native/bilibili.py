# -*- coding: utf-8 -*-
"""Native Bilibili backend: WBI-signed search/read, subtitles and AI summary.

Ported from the former ``~/.local/bin/bilibili_subtitle.py`` with these fixes:

* no hard-coded SESSDATA / proxy constants — credentials come from ``Config``
  (``bili_cookie``), ``BILI_COOKIE``, the local CDP cookie file, or optionally
  Chrome through ``rookiepy``; the proxy comes from ``Config`` / the
  environment via ``requests``' ``trust_env``;
* library code uses ``logging`` only — no ``print`` and no import-time
  cookie/Chrome reads;
* every HTTP call takes and forwards ``timeout``;
* Bilibili errors map to unified codes via ``native._items.map_bili_error``;
* ``search_videos`` adds the WBI search endpoint so search no longer needs
  bili-cli.

The public ``search/read/subtitle/summary`` helpers return unified items;
``extract_subtitle``/``get_video_info``/... keep the original data shapes for
``main()`` and for embedding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote, urlparse, urlsplit

import requests

from agent_reach.config import Config
from agent_reach.native._items import (
    BILI_NO_KEY_HINT,
    map_bili_error,
    search_item,
    subtitle_item,
    summary_item,
    video_item,
)
from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NEED_SETUP,
    NOT_FOUND,
    RATE_LIMITED,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
)
from agent_reach.utils.paths import (
    PrivatePathError,
    home_dir,
    read_small_text_no_follow,
)
from agent_reach.utils.text import scrub_url_credentials
from agent_reach.utils.url import host_matches

LOG = logging.getLogger(__name__)

API = "https://api.bilibili.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}
COOKIE_NAMES = ("SESSDATA", "bili_jct", "DedeUserID", "buvid3")
DEFAULT_TIMEOUT = 30.0
DEFAULT_SUMMARY_BASE_URL = "https://api.qnaigc.com/v1"
DEFAULT_SUMMARY_MODEL = "deepseek/deepseek-v4-flash"
MAX_SUMMARY_INPUT = 30000
MAX_COOKIE_FILE_BYTES = 64 * 1024

_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")

# WBI signature constants (from the Chrono extension).
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32,
    15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19,
    29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63,
    57, 62, 11, 36, 20, 34, 44, 52,
]

_SESSION: Optional[requests.Session] = None


# ── HTTP plumbing ──


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        session.trust_env = True
        _SESSION = session
    return _SESSION


def _proxies() -> Optional[Dict[str, str]]:
    """Only an explicitly configured proxy is passed; requests reads env when None."""
    proxy = Config(read_only=True).get("proxy")
    proxy = str(proxy).strip() if proxy else ""
    return {"http": proxy, "https": proxy} if proxy else None


def _request(
    method: str,
    url: str,
    *,
    timeout: float,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cookies: Optional[dict] = None,
    action: str = "read",
) -> requests.Response:
    try:
        response = _session().request(
            method,
            url,
            params=params,
            headers={**HEADERS, **(headers or {})},
            cookies=cookies or {},
            proxies=_proxies(),
            timeout=max(float(timeout), 0.1),
        )
    except requests.Timeout:
        raise ReachError(TIMEOUT, f"Bilibili did not answer within {timeout:.0f}s") from None
    except requests.RequestException as exc:
        raise ReachError(
            UPSTREAM_BROKEN, f"Bilibili network error: {type(exc).__name__}"
        ) from None
    if response.status_code >= 400:
        if response.status_code in (401, 403) and not (cookies or {}).get("SESSDATA"):
            # An anonymous request was denied: this says nothing about the
            # user's credentials, so keep the bili-cli fallback reachable.
            raise ReachError(
                UPSTREAM_BROKEN,
                f"Bilibili denied the anonymous request (HTTP {response.status_code})",
            )
        raise map_bili_error(response.status_code, f"HTTP {response.status_code}", action)
    return response


def _decode_json(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        raise ReachError(
            UPSTREAM_BROKEN, "Bilibili returned an HTML/verification page instead of JSON"
        ) from None
    if not isinstance(payload, dict):
        raise ReachError(UPSTREAM_BROKEN, "Bilibili returned an unexpected JSON shape")
    return payload


def _raise_for_code(payload: dict, action: str, cookies: Optional[dict] = None) -> None:
    code = payload.get("code")
    if code in (0, None):
        return
    if code == -101 and (cookies or {}).get("SESSDATA"):
        # A credential was provided and refused; NEED_SETUP would be wrong here.
        raise ReachError(
            NEED_LOGIN,
            str(payload.get("message") or "Bilibili rejected the provided login"),
            hint="Sign in to bilibili.com in Chrome or update `bili_cookie`.",
        )
    raise map_bili_error(code, payload.get("message"), action)


def fetch_json(
    url: str,
    params: Optional[dict] = None,
    *,
    timeout: float,
    cookies: Optional[dict] = None,
    action: str = "read",
    check_code: bool = True,
) -> dict:
    """GET and decode JSON; Bilibili ``code`` failures become unified errors."""
    response = _request(
        "GET", url, timeout=timeout, params=params, cookies=cookies, action=action
    )
    payload = _decode_json(response)
    if check_code:
        _raise_for_code(payload, action, cookies)
    return payload


def fetch_text(
    url: str, *, timeout: float, cookies: Optional[dict] = None, action: str = "read"
) -> str:
    response = _request("GET", url, timeout=timeout, cookies=cookies, action=action)
    return response.text


# ── cookies ──


def _parse_cookie_value(value: Any) -> Dict[str, str]:
    """Accept a ``name=value; ...`` string, a YAML dict, or None."""
    if not value:
        return {}
    if isinstance(value, dict):
        return {str(name): str(item) for name, item in value.items() if item}
    text = str(value).strip()
    if not text:
        return {}
    try:
        parsed = SimpleCookie()
        parsed.load(text)
        jar = {name: morsel.value for name, morsel in parsed.items() if morsel.value}
        if jar:
            return jar
    except Exception:  # noqa: BLE001 - fall through to the lenient parser
        pass
    jar = {}
    for chunk in text.split(";"):
        name, sep, item = chunk.strip().partition("=")
        if sep and name.strip():
            jar[name.strip()] = item.strip().strip('"')
    return jar


def _configured_cookies() -> Dict[str, str]:
    """Merge config and BILI_COOKIE by name; config wins on conflicts.

    SESSDATA is the required field, but a config value that only carries
    ``bili_jct``/``buvid3`` must not be discarded when the env supplies the rest.
    """
    configured = _parse_cookie_value(Config(read_only=True).get("bili_cookie"))
    environment = _parse_cookie_value(os.environ.get("BILI_COOKIE"))
    return {**environment, **configured}


def _cookie_file() -> Path:
    return home_dir() / ".local/share/bili-sub/cookies.json"


def _load_cookies_from_cdp_file() -> Dict[str, str]:
    """Read the JSON extracted from Chrome by the user's cookie helper.

    The file is user-controlled, so refuse symlinks and anything above a small
    size cap before parsing it.
    """
    path = _cookie_file()
    try:
        payload = read_small_text_no_follow(path, max_bytes=MAX_COOKIE_FILE_BYTES)
    except (OSError, PrivatePathError) as exc:
        LOG.debug("Cookie file unreadable: %s", type(exc).__name__)
        return {}
    if payload is None:
        return {}
    try:
        fresh = json.loads(payload)
    except ValueError:
        return {}
    if not isinstance(fresh, dict):
        return {}
    jar = {
        name: str(fresh[name])
        for name in COOKIE_NAMES
        if fresh.get(name)
    }
    if jar.get("SESSDATA"):
        LOG.debug("Loaded Bilibili cookies from %s", path)
    return jar


def _load_cookies_from_chrome() -> Dict[str, str]:
    """Optional Chrome cookie bootstrap; never raises and never logs values."""
    jar = _load_cookies_from_cdp_file()
    if jar.get("SESSDATA"):
        return jar
    try:
        import rookiepy

        fresh = {
            cookie.get("name"): cookie.get("value")
            for cookie in rookiepy.chrome(domains=[".bilibili.com"])
        }
    except Exception as exc:  # noqa: BLE001 - rookiepy is an optional helper
        LOG.debug("Chrome cookie read unavailable: %s", type(exc).__name__)
        return {}
    return {name: str(fresh[name]) for name in COOKIE_NAMES if fresh.get(name)}


def _resolve_cookies(*, allow_chrome: bool = False) -> Dict[str, str]:
    """Config/env override the local file; Chrome is only consulted when needed."""
    configured = _configured_cookies()
    jar = _load_cookies_from_cdp_file()
    jar.update(configured)
    if jar.get("SESSDATA"):
        return jar
    if allow_chrome:
        from_chrome = _load_cookies_from_chrome()
        from_chrome.update(configured)
        if from_chrome.get("SESSDATA"):
            return from_chrome
    return jar


def _login_cookies() -> Dict[str, str]:
    """Subtitles and summaries need a login; a missing cookie is non-final."""
    jar = _resolve_cookies(allow_chrome=True)
    if not jar.get("SESSDATA"):
        raise ReachError(
            NEED_SETUP,
            "Bilibili subtitles need a login, and no SESSDATA was found",
            hint=(
                "Set `bili_cookie` in ~/.agent-reach/config.yaml (or export BILI_COOKIE), "
                "or sign in to bilibili.com in Chrome."
            ),
        )
    return jar


# ── WBI signing ──


def get_mixin_key(original: str) -> str:
    """Reorder the mixin key using the encoding table."""
    return "".join(original[MIXIN_KEY_ENC_TAB[i]] for i in range(32))[:32]


def get_wbi_keys(*, timeout: float, cookies: Optional[dict] = None) -> tuple:
    """Fetch WBI keys from the nav endpoint (guests get them too)."""
    nav = fetch_json(
        f"{API}/x/web-interface/nav",
        timeout=timeout,
        cookies=cookies,
        action="search",
        check_code=False,
    )
    image = (nav.get("data") or {}).get("wbi_img", {}).get("img_url", "")
    sub = (nav.get("data") or {}).get("wbi_img", {}).get("sub_url", "")
    if not image or not sub:
        raise ReachError(UPSTREAM_BROKEN, "Bilibili did not return WBI signing keys")

    def extract_key(url: str) -> str:
        filename = urlparse(url).path.rsplit("/", 1)[-1]
        return filename.split(".")[0]

    return extract_key(image), extract_key(sub)


def _encode_param(value: str) -> str:
    cleaned = re.sub(r"[!'()*]", "", str(value))
    # safe="" also encodes "/", which otherwise breaks WBI w_rid for keywords
    # such as "C/C++" (Bili's reference implementation encodes it).
    return quote(cleaned, safe="")


def sign_wbi_params(params: dict, img_key: str, sub_key: str, wts: Optional[str] = None) -> str:
    """Return the signed query string (values already URL-encoded)."""
    mixin_key = get_mixin_key(img_key + sub_key)
    if wts is None:
        wts = str(int(time.time()))
    signed = dict(params)
    signed["wts"] = wts
    encoded = "&".join(
        f"{key}={_encode_param(str(signed[key]))}" for key in sorted(signed)
    )
    w_rid = hashlib.md5((encoded + mixin_key).encode("utf-8")).hexdigest()
    return f"{encoded}&w_rid={w_rid}"


# ── search / read ──


def search_videos(query: str, limit: int = 5, *, timeout: float = DEFAULT_TIMEOUT) -> list:
    """Search videos through the WBI endpoint; returns raw result rows."""
    limit = max(1, int(limit))
    cookies = _resolve_cookies()
    image, sub = get_wbi_keys(timeout=timeout, cookies=cookies)
    params = {
        "search_type": "video",
        "keyword": str(query),
        "page": 1,
        "page_size": limit,
    }
    signed = sign_wbi_params(params, image, sub)
    payload = fetch_json(
        f"{API}/x/web-interface/wbi/search/type?{signed}",
        timeout=timeout,
        cookies=cookies,
        action="search",
    )
    data = payload.get("data") or {}
    rows = data.get("result") if isinstance(data, dict) else None
    return [row for row in (rows or []) if isinstance(row, dict)][:limit]


def get_video_info(
    bvid: str, *, timeout: float = DEFAULT_TIMEOUT, cookies: Optional[dict] = None
) -> dict:
    """Video metadata including the full multi-part ``pages`` list."""
    if cookies is None:
        cookies = _resolve_cookies()
    payload = fetch_json(
        f"{API}/x/web-interface/view",
        params={"bvid": bvid},
        timeout=timeout,
        cookies=cookies,
        action="read",
    )
    view = payload.get("data") or {}

    pages = []
    cumulative = 0
    for raw_page in view.get("pages") or []:
        duration = raw_page.get("duration", 0)
        pages.append(
            {
                "cid": raw_page.get("cid", 0),
                "page": raw_page.get("page", 0),
                "part": raw_page.get("part", ""),
                "duration": duration,
                "time_offset": cumulative,
            }
        )
        cumulative += duration

    cid = pages[0]["cid"] if pages else view.get("cid", 0)
    stat = view.get("stat") or {}
    return {
        "bvid": bvid,
        "aid": view.get("aid", 0),
        "cid": cid,
        "pages": pages,
        "page_count": len(pages),
        "title": view.get("title", ""),
        "desc": view.get("desc", ""),
        "owner": (view.get("owner") or {}).get("name", ""),
        "duration": view.get("duration", 0),
        "pubdate": view.get("pubdate", 0),
        "views": stat.get("view", 0),
        "stat": stat,
        "subtitle_allow_submit": (view.get("subtitle") or {}).get("allow_submit", False),
        "subtitle_list": (view.get("subtitle") or {}).get("list", []),
        "url": f"https://www.bilibili.com/video/{bvid}",
    }


# ── subtitles ──


def get_subtitle_tracks(
    bvid: str, cid: int, aid: int, *, timeout: float, cookies: dict
) -> list:
    """Subtitle tracks for one part, WBI-signed with a v2 fallback."""
    image, sub = get_wbi_keys(timeout=timeout, cookies=cookies)
    params = {
        "aid": str(aid),
        "cid": str(cid),
        "isGaiaAvoided": "false",
        "web_location": 1315873,
    }
    signed = sign_wbi_params(params, image, sub)
    player_url = f"{API}/x/player/wbi/v2?{signed}"
    try:
        player = fetch_json(
            player_url, timeout=timeout, cookies=cookies, action="subtitle"
        )
    except ReachError as exc:
        if exc.code != UPSTREAM_BROKEN:
            raise
        # The old unsigned endpoint still answers on some deployments.
        player = fetch_json(
            f"{API}/x/player/v2",
            params={"cid": cid, "bvid": bvid},
            timeout=timeout,
            cookies=cookies,
            action="subtitle",
        )

    login_mid = (player.get("data") or {}).get("login_mid", 0)
    if not login_mid:
        if cookies.get("SESSDATA"):
            raise ReachError(
                NEED_LOGIN,
                "Bilibili rejected the provided login; subtitles need a fresh session",
                hint="Sign in to bilibili.com in Chrome or update `bili_cookie`.",
            )
        raise ReachError(
            NEED_SETUP,
            "Bilibili subtitles need a login",
            hint="Set `bili_cookie` or sign in to bilibili.com in Chrome.",
        )

    tracks = []
    for subtitle in (player.get("data") or {}).get("subtitle", {}).get("subtitles", []):
        url = str(subtitle.get("subtitle_url") or "").strip()
        if not url:
            LOG.debug("Skipping a Bilibili subtitle track without a URL")
            continue
        if url.startswith("//"):
            url = "https:" + url
        tracks.append(
            {
                "id": str(subtitle.get("id", "")),
                "language": subtitle.get("lan", "unknown"),
                "label": subtitle.get("lan_doc", subtitle.get("lan", "")),
                "url": url,
            }
        )
    return tracks


def download_subtitle(
    url: str, *, timeout: float, cookies: Optional[dict] = None
) -> list:
    """Download a subtitle JSON document and return its segments."""
    text = fetch_text(url, timeout=timeout, cookies=cookies, action="subtitle")
    try:
        data = json.loads(text)
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "Bilibili subtitle payload was not JSON") from None
    return data.get("body", []) if isinstance(data, dict) else []


def format_segments(body: list, show_timestamps: bool = True, offset: float = 0) -> str:
    """Render subtitle segments; timestamps use HH:MM:SS in video time."""
    lines = []
    for entry in body:
        start = entry.get("from", 0) + offset
        content = entry.get("content", "").strip()
        if not content:
            continue
        if show_timestamps:
            total = int(start)
            hours, rest = divmod(total, 3600)
            minutes, seconds = divmod(rest, 60)
            lines.append(f"[{hours:02d}:{minutes:02d}:{seconds:02d}] {content}")
        else:
            lines.append(content)
    return "\n".join(lines)


def extract_subtitle(
    bvid: str,
    language: Optional[str] = None,
    show_timestamps: bool = True,
    part: Optional[int] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    cookies: Optional[dict] = None,
) -> dict:
    """Extract one part's subtitles. ``part`` is 1-based; out-of-range clamps to the last part."""
    if cookies is None:
        cookies = _login_cookies()
    elif not cookies.get("SESSDATA"):
        raise ReachError(
            NEED_SETUP,
            "Bilibili subtitles need a login",
            hint="Set `bili_cookie` or sign in to bilibili.com in Chrome.",
        )

    info = get_video_info(bvid, timeout=timeout, cookies=cookies)
    pages = info.get("pages") or [
        {
            "cid": info.get("cid", 0),
            "page": 1,
            "part": "",
            "duration": info.get("duration", 0),
            "time_offset": 0,
        }
    ]
    page_count = len(pages)

    if part is None:
        part = 1
    part = max(1, int(part))
    if part > page_count:
        LOG.warning(
            "Requested P%d but the video has %d part(s); using P%d",
            part,
            page_count,
            page_count,
        )
        part = page_count

    selected = pages[part - 1]
    part_result = _extract_one_part(
        bvid, info, selected, language, show_timestamps, timeout=timeout, cookies=cookies
    )

    result = {
        "bvid": bvid,
        "title": info["title"],
        "owner": info["owner"],
        "duration": info["duration"],
        "views": info["views"],
        "pubdate": info.get("pubdate", 0),
        "url": info["url"],
        "page_count": page_count,
        "pages": pages,
        "parts": [part_result],
        "subtitles": part_result["subtitles"],
        "ai_summary": None,
        "has_subtitles": part_result["has_subtitles"],
    }
    if part_result["has_subtitles"]:
        result["subtitle_available"] = True
    else:
        if not info.get("subtitle_allow_submit", False):
            result["subtitle_closed"] = True
        subtitle_list = info.get("subtitle_list") or []
        if subtitle_list:
            result["subtitle_count"] = len(subtitle_list)
        result["subtitle_available"] = False
    return result


def _extract_one_part(
    bvid: str,
    info: dict,
    page: dict,
    language: Optional[str],
    show_timestamps: bool,
    *,
    timeout: float,
    cookies: dict,
) -> dict:
    tracks = get_subtitle_tracks(
        bvid, page["cid"], info["aid"], timeout=timeout, cookies=cookies
    )
    part_result = {
        "part": page["page"],
        "part_name": page["part"],
        "cid": page["cid"],
        "duration": page["duration"],
        "has_subtitles": False,
        "subtitle_available": bool(tracks),
        "tracks": tracks,
        "subtitles": {},
    }
    for track in tracks:
        code = track["language"]
        if language and code != language:
            continue
        body = download_subtitle(track["url"], timeout=timeout, cookies=cookies)
        text = format_segments(
            body, show_timestamps, offset=page.get("time_offset", 0)
        )
        if not text.strip():
            # An empty track must not claim the part has subtitles.
            continue
        existing = part_result["subtitles"].get(code)
        if existing is not None:
            # Some videos expose several tracks with the same `lan`; keep both.
            existing["line_count"] += len(body)
            existing["text"] = "\n\n".join(
                chunk for chunk in (existing["text"], text) if chunk
            )
            continue
        part_result["subtitles"][code] = {
            "label": track["label"],
            "url": track["url"],
            "line_count": len(body),
            "text": text,
        }
        part_result["has_subtitles"] = True
    if language and not part_result["has_subtitles"]:
        part_result["subtitles"] = {}
    return part_result


# ── AI summary ──


def _summary_settings() -> tuple:
    config = Config(read_only=True)
    # `Config.get` checks the YAML before the uppercase env var, so an explicit
    # empty YAML value would otherwise shadow SUMMARY_API_KEY.
    api_key = str(
        config.get("summary_api_key")
        or os.environ.get("SUMMARY_API_KEY")
        or os.environ.get("BILIBILI_SUMMARY_API_KEY")
        or ""
    ).strip()
    base_url = str(
        config.get("summary_base_url")
        or os.environ.get("SUMMARY_BASE_URL")
        or os.environ.get("BILIBILI_SUMMARY_BASE_URL")
        or DEFAULT_SUMMARY_BASE_URL
    ).strip()
    model = str(
        config.get("summary_model")
        or os.environ.get("SUMMARY_MODEL")
        or os.environ.get("BILIBILI_SUMMARY_MODEL")
        or DEFAULT_SUMMARY_MODEL
    ).strip()
    return api_key, base_url, model


def _provider_message(response: requests.Response) -> str:
    """Provider-supplied detail, scrubbed and bounded, for the error envelope."""
    text = str(getattr(response, "text", "") or "")
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            text = str(error["message"])
        elif payload.get("message"):
            text = str(payload["message"])
    return scrub_url_credentials(text).strip()[:200]


def get_ai_summary(
    text: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Call an OpenAI-compatible endpoint and return the summary text."""
    if not api_key:
        raise ReachError(NEED_SETUP, "Bilibili summary needs an API key", hint=BILI_NO_KEY_HINT)
    prompt = [
        "你是一个中文视频内容分析助手。",
        "根据字幕输出结构化总结，不要编造字幕中没有的信息。",
        "输出包含：一句话概括、要点列表、关键术语、适合复习的时间线。",
    ]
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "\n".join(prompt)},
            {"role": "user", "content": text[:MAX_SUMMARY_INPUT]},
        ],
        "stream": False,
    }
    try:
        response = _session().request(
            "POST",
            base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            proxies=_proxies(),
            timeout=max(float(timeout), 0.1),
        )
    except requests.Timeout:
        raise ReachError(TIMEOUT, f"summary endpoint did not answer within {timeout:.0f}s") from None
    except requests.RequestException as exc:
        raise ReachError(
            UPSTREAM_BROKEN, f"summary endpoint network error: {type(exc).__name__}"
        ) from None
    if response.status_code != 200:
        provider = _provider_message(response)
        suffix = f": {provider}" if provider else ""
        if response.status_code in (401, 403):
            raise ReachError(
                NEED_SETUP,
                f"summary endpoint rejected the API key (HTTP {response.status_code}){suffix}",
                hint=BILI_NO_KEY_HINT,
            )
        if response.status_code == 429:
            raise ReachError(
                RATE_LIMITED,
                provider or "summary endpoint rate limited the request",
            )
        raise ReachError(
            UPSTREAM_BROKEN,
            f"summary endpoint returned HTTP {response.status_code}{suffix}",
        )
    try:
        payload = response.json()
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "summary endpoint returned non-JSON") from None
    choices = payload.get("choices") or [{}]
    content = ((choices[0] or {}).get("message") or {}).get("content") or ""
    content = str(content).strip()
    if not content:
        raise ReachError(UPSTREAM_BROKEN, "summary endpoint returned an empty answer")
    return content


# ── unified item helpers (used by channels/bilibili.py) ──


def _bvid_from_target(target: str, *, timeout: float) -> str:
    text = str(target).strip()
    match = _BV_RE.search(text)
    if match:
        return match.group(0)
    if "b23.tv/" in text:
        url = text if "://" in text else f"https://{text}"
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            _ = parsed.port  # malformed/out-of-range ports raise here
        except ValueError:
            parsed, host = None, ""
        if (
            parsed is None
            or host not in {"b23.tv", "www.b23.tv"}
            or not host_matches(url, "b23.tv")
        ):
            raise ReachError(
                BAD_INPUT,
                "b23.tv short links must use http(s) on b23.tv or www.b23.tv",
            )
        response = _request("HEAD", url, timeout=timeout, action="read")
        match = _BV_RE.search(response.url)
        if match:
            return match.group(0)
    raise ReachError(
        BAD_INPUT, "target must be a BV id or a bilibili.com / b23.tv video link"
    )


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    raise ReachError(BAD_INPUT, "timestamps must be true or false")


def search(query: str, limit: int = 5, *, timeout: float = DEFAULT_TIMEOUT) -> list:
    rows = search_videos(query, limit=limit, timeout=timeout)
    return [search_item(row) for row in rows]


def read(target: str, *, timeout: float = DEFAULT_TIMEOUT) -> list:
    bvid = _bvid_from_target(target, timeout=timeout)
    return [video_item(get_video_info(bvid, timeout=timeout, cookies=_resolve_cookies()))]


def subtitle(
    target: str,
    part: int = 1,
    language: Optional[str] = "ai-zh",
    timestamps: Any = "true",
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list:
    show_timestamps = _parse_bool(timestamps, default=True)
    bvid = _bvid_from_target(target, timeout=timeout)
    result = extract_subtitle(
        bvid,
        language=language or None,
        show_timestamps=show_timestamps,
        part=part,
        timeout=timeout,
    )
    part_result = result["parts"][0]
    if not part_result.get("has_subtitles"):
        available = sorted(
            {
                str(track.get("language"))
                for track in part_result.get("tracks") or []
                if track.get("language")
            }
        )
        if available:
            # Tracks exist but not the requested one: non-final so bili-cli's
            # own default-language attempt still runs.
            raise ReachError(
                UPSTREAM_BROKEN,
                f"no subtitles for language '{language}' (available: {', '.join(available)})",
            )
        wanted = f" for language '{language}'" if language else ""
        raise ReachError(NOT_FOUND, f"this video part has no subtitles{wanted}")
    return [subtitle_item(result, language=language or None)]


def summary(
    target: str,
    part: int = 1,
    language: Optional[str] = "ai-zh",
    model: Optional[str] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list:
    api_key, base_url, configured_model = _summary_settings()
    model = str(model or "").strip() or configured_model
    if not api_key:
        raise ReachError(
            NEED_SETUP, "Bilibili summary needs `summary_api_key`", hint=BILI_NO_KEY_HINT
        )
    bvid = _bvid_from_target(target, timeout=timeout)
    cookies = _login_cookies()
    result = extract_subtitle(
        bvid,
        language=language or None,
        # The prompt asks for a timeline, so timestamps must be part of the input.
        show_timestamps=True,
        part=part,
        timeout=timeout,
        cookies=cookies,
    )
    part_result = result["parts"][0]
    texts = [
        track["text"]
        for track in part_result.get("subtitles", {}).values()
        if track.get("text")
    ]
    available = sorted(
        {
            str(track.get("language"))
            for track in part_result.get("tracks") or []
            if track.get("language")
        }
    )
    if not texts and available:
        # The requested language is missing; summarize the first available one.
        result = extract_subtitle(
            bvid,
            language=available[0],
            show_timestamps=True,
            part=part,
            timeout=timeout,
            cookies=cookies,
        )
        part_result = result["parts"][0]
        texts = [
            track["text"]
            for track in part_result.get("subtitles", {}).values()
            if track.get("text")
        ]
    if not texts:
        detail = f" (available: {', '.join(available)})" if available else ""
        raise ReachError(NOT_FOUND, f"this video has no subtitles to summarize{detail}")
    source_text = "\n\n".join(texts)
    summary_text = get_ai_summary(
        source_text,
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )
    return [
        summary_item(
            result,
            summary_text,
            model=model,
            input_characters=len(source_text),
            truncated=len(source_text) > MAX_SUMMARY_INPUT,
        )
    ]


# ── CLI compatibility layer ──


def _dump_result(result: dict, args: argparse.Namespace) -> str:
    if args.json:
        return json.dumps(result, ensure_ascii=False, indent=2)
    lines = [
        "=== Bilibili Subtitle Extractor (Chrono-powered) ===",
        f'Title: {result["title"]}',
        f'UP: {result["owner"]}',
        f'Duration: {result["duration"]}s | Views: {result["views"]:,}',
    ]
    if result.get("page_count", 1) > 1:
        current = result["parts"][0] if result["parts"] else {}
        lines.append(
            f'多P合集: {result["page_count"]} P | 当前: P{current.get("part", "?")} '
            f'{current.get("part_name", "")} ({current.get("duration", 0)}s)'
        )
    lines.append(
        f'Subtitles: {result.get("subtitle_available", False)} '
        f'(count: {len(result.get("subtitles", {}))})'
    )
    lines.append(f'URL: {result["url"]}')
    lines.append("")
    if not result.get("has_subtitles"):
        if result.get("subtitle_closed"):
            lines.append("⚠️ 字幕已关闭下载权限 (UP主设置了 allow_submit=false)")
        else:
            lines.append("⚠️ 该视频没有字幕")
    for part_result in result.get("parts", []):
        if part_result.get("part_name") and result.get("page_count", 1) > 1:
            lines.append(f'--- P{part_result["part"]} {part_result["part_name"]} ---')
        for track in part_result.get("subtitles", {}).values():
            lines.append(f'[{track["label"]}] {track["line_count"]} lines')
            lines.append(track["text"])
            lines.append("")
    if result.get("ai_summary"):
        ai = result["ai_summary"]
        if ai.get("summary"):
            lines.append("=== AI 总结 ===")
            lines.append(ai["summary"])
        if ai.get("error"):
            lines.append(f'AI Error: {ai["error"]}')
    return "\n".join(lines)


def _save_result(result: dict, args: argparse.Namespace, content: str) -> str:
    save_arg = Path(str(args.save))
    part_result = result["parts"][0] if result.get("parts") else {}
    part_label = f'[P{part_result.get("part", "?")} {part_result.get("part_name", "")}]'.strip()
    is_directory = str(args.save).endswith(("/", os.sep)) or save_arg.is_dir()
    if is_directory:
        safe_title = "".join(
            char for char in str(result.get("title") or "") if char not in r'\/:*?"<>|'
        )[:80] or "bilibili"
        name = (
            f"{safe_title} {part_label}.md"
            if part_label and result.get("page_count", 1) > 1
            else f"{safe_title}.md"
        )
        save_path = save_arg / name
    elif result.get("page_count", 1) > 1 and not save_arg.suffix:
        save_path = Path(f"{save_arg} {part_label}.md")
    else:
        save_path = save_arg
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return str(save_path)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract subtitles from Bilibili videos (automated, no browser needed)"
    )
    parser.add_argument("bvid", help="Bilibili BV号 (e.g. BV1vVfmY1EBW)")
    parser.add_argument(
        "--language",
        "-l",
        default="ai-zh",
        help="Subtitle language (default: ai-zh 中文; e.g. ai-en, ai-ja, zh-Hans)",
    )
    parser.add_argument("--save", "-s", help="Save to file path (or directory for multi-P)")
    parser.add_argument("--no-timestamp", action="store_true", help="Hide timestamps")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--ai", action="store_true", help="Generate AI summary")
    parser.add_argument("--ai-model", help="AI model name")
    parser.add_argument("--ai-base-url", help="AI base URL")
    parser.add_argument(
        "--part",
        "-p",
        type=int,
        default=1,
        help="多P合集选哪个 P (1-based, default 1)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = extract_subtitle(
            args.bvid,
            language=args.language,
            show_timestamps=not args.no_timestamp,
            part=args.part,
            timeout=DEFAULT_TIMEOUT,
        )
    except ReachError as exc:
        print(f"\n❌ {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"\n❌ 提取失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.ai:
        api_key, base_url, model = _summary_settings()
        for track in result.get("subtitles", {}).values():
            if track.get("text"):
                try:
                    summary_text = get_ai_summary(
                        track["text"],
                        model=args.ai_model or model,
                        base_url=args.ai_base_url or base_url,
                        api_key=api_key,
                        timeout=60.0,
                    )
                    result["ai_summary"] = {"summary": summary_text, "error": None}
                except ReachError as exc:
                    result["ai_summary"] = {"summary": None, "error": exc.message}
                break

    content = _dump_result(result, args)
    if not args.save:
        print(content)
        return 0

    if args.json:
        saved_content = content
    else:
        saved_content = f'Bilibili: {result["title"]}\n'
        saved_content += f'UP: {result["owner"]}\n'
        saved_content += f'Duration: {result["duration"]}s\n'
        saved_content += f'Subtitles: {result.get("subtitle_available", False)}\n'
        saved_content += f'URL: {result["url"]}\n'
        saved_content += "=" * 60 + "\n\n"
        for part_result in result.get("parts", []):
            if part_result.get("part_name") and result.get("page_count", 1) > 1:
                saved_content += f'\n## P{part_result["part"]} {part_result["part_name"]}\n\n'
            for track in part_result.get("subtitles", {}).values():
                saved_content += f'\n## {track["label"]}\n\n'
                saved_content += track["text"] + "\n"
        if result.get("ai_summary") and result["ai_summary"].get("summary"):
            saved_content += "\n## AI 总结\n\n"
            saved_content += result["ai_summary"]["summary"] + "\n"
    print(content)
    save_path = _save_result(result, args, saved_content)
    print(f"\nSaved to: {save_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
