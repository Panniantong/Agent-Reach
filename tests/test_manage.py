# -*- coding: utf-8 -*-
"""Management commands: installs, add/remove, setup, sync, doctor, uninstall, update notice, skill.

Package managers and downloads are faked (fake executables that print a
version); everything else (state.json, tool folders, pruning, the CLI JSON)
runs for real in the per-test temp HOME.
"""

import dataclasses
import json
import os
import re
import shutil
import time

import pytest

from agent_reach.channels.base import Action, Channel, Param
from agent_reach.runtime import browser, manage, state, tools, update_notice
from agent_reach.runtime.result import ReachError
from agent_reach.utils.paths import home_dir


class _Base(Channel):
    description = "x"
    passes = True

    def can_handle(self, url):
        return False

    def _go(self, **kw):
        if not type(self).passes:
            raise ReachError("UPSTREAM_BROKEN", "down")
        return [{"title": "ok"}]


def _actions():
    return (Action("search", "s", (Param("query", "q"),), (("b", "_go"),), live_test={"query": "x"}),)


class Web(_Base):
    name, level, actions = "web", "default", _actions()


class Vid(_Base):
    name, level, actions, tools = "vid", "default", _actions(), ("bili-cli",)


class Bili(_Base):
    name, level, actions, tools = "bili", "optional", _actions(), ("bili-cli",)


class Bili2(_Base):
    name, level, actions, tools = "bili2", "optional", _actions(), ("bili-cli",)


class Needy(_Base):
    name, level, actions, prereqs = "needy", "optional", _actions(), ("ffmpeg",)


class Site(_Base):
    name, level, actions, tools, prereqs = "site", "optional", _actions(), ("opencli",), ("node",)
    login_url = "https://www.site.example/login"


class Site2(Site):
    name, login_url = "site2", "https://other.example/"


class Linky(_Base):
    name, level, actions, tools = "linky", "optional", _actions(), ("mcporter",)
    login_argv = ("mcporter", "login")


def _fake_exe(path, version):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho {version}\n")
    path.chmod(0o755)


def _fake_version(exe):
    """What `<exe> --version` prints for a _fake_exe; read instead of run so it works on Windows."""
    try:
        m = re.search(r"echo (\S+)", open(exe, encoding="utf-8").read())
    except (OSError, TypeError):
        return None
    return m.group(1) if m else None


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))  # cli.main extends PATH; restore it
    chans = [Web(), Vid(), Bili(), Bili2(), Needy(), Site(), Site2(), Linky()]
    monkeypatch.setattr(manage, "_channels", lambda: chans)
    system = {}  # command -> path the "user's PATH" has
    monkeypatch.setattr(tools.shutil, "which", lambda c, *a, **k: system.get(c))
    monkeypatch.setattr(tools, "_command_version", _fake_version)
    installs, versions = [], {}

    def fake_install(tool, *, global_=False):
        installs.append(tool.name)
        version = versions.get(tool.name, "1.2.3")
        if tool.kind in ("pip", "ffmpeg"):
            shutil.rmtree(tools.tool_dir(tool.name) / "venv", ignore_errors=True)  # as the real installer
        paths = ([tools._npm_global_bin() / (c + (".cmd" if tools._WIN else "")) for c in tool.commands] if global_
                 else [tools._private_bin(tool, c) for c in tool.commands])
        for p in paths:
            _fake_exe(p, version)
        if tool.kind in ("pip", "ffmpeg"):
            venv = tools.tool_dir(tool.name) / "venv"
            site = venv / "Lib" / "site-packages" if tools._WIN else venv / "lib" / "python3.12" / "site-packages"
            dist = re.sub(r"[-_.]+", "_", tools._dist_name(tool))
            (site / f"{dist}-{version}.dist-info").mkdir(parents=True, exist_ok=True)
        if tool.kind == "npm" and not global_:
            pkg = tools.tool_dir(tool.name) / "node_modules" / tool.package
            pkg.mkdir(parents=True, exist_ok=True)
            (pkg / "package.json").write_text(json.dumps({"version": version}))

    def fake_user_upgrade(tool):
        installs.append(("user-upgrade", tool.name))
        _fake_exe(home_dir() / "usr-bin" / tool.commands[0], versions.get(tool.name, "1.9.0"))

    monkeypatch.setattr(tools, "_install", fake_install)
    monkeypatch.setattr(tools, "_upgrade_user_singleton", fake_user_upgrade)
    calls, stopped = [], []
    monkeypatch.setattr(browser, "ensure_chrome", lambda: calls.append("ensure_chrome") or "/x/chrome", raising=False)
    monkeypatch.setattr(browser, "chrome_binary", lambda: "/x/chrome")
    monkeypatch.setattr(browser, "setup", lambda: calls.append("setup") or {}, raising=False)
    monkeypatch.setattr(browser, "start", lambda url="about:blank": calls.append(("start", url)))
    monkeypatch.setattr(browser, "clear_site", lambda d: calls.append(("clear_site", tuple(d))) or 3, raising=False)
    monkeypatch.setattr(browser, "delete_profile", lambda: calls.append("delete_profile") or True, raising=False)
    monkeypatch.setattr(browser, "is_running", lambda: False)
    monkeypatch.setattr(browser, "stop", lambda *a, **k: stopped.append(True) or True, raising=False)
    return {"chans": chans, "installs": installs, "versions": versions, "system": system,
            "calls": calls, "stopped": stopped}


