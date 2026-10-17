"""Private subprocess worker. Only fixed read-only site actions are accepted."""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from agent_reach.runtime.result import ReachError, make_item
from agent_reach.utils.url import host_matches

SITES = {"boss": "https://www.zhipin.com", "xiaohongshu": "https://www.xiaohongshu.com",
         "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com",
         "twitter": "https://x.com", "reddit": "https://www.reddit.com",
         "linkedin": "https://www.linkedin.com"}
CITIES = {"深圳": "101280600", "北京": "101010100", "上海": "101020100", "广州": "101280100",
          "杭州": "101210100", "成都": "101270100", "全国": "100010000"}


def target_url(channel, target):
    host = urlsplit(SITES[channel]).hostname
    parsed = urlsplit(target)
    if not host_matches(target, host or "") or parsed.scheme != "https" or parsed.port not in (None, 443):
        raise ReachError("BAD_INPUT", "Use a direct HTTPS note/job URL on the selected site")
    pattern = (r"/job_detail/[A-Za-z0-9_-]+\.html" if channel == "boss" else
               r"/jobs/view/\d+/?" if channel == "linkedin" else
               r"/(?:explore|search_result)/[A-Za-z0-9_-]+")
    if not re.fullmatch(pattern, parsed.path):
        raise ReachError("BAD_INPUT", "Expected a direct note/job detail URL")
    return target


def search_url(channel, params):
    query = params.get("query", "")
    if not isinstance(query, str) or not query.strip() or len(query) > 300:
        raise ReachError("BAD_INPUT", "query must contain 1..300 characters")
    if channel == "facebook":
        return SITES[channel] + "/search/top?" + urlencode({"q": query})
    if channel == "twitter":
        return SITES[channel] + "/search?" + urlencode({"q": query, "src": "typed_query", "f": "live"})
    if channel == "reddit":
        return SITES[channel] + "/search/?" + urlencode({"q": query, "type": "posts"})
    if channel == "linkedin":
        return SITES[channel] + "/jobs/search/?" + urlencode({"keywords": query,
                                                                 "location": params.get("location") or ""})
    if channel == "xiaohongshu":
        return SITES[channel] + "/search_result?" + urlencode({"keyword": query, "source": "web_explore_feed"})
    if channel == "instagram":
        return SITES[channel] + "/web/search/topsearch/?" + urlencode({"query": query, "context": "user"})
    city = params.get("city") or "全国"
    code = CITIES.get(city, city)
    if not re.fullmatch(r"\d{9}", code):
        raise ReachError("BAD_INPUT", "Use 深圳/北京/上海/广州/杭州/成都/全国 or a 9-digit BOSS city code")
    return SITES[channel] + "/web/geek/jobs?" + urlencode({"query": query, "city": code})


def check_page(page):
    text = page.locator("body").inner_text(timeout=5000)
    path = urlsplit(page.url).path
    if any(marker in path for marker in ("/checkpoint", "/challenge", "/check/china/add-phone")):
        raise ReachError("PLATFORM_BLOCKED", "Site verification requires human intervention")
    if any(marker in path for marker in ("/login", "/authwall", "/i/flow/login")):
        raise ReachError("NEED_LOGIN", "Site login is required")
    if any(s in text for s in ("访问过于频繁", "请求过于频繁")):
        raise ReachError("RATE_LIMITED", "Site rate limit; stop and retry later")
    if any(s in text for s in ("安全验证", "访问异常", "滑动验证", "请完成验证", "滑块验证")):
        raise ReachError("PLATFORM_BLOCKED", "Site verification requires human intervention")
    if any(s in text for s in ("登录/注册", "登录查看完整内容", "扫码登录", "手机号登录")):
        raise ReachError("NEED_LOGIN", "CloakBrowser login expired; explicitly import fresh site cookies")
    if page.locator(".login-container").is_visible():
        raise ReachError("NEED_LOGIN", "Xiaohongshu login dialog is visible")
    return text


def navigate(page, url, selector):
    from playwright.sync_api import TimeoutError as BrowserTimeout
    response = page.goto(url, wait_until="domcontentloaded", timeout=25000)
    if response and response.status == 429:
        raise ReachError("RATE_LIMITED", "Site returned HTTP 429")
    try:
        page.wait_for_selector(selector, timeout=10000)
    except BrowserTimeout:
        check_page(page)
        text = page.locator("body").inner_text()
        if any(s in text for s in ("笔记不存在", "职位已关闭", "内容不存在")):
            raise ReachError("NOT_FOUND", "Content no longer available") from None
        raise ReachError("UPSTREAM_BROKEN", "Expected page content did not appear") from None
    check_page(page)


