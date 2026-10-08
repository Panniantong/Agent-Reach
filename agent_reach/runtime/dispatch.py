"""Run a unified action: validate params, try backends in order, build the envelope."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from agent_reach.channels.base import Action, Channel

from .result import (
    BAD_INPUT,
    FINAL_CODES,
    NEED_SETUP,
    TIMEOUT,
    ReachError,
    classify,
    envelope,
)

DEFAULT_TIMEOUT = 30.0


def find_action(channel: Channel, name: str) -> Optional[Action]:
    return next((a for a in channel.actions if a.name == name), None)


def _validate(action: Action, params: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for p in action.params:
        value = params.get(p.name)
        if value is None or value == "":
            if p.required:
                raise ReachError(BAD_INPUT, f"missing required argument: {p.name}")
            value = p.default
        elif p.type is not str:
            try:
                value = p.type(value)
            except (TypeError, ValueError):
                raise ReachError(BAD_INPUT, f"{p.name} must be {p.type.__name__}") from None
        clean[p.name] = value
    unknown = set(params) - {p.name for p in action.params}
    if unknown:
        raise ReachError(BAD_INPUT, f"unknown argument(s): {', '.join(sorted(unknown))}")
    return clean


def _call_with_deadline(fn, params: Dict[str, Any], timeout: float) -> List[dict]:
    """Run fn(timeout=..., **params); give up after `timeout` seconds.

    In-process HTTP calls cannot be interrupted, so the call runs in a daemon
    thread. Subprocess backends also receive `timeout` and kill themselves.
    """
    box: Dict[str, Any] = {}

    def target() -> None:
        try:
            box["items"] = fn(timeout=timeout, **params)
        except BaseException as exc:  # noqa: BLE001 - forwarded to classify()
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout + 1.0)
    if worker.is_alive():
        raise ReachError(TIMEOUT, f"backend did not answer within {timeout:.0f}s")
    if "error" in box:
        raise box["error"]
    return list(box.get("items") or [])


def _pick_error(errors: List[ReachError]) -> ReachError:
    """Report the most useful failure: a real error beats 'not installed'."""
    for err in errors:
        if err.code != NEED_SETUP:
            return err
    return errors[0]


def run_action(
    channel: Channel,
    action_name: str,
    params: Dict[str, Any],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    only_backend: Optional[str] = None,
) -> dict:
    """Execute one unified action and return the envelope dict."""
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    action = find_action(channel, action_name)
    if action is None:
        valid = ", ".join(a.name for a in channel.actions) or "none"
        err = ReachError(BAD_INPUT, f"unknown action '{action_name}' for {channel.name}; valid: {valid}")
        return envelope(channel=channel.name, action=action_name, elapsed_ms=elapsed(), error=err)
    try:
        clean = _validate(action, params)
    except ReachError as err:
        return envelope(channel=channel.name, action=action_name, elapsed_ms=elapsed(), error=err)

    backends = [b for b in action.backends if only_backend in (None, b[0])]
    deadline = started + timeout
    attempts: List[dict] = []
    errors: List[ReachError] = []
    for label, method_name in backends:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            attempts.append({"backend": label, "result": TIMEOUT})
            errors.append(ReachError(TIMEOUT, "no time left for this backend"))
            continue
        try:
            items = _call_with_deadline(getattr(channel, method_name), clean, remaining)
        except BaseException as exc:  # noqa: BLE001
            err = classify(exc)
            attempts.append({"backend": label, "result": err.code, "message": err.message})
            errors.append(err)
            if err.code in FINAL_CODES:
                break
            continue
        attempts.append({"backend": label, "result": "ok"})
        return envelope(
            channel=channel.name,
            action=action_name,
            backend=label,
            items=items,
            elapsed_ms=elapsed(),
            attempts=attempts,
        )

    final = errors and next((e for e in errors if e.code in FINAL_CODES), None)
    err = final or (_pick_error(errors) if errors else ReachError(BAD_INPUT, f"no backend named '{only_backend}'"))
    return envelope(
        channel=channel.name,
        action=action_name,
        elapsed_ms=elapsed(),
        attempts=attempts,
        error=err,
    )
