# -*- coding: utf-8 -*-
"""Tests for the ``agent-reach career`` subcommand.

The subcommand wraps two upstream MCP tools (LinkedIn MCP and JobSpy MCP)
behind a single CLI surface, applies the Cph location filter and freshness
gate, and emits deterministic JSON ready for downstream piping (Hermes bridge
or any other ingest destination).
"""

from __future__ import annotations

import json

import pytest

from agent_reach.career import (
    CareerCollectedJob,
    CareerOptions,
    IndeedJob,
    LinkedInJob,
    _canonical_url,
    _indeed_posted_at,
    _linkedin_posted_at,
    collect_career_jobs,
    filter_career_jobs,
    format_career_json,
    location_passes,
    select_posted_within,
    title_matches,
)


def _linkedin_payload(job_id: str, title: str, company: str, location: str) -> dict:
    return {
        "url": f"https://www.linkedin.com/jobs/view/{job_id}",
        "sections": {
            "job_details": (
                f"{company}\n{title}\n{location} · Genopslået 1 dag siden · "
                f"31 personer klikkede på Ansøg\n\nOm jobbet\nLong enough description."
            )
        },
    }


def test_canonical_url_keeps_linkedin_job_id_and_drops_tracking():
    raw = "https://www.linkedin.com/jobs/view/4435069132/?trackingId=abc&utm=tracker"

    canonical = _canonical_url(raw)

    assert canonical == "https://www.linkedin.com/jobs/view/4435069132"


def test_canonical_url_keeps_indeed_viewjob_jk_only():
    raw = (
        "https://dk.indeed.com/viewjob?jk=975002cb6e596c69&utm_source=tracker&fromage=7"
    )

    canonical = _canonical_url(raw)

    assert canonical == "https://dk.indeed.com/viewjob?jk=975002cb6e596c69"


def test_canonical_url_rejects_userinfo_and_non_http():
    for bad in (
        "javascript:alert(1)",
        "https://user:pass@linkedin.com/jobs/view/1",
        "",
        "ftp://example.com/job",
    ):
        assert _canonical_url(bad) == ""


def test_linkedin_posted_at_parses_danish_relative_and_yesterday():
    now = "2026-07-31T06:22:16+00:00"
    text = "Aarhus, Region Midtjylland, Danmark · Genopslået 6 dage siden · ..."

    parsed = _linkedin_posted_at(text, now_iso=now)

    assert parsed is not None
    assert parsed.startswith("2026-07-25")


def test_linkedin_posted_at_handles_i_gaar_shortcut():
    now = "2026-07-31T06:22:16+00:00"

    parsed = _linkedin_posted_at("København · I går", now_iso=now)

    assert parsed is not None
    assert parsed.startswith("2026-07-30")


def test_linkedin_posted_at_returns_none_when_unparseable():
    assert _linkedin_posted_at("København", "2026-07-31T06:22:16+00:00") is None


def test_indeed_posted_at_normalizes_dashed_date_to_iso():
    parsed = _indeed_posted_at("2026-07-29", "2026-07-31T06:22:16+00:00")

    assert parsed == "2026-07-29T00:00:00+00:00"


def test_title_matches_rejects_broad_operations_false_positive():
    assert title_matches(
        "IT Operations Senior Specialist - Automation", "IT Operations"
    )
    assert not title_matches(
        "Strategy & Operations Manager - Partnerships", "IT Operations"
    )


def test_location_passes_cph_accepts_only_copenhagen_postcodes():
    rules = {"include": (r"\bcopenhagen\b", r"\bkøbenhavn\b"), "exclude": ()}

    assert location_passes("København, Danmark", rules)
    assert location_passes("Copenhagen, Denmark", rules)
    assert location_passes("København K 1050", rules)
    assert location_passes("Frederiksberg C 1606", rules)
    assert not location_passes("Fredericia, Region Syddanmark, Danmark", rules)
    assert not location_passes("Aarhus, Region Midtjylland, Danmark", rules)
    assert not location_passes("Lyngby 2800", rules)


def test_location_passes_any_denmark_allows_everywhere():
    rules = {"include": (), "exclude": ()}

    assert location_passes("Fredericia", rules)
    assert location_passes("Malmö", rules)


def test_location_passes_unknown_policy_raises():
    with pytest.raises(ValueError, match="Unknown location_filter"):
        location_passes("Copenhagen", {"include": (), "exclude": ()}, policy="nope")


