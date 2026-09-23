"""NGA: read posts through OpenCLI's public Chrome browser commands."""

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from ._opencli_site import OpenCLISiteChannel

HOSTS = {"bbs.nga.cn", "nga.178.com", "ngabbs.com"}
EXTRACT_SCRIPT = Path(__file__).with_name("_nga_extract.js").read_text(encoding="utf-8")


def thread_url(url: str, page: int | None = None) -> str:
    """Canonicalize only full-thread NGA read URLs, rejecting filtered views."""
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (parsed.scheme not in {"https", "http"} or parsed.hostname not in HOSTS
            or parsed.username or parsed.password or parsed.port not in {None, 80, 443}
            or parsed.path != "/read.php"):
        raise ValueError("需要 NGA 的 read.php?tid=数字 帖子链接")
    if set(query) - {"tid", "page"}:
        raise ValueError("请使用完整主题链接，仅保留 tid 和 page 参数（不要使用筛选视图）")
    if any(len(values) != 1 for values in query.values()):
        raise ValueError("链接含重复参数")
    tid = query.get("tid", [""])[0]
    if not re.fullmatch(r"[1-9][0-9]*", tid):
        raise ValueError("帖子 tid 必须为正整数")
    raw_page = query.get("page", ["1"])[0]
    if not re.fullmatch(r"[1-9][0-9]*", raw_page):
        raise ValueError("page 必须为正整数")
    page = int(raw_page) if page is None else page
    if type(page) is not int or page < 1:
        raise ValueError("page 必须为正整数")
    return urlunsplit(("https", parsed.hostname, "/read.php",
                       urlencode({"tid": tid, "page": page}), ""))


def validate_page(data: dict, url: str) -> dict:
    """Reject login/challenge pages, wrong navigation, and incomplete DOM output."""
    expected = thread_url(url)
    query = parse_qs(urlsplit(expected).query)
    if not isinstance(data, dict) or thread_url(data.get("url", "")) != expected:
        raise ValueError("NGA 返回了不同页面，可能需要登录或验证；未记录为成功")
    page = int(query["page"][0])
    if (data.get("tid") != query["tid"][0] or data.get("page") != page
            or type(data.get("total_pages")) is not int or data["total_pages"] < page
            or not isinstance(data.get("title"), str) or not data["title"]):
        raise ValueError("NGA 页面元信息不完整")
    posts = data.get("posts")
    if not isinstance(posts, list) or not posts:
        raise ValueError("未读取到 NGA 正文；请检查登录、访问权限或验证码")
    for post in posts:
        if (not isinstance(post, dict) or not post.get("content_present")
                or not isinstance(post.get("pid"), str) or not post["pid"].isdigit()
                or type(post.get("floor")) is not int or post["floor"] < 0
                or not isinstance(post.get("author_uid"), str) or not post["author_uid"]
                or not isinstance(post.get("author"), str)
                or not isinstance(post.get("created_at"), str) or not post["created_at"]
                or not isinstance(post.get("edited"), str)
                or not isinstance(post.get("text"), str)
                or not isinstance(post.get("images"), list)
                or not isinstance(post.get("links"), list)):
            raise ValueError("NGA 楼层内容尚未完整加载；未记录为成功")
        for item in post["images"] + post["links"]:
            if (not isinstance(item, dict) or not isinstance(item.get("url"), str)
                    or not isinstance(item.get("alt", ""), str)
                    or not isinstance(item.get("text", ""), str)):
                raise ValueError("NGA 图片或链接数据不完整")
    return data


class NGABrowser:
    """One owned tab lease per export, with no Cookie extraction or browser restart."""

    def __init__(self, profile: str | None = None, timeout: int = 45):
        self.profile = profile
        self.timeout = timeout
        self.session = "agent-reach-nga-" + uuid.uuid4().hex[:12]
        self.started = False

    def _run(self, *args: str) -> str:
        binary = shutil.which("opencli")
        if not binary:
            raise RuntimeError("未安装 OpenCLI；运行 agent-reach install --system --channels nga")
        cmd = [binary]
        if self.profile:
            cmd += ["--profile", self.profile]
        cmd += ["browser", self.session, *args]
        env = os.environ.copy()
        env.pop("OPENCLI_DAEMON_PORT", None)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                    timeout=self.timeout, env=env)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("OpenCLI 超时；请检查 Chrome 和扩展连接后续传") from exc
        if result.returncode:
            # Do not echo upstream output, which can contain browser/account data.
            raise RuntimeError(f"OpenCLI {args[0]} 失败；运行 opencli doctor 检查扩展连接，"
                               "并确认所选 Chrome 配置中能打开该帖")
        return result.stdout.strip()

    def read_page(self, url: str) -> dict:
        url = thread_url(url)
        self.started = True
        self._run("open", url, "--window", "background")
        self._run("wait", "selector", ".postcontent", "--timeout", "20000")
        try:
            data = json.loads(self._run("eval", EXTRACT_SCRIPT))
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenCLI 没有返回有效的 NGA JSON 数据") from exc
        return validate_page(data, url)

    def close(self) -> None:
        if self.started:
            try:
                self._run("close")
            except (OSError, RuntimeError):
                pass  # Keep the original read error; the owned lease also expires upstream.
            self.started = False


class NGAChannel(OpenCLISiteChannel):
    name = "nga"
    description = "NGA 论坛"
    site = "nga"
    domains = tuple(sorted(HOSTS))
    login_hint = "bbs.nga.cn"
    usage = "agent-reach nga read URL --all-pages --only-author"

    def can_handle(self, url: str) -> bool:
        try:
            thread_url(url)
            return True
        except (ValueError, TypeError):
            return False

    def read(self, url: str, *, profile: str | None = None) -> dict:
        """Read one page. Multi-page export/checkpoints live in nga_export."""
        browser = NGABrowser(profile=profile)
        try:
            data = browser.read_page(url)
            self.active_backend = "OpenCLI"
            return data
        finally:
            browser.close()

    def search(self, query: str):
        raise NotImplementedError("NGA 首版支持按帖子链接读取，暂不支持站内搜索")