def _user_copy(env, command, version):
    path = home_dir() / "usr-bin" / command
    _fake_exe(path, version)
    env["system"][command] = str(path)


# ── installs and versions ──


def test_private_copy_wins_over_path(env):
    env["system"]["bili"] = "/usr/bin/bili"
    assert tools.resolve("bili") == "/usr/bin/bili"
    tools.ensure("bili-cli")
    assert tools.resolve("bili") == str(tools._private_bin(tools.TOOLS["bili-cli"], "bili"))


def test_install_records_the_installed_version_and_upgrade_reinstalls(env):
    assert tools.ensure("bili-cli") == {"tool": "bili-cli", "owner": "agent-reach", "scope": "private",
                                         "version": "1.2.3"}
    tools.ensure("bili-cli")
    assert env["installs"] == ["bili-cli"], "an installed tool is not reinstalled by add"
    env["versions"]["bili-cli"] = "2.0.0"
    tools.ensure("bili-cli", upgrade=True)
    assert env["installs"] == ["bili-cli", "bili-cli"]
    assert state.load()["tools"]["bili-cli"]["version"] == "2.0.0"


def test_old_record_without_version_gets_one_without_reinstall(env):
    tools.ensure("bili-cli")
    data = state.load()
    data["tools"]["bili-cli"] = {"spec": "bilibili-cli==0.6.2", "owner": "agent-reach", "scope": "private"}
    state.save(data)
    assert tools.ensure("bili-cli")["version"] == "1.2.3"
    assert env["installs"] == ["bili-cli"]


def test_install_spec_uses_tested_versions_or_floor_and_exclude():
    assert tools.install_spec(tools.TOOLS["bili-cli"]) == "bilibili-cli==0.6.2"
    assert tools.install_spec(tools.TOOLS["boss-agent-cli"]).endswith("@4c991b77086a203173bf08a4cb64a23af6514fe6")
    assert tools.install_spec(tools.Tool("y", "pip", "pkg", ("y",), floor="1.0", exclude=("1.5",))) == "pkg>=1.0,!=1.5"
    npm = tools.Tool("x", "npm", "pkg", ("x",), floor="1.0.0", exclude=("1.2.0", "1.1.0"))
    assert tools.install_spec(npm) == "pkg@>=1.0.0 <1.1.0 || >1.1.0 <1.2.0 || >1.2.0"
    assert tools.install_spec(tools.Tool("z", "npm", "pkg", ("z",))) == "pkg"