def test_select_posted_within_keeps_only_fresh_jobs():
    now = "2026-07-31T06:22:16+00:00"
    jobs = [
        {"posted_at": "2026-07-31T00:00:00+00:00"},
        {"posted_at": "2026-07-24T06:00:00+00:00"},
        {"posted_at": "2026-07-23T06:00:00+00:00"},
        {"posted_at": None},
        {"posted_at": "garbage"},
    ]

    kept = list(select_posted_within(jobs, hours_old=168, now_iso=now))

    assert len(kept) == 2
    assert all(isinstance(job, dict) for job in kept)


def test_filter_career_jobs_applies_title_location_and_freshness():
    options = CareerOptions(
        query="IT Operations",
        location_filter="cph",
        hours_old=168,
    )
    now = "2026-07-31T06:22:16+00:00"

    inside = LinkedInJob(
        source="linkedin",
        url="https://www.linkedin.com/jobs/view/11",
        title="IT Operations Senior Specialist - Automation",
        company="DLG",
        location="København, Region Hovedstaden, Danmark",
        external_id="11",
        posted_at="2026-07-30T06:00:00+00:00",
        raw={"probe": "linkedin"},
    )
    outside = LinkedInJob(
        source="linkedin",
        url="https://www.linkedin.com/jobs/view/22",
        title="IT Operations Senior Specialist - Automation",
        company="DLG",
        location="Fredericia, Region Syddanmark, Danmark",
        external_id="22",
        posted_at="2026-07-30T06:00:00+00:00",
        raw={"probe": "linkedin"},
    )
    stale = LinkedInJob(
        source="linkedin",
        url="https://www.linkedin.com/jobs/view/33",
        title="IT Operations Senior Specialist - Automation",
        company="DLG",
        location="København, Region Hovedstaden, Danmark",
        external_id="33",
        posted_at="2026-07-22T06:00:00+00:00",
        raw={"probe": "linkedin"},
    )

    kept = filter_career_jobs([inside, outside, stale], options=options, now_iso=now)

    assert [job.external_id for job in kept] == ["11"]


def test_format_career_json_is_pure_data_with_consistent_schema():
    options = CareerOptions(
        query="IT Operations",
        location_filter="cph",
        hours_old=168,
    )
    now = "2026-07-31T06:22:16+00:00"

    payload = format_career_json(
        collected=[
            CareerCollectedJob(
                source="linkedin",
                url="https://www.linkedin.com/jobs/view/1",
                external_id="1",
                title="IT Operations Senior Specialist - Automation",
                company="DLG",
                location="København, Region Hovedstaden, Danmark",
                posted_at="2026-07-30T06:00:00+00:00",
                raw={"probe": "linkedin"},
            )
        ],
        options=options,
        now_iso=now,
        mode="dry_run",
    )

    text = json.dumps(payload)
    assert "IT Operations Senior Specialist - Automation" in text
    assert "linkedin" in text
    assert payload["mode"] == "dry_run"
    assert payload["query"] == "IT Operations"
    assert payload["location_filter"] == "cph"
    assert payload["collected"] == 1
    assert payload["kept"] == 1
    assert payload["kept_jobs"][0]["external_id"] == "1"


def test_filter_career_jobs_dedupes_keeps_richer_record_within_source():
    options = CareerOptions(
        query="IT Operations",
        location_filter="any_denmark",
        hours_old=168,
    )
    now = "2026-07-31T06:22:16+00:00"
    base = LinkedInJob(
        source="linkedin",
        url="https://www.linkedin.com/jobs/view/44",
        external_id="44",
        title="IT Operations Senior Specialist - Automation",
        company="DLG",
        location="Fredericia, Region Syddanmark, Danmark",
        posted_at="2026-07-30T06:00:00+00:00",
    )
    richer = dict(base, **{"raw": {"description": "Richer description"}})

    kept = filter_career_jobs([base, richer], options=options, now_iso=now)

    assert len(kept) == 1
    assert kept[0].url == base.url


def test_filter_career_jobs_preserves_cross_source_variants():
    options = CareerOptions(
        query="IT Operations",
        location_filter="any_denmark",
        hours_old=168,
    )
    now = "2026-07-31T06:22:16+00:00"
    linkedin = LinkedInJob(
        source="linkedin",
        url="https://www.linkedin.com/jobs/view/55",
        external_id="55",
        title="IT Operations Senior Specialist - Automation",
        company="DLG",
        location="Fredericia, Region Syddanmark, Danmark",
        posted_at="2026-07-30T06:00:00+00:00",
    )
    indeed = IndeedJob(
        source="indeed",
        url="https://dk.indeed.com/viewjob?jk=abc",
        external_id="abc",
        title="IT Operations Senior Specialist - Automation",
        company="DLG",
        location="Fredericia, Region Syddanmark, Danmark",
        posted_at="2026-07-30T00:00:00+00:00",
    )

    kept = filter_career_jobs([linkedin, indeed], options=options, now_iso=now)

    assert {job.source for job in kept} == {"linkedin", "indeed"}


