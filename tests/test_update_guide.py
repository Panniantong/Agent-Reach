"""Regression guards for the Agent Reach update guide."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_update_guide_keeps_doctor_read_only_and_skill_refresh_explicit():
    """Update instructions must not turn diagnostics into a write operation."""
    text = (ROOT / "docs" / "update.md").read_text(encoding="utf-8")

    assert "`agent-reach doctor` is read-only" in text
    assert "`agent-reach skill --install`" in text
    assert "active_backend: null" in text
    assert "doctor` (text mode) also makes sure" not in text