@pytest.mark.parametrize(
    "user_version, allow, expect_install, expect_owner, expect_version",
    [("1.9.0", False, [], "user", "1.9.0"),
     ("1.8.0", True, [("user-upgrade", "opencli")], "user", "1.9.0"),
     (None, False, ["opencli"], "agent-reach", "1.2.3")],
)
def test_singleton_reuses_user_copy_and_upgrades_only_with_consent(
    env, user_version, allow, expect_install, expect_owner, expect_version
):
    env["system"].update(node="/usr/bin/node", npm="/usr/bin/npm", npx="/usr/bin/npx")
    if user_version:
        _user_copy(env, "opencli", user_version)
    entry = tools.ensure("opencli", allow_upgrade=allow)
    assert entry["owner"] == expect_owner and entry["scope"] == "global"
    assert entry["version"] == expect_version
    assert env["installs"] == expect_install


def test_singleton_outside_limits_without_consent_changes_nothing(env, monkeypatch):
    env["system"].update(node="/usr/bin/node", npm="/usr/bin/npm", npx="/usr/bin/npx")
    monkeypatch.setitem(tools.TOOLS, "opencli", dataclasses.replace(tools.TOOLS["opencli"], exclude=("1.9.0",)))
    _user_copy(env, "opencli", "1.9.0")
    with pytest.raises(ReachError) as info:
        tools.ensure("opencli")
    assert info.value.code == "NEED_SETUP" and "--allow-upgrade" in info.value.hint
    assert env["installs"] == [] and "opencli" not in state.load()["tools"]


def test_our_singleton_is_upgraded_by_update(env):
    tools.ensure("opencli")
    env["versions"]["opencli"] = "2.0.0"
    assert tools.ensure("opencli", upgrade=True)["version"] == "2.0.0"
    assert env["installs"] == ["node", "opencli", "opencli"]


# ── add: missing prerequisites are installed ──


def test_add_installs_missing_prerequisite_privately(env):
    out = manage.add("needy")
    assert out["added"] is True and env["installs"] == ["ffmpeg"]
    assert tools.ffmpeg_path() == str(tools._private_bin(tools.TOOLS["ffmpeg"], "ffmpeg"))
    assert state.load()["tools"]["ffmpeg"] == {"owner": "agent-reach", "scope": "private", "version": "1.2.3"}
    assert "needy" in state.load()["channels"]


def test_system_prerequisite_is_used_not_installed(env):
    env["system"]["ffmpeg"] = "/usr/bin/ffmpeg"
    manage.add("needy")
    assert env["installs"] == [] and "ffmpeg" not in state.load()["tools"]


def test_npm_tool_gets_private_node_first(env):
    out = manage.add("linky")
    assert env["installs"] == ["node", "mcporter"]
    assert {t: e["version"] for t, e in state.load()["tools"].items()} == {"node": "1.2.3", "mcporter": "1.2.3"}
    assert "agent-reach login linky" in out["next"]


def test_browser_channel_add_never_opens_login_and_explicit_dedicated_remove_cleans_up(env):
    from agent_reach.runtime.browser_binding import bind_profile
    bind_profile("site", "dedicated")
    bind_profile("site2", "dedicated")
    out = manage.add("site")
    assert "ensure_chrome" in env["calls"]
    assert env["calls"] == ["ensure_chrome"]
    assert isinstance(out["next"], str) and "Reuse existing login" in out["next"]
    manage.add("site2")
    browser.profile_dir().mkdir(parents=True)
    first = manage.remove("site")
    assert ("clear_site", ("site.example",)) in env["calls"] and first["cleared_cookies"] == 3
    assert first["removed_tools"] == [] and "delete_profile" not in env["calls"]
    last = manage.remove("site2")
    assert "delete_profile" in env["calls"] and last["browser_deleted"] is True
    assert set(last["removed_tools"]) == {"opencli", "node"}
    assert state.load()["tools"] == {}
    assert not tools.tool_dir("node").exists()


# ── remove ──


