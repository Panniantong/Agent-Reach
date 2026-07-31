# -*- coding: utf-8 -*-
"""Career intelligence helpers shared by Agent Reach and downstream tooling.

Agent Reach exposes a single ``career`` subcommand that fans out to upstream
MCP servers (LinkedIn MCP and JobSpy MCP), normalizes records, applies a
location filter and freshness gate, and emits deterministic JSON on stdout.

The job records use a ``source`` discriminator so downstream consumers can
collapse cross-board variants without losing source attribution:

* ``source = "linkedin"`` for rows from mcp-server-linkedin (job_id-based
  join key)
* ``source = "indeed"`` for rows from JobSpy MCP via Indeed search
  (jk= key + canonical viewjob URL)

A job's external_id is unique within its source. Cross-source dedup is left to
the consumer because JustApply already owns canonical fingerprint resolution.

This module is decoupled from any IO. Async upstream collectors live in
``collect_career_io`` (no public test surface) and are imported lazily so
unit tests can mock them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urlsplit

SUPPORTED_SOURCES = frozenset({"linkedin", "indeed"})
LOCATION_FILTERS: dict[str, dict[str, tuple[str, ...]]] = {
    "any_denmark": {"include": (), "exclude": ()},
    "cph": {
        "include": (
            r"\bcopenhagen\b",
            r"\bkøbenhavn\b",
            r"\bfrederiksberg\b",
        ),
        "exclude": (
            r"\bfredericia\b",
            r"\baarhus\b",
            r"\baalborg\b",
            r"\bodense\b",
            r"\bmalmö\b",
            r"\bgreater\s+region",
        ),
    },
    "greater_cph": {
        "include": (
            r"\bcopenhagen\b",
            r"\bkøbenhavn\b",
            r"\bfrederiksberg\b",
            r"\bgentofte\b",
            r"\bgladsaxe\b",
            r"\bhvidovre\b",
            r"\brødovre\b",
            r"\bballerup\b",
        ),
        "exclude": (
            r"\bmalmö\b",
            r"\bgreater\s+region",
        ),
    },
}
DEFAULT_HOURS_OLD = 168
DEFAULT_TERM_LIMIT = 3
DEFAULT_LOCATION_FILTER = "any_denmark"


class CareerCollectedJob(dict):
    """Convenience dict subclass for typed access in tests.

    Real collector code returns plain dicts; tests instantiate this subclass
    so attribute access behaves consistently.
    """

    @property
    def source(self) -> str:
        return str(self.get("source") or "")

    @property
    def external_id(self) -> str:
        return str(self.get("external_id") or "")

    @property
    def url(self) -> str:
        return str(self.get("url") or "")

    @property
    def title(self) -> str:
        return str(self.get("title") or "")

    @property
    def company(self) -> str:
        return str(self.get("company") or "")

    @property
    def location(self) -> str:
        return str(self.get("location") or "")

    @property
    def posted_at(self) -> str | None:
        value = self.get("posted_at")
        return str(value) if value else None

    @property
    def description(self) -> str | None:
        value = self.get("description")
        return str(value) if value else None

    @property
    def job_type(self) -> str | None:
        value = self.get("job_type")
        return str(value) if value else None

    @property
    def salary_range(self) -> str | None:
        value = self.get("salary_range")
        return str(value) if value else None


def LinkedInJob(**kwargs):  # pragma: no cover - thin alias for readability
    kwargs.setdefault("source", "linkedin")
    return CareerCollectedJob(**kwargs)


def IndeedJob(**kwargs):  # pragma: no cover - thin alias for readability
    kwargs.setdefault("source", "indeed")
    return CareerCollectedJob(**kwargs)


@dataclass(frozen=True)
class CareerOptions:
    query: str
    location_filter: str = DEFAULT_LOCATION_FILTER
    hours_old: int = DEFAULT_HOURS_OLD
    results_wanted: int = 10
    term_limit: int = DEFAULT_TERM_LIMIT


@dataclass
class CareerReport:
    query: str
    location_filter: str
    hours_old: int
    mode: str
    now: str
    sources: list[str]
    collected: int
    kept: int
    errors: dict[str, str] = field(default_factory=dict)
    kept_jobs: list[CareerCollectedJob] = field(default_factory=list)
    collected_jobs: list[CareerCollectedJob] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "location_filter": self.location_filter,
            "hours_old": self.hours_old,
            "mode": self.mode,
            "run_at": self.now,
            "sources": self.sources,
            "collected": self.collected,
            "kept": self.kept,
            "kept_jobs": [_job_to_dict(job) for job in self.kept_jobs],
            "collected_jobs": [_job_to_dict(job) for job in self.collected_jobs],
            "errors": dict(self.errors),
        }


def _job_to_dict(job: CareerCollectedJob | dict) -> dict[str, Any]:
    if isinstance(job, CareerCollectedJob):
        return {k: v for k, v in job.items() if v is not None}
    cleaned = {k: v for k, v in job.items() if v is not None}
    return cleaned


def _canonical_url(url: str) -> str:
    candidate = str(url or "").strip()
    if not candidate:
        return ""
    lowered = candidate.lower()
    has_known_scheme = lowered.startswith(("http://", "https://"))
    if not has_known_scheme:
        if ":" in candidate:
            # Reject javascript:, data:, ftp:, file:, and other custom schemes
            return ""
        if candidate.startswith("//"):
            return ""
        if candidate.startswith("/"):
            candidate = "https://www.linkedin.com" + candidate
        else:
            candidate = "https://" + candidate.lstrip("/")
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or parts.username or parts.password:
        return ""
    if parts.scheme.lower() not in {"http", "https"}:
        return ""

    path = parts.path.rstrip("/") or "/"

    if host.endswith("linkedin.com"):
        match = re.search(r"/jobs/view/(?:.*-)?(\d{8,})", path)
        if match:
            return f"https://www.linkedin.com/jobs/view/{match.group(1)}"

    if host.endswith("indeed.com"):
        if path.lower() == "/viewjob":
            job_keys = parse_qs(parts.query).get("jk", [])
            if job_keys:
                return f"https://{host}/viewjob?{urlencode({'jk': job_keys[0]})}"

    return f"https://{host}{path}"


def _linkedin_posted_at(text: str, now_iso: str) -> str | None:
    if not text:
        return None
    low = text.lower()
    now = _parse_iso8601(now_iso)
    if now is None:
        return None
    if "i går" in low or "yesterday" in low:
        return _iso_offset(now, days=-1)
    patterns = (
        (r"(\d+)\s*(?:minut|minutter|minute|minutes)\b", "minutes"),
        (r"(\d+)\s*(?:time|timer|hour|hours)\b", "hours"),
        (r"(\d+)\s*(?:dag|dage|day|days)\b", "days"),
        (r"(\d+)\s*(?:uge|uger|week|weeks)\b", "weeks"),
        (r"(\d+)\s*(?:måned|måneder|month|months)\b", "months"),
    )
    for pattern, unit in patterns:
        match = re.search(pattern, low)
        if not match:
            continue
        amount = int(match.group(1))
        delta_seconds = int(amount) * {
            "minutes": 60,
            "hours": 3600,
            "days": 86400,
            "weeks": 604800,
            "months": 2592000,
        }[unit]
        return _iso_offset_seconds(now, -delta_seconds)
    return None


def _indeed_posted_at(text: str, now_iso: str) -> str | None:
    if not text:
        return None
    text = str(text).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text}T00:00:00+00:00"
    return text.replace("Z", "+00:00")


def _parse_iso8601(value: str):
    from datetime import datetime

    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso_offset(value, days: int):
    from datetime import timedelta

    return (value + timedelta(days=days)).isoformat()


def _iso_offset_seconds(value, seconds: int):
    from datetime import timedelta

    return (value + timedelta(seconds=seconds)).isoformat()


def title_matches(title: str, query: str) -> bool:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", (title or "").lower())
        if token not in {"senior", "junior", "lead", "sr", "jr", "head"}
    }
    query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", (query or "").lower())
        if token not in {"senior", "junior", "lead", "sr", "jr", "head"}
    }
    if not query_tokens:
        return True
    overlap = len(query_tokens & tokens)
    if len(query_tokens) <= 2:
        required = len(query_tokens)
    else:
        required = (2 * len(query_tokens) + 2) // 3
    return overlap >= required


def location_passes(
    location: str,
    rules: dict[str, tuple[str, ...]],
    *,
    policy: str | None = None,
) -> bool:
    """Return whether *location* falls inside a normalized ``rules`` block.

    ``policy`` is the name of the LOCATION_FILTERS entry to look up. When
    supplied, the rules are resolved from LOCATION_FILTERS. When omitted, the
    caller passes rules directly — used by the unit tests with explicit
    include/exclude tuples.
    """
    if policy is not None:
        resolved = LOCATION_FILTERS.get(policy)
        if resolved is None:
            raise ValueError(f"Unknown location_filter: {policy}")
        rules = resolved
    if not rules["include"] and not rules["exclude"]:
        return True
    if not location:
        return False
    if _postcode_in_cph(location):
        return True
    low = location.lower()
    if any(re.search(pattern, low) for pattern in rules["include"]):
        return all(not re.search(pattern, low) for pattern in rules["exclude"])
    return False


def _postcode_in_cph(location: str) -> bool:
    for match in re.finditer(r"\b(\d{4})\b", location or ""):
        postcode = int(match.group(1))
        if 1050 <= postcode <= 1799:
            return True
    return False


def select_posted_within(
    jobs: Iterable[dict], *, hours_old: int, now_iso: str
) -> Iterable[dict]:
    from datetime import timedelta

    now = _parse_iso8601(now_iso)
    if now is None:
        return []
    window = timedelta(hours=hours_old)
    buffer = timedelta(hours=2)
    out: list[dict] = []
    for job in jobs:
        posted_at = job.get("posted_at")
        if not posted_at:
            continue
        posted = _parse_iso8601(str(posted_at))
        if posted is None:
            continue
        age = now - posted
        if timedelta(hours=-24) <= age <= window + buffer:
            out.append(job)
    return out


def _record_key(job: dict) -> tuple[str, str]:
    return str(job.get("source") or ""), str(job.get("external_id") or job.get("url") or "")


def _record_richness(job: dict) -> tuple[int, int]:
    return (
        len(str(job.get("description") or "")),
        sum(value not in (None, "") for value in job.values()),
    )


def _dedupe_within_source(jobs: list[dict]) -> list[dict]:
    winners: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for job in jobs:
        key = _record_key(job)
        if not all(key):
            continue
        normalized = CareerCollectedJob(job)
        if key not in winners:
            winners[key] = normalized
            order.append(key)
        elif _record_richness(job) > _record_richness(winners[key]):
            winners[key] = normalized
    return [winners[key] for key in order]


def filter_career_jobs(
    jobs: list[dict], *, options: CareerOptions, now_iso: str
) -> list[CareerCollectedJob]:
    rules = LOCATION_FILTERS.get(options.location_filter)
    if rules is None:
        raise ValueError(f"Unknown location_filter: {options.location_filter}")

    accepted: list[CareerCollectedJob] = []
    for job in jobs:
        title = str(job.get("title") or "")
        location = str(job.get("location") or "")
        if not title_matches(title, options.query):
            continue
        if not location_passes(location, rules):
            continue
        accepted.append(CareerCollectedJob(job))

    accepted = _dedupe_within_source(accepted)
    accepted = list(
        select_posted_within(accepted, hours_old=options.hours_old, now_iso=now_iso)
    )
    return [CareerCollectedJob(job) for job in accepted]  # type: ignore[misc]  # noqa: E501


def format_career_json(
    *,
    collected: list[dict],
    options: CareerOptions,
    now_iso: str,
    mode: str,
    errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    kept = filter_career_jobs(collected, options=options, now_iso=now_iso)
    report = CareerReport(
        query=options.query,
        location_filter=options.location_filter,
        hours_old=options.hours_old,
        mode=mode,
        now=now_iso,
        sources=sorted({str(job.get("source") or "unknown") for job in collected}),
        collected=len(collected),
        kept=len(kept),
        errors=dict(errors or {}),
        kept_jobs=[CareerCollectedJob(job) for job in kept],
        collected_jobs=[CareerCollectedJob(job) for job in collected],
    )
    return report.to_dict()


def collect_linkedin_jobs(
    options: CareerOptions, *, now_iso: str
) -> list[CareerCollectedJob]:
    """Default per-source collector delegated to the IO module.

    Tests can monkeypatch this attribute in ``agent_reach.career``; the
    orchestrator below binds to the module-level name, not the inner import.
    """

    from agent_reach.career_io import collect_linkedin_jobs as _collect

    return _collect(options, now_iso=now_iso)


def collect_indeed_jobs(
    options: CareerOptions, *, now_iso: str
) -> list[CareerCollectedJob]:
    from agent_reach.career_io import collect_indeed_jobs as _collect

    return _collect(options, now_iso=now_iso)


def collect_career_jobs(
    options: CareerOptions,
    *,
    sources: set[str],
    now_iso: str | None = None,
    return_errors: bool = False,
) -> list[dict] | tuple[list[dict], dict[str, str]]:
    """Synchronous orchestration over upstream MCP collectors.

    The actual MCP transport lives in :mod:`agent_reach.career_io` so this
    module can be unit-tested without an active MCP server.
    """
    if not 1 <= options.term_limit <= 20:
        raise ValueError(
            f"term_limit must be between 1 and 20 (got {options.term_limit!r})"
        )
    unsupported = sources - SUPPORTED_SOURCES
    if unsupported:
        raise ValueError(
            "Unsupported sources: " + ", ".join(sorted(unsupported))
        )
    if now_iso is None:
        now_iso = _default_now_iso()

    collected: list[dict] = []
    errors: dict[str, str] = {}

    if "linkedin" in sources:
        try:
            collected.extend(
                collect_linkedin_jobs(options=options, now_iso=now_iso)
            )
        except Exception as exc:  # noqa: BLE001
            errors["linkedin"] = f"{type(exc).__name__}: {exc}"

    if "indeed" in sources:
        try:
            collected.extend(
                collect_indeed_jobs(options=options, now_iso=now_iso)
            )
        except Exception as exc:  # noqa: BLE001
            errors["indeed"] = f"{type(exc).__name__}: {exc}"

    filtered = filter_career_jobs(collected, options=options, now_iso=now_iso)

    if return_errors:
        return list(filtered), dict(errors)
    return list(filtered)


def _default_now_iso() -> str:
    """Return the current UTC ISO timestamp with explicit timezone offset."""

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def collect_career_command(
    *,
    query: str,
    sources: set[str],
    location_filter: str,
    hours_old: int,
    term_limit: int,
    results_wanted: int,
    mode: str = "dry_run",
) -> dict[str, Any]:
    options = CareerOptions(
        query=query,
        location_filter=location_filter,
        hours_old=hours_old,
        term_limit=term_limit,
        results_wanted=results_wanted,
    )
    now_iso = _default_now_iso()
    collected, errors = collect_career_jobs(
        options,
        sources=sources,
        now_iso=now_iso,
        return_errors=True,
    )
    return format_career_json(
        collected=collected,
        options=options,
        now_iso=now_iso,
        mode=mode,
        errors=errors,
    )
