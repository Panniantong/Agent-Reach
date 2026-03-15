# -*- coding: utf-8 -*-
"""Environment health checker — powered by channels.

Each channel knows how to check itself. Doctor just collects the results.
"""

from typing import Dict
from agent_reach.config import Config
from agent_reach.channels import get_all_channels


def check_all(config: Config) -> Dict[str, dict]:
    """Check all channels and return status dict."""
    results = {}
    for ch in get_all_channels():
        status, message = ch.check(config)
        results[ch.name] = {
            "status": status,
            "name": ch.description,
            "message": message,
            "tier": ch.tier,
            "backends": ch.backends,
        }
    return results


def format_report(results: Dict[str, dict]) -> str:
    """Format results as a readable text report (with Rich markup)."""
    try:
        from rich.markup import escape
    except ImportError:
        escape = lambda x: x

    lines = []
    lines.append("[bold cyan]Agent Reach 状态[/bold cyan]")
    lines.append("[cyan]" + "=" * 40 + "[/cyan]")

    ok_count = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Tier 0 — zero config
    lines.append("")
    lines.append("[bold]✅ 装好即用：[/bold]")
    for key, r in results.items():
        if r["tier"] == 0:
            name_msg = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
            if r["status"] == "ok":
                lines.append(f"  [green]✅[/green] {name_msg}")
            elif r["status"] == "warn":
                lines.append(f"  [yellow][!][/yellow]  {name_msg}")
            elif r["status"] in ("off", "error"):
                lines.append(f"  [red][X][/red]  {name_msg}")

    # Tier 1 — needs free key
    tier1 = {k: r for k, r in results.items() if r["tier"] == 1}
    if tier1:
        lines.append("")
        lines.append("[bold]搜索（mcporter 即可解锁）：[/bold]")
        for key, r in tier1.items():
            name_msg = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
            if r["status"] == "ok":
                lines.append(f"  [green]✅[/green] {name_msg}")
            else:
                lines.append(f"  [dim]--[/dim]  {name_msg}")

    # Tier 2 — optional setup
    tier2 = {k: r for k, r in results.items() if r["tier"] == 2}
    if tier2:
        lines.append("")
        lines.append("[bold]配置后可用：[/bold]")
        for key, r in tier2.items():
            name_msg = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
            if r["status"] == "ok":
                lines.append(f"  [green]✅[/green] {name_msg}")
            elif r["status"] == "warn":
                lines.append(f"  [yellow][!][/yellow]  {name_msg}")
            else:
                lines.append(f"  [dim]--[/dim]  {name_msg}")

    lines.append("")
    status_color = "green" if ok_count == total else ("yellow" if ok_count > 0 else "red")
    lines.append(f"状态：[{status_color}]{ok_count}/{total}[/{status_color}] 个渠道可用")
    if ok_count < total:
        lines.append("运行 [cyan]`agent-reach setup`[/cyan] 解锁更多渠道")

    # Security check: config file permissions (Unix only)
    import os
    import stat
    import sys

    config_path = Config.CONFIG_DIR / "config.yaml"
    if config_path.exists() and sys.platform != "win32":
        try:
            mode = config_path.stat().st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                lines.append("")
                lines.append(
                    "[bold red][!]  安全提示：config.yaml 权限过宽（其他用户可读）[/bold red]"
                )
                lines.append("   修复：chmod 600 ~/.agent-reach/config.yaml")
        except OSError:
            pass

    return "\n".join(lines)