def test_remove_keeps_tool_still_used_by_another_channel(env):
    manage.remove("vid")
    manage.add("bili")
    manage.add("bili2")
    assert manage.remove("bili")["removed_tools"] == []
    assert tools.resolve("bili") is not None
    assert manage.remove("bili2")["removed_tools"] == ["bili-cli"]
    assert not tools.tool_dir("bili-cli").exists()


def test_default_channel_can_be_removed_and_stays_removed(env):
    manage.setup()
    assert tools.tool_dir("bili-cli").exists()
    out = manage.remove("vid")
    assert out["removed"] is True and out["removed_tools"] == ["bili-cli"]
    assert state.load()["removed_defaults"] == ["vid"]
    manage.setup()
    manage.sync()
    assert not tools.tool_dir("bili-cli").exists() and _status("vid") == "not_added"
    manage.add("vid")
    assert state.load()["removed_defaults"] == [] and _status("vid") == "unverified"


# ── sync / update ──


def test_sync_upgrades_prunes_drops_and_reports(env):
    manage.add("bili")
    data = state.load()
    data["tools"]["old-tool"] = {"owner": "agent-reach", "scope": "private", "version": "0.1.0"}
    data["tools"]["user-thing"] = {"owner": "user", "scope": "global", "version": "1.0.0"}
    data["channels"]["xiaoyuzhou"] = {"added_at": "2026-01-01T00:00:00Z"}
    data["checks"]["bili"] = {"at": state.now(), "actions": {"search": False}, "codes": {"search": "NEED_LOGIN"},
                              "previous": {"search": True}}
    state.save(data)
    (tools.tool_dir("old-tool") / "bin").mkdir(parents=True)
    env["versions"]["bili-cli"] = "2.0.0"
    out = manage.sync()
    assert out["removed_tools"] == ["old-tool"] and not tools.tool_dir("old-tool").exists()
    assert set(state.load()["tools"]) == {"bili-cli"}, "records of unused user copies are dropped, the copies kept"
    assert state.load()["tools"]["bili-cli"]["version"] == "2.0.0"
    assert env["installs"].count("bili-cli") == 2, "shared tools upgrade once per sync"
    assert out["dropped_channels"] == ["xiaoyuzhou"] and "xiaoyuzhou" not in state.load()["channels"]
    assert any("xiaoyuzhou" in a for a in out["user_actions"])
    assert any("log in to bili" in a for a in out["user_actions"]), "a login that worked before and now fails"


def test_sync_does_not_ask_to_log_in_again_when_never_logged_in(env):
    manage.add("bili")
    data = state.load()
    data["checks"]["bili"] = {"at": state.now(), "actions": {"search": False}, "codes": {"search": "NEED_LOGIN"},
                              "previous": {}}
    state.save(data)
    assert not any("log in" in a for a in manage.sync()["user_actions"])


@pytest.mark.parametrize("latest, available", [("v2.0.1", True), ("v2.0.0", False), ("v1.9.9", False)])
def test_update_check_compares_versions_and_refreshes_the_cache(monkeypatch, latest, available):
    monkeypatch.setattr(manage, "__version__", "2.0.0")
    monkeypatch.setattr(update_notice, "__version__", "2.0.0")
    monkeypatch.setattr(update_notice, "fetch_latest", lambda timeout=10: {"latest": latest.lstrip("v"), "notes": "n"})
    assert manage.update_check()["update_available"] is available
    assert update_notice.read_cache()["latest"] == latest.lstrip("v")
    assert (update_notice.notice() is not None) is available


def test_upgrade_reinstalls_the_release_with_uv():
    cmd = manage.upgrade_command("2.0.1")
    assert cmd[:4] == ["uv", "tool", "install", "--force"] and cmd[-1].endswith("/v2.0.1.zip")


def test_update_from_a_non_uv_install_asks_for_one_uv_reinstall(monkeypatch):
    monkeypatch.setattr(manage, "update_check", lambda: {"current": "2.0.0", "latest": "2.0.1",
                                                         "update_available": True})
    monkeypatch.setattr(manage, "install_method", lambda: "other")
    monkeypatch.setattr(manage.subprocess, "run", lambda *a, **k: pytest.fail("must not run an installer"))
    with pytest.raises(ReachError) as info:
        manage.update()
    assert "uv tool install --force" in info.value.hint


