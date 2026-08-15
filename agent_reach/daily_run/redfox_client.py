# -*- coding: utf-8
"""Low-level RedFox API client (stock-feed, trending-hub, gzh-astock-top)."""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run")

WORK_SEARCH_URL = "https://redfox.hk/story/api/multiPlatform/workSearch"
HOTSPOT_URL = "https://redfox.hk/story/api/hotSpot/getListByPlatformWithKeyword"
GZH_DAILY_URL = "https://redfox.hk/story/api/gzh/search/dailyPublish"
WEIBO_SEARCH_URL = "https://redfox.hk/story/api/weibo/ability/searchWork"

STOCK_FEED_SOURCE = "agent-reach-daily-run"
GZH_SOURCE = "A股公众号大V-GitHub"

DEFAULT_STOCK_KEYWORDS = (
    "A股,A股市场,A股大盘,A股分析,股票,涨停,涨跌,"
    "潜力股,A股龙头,A股复盘,选股,加仓,调仓,补仓,"
    "拆股,仓位管理,A股行情"
)

PLATFORM_RESULT_KEYS = {
    "xhs": ("小红书", "xhsResult"),
    "dy": ("抖音", "dyResult"),
    "gzh": ("公众号", "gzhResult"),
}

TRENDING_PLATFORM_MAP = {
    "wb": 5,
    "dy": 2,
    "bz": 8,
    "ks": 1,
    "zh": 9,
    "tt": 10,
    "bd": 7,
}

TRENDING_LIST_KEYS = {
    "bd": "bdList",
    "bz": "bzList",
    "dy": "dyList",
    "ks": "ksList",
    "tt": "ttList",
    "wb": "wbList",
    "zh": "zhList",
}

KEYWORD_EXPANSION_MAP: dict[str, list[str]] = {
    "体育": ["体育", "足球", "篮球", "运动", "健身", "奥运", "世界杯", "NBA", "CBA", "乒乓球"],
    "娱乐": ["娱乐", "明星", "电影", "电视剧", "综艺", "音乐", "八卦"],
    "科技": ["科技", "互联网", "手机", "电脑", "AI", "人工智能", "数码"],
    "财经": ["财经", "股市", "基金", "理财", "经济", "金融"],
    "社会": ["社会", "民生", "新闻", "热点", "事件"],
    "游戏": ["游戏", "电竞", "网游", "手游", "王者荣耀", "英雄联盟"],
    "汽车": ["汽车", "车", "新能源", "电动车", "特斯拉", "比亚迪"],
    "美食": ["美食", "吃", "餐厅", "菜谱", "做饭"],
    "旅游": ["旅游", "旅行", "景点", "攻略", "酒店"],
    "时尚": ["时尚", "穿搭", "美妆", "护肤", "衣服"],
    "半导体": ["半导体", "芯片", "集成电路", "晶圆", "封测", "存储", "AI芯片"],
    "存储": ["存储", "DDR", "DRAM", "NAND", "闪存", "内存", "SSD"],
    "光通信": ["光通信", "光模块", "CPO", "光纤", "光器件"],
}

GZH_PERSONAL_ACCOUNTS = [
    "好运哥2008", "雷立刚本人", "孥孥的大树", "财经作家雷立刚", "凯恩斯",
    "冷眼局中人", "毛有话说", "EarlETF", "研报号角", "齐俊杰看财经",
    "laoduo", "思哲与创富", "A股研报君", "价值成长", "唐老师笔记",
    "金成探市", "丹湖渔翁", "远行者与碎冰匠", "胡斐投资办公室",
]

GZH_OFFICIAL_ACCOUNTS = [
    "大红好运哥", "央视财经", "华夏基金", "金融时报", "中国基金报",
    "沙黾农", "券商中国", "吴晓波频道", "每日经济新闻", "财联社",
    "投资界", "第一财经", "21世纪经济报道", "ETF进化论", "界面新闻",
    "中国证券报", "证券时报", "中国财经报", "第一财经资讯", "上海证券报",
    "e公司", "腾讯财经", "期货日报", "侯勃说股", "财经",
    "中新经纬", "科奖中心", "天天基金网", "投资作业本Pro", "每财网",
]


def get_api_key(settings: Optional[dict[str, Any]] = None) -> str:
    """Resolve API key: env (configured name) > REDFOX_API_KEY > local json files."""
    cfg = (settings or {}).get("redfox") or {}
    env_name = str(cfg.get("api_key_env") or "REDFOX_API_KEY")
    for name in (env_name, "REDFOX_API_KEY"):
        val = os.environ.get(name, "").strip()
        if val:
            return val
    for config_path in (
        Path.home() / ".agent-reach" / "redfox.json",
        Path.home() / ".qoder" / "apis" / "redfox.json",
    ):
        if not config_path.is_file():
            continue
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            key = str(data.get("api_key") or "").strip()
            if key:
                return key
        except (json.JSONDecodeError, OSError):
            pass
    return ""


