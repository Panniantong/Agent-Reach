# -*- coding: utf-8 -*-
"""Environment health checker — powered by channels.

Each channel knows how to check itself. Doctor just collects the results.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Tuple
from agent_reach.config import Config
from agent_reach.channels import Channel, get_all_channels


def _check_one(ch: Channel, config: Config) -> Tuple[str, dict]:
    """Probe a single channel; return (name, result). Never raises.

    A single misbehaving channel must never take the whole report down,
    so per-channel exceptions degrade to status="error".
    """
    try:
        status, message = ch.check(config)
        active = getattr(ch, "active_backend", None)
    except Exception as e:  # noqa: BLE001 — doctor must survive any channel
        # Channels are registry singletons: a stale active_backend from a
        # previous check must not leak into an errored result.
        status, message, active = "error", f"体检异常：{e}", None
    return ch.name, {
        "status": status,
        "name": ch.description,
        "message": message,
        "tier": ch.tier,
        "backends": ch.backends,
        "active_backend": active,
    }


def check_all(config: Config) -> Dict[str, dict]:
    """Check all channels concurrently and return status dict.

    Each check() does real subprocess/network probing with multi-second
    timeouts (e.g. `rdt status` waits up to 10s), so sequential probing makes
    doctor needlessly slow — wall time becomes the *sum* of every timeout.
    Probing is I/O-bound, so threads sidestep the GIL and wall time collapses
    to roughly the single slowest channel. Each channel is a distinct registry
    object and probes are stateless (no shared mutable state), so this is safe.

    Result order follows the channel registry — ThreadPoolExecutor.map()
    preserves input order — which format_report() relies on for tiered output.
    """
    channels = get_all_channels()
    if not channels:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(channels), 16)) as pool:
        pairs = pool.map(lambda ch: _check_one(ch, config), channels)
        return dict(pairs)


def _name_msg(r: dict, escape) -> str:
    """Render one channel line; show the active backend when there is a choice."""
    text = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
    active = r.get("active_backend")
    if active and len(r.get("backends", [])) > 1:
        text += f" [dim]（当前后端：{escape(active)}）[/dim]"
    return text


def format_report(results: Dict[str, dict]) -> str:
    """Format results as a readable text report (with Rich markup)."""
    try:
        from rich.markup import escape
    except ImportError:
        escape = lambda x: x

    lines = []
    lines.append("[bold cyan]Agent Reach 状态[/bold cyan]")
    lines.append("[cyan]" + "=" * 40 + "[/cyan]")
    lines.append("图例：[green]✅[/green] 可用  [yellow][!][/yellow] 已装但需配置/登录  [red][X][/red] 未安装")

    ok_count = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Tier 0 — zero config
    lines.append("")
    lines.append("[bold]✅ 装好即用：[/bold]")
    for key, r in results.items():
        if r["tier"] == 0:
            name_msg = _name_msg(r, escape)
            if r["status"] == "ok":
                lines.append(f"  [green]✅[/green] {name_msg}")
            elif r["status"] == "warn":
                lines.append(f"  [yellow][!][/yellow]  {name_msg}")
            elif r["status"] in ("off", "error"):
                lines.append(f"  [red][X][/red]  {name_msg}")

    # Tier 1 — needs free key / login
    tier1 = {k: r for k, r in results.items() if r["tier"] == 1}
    tier1_active = {k: r for k, r in tier1.items() if r["status"] == "ok"}
    tier1_inactive = {k: r for k, r in tier1.items() if r["status"] != "ok"}
    if tier1_active:
        lines.append("")
        lines.append("[bold]可选渠道（已安装）：[/bold]")
        for key, r in tier1_active.items():
            lines.append(f"  [green]✅[/green] {_name_msg(r, escape)}")

    # Tier 2 — optional complex setup
    tier2 = {k: r for k, r in results.items() if r["tier"] == 2}
    tier2_active = {k: r for k, r in tier2.items() if r["status"] == "ok"}
    tier2_inactive = {k: r for k, r in tier2.items() if r["status"] != "ok"}
    if tier2_active:
        if not tier1_active:
            lines.append("")
            lines.append("[bold]可选渠道（已安装）：[/bold]")
        for key, r in tier2_active.items():
            lines.append(f"  [green]✅[/green] {_name_msg(r, escape)}")

    lines.append("")
    status_color = "green" if ok_count == total else ("yellow" if ok_count > 0 else "red")
    lines.append(f"状态：[{status_color}]{ok_count}/{total}[/{status_color}] 个渠道可用")

    # Summarize inactive optional channels in one line instead of listing each
    all_inactive = list(tier1_inactive.values()) + list(tier2_inactive.values())
    if all_inactive:
        names = [r["name"] for r in all_inactive]
        lines.append(
            f"还有 {len(names)} 个可选渠道可以解锁（{'、'.join(names)}），"
            "告诉你的 Agent「帮我装 XXX」即可"
        )

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
