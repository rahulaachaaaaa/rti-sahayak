"""get_llm() factory honoring RTI_PROVIDER, with cross-provider fallback (spec s3).

Claude  -> UiPath LLM Gateway via uipath_langchain.chat.UiPathChat (no personal key).
            Verified against uipath-langchain 0.13.11 / uipath-langchain-client 1.15.0:
            UiPathChat's field `model_name` is aliased "model", so we pass model=...,
            and auth is resolved from the `uipath auth` session (client_settings default).
DeepSeek-> langchain_deepseek.ChatDeepSeek with DEEPSEEK_API_KEY (bring-your-own).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Optional, Type

from .config_loader import load_config, provider_for

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from pydantic import BaseModel


def _build(provider_name: str) -> "BaseChatModel":
    cfg = load_config()
    p = cfg["providers"][provider_name]
    ptype = p["type"]

    if ptype == "uipath_gateway":
        # Lazy import: UiPathChat pulls heavy deps and needs a uipath session.
        from uipath_langchain.chat import UiPathChat
        return UiPathChat(model=p["model"], temperature=0)

    if ptype == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        key = os.environ.get(p["api_key_env"])
        if not key:
            raise RuntimeError(
                f"{p['api_key_env']} is not set. DeepSeek is bring-your-own-key; "
                f"export it or switch RTI_PROVIDER=claude (needs `uipath auth`)."
            )
        return ChatDeepSeek(
            model=p["model"], api_key=key, base_url=p["base_url"], temperature=0,
        )

    raise ValueError(f"Unknown provider type: {ptype!r}")


def get_llm(node: str) -> "BaseChatModel":
    """Resolve the chat model for a node: per-node pin > RTI_PROVIDER > default."""
    return _build(provider_for(node))


def get_llm_named(provider_name: str) -> "BaseChatModel":
    """Force a specific provider (used by cross-model verification)."""
    return _build(provider_name)


def default_provider() -> str:
    return os.getenv("RTI_PROVIDER", load_config()["default"])


def invoke_structured(
    node: str,
    schema: "Type[BaseModel]",
    messages: list,
    *,
    provider: Optional[str] = None,
) -> Any:
    """Structured-output call with auto-fallback to `default` (config on_failure).

    DeepSeek-chat supports function-calling structured output; deepseek-reasoner does
    not. On any provider/parse failure we retry on the configured default provider.
    """
    name = provider or provider_for(node)
    cfg = load_config()
    try:
        llm = _build(name).with_structured_output(schema)
        return llm.invoke(messages)
    except Exception as exc:  # noqa: BLE001 — fallback is the whole point
        fallback = default_provider()
        if cfg.get("on_failure") == "fallback_to_default" and fallback != name:
            llm = _build(fallback).with_structured_output(schema)
            return llm.invoke(messages)
        raise RuntimeError(f"structured call failed on {name!r}: {exc}") from exc
