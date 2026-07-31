"""Live MCP collectors used by the Agent Reach ``career`` subcommand.

The collectors in this module spawn the local LinkedIn and Indeed MCP servers
(MCP stdio) and gather raw rows from each. They are intentionally verbose —
the synchronous orchestrator in :mod:`agent_reach.career` writes a small
JSON report on stdout, so any upstream banner or Rich formatting would corrupt
that output.

If neither MCP server is reachable on the current host, both collectors return
an empty list and the orchestrator records the failure in the report's
``errors`` block instead of raising. This keeps a single broken backend from
silently killing the other's data.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .career import (
    CareerCollectedJob,
    CareerOptions,
    _canonical_url,
    _indeed_posted_at,
    _linkedin_posted_at,
)

HERMES_DIR = Path.home() / ".hermes"

LINKEDIN_SERVER_PARAMS = {
    "command": "/opt/homebrew/bin/uvx",
    "args": [
        "mcp-server-linkedin==4.20.0",
        "--no-auto-import",
        "--timeout",
        "10000",
        "--tool-timeout",
        "300",
        "--browser-idle-timeout",
        "300",
    ],
    "env": {
        "AUTO_IMPORT_FROM_BROWSER": "false",
        "LOG_LEVEL": "ERROR",
        "FASTMCP_NO_BANNER": "1",
        "FASTMCP_QUIET": "1",
        "NO_COLOR": "1",
        "PYTHONIOENCODING": "utf-8",
    },
}

JOBSPY_SERVER_PARAMS = {
    "command": str(HERMES_DIR / "venvs" / "jobspy-mcp" / "bin" / "python"),
    "args": [str(HERMES_DIR / "bin" / "jobspy_mcp.py")],
    "env": {
        "FASTMCP_NO_BANNER": "1",
        "FASTMCP_QUIET": "1",
        "NO_COLOR": "1",
        "LOG_LEVEL": "ERROR",
        "PYTHONIOENCODING": "utf-8",
    },
}


@contextlib.asynccontextmanager
async def _silent_stdio(server_params: dict):
    """Open the MCP stdio connection while discarding the subprocess banner."""

    import contextlib

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=server_params["command"],
        args=list(server_params.get("args", []) or []),
        env={**os.environ, **server_params.get("env", {})},
    )
    devnull = open(os.devnull, "w")
    try:
        with contextlib.redirect_stderr(devnull):
            async with stdio_client(params) as pair:
                yield ClientSession(pair[0], pair[1])
    finally:
        devnull.close()


async def _call_tool(session, name: str, arguments: dict) -> dict:
    """Invoke a tool and return the un-wrapped result, raising on MCP errors."""

    response = await session.call_tool(name, arguments)
    if getattr(response, "isError", False):
        messages = [
            str(getattr(content, "text", "")).strip()
            for content in getattr(response, "content", []) or []
            if getattr(content, "text", None)
        ]
        raise RuntimeError("; ".join(messages) or f"{name} failed")
    structured = getattr(response, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for content in getattr(response, "content", []) or []:
        text = getattr(content, "text", None)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _linkedin_from_detail(payload: dict, *, job_id: str, now_iso: str) -> CareerCollectedJob | None:
    sections = payload.get("sections") or {}
    detail_text = str(sections.get("job_details") or "")
    if not detail_text and sections:
        detail_text = str(next(iter(sections.values())) or "")
    lines = [line.strip() for line in detail_text.splitlines() if line.strip()]
    if len(lines) < 3:
        return None
    company = lines[0]
    title = re_sub_with_verification(lines[1])
    metadata = lines[2]
    location = metadata.split(" · ", 1)[0].strip()
    posted_at = _linkedin_posted_at(metadata, now_iso)
    url = _canonical_url(
        str(payload.get("url") or f"https://www.linkedin.com/jobs/view/{job_id}")
    )
    if not title or not company or not location or not url:
        return None
    job = CareerCollectedJob(
        source="linkedin",
        url=url,
        title=title,
        company=company,
        location=location,
        country="DK",
        external_id=job_id,
    )
    if posted_at:
        job["posted_at"] = posted_at
    return job


def re_sub_with_verification(text: str) -> str:
    """Strip the LinkedIn 'with verification' suffix from titles."""

    import re

    return re.sub(r"\s+with verification$", "", text or "", flags=re.IGNORECASE).strip()


def _indeed_from_payload(job: dict, *, now_iso: str) -> CareerCollectedJob | None:
    from urllib.parse import parse_qs, urlsplit

    url = _canonical_url(str(job.get("job_url") or ""))
    if not url:
        return None
    title = str(job.get("title") or "").strip()
    company = str(job.get("company") or "").strip()
    if not title or not company:
        return None
    parsed = parse_qs(urlsplit(url).query)
    jk = parsed.get("jk", [None])[0]
    if not jk:
        return None
    job_data = CareerCollectedJob(
        source="indeed",
        url=url,
        title=title,
        company=company,
        location=str(job.get("location") or "Denmark").strip(),
        country="DK",
        external_id=jk,
    )
    posted_at = _indeed_posted_at(str(job.get("date_posted") or ""), now_iso)
    if posted_at:
        job_data["posted_at"] = posted_at
    description = str(job.get("description") or "").strip()
    if description:
        job_data["description"] = description
    job_type = str(job.get("job_type") or "").strip().lower()
    if job_type:
        aliases = {
            "fulltime": "full_time",
            "parttime": "part_time",
        }
        job_data["job_type"] = aliases.get(job_type, job_type)
    return job_data


async def _linkedin_async(options: CareerOptions, *, now_iso: str) -> list[CareerCollectedJob]:
    try:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise RuntimeError("mcp client not installed") from exc

    params = {
        "command": LINKEDIN_SERVER_PARAMS["command"],
        "args": LINKEDIN_SERVER_PARAMS["args"],
        "env": {
            **os.environ,
            **LINKEDIN_SERVER_PARAMS.get("env", {}),
        },
    }
    jobs: list[CareerCollectedJob] = []
    stdout_devnull = open(os.devnull, "w")
    stderr_devnull = open(os.devnull, "w")
    try:
        from mcp import StdioServerParameters
        params_obj = StdioServerParameters(
            command=params["command"],
            args=params["args"],
            env=params["env"],
        )
        # Replace both streams at the Python interpreter level so any Rich
        # banners emitted by the LinkedIn MCP server before/after startup
        # never reach the JSON-RPC write pipe.
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout = stdout_devnull
        sys.stderr = stderr_devnull
        try:
            async with stdio_client(params_obj) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "search_jobs",
                        {
                            "keywords": options.query,
                            "location": "Denmark",
                            "date_posted": "past_week",
                            "sort_by": "most_recent",
                        },
                    )
                    payload = _call_result_dict(result)
                    for job_id in payload.get("job_ids", []):
                        detail = await session.call_tool(
                            "get_job_details",
                            {"job_id": str(job_id)},
                        )
                        job = _linkedin_from_detail(
                            _call_result_dict(detail),
                            job_id=str(job_id),
                            now_iso=now_iso,
                        )
                        if job is not None:
                            jobs.append(job)
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
    finally:
        stdout_devnull.close()
        stderr_devnull.close()
    return jobs


async def _indeed_async(
    options: CareerOptions, *, now_iso: str
) -> list[CareerCollectedJob]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise RuntimeError("mcp client not installed") from exc

    params_obj = StdioServerParameters(
        command=JOBSPY_SERVER_PARAMS["command"],
        args=JOBSPY_SERVER_PARAMS["args"],
        env={**os.environ, **JOBSPY_SERVER_PARAMS.get("env", {})},
    )
    jobs: list[CareerCollectedJob] = []
    stdout_devnull = open(os.devnull, "w")
    stderr_devnull = open(os.devnull, "w")
    try:
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout = stdout_devnull
        sys.stderr = stderr_devnull
        try:
            async with stdio_client(params_obj) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "search_jobs",
                        {
                            "search_term": options.query,
                            "location": "Denmark",
                            "country_indeed": "Denmark",
                            "results_wanted": options.results_wanted,
                            "hours_old": options.hours_old,
                        },
                    )
                    payload = _call_result_dict(result)
                    for raw_job in payload.get("jobs", []):
                        job = _indeed_from_payload(raw_job, now_iso=now_iso)
                        if job is not None:
                            jobs.append(job)
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
    finally:
        stdout_devnull.close()
        stderr_devnull.close()
    return jobs


def _call_result_dict(result: Any) -> dict:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for content in getattr(result, "content", []) or []:
        text = getattr(content, "text", None)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def collect_linkedin_jobs(options: CareerOptions, *, now_iso: str) -> list[CareerCollectedJob]:
    """Synchronous wrapper around :func:`_linkedin_async`."""

    import asyncio

    return asyncio.run(_linkedin_async(options, now_iso=now_iso))


def collect_indeed_jobs(options: CareerOptions, *, now_iso: str) -> list[CareerCollectedJob]:
    """Synchronous wrapper around :func:`_indeed_async`."""

    import asyncio

    return asyncio.run(_indeed_async(options, now_iso=now_iso))


def utcnow_iso() -> str:
    """Return the current UTC ISO timestamp with explicit timezone offset."""

    return datetime.now(UTC).isoformat()
