"""The shipped routing references must not imply private tools are installed."""

from pathlib import Path

REFERENCES = Path(__file__).resolve().parents[1] / "agent_reach" / "skill" / "references"


def test_search_recommends_only_traceable_documented_routes():
    text = (REFERENCES / "search.md").read_text(encoding="utf-8")
    assert "my-mcp-tools" not in text
    assert "mcporter call exa.web_search_exa" in text
    assert "dev.md" in text


def test_dev_does_not_advertise_unconfigured_private_mcp_tools():
    text = (REFERENCES / "dev.md").read_text(encoding="utf-8")
    assert "my-mcp-tools" not in text
    assert "| zread" not in text
    assert "| context7" not in text
    assert "gh search code" in text
    assert "gh auth status" in text
    assert "https://cli.github.com/manual/" in text
    assert "| gh CLI | agent-reach |" not in text
