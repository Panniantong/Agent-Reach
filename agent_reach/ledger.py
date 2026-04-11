# -*- coding: utf-8 -*-
"""Evidence ledger helpers for collection runs."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, TypedDict, cast

from agent_reach.results import CollectionResult
from agent_reach.schemas import SCHEMA_VERSION, utc_timestamp


class EvidenceLedgerRecord(TypedDict):
    """A JSONL record preserving one collection result envelope."""

    schema_version: str
    record_type: str
    run_id: str
    created_at: str
    channel: str
    operation: str
    input: str | None
    ok: bool
    count: int
    item_ids: list[str]
    urls: list[str]
    error_code: str | None
    intent: str | None
    query_id: str | None
    source_role: str | None
    result: CollectionResult


_LEDGER_GLOB = "*.jsonl"
_SHARD_CHOICES = {"channel", "operation", "channel-operation"}
_LARGE_TEXT_CHARS = 10_000
_LARGE_RAW_CHARS = 100_000
_DIAGNOSTIC_LIMIT = 50
_UTF8_BOM = b"\xef\xbb\xbf"
_JSONL_UNSAFE_LINE_SEPARATORS = {
    "\u0085": "\\u0085",
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}
_FILTER_EXPRESSION_RE = re.compile(
    r"^\s*(?P<path>[A-Za-z0-9_.-]+)\s*(?P<operator>==|!=|>=|<=|>|<|contains)\s*(?P<value>.+?)\s*$"
)
_MISSING = object()


def default_run_id() -> str:
    """Return the run ID for this command invocation."""

    configured = os.environ.get("AGENT_REACH_RUN_ID")
    if configured:
        return configured
    return f"run-{utc_timestamp().replace(':', '').replace('-', '')}"


def build_ledger_record(
    result: CollectionResult,
    *,
    run_id: str,
    input_value: str | None = None,
    intent: str | None = None,
    query_id: str | None = None,
    source_role: str | None = None,
) -> EvidenceLedgerRecord:
    """Build a compact ledger record around a full collection result."""

    items = result.get("items") or []
    error = result.get("error")
    meta = result.get("meta") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "collection_result",
        "run_id": run_id,
        "created_at": utc_timestamp(),
        "channel": result["channel"],
        "operation": result["operation"],
        "input": input_value if input_value is not None else meta.get("input"),
        "ok": bool(result["ok"]),
        "count": int(meta.get("count", len(items)) or 0),
        "item_ids": [str(item.get("id")) for item in items if item.get("id")],
        "urls": [str(item.get("url")) for item in items if item.get("url")],
        "error_code": error["code"] if error else None,
        "intent": intent if intent is not None else meta.get("intent"),
        "query_id": query_id if query_id is not None else meta.get("query_id"),
        "source_role": source_role if source_role is not None else meta.get("source_role"),
        "result": result,
    }


def append_ledger_record(path: str | Path, record: EvidenceLedgerRecord) -> None:
    """Append a ledger record as JSON Lines, creating parent directories."""

    ledger_path = Path(path)
    _ensure_parent_dir(ledger_path)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(_jsonl_record_text(record))
        handle.write("\n")


def iter_jsonl_lines(path: str | Path) -> Iterable[tuple[int, str]]:
    """Yield physical JSONL lines split only on LF/CRLF bytes.

    Python's str.splitlines() treats Unicode line separators such as U+2028
    as line boundaries. JSONL records may legitimately contain those
    characters inside JSON strings, so ledger readers must split on physical
    LF bytes only.
    """

    with Path(path).open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if line_number == 1 and raw_line.startswith(_UTF8_BOM):
                raw_line = raw_line[len(_UTF8_BOM) :]
            if raw_line.endswith(b"\n"):
                raw_line = raw_line[:-1]
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]
            yield line_number, raw_line.decode("utf-8")


def save_collection_result(
    path: str | Path,
    result: CollectionResult,
    *,
    run_id: str,
    input_value: str | None = None,
    intent: str | None = None,
    query_id: str | None = None,
    source_role: str | None = None,
) -> EvidenceLedgerRecord:
    """Build and append a collection result ledger record."""

    record = build_ledger_record(
        result,
        run_id=run_id,
        input_value=input_value,
        intent=intent,
        query_id=query_id,
        source_role=source_role,
    )
    append_ledger_record(path, record)
    return record


def ledger_input_paths(
    path: str | Path,
    *,
    allow_missing: bool = False,
    exclude: str | Path | None = None,
) -> list[Path]:
    """Resolve a ledger file or directory into concrete JSONL input paths."""

    target = Path(path)
    if not target.exists():
        if allow_missing:
            return []
        raise FileNotFoundError(f"Ledger input does not exist: {target}")

    excluded_path = _resolved_path(exclude) if exclude is not None else None
    if target.is_dir():
        paths = [
            candidate
            for candidate in sorted(target.rglob(_LEDGER_GLOB), key=lambda item: str(item).lower())
            if candidate.is_file() and _resolved_path(candidate) != excluded_path
        ]
        if paths or allow_missing:
            return paths
        raise FileNotFoundError(f"No ledger JSONL files were found under: {target}")

    if excluded_path is not None and _resolved_path(target) == excluded_path:
        if allow_missing:
            return []
        raise ValueError("Ledger input and output paths must differ")
    return [target]


def iter_ledger_records(path: str | Path, *, allow_missing: bool = False) -> Iterable[dict[str, Any]]:
    """Yield parsed JSON records from one ledger file or a ledger directory."""

    for ledger_path in ledger_input_paths(path, allow_missing=allow_missing):
        for _line_number, line in iter_jsonl_lines(ledger_path):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def shard_ledger_path(
    base_dir: str | Path,
    *,
    channel: str,
    operation: str,
    shard_by: str = "channel",
) -> Path:
    """Return the target shard path for one collection result."""

    if shard_by not in _SHARD_CHOICES:
        choices = ", ".join(sorted(_SHARD_CHOICES))
        raise ValueError(f"Unsupported shard_by value: {shard_by}. Expected one of: {choices}")

    root = Path(base_dir)
    if shard_by == "channel":
        filename = f"{channel}.jsonl"
    elif shard_by == "operation":
        filename = f"{operation}.jsonl"
    else:
        filename = f"{channel}__{operation}.jsonl"
    return root / filename


def save_collection_result_sharded(
    base_dir: str | Path,
    result: CollectionResult,
    *,
    run_id: str,
    shard_by: str = "channel",
    input_value: str | None = None,
    intent: str | None = None,
    query_id: str | None = None,
    source_role: str | None = None,
) -> tuple[EvidenceLedgerRecord, Path]:
    """Save a collection result into a sharded ledger directory."""

    record = build_ledger_record(
        result,
        run_id=run_id,
        input_value=input_value,
        intent=intent,
        query_id=query_id,
        source_role=source_role,
    )
    shard_path = shard_ledger_path(
        base_dir,
        channel=record["channel"],
        operation=record["operation"],
        shard_by=shard_by,
    )
    append_ledger_record(shard_path, record)
    return record, shard_path


def merge_ledger_inputs(
    input_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Merge one ledger file or a directory of ledger shards into one JSONL output."""

    source = Path(input_path)
    destination = Path(output_path)
    if _resolved_path(source) == _resolved_path(destination):
        raise ValueError("Ledger input and output paths must differ")

    inputs = ledger_input_paths(source, exclude=destination)
    _ensure_parent_dir(destination)

    records_written = 0
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for ledger_path in inputs:
            for _line_number, line in iter_jsonl_lines(ledger_path):
                if not line.strip():
                    continue
                handle.write(_escape_jsonl_line_separators(line))
                handle.write("\n")
                records_written += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "ledger merge",
        "input": str(source),
        "output": str(destination),
        "files_merged": len(inputs),
        "records_written": records_written,
        "inputs": [str(path) for path in inputs],
    }


