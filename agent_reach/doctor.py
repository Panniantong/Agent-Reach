# -*- coding: utf-8 -*-
"""Environment health checker — powered by channels.

Each channel knows how to check itself. Doctor just collects the results.
"""

from typing import Dict

from rich.markup import escape

from agent_reach.channels import get_all_channels
from agent_reach.config import Config
from agent_reach.locale import is_english_locale
from agent_reach.utils.text import scrub_url_credentials

_ENGLISH_CHANNEL_NAMES = {
    "github": "GitHub repositories and code",
    "twitter": "Twitter/X posts",
    "youtube": "YouTube videos and subtitles",
    "reddit": "Reddit posts and comments",
    "facebook": "Facebook posts, pages, and groups",
    "instagram": "Instagram users, profiles, and user posts",
    "bilibili": "Bilibili videos, subtitles, and search",
    "xiaohongshu": "Xiaohongshu notes",
    "linkedin": "LinkedIn professional networking",
    "xiaoyuzhou": "Xiaoyuzhou podcast transcription",
    "v2ex": "V2EX nodes, topics, and replies",
    "xueqiu": "Xueqiu stock quotes and community updates",
    "rss": "RSS/Atom feeds",
    "exa_search": "Semantic web search",
    "web": "Any web page",
}

_ENGLISH_BACKENDS = {
    "B站搜索 API": "Bilibili search API",
    "Xueqiu API (需要登录 Cookie)": "Xueqiu API (login cookie required)",
}

