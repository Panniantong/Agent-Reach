# -*- coding: utf-8 -*-
"""Environment health checker — powered by channels.

Each channel knows how to check itself. Doctor just collects the results.
"""

from typing import Dict
from agent_reach.config import Config
from agent_reach.channels import get_all_channels


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
            status, message, active = "error", f"Health check failed: {e}", None
        results[ch.name] = {
            "status": status,
            "name": ch.description,
            "message": message,
            "tier": ch.tier,
            "backends": ch.backends,
            "active_backend": active,
        }
    return results


def _name_msg(r: dict, escape) -> str:
    """Render one channel line; show the active backend when there is a choice."""
    text = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
    active = r.get("active_backend")
    if active and len(r.get("backends", [])) > 1:
        text += f" [dim](current backend: {escape(active)})[/dim]"
    return text


def format_report(results: Dict[str, dict]) -> str:
    """Format results as a readable text report (with Rich markup)."""
    try:
        from rich.markup import escape
    except ImportError:
        escape = lambda x: x

    lines = []
    lines.append("[bold cyan]Agent Reach Status[/bold cyan]")
    lines.append("[cyan]" + "=" * 40 + "[/cyan]")
    lines.append("Legend: [green]✅[/green] Available  [yellow][!][/yellow] Installed but needs config/login  [red][X][/red] Not installed")

    ok_count = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Tier 0 — zero config
    lines.append("")
    lines.append("[bold]✅ Ready to use:[/bold]")
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
        lines.append("[bold]Optional channels (installed):[/bold]")
        for key, r in tier1_active.items():
            lines.append(f"  [green]✅[/green] {_name_msg(r, escape)}")

    # Tier 2 — optional complex setup
    tier2 = {k: r for k, r in results.items() if r["tier"] == 2}
    tier2_active = {k: r for k, r in tier2.items() if r["status"] == "ok"}
    tier2_inactive = {k: r for k, r in tier2.items() if r["status"] != "ok"}
    if tier2_active:
        if not tier1_active:
            lines.append("")
            lines.append("[bold]Optional channels (installed):[/bold]")
        for key, r in tier2_active.items():
            lines.append(f"  [green]✅[/green] {_name_msg(r, escape)}")

    lines.append("")
    status_color = "green" if ok_count == total else ("yellow" if ok_count > 0 else "red")
    lines.append(f"Status: [{status_color}]{ok_count}/{total}[/{status_color}] channels available")

    # Summarize inactive optional channels in one line instead of listing each
    all_inactive = list(tier1_inactive.values()) + list(tier2_inactive.values())
    if all_inactive:
        names = [r["name"] for r in all_inactive]
        lines.append(
            f"{len(names)} more optional channels to unlock ({', '.join(names)}). "
            "Tell your Agent \"help me install XXX\""
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
                    "[bold red][!]  Security warning: config.yaml permissions too open (readable by others)[/bold red]"
                )
                lines.append("   Fix: chmod 600 ~/.agent-reach/config.yaml")
        except OSError:
            pass

    return "\n".join(lines)
