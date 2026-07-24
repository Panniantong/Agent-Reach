# -*- coding: utf-8 -*-
"""Cover the interactive profile-picker input parsing in cli.py.

The picker maps a 1-based menu number to a profile folder. The subtle bug it
must guard against: Python negative indexing. `int("0") - 1 == -1` and
`profiles[-1]` is a *valid* index, so a naive `profiles[int(choice) - 1]`
silently selects the LAST profile (often a burner account) when the user types
`0` instead of aborting — the exact wrong-account extraction --chrome-profile
exists to prevent.
"""

from agent_reach.cli import _resolve_profile_choice

PROFILES = [
    {"folder": "Default"},
    {"folder": "Profile 1"},
    {"folder": "Profile 2"},
]


def test_valid_selection_maps_to_folder():
    assert _resolve_profile_choice(PROFILES, "1") == "Default"
    assert _resolve_profile_choice(PROFILES, "2") == "Profile 1"
    assert _resolve_profile_choice(PROFILES, "3") == "Profile 2"


def test_zero_is_rejected_not_treated_as_last():
    # The regression: "0" → int-1 == -1 → profiles[-1] == "Profile 2" if unguarded.
    assert _resolve_profile_choice(PROFILES, "0") is None


def test_negative_is_rejected():
    assert _resolve_profile_choice(PROFILES, "-1") is None
    assert _resolve_profile_choice(PROFILES, "-2") is None


def test_out_of_range_high_is_rejected():
    assert _resolve_profile_choice(PROFILES, "4") is None
    assert _resolve_profile_choice(PROFILES, "99") is None


def test_non_numeric_is_rejected():
    assert _resolve_profile_choice(PROFILES, "abc") is None
    assert _resolve_profile_choice(PROFILES, "") is None
    assert _resolve_profile_choice(PROFILES, "1.5") is None
