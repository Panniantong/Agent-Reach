# -*- coding: utf-8 -*-
"""
Agent Reach MCP Server — expose doctor/status, search, and read as MCP tools.

Run: python -m agent_reach.integrations.mcp_server

Agent Reach is an installer + doctor tool. The `search` and `read` tools
below do NOT reimplement any platform logic — they route to the same
upstream CLIs documented in the skill (twitter-cli, yt-dlp, opencli,
bili-cli, gh, mcporter, Jina Reader), exactly as an agent with shell
access would call them. This lets MCP-only agents (e.g. Claude Desktop /
Cowork) use Agent Reach without a shell on this machine.

Tools:
  - get_status         → agent-reach doctor report
  - search(query, platform, limit)
  - read(url)          → routes by channel `can_handle()`, falls back to
                         Jina Reader for generic web pages
"""

import asyncio
import json
import subprocess
import sys
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from agent_reach.channels import ALL_CHANNELS
from agent_reach.config import Config
from agent_reach.core import AgentReach

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

# Platforms exposed by the `search` tool. Commands mirror SKILL.md —
# zero-config first, login-required platforms surface doctor hints on failure.
SEARCH_PLATFORMS = (
    "web", "twitter", "reddit", "instagram", "tiktok", "xiaohongshu",
    "bilibili", "github", "youtube",
)

_DEFAULT_TIMEOUT = 60
_MCPORTER_TIMEOUT = 120

# Max characters returned to the MCP client per call (protects context windows).
MAX_OUTPUT_CHARS = 20000

# OpenCLI fallbacks (browser login state) used when the preferred CLI for a
# platform is not installed — mirrors doctor's multi-backend routing.
OPENCLI_SEARCH_FALLBACKS = {
    "twitter": lambda q, n: ["opencli", "twitter", "search", q, "-f", "yaml"],
    "bilibili": lambda q, n: ["opencli", "bilibili", "search", q, "-f", "yaml"],
}

OPENCLI_READ_FALLBACKS = {
    "twitter": lambda url: ["opencli", "twitter", "article", url, "-f", "yaml"],
    "bilibili": lambda url: ["opencli", "bilibili", "video", url, "-f", "yaml"],
}


def build_search_command(platform: str, query: str, limit: int = 5) -> Tuple[List[str], int]:
    """Return (argv, timeout_seconds) for a platform search.

    Pure function — no side effects — so routing is unit-testable without
    the upstream tools installed. Raises ValueError for unknown platforms.
    """
    limit = max(1, min(int(limit), 50))
    if platform == "web":
        escaped = query.replace('"', '\\"')
        call = f'exa.web_search_exa(query: "{escaped}", numResults: {limit})'
        return (["mcporter", "call", call], _MCPORTER_TIMEOUT)
    if platform == "twitter":
        return (["twitter", "search", query, "-n", str(limit)], _DEFAULT_TIMEOUT)
    if platform == "reddit":
        return (["opencli", "reddit", "search", query, "-f", "yaml"], _DEFAULT_TIMEOUT)
    if platform == "instagram":
        return (["opencli", "instagram", "search", query, "-f", "yaml"], _DEFAULT_TIMEOUT)
    if platform == "tiktok":
        return (["opencli", "tiktok", "search", query, "--limit", str(limit),
                 "-f", "yaml"], _DEFAULT_TIMEOUT)
    if platform == "xiaohongshu":
        return (["opencli", "xiaohongshu", "search", query, "-f", "yaml"], _DEFAULT_TIMEOUT)
    if platform == "bilibili":
        return (["bili", "search", query, "--type", "video", "-n", str(limit)], _DEFAULT_TIMEOUT)
    if platform == "github":
        return (["gh", "search", "repos", query, "--sort", "stars", "--limit", str(limit)],
                _DEFAULT_TIMEOUT)
    if platform == "youtube":
        return (["yt-dlp", "--flat-playlist", "-J", f"ytsearch{limit}:{query}"],
                _DEFAULT_TIMEOUT)
    raise ValueError(
        f"Unknown platform '{platform}'. Supported: {', '.join(SEARCH_PLATFORMS)}"
    )