def test_update_without_new_release_still_upgrades_tools(env, monkeypatch):
    monkeypatch.setattr(manage, "update_check", lambda: {"current": "2.0.0", "latest": "2.0.0",
                                                         "update_available": False})
    manage.add("bili")
    env["versions"]["bili-cli"] = "3.0.0"
    out = manage.update()
    assert out["upgraded"] is False and isinstance(out["user_actions"], list)
    assert state.load()["tools"]["bili-cli"]["version"] == "3.0.0"


# ── update notice ──


def _cli_json(capsys, argv):
    from agent_reach.runtime import cli

    cli.main(argv)
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_every_json_output_carries_meta_update_only_when_newer(env, capsys, monkeypatch):
    monkeypatch.setattr(update_notice, "__version__", "1.6.0")
    assert "meta" not in _cli_json(capsys, ["doctor"]), "no cache, no notice"
    update_notice.write_cache({"latest": "1.7.0", "notes": "faster"})
    expected = {"current": "1.6.0", "latest": "1.7.0", "notes": "faster"}
    assert _cli_json(capsys, ["doctor"])["meta"]["update"] == expected
    channels = _cli_json(capsys, ["channels"])
    assert channels["meta"]["update"] == expected
    action = _cli_json(capsys, ["web", "search", "x"])
    assert action["meta"]["update"] == expected and "elapsed_ms" in action["meta"]
    update_notice.write_cache({"latest": "1.6.0", "notes": ""})
    assert "meta" not in _cli_json(capsys, ["doctor"])


def test_background_check_starts_at_most_once_a_day(monkeypatch):
    monkeypatch.delenv(update_notice.DISABLE_ENV)
    started = []
    monkeypatch.setattr(update_notice.subprocess, "Popen", lambda argv, **k: started.append(argv))
    update_notice.maybe_refresh()
    update_notice.maybe_refresh()
    assert len(started) == 1 and started[0][-1] == "agent_reach.runtime.update_notice"
    old = time.time() - update_notice.INTERVAL - 5
    os.utime(update_notice.started_path(), (old, old))
    update_notice.maybe_refresh()
    assert len(started) == 2


def test_background_check_writes_cache_or_stays_silent(monkeypatch):
    def offline(timeout=10):
        raise OSError("offline")

    monkeypatch.setattr(update_notice, "fetch_latest", offline)
    assert update_notice._main() == 1 and not update_notice.cache_path().exists()
    monkeypatch.setattr(update_notice, "fetch_latest", lambda timeout=10: {"latest": "9.9.9", "notes": "n"})
    assert update_notice._main() == 0 and update_notice.read_cache()["latest"] == "9.9.9"


# ── doctor ──


def _status(name):
    return next(c for c in manage.doctor()["channels"] if c["channel"] == name)["status"]


def test_doctor_states(env):
    assert _status("bili") == "not_added"
    manage.add("bili")
    assert _status("bili") == "unverified"
    manage.run_checks(["bili"])
    assert _status("bili") == "ready"
    Bili.passes = False
    try:
        manage.run_checks(["bili"])
        assert _status("bili") == "broken"
    finally:
        Bili.passes = True
    data = state.load()
    data["checks"]["bili"]["at"] = "2000-01-01T00:00:00Z"
    data["checks"]["bili"]["evidence"]["search"]["at"] = "2000-01-01T00:00:00Z"
    state.save(data)
    assert _status("bili") == "unverified"


def test_doctor_reports_missing_tool_and_shows_versions(env):
    manage.add("bili")
    assert {"tool": "bili-cli", "owner": "agent-reach", "scope": "private", "version": "1.2.3"} in manage.doctor()["tools"]
    tools.remove_private("bili-cli")
    assert _status("bili") == "needs_setup"


