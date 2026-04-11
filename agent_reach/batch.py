# -*- coding: utf-8 -*-
"""Batch collection runner for research plans."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from agent_reach import __version__
from agent_reach.client import AgentReachClient
from agent_reach.ledger import (
    default_run_id,
    iter_ledger_records,
    save_collection_result,
    save_collection_result_sharded,
)
from agent_reach.operation_contracts import (
    OperationContractError,
    batch_option_values,
    validate_operation_options,
)
from agent_reach.schemas import SCHEMA_VERSION, utc_timestamp


class BatchPlanError(Exception):
    """Raised when a batch plan cannot be executed."""


def run_batch_plan(
    plan_path: str | Path,
    *,
    save_path: str | Path | None = None,
    save_dir: str | Path | None = None,
    shard_by: str = "channel",
    concurrency: int = 1,
    resume: bool = False,
    checkpoint_every: int = 100,
    quality: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Run a JSON research plan and append results to a ledger."""

    if bool(save_path) == bool(save_dir):
        raise BatchPlanError("Provide exactly one of save_path or save_dir")
    if concurrency < 1:
        raise BatchPlanError("concurrency must be greater than or equal to 1")
    if checkpoint_every < 1:
        raise BatchPlanError("checkpoint-every must be greater than or equal to 1")
    if save_dir is not None:
        save_dir_path = Path(save_dir)
        if save_dir_path.exists() and not save_dir_path.is_dir():
            raise BatchPlanError("save_dir must point to a directory")

    path = Path(plan_path)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BatchPlanError(f"Could not read batch plan: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BatchPlanError(f"Invalid batch plan JSON: {exc.msg}") from exc
    if not isinstance(plan, dict):
        raise BatchPlanError("batch plan must be a JSON object")

    queries = plan.get("queries") or plan.get("pilot_queries") or []
    if not isinstance(queries, list):
        raise BatchPlanError("batch plan queries must be a list")
    normalized_queries = [_normalize_query(query, index) for index, query in enumerate(queries)]

    run_id = str(plan.get("run_id") or default_run_id())
    failure_policy = str(plan.get("failure_policy") or "partial")
    requested_quality = quality or plan.get("quality_profile") or "precision"
    save_target = save_dir or save_path
    completed_keys = _completed_query_keys(save_target) if resume and save_target is not None else set()
    statuses: list[dict[str, Any] | None] = [None] * len(normalized_queries)
    checkpoints: list[dict[str, Any]] = []
    written_targets: set[str] = set()
    started_at = utc_timestamp()

    def execute(index: int, query: dict[str, Any]) -> dict[str, Any]:
        key = _query_key(query)
        if resume and key in completed_keys:
            return {
                "query_id": query["query_id"],
                "channel": query["channel"],
                "operation": query["operation"],
                "input": query["input"],
                "limit": query.get("limit"),
                "intent": query.get("intent"),
                "source_role": query.get("source_role"),
                "status": "skipped",
                "reason": "resume_existing",
                "ok": True,
                "count": 0,
            }

        client = AgentReachClient()
        kwargs: dict[str, Any] = {}
        if query.get("limit") is not None:
            kwargs["limit"] = int(query["limit"])
        if query.get("body_mode") is not None:
            kwargs["body_mode"] = query["body_mode"]
        if query.get("crawl_query") is not None:
            kwargs["crawl_query"] = query["crawl_query"]
        for option_name in ("page_size", "max_pages", "cursor", "page", "since", "until"):
            if query.get(option_name) is not None:
                kwargs[option_name] = query[option_name]
        payload = client.collect(query["channel"], query["operation"], query["input"], **kwargs)
        error = payload.get("error")
        return {
            "_payload": payload,
            "_query": query,
            "query_id": query["query_id"],
            "channel": query["channel"],
            "operation": query["operation"],
            "input": query["input"],
            "limit": query.get("limit"),
            "intent": query.get("intent"),
            "source_role": query.get("source_role"),
            "body_mode": query.get("body_mode"),
            "crawl_query": query.get("crawl_query"),
            "page_size": query.get("page_size"),
            "max_pages": query.get("max_pages"),
            "cursor": query.get("cursor"),
            "page": query.get("page"),
            "since": query.get("since"),
            "until": query.get("until"),
            "status": "ok" if payload.get("ok") else "error",
            "ok": bool(payload.get("ok")),
            "count": len(payload.get("items") or []),
            "urls": [item.get("url") for item in payload.get("items") or [] if item.get("url")],
            "error_code": error["code"] if error else None,
            "error_message": error["message"] if error else None,
        }

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(execute, index, query): index
            for index, query in enumerate(normalized_queries)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                status = future.result()
            except Exception as exc:
                status = {
                    "query_id": f"q{index + 1:02d}",
                    "status": "error",
                    "ok": False,
                    "count": 0,
                    "error_code": "batch_error",
                    "error_message": str(exc),
                }
            payload = status.pop("_payload", None)
            query = status.pop("_query", None)
            if payload is not None and query is not None:
                try:
                    if save_path is not None:
                        save_collection_result(
                            save_path,
                            payload,
                            run_id=run_id,
                            input_value=query["input"],
                            intent=query.get("intent"),
                            query_id=query["query_id"],
                            source_role=query.get("source_role"),
                        )
                        written_targets.add(str(Path(save_path)))
                    elif save_dir is not None:
                        _record, shard_path = save_collection_result_sharded(
                            save_dir,
                            payload,
                            run_id=run_id,
                            shard_by=shard_by,
                            input_value=query["input"],
                            intent=query.get("intent"),
                            query_id=query["query_id"],
                            source_role=query.get("source_role"),
                        )
                        written_targets.add(str(shard_path))
                except (OSError, TypeError, ValueError) as exc:
                    status.update(
                        {
                            "status": "error",
                            "ok": False,
                            "error_code": "ledger_error",
                            "error_message": str(exc),
                        }
                    )
            statuses[index] = status
            completed = len([item for item in statuses if item is not None])
            if completed % checkpoint_every == 0:
                checkpoints.append(_checkpoint_summary(statuses, completed=completed))

    final_statuses = [status for status in statuses if status is not None]
    finished_at = utc_timestamp()
    summary = _summary(final_statuses)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": finished_at,
        "command": "batch",
        "cli_version": __version__,
        "plan": str(path),
        "save_mode": "sharded" if save_dir is not None else "file",
        "save": str(save_path) if save_path is not None else None,
        "save_dir": str(save_dir) if save_dir is not None else None,
        "shard_by": shard_by if save_dir is not None else None,
        "save_targets": sorted(written_targets),
        "run_id": run_id,
        "quality_profile": requested_quality,
        "failure_policy": failure_policy,
        "concurrency": concurrency,
        "resume": resume,
        "started_at": started_at,
        "finished_at": finished_at,
        "summary": summary,
        "queries": final_statuses,
        "checkpoints": checkpoints,
    }
    exit_code = 1 if failure_policy == "strict" and summary["errors"] else 0
    return payload, exit_code