def search(page, channel, params):
    limit = params.get("limit", 5)
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ReachError("BAD_INPUT", "limit must be between 1 and 100")
    selector = ({"boss": ".job-card-wrap", "twitter": 'article[data-testid="tweet"]',
                 "reddit": 'a[href*="/comments/"]',
                 "linkedin": 'a[href*="/jobs/view/"]'}).get(channel, "section.note-item")
    navigate(page, search_url(channel, params), selector)
    for _ in range(6):
        count = page.locator(selector).count()
        if count >= limit:
            break
        page.locator(selector).last.scroll_into_view_if_needed()
        page.mouse.wheel(0, 1400)
        page.wait_for_timeout(1200)
        check_page(page)
        if page.locator(selector).count() == count:
            break
    if channel == "twitter":
        rows = page.locator(selector).evaluate_all('''els => els.map(e => ({
            title:e.querySelector('[data-testid="tweetText"]')?.innerText,
            url:e.querySelector('a[href*="/status/"]')?.href
        })).filter(x => x.title && x.url)''')
    elif channel in {"reddit", "linkedin"}:
        rows = page.locator(selector).evaluate_all('''els => els.map(e => ({
            title:e.innerText?.trim(), url:e.href
        })).filter(x => x.title && x.url)''')
    elif channel == "boss":
        rows = page.locator(selector).evaluate_all('''els => els.map(e => ({
            title:e.querySelector('.job-name')?.innerText,
            url:e.querySelector('.job-name')?.href,
            author:e.querySelector('.boss-name')?.innerText,
            salary:e.querySelector('.job-salary')?.innerText,
            location:e.querySelector('.company-location')?.innerText,
            requirements:e.querySelector('.tag-list')?.innerText
        }))''')
    else:
        rows = page.locator(selector).evaluate_all('''els => els.map(e => ({
            title:e.querySelector('.title')?.innerText,
            url:e.querySelector('a.cover')?.href,
            author:e.querySelector('.author .name')?.innerText
        }))''')
    items, seen = [], set()
    for row in rows:
        if not row.get("url") or not row.get("title") or row["url"] in seen:
            continue
        seen.add(row["url"])
        if channel in {"twitter", "reddit", "linkedin"}:
            host = {"twitter": "x.com", "reddit": "reddit.com", "linkedin": "linkedin.com"}[channel]
            if not host_matches(row["url"], host):
                continue
            text = row["title"]
        elif channel == "boss":
            salary = row.get("salary") or ""
            # Never guess dynamically encoded font glyphs as salary digits.
            if any(0xE000 <= ord(c) <= 0xF8FF for c in salary):
                row["salary_encoded"] = True
                row["salary"] = None
            text = " · ".join(row[k] for k in ("salary", "location", "requirements") if row.get(k))
        else:
            text = None
        row["content_scope"] = "search_card"
        items.append(make_item(title=row["title"], url=row["url"], author=row.get("author"), text=text, raw=row))
    if not items:
        raise ReachError("UPSTREAM_BROKEN", "Cards loaded but no valid results could be extracted")
    return items[:limit]


def read(page, channel, target):
    url = target_url(channel, target)
    selector = (".job-sec-text" if channel == "boss" else
                "main"
                if channel == "linkedin" else "#detail-desc")
    navigate(page, url, selector)
    if channel == "linkedin":
        from playwright.sync_api import TimeoutError as BrowserTimeout

        try:
            page.wait_for_function("""() => {
                const text = document.querySelector('main')?.innerText || '';
                return text.includes('关于职位') || text.includes('About the job');
            }""", timeout=12000)
        except BrowserTimeout:
            check_page(page)
            raise ReachError("UPSTREAM_BROKEN", "LinkedIn job description did not load") from None
    raw: dict = {}
    if channel == "boss":
        title = page.locator(".job-banner h1").inner_text()
        header = page.locator(".job-banner").inner_text()
        match = re.search(r"\d+(?:\.\d+)?-\d+(?:\.\d+)?K(?:·\d+薪)?", header)
        raw = {"salary": match.group() if match else None, "content_scope": "job_description"}
    elif channel == "linkedin":
        title = page.title().split(" | ")[0]
        raw = {"content_scope": "job_description"}
    else:
        title = page.locator("#detail-title").inner_text() if page.locator("#detail-title").count() else page.title()
        raw = {"content_scope": "description_only", "images_read": False, "video_read": False}
    text = "\n\n".join(page.locator(selector).all_inner_texts())
    if channel == "linkedin":
        marker = next((m for m in ("关于职位", "About the job") if m in text), None)
        if marker is None:
            raise ReachError("UPSTREAM_BROKEN", "LinkedIn job description did not appear")
        text = text.split(marker, 1)[1].split("关于公司", 1)[0].split("About the company", 1)[0][:12000]
    if not text.strip():
        raise ReachError("UPSTREAM_BROKEN", "Detail page returned an empty description")
    return [make_item(title=title, url=url, text=text, raw=raw)]