def validate_ledger_input(input_path: str | Path, *, require_metadata: bool = False) -> dict[str, Any]:
    """Validate one evidence ledger file or a directory of ledger shards."""

    source = Path(input_path)
    inputs = ledger_input_paths(source)
    records = 0
    collection_results = 0
    items_seen = 0
    empty_lines = 0
    invalid_line_count = 0
    invalid_record_count = 0
    invalid_lines: list[dict[str, Any]] = []
    invalid_records: list[dict[str, Any]] = []
    large_text_fields: list[dict[str, Any]] = []
    large_raw_payloads: list[dict[str, Any]] = []
    ok_records = 0
    error_records = 0
    channel_counts: dict[str, int] = {}
    operation_counts: dict[str, int] = {}
    error_codes: dict[str, int] = {}
    intent_counts: dict[str, int] = {}
    query_id_counts: dict[str, int] = {}
    source_role_counts: dict[str, int] = {}
    missing_metadata_counts = {"intent": 0, "query_id": 0, "source_role": 0}
    metadata_missing_records = 0
    missing_metadata_samples: list[dict[str, Any]] = []

    for ledger_path in inputs:
        for line_number, line in iter_jsonl_lines(ledger_path):
            if not line.strip():
                empty_lines += 1
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                invalid_line_count += 1
                if len(invalid_lines) < _DIAGNOSTIC_LIMIT:
                    invalid_lines.append(
                        {
                            "file": str(ledger_path),
                            "line": line_number,
                            "error": exc.msg,
                        }
                    )
                continue
            records += 1
            if not isinstance(record, dict):
                invalid_record_count += 1
                if len(invalid_records) < _DIAGNOSTIC_LIMIT:
                    invalid_records.append(
                        {
                            "file": str(ledger_path),
                            "line": line_number,
                            "error": "record must be a JSON object",
                        }
                    )
                continue
            result_payload = record.get("result")
            if record.get("record_type") != "collection_result" or not _is_collection_result(result_payload):
                invalid_record_count += 1
                if len(invalid_records) < _DIAGNOSTIC_LIMIT:
                    invalid_records.append(
                        {
                            "file": str(ledger_path),
                            "line": line_number,
                            "error": "record must be a collection_result with a valid result envelope",
                        }
                    )
                continue
            result = cast(dict[str, Any], result_payload)
            collection_results += 1
            channel = str(record.get("channel") or result.get("channel") or "unknown")
            operation = str(record.get("operation") or result.get("operation") or "unknown")
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
            operation_counts[operation] = operation_counts.get(operation, 0) + 1
            if bool(result.get("ok")):
                ok_records += 1
            else:
                error_records += 1
                error = result.get("error") if isinstance(result.get("error"), dict) else None
                code = record.get("error_code") or (error.get("code") if error else None)
                if code:
                    error_code = str(code)
                    error_codes[error_code] = error_codes.get(error_code, 0) + 1
            raw_meta = result.get("meta")
            meta = cast(dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
            missing_fields = [
                name
                for name in ("intent", "query_id", "source_role")
                if record.get(name) is None and meta.get(name) is None
            ]
            _increment_if_present(intent_counts, record.get("intent") if record.get("intent") is not None else meta.get("intent"))
            _increment_if_present(
                query_id_counts,
                record.get("query_id") if record.get("query_id") is not None else meta.get("query_id"),
            )
            _increment_if_present(
                source_role_counts,
                record.get("source_role") if record.get("source_role") is not None else meta.get("source_role"),
            )
            for name in missing_fields:
                missing_metadata_counts[name] += 1
            if missing_fields:
                metadata_missing_records += 1
            if missing_fields and len(missing_metadata_samples) < _DIAGNOSTIC_LIMIT:
                missing_metadata_samples.append(
                    {
                        "file": str(ledger_path),
                        "line": line_number,
                        "channel": channel,
                        "operation": operation,
                        "missing": missing_fields,
                    }
                )
            raw_length = _raw_payload_length(result.get("raw"))
            if raw_length > _LARGE_RAW_CHARS and len(large_raw_payloads) < _DIAGNOSTIC_LIMIT:
                large_raw_payloads.append(
                    {
                        "file": str(ledger_path),
                        "line": line_number,
                        "channel": channel,
                        "operation": operation,
                        "raw_length": raw_length,
                    }
                )
            items = result.get("items") or []
            items_seen += len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and len(text) > _LARGE_TEXT_CHARS:
                    large_text_fields.append(
                        {
                            "file": str(ledger_path),
                            "line": line_number,
                            "item_id": item.get("id"),
                            "text_length": len(text),
                        }
                    )

    metadata_valid = not require_metadata or metadata_missing_records == 0
    valid = invalid_line_count == 0 and invalid_record_count == 0 and metadata_valid
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "ledger validate",
        "input": str(source),
        "require_metadata": require_metadata,
        "valid": valid,
        "files_checked": len(inputs),
        "records": records,
        "collection_results": collection_results,
        "counts_scope": "parseable_records_only",
        "ok_records": ok_records,
        "error_records": error_records,
        "channel_counts": channel_counts,
        "operation_counts": operation_counts,
        "intent_counts": intent_counts,
        "query_id_counts": query_id_counts,
        "source_role_counts": source_role_counts,
        "error_codes": error_codes,
        "missing_metadata": {
            **missing_metadata_counts,
            "records": metadata_missing_records,
            "samples": missing_metadata_samples,
        },
        "items_seen": items_seen,
        "empty_lines": empty_lines,
        "invalid_lines": invalid_line_count,
        "invalid_line_samples": invalid_lines,
        "invalid_records": invalid_record_count,
        "invalid_record_samples": invalid_records,
        "large_text_threshold": _LARGE_TEXT_CHARS,
        "large_text_fields": large_text_fields,
        "large_raw_payload_threshold": _LARGE_RAW_CHARS,
        "large_raw_payloads": large_raw_payloads,
    }