def render_batch_text(payload: dict[str, Any]) -> str:
    """Render a batch manifest for humans."""

    summary = payload["summary"]
    lines = [
        "Agent Reach Batch",
        "========================================",
        f"Plan: {payload['plan']}",
        (
            f"Save dir: {payload['save_dir']} (shard_by={payload['shard_by']})"
            if payload.get("save_mode") == "sharded"
            else f"Save: {payload['save']}"
        ),
        f"Run ID: {payload['run_id']}",
        f"Queries: {summary['total']} total, {summary['ok']} ok, {summary['errors']} errors, {summary['skipped']} skipped",
        f"Items: {summary['items']}",
    ]
    return "\n".join(lines)


def _normalize_query(raw_query: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw_query, dict):
        raise BatchPlanError(f"query {index + 1} must be a JSON object")
    missing = [field for field in ("channel", "operation", "input") if not raw_query.get(field)]
    if missing:
        raise BatchPlanError(f"query {index + 1} is missing required field(s): {', '.join(missing)}")
    query = dict(raw_query)
    query["query_id"] = str(query.get("query_id") or f"q{index + 1:02d}")
    query["channel"] = str(query["channel"])
    query["operation"] = str(query["operation"])
    query["input"] = str(query["input"])
    if query.get("query") is not None and query.get("crawl_query") is None:
        query["crawl_query"] = query["query"]
    try:
        validate_operation_options(
            query["channel"],
            query["operation"],
            batch_option_values(query),
            strict_contract=True,
        )
    except OperationContractError as exc:
        raise BatchPlanError(f"query {index + 1} is invalid: {exc.message}") from exc
    return query