def execute(request):
    from cloakbrowser import launch_persistent_context
    from cloakbrowser.config import PLATFORM_CHROMIUM_VERSIONS, get_binary_path, get_platform_tag
    channel, action = request["channel"], request["action"]
    allowed = {"search", "profile", "posts", "import", "login"} if channel == "instagram" else {"search", "read", "import", "login"}
    if channel in {"facebook", "twitter", "reddit"}:
        allowed = {"search", "import", "login"}
    if channel == "linkedin":
        allowed = {"jobs", "read", "import", "login"}
    if channel not in SITES or action not in allowed:
        raise ReachError("BAD_INPUT", "Unsupported CloakBrowser action")
    if channel == "instagram" and action != "login":
        from agent_reach.backends.instagram_cloak import validate
        validate(action, request)
    # Validate user input before opening a browser.
    if action == "read":
        target_url(channel, request["target"])
    elif action in {"search", "jobs"}:
        search_url(channel, request)
        limit = request.get("limit", 5)
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ReachError("BAD_INPUT", "limit must be between 1 and 100")
    # Pin the SDK's platform build. Query execution never downloads/upgrades a binary.
    version = PLATFORM_CHROMIUM_VERSIONS[get_platform_tag()]
    binary = get_binary_path(version)
    if not binary.is_file():
        raise ReachError("NEED_SETUP", "CloakBrowser binary missing; run agent-reach cloak setup")
    os.environ['CLOAKBROWSER_BINARY_PATH'] = str(binary)
    os.environ['CLOAKBROWSER_LICENSE_KEY'] = ''
    ctx = launch_persistent_context(request["profile"], headless=(action != "login"), browser_version=version,
                                    locale="zh-CN", proxy=os.environ.get("REACH_CLOAK_PROXY") or None)
    try:
        # All pages here belong to the Reach-owned profile, never the source Chrome.
        old_pages = list(ctx.pages)
        page = ctx.new_page()
        # Keep a tab alive: closing the last headed tab exits Chromium.
        for old in old_pages:
            old.close()
        if action == "login":
            from playwright.sync_api import Error as PlaywrightError
            try:
                page.goto(SITES[channel], wait_until="domcontentloaded", timeout=30000)
            except PlaywrightError as exc:
                if type(exc).__name__ != "TimeoutError":
                    raise
                # A slow page can still be completed manually in the visible window.
            print("Complete login yourself, then close this Cloak browser window to save the session.", file=sys.stderr)
            try:
                while ctx.pages:
                    ctx.pages[0].wait_for_timeout(500)
            except PlaywrightError as exc:
                if type(exc).__name__ != "TargetClosedError":
                    raise
            return [{"session_saved": True, "identity_verified": False}]
        if action == "import":
            cookies = json.loads(Path(request["cookie_file"]).read_text())
            from agent_reach.backends.cloak import DOMAINS
            domain = DOMAINS[channel]
            ctx.clear_cookies(domain=re.compile(r"(^|\.)" + re.escape(domain) + r"$"))
            ctx.add_cookies(cookies)
            params = {"query": "数据平台" if channel == "boss" else "VLA", "limit": 1}
            if channel == "facebook":
                from agent_reach.backends.facebook_cloak import search as facebook_search
                facebook_search(page, "OpenAI", 1)
            elif channel == "instagram":
                from agent_reach.backends.instagram_cloak import execute as instagram_execute
                instagram_execute(page, "profile", {"username": "nasa"})
            else:
                if channel == "twitter":
                    params["query"] = "OpenAI"
                elif channel == "reddit":
                    params["query"] = "python"
                elif channel == "linkedin":
                    params["query"] = "data engineer"
                search(page, channel, params)
            return [{"access_verified": True, "scope": "search", "identity_verified": False}]
        if channel == "facebook":
            from agent_reach.backends.facebook_cloak import search as facebook_search
            return facebook_search(page, request["query"], request.get("limit", 5))
        if channel == "instagram":
            from agent_reach.backends.instagram_cloak import execute as instagram_execute
            return instagram_execute(page, action, request)
        if action in {"search", "jobs"}:
            return search(page, channel, request)
        return read(page, channel, request["target"])
    finally:
        ctx.close()


def main():
    os.umask(0o077)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            items = execute(json.loads(sys.argv[1]))
        result = {"items": items}
    except ReachError as exc:
        result = {"error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:
        # Browser exceptions may contain signed URLs, page contents or cookies.
        code = "TIMEOUT" if type(exc).__name__ == "TimeoutError" else "UPSTREAM_BROKEN"
        result = {"error": {"code": code, "message": f"CloakBrowser worker failed ({type(exc).__name__})"}}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
