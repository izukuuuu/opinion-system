"""
LangChain-based chat helper.

Provides a thin wrapper around ``langchain_openai.ChatOpenAI`` so existing
modules can gradually migrate from direct HTTP/OpenAI SDK calls.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..setting.env_loader import get_api_key, get_openai_api_key, get_openai_base_url
from ..setting.settings import settings


QWEN_COMPAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_langchain_config() -> Dict[str, Any]:
    llm_config = settings.get_llm_config()
    if not isinstance(llm_config, dict):
        return {}
    langchain_cfg = llm_config.get("langchain")
    if not isinstance(langchain_cfg, dict):
        return {}
    return langchain_cfg


def _resolve_client_config(
    *,
    task: str = "default",
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    cfg = _read_langchain_config()
    if not cfg.get("enabled", False):
        return None

    provider = str(cfg.get("provider") or "qwen").strip().lower()
    default_model = str(cfg.get("model") or "").strip()
    task_model = str(cfg.get(f"{task}_model") or "").strip()
    resolved_model = (model or task_model or default_model).strip()
    if not resolved_model:
        resolved_model = "qwen-plus" if provider == "qwen" else "gpt-4o-mini"

    if provider == "openai":
        api_key = get_openai_api_key()
        base_url = (
            str(cfg.get("base_url") or "").strip()
            or get_openai_base_url()
            or "https://api.openai.com/v1"
        )
    else:
        provider = "qwen"
        api_key = get_api_key()
        base_url = str(cfg.get("base_url") or "").strip() or QWEN_COMPAT_BASE_URL

    if not api_key:
        return None

    resolved_temperature = (
        _as_float(temperature, 0.3)
        if temperature is not None
        else _as_float(cfg.get("temperature"), 0.3)
    )
    resolved_max_tokens = (
        _as_int(max_tokens, 1024)
        if max_tokens is not None
        else _as_int(cfg.get("max_tokens"), 1024)
    )
    resolved_timeout = (
        _as_float(timeout, 60.0)
        if timeout is not None
        else _as_float(cfg.get("timeout"), 60.0)
    )
    resolved_max_retries = (
        _as_int(max_retries, 2)
        if max_retries is not None
        else _as_int(cfg.get("max_retries"), 2)
    )

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": resolved_model,
        "temperature": resolved_temperature,
        "max_tokens": resolved_max_tokens,
        "timeout": resolved_timeout,
        "max_retries": resolved_max_retries,
    }


def _coerce_response_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item.strip())
                continue
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "").strip()


async def call_langchain_chat(
    messages: List[Dict[str, str]],
    *,
    task: str = "default",
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> Optional[str]:
    """
    Attempt to call chat model via LangChain.

    Returns ``None`` when LangChain is disabled/unavailable or request fails.
    """
    client_cfg = _resolve_client_config(
        task=task,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
    if not client_cfg:
        return None

    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
    except Exception:
        return None

    lc_messages = []
    for item in messages:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "")
        if not content:
            continue
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))

    if not lc_messages:
        return None

    try:
        llm = ChatOpenAI(
            model=client_cfg["model"],
            api_key=client_cfg["api_key"],
            base_url=client_cfg["base_url"],
            temperature=client_cfg["temperature"],
            max_tokens=client_cfg["max_tokens"],
            timeout=client_cfg["timeout"],
            max_retries=client_cfg["max_retries"],
        )
        response = await llm.ainvoke(lc_messages)
        return _coerce_response_content(getattr(response, "content", ""))
    except Exception:
        return None

