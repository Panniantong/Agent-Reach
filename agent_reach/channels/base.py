# -*- coding: utf-8 -*-
"""Base types for supported research channels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Tuple

_DEFAULT_INPUT_KINDS = {
    "search": "query",
    "read": "resource",
    "user": "profile",
    "user_posts": "profile",
    "tweet": "post",
    "crawl": "url",
}


class Channel(ABC):
    """A research source that Agent Reach can diagnose for availability."""

    name: str = ""
    description: str = ""
    backends: List[str] = []
    tier: int = 0  # 0 = core, 1 = optional login/setup, 2 = advanced/manual
    auth_kind: str = "none"
    entrypoint_kind: str = "cli"
    operations: List[str] = []
    required_commands: List[str] = []
    host_patterns: List[str] = []
    example_invocations: List[str] = []
    supports_probe: bool = False
    probe_operations: List[str] = []
    install_hints: List[str] = []
    operation_inputs: dict[str, str] = {}
    operation_limit_support: dict[str, bool] = {}
    operation_options: dict[str, list[dict[str, Any]]] = {}

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True when this channel is a natural fit for the URL."""

    def check(self, config=None) -> Tuple[str, str]:
        """Return a health tuple: (status, message)."""

        summary = ", ".join(self.backends) if self.backends else "configured"
        return "ok", summary

    def probe(self, config=None) -> Tuple[str, str]:
        """Run a lightweight live validation when supported."""

        return self.check(config)

    def check_detailed(self, config=None) -> Tuple[str, str, dict[str, Any]]:
        """Return health plus optional machine-readable diagnostics."""

        status, message = self.check(config)
        return status, message, {}

    def probe_detailed(self, config=None) -> Tuple[str, str, dict[str, Any]]:
        """Run a live probe plus optional machine-readable diagnostics."""

        status, message = self.probe(config)
        return status, message, {}

    def get_operation_contracts(self) -> dict[str, dict[str, Any]]:
        """Return per-operation capability contracts for external controllers."""

        contracts: dict[str, dict[str, Any]] = {}
        for operation in self.operations:
            contracts[operation] = {
                "name": operation,
                "input_kind": self.operation_inputs.get(
                    operation,
                    _DEFAULT_INPUT_KINDS.get(operation, "text"),
                ),
                "accepts_limit": self.operation_limit_support.get(operation, True),
                "options": [dict(option) for option in self.operation_options.get(operation, [])],
            }
        return contracts

    def get_probe_operations(self) -> list[str]:
        """Return the operations covered by this channel's live probe contract."""

        if not self.supports_probe:
            return []
        if self.probe_operations:
            return list(self.probe_operations)
        return list(self.operations)

    def get_probe_coverage(self) -> str:
        """Return whether probe support covers all operations or only a subset."""

        if not self.supports_probe:
            return "none"
        if set(self.get_probe_operations()) == set(self.operations):
            return "full"
        return "partial"

    def to_contract(self) -> dict:
        """Return the machine-readable channel contract."""

        return {
            "name": self.name,
            "description": self.description,
            "tier": self.tier,
            "backends": list(self.backends),
            "auth_kind": self.auth_kind,
            "entrypoint_kind": self.entrypoint_kind,
            "operations": list(self.operations),
            "required_commands": list(self.required_commands),
            "host_patterns": list(self.host_patterns),
            "example_invocations": list(self.example_invocations),
            "supports_probe": self.supports_probe,
            "probe_operations": self.get_probe_operations(),
            "probe_coverage": self.get_probe_coverage(),
            "install_hints": list(self.install_hints),
            "operation_contracts": self.get_operation_contracts(),
        }