# Channel checks intentionally keep their detailed diagnostics close to the
# integration they describe. This report-level catalog translates the stable
# diagnostics without changing the JSON contract or duplicating check logic.
_ENGLISH_MESSAGE_REPLACEMENTS = (
    ("体检异常：", "Doctor check failed: "),
    ("gh CLI 未安装。安装：", "gh CLI is not installed. Install: "),
    (
        "gh 命令存在但无法执行——安装已损坏。重装即可修复：",
        "gh is installed but cannot run; the installation is broken. Reinstall to fix:",
    ),
    ("或从", "or reinstall from"),
    ("重新安装 gh CLI", " to reinstall the gh CLI"),
    ("gh CLI 版本检查失败：", "gh CLI version check failed: "),
    ("gh hosts.yml 无法安全读取", "gh hosts.yml could not be read safely"),
    ("gh hosts.yml 不是有效的 UTF-8 YAML", "gh hosts.yml is not valid UTF-8 YAML"),
    ("gh hosts.yml 顶层必须是对象", "the top level of gh hosts.yml must be an object"),
    ("gh hosts.yml 的 github.com 配置无效", "the github.com entry in gh hosts.yml is invalid"),
    ("gh hosts.yml 的 users 配置无效", "the users entry in gh hosts.yml is invalid"),
    ("Agent Reach 的 GitHub 配置无法读取", "Agent Reach's GitHub configuration could not be read"),
    (
        "gh CLI 可执行，但认证配置无法安全确认：",
        "gh CLI is executable, but its authentication configuration could not be checked safely: ",
    ),
    (
        "gh CLI 可执行，且检测到显式认证配置；Doctor 不执行会写 device-id 的 `gh auth status`，因此未实时验证，未标记为可用。",
        "gh CLI is executable and explicit authentication was found; Doctor does not run `gh auth status` because it may write a device-id, so authentication is not verified live and the channel is not marked available.",
    ),
    (
        "gh CLI 可执行，但未检测到显式认证配置。运行 `gh auth login` 完成登录；Doctor 不会自动执行 `gh auth status`。",
        "gh CLI is executable, but no explicit authentication was found. Run `gh auth login` to sign in; Doctor will not run `gh auth status` automatically.",
    ),
    ("yt-dlp 未安装。安装：", "yt-dlp is not installed. Install: "),
    (
        "yt-dlp 已安装但无法执行。重装（含 JS 支持）：",
        "yt-dlp is installed but cannot run. Reinstall with JS support:",
    ),
    ("yt-dlp 无法正常运行：", "yt-dlp could not run normally: "),
    (
        "yt-dlp 已安装但缺少 JS runtime（YouTube 必须）。",
        "yt-dlp is installed but the JS runtime required by YouTube is missing.",
    ),
    ("安装 Node.js 或 deno，然后运行：", "Install Node.js or deno, then run:"),
    (
        "无法确认 yt-dlp 版本是否支持 JS runtime 配置。",
        "Could not confirm whether this yt-dlp version supports JS runtime configuration.",
    ),
    ("请先升级并重新运行 doctor：", "Upgrade first, then run doctor again:"),
    (
        "yt-dlp 版本过旧，不支持 JS runtime 配置。请先升级并重新运行 doctor：",
        "This yt-dlp version is too old to support JS runtime configuration. Upgrade first, then run doctor again:",
    ),
    ("yt-dlp 已安装但未配置 JS runtime。运行：", "yt-dlp is installed but no JS runtime is configured. Run:"),
    ("可提取视频信息和字幕", "Video metadata and subtitles can be extracted"),
    ("（音频转写需安装 ", " (audio transcription requires "),
    ("），可转写音频（", "); audio transcription available ("),
    ("公开 API 可用（热门主题、节点浏览、主题详情、用户信息）", "Public API available (hot topics, node browsing, topic details, and user information)"),
    ("V2EX API 连接失败（可能需要代理）：", "V2EX API connection failed (a proxy may be required): "),
    ("feedparser 未安装。安装：", "feedparser is not installed. Install: "),
    ("feedparser 导入失败：", "feedparser import failed: "),
    ("修复：", "Fix: "),
    ("可读取 RSS/Atom 源", "RSS/Atom feeds can be read"),
    ("通过 Jina Reader 读取任意网页（curl https://r.jina.ai/URL）", "Read any web page through Jina Reader (curl https://r.jina.ai/URL)"),
    ("需要 mcporter + Exa MCP。安装：", "mcporter + Exa MCP are required. Install: "),
    ("Exa 已写入 mcporter 配置，但 Doctor 未启动远端服务做连通验证，不能仅凭配置宣称可用。", "Exa is configured in mcporter, but Doctor does not start the remote service to verify connectivity; configuration alone is not enough to mark it available."),
    ("mcporter 配置检查失败：", "mcporter configuration check failed: "),
    ("mcporter 本地配置未发现 Exa；配置还启用了 editor imports，Doctor 为避免扩大凭据读取范围没有展开，当前未验证。", "Exa was not found in the local mcporter configuration; editor imports are enabled, so Doctor did not expand them to avoid reading more credentials and could not verify the channel."),
    ("mcporter 已装但 Exa 未配置。运行：", "mcporter is installed but Exa is not configured. Run:"),
    ("B站搜索 API 可达（仅搜索，curl 直连）。", "Bilibili search API is reachable (search only, direct curl). "),
    ("完整功能建议安装 bili-cli：", "For full functionality, install bili-cli: "),
    ("没有可用的 B站后端（搜索 API 也不可达，可能是网络问题）。推荐：", "No Bilibili backend is available (the search API is also unreachable, possibly due to network conditions). Recommended:"),
    ("bili 命令存在但无法执行", "the bili command is present but cannot run"),
    ("bili-cli 探测失败（", "bili-cli probe failed ("),
    ("），运行 `bili status` 查看详情", "); run `bili status` for details"),
    ("bili-cli 可用（搜索/热门/排行/视频详情/音频，无需登录；字幕需 OpenCLI。上游 2026-03 起停更）", "bili-cli is available (search, trending, rankings, video details, and audio without login; subtitles require OpenCLI. The upstream project has been unmaintained since 2026-03)"),
    ("完整可用（播客下载 + Whisper 转录）", "Fully available (podcast download + Whisper transcription)"),
    ("需要 ffmpeg（音频转码和切片）。安装：", "ffmpeg is required (audio transcoding and splitting). Install:"),
    ("转录脚本未安装。运行：", "The transcription script is not installed. Run:"),
    ("需要配置 Groq API Key（免费）。步骤：", "A Groq API key is required (free). Steps:"),
    ("公开 API 可用（行情、搜索、热帖、热股）", "Public API available (quotes, search, popular posts, and trending stocks)"),
    ("API 响应异常（返回数据为空）", "API returned an unexpected empty response"),
    ("Xueqiu API 连接失败：", "Xueqiu API connection failed: "),
    ("如需登录 Cookie，请运行：", "For a login cookie, run: "),
    ("doctor 不会自动读取浏览器 Cookie。", "Doctor will not read browser cookies automatically."),
    ("基本内容可通过 Jina Reader 读取。完整功能需要：", "Basic content can be read through Jina Reader. Full functionality requires:"),
    ("LinkedIn MCP 已写入 mcporter 配置，但 Doctor 未启动本地服务做连通验证，不能仅凭配置宣称完整可用。", "LinkedIn MCP is present in the mcporter configuration, but Doctor does not start the local service to verify connectivity; configuration alone is not enough to mark full functionality available."),
    ("mcporter 本地配置未发现 LinkedIn MCP；配置还启用了 editor imports，Doctor 为避免扩大凭据读取范围没有展开，当前未验证。", "LinkedIn MCP was not found in the local mcporter configuration; editor imports are enabled, so Doctor did not expand them to avoid reading more credentials and could not verify the channel."),
    ("mcporter 已装但 LinkedIn MCP 未配置。运行：", "mcporter is installed but LinkedIn MCP is not configured. Run:"),
    ("OpenCLI 桥接已连接，但 ", "OpenCLI bridge is connected, but "),
    ("登录态和实际命令未实时验证；", "the login session and commands were not verified live;"),
    ("未实时验证；Doctor 不执行平台命令，因此当前不标记为可用。", "was not verified live; Doctor does not execute platform commands, so it is not marked as available."),
    ("需要时请先在 Chrome 里登录 ", "When needed, sign in to "),
    ("未安装任何 Reddit 后端。注意：Reddit 没有零配置路径", "No Reddit backend is installed. Reddit has no zero-configuration path"),
    ("未安装任何小红书后端。推荐：", "No Xiaohongshu backend is installed. Recommended:"),
    ("Twitter CLI 未安装。安装方式：", "Twitter CLI is not installed. Install with:"),
    ("twitter-cli 已安装，且 Cookie-Editor 凭据已配置；", "twitter-cli is installed and Cookie-Editor credentials are configured;"),
    ("twitter-cli 已安装但没有完整的显式凭据。请用 Cookie-Editor", "twitter-cli is installed but complete explicit credentials are missing. Use Cookie-Editor"),
    ("Twitter/X 登录态和实际命令未实时验证；", "the Twitter/X login session and commands were not verified live;"),
    ("Doctor 不执行平台命令，因此当前不标记为可用。", "Doctor does not execute platform commands, so it is not marked as available."),
    ("OpenCLI 已安装，但未检测到已连接的浏览器扩展。", "OpenCLI is installed, but no connected browser extension was detected."),
    ("检测到 Chrome/Edge 的 OpenCLI 扩展文件，但扩展当前未连接；", "OpenCLI extension files were found in Chrome/Edge, but the extension is not connected;"),
    ("仅凭磁盘文件无法确认它已加载或启用。", "disk files alone cannot confirm that it is loaded or enabled."),
    ("打开浏览器扩展页确认 OpenCLI 已启用，再运行一个 opencli 命令验证", "Open the browser extension page to confirm OpenCLI is enabled, then run an opencli command to verify"),
    ("安装并启用扩展（Chrome/Edge）：", "Install and enable the extension (Chrome/Edge): "),
    ("保持浏览器打开，再运行一个 opencli 命令验证", "Keep the browser open, then run an opencli command to verify"),
    ("opencli 命令存在但无法执行（node 环境损坏），重装：", "opencli is installed but cannot run (the Node environment is broken). Reinstall:"),
    ("未安装 ", "The "),
    (" 后端。安装：", " backend is not installed. Install: "),
    ("然后在 Chrome 里登录 ", "Then sign in to "),
    ("状态：", "Status: "),
)


