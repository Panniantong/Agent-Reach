# -*- coding: utf-8
"""Harness static-config pollution detection."""

from agent_reach.daily_run.harness_policy import (
    EVOLVED_CONFIG_KEYS_BY_SECTION,
    list_static_config_pollution,
)
from agent_reach.daily_run.settings import load_settings


def test_repo_settings_has_no_harness_evolved_keys():
    settings = load_settings()
    settings["harness"] = {"threshold_evolution_mode": "harness"}
    pollution = list_static_config_pollution(settings)
    assert pollution == [], f"remove evolved keys from static JSON: {pollution}"


def test_pollution_detects_static_macro_veto():
    settings = {
        "harness": {"threshold_evolution_mode": "harness"},
        "thresholds": {"macro_veto": 40, "max_snapshot_age_hours": 24},
    }
    assert "thresholds.macro_veto" in list_static_config_pollution(settings)


def test_evolved_catalog_covers_all_runtime_sections():
    assert "thresholds" in EVOLVED_CONFIG_KEYS_BY_SECTION
    assert "trading" in EVOLVED_CONFIG_KEYS_BY_SECTION
    assert "holding_lock_days" in EVOLVED_CONFIG_KEYS_BY_SECTION["trading"]
