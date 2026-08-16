# -*- coding: utf-8
"""Minimal OpenAI-compatible chat completion for daily-run LLM refine."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional


def _resolve_api_key(provider: str) -> tuple[str, str]:
    from agent_reach.config import Config

    cfg = Config()
    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY") or cfg.get("groq_api_key") or ""
        return str(key).strip(), "https://api.groq.com/openai/v1/chat/completions"
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY") or cfg.get("openai_api_key") or ""
        return str(key).strip(), "https://api.openai.com/v1/chat/completions"
    raise ValueError(f"unknown provider: {provider}")


def resolve_chat_provider(preferred: str = "auto") -> Optional[str]:
    """Return groq, openai, or None when no key is configured."""
    order = ["groq", "openai"] if preferred == "auto" else [preferred]
    for provider in order:
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
    }
    use_model = model or default_models.get(resolved, default_models["groq"])

    payload = {
        "model": use_model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
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
