# -*- coding: utf-8 -*-
"""Dedicated tests for the ``boss`` channel.

Boss直聘 走 CDP 调试端口复用已登录的真 Chrome（headless 是禁区，code 36 风控）。
check() 只做三层只读探测：boss-agent-cli 装没装 → CDP 端口通不通 → 有无可复用
zhipin 页签。四分支各自返回 (status, message)，且永不触发浏览器启动（无副作用）。
"""

from unittest.mock import patch

from agent_reach.channels import boss as boss_mod
from agent_reach.channels.boss import BossChannel
from agent_reach.probe import ProbeResult


def _ok_probe():
    return ProbeResult("ok", output="1.18.0")


# --- can_handle ---

def test_can_handle_matches_zhipin_hosts():
    ch = BossChannel()
    for url in [
        "https://www.zhipin.com/job_detail/abc.html",
        "https://zhipin.com/web/geek/job?query=大模型",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://zhipin.com.evil.test/job",
        "",
        "https://user@zhipin.com/job",
    ]:
        assert ch.can_handle(url) is False, url


# --- check() 四分支 ---

def test_check_off_when_cli_missing():
    ch = BossChannel()
    with patch.object(boss_mod, "probe_command", return_value=ProbeResult("missing")):
        status, message = ch.check()
    assert status == "off"
    assert "boss-agent-cli" in message
    assert "agent-reach install --system --channels=boss" in message
    assert ch.active_backend is None


def test_check_error_when_cli_broken():
    ch = BossChannel()
    with patch.object(boss_mod, "probe_command", return_value=ProbeResult("broken")):
        status, message = ch.check()
    assert status == "error"
    assert ch.active_backend is None


def test_check_off_when_cdp_unreachable():
    ch = BossChannel()
    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", return_value=None
    ):
        status, message = ch.check()
    assert status == "off"
    assert "9222" in message
    assert ch.active_backend is None


def test_chrome_launch_command_is_portable_and_loopback_only():
    mac = boss_mod._chrome_launch_command("Darwin")
    linux = boss_mod._chrome_launch_command("Linux")
    windows = boss_mod._chrome_launch_command("Windows")

    assert mac.startswith('open -na "Google Chrome" --args ')
    assert linux.startswith("google-chrome ")
    assert windows.startswith("Start-Process chrome.exe -ArgumentList ")
    for command in (mac, linux, windows):
        assert "--remote-debugging-address=127.0.0.1" in command
        assert "--remote-debugging-port=9222" in command
        assert "boss-chrome-profile" in command
        assert "https://www.zhipin.com/web/geek/job" in command


def test_check_warn_when_no_zhipin_page():
    ch = BossChannel()

    def fake_cdp(path):
        if path == "/json/version":
            return {"Browser": "Chrome"}
        return [{"type": "page", "url": "https://example.com"}]

    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", side_effect=fake_cdp
    ):
        status, message = ch.check()
    assert status == "warn"
    assert ch.active_backend is None


def test_check_warn_when_ready():
    ch = BossChannel()

    def fake_cdp(path):
        if path == "/json/version":
            return {"Browser": "Chrome"}
        return [{"type": "page", "url": "https://www.zhipin.com/web/geek/job"}]

    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", side_effect=fake_cdp
    ):
        status, message = ch.check()
    assert status == "warn"
    assert "PR #382" in message
    assert "boss --cdp-url http://localhost:9222 login --cdp" in message
    assert "--browser-mode cdp-required" in message
    assert "code 37 = TOKEN_REFRESH_FAILED" not in message
    assert ch.active_backend is None


def test_check_clears_stale_active_backend():
    ch = BossChannel()
    ch.active_backend = "stale"
    with patch.object(boss_mod, "probe_command", return_value=ProbeResult("missing")):
        ch.check()
    assert ch.active_backend is None
