"""
LangChain-based chat helper.

Provides a thin wrapper around ``langchain_openai.ChatOpenAI`` so existing
modules can gradually migrate from direct HTTP/OpenAI SDK calls.
"""
from __future__ import annotations

import json
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
    model_role: Optional[str] = None,
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
    role_model = str(cfg.get(f"{str(model_role or '').strip()}_model") or "").strip() if model_role else ""
    resolved_model = (model or role_model or task_model or default_model).strip()
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

    role_prefix = str(model_role or "").strip()
    role_temperature = cfg.get(f"{role_prefix}_temperature") if role_prefix else None
    task_temperature = cfg.get(f"{task}_temperature")
    resolved_temperature = (
        _as_float(temperature, 0.3)
        if temperature is not None
        else _as_float(role_temperature if role_temperature is not None else task_temperature if task_temperature is not None else cfg.get("temperature"), 0.3)
    )
    role_max_tokens = cfg.get(f"{role_prefix}_max_tokens") if role_prefix else None
    task_max_tokens = cfg.get(f"{task}_max_tokens")
    resolved_max_tokens = (
        _as_int(max_tokens, 1024)
        if max_tokens is not None
        else _as_int(role_max_tokens if role_max_tokens is not None else task_max_tokens if task_max_tokens is not None else cfg.get("max_tokens"), 1024)
    )
    role_timeout = cfg.get(f"{role_prefix}_timeout") if role_prefix else None
    task_timeout = cfg.get(f"{task}_timeout")
    resolved_timeout = (
        _as_float(timeout, 60.0)
        if timeout is not None
        else _as_float(role_timeout if role_timeout is not None else task_timeout if task_timeout is not None else cfg.get("timeout"), 60.0)
    )
    role_retries = cfg.get(f"{role_prefix}_max_retries") if role_prefix else None
    task_retries = cfg.get(f"{task}_max_retries")
    resolved_max_retries = (
        _as_int(max_retries, 2)
        if max_retries is not None
        else _as_int(role_retries if role_retries is not None else task_retries if task_retries is not None else cfg.get("max_retries"), 2)
    )

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": resolved_model,
        "model_role": role_prefix or "",
        "temperature": resolved_temperature,
        "max_tokens": resolved_max_tokens,
        "timeout": resolved_timeout,
        "max_retries": resolved_max_retries,
    }


def _resolve_max_tool_rounds(
    *,
    task: str = "default",
    model_role: Optional[str] = None,
    explicit_value: Optional[int] = None,
) -> int:
    if explicit_value is not None:
        return max(1, _as_int(explicit_value, 5))
    cfg = _read_langchain_config()
    role_prefix = str(model_role or "").strip()
    role_value = cfg.get(f"{role_prefix}_max_tool_rounds") if role_prefix else None
    task_value = cfg.get(f"{task}_max_tool_rounds")
    global_value = cfg.get("max_tool_rounds")
    return max(
        1,
        _as_int(
            role_value if role_value is not None else task_value if task_value is not None else global_value,
            5,
        ),
    )


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


def _tool_call_name(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("name") or "").strip()
    return str(getattr(call, "name", "") or "").strip()


def _tool_call_args(call: Any) -> Any:
    if isinstance(call, dict):
        return call.get("args", {})
    return getattr(call, "args", {})


def _tool_call_id(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or "").strip()
    return str(getattr(call, "id", "") or "").strip()


def _build_lc_messages(messages: List[Dict[str, str]]) -> Optional[List[Any]]:
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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
    return lc_messages or None


def _build_chat_model(client_cfg: Dict[str, Any]) -> Optional[Any]:
    try:
        from langchain_openai import ChatOpenAI
    except Exception:
        return None
    try:
        return ChatOpenAI(
            model=client_cfg["model"],
            api_key=client_cfg["api_key"],
            base_url=client_cfg["base_url"],
            temperature=client_cfg["temperature"],
            max_tokens=client_cfg["max_tokens"],
            timeout=client_cfg["timeout"],
            max_retries=client_cfg["max_retries"],
        )
    except Exception:
        return None