def redfox_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = (settings or {}).get("redfox") or {}
    if cfg.get("enabled") is not True:
        return False
    return bool(get_api_key(settings))


def expand_keywords(keyword: str) -> list[str]:
    text = (keyword or "").strip()
    if not text:
        return []
    for big_word, expanded in KEYWORD_EXPANSION_MAP.items():
        if text == big_word or big_word in text:
            return list(expanded)
    if len(text) <= 2:
        return [text]
    return [text]


def _ssl_context(settings: Optional[dict[str, Any]] = None) -> ssl.SSLContext:
    cfg = (settings or {}).get("redfox") or {}
    if cfg.get("insecure_skip_tls_verify") is True:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def _http_post(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    *,
    timeout: int = 20,
    max_retries: int = 2,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
        "User-Agent": "agent-reach-daily-run/1.0",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = "unknown"
    ctx = _ssl_context(settings)

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            code = result.get("code")
            if code in (200, 2000):
                return result
            last_error = f"code={code} msg={result.get('msg', '')}"
            if code == 3108 and attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return {"__error__": last_error, "code": code}
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < max_retries - 1:
            time.sleep(1 + attempt)
    return {"__error__": last_error}


def _article_title(art: dict[str, Any]) -> str:
    for key in (
        "workTitle", "title", "displayTitle", "workDesc", "desc", "summary", "word",
    ):
        val = art.get(key)
        if val:
            return str(val).strip()[:200]
    return ""


def _article_url(art: dict[str, Any], platform: str) -> str:
    for key in ("workUrl", "url", "shareInfoLink"):
        val = art.get(key)
        if val:
            return str(val)
    if platform == "xhs":
        note_id = art.get("workId") or art.get("id") or art.get("noteId")
        if note_id:
            token = art.get("xsecToken", "")
            suffix = f"?xsec_token={token}" if token else ""
            return f"https://www.xiaohongshu.com/explore/{note_id}{suffix}"
    return ""


def _now_shanghai() -> datetime:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Shanghai"))


def fetch_stock_feed(
    keyword: str,
    *,
    platforms: Optional[list[str]] = None,
    days: int = 7,
    api_key: Optional[str] = None,
    timeout: int = 20,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Multi-platform A-share social feed via workSearch API."""
    key = api_key or get_api_key()
    if not key:
        return {"error": "missing_api_key", "items": []}

    plats = platforms or list(PLATFORM_RESULT_KEYS.keys())
    feed_cfg = ((settings or {}).get("redfox") or {}).get("stock_feed") or {}
    count_limit = int(feed_cfg.get("count_per_platform", 50))
    today = _now_shanghai()
    payload = {
        "keyword": keyword,
        "source": STOCK_FEED_SOURCE,
        "startDate": (today - timedelta(days=days)).strftime("%Y-%m-%d"),
        "endDate": today.strftime("%Y-%m-%d"),
    }
    result = _http_post(WORK_SEARCH_URL, payload, key, timeout=timeout, settings=settings)
    if "__error__" in result:
        return {"error": result["__error__"], "items": []}

    data = result.get("data") or {}
    items: list[dict[str, Any]] = []
    for plat in plats:
        if plat not in PLATFORM_RESULT_KEYS:
            continue
        label, result_key = PLATFORM_RESULT_KEYS[plat]
        articles = data.get(result_key, [])
        if isinstance(articles, dict):
            articles = articles.get("articles", [])
        if not isinstance(articles, list):
            continue
        for art in articles[:count_limit]:
            if not isinstance(art, dict):
                continue
            title = _article_title(art)
            if not title:
                continue
            items.append(
                {
                    "platform": plat,
                    "platform_label": label,
                    "title": title,
                    "url": _article_url(art, plat),
                    "author": str(
                        art.get("accountNickname")
                        or art.get("accountName")
                        or art.get("author")
                        or ""
                    )[:60],
                    "keyword": keyword,
                    "source": "redfox_stock_feed",
                }
            )
    return {"keyword": keyword, "items": items, "platforms": plats}


def fetch_trending_hub(
    *,
    source: str = "全平台热点事件",
    platforms: Optional[list[str]] = None,
    keywords: Optional[list[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 20,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Aggregate hot lists from RedFox trending-hub API."""
    key = api_key or get_api_key()
    if not key:
        return {"error": "missing_api_key", "items": []}

    plats = platforms or ["wb", "dy", "zh"]
    platform_enums = [TRENDING_PLATFORM_MAP[p] for p in plats if p in TRENDING_PLATFORM_MAP]
    payload: dict[str, Any] = {
        "source": source,
        "platforms": platform_enums,
        "keywords": keywords or [],
    }
    if start_date:
        payload["startDate"] = start_date
    if end_date:
        payload["endDate"] = end_date

    result = _http_post(HOTSPOT_URL, payload, key, timeout=timeout, settings=settings)
    if "__error__" in result:
        return {"error": result["__error__"], "items": []}

    data = result.get("data") or {}
    items: list[dict[str, Any]] = []
    for plat, list_key in TRENDING_LIST_KEYS.items():
        if plats and plat not in plats:
            continue
        for hotspot in data.get(list_key) or []:
            if not isinstance(hotspot, dict):
                continue
            title = str(hotspot.get("title") or "").strip()
            if not title:
                continue
            items.append(
                {
                    "platform": plat,
                    "platform_label": plat.upper(),
                    "title": title,
                    "url": str(hotspot.get("url") or ""),
                    "hot_value": hotspot.get("hotCount"),
                    "index": hotspot.get("index"),
                    "source": "redfox_trending_hub",
                }
            )
    return {"items": items, "platforms": plats, "keywords": keywords or []}


def fetch_gzh_astock(
    target_date: Optional[str] = None,
    *,
    dual_category: bool = True,
    api_key: Optional[str] = None,
    timeout: int = 20,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fetch A-share WeChat official account posts for a date."""
    key = api_key or get_api_key()
    if not key:
        return {"error": "missing_api_key"}

    ds = target_date or _now_shanghai().strftime("%Y-%m-%d")
    all_authors = list(GZH_PERSONAL_ACCOUNTS) + list(GZH_OFFICIAL_ACCOUNTS)
    payload = {
        "date": ds,
        "accountNames": all_authors,
        "source": GZH_SOURCE,
    }
    result = _http_post(GZH_DAILY_URL, payload, key, timeout=timeout, settings=settings)
    if "__error__" in result:
        return {"error": result["__error__"], "date": ds}

    accounts_raw = (result.get("data") or {}).get("accounts") or []
    personal: list[dict[str, Any]] = []
    official: list[dict[str, Any]] = []

    for acc in accounts_raw:
        if not isinstance(acc, dict):
            continue
        name = str(acc.get("accountName") or "")
        works = acc.get("works") or []
        latest = works[0] if works else None
        entry = {
            "account_name": name,
            "avg_read_count": acc.get("avgReadCount"),
            "redfox_index": acc.get("redfoxIndex"),
            "latest_title": (latest or {}).get("title") if latest else None,
            "latest_url": (latest or {}).get("workUrl") if latest else None,
            "latest_reads": (latest or {}).get("clicksCount") if latest else None,
        }
        if name in GZH_PERSONAL_ACCOUNTS:
            personal.append(entry)
        elif name in GZH_OFFICIAL_ACCOUNTS:
            official.append(entry)

    personal.sort(key=lambda x: float(x.get("avg_read_count") or 0), reverse=True)
    official.sort(key=lambda x: float(x.get("avg_read_count") or 0), reverse=True)

    out: dict[str, Any] = {
        "date": ds,
        "personal": personal,
        "official": official,
    }
    if not dual_category:
        out["accounts"] = personal + official
    return out


def fetch_weibo_search(
    keyword: str,
    *,
    search_type: str = "61",
    page: int = 1,
    api_key: Optional[str] = None,
    timeout: int = 20,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Weibo realtime/hot search via RedFox (searchType 61=实时)."""
    key = api_key or get_api_key(settings)
    if not key:
        return {"error": "missing_api_key", "items": []}
    payload = {
        "searchType": str(search_type),
        "page": str(page),
        "keyword": keyword,
        "extParam": "",
        "source": "agent-reach-daily-run",
    }
    result = _http_post(WEIBO_SEARCH_URL, payload, key, timeout=timeout, settings=settings)
    if "__error__" in result:
        return {"error": result["__error__"], "items": []}

    data = result.get("data") or {}
    if isinstance(data, list):
        articles = data
    elif isinstance(data, dict):
        articles = data.get("workList") or data.get("list") or []
    else:
        articles = []

    items: list[dict[str, Any]] = []
    for art in articles[:20]:
        if not isinstance(art, dict):
            continue
        title = str(
            art.get("text")
            or art.get("caption")
            or art.get("workTitle")
            or art.get("title")
            or ""
        ).strip()
        if not title:
            continue
        items.append(
            {
                "platform": "wb_search",
                "platform_label": "微博搜索",
                "title": title[:200],
                "url": str(art.get("workUrl") or art.get("url") or ""),
                "author": str(art.get("authorName") or art.get("nickname") or ""),
                "keyword": keyword,
                "source": "redfox_weibo_search",
            }
        )
    return {"keyword": keyword, "items": items, "search_type": search_type}