def check_all(config: Config) -> Dict[str, dict]:
    """Check all channels and return status dict.

    A single misbehaving channel must never take the whole report down,
    so per-channel exceptions degrade to status="error".
    """
    results = {}
    for ch in get_all_channels():
        try:
            status, message = ch.check(config)
            active = getattr(ch, "active_backend", None)
        except Exception as e:  # noqa: BLE001 — doctor must survive any channel
            # Channels are registry singletons: a stale active_backend from a
            # previous check must not leak into an errored result.
            status = "error"
            message = f"体检异常：{e}"
            active = None
        # Doctor is the final output boundary for both expected channel
        # messages and unexpected exceptions. Upstream probe output can echo a
        # configured URL, so scrub every path before JSON/text rendering.
        message = scrub_url_credentials(message)
        results[ch.name] = {
            "status": status,
            "name": ch.description,
            "message": message,
            "tier": ch.tier,
            "backends": ch.backends,
            "active_backend": active,
        }
    return results


def _translate_doctor_message(message: str) -> str:
    """Translate stable channel diagnostics while preserving commands and URLs."""
    translated = message
    for source, target in _ENGLISH_MESSAGE_REPLACEMENTS:
        translated = translated.replace(source, target)
    return translated


def _localize_result(key: str, result: dict, english: bool) -> dict:
    if not english:
        return result
    localized = dict(result)
    localized["name"] = _ENGLISH_CHANNEL_NAMES.get(key, result["name"])
    localized["message"] = _translate_doctor_message(result["message"])
    localized["backends"] = [
        _ENGLISH_BACKENDS.get(backend, backend)
        for backend in result.get("backends", [])
    ]
    if result.get("active_backend"):
        localized["active_backend"] = _ENGLISH_BACKENDS.get(
            result["active_backend"], result["active_backend"]
        )
    return localized


def _name_msg(r: dict, escape, english: bool = False) -> str:
    """Render one channel line; show the active backend when there is a choice."""
    text = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
    active = r.get("active_backend")
    if active and len(r.get("backends", [])) > 1:
        if english:
            text += f" [dim](active backend: {escape(active)})[/dim]"
        else:
            text += f" [dim]（当前后端：{escape(active)}）[/dim]"
    return text


