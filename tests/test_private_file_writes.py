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








































