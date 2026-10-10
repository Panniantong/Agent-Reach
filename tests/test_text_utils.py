"""Coverage for the UTF-8-safe file reading helper."""

from pathlib import Path

from agent_reach.utils.text import read_utf8_text


def test_returns_default_when_path_missing(tmp_path: Path):
    missing = tmp_path / "does-not-exist.txt"
    assert read_utf8_text(missing, default="fallback") == "fallback"


def test_returns_default_empty_string_by_default(tmp_path: Path):
    missing = tmp_path / "does-not-exist.txt"
    assert read_utf8_text(missing) == ""


def test_reads_existing_utf8_file(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("hello 你好", encoding="utf-8")
    assert read_utf8_text(target) == "hello 你好"


def test_replaces_invalid_utf8_bytes_instead_of_raising(tmp_path: Path):
    target = tmp_path / "bad-bytes.txt"
    target.write_bytes(b"valid-\xff-bytes")

    result = read_utf8_text(target)

    assert "valid-" in result
    assert "-bytes" in result
    assert "�" in result