def build_langchain_chat_model(
    *,
    task: str = "default",
    model_role: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> tuple[Optional[Any], Optional[Dict[str, Any]]]:
    client_cfg = _resolve_client_config(
        task=task,
        model_role=model_role,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
    if not client_cfg:
        return None, None
    llm = _build_chat_model(client_cfg)
    if llm is None:
        return None, client_cfg
    return llm, client_cfg


async def call_langchain_chat(
    messages: List[Dict[str, str]],
    *,
    task: str = "default",
    model_role: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
    event_callback: Optional[Any] = None,
) -> Optional[str]:
    """
    Attempt to call chat model via LangChain.

    Returns ``None`` when LangChain is disabled/unavailable or request fails.
    """
    client_cfg = _resolve_client_config(
        task=task,
        model_role=model_role,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
    if not client_cfg:
        return None

    lc_messages = _build_lc_messages(messages)
    if not lc_messages:
        return None

    try:
        llm = _build_chat_model(client_cfg)
        if llm is None:
            return None
        response = await llm.ainvoke(lc_messages)
        content = _coerce_response_content(getattr(response, "content", ""))
        if content and callable(event_callback):
            try:
                event_callback({"type": "final_text", "text": content})
            except Exception:
                pass
        return content
    except Exception:
        return None


async def call_langchain_with_tools(
    messages: List[Dict[str, str]],
    *,
    tools: List[Any],
    task: str = "default",
    model_role: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
    max_tool_rounds: Optional[int] = None,
    event_callback: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Attempt a lightweight tool-augmented LangChain chat loop.

    This is intentionally narrower than a full ReAct agent. The model can call a
    bounded set of tools for a few rounds, after which the final assistant text is
    returned together with a simple tool trace.
    """
    client_cfg = _resolve_client_config(
        task=task,
        model_role=model_role,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
    if not client_cfg:
        return None

    lc_messages = _build_lc_messages(messages)
    if not lc_messages:
        return None

    try:
        from langchain_core.messages import ToolMessage
    except Exception:
        return None

    llm = _build_chat_model(client_cfg)
    if llm is None:
        return None
    resolved_max_tool_rounds = _resolve_max_tool_rounds(
        task=task,
        model_role=model_role,
        explicit_value=max_tool_rounds,
    )

    try:
        bound_llm = llm.bind_tools(tools)
    except Exception:
        fallback = await call_langchain_chat(
            messages,
            task=task,
            model_role=model_role,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
            event_callback=event_callback,
        )
        if not fallback:
            return None
        return {
            "content": fallback,
            "tool_calls": [],
            "tool_results": [],
            "model": client_cfg["model"],
            "provider": client_cfg["provider"],
            "model_role": client_cfg.get("model_role", ""),
        }

    tool_map = {
        str(getattr(tool, "name", "") or "").strip(): tool
        for tool in (tools or [])
        if str(getattr(tool, "name", "") or "").strip()
    }
    history = list(lc_messages)
    tool_calls_trace: List[Dict[str, Any]] = []
    tool_results_trace: List[Dict[str, Any]] = []

    for _ in range(resolved_max_tool_rounds):
        try:
            response = await bound_llm.ainvoke(history)
        except Exception:
            return None

        history.append(response)
        raw_tool_calls = getattr(response, "tool_calls", None) or []
        if not raw_tool_calls:
            content = _coerce_response_content(getattr(response, "content", ""))
            if content and callable(event_callback):
                try:
                    event_callback({"type": "final_text", "text": content})
                except Exception:
                    pass
            return {
                "content": content,
                "tool_calls": tool_calls_trace,
                "tool_results": tool_results_trace,
                "model": client_cfg["model"],
                "provider": client_cfg["provider"],
                "model_role": client_cfg.get("model_role", ""),
            }

        for tool_call in raw_tool_calls:
            tool_name = _tool_call_name(tool_call)
            tool_args = _tool_call_args(tool_call)
            tool_call_id = _tool_call_id(tool_call)
            tool_obj = tool_map.get(tool_name)
            tool_calls_trace.append(
                {
                    "name": tool_name,
                    "args": tool_args,
                    "id": tool_call_id,
                }
            )
            if callable(event_callback):
                try:
                    event_callback(
                        {
                            "type": "tool_call",
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "tool_call_id": tool_call_id,
                        }
                    )
                except Exception:
                    pass

            if tool_obj is None:
                output = json.dumps({"error": f"tool not found: {tool_name}"}, ensure_ascii=False)
            else:
                try:
                    invoke_payload = tool_args if isinstance(tool_args, dict) else tool_args or {}
                    output = str(tool_obj.invoke(invoke_payload))
                except Exception as exc:
                    output = json.dumps(
                        {"error": f"tool execution failed: {tool_name}", "detail": str(exc)},
                        ensure_ascii=False,
                    )

            tool_results_trace.append(
                {
                    "name": tool_name,
                    "id": tool_call_id,
                    "output": output,
                }
            )
            if callable(event_callback):
                try:
                    event_callback(
                        {
                            "type": "tool_result",
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "output": output,
                        }
                    )
                except Exception:
                    pass
            history.append(
                ToolMessage(
                    content=output,
                    tool_call_id=tool_call_id or tool_name or "tool_call",
                    name=tool_name or "tool",
                )
            )

    try:
        final_response = await llm.ainvoke(history)
    except Exception:
        return {
            "content": "",
            "tool_calls": tool_calls_trace,
            "tool_results": tool_results_trace,
            "model": client_cfg["model"],
            "provider": client_cfg["provider"],
            "model_role": client_cfg.get("model_role", ""),
        }
    final_content = _coerce_response_content(getattr(final_response, "content", ""))
    if final_content and callable(event_callback):
        try:
            event_callback({"type": "final_text", "text": final_content})
        except Exception:
            pass
    return {
        "content": final_content,
        "tool_calls": tool_calls_trace,
        "tool_results": tool_results_trace,
        "model": client_cfg["model"],
        "provider": client_cfg["provider"],
        "model_role": client_cfg.get("model_role", ""),
    }
