# -*- coding: utf-8 -*-
"""Health checks and machine-readable diagnostics for supported channels."""

from __future__ import annotations

from typing import Any, Callable, Dict

from agent_reach.channels import get_all_channels
from agent_reach.config import Config
from agent_reach.schemas import SCHEMA_VERSION, utc_timestamp


def _normalize_health_result(result: object) -> tuple[str, str, dict[str, Any]]:
    """Accept legacy 2-tuples and newer 3-tuples with extra machine-readable data."""

    if not isinstance(result, tuple):
        raise TypeError("health checks must return a tuple")
    if len(result) == 2:
        status, message = result
        return status, message, {}
    if len(result) == 3:
        status, message, extra = result
        return status, message, extra if isinstance(extra, dict) else {}
    raise ValueError("health checks must return a 2-tuple or 3-tuple")


def _default_operation_statuses(contract: dict, status: str, message: str) -> dict[str, dict[str, str]]:
    """Provide operation-level health when a channel has no richer diagnostic data."""

    return {
        operation: {
            "status": status,
            "message": message,
            "diagnostic_basis": "channel_health",
        }
        for operation in contract.get("operations", [])
    }


def _default_probe_state(contract: dict, *, probe: bool) -> dict[str, object]:
    """Provide probe-run diagnostics even when a channel returns only a basic health tuple."""

    supports_probe = bool(contract.get("supports_probe"))
    operations = list(contract.get("operations", []))
    probe_operations = list(contract.get("probe_operations") or (operations if supports_probe else []))
    if not supports_probe:
        return {
            "probed_operations": [],
            "unprobed_operations": [],
            "probe_run_coverage": "unsupported",
        }
    if not probe:
        return {
            "probed_operations": [],
            "unprobed_operations": operations,
            "probe_run_coverage": "not_run",
        }
    return {
        "probed_operations": probe_operations,
        "unprobed_operations": [operation for operation in operations if operation not in probe_operations],
        "probe_run_coverage": "full" if set(probe_operations) == set(operations) else "partial",
    }


def check_all(config: Config, probe: bool = False) -> Dict[str, dict]:
    """Collect health information from every registered channel."""

    results: Dict[str, dict] = {}
    for channel in get_all_channels():
        extra: dict[str, Any] = {}
        try:
            if probe and channel.supports_probe:
                method = getattr(channel, "probe_detailed", channel.probe)
                status, message, extra = _normalize_health_result(method(config))
            else:
                method = getattr(channel, "check_detailed", channel.check)
                status, message, extra = _normalize_health_result(method(config))
        except Exception as exc:
            status, message = "error", f"Health check crashed: {exc}"

        contract = (
            channel.to_contract()
            if hasattr(channel, "to_contract")
            else {
                "name": channel.name,
                "description": getattr(channel, "description", channel.name),
                "tier": getattr(channel, "tier", 0),
                "backends": list(getattr(channel, "backends", [])),
                "auth_kind": getattr(channel, "auth_kind", "none"),
                "entrypoint_kind": getattr(channel, "entrypoint_kind", "cli"),
                "operations": list(getattr(channel, "operations", [])),
                "required_commands": list(getattr(channel, "required_commands", [])),
                "host_patterns": list(getattr(channel, "host_patterns", [])),
                "example_invocations": list(getattr(channel, "example_invocations", [])),
                "supports_probe": bool(getattr(channel, "supports_probe", False)),
                "install_hints": list(getattr(channel, "install_hints", [])),
                "operation_contracts": getattr(channel, "get_operation_contracts", lambda: {})(),
            }
        )

        payload = {
            **contract,
            "status": status,
            "message": message,
        }
        if contract.get("operations") and "operation_statuses" not in extra:
            payload["operation_statuses"] = _default_operation_statuses(contract, status, message)
        probe_state = _default_probe_state(contract, probe=probe)
        for key, value in probe_state.items():
            if key not in extra:
                payload[key] = value
        reserved = set(payload)
        payload.update({key: value for key, value in extra.items() if key not in reserved})
        results[channel.name] = payload
    return results


def _not_ready_names(items: list[dict]) -> list[str]:
    return [item["name"] for item in items if item["status"] != "ok"]


def _blocking_and_advisory_not_ready(
    results: Dict[str, dict],
    *,
    exit_policy: str = "core",
) -> tuple[list[str], list[str]]:
    values = list(results.values())
    if exit_policy == "all":
        return _not_ready_names(values), []
    if exit_policy != "core":
        raise ValueError("exit_policy must be one of: core, all")

    blocking = [
        item["name"]
        for item in values
        if (item["tier"] == 0 and item["status"] != "ok") or item["status"] == "error"
    ]
    advisory = [
        item["name"]
        for item in values
        if item["tier"] != 0 and item["status"] != "ok" and item["status"] != "error"
    ]
    return blocking, advisory


