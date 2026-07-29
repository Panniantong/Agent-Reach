# -*- coding: utf-8 -*-
"""Tests for agent_reach.polish — the configurable transcript-polishing backend."""

import pytest

from agent_reach import polish
from agent_reach.config import Config


@pytest.fixture
def fake_config(tmp_path, monkeypatch):
    """A Config that writes to a temp dir and never touches the user's HOME."""
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(Config, "CONFIG_FILE", cfg_path)
    return Config(config_path=cfg_path)


# --- Provider registry -------------------------------------------------- #


class TestPolishProviderRegistry:
    def test_groq_and_minimax_are_registered(self):
        assert set(polish.POLISH_PROVIDERS) >= {"groq", "minimax"}

    def test_minimax_exposes_global_and_cn_regions(self):
        regions = polish.POLISH_PROVIDERS["minimax"]["regions"]
        assert regions["global_en"] == "https://api.minimax.io/v1"
        assert regions["cn_zh"] == "https://api.minimaxi.com/v1"

    def test_minimax_supports_current_text_models(self):
        models = polish.POLISH_PROVIDERS["minimax"]["models"]
        assert "MiniMax-M3" in models
        assert "MiniMax-M2.7" in models
        # the provider default is MiniMax-M3
        assert polish.POLISH_PROVIDERS["minimax"]["model"] == "MiniMax-M3"

    def test_minimax_uses_minimax_api_key_field(self):
        assert polish.POLISH_PROVIDERS["minimax"]["key_field"] == "minimax_api_key"
        assert polish.POLISH_PROVIDERS["minimax"]["key_env"] == "MINIMAX_API_KEY"

    def test_groq_keeps_default_model(self):
        # backward compatible default — polishing is configurable, not removed
        assert polish.POLISH_PROVIDERS["groq"]["model"] == "llama-3.3-70b-versatile"


# --- resolve() ---------------------------------------------------------- #


class TestResolve:
    def test_minimax_global_endpoint_derived_from_region(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("POLISH_PROVIDER", raising=False)
        monkeypatch.delenv("POLISH_MODEL", raising=False)
        monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
        monkeypatch.delenv("MINIMAX_REGION", raising=False)
        resolved = polish.resolve(
            provider="minimax",
            api_key="k",
            region="global_en",
        )
        assert resolved["endpoint"] == "https://api.minimax.io/v1/chat/completions"
        assert resolved["model"] == "MiniMax-M3"
        assert resolved["api_key"] == "k"

    def test_minimax_cn_endpoint_derived_from_region(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
        monkeypatch.delenv("MINIMAX_REGION", raising=False)
        resolved = polish.resolve(
            provider="minimax",
            api_key="k",
            region="cn_zh",
        )
        assert resolved["endpoint"] == "https://api.minimaxi.com/v1/chat/completions"

    def test_minimax_model_override(self, monkeypatch):
        resolved = polish.resolve(
            provider="minimax",
            model="MiniMax-M2.7",
            api_key="k",
            region="global_en",
        )
        assert resolved["model"] == "MiniMax-M2.7"

    def test_minimax_base_url_override(self, monkeypatch):
        resolved = polish.resolve(
            provider="minimax",
            api_key="k",
            base_url="https://api.minimax.io/v1",
        )
        assert resolved["endpoint"] == "https://api.minimax.io/v1/chat/completions"

    def test_groq_default_endpoint_and_model(self, monkeypatch):
        monkeypatch.delenv("POLISH_PROVIDER", raising=False)
        monkeypatch.delenv("POLISH_MODEL", raising=False)
        resolved = polish.resolve(provider="groq", api_key="g")
        assert resolved["endpoint"] == "https://api.groq.com/openai/v1/chat/completions"
        assert resolved["model"] == "llama-3.3-70b-versatile"

    def test_unknown_provider_raises(self):
        with pytest.raises(polish.PolishError, match=r"unknown polish provider"):
            polish.resolve(provider="acme", api_key="k")

    def test_missing_key_raises(self, monkeypatch, fake_config):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_REGION", raising=False)
        monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
        with pytest.raises(polish.PolishError, match=r"missing minimax_api_key"):
            polish.resolve(provider="minimax", config=fake_config)

    def test_key_read_from_config(self, monkeypatch, fake_config):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_REGION", raising=False)
        monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
        fake_config.set("minimax_api_key", "from-config")
        resolved = polish.resolve(provider="minimax", config=fake_config)
        assert resolved["api_key"] == "from-config"


# --- Config feature requirement ---------------------------------------- #


class TestConfigMinimaxPolish:
    def test_minimax_polish_feature_registered(self, fake_config):
        assert "minimax_polish" in Config.FEATURE_REQUIREMENTS
        assert Config.FEATURE_REQUIREMENTS["minimax_polish"] == ["minimax_api_key"]
        assert not fake_config.is_configured("minimax_polish")
        fake_config.set("minimax_api_key", "mm-test")
        assert fake_config.is_configured("minimax_polish")


# --- polish_text routing ----------------------------------------------- #


class TestPolishTextRouting:
    def test_minimax_calls_resolved_endpoint(self, monkeypatch):
        captured = {}

        def fake_call(endpoint, model, api_key, text, timeout):
            captured.update(endpoint=endpoint, model=model, api_key=api_key, text=text)
            return text, "stop"

        monkeypatch.setattr(polish, "_call_chat_completion", fake_call)
        out = polish.polish_text(
            "raw",
            provider="minimax",
            model="MiniMax-M3",
            region="cn_zh",
            api_key="k",
        )
        assert out == "raw"
        assert captured["endpoint"] == "https://api.minimaxi.com/v1/chat/completions"
        assert captured["model"] == "MiniMax-M3"
        assert captured["api_key"] == "k"

    def test_transport_error_returns_raw_text(self, monkeypatch):
        def raise_(endpoint, model, api_key, text, timeout):
            raise polish.urllib.error.URLError("boom")

        monkeypatch.setattr(polish, "_call_chat_completion", raise_)
        out = polish.polish_text(
            "raw chunk",
            provider="groq",
            api_key="g",
        )
        # graceful degradation: original text returned unchanged
        assert out == "raw chunk"