def _query_key(
    query: dict[str, Any],
) -> tuple[
    str,
    str,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    limit = query.get("limit")
    return (
        str(query.get("channel")),
        str(query.get("operation")),
        str(query.get("input")),
        str(limit) if limit is not None else None,
        str(query.get("intent")) if query.get("intent") is not None else None,
        str(query.get("body_mode")) if query.get("body_mode") is not None else None,
        str(query.get("crawl_query")) if query.get("crawl_query") is not None else None,
        str(query.get("page_size")) if query.get("page_size") is not None else None,
        str(query.get("max_pages")) if query.get("max_pages") is not None else None,
        str(query.get("cursor")) if query.get("cursor") is not None else None,
        str(query.get("page")) if query.get("page") is not None else None,
        str(query.get("since")) if query.get("since") is not None else None,
        str(query.get("until")) if query.get("until") is not None else None,
    )


def _completed_query_keys(
    path: str | Path | None,
) -> set[
    tuple[
        str,
        str,
        str,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
    ]
]:
    if path is None:
        return set()

    completed: set[
        tuple[
            str,
            str,
            str,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
        ]
    ] = set()
    for record in iter_ledger_records(path, allow_missing=True):
        if not isinstance(record, dict) or record.get("record_type") != "collection_result":
            continue
        raw_result = record.get("result")
        result: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
        raw_meta = result.get("meta")
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        query = {
            "channel": record.get("channel") or result.get("channel"),
            "operation": record.get("operation") or result.get("operation"),
            "input": record.get("input") if record.get("input") is not None else meta.get("input"),
            "limit": meta.get("requested_limit") if meta.get("requested_limit") is not None else meta.get("limit"),
            "intent": record.get("intent") if record.get("intent") is not None else meta.get("intent"),
            "body_mode": meta.get("body_mode"),
            "crawl_query": meta.get("crawl_query"),
            "page_size": meta.get("requested_page_size"),
            "max_pages": meta.get("requested_max_pages"),
            "cursor": meta.get("requested_cursor"),
            "page": meta.get("requested_page"),
            "since": meta.get("since"),
            "until": meta.get("until"),
        }
        if query["channel"] and query["operation"] and query["input"]:
            completed.add(_query_key(query))
    return completed


def _checkpoint_summary(
    statuses: list[dict[str, Any] | None],
    *,
    completed: int,
) -> dict[str, Any]:
    current = [status for status in statuses if status is not None]
    return {"completed": completed, **_summary(current)}


def _summary(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    urls = []
    source_roles: dict[str, int] = {}
    for status in statuses:
        role = status.get("source_role")
        if role:
            source_roles[str(role)] = source_roles.get(str(role), 0) + 1
        for url in status.get("urls") or []:
            urls.append(str(url))
    unique_urls = set(urls)
    return {
        "total": len(statuses),
        "ok": sum(1 for status in statuses if status.get("status") == "ok"),
        "errors": sum(1 for status in statuses if status.get("status") == "error"),
        "skipped": sum(1 for status in statuses if status.get("status") == "skipped"),
        "items": sum(int(status.get("count") or 0) for status in statuses),
        "unique_urls": len(unique_urls),
        "duplicate_urls": len(urls) - len(unique_urls),
        "source_roles": source_roles,
    }
