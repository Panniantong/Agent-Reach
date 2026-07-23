# -*- coding: utf-8 -*-
"""Tests for the optional Linux.do channel."""

from agent_reach.channels.linuxdo import LinuxDoChannel
from agent_reach.probe import ProbeResult


def test_can_handle_exact_linuxdo_hosts():
    ch = LinuxDoChannel()
    assert ch.can_handle("https://linux.do/t/topic/123")
    assert ch.can_handle("https://www.linux.do/t/topic/123")
    assert ch.can_handle("https://LINUX.DO./latest")
    assert not ch.can_handle("https://notlinux.do/t/topic/123")
    assert not ch.can_handle("https://example.com/?next=https://linux.do/t/123")
    assert not ch.can_handle("https://linux.do.example.com/t/123")


def test_check_missing(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.channels.linuxdo.probe_command",
        lambda *args, **kwargs: ProbeResult("missing"),
    )
    ch = LinuxDoChannel()
    status, message = ch.check()
    assert status == "off"
    assert "v0.3.0" in message
    assert "--with playwright" in message
    assert ch.active_backend is None


def test_check_broken(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.channels.linuxdo.probe_command",
        lambda *args, **kwargs: ProbeResult("broken", hint="stale shim"),
    )
    ch = LinuxDoChannel()
    status, message = ch.check()
    assert status == "error"
    assert "重装" in message
    assert "v0.3.0" in message
    assert ch.active_backend is None


def test_check_timeout(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.channels.linuxdo.probe_command",
        lambda *args, **kwargs: ProbeResult("timeout"),
    )
    ch = LinuxDoChannel()
    status, message = ch.check()
    assert status == "error"
    assert "超时" in message
    assert ch.active_backend is None


def test_check_nonzero_exit(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.channels.linuxdo.probe_command",
        lambda *args, **kwargs: ProbeResult("error", output="bad help"),
    )
    ch = LinuxDoChannel()
    status, message = ch.check()
    assert status == "error"
    assert "bad help" in message
    assert ch.active_backend is None


def test_check_ok_sets_active_backend(monkeypatch):
    calls = []

    def fake_probe(*args, **kwargs):
        calls.append((args, kwargs))
        return ProbeResult("ok", output="Usage: linuxdo-reader")

    monkeypatch.setattr("agent_reach.channels.linuxdo.probe_command", fake_probe)
    ch = LinuxDoChannel()
    status, message = ch.check()
    assert status == "ok"
    assert "抓取" in message
    assert ch.active_backend == "linuxdo-reader CLI"
    assert calls[0][0][:2] == ("linuxdo-reader", ["-h"])
    assert calls[0][1]["timeout"] == 10
