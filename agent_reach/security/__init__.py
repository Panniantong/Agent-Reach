# -*- coding: utf-8 -*-
"""Security boundary for Agent Reach shell execution (Grimdall guardrails)."""

from agent_reach.security.grimdall_guard import (
    EGRESS_ALLOWLIST,
    GrimdallBlockError,
    Violation,
    check_command,
    check_destructive,
    check_egress_allowlist,
    check_secret_denial,
    is_enforce_mode,
    normalize_command,
    reset_enforce_mode,
    safe_execute,
    set_enforce_mode,
    verify_receipt,
)

__all__ = [
    "EGRESS_ALLOWLIST",
    "GrimdallBlockError",
    "Violation",
    "check_command",
    "check_destructive",
    "check_egress_allowlist",
    "check_secret_denial",
    "is_enforce_mode",
    "normalize_command",
    "reset_enforce_mode",
    "safe_execute",
    "set_enforce_mode",
    "verify_receipt",
]