def summarize_ledger_input(input_path: str | Path) -> dict[str, Any]:
    """Return non-scoring evidence ledger health counts for downstream automation."""

    validation = validate_ledger_input(input_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "ledger summarize",
        "input": validation["input"],
        "valid": validation["valid"],
        "counts_scope": validation["counts_scope"],
        "files_checked": validation["files_checked"],
        "records": validation["records"],
        "collection_results": validation["collection_results"],
        "items_seen": validation["items_seen"],
        "ok_records": validation["ok_records"],
        "error_records": validation["error_records"],
        "channel_counts": validation["channel_counts"],
        "operation_counts": validation["operation_counts"],
        "intent_counts": validation["intent_counts"],
        "query_id_counts": validation["query_id_counts"],
        "source_role_counts": validation["source_role_counts"],
        "error_codes": validation["error_codes"],
        "missing_metadata": validation["missing_metadata"],
        "invalid_lines": validation["invalid_lines"],
        "invalid_records": validation["invalid_records"],
    }


def query_ledger_input(
    input_path: str | Path,
    *,
    filters: list[str] | None = None,
    limit: int | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Filter evidence ledger records with a small dotted-path query surface."""

    if limit is not None and limit < 1:
        raise ValueError("limit must be greater than or equal to 1")

    source = Path(input_path)
    inputs = ledger_input_paths(source)
    parsed_filters = [_parse_filter_expression(expression) for expression in (filters or [])]
    projected_fields = _normalize_query_fields(fields)
    invalid_lines = 0
    invalid_records = 0
    records_scanned = 0
    matched_records = 0
    matches: list[dict[str, Any]] = []

    for ledger_path in inputs:
        for line_number, line in iter_jsonl_lines(ledger_path):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue
            if not isinstance(record, dict):
                invalid_records += 1
                continue

            records_scanned += 1
            context = {
                **record,
                "source": {
                    "file": str(ledger_path),
                    "line": line_number,
                },
            }
            if not all(_record_matches_filter(context, parsed_filter) for parsed_filter in parsed_filters):
                continue

            matched_records += 1
            if limit is None or len(matches) < limit:
                matches.append(_project_query_match(context, projected_fields))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "ledger query",
        "input": str(source),
        "files_checked": len(inputs),
        "filters": parsed_filters,
        "limit": limit,
        "fields": projected_fields,
        "records_scanned": records_scanned,
        "invalid_lines": invalid_lines,
        "invalid_records": invalid_records,
        "matched_records": matched_records,
        "returned_records": len(matches),
        "matches": matches,
    }


def append_result_json(
    input_path: str | Path,
    output_path: str | Path,
    *,
    run_id: str,
    intent: str | None = None,
    query_id: str | None = None,
    source_role: str | None = None,
) -> dict[str, Any]:
    """Append an already-saved CollectionResult JSON file to an evidence ledger."""

    source = Path(input_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"CollectionResult input does not exist: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"CollectionResult input is not valid JSON: {exc.msg}") from exc
    if not _is_collection_result(payload):
        raise ValueError("Input JSON must be a CollectionResult envelope")

    record = save_collection_result(
        output_path,
        payload,
        run_id=run_id,
        intent=intent,
        query_id=query_id,
        source_role=source_role,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "ledger append",
        "input": str(source),
        "output": str(output_path),
        "record_type": record["record_type"],
        "run_id": record["run_id"],
        "channel": record["channel"],
        "operation": record["operation"],
        "ok": record["ok"],
        "count": record["count"],
        "item_ids": record["item_ids"],
        "urls": record["urls"],
        "intent": record["intent"],
        "query_id": record["query_id"],
        "source_role": record["source_role"],
    }


def _is_collection_result(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("channel"), str):
        return False
    if not isinstance(value.get("operation"), str):
        return False
    if not isinstance(value.get("ok"), bool):
        return False
    if not isinstance(value.get("items"), list):
        return False
    if not isinstance(value.get("meta"), dict):
        return False
    if "error" not in value:
        return False
    return True


def _ensure_parent_dir(path: Path) -> None:
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)


def _jsonl_record_text(record: EvidenceLedgerRecord | dict[str, Any]) -> str:
    return _escape_jsonl_line_separators(json.dumps(record, ensure_ascii=False))


def _escape_jsonl_line_separators(text: str) -> str:
    for char, replacement in _JSONL_UNSAFE_LINE_SEPARATORS.items():
        text = text.replace(char, replacement)
    return text


def _raw_payload_length(raw_payload: Any) -> int:
    if raw_payload is None:
        return 0
    if isinstance(raw_payload, str):
        return len(raw_payload)
    try:
        return len(json.dumps(raw_payload, ensure_ascii=False))
    except (TypeError, ValueError):
        return len(str(raw_payload))


def _increment_if_present(counts: dict[str, int], value: Any) -> None:
    if value is None or value == "":
        return
    key = str(value)
    counts[key] = counts.get(key, 0) + 1


def _resolved_path(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    return Path(path).resolve()


def _normalize_query_fields(fields: list[str] | None) -> list[str] | None:
    if not fields:
        return None
    normalized = [field.strip() for field in fields if isinstance(field, str) and field.strip()]
    return normalized or None


def _parse_filter_expression(expression: str) -> dict[str, Any]:
    text = expression.strip()
    if not text:
        raise ValueError("filter expressions must not be empty")
    match = _FILTER_EXPRESSION_RE.match(text)
    if not match:
        raise ValueError(
            "Invalid filter expression. Use forms like `channel == github`, `ok == true`, or `count >= 10`."
        )
    return {
        "expression": text,
        "path": match.group("path"),
        "operator": match.group("operator"),
        "value": _parse_filter_value(match.group("value")),
    }


def _parse_filter_value(raw_value: str) -> Any:
    value = raw_value.strip()
    if not value:
        raise ValueError("filter values must not be empty")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"filter value is not valid JSON: {exc.msg}") from exc
    lowered = value.lower()
    if lowered in {"true", "false", "null"}:
        return json.loads(lowered)
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _record_matches_filter(record: dict[str, Any], parsed_filter: dict[str, Any]) -> bool:
    actual = _query_path_value(record, parsed_filter["path"])
    if actual is _MISSING:
        return False
    operator = parsed_filter["operator"]
    expected = parsed_filter["value"]
    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, dict):
            return str(expected) in actual
        if isinstance(actual, (list, tuple, set)):
            return any(item == expected or str(item) == str(expected) for item in actual)
        return False
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected

    comparison = _compare_query_values(actual, expected)
    if comparison is None:
        return False
    if operator == ">":
        return comparison > 0
    if operator == ">=":
        return comparison >= 0
    if operator == "<":
        return comparison < 0
    if operator == "<=":
        return comparison <= 0
    return False


def _compare_query_values(actual: Any, expected: Any) -> int | None:
    if actual is None or expected is None:
        return None
    if isinstance(actual, bool) or isinstance(expected, bool):
        return None
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if actual < expected:
            return -1
        if actual > expected:
            return 1
        return 0
    actual_text = actual if isinstance(actual, str) else str(actual)
    expected_text = expected if isinstance(expected, str) else str(expected)
    if actual_text < expected_text:
        return -1
    if actual_text > expected_text:
        return 1
    return 0


def _query_path_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index < 0 or index >= len(current):
                return _MISSING
            current = current[index]
            continue
        return _MISSING
    return current


def _project_query_match(match: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    if not fields:
        return match
    projected: dict[str, Any] = {}
    for field in fields:
        value = _query_path_value(match, field)
        projected[field] = None if value is _MISSING else value
    return projected
