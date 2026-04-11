# -*- coding: utf-8 -*-
"""Validation helpers derived from channel operation contracts."""

from __future__ import annotations

from typing import Any

from agent_reach.channels import get_channel_contract


class OperationContractError(Exception):
    """Raised when a request violates a channel operation contract."""

    def __init__(self, *, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def operation_contract(channel: str, operation: str) -> dict[str, Any] | None:
    """Return one operation contract when the channel registry knows it."""

    channel_contract = get_channel_contract(channel)
    if channel_contract is None:
        return None
    raw_contract = channel_contract.get("operation_contracts", {}).get(operation)
    return raw_contract if isinstance(raw_contract, dict) else None


def validate_operation_options(
    channel: str,
    operation: str,
    options: dict[str, Any],
    *,
    strict_contract: bool = False,
) -> None:
    """Validate operation-specific options against the registry contract."""

    channel_contract = get_channel_contract(channel)
    if channel_contract is None:
        if strict_contract:
            raise OperationContractError(
                code="unknown_channel",
                message=f"Unknown channel: {channel}",
                details={"channel": channel},
            )
        return

    raw_operation_contract = channel_contract.get("operation_contracts", {}).get(operation)
    if not isinstance(raw_operation_contract, dict):
        raise OperationContractError(
            code="unsupported_operation",
            message=f"{channel} does not support operation: {operation}",
            details={"supported_operations": list(channel_contract.get("operations", []))},
        )

    option_descriptors = [
        option
        for option in raw_operation_contract.get("options", [])
        if isinstance(option, dict) and option.get("name")
    ]
    option_keys = _option_keys(option_descriptors)
    provided = {key: value for key, value in options.items() if value is not None}
    unsupported = sorted(key for key in provided if key not in option_keys)
    if unsupported:
        raise OperationContractError(
            code="unsupported_option",
            message=(
                f"{', '.join(unsupported)} "
                f"{'is' if len(unsupported) == 1 else 'are'} not supported for {channel} {operation}"
            ),
            details={
                "unsupported_options": unsupported,
                "supported_options": sorted(option_keys),
                "operation": f"{channel}:{operation}",
            },
        )

    for descriptor in option_descriptors:
        names = _descriptor_names(descriptor)
        value = _first_option_value(provided, names)
        if descriptor.get("required") and (value is None or str(value).strip() == ""):
            raise OperationContractError(
                code="invalid_input",
                message=f"{channel} {operation} requires {descriptor['name']}",
                details={
                    "option": descriptor["name"],
                    "operation": f"{channel}:{operation}",
                },
            )

        choices = descriptor.get("choices")
        if value is not None and choices and value not in choices:
            raise OperationContractError(
                code="invalid_input",
                message=f"{descriptor['name']} must be one of: {', '.join(str(choice) for choice in choices)}",
                details={
                    "option": descriptor["name"],
                    "choices": list(choices),
                    "value": value,
                    "operation": f"{channel}:{operation}",
                },
            )

        minimum = descriptor.get("minimum")
        if value is not None and minimum is not None:
            normalized_value = value
            if descriptor.get("type") == "integer":
                try:
                    normalized_value = int(value)
                except (TypeError, ValueError) as exc:
                    raise OperationContractError(
                        code="invalid_input",
                        message=f"{descriptor['name']} must be an integer",
                        details={
                            "option": descriptor["name"],
                            "value": value,
                            "operation": f"{channel}:{operation}",
                        },
                    ) from exc
            if normalized_value < minimum:
                raise OperationContractError(
                    code="invalid_input",
                    message=f"{descriptor['name']} must be greater than or equal to {minimum}",
                    details={
                        "option": descriptor["name"],
                        "minimum": minimum,
                        "value": value,
                        "operation": f"{channel}:{operation}",
                    },
                )


def batch_option_values(query: dict[str, Any]) -> dict[str, Any]:
    """Extract operation-specific option values from a normalized batch query."""

    options: dict[str, Any] = {}
    if "body_mode" in query:
        options["body_mode"] = query.get("body_mode")
    if "crawl_query" in query or "query" in query:
        options["crawl_query"] = query.get("crawl_query") if query.get("crawl_query") is not None else query.get("query")
    for key in ("page_size", "max_pages", "cursor", "page", "since", "until"):
        if key in query:
            options[key] = query.get(key)
    return options


def _option_keys(descriptors: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for descriptor in descriptors:
        keys.update(_descriptor_names(descriptor))
    return keys


def _descriptor_names(descriptor: dict[str, Any]) -> set[str]:
    names = {str(descriptor["name"])}
    sdk_kwarg = descriptor.get("sdk_kwarg")
    if sdk_kwarg:
        names.add(str(sdk_kwarg))
    return names


def _first_option_value(options: dict[str, Any], names: set[str]) -> Any:
    for name in names:
        if name in options:
            return options[name]
    return None
