"""SECURITY.md must document a usable private reporting path (#703)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURITY_MD = ROOT / "SECURITY.md"


def test_security_policy_documents_private_email_fallback():
    """When private vulnerability reporting is off, email must still work."""
    text = SECURITY_MD.read_text(encoding="utf-8")

    assert "security/advisories/new" in text
    assert "pnt01@foxmail.com" in text
    assert "Please do NOT open a public GitHub issue" in text
    assert "Email fallback" in text