def detect_platform(url: str) -> str:
    """Map a URL to a channel name via the channel registry's can_handle()."""
    for ch in ALL_CHANNELS:
        try:
            if ch.name != "web" and ch.can_handle(url):
                return ch.name
        except Exception:
            continue
    return "web"


def _extract_reddit_post_id(url: str) -> Optional[str]:
    # e.g. https://www.reddit.com/r/sub/comments/abc123/title/
    parts = [p for p in url.split("/") if p]
    if "comments" in parts:
        idx = parts.index("comments")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


#: Instagram URL path prefixes that are not profiles (posts, reels, etc.).
_IG_NON_PROFILE_PATHS = {
    "p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct",
}


def _extract_instagram_username(url: str) -> Optional[str]:
    """Return the username for an Instagram profile URL, else None.

    Post/reel/story URLs return None so they fall through to Jina Reader —
    OpenCLI's instagram command reads profiles and user posts, not permalinks.
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    first = path.split("/")[0].split("?")[0]
    if not first or first.lower() in _IG_NON_PROFILE_PATHS:
        return None
    return first


def _extract_tiktok_username(url: str) -> Optional[str]:
    """Return the username for a TikTok profile URL, else None.

    Video permalinks (/@user/video/<id>) return None: OpenCLI's tiktok
    adapter reads profiles and user video lists, not single videos.
    """
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts or not parts[0].startswith("@"):
        return None
    if len(parts) > 1:  # /@user/video/<id>, /@user/live, …
        return None
    username = parts[0][1:].split("?")[0]
    return username or None


def _extract_bilibili_bvid(url: str) -> Optional[str]:
    for part in url.split("/"):
        cleaned = part.split("?")[0]
        if cleaned.startswith("BV"):
            return cleaned
    return None


def build_read_command(url: str) -> Tuple[str, List[str], int]:
    """Return (platform, argv, timeout_seconds) for reading a URL.

    Routes by channel registry; anything unrecognized (or with no CLI
    read path) falls back to Jina Reader, per SKILL.md.
    """
    platform = detect_platform(url)
    if platform == "twitter":
        return (platform, ["twitter", "tweet", url], _DEFAULT_TIMEOUT)
    if platform == "reddit":
        post_id = _extract_reddit_post_id(url)
        if post_id:
            return (platform, ["opencli", "reddit", "read", post_id, "-f", "yaml"],
                    _DEFAULT_TIMEOUT)
    if platform == "instagram":
        username = _extract_instagram_username(url)
        if username:
            return (platform, ["opencli", "instagram", "profile", username, "-f", "yaml"],
                    _DEFAULT_TIMEOUT)
    if platform == "tiktok":
        username = _extract_tiktok_username(url)
        if username:
            return (platform, ["opencli", "tiktok", "profile", username, "-f", "yaml"],
                    _DEFAULT_TIMEOUT)
    if platform == "xiaohongshu":
        return (platform, ["opencli", "xiaohongshu", "note", url, "-f", "yaml"],
                _DEFAULT_TIMEOUT)
    if platform == "bilibili":
        bvid = _extract_bilibili_bvid(url)
        if bvid:
            return (platform, ["bili", "video", bvid], _DEFAULT_TIMEOUT)
    if platform == "youtube":
        return (platform, ["yt-dlp", "--skip-download", "--no-warnings", "-J", url],
                _DEFAULT_TIMEOUT)
    # Generic web / unhandled platform → Jina Reader (zero-config).
    return ("web", ["curl", "-s", "--max-time", str(_DEFAULT_TIMEOUT),
                    f"https://r.jina.ai/{url}"], _DEFAULT_TIMEOUT + 10)


def _trim_youtube_json(raw: str) -> str:
    """Reduce yt-dlp -J output to the fields an agent actually needs."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    keep = {k: data.get(k) for k in (
        "id", "title", "uploader", "channel", "upload_date", "duration",
        "view_count", "like_count", "description", "categories", "tags",
    )}
    subs = data.get("subtitles") or {}
    autosubs = data.get("automatic_captions") or {}
    keep["subtitle_languages"] = sorted(subs.keys())
    keep["auto_caption_languages"] = sorted(autosubs.keys())[:20]
    return json.dumps(keep, ensure_ascii=False, indent=2)