def test_collect_career_jobs_invokes_linkedin_and_indeed_with_options(monkeypatch):
    options = CareerOptions(
        query="IT Operations",
        location_filter="cph",
        hours_old=168,
    )
    linkedin_calls: list[dict] = []
    indeed_calls: list[dict] = []

    def fake_linkedin(options, *, now_iso):
        linkedin_calls.append({"options": options, "now": now_iso})
        return [
            LinkedInJob(
                source="linkedin",
                url="https://www.linkedin.com/jobs/view/77",
                external_id="77",
                title="IT Operations Senior Specialist - Automation",
                company="DLG",
                location="København, Region Hovedstaden, Danmark",
                posted_at="2026-07-30T06:00:00+00:00",
            )
        ]

    def fake_indeed(options, *, now_iso):
        indeed_calls.append({"options": options, "now": now_iso})
        return [
            IndeedJob(
                source="indeed",
                url="https://dk.indeed.com/viewjob?jk=def",
                external_id="def",
                title="Strategy & Operations Manager",
                company="n8n",
                location="København, D84, DK",
                posted_at="2026-07-30T00:00:00+00:00",
            )
        ]

    monkeypatch.setattr("agent_reach.career.collect_linkedin_jobs", fake_linkedin)
    monkeypatch.setattr("agent_reach.career.collect_indeed_jobs", fake_indeed)

    jobs = collect_career_jobs(
        options, sources={"linkedin", "indeed"}, now_iso="2026-07-31T06:22:16+00:00"
    )

    assert len(linkedin_calls) == 1
    assert len(indeed_calls) == 1
    assert {job.source for job in jobs} == {"linkedin"}


def test_collect_career_jobs_skips_disabled_source(monkeypatch):
    options = CareerOptions(
        query="IT Operations",
        location_filter="cph",
        hours_old=168,
    )
    linkedin_called = False
    indeed_called = False

    def fake_linkedin(options, *, now_iso):
        nonlocal linkedin_called
        linkedin_called = True
        return []

    def fake_indeed(options, *, now_iso):
        nonlocal indeed_called
        indeed_called = True
        return []

    monkeypatch.setattr("agent_reach.career.collect_linkedin_jobs", fake_linkedin)
    monkeypatch.setattr("agent_reach.career.collect_indeed_jobs", fake_indeed)

    collect_career_jobs(
        options, sources={"indeed"}, now_iso="2026-07-31T06:22:16+00:00"
    )

    assert not linkedin_called
    assert indeed_called


def test_collect_career_jobs_isolates_per_source_failures(monkeypatch):
    options = CareerOptions(
        query="IT Operations",
        location_filter="cph",
        hours_old=168,
    )

    def broken_linkedin(options, *, now_iso):
        raise RuntimeError("linkedin down")

    def fine_indeed(options, *, now_iso):
        return [
            IndeedJob(
                source="indeed",
                url="https://dk.indeed.com/viewjob?jk=ok",
                external_id="ok",
                title="IT Operations Senior Specialist - Automation",
                company="DLG",
                location="København, Danmark",
                posted_at="2026-07-30T00:00:00+00:00",
            )
        ]

    monkeypatch.setattr("agent_reach.career.collect_linkedin_jobs", broken_linkedin)
    monkeypatch.setattr("agent_reach.career.collect_indeed_jobs", fine_indeed)

    jobs, errors = collect_career_jobs(
        options,
        sources={"linkedin", "indeed"},
        now_iso="2026-07-31T06:22:16+00:00",
        return_errors=True,
    )

    assert errors == {"linkedin": "RuntimeError: linkedin down"}
    assert {job.source for job in jobs} == {"indeed"}


def test_collect_career_jobs_rejects_unknown_source_names():
    options = CareerOptions(
        query="IT Operations",
        location_filter="cph",
        hours_old=168,
    )

    with pytest.raises(ValueError, match="Unsupported sources"):
        collect_career_jobs(
            options,
            sources={"monster"},
            now_iso="2026-07-31T06:22:16+00:00",
        )


def test_collect_career_jobs_enforces_term_limit_range():
    options = CareerOptions(
        query="IT Operations",
        location_filter="cph",
        hours_old=168,
        term_limit=21,
    )

    with pytest.raises(ValueError, match="term_limit"):
        collect_career_jobs(
            options,
            sources={"linkedin"},
            now_iso="2026-07-31T06:22:16+00:00",
        )
