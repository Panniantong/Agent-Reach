import json

from agent_reach.runtime import mcp_registration


def test_cursor_mcp_install_preserves_other_servers_and_uninstall(tmp_path, monkeypatch):
    cursor = tmp_path / "home" / ".cursor"
    cursor.mkdir()
    config = cursor / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}))
    monkeypatch.setattr(mcp_registration.shutil, "which", lambda name: "/opt/reach/bin/agent-reach")
    installed = mcp_registration.install()
    assert installed["installed"] is True
    servers = json.loads(config.read_text())["mcpServers"]
    assert set(servers) == {"other", "agent-reach"}
    assert mcp_registration.uninstall()["removed"] is True
    assert json.loads(config.read_text())["mcpServers"] == {"other": {"command": "other"}}