def test_check_without_names_tests_only_default_and_added_channels(env):
    manage.add("bili")
    tested = {r["channel"] for r in manage.run_checks()["results"]}
    assert tested == {"web", "vid", "bili"}


def test_doctor_marks_regressed_only_when_the_previous_check_passed(env):
    manage.add("bili")
    manage.run_checks(["bili"])
    assert _doctor("bili")["regressed"] is False
    Bili.passes = False
    try:
        manage.run_checks(["bili"])
        assert _doctor("bili")["regressed"] is True
        state.mutate(lambda data: data["tools"].__setitem__("bili-cli", {"version": "changed"}))
        assert _doctor("bili")["status"] == "unverified"
        assert _doctor("bili")["regressed"] is False, "stale evidence cannot prove regression"
        manage.run_checks(["bili"])
        assert _doctor("bili")["regressed"] is False, "an already-broken channel is not a regression"
    finally:
        Bili.passes = True


def _doctor(name):
    return next(c for c in manage.doctor()["channels"] if c["channel"] == name)


# ── setup ──


class Broken(_Base):
    name, level, actions, tools = "broken", "default", _actions(), ("bili-cli",)
    login_argv = ("bili", "login")


def test_setup_adds_default_channels_and_survives_a_failing_install(env, monkeypatch):
    env["chans"].append(Broken())

    def failing_install(tool, *, global_=False):
        raise ReachError("UPSTREAM_BROKEN", "install failed: no network")

    monkeypatch.setattr(tools, "_install", failing_install)
    result = manage.setup()
    by_name = {c["channel"]: c for c in result["default_channels"]}
    assert set(by_name) == {"web", "vid", "broken"}
    assert by_name["web"]["ok"] is True
    assert by_name["broken"]["ok"] is False and by_name["broken"]["error"]["code"] == "UPSTREAM_BROKEN"
    assert "prerequisites" not in result, "prerequisites are installed, not reported"
    assert result["logins"] == [{"channel": "broken", "command": "agent-reach login broken"}]
    optional = {c["channel"]: c["needs"] for c in result["optional_channels"]}
    assert set(optional) == {"bili", "bili2", "needy", "site", "site2", "linky"}
    assert optional["needy"] == [] and optional["site"] == ["login"]
    assert result["skill"]["installed"] is True
    assert env["calls"] == [], "setup opens no login window"


# ── uninstall ──


def test_uninstall_removes_only_what_we_own(env):
    manage.add("bili")
    root = state.root()
    (root / "config.yaml").write_text("x: 1")
    (root / "my-notes").mkdir()
    (root / "tools" / "someone-elses-tool").mkdir(parents=True)
    update_notice.write_cache({"latest": "1.0.0", "notes": ""})
    dry = manage.uninstall(dry_run=True)
    assert (root / "state.json").exists(), "dry run changes nothing"
    assert str(tools.tool_dir("bili-cli")) in dry["removed"]
    assert env["stopped"] == []
    manage.uninstall()
    assert not (root / "state.json").exists() and not (root / "config.yaml").exists()
    assert not update_notice.cache_path().exists()
    assert not tools.tool_dir("bili-cli").exists()
    assert (root / "my-notes").exists() and (root / "tools" / "someone-elses-tool").exists()


def test_uninstall_closes_the_browser_instead_of_refusing(env):
    manage.uninstall()
    assert env["stopped"] == [True]

# ── skill ──


def test_skill_lists_every_channel_and_has_no_placeholders(env):
    for lang in ("zh", "en"):
        text = manage.render_skill(lang)
        assert "{{" not in text
        for ch in env["chans"]:
            assert f"| {ch.name} |" in text


def _seed_our_copy(path):
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\nname: agent-reach\ndescription: old\n---\nold\n")
    (path / "references").mkdir()


