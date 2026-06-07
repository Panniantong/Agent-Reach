import os
from pathlib import Path

from agent_reach.config import Config
from agent_reach.envfile import (
    install_tool_wrappers,
    load_agent_env,
    read_env_file,
    sync_config_to_env,
    update_env_file,
)


def test_update_env_file_writes_utf8_without_bom(tmp_path):
    env_path = tmp_path / ".env"
    update_env_file({"AUTH_TOKEN": "tok", "CT0": "ct0"}, env_path)

    data = env_path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert read_env_file(env_path)["AUTH_TOKEN"] == "tok"


def test_load_agent_env_handles_accidental_bom(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_bytes(b"\xef\xbb\xbfAUTH_TOKEN=\"tok\"\n")

    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    load_agent_env(env_path)
    assert read_env_file(env_path)["AUTH_TOKEN"] == "tok"


def test_sync_config_to_env_maps_agent_reach_keys(tmp_path):
    config = Config(config_path=tmp_path / "config.yaml")
    config.set("twitter_auth_token", "auth")
    config.set("twitter_ct0", "ct0")
    config.set("xueqiu_cookie", "xq")
    config.set("bilibili_proxy", "http://127.0.0.1:7890")

    env_path = tmp_path / ".env"
    sync_config_to_env(config, env_path)
    values = read_env_file(env_path)

    assert values["AUTH_TOKEN"] == "auth"
    assert values["TWITTER_AUTH_TOKEN"] == "auth"
    assert values["CT0"] == "ct0"
    assert values["TWITTER_CT0"] == "ct0"
    assert values["XUEQIU_COOKIE"] == "xq"
    assert values["BILIBILI_PROXY"] == "http://127.0.0.1:7890"


def test_install_tool_wrappers_uses_envexec_without_secrets(tmp_path, monkeypatch):
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool = upstream_dir / ("twitter.exe" if os.name == "nt" else "twitter")
    tool.write_text("", encoding="utf-8")

    monkeypatch.setenv("PATH", str(upstream_dir))
    env_path = tmp_path / ".env"
    update_env_file({"AUTH_TOKEN": "secret-token"}, env_path)

    results = install_tool_wrappers(["twitter"], bin_dir=bin_dir, env_path=env_path)

    wrapper = Path(results["twitter"])
    content = wrapper.read_text(encoding="utf-8")
    assert "agent_reach.envexec" in content
    assert "secret-token" not in content
