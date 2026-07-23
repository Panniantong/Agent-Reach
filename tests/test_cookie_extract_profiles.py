# -*- coding: utf-8 -*-
"""Cover the Chromium profile-selection fix for cookie_extract.py.

Root cause: rookiepy and browser_cookie3 both resolve to the first matching
Chrome profile path (always "Default" when it exists) with no way to target
another profile from their public API. Anyone keeping research/burner
social accounts logged into a *separate* Chrome profile would otherwise
have `agent-reach configure --from-browser chrome` silently read cookies
from their real "Default" profile instead of the one they intended.
"""

import json
import sys

import pytest

from agent_reach.cookie_extract import extract_all, list_chrome_profiles


def _chrome_user_data_dir(tmp_path):
    if sys.platform == "darwin":
        return tmp_path / "Library" / "Application Support" / "Google" / "Chrome"
    return tmp_path / ".config" / "google-chrome"


def _make_profile(user_data_dir, folder, name, email):
    profile_dir = user_data_dir / folder
    profile_dir.mkdir(parents=True)
    (profile_dir / "Cookies").write_text("", encoding="utf-8")
    return {"name": name, "user_name": email}


def _write_local_state(user_data_dir, info_cache):
    user_data_dir.mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": info_cache}}), encoding="utf-8"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="path layout differs on Windows")
def test_list_chrome_profiles_reads_local_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    user_data_dir = _chrome_user_data_dir(tmp_path)
    info_cache = {
        "Default": _make_profile(user_data_dir, "Default", "Person 1", "real@gmail.com"),
        "Profile 1": _make_profile(user_data_dir, "Profile 1", "Research", "burner@gmail.com"),
    }
    _write_local_state(user_data_dir, info_cache)

    profiles = list_chrome_profiles("chrome")
    folders = [p["folder"] for p in profiles]

    assert folders[0] == "Default", "Default must sort first to keep the no-profile default behavior unchanged"
    assert "Profile 1" in folders
    research = next(p for p in profiles if p["folder"] == "Profile 1")
    assert research["email"] == "burner@gmail.com"
    assert research["cookies_path"] == str(user_data_dir / "Profile 1" / "Cookies")


@pytest.mark.skipif(sys.platform == "win32", reason="path layout differs on Windows")
def test_list_chrome_profiles_skips_entries_without_a_cookies_file(tmp_path, monkeypatch):
    """info_cache can list profiles Chrome created but never actually used
    (no Cookies db yet) — those aren't extractable and shouldn't be offered."""
    monkeypatch.setenv("HOME", str(tmp_path))
    user_data_dir = _chrome_user_data_dir(tmp_path)
    info_cache = {
        "Default": _make_profile(user_data_dir, "Default", "Person 1", "real@gmail.com"),
        "Profile 1": {"name": "Empty", "user_name": ""},  # no Cookies file created
    }
    _write_local_state(user_data_dir, info_cache)

    profiles = list_chrome_profiles("chrome")

    assert [p["folder"] for p in profiles] == ["Default"]


@pytest.mark.skipif(sys.platform == "win32", reason="path layout differs on Windows")
def test_list_chrome_profiles_empty_when_no_local_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert list_chrome_profiles("chrome") == []


class _FakeBrowserCookie3:
    """Stand-in for the browser_cookie3 module — only tracks what cookie_file
    it was called with, so tests don't touch a real browser install."""

    calls = []

    @staticmethod
    def chrome(cookie_file=None, domain_name="", key_file=None):
        _FakeBrowserCookie3.calls.append(cookie_file)
        return []

    firefox = staticmethod(lambda cookie_file=None, domain_name="", key_file=None: [])
    edge = staticmethod(lambda cookie_file=None, domain_name="", key_file=None: [])
    brave = staticmethod(lambda cookie_file=None, domain_name="", key_file=None: [])
    opera = staticmethod(lambda cookie_file=None, domain_name="", key_file=None: [])


@pytest.mark.skipif(sys.platform == "win32", reason="path layout differs on Windows")
def test_extract_all_with_profile_targets_that_profiles_cookies_path(tmp_path, monkeypatch):
    """The core regression check: passing profile= must make extract_all
    read THAT profile's Cookies db, not whichever the library defaults to."""
    monkeypatch.setenv("HOME", str(tmp_path))
    user_data_dir = _chrome_user_data_dir(tmp_path)
    info_cache = {
        "Default": _make_profile(user_data_dir, "Default", "Person 1", "real@gmail.com"),
        "Profile 1": _make_profile(user_data_dir, "Profile 1", "Research", "burner@gmail.com"),
    }
    _write_local_state(user_data_dir, info_cache)

    _FakeBrowserCookie3.calls = []
    monkeypatch.setitem(sys.modules, "browser_cookie3", _FakeBrowserCookie3)
    monkeypatch.setitem(sys.modules, "rookiepy", None)  # not consulted when profile is given

    extract_all("chrome", profile="Profile 1")

    assert _FakeBrowserCookie3.calls == [str(user_data_dir / "Profile 1" / "Cookies")]


@pytest.mark.skipif(sys.platform == "win32", reason="path layout differs on Windows")
def test_extract_all_rejects_unknown_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    user_data_dir = _chrome_user_data_dir(tmp_path)
    info_cache = {"Default": _make_profile(user_data_dir, "Default", "Person 1", "real@gmail.com")}
    _write_local_state(user_data_dir, info_cache)

    with pytest.raises(RuntimeError, match="not found"):
        extract_all("chrome", profile="Profile 7")


def test_extract_all_rejects_profile_for_firefox():
    with pytest.raises(ValueError, match="Chromium-based"):
        extract_all("firefox", profile="whatever")
