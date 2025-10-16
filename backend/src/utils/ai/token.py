"""Token counting utilities for supported AI providers."""
from __future__ import annotations

from typing import Dict

from dashscope import get_tokenizer  # type: ignore


def count_qwen_tokens(prompt: str, model: str = "qwen-plus") -> int:
    """
    使用官方 tokenizer 统计千问模型的 token 数量。
    """
    if not isinstance(prompt, str):
        return 0

    tokenizer = get_tokenizer(model)
    return len(tokenizer.encode(prompt))


def _get_openai_encoding(model: str):
    """
    获取 OpenAI 对应的 tiktoken 编码，失败时返回默认编码。
    """
    try:
        import tiktoken  # type: ignore
    except ImportError:  # pragma: no cover - 可选依赖
        return None

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_openai_tokens(prompt: str, model: str = "gpt-3.5-turbo") -> int:
    """
    使用 tiktoken 估算 OpenAI 兼容模型的 token 数量。
    """
    if not isinstance(prompt, str):
        return 0

    encoding = _get_openai_encoding(model)
    if encoding is None:
        return len(prompt)

    return len(encoding.encode(prompt))


def count_tokens(prompt: str, model: str, provider: str) -> int:
    """
    根据提供方调度合适的 tokenizer。
    """
    key = (provider or "").lower()
    if key == "openai":
        return count_openai_tokens(prompt, model or "gpt-3.5-turbo")
    return count_qwen_tokens(prompt, model or "qwen-plus")


def estimate_total_tokens(prompt: str, completion: str, model: str, provider: str) -> Dict[str, int]:
    """
    粗略估算输入、输出及总 token 数量。
    """
    input_tokens = count_tokens(prompt, model, provider)
    output_tokens = count_tokens(completion, model, provider)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
