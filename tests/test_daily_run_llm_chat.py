# -*- coding: utf-8 -*-
"""Tests for daily-run LLM chat helper."""

from agent_reach.daily_run.llm_chat import chat_completions_url, resolve_chat_provider


def test_chat_completions_url_normalizes_deepseek_base():
    assert chat_completions_url("https://api.deepseek.com") == (
        "https://api.deepseek.com/v1/chat/completions"
    )
    assert chat_completions_url("https://api.deepseek.com/v1") == (
        "https://api.deepseek.com/v1/chat/completions"
    )


def test_resolve_deepseek_provider(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert resolve_chat_provider("deepseek") == "deepseek"
    assert resolve_chat_provider("auto") == "deepseek"
