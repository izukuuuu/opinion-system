"""
AI工具模块
"""
import uuid

from .qwen import QwenClient, get_qwen_client
from .openai_client import OpenAIClient, get_openai_client
from .langchain_client import build_langchain_chat_model, call_langchain_chat, call_langchain_with_tools


def ensure_langchain_uuid_compat() -> None:
    """Patch LangChain/LangGraph uuid7 helper for environments without uuid_utils.uuid7."""
    try:
        import langchain_core.utils.uuid as lc_uuid
    except Exception:
        return
    try:
        lc_uuid._uuid_utils_uuid7()  # type: ignore[attr-defined]
    except Exception:
        lc_uuid._uuid_utils_uuid7 = lambda timestamp=None, nanos=None: uuid.uuid4()  # type: ignore[attr-defined]

__all__ = [
    'QwenClient',
    'get_qwen_client',
    'OpenAIClient',
    'get_openai_client',
    'build_langchain_chat_model',
    'call_langchain_chat',
    'call_langchain_with_tools',
    'ensure_langchain_uuid_compat',
]
