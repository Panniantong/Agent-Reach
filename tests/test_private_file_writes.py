"""Security regressions for local credential and tool configuration writes."""

from __future__ import annotations

import os
import stat

import pytest

from agent_reach.utils import paths


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
def test_atomic_private_text_write_is_0600(tmp_path):
    target = tmp_path / "private" / "secret.txt"

    paths.atomic_write_private_text(target, "secret")

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_atomic_private_text_write_preserves_old_file_on_replace_failure(
    tmp_path, monkeypatch
):
    target = tmp_path / "private" / "secret.txt"
    target.parent.mkdir()
    target.write_text("keep-old", encoding="utf-8")

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(paths.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failure"):
        paths.atomic_write_private_text(target, "new-secret")

    assert target.read_text(encoding="utf-8") == "keep-old"
    assert list(target.parent.glob(".secret.txt.*.tmp")) == []


class _OsShim:
    """Stands in for ``os`` so a test can refuse one call on any platform.

    A sandbox that blocks ``chmod`` (Claude Code's, a container with a seccomp
    profile) hits PermissionError even on a directory whose mode is already
    correct (#684). Real POSIX chmod cannot be refused on demand and Windows
    has no ``fchmod`` at all, so the calls are faked; anything else the module
    is asked for delegates to the real ``os``.
    """

    def __init__(self, **overrides):
        self._real = paths.os
        for name, fn in overrides.items():
            setattr(self, name, fn)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _refused(*_args, **_kwargs):
    raise PermissionError(1, "Operation not permitted")


def _dir_stat(mode: int):
    """An os.fstat result reporting a directory with the given mode."""
    return type("Stat", (), {"st_mode": stat.S_IFDIR | mode})()


def test_make_private_dir_skips_chmod_when_mode_is_already_private(tmp_path, monkeypatch):
    """Mode 0700 already: no chmod call, so a blocked chmod cannot break it."""
    calls = []
    fake = _OsShim(
        open=lambda *_a, **_k: 7,
        fstat=lambda _fd: _dir_stat(0o700),
        fchmod=lambda *_a: calls.append("fchmod"),
        close=lambda _fd: None,
    )
    monkeypatch.setattr(paths, "os", fake)
    monkeypatch.setattr(paths.sys, "platform", "linux")

    target = tmp_path / "reachable"
    assert paths.make_private_dir(target) == target
    assert calls == []


def test_make_private_dir_survives_a_refused_chmod(tmp_path, monkeypatch, capsys):
    """A refused chmod warns and keeps the directory: doctor still runs (#684)."""
    fake = _OsShim(
        open=lambda *_a, **_k: 7,
        fstat=lambda _fd: _dir_stat(0o755),
        fchmod=_refused,
        close=lambda _fd: None,
    )
    monkeypatch.setattr(paths, "os", fake)
    monkeypatch.setattr(paths.sys, "platform", "linux")

    target = tmp_path / "sandboxed"
    assert paths.make_private_dir(target) == target
    assert str(target) in capsys.readouterr().err


def test_make_private_dir_survives_a_refused_directory_open(tmp_path, monkeypatch, capsys):
    fake = _OsShim(open=_refused, close=lambda _fd: None)
    monkeypatch.setattr(paths, "os", fake)
    monkeypatch.setattr(paths.sys, "platform", "linux")

    target = tmp_path / "unreadable"
    assert paths.make_private_dir(target) == target
    assert str(target) in capsys.readouterr().err


def test_atomic_private_text_write_survives_a_refused_chmod(tmp_path, monkeypatch):
    """mkstemp creates the file 0600 already, so the fchmod only re-tightens."""
    monkeypatch.setattr(paths, "os", _OsShim(fchmod=_refused))
    monkeypatch.setattr(paths.sys, "platform", "linux")

    target = tmp_path / "private" / "secret.txt"
    paths.atomic_write_private_text(target, "secret")

    assert target.read_text(encoding="utf-8") == "secret"








































