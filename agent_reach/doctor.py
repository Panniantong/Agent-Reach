# -*- coding: utf-8 -*-
"""Health checks for the supported Windows/Codex channels."""

from __future__ import annotations

from typing import Dict

from agent_reach.channels import get_all_channels
from agent_reach.config import Config


def check_all(config: Config) -> Dict[str, dict]:
    """Collect health information from every registered channel."""

    results: Dict[str, dict] = {}
    for channel in get_all_channels():
        status, message = channel.check(config)
        results[channel.name] = {
            "status": status,
            "name": channel.description,
            "message": message,
            "tier": channel.tier,
            "backends": channel.backends,
        }
    return results


def format_report(results: Dict[str, dict]) -> str:
    """Render a compact terminal-friendly health report."""

    try:
        from rich.markup import escape
    except ImportError:
        def escape(value: str) -> str:
            return value

    def render_line(result: dict) -> str:
        status = result["status"]
        label = f"[bold]{escape(result['name'])}[/bold]: {escape(result['message'])}"
        if status == "ok":
            return f"  [green][OK][/green] {label}"
        if status == "warn":
            return f"  [yellow][WARN][/yellow] {label}"
        if status == "off":
            return f"  [red][OFF][/red] {label}"
        return f"  [red][ERR][/red] {label}"

    lines = [
        "[bold cyan]Agent Reach Health[/bold cyan]",
        "[cyan]========================================[/cyan]",
        "",
        "[bold]Core channels[/bold]",
    ]

    core = [result for result in results.values() if result["tier"] == 0]
    optional = [result for result in results.values() if result["tier"] != 0]
    for result in core:
        lines.append(render_line(result))

    if optional:
        lines.extend(["", "[bold]Optional channels[/bold]"])
        for result in optional:
            lines.append(render_line(result))

    ready = sum(1 for result in results.values() if result["status"] == "ok")
    lines.extend(["", f"Summary: [bold]{ready}/{len(results)}[/bold] channels ready"])

    not_ready = [result["name"] for result in results.values() if result["status"] != "ok"]
    if not_ready:
        lines.append(f"Not ready: {', '.join(not_ready)}")

    return "\n".join(lines)