def test_skill_one_real_copy_linked_only_for_present_ais(env):
    home = home_dir()
    for d in (".claude", ".codex", ".openclaw"):
        (home / d).mkdir()
    result = manage.place_skill()
    real = home / ".agents" / "skills" / "agent-reach"
    assert (real / "SKILL.md").is_file()
    for name in ("sessions.md", "maintenance.md"):
        assert (real / "references" / name).is_file()
    for link in (home / ".claude" / "skills" / "agent-reach", home / ".openclaw" / "skills" / "agent-reach"):
        assert link.is_symlink() and os.path.realpath(link) == os.path.realpath(real)
    assert not (home / ".codex" / "skills").exists(), "codex reads ~/.agents/skills itself"
    assert not (home / ".cursor").exists(), "absent AIs get nothing"
    assert set(result["agents"]) == {"claude-code", "codex", "openclaw"}
    assert len(state.load()["skill"]["links"]) == 2


def test_skill_replaces_our_old_copy_but_not_a_foreign_one(env):
    home = home_dir()
    ours = home / ".claude" / "skills" / "agent-reach"
    _seed_our_copy(ours)
    foreign = home / ".cursor" / "skills" / "agent-reach"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("---\nname: someone-else\n---\n")
    native_old = home / ".codex" / "skills" / "agent-reach"
    _seed_our_copy(native_old)
    result = manage.place_skill()
    assert ours.is_symlink()
    assert not foreign.is_symlink() and "someone-else" in (foreign / "SKILL.md").read_text(encoding="utf-8")
    assert [n["agent"] for n in result["not_linked"]] == ["cursor"]
    assert not native_old.exists() and result["removed_old_copies"] == [str(native_old)]


def test_skill_falls_back_to_a_copy_without_symlink_rights(env, monkeypatch):
    home = home_dir()
    (home / ".claude").mkdir()

    def no_symlinks(self, *a, **k):
        raise OSError("symlinks not permitted")

    monkeypatch.setattr(type(home), "symlink_to", no_symlinks)
    result = manage.place_skill()
    copy = home / ".claude" / "skills" / "agent-reach"
    assert not copy.is_symlink() and (copy / "SKILL.md").is_file()
    for name in ("sessions.md", "maintenance.md"):
        assert (copy / "references" / name).read_text() == (manage.skill_dir() / "references" / name).read_text()
    assert result["copies"] == [str(copy)] and result["links"] == []
    (copy / "SKILL.md").write_text("---\nname: agent-reach\n---\nstale\n")
    manage.place_skill()
    assert "stale" not in (copy / "SKILL.md").read_text(encoding="utf-8"), "update refreshes recorded copies"
    manage.uninstall()
    assert not copy.exists()


def test_skill_link_for_an_unlisted_ai_and_uninstall_removes_everything(env):
    home = home_dir()
    (home / ".claude").mkdir()
    manage.place_skill()
    other = home / "my-ai" / "skills"
    manage.link_skill(str(other))
    assert (other / "agent-reach").is_symlink()
    stray = home / ".gemini" / "skills" / "agent-reach"
    stray.parent.mkdir(parents=True)
    stray.symlink_to(home / ".agents" / "skills" / "agent-reach")
    manage.place_skill()
    assert (other / "agent-reach").is_symlink(), "update keeps recorded links"
    manage.uninstall()
    for p in (other / "agent-reach", home / ".claude" / "skills" / "agent-reach", stray,
              home / ".agents" / "skills" / "agent-reach"):
        assert not p.exists() and not p.is_symlink()


# ── configure ──


def test_configure_saves_known_keys_only(env):
    from agent_reach.config import Config

    manage.configure("groq-key", "gsk_test")
    assert Config(read_only=True).get("groq_api_key") == "gsk_test"
    with pytest.raises(ReachError):
        manage.configure("twitter-cookies", "x")


def test_doctor_separates_needs_login_from_broken(env, monkeypatch):
    def need_login(self, **kw):
        raise ReachError("NEED_LOGIN", "log in")

    monkeypatch.setattr(Bili, "_go", need_login)
    manage.add("bili")
    manage.run_checks(["bili"])
    assert _status("bili") == "needs_login"
