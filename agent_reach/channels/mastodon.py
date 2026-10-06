# -*- coding: utf-8 -*-
"""Mastodon — public API channel for accounts, statuses, and federated account search.

Mastodon is federated: always query the account's HOME instance (a remote
instance's copy of an account is incomplete). Public endpoints need no login;
an optional `mastodon_token` (env `MASTODON_TOKEN`, read scope) unlocks
fuzzy federated account search via /api/v2/search. Read-only — never performs
write actions.
"""

import ipaddress
import json
import re
import shutil
import ssl
import subprocess
import time
import urllib.request
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from agent_reach.utils.process import utf8_subprocess_env
from agent_reach.utils.text import scrub_url_credentials
from agent_reach.utils.url import normalize_public_http_url

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 1024 * 1024
_DEFAULT_INSTANCE = "mastodon.social"
_PAGE_SLEEP = 1.5  # seconds between paginated requests (politeness)

# Common instances for can_handle() only — NOT an API allowlist. can_handle
# must not path-match bare "/@user" URLs: YouTube and Medium use the same
# shape. Accounts on other instances are reached via the "@user@instance"
# handle form instead.
_KNOWN_INSTANCES = frozenset(
    {
        "fosstodon.org",
        "hachyderm.io",
        "indieweb.social",
        "infosec.exchange",
        "journa.host",
        "mas.to",
        "mastodon.online",
        "mastodon.social",
        "mathstodon.xyz",
        "mstdn.social",
        "scicomm.xyz",
        "techhub.social",
    }
)

# https://<instance>/@user · https://<instance>/@user@remote · .../@user/<status id>
_FEDIVERSE_URL_RE = re.compile(
    r"^https?://(?P<host>[^/@:\s]+)(?::\d+)?"
    r"/@(?P<user>[A-Za-z0-9_.]+)"
    r"(?:@(?P<remote>[A-Za-z0-9_.]+))?"
    r"(?:/(?P<sid>\d+))?"
    r"(?:/.*)?$",
    re.IGNORECASE,
)
_FULL_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.]+@[A-Za-z0-9_.]+$")


class _Text(HTMLParser):
    """Minimal HTML -> text (Mastodon status content is HTML)."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag == "p":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def strip_html(s: str) -> str:
    """Convert Mastodon's HTML status/note fields to plain text."""
    parser = _Text()
    parser.feed(s or "")
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def parse_handle(arg: str) -> tuple[str, str]:
    """Resolve '@user@instance' / 'user@instance' / 'https://inst/@user' to (user, instance)."""
    text = str(arg or "").strip()
    m = _FEDIVERSE_URL_RE.match(text)
    if m:
        return m.group("user"), (m.group("remote") or m.group("host")).lower()
    handle = text.lstrip("@")
    if (
        "://" in handle
        or any(ch.isspace() for ch in handle)
        or handle.count("@") != 1
    ):
        raise ValueError(f"invalid Mastodon handle: {arg!r} (expected @user@instance)")
    user, _, instance = handle.partition("@")
    if not user or not instance:
        raise ValueError(f"invalid Mastodon handle: {arg!r} (expected @user@instance)")
    return user, instance.lower()


def _parse_status_url(url: str) -> tuple[str, str]:
    """'https://inst/@user[ @remote]/<id>' -> (home_instance, status_id)."""
    m = _FEDIVERSE_URL_RE.match(str(url or "").strip())
    if not m or not m.group("sid"):
        raise ValueError(
            f"invalid Mastodon status URL: {url!r} (expected https://<instance>/@<user>/<id>)"
        )
    # A "/@user@remote/<id>" path points at a remote account — fetch from its home instance.
    return (m.group("remote") or m.group("host")).lower(), m.group("sid")


def _mastodon_url(instance: str, path: str, **params: Any) -> str:
    """Build an instance API URL; `instance` may be a bare domain or an https URL."""
    host = str(instance or "").strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
            break
    host = host.split("/", 1)[0].lower()
    query = urlencode({k: v for k, v in params.items() if v is not None})
    url = f"https://{host}{path}"
    return f"{url}?{query}" if query else url


def _validate_api_url(url: str) -> None:
    """Allow only public instance HTTPS JSON APIs.

    Instance domains come from user input, so this is stricter than V2EX's
    pinned-host check: reject userinfo, non-HTTPS, odd ports, IP literals,
    and any non-/api/ path (normalize_public_http_url also blocks localhost
    and internal/private hosts).
    """
    try:
        normalized = normalize_public_http_url(url)
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Mastodon API URL") from exc
    try:
        literal_ip = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        literal_ip = None
    if (
        parsed.scheme.lower() != "https"
        or port not in {None, 443}
        or literal_ip is not None
        or not parsed.path.startswith("/api/")
    ):
        raise ValueError("only public Mastodon instance HTTPS APIs are allowed")


def _get_json_with_urllib(url: str, token: str = "") -> Any:
    """Fetch JSON with Python's standard HTTP stack."""
    _validate_api_url(url)
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("Mastodon API response exceeds the 1 MiB safety limit")
    return json.loads(raw.decode("utf-8"))