def summarize_results(results: Dict[str, dict], *, exit_policy: str = "core") -> dict:
    """Build a stable summary block for machine-readable output."""

    values = list(results.values())
    core = [item for item in values if item["tier"] == 0]
    optional = [item for item in values if item["tier"] != 0]
    exit_code = doctor_exit_code(results, exit_policy=exit_policy)
    blocking, advisory = _blocking_and_advisory_not_ready(results, exit_policy=exit_policy)
    return {
        "total": len(values),
        "ready": sum(1 for item in values if item["status"] == "ok"),
        "warnings": sum(1 for item in values if item["status"] == "warn"),
        "off": sum(1 for item in values if item["status"] == "off"),
        "errors": sum(1 for item in values if item["status"] == "error"),
        "not_ready": [item["name"] for item in values if item["status"] != "ok"],
        "exit_policy": exit_policy,
        "exit_code": exit_code,
        "blocking_not_ready": blocking,
        "advisory_not_ready": advisory,
        "core": {
            "total": len(core),
            "ready": sum(1 for item in core if item["status"] == "ok"),
        },
        "optional": {
            "total": len(optional),
            "ready": sum(1 for item in optional if item["status"] == "ok"),
        },
    }


def doctor_exit_code(results: Dict[str, dict], *, exit_policy: str = "core") -> int:
    """Return the standardized exit code for doctor results."""

    if exit_policy not in {"core", "all"}:
        raise ValueError("exit_policy must be one of: core, all")

    core = [item for item in results.values() if item["tier"] == 0]
    if any(item["status"] in {"off", "error"} for item in core):
        return 2
    if exit_policy == "all" and any(item["status"] != "ok" for item in results.values()):
        return 1
    if any(item["status"] == "warn" for item in core):
        return 1
    if any(item["status"] == "error" for item in results.values()):
        return 1
    return 0


def make_doctor_payload(
    results: Dict[str, dict],
    probe: bool = False,
    *,
    exit_policy: str = "core",
) -> dict:
    """Build a machine-readable doctor payload."""

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "probe": probe,
        "summary": summarize_results(results, exit_policy=exit_policy),
        "channels": list(results.values()),
    }


def format_report(results: Dict[str, dict], probe: bool = False, *, exit_policy: str = "core") -> str:
    """Render a compact terminal-friendly health report."""

    escape_markup: Callable[[str], str]
    try:
        from rich.markup import escape as rich_escape

        escape_markup = rich_escape
    except ImportError:

        def escape_markup(value: str) -> str:
            return value

    def render_line(result: dict) -> str:
        status = result["status"]
        label_name = result.get("description") or result.get("name", "unknown")
        label = f"[bold]{escape_markup(label_name)}[/bold]: {escape_markup(result['message'])}"
        if status == "ok":
            return f"  [green][OK][/green] {label}"
        if status == "warn":
            return f"  [yellow][WARN][/yellow] {label}"
        if status == "off":
            return f"  [red][OFF][/red] {label}"
        return f"  [red][ERR][/red] {label}"

    summary = summarize_results(results, exit_policy=exit_policy)
    lines = [
        "[bold cyan]Agent Reach Health[/bold cyan]",
        "[cyan]========================================[/cyan]",
    ]
    if probe:
        lines.append("[cyan]Mode: lightweight live probes enabled[/cyan]")
    lines.extend(["", "[bold]Core channels[/bold]"])

    core = [result for result in results.values() if result["tier"] == 0]
    optional = [result for result in results.values() if result["tier"] != 0]
    for result in core:
        lines.append(render_line(result))

    if optional:
        lines.extend(["", "[bold]Optional channels[/bold]"])
        for result in optional:
            lines.append(render_line(result))

    lines.extend(["", f"Summary: [bold]{summary['ready']}/{summary['total']}[/bold] channels ready"])
    if summary["blocking_not_ready"]:
        labels = [
            item.get("description") or item.get("name", "unknown")
            for item in results.values()
            if item["name"] in summary["blocking_not_ready"]
        ]
        lines.append(f"Not ready: {', '.join(labels)}")
    if summary["advisory_not_ready"]:
        labels = [
            item.get("description") or item.get("name", "unknown")
            for item in results.values()
            if item["name"] in summary["advisory_not_ready"]
        ]
        lines.append(f"Advisory only: {', '.join(labels)}")

    return "\n".join(lines)
