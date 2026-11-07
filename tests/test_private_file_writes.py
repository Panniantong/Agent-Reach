"""Security regressions for local credential and tool configuration writes."""

from __future__ import annotations

import hashlib
import os
import stat

import pytest

from agent_reach.utils import paths

MULTILINE_TEXT = "first\nsecond\nthird\n"


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


def test_atomic_private_text_write_does_not_translate_newlines(tmp_path):
    """The bytes on disk must equal text.encode(encoding) with no platform
    newline translation. The project skill manifest records
    sha256(content.encode("utf-8")) while the owned-file guard rehashes
    read_bytes(); a text-mode \\n -> \\r\\n rewrite (Windows default) made the
    two disagree and the guard rejected freshly installed skills."""
    target = tmp_path / "private" / "skill.md"

    paths.atomic_write_private_text(target, MULTILINE_TEXT)

    on_disk = target.read_bytes()
    assert b"\r\n" not in on_disk
    assert on_disk == MULTILINE_TEXT.encode("utf-8")
    assert hashlib.sha256(on_disk).hexdigest() == hashlib.sha256(
        MULTILINE_TEXT.encode("utf-8")
    ).hexdigest()








