def _is_unexpected_tls_eof(error: BaseException) -> bool:
    """Return whether an exception chain contains the retryable TLS EOF."""
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ssl.SSLError) and not isinstance(
            current, ssl.SSLCertVerificationError
        ):
            text = str(current).casefold()
            if (
                "unexpected_eof_while_reading" in text
                or "eof occurred in violation of protocol" in text
            ):
                return True
        for nested in (
            getattr(current, "reason", None),
            current.__cause__,
            current.__context__,
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


def _get_json_with_curl(url: str, token: str = "") -> Any:
    """Fetch bounded JSON with the OS curl TLS stack."""
    _validate_api_url(url)
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is unavailable for the Mastodon TLS fallback")

    command = [
        curl,
        "--fail",
        "--silent",
        "--show-error",
        "--proto",
        "=https",
        "--connect-timeout",
        "5",
        "--max-time",
        str(_TIMEOUT),
        "--max-filesize",
        str(_MAX_RESPONSE_BYTES),
        "--header",
        f"User-Agent: {_UA}",
    ]
    if token:
        command += ["--header", f"Authorization: Bearer {token}"]
    command += ["--url", url]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT + 2,
            env=utf8_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("curl could not complete the Mastodon TLS fallback") from exc
    if result.returncode != 0:
        raise RuntimeError("curl could not complete the Mastodon TLS fallback")
    if len(result.stdout.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        raise ValueError("Mastodon API response exceeds the 1 MiB safety limit")
    return json.loads(result.stdout)


def _get_json(url: str, token: str = "") -> Any:
    """Fetch JSON, retrying only Python's known TLS EOF via native curl."""
    try:
        return _get_json_with_urllib(url, token)
    except Exception as exc:
        if isinstance(exc, ssl.SSLCertVerificationError):
            raise
        if not _is_unexpected_tls_eof(exc):
            raise
        return _get_json_with_curl(url, token)


def _mastodon_token(config=None) -> str:
    """Optional token: config key `mastodon_token` / env `MASTODON_TOKEN`. Never raises."""
    try:
        from ..config import Config

        cfg = config if config is not None else Config(read_only=True)
        return str(cfg.get("mastodon_token") or "")
    except Exception:
        return ""


def _account_payload(account: dict, instance: str) -> dict:
    acct = account.get("acct", "")
    if acct and "@" not in acct:
        acct = f"{acct}@{instance}"
    return {
        "id": account.get("id", ""),
        "handle": acct,
        "display_name": account.get("display_name", ""),
        "url": account.get("url", ""),
        "bio": strip_html(account.get("note") or ""),
        "followers": account.get("followers_count", 0),
        "following": account.get("following_count", 0),
        "statuses_count": account.get("statuses_count", 0),
        "created": (account.get("created_at") or "")[:10],
        "instance": instance,
        "avatar": account.get("avatar", ""),
    }


def _status_payload(status: dict, instance: str) -> dict:
    """Map a Mastodon status (or reblog wrapper) to a plain dict."""
    reblog = status.get("reblog")
    source = reblog or status
    author = source.get("account") or {}
    author_acct = author.get("acct", "")
    if author_acct and "@" not in author_acct:
        author_acct = f"{author_acct}@{instance}"
    return {
        "id": status.get("id", ""),
        "date": (status.get("created_at") or "")[:10],
        "kind": "repost" if reblog else "post",
        "author": author_acct,
        "author_display": author.get("display_name", ""),
        "url": source.get("url", "") or status.get("url", ""),
        "content": strip_html(source.get("content") or ""),
        "favourites": status.get("favourites_count", 0),
        "reblogs": status.get("reblogs_count", 0),
        "replies": status.get("replies_count", 0),
    }


class MastodonChannel(Channel):
    name = "mastodon"
    description = "Mastodon（联邦宇宙）账号资料与帖子"
    backends = ["Mastodon API (public)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        # Domain allowlist only — no network, no bare "/@user" path matching
        # (YouTube and Medium use that shape too).
        from agent_reach.utils.url import host_matches

        return host_matches(url, *_KNOWN_INSTANCES)

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        token = _mastodon_token(config)
        try:
            _get_json(_mastodon_url(_DEFAULT_INSTANCE, "/api/v1/instance"), token)
            self.active_backend = self.backends[0]
            message = "公开 API 可用（账号资料、用户帖子、单条帖子）"
            if token:
                message += "；检测到 MASTODON_TOKEN，联邦账号搜索可用"
            else:
                message += "；联邦账号搜索可选配置 MASTODON_TOKEN"
            return "ok", message
        except Exception as e:
            self.active_backend = None
            return (
                "warn",
                f"Mastodon API 连接失败（可能需要代理）：{scrub_url_credentials(e)}",
            )

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def lookup_account(self, handle: str, config=None) -> dict:
        """解析账号资料（在账号所在实例上查询）。

        Args:
            handle: "@user@instance" / "user@instance" / "https://instance/@user"

        Returns a dict with keys:
          id, handle, display_name, url, bio, followers, following,
          statuses_count, created, instance, avatar
        """
        user, instance = parse_handle(handle)
        data = _get_json(
            _mastodon_url(instance, "/api/v1/accounts/lookup", acct=f"{user}@{instance}"),
            _mastodon_token(config),
        )
        return _account_payload(data, instance)

    def get_statuses(
        self,
        handle: str,
        limit: int = 40,
        exclude_replies: bool = True,
        config=None,
    ) -> list:
        """拉取账号的公开帖子（最新在前，自动翻页）。

        Args:
            handle:          "@user@instance" 等形式
            limit:           最多返回条数（跨页累计）
            exclude_replies: 是否排除回复（默认排除，只看原创帖）

        Returns a list of dicts with keys:
          id, date, kind (post/repost), author, author_display, url,
          content, favourites, reblogs, replies
        """
        user, instance = parse_handle(handle)
        token = _mastodon_token(config)
        account = _get_json(
            _mastodon_url(instance, "/api/v1/accounts/lookup", acct=f"{user}@{instance}"),
            token,
        )
        account_id = quote(str(account.get("id", "")), safe="")
        results: list[dict] = []
        max_id: str | None = None
        while len(results) < limit:
            page_size = min(40, limit - len(results))
            params: dict[str, Any] = {"limit": page_size}
            if max_id is not None:
                params["max_id"] = max_id
            if exclude_replies:
                params["exclude_replies"] = "true"
            batch = _get_json(
                _mastodon_url(instance, f"/api/v1/accounts/{account_id}/statuses", **params),
                token,
            )
            if not batch:
                break
            results.extend(_status_payload(s, instance) for s in batch)
            if len(batch) < page_size:
                break
            max_id = str(batch[-1]["id"])
            if len(results) < limit:
                time.sleep(_PAGE_SLEEP)
        return results[:limit]

    def get_status(self, url: str, config=None) -> dict:
        """获取单条帖子全文。

        Args:
            url: 帖子 URL，如 https://mastodon.social/@user/1234567
                 （/@user@remote/<id> 形式会自动改查该账号的home实例）

        Returns a dict with keys:
          id, date, kind, author, author_display, url, content,
          favourites, reblogs, replies
        """
        instance, status_id = _parse_status_url(url)
        data = _get_json(
            _mastodon_url(instance, f"/api/v1/statuses/{quote(str(status_id), safe='')}"),
            _mastodon_token(config),
        )
        return _status_payload(data, instance)

    def search(
        self,
        query: str,
        instance: str = _DEFAULT_INSTANCE,
        limit: int = 10,
        config=None,
    ) -> list:
        """按名字模糊搜索联邦账号（需要 MASTODON_TOKEN）。

        无 token 时降级：查询是精确 handle（@user@instance）仍走公开 lookup；
        模糊查询返回包含 {"error": ...} 的列表并提示如何配置。

        Returns:
            list of account dicts (keys 同 lookup_account)；
            失败/未配置时返回包含单条 {"error": str} 的列表。
        """
        query = str(query or "").strip()
        if not query:
            return [{"error": "搜索词为空。请给出要搜索的账号名或 @user@instance 形式的 handle。"}]
        token = _mastodon_token(config)
        if token:
            data = _get_json(
                _mastodon_url(
                    instance, "/api/v2/search", q=query, type="accounts", limit=limit
                ),
                token,
            )
            return [_account_payload(a, instance) for a in (data.get("accounts") or [])]
        # No token: degrade to exact-handle lookup on the handle's home instance.
        if _FULL_HANDLE_RE.match(query.lstrip("@")):
            return [self.lookup_account(query, config=config)]
        lookup_example = f"@user@{instance}"
        return [
            {
                "error": (
                    "联邦账号搜索需要 MASTODON_TOKEN"
                    "（任意实例网页端 Preferences → Development → New Application，"
                    "勾选 read 即可）。无 token 时仍支持精确 handle 查询，"
                    f"例如 search(\"{lookup_example}\")，"
                    f"或直接 curl https://{instance}/api/v1/accounts/lookup?acct={lookup_example.lstrip('@')}"
                )
            }
        ]

    def read(self, url: str, config=None) -> dict:
        """读取 Mastodon URL：帖子 URL 返回单帖，主页 URL 返回账号+最近帖子。

        Returns:
            帖子 URL（/@user/<id>）→ 单条帖子 dict；
            主页 URL（/@user）→ {"account": ..., "recent_statuses": [...]}
        """
        text = str(url or "").strip()
        m = _FEDIVERSE_URL_RE.match(text)
        if not m:
            raise ValueError(
                f"invalid Mastodon URL: {url!r} (expected https://<instance>/@<user>[/<id>])"
            )
        if m.group("sid"):
            return self.get_status(text, config=config)
        handle = f"{m.group('user')}@{(m.group('remote') or m.group('host')).lower()}"
        return {
            "account": self.lookup_account(handle, config=config),
            "recent_statuses": self.get_statuses(handle, limit=10, config=config),
        }
