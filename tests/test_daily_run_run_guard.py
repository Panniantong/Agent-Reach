# -*- coding: utf-8
"""Tests for run_guard busy lock and dedupe."""

import pytest

from agent_reach.daily_run.run_guard import (
    HarnessCooldownError,
    JobBusyError,
    assert_harness_refine_allowed,
    check_duplicate_job,
    job_run_lock,
)


class TestRunGuard:
    def test_check_duplicate_close(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.run_manifest.has_job_manifest_today",
            lambda job, require_feishu=True: job == "close",
        )
        reason = check_duplicate_job("close", settings={"schedule": {"guard": {"enabled": True}}})
        assert reason and "manifest" in reason
        assert check_duplicate_job("close", force=True) is None

    def test_job_run_lock_blocks_parallel(self, tmp_path, monkeypatch):
        monkeypatch.setattr("agent_reach.daily_run.run_guard._LOCK_DIR", tmp_path)
        with job_run_lock("close", settings={"schedule": {"guard": {"enabled": True}}}) as _:
            with pytest.raises(JobBusyError):
                with job_run_lock("close", settings={"schedule": {"guard": {"enabled": True}}}) as _:
                    pass

    def test_harness_cooldown_blocks_refine(self, monkeypatch):
        monkeypatch.setattr("agent_reach.daily_run.harness._within_llm_cooldown", lambda state, cfg: True)
        with pytest.raises(HarnessCooldownError):
            assert_harness_refine_allowed(settings={"harness": {"llm_refine": {"cooldown_hours": 24}}})

    def test_harness_ignore_cooldown(self, monkeypatch):
        monkeypatch.setattr("agent_reach.daily_run.harness._within_llm_cooldown", lambda state, cfg: True)
        assert_harness_refine_allowed(ignore_cooldown=True)
