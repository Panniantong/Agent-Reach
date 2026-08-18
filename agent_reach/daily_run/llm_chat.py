# -*- coding: utf-8
"""Minimal OpenAI-compatible chat completion for daily-run LLM refine."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

_DEFAULT_DEEPSEEK_BASE = "https://api.deepseek.com"


def chat_completions_url(base_url: str) -> str:
    """Normalize an OpenAI-compatible base URL to a chat/completions endpoint."""
    base = str(base_url or _DEFAULT_DEEPSEEK_BASE).strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _resolve_api_key(provider: str) -> tuple[str, str]:
    from agent_reach.config import Config

    cfg = Config()
    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY") or cfg.get("groq_api_key") or ""
        return str(key).strip(), "https://api.groq.com/openai/v1/chat/completions"
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY") or cfg.get("openai_api_key") or ""
        return str(key).strip(), "https://api.openai.com/v1/chat/completions"
    if provider == "deepseek":
        key = os.environ.get("DEEPSEEK_API_KEY") or cfg.get("deepseek_api_key") or ""
        base = (
            os.environ.get("DEEPSEEK_BASE_URL")
            or cfg.get("deepseek_base_url")
            or _DEFAULT_DEEPSEEK_BASE
        )
        return str(key).strip(), chat_completions_url(str(base))
    raise ValueError(f"unknown provider: {provider}")


def resolve_chat_provider(preferred: str = "auto") -> Optional[str]:
    """Return configured provider name, or None when no key is available."""
    if preferred != "auto":
        key, _ = _resolve_api_key(preferred)
        return preferred if key else None
    for provider in ("deepseek", "groq", "openai"):
        key, _ = _resolve_api_key(provider)
        if key:
            return provider
    return None


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def chat_json(
    *,
    system: str,
    user: str,
    provider: str = "auto",
    model: Optional[str] = None,
    temperature: float = 0.2,
    timeout: int = 45,
    max_tokens: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Call chat completions and parse a JSON object from the assistant reply."""
    resolved = resolve_chat_provider(provider)
    if not resolved:
        return None
    api_key, endpoint = _resolve_api_key(resolved)
    if not api_key:
        return None

    default_models = {
        "groq": "llama-3.3-70b-versatile",
        "openai": "gpt-4o-mini",
        "deepseek": "deepseek-chat",
    }
    use_model = model or default_models.get(resolved, default_models["deepseek"])

    payload = {
        "model": use_model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if max_tokens is not None and int(max_tokens) > 0:
        payload["max_tokens"] = int(max_tokens)
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    choices = body.get("choices") or []
    if not choices:
        return None
    content = ((choices[0] or {}).get("message") or {}).get("content") or ""
    return _extract_json(content)
