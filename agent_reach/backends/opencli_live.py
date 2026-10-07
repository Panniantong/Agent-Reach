# -*- coding: utf-8 -*-

import json
import os
import re
import time
from typing import Optional, Tuple

from agent_reach.probe import probe_command

LIVE_ENV = "AGENT_REACH_DOCTOR_LIVE"
LIVE_CACHE_TTL_SECONDS = 6 * 3600
LIVE_FAIL_TTL_SECONDS = 15 * 60
_LIVE_TIMEOUT = 90

_LIVE_PROBES = {
    "reddit": ("reddit", "search", "test", "-f", "json"),
    "twitter": ("twitter", "whoami", "-f", "json"),
    "facebook": ("facebook", "profile", "zuck", "-f", "json"),
    "instagram": ("instagram", "profile", "nasa", "-f", "json"),
}

_LOGGED_IN_RE = re.compile(r'"logged_in"\s*:\s*true', re.IGNORECASE)


def live_enabled() -> bool:
    return os.environ.get(LIVE_ENV, "").strip().lower() in ("1", "true", "yes")


def _cache_path():
    from agent_reach.config import Config

    return Config.CONFIG_DIR / "live-check.json"


def _read_cache() -> dict:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(cache: dict) -> None:
    from agent_reach.utils.paths import PrivatePathError, atomic_write_private_text

    try:
        atomic_write_private_text(_cache_path(), json.dumps(cache, indent=2))
    except (OSError, PrivatePathError):
        pass


def _succeeded(site: str, output: str) -> bool:
    if site == "twitter":
        return bool(_LOGGED_IN_RE.search(output))
    return not re.search(r'"?ok"?\s*:\s*false', output)


def live_probe(site: str) -> Optional[Tuple[bool, str]]:
    if not live_enabled() or site not in _LIVE_PROBES:
        return None

    cache = _read_cache()
    entry = cache.get(site)
    now = time.time()
    ttl = (
        LIVE_CACHE_TTL_SECONDS
        if isinstance(entry, dict) and entry.get("ok")
        else LIVE_FAIL_TTL_SECONDS
    )
    if isinstance(entry, dict) and now - entry.get("at", 0) < ttl:
        age_min = int((now - entry["at"]) / 60)
        return bool(entry.get("ok")), f"{entry.get('detail', '')}（缓存，{age_min} 分钟前实测）"

    result = probe_command("opencli", _LIVE_PROBES[site], timeout=_LIVE_TIMEOUT)
    ok = result.ok and _succeeded(site, result.output)
    if ok:
        detail = f"OpenCLI 实时验证通过：`opencli {' '.join(_LIVE_PROBES[site])}` 成功"
    else:
        snippet = (result.output or result.hint or result.status).strip().splitlines()
        detail = "OpenCLI 实时验证失败：" + (snippet[-1][:200] if snippet else result.status)
    cache[site] = {"ok": ok, "at": now, "detail": detail}
    _write_cache(cache)
    return ok, detail
