# -*- coding: utf-8 -*-
"""LLM routing + provider health tests — fully offline."""

import agent_reach.llm as llm_mod
import agent_reach.radar_report as rr
from agent_reach.config import Config
from agent_reach.llm import llm_chat, llm_chat_first, parse_spec, providers_status


def _empty_config(tmp_path) -> Config:
    return Config(config_path=tmp_path / "config.yaml")


def test_parse_spec_keeps_colons_in_model():
    assert parse_spec("ollama:qwen3:4b") == ("ollama", "qwen3:4b")
    assert parse_spec("nvidia:nvidia/llama-3.3-nemotron-super-49b-v1.5") == (
        "nvidia", "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    )
    assert parse_spec("bad") == ("bad", "")


def test_llm_chat_routes_ollama(monkeypatch, tmp_path):
    seen = {}

    def fake_ollama(model, system, user, base_url, timeout=600, options=None):
        seen.update(model=model, base=base_url)
        return "本地回覆"

    monkeypatch.setattr(rr, "_ollama_chat", fake_ollama)
    out = llm_chat("ollama:qwen3:4b", "sys", "hi", _empty_config(tmp_path))
    assert out == "本地回覆" and seen["model"] == "qwen3:4b"


def test_llm_chat_routes_panel_providers(monkeypatch, tmp_path):
    seen = {}

    def fake_panel(provider, model, system, user, config=None, temperature=None):
        seen.update(provider=provider, model=model)
        return "NIM 回覆"

    monkeypatch.setattr(rr, "_panel_chat", fake_panel)
    out = llm_chat("nvidia:meta/model-x", "sys", "hi", _empty_config(tmp_path))
    assert out == "NIM 回覆" and seen == {"provider": "nvidia", "model": "meta/model-x"}


def test_llm_chat_bad_spec_and_ollama_failure(monkeypatch, tmp_path):
    assert llm_chat("", "s", "u", _empty_config(tmp_path)) is None
    assert llm_chat("noprovider", "s", "u", _empty_config(tmp_path)) is None

    def boom(*a, **k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(rr, "_ollama_chat", boom)
    assert llm_chat("ollama:qwen3:4b", "s", "u", _empty_config(tmp_path)) is None


def test_llm_chat_first_falls_through(monkeypatch, tmp_path):
    monkeypatch.setattr(
        llm_mod, "llm_chat",
        lambda spec, s, u, c=None, timeout=600: "答" if spec == "ollama:b" else None,
    )
    text, used = llm_chat_first(["nvidia:a", "ollama:b"], "s", "u", _empty_config(tmp_path))
    assert (text, used) == ("答", "ollama:b")
    assert llm_chat_first(["nvidia:a"], "s", "u") == (None, "")


def test_nvidia_provider_registered():
    assert rr.PROVIDERS["nvidia"]["base_url"] == "https://integrate.api.nvidia.com/v1"
    assert rr.PROVIDERS["nvidia"]["key"] == "nvidia_api_key"


def test_providers_status_offline(monkeypatch, tmp_path):
    for var in ("ANTHROPIC_API_KEY", "NVIDIA_API_KEY", "OPENAI_API_KEY",
                "XAI_API_KEY", "FINVIZ_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    config = _empty_config(tmp_path)
    config.data["nvidia_api_key"] = "k"
    import agent_reach.radar_finviz as rf
    monkeypatch.setattr(rf, "_finviz_token", lambda c=None, s=None: "")
    status = providers_status(config, probe=False)
    assert status["nvidia"]["ok"] is True
    assert status["anthropic"]["ok"] is False
    assert status["finviz"]["ok"] is False
    assert "notebooklm" in status and "twitter" in status and "exa" in status
    # No probe → ollama reported without a live call.
    assert "未探測" in status["ollama"]["detail"]
