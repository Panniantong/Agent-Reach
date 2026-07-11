# -*- coding: utf-8 -*-
"""Unified LLM routing + provider health.

Specs are ``provider:model`` strings — ``ollama:qwen3:4b``,
``nvidia:nvidia/llama-3.3-nemotron-super-49b-v1.5``,
``anthropic:claude-fable-5`` — routed onto the existing implementations in
``radar_report`` (local Ollama / Anthropic / OpenAI-compatible incl. NVIDIA
NIM). Thin layer: no new HTTP clients, never raises (failures → None so a
scenario can fall through its spec list).
"""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger

from agent_reach.config import Config


def parse_spec(spec: str) -> tuple[str, str]:
    """"provider:model" → (provider, model); model may itself contain colons."""
    provider, _, model = (spec or "").partition(":")
    return provider.strip().lower(), model.strip()


def _ollama_base(config: Config) -> str:
    return (
        config.get("ollama_base_url")
        or os.environ.get("OLLAMA_BASE_URL")
        or "http://127.0.0.1:11434"
    )


def llm_chat(
    spec: str,
    system: str,
    user: str,
    config: Optional[Config] = None,
    timeout: int = 600,
    temperature: Optional[float] = None,
) -> Optional[str]:
    """One chat call routed by spec. None on missing key / any failure."""
    provider, model = parse_spec(spec)
    if not provider or not model:
        logger.warning(f"bad LLM spec: {spec!r} (want provider:model)")
        return None
    config = config or Config()
    if provider == "ollama":
        from agent_reach.radar_report import _ollama_chat

        try:
            return _ollama_chat(model, system, user, _ollama_base(config), timeout=timeout)
        except Exception as e:  # noqa: BLE001 - callers fall through to the next spec
            logger.warning(f"ollama chat failed ({model}): {e}")
            return None
    from agent_reach.radar_report import _panel_chat

    return _panel_chat(provider, model, system, user, config, temperature=temperature)


def llm_chat_first(
    specs: list[str],
    system: str,
    user: str,
    config: Optional[Config] = None,
    timeout: int = 600,
) -> tuple[Optional[str], str]:
    """Try specs in order; return (text, spec_that_worked) or (None, "")."""
    for spec in specs or []:
        out = llm_chat(spec, system, user, config, timeout=timeout)
        if out:
            return out, spec
    return None, ""


# ── provider health ───────────────────────────────────────────────────────


def providers_status(config: Optional[Config] = None, probe: bool = False) -> dict:
    """{provider: {"ok": bool, "detail": str, ...}} for CLI tables / UI lights.

    Offline by default (key/binary presence); ``probe=True`` adds cheap live
    checks (Ollama /api/tags model list). Never raises.
    """
    import shutil

    from agent_reach.radar_report import PROVIDERS

    config = config or Config()
    out: dict[str, dict] = {}

    for name, spec in PROVIDERS.items():
        key_name = spec["key"]
        has = bool(config.get(key_name))
        out[name] = {
            "ok": has,
            "detail": "API key 已設" if has else f"缺 {key_name.upper()}",
        }

    base = _ollama_base(config)
    if probe:
        try:
            import requests

            r = requests.get(f"{base}/api/tags", timeout=3)
            r.raise_for_status()
            models = [m.get("name", "") for m in r.json().get("models", [])]
            out["ollama"] = {
                "ok": True,
                "detail": f"{len(models)} 個模型: {', '.join(models[:8])}" if models else "在線但沒有模型",
                "models": models,
            }
        except Exception as e:  # noqa: BLE001
            out["ollama"] = {"ok": False, "detail": f"連不上 {base}（{e}）"}
    else:
        out["ollama"] = {"ok": True, "detail": f"未探測（{base}）— probe=True 可列模型"}

    tw = bool(config.get("twitter_auth_token") and config.get("twitter_ct0"))
    tw_bin = bool(shutil.which("twitter"))
    out["twitter"] = {
        "ok": tw and tw_bin,
        "detail": "cookies + CLI 就緒" if (tw and tw_bin)
        else ("缺 twitter-cli" if tw else "缺 twitter_auth_token/ct0"),
    }

    out["exa"] = {
        "ok": bool(shutil.which("mcporter")),
        "detail": "mcporter 在 PATH" if shutil.which("mcporter") else "缺 mcporter（npm install -g mcporter）",
    }

    from agent_reach.radar_finviz import _finviz_token

    fv = bool(_finviz_token(config))
    out["finviz"] = {"ok": fv, "detail": "token 可解析" if fv else "缺 FINVIZ_AUTH_TOKEN"}

    from agent_reach.integrations.notebooklm_sync import sync_available

    nb_ok, nb_msg = sync_available(config)
    out["notebooklm"] = {"ok": nb_ok, "detail": "就緒" if nb_ok else nb_msg}

    return out