def run_upstream(cmd: List[str], timeout: int) -> Tuple[bool, str]:
    """Execute an upstream CLI (no shell). Returns (ok, output)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False,
        )
    except FileNotFoundError:
        return False, (
            f"MISSING_TOOL:{cmd[0]} Upstream tool '{cmd[0]}' is not installed. "
            "Run `agent-reach install --env=auto`, then `agent-reach doctor` to verify."
        )
    except subprocess.TimeoutExpired:
        return False, f"'{cmd[0]}' timed out after {timeout}s."
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, (
            f"'{' '.join(cmd[:2])}' failed (exit {proc.returncode}).\n{detail}\n"
            "Hint: run `agent-reach doctor` to check this channel's backend/login state."
        )
    return True, proc.stdout.strip()


def _clip(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n… [truncated at {MAX_OUTPUT_CHARS} chars]"
    return text


def do_search(query: str, platform: str = "web", limit: int = 5) -> str:
    cmd, timeout = build_search_command(platform, query, limit)
    ok, output = run_upstream(cmd, timeout)
    if not ok and output.startswith("MISSING_TOOL:") and platform in OPENCLI_SEARCH_FALLBACKS:
        ok, output = run_upstream(OPENCLI_SEARCH_FALLBACKS[platform](query, limit), timeout)
    return _clip(output) if ok else output.replace("MISSING_TOOL:", "", 1)


def do_read(url: str) -> str:
    platform, cmd, timeout = build_read_command(url)
    ok, output = run_upstream(cmd, timeout)
    if not ok and output.startswith("MISSING_TOOL:") and platform in OPENCLI_READ_FALLBACKS:
        ok, output = run_upstream(OPENCLI_READ_FALLBACKS[platform](url), timeout)
    if ok and platform == "youtube":
        output = _trim_youtube_json(output)
    return _clip(output) if ok else output.replace("MISSING_TOOL:", "", 1)


def create_server():
    if not HAS_MCP:
        print("MCP not installed. Install: pip install agent-reach[mcp]", file=sys.stderr)
        sys.exit(1)

    server = Server("agent-reach")
    config = Config()
    eyes = AgentReach(config)

    @server.list_tools()
    async def list_tools():
        return [
            Tool(name="get_status",
                 description="Get Agent Reach status: which channels are installed and active.",
                 inputSchema={"type": "object", "properties": {}}),
            Tool(name="search",
                 description=(
                     "Search a platform via Agent Reach's upstream tools. "
                     f"Platforms: {', '.join(SEARCH_PLATFORMS)}. "
                     "'web' is semantic full-web search (Exa). Login-required "
                     "platforms (twitter, reddit, instagram, tiktok, "
                     "xiaohongshu) reuse your browser session — check "
                     "get_status if they fail."
                 ),
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "query": {"type": "string", "description": "Search query"},
                         "platform": {"type": "string", "enum": list(SEARCH_PLATFORMS),
                                      "default": "web"},
                         "limit": {"type": "integer", "default": 5,
                                   "minimum": 1, "maximum": 50},
                     },
                     "required": ["query"],
                 }),
            Tool(name="read",
                 description=(
                     "Read a URL via Agent Reach. Auto-routes: tweets, reddit "
                     "posts, Instagram/TikTok profiles, xiaohongshu notes, "
                     "bilibili/youtube videos go to their platform CLI; any "
                     "other URL is fetched as clean text via Jina Reader."
                 ),
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "url": {"type": "string", "description": "URL to read"},
                     },
                     "required": ["url"],
                 }),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            if name == "get_status":
                result = eyes.doctor_report()
            elif name == "search":
                result = await asyncio.to_thread(
                    do_search,
                    arguments["query"],
                    arguments.get("platform", "web"),
                    arguments.get("limit", 5),
                )
            elif name == "read":
                result = await asyncio.to_thread(do_read, arguments["url"])
            else:
                result = f"Unknown tool: {name}"

            text = json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)
            return [TextContent(type="text", text=text)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    return server


async def main():
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