def format_report(results: Dict[str, dict], language: str | None = None) -> str:
    """Format results as a readable text report (with Rich markup)."""
    english = is_english_locale(language)
    rendered_results = {
        key: _localize_result(key, result, english)
        for key, result in results.items()
    }
    lines = []
    lines.append(
        "[bold cyan]Agent Reach status[/bold cyan]"
        if english
        else "[bold cyan]Agent Reach 状态[/bold cyan]"
    )
    lines.append("[cyan]" + "=" * 40 + "[/cyan]")
    if english:
        lines.append(
            "Legend: [green]✅[/green] available  [yellow][!][/yellow] "
            "installed but needs configuration/login  [red][X][/red] not installed"
        )
    else:
        lines.append(
            "图例：[green]✅[/green] 可用  [yellow][!][/yellow] 已装但需配置/登录  "
            "[red][X][/red] 未安装"
        )

    ok_count = sum(1 for r in rendered_results.values() if r["status"] == "ok")
    total = len(rendered_results)

    # Tier 0 — zero config
    lines.append("")
    lines.append(
        "[bold]✅ Ready to use:[/bold]"
        if english
        else "[bold]✅ 装好即用：[/bold]"
    )
    for key, r in rendered_results.items():
        if r["tier"] == 0:
            name_msg = _name_msg(r, escape, english)
            if r["status"] == "ok":
                lines.append(f"  [green]✅[/green] {name_msg}")
            elif r["status"] == "warn":
                lines.append(f"  [yellow][!][/yellow]  {name_msg}")
            elif r["status"] in ("off", "error"):
                lines.append(f"  [red][X][/red]  {name_msg}")

    # Tier 1 — needs free key / login
    tier1 = {k: r for k, r in rendered_results.items() if r["tier"] == 1}
    tier1_active = {k: r for k, r in tier1.items() if r["status"] == "ok"}
    tier1_inactive = {k: r for k, r in tier1.items() if r["status"] != "ok"}
    if tier1_active:
        lines.append("")
        lines.append(
            "[bold]Optional channels (installed):[/bold]"
            if english
            else "[bold]可选渠道（已安装）：[/bold]"
        )
        for key, r in tier1_active.items():
            lines.append(f"  [green]✅[/green] {_name_msg(r, escape, english)}")

    # Tier 2 — optional complex setup
    tier2 = {k: r for k, r in rendered_results.items() if r["tier"] == 2}
    tier2_active = {k: r for k, r in tier2.items() if r["status"] == "ok"}
    tier2_inactive = {k: r for k, r in tier2.items() if r["status"] != "ok"}
    if tier2_active:
        if not tier1_active:
            lines.append("")
            lines.append(
                "[bold]Optional channels (installed):[/bold]"
                if english
                else "[bold]可选渠道（已安装）：[/bold]"
            )
        for key, r in tier2_active.items():
            lines.append(f"  [green]✅[/green] {_name_msg(r, escape, english)}")

    lines.append("")
    status_color = "green" if ok_count == total else ("yellow" if ok_count > 0 else "red")
    if english:
        lines.append(
            f"Status: [{status_color}]{ok_count}/{total}[/{status_color}] "
            "channels available"
        )
    else:
        lines.append(f"状态：[{status_color}]{ok_count}/{total}[/{status_color}] 个渠道可用")

    # Summarize inactive optional channels in one line instead of listing each
    all_inactive = list(tier1_inactive.values()) + list(tier2_inactive.values())
    if all_inactive:
        names = [r["name"] for r in all_inactive]
        if english:
            lines.append(
                f"{len(names)} optional channels can be unlocked ({', '.join(names)}). "
                'Tell your Agent "help me install XXX".'
            )
        else:
            lines.append(
                f"还有 {len(names)} 个可选渠道可以解锁（{'、'.join(names)}），"
                "告诉你的 Agent「帮我装 XXX」即可"
            )

    # Security check: config file permissions (Unix only)
    import stat
    import sys

    config_path = Config.CONFIG_DIR / "config.yaml"
    if config_path.exists() and sys.platform != "win32":
        try:
            mode = config_path.stat().st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                lines.append("")
                if english:
                    lines.append(
                        "[bold red][!]  Security: config.yaml is readable by other users"
                        "[/bold red]"
                    )
                    lines.append("   Fix: chmod 600 ~/.agent-reach/config.yaml")
                else:
                    lines.append(
                        "[bold red][!]  安全提示：config.yaml 权限过宽（其他用户可读）[/bold red]"
                    )
                    lines.append("   修复：chmod 600 ~/.agent-reach/config.yaml")
        except OSError:
            pass

    return "\n".join(lines)
