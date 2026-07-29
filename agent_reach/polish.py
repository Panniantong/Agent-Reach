# -*- coding: utf-8 -*-
"""Transcript-polishing LLM backend.

After Whisper transcription, Chinese podcasts often lack punctuation. The
polish step asks an OpenAI-compatible chat-completion model to add Chinese
punctuation and reasonable paragraph breaks without altering the words.

The backend is configurable so users are not locked to a single vendor. Two
providers are supported:

- ``groq``: Groq's OpenAI-compatible endpoint (default, free tier).
- ``minimax``: MiniMax's OpenAI-compatible global (``api.minimax.io``) and
  China (``api.minimaxi.com``) endpoints, exposing the ``MiniMax-M3`` and
  ``MiniMax-M2.7`` text models.

Provider, model, region and API key are resolved from explicit kwargs, then
environment variables, then the Agent Reach config file. The shell
transcription script invokes :func:`polish_chunk_file` via
``python3 -m agent_reach.polish`` so the same registry is used at runtime and
in tests.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Optional
from urllib.parse import urljoin

# Prompts and limits are shared across providers.
PROMPT_TMPL = (
    "以下是一段中文普通话播客的语音转写片段，由于 Whisper 对中文标点支持较弱，"
    "整段几乎没有标点。请你**只做一件事**：在合适位置补充中文标点（，。！？：；），"
    "可以适度分段。\n\n"
    "**严格要求**：\n"
    "- 不得修改、删除、增加任何汉字或英文/数字\n"
    "- 不得改写、润色、总结\n"
    "- 不得添加任何解释、前言、后记\n"
    "- 直接输出加好标点+合理分段后的全文\n\n"
    "原文：\n{}"
)

MAX_DEPTH = 3
REQUEST_TIMEOUT = 180
USER_AGENT = "agent-reach-polish/1.0"

# Provider registry. Each entry exposes:
#   endpoint:    default OpenAI-compatible chat-completions URL
#   model:       default model id
#   key_field:   Agent Reach config key holding the API key
#   key_env:     environment variable holding the API key
#   regions:     optional regional base URLs (without /chat/completions)
#   models:      supported model ids for this provider
POLISH_PROVIDERS: dict[str, dict[str, Any]] = {
    "groq": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "key_field": "groq_api_key",
        "key_env": "GROQ_API_KEY",
        "models": ["llama-3.3-70b-versatile"],
    },
    "minimax": {
        # Endpoint is derived from the selected region below.
        "endpoint": "https://api.minimax.io/v1/chat/completions",
        "model": "MiniMax-M3",
        "key_field": "minimax_api_key",
        "key_env": "MINIMAX_API_KEY",
        "regions": {
            "global_en": "https://api.minimax.io/v1",
            "cn_zh": "https://api.minimaxi.com/v1",
        },
        "models": ["MiniMax-M3", "MiniMax-M2.7"],
    },
}

DEFAULT_PROVIDER = "groq"
DEFAULT_MINIMAX_REGION = "global_en"


class PolishError(RuntimeError):
    """Raised when transcript polishing cannot complete."""


def _config_get(key: str, config: Optional[Any] = None) -> Optional[str]:
    """Read a value from an Agent Reach Config without importing it eagerly."""
    if config is not None:
        try:
            val = config.get(key)
        except Exception:
            val = None
        return val or None
    # Fall back to the config file via a lazy import so this module stays
    # importable in environments where the full config stack is unavailable.
    try:
        from agent_reach.config import Config  # local import avoids cycles
    except Exception:
        return None
    try:
        cfg = Config()
        val = cfg.get(key)
    except Exception:
        return None
    return val or None


def resolve(
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    region: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    config: Optional[Any] = None,
) -> dict[str, str]:
    """Resolve the endpoint, model and API key for a polish request.

    Resolution order for every field: explicit argument → environment variable
    → Agent Reach config file → provider default.
    """
    provider = provider or os.environ.get("POLISH_PROVIDER") or DEFAULT_PROVIDER
    if provider not in POLISH_PROVIDERS:
        raise PolishError(f"unknown polish provider: {provider} (use {'|'.join(POLISH_PROVIDERS)})")
    info = POLISH_PROVIDERS[provider]

    # Endpoint: explicit base_url → region → provider default.
    endpoint = info["endpoint"]
    regions = info.get("regions") or {}
    if base_url is None:
        base_url = os.environ.get("MINIMAX_BASE_URL")
    if base_url is None and regions:
        region = region or os.environ.get("MINIMAX_REGION") or DEFAULT_MINIMAX_REGION
        if region not in regions:
            raise PolishError(f"unknown minimax region: {region} (use {'|'.join(regions)})")
        base_url = regions[region]
    if base_url:
        # base_url is the OpenAI-compatible root (e.g. .../v1); append the
        # standard chat-completions path. urljoin keeps trailing slashes sane.
        endpoint = urljoin(base_url.rstrip("/") + "/", "chat/completions")

    # Model: explicit → env → provider default.
    if model is None:
        model = os.environ.get("POLISH_MODEL")
    if not model:
        model = info["model"]

    # API key: explicit → env → config.
    if not api_key:
        api_key = os.environ.get(info["key_env"])
    if not api_key:
        api_key = _config_get(info["key_field"], config)
    if not api_key:
        raise PolishError(
            f"{provider}: missing {info['key_field']} "
            f"(configure with `agent-reach configure "
            f"{_configure_key(provider)} ...`)"
        )

    return {
        "provider": provider,
        "endpoint": endpoint,
        "model": model,
        "api_key": api_key,
    }


def _configure_key(provider: str) -> str:
    """Map a polish provider to its `agent-reach configure` key."""
    return "minimax-key" if provider == "minimax" else "groq-key"


def _call_chat_completion(
    endpoint: str, model: str, api_key: str, text: str, timeout: int
) -> tuple[str, Optional[str]]:
    """POST one chat-completion request; return (content, finish_reason)."""
    body = json.dumps(
        {
            "model": model,
            "temperature": 0.2,
            "max_completion_tokens": 8192,
            "messages": [{"role": "user", "content": PROMPT_TMPL.format(text)}],
        }
    ).encode()
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    choice = payload["choices"][0]
    return (
        choice["message"]["content"].strip(),
        choice.get("finish_reason"),
    )


def polish_text(
    text: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    region: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    config: Optional[Any] = None,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    """Polish a transcript chunk, returning the punctuated text.

    If the model truncates the output (``finish_reason == "length"``), the
    input is split in half and each half is polished recursively, mirroring the
    original shell-script behaviour. On HTTP/transport errors the raw input is
    returned rather than raised, so polishing degrades gracefully.
    """
    resolved = resolve(
        provider=provider,
        model=model,
        region=region,
        base_url=base_url,
        api_key=api_key,
        config=config,
    )

    def _polish(chunk: str, depth: int) -> str:
        try:
            out, finish = _call_chat_completion(
                resolved["endpoint"],
                resolved["model"],
                resolved["api_key"],
                chunk,
                timeout,
            )
        except urllib.error.HTTPError as exc:
            sys.stderr.write(
                f"polish HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}\n"
            )
            return chunk
        except Exception as exc:  # noqa: BLE001 - degrade to raw on any error
            sys.stderr.write(f"polish error: {exc}\n")
            return chunk
        if finish != "length" or depth >= MAX_DEPTH:
            return out
        mid = len(chunk) // 2
        return _polish(chunk[:mid], depth + 1) + _polish(chunk[mid:], depth + 1)

    return _polish(text.strip(), 0)


def polish_chunk_file(
    in_path: str,
    out_path: str,
    **kwargs: Any,
) -> int:
    """Polish one transcript file and write the result. Returns char count."""
    content = open(in_path, encoding="utf-8").read().strip()
    result = polish_text(content, **kwargs)
    open(out_path, "w", encoding="utf-8").write(result + "\n")
    return len(result)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry: ``python3 -m agent_reach.polish IN OUT``."""
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 2:
        sys.stderr.write("usage: python3 -m agent_reach.polish IN_FILE OUT_FILE\n")
        return 2
    try:
        chars = polish_chunk_file(args[0], args[1])
    except PolishError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    print(f"✅ ({chars} 字)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
