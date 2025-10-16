"""
OpenAI (以及兼容 API) 客户端封装
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from openai import AsyncOpenAI
    from openai import OpenAIError  # type: ignore
except ImportError as exc:  # pragma: no cover - 依赖缺失时提供清晰错误
    AsyncOpenAI = None  # type: ignore
    OpenAIError = Exception  # type: ignore
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

from ..setting.env_loader import get_openai_api_key, get_openai_base_url


class OpenAIClient:
    """OpenAI Chat Completions 异步客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_temperature: float = 0.7,
    ) -> None:
        """
        初始化 OpenAI 客户端。

        Args:
            api_key: API 密钥，默认从环境变量读取。
            base_url: 兼容 OpenAI 协议的自定义地址，例如私有部署。
            default_temperature: 默认采样温度。
        """
        self.api_key = api_key or get_openai_api_key()
        if not self.api_key:
            raise ValueError("OpenAI API 密钥未配置，请设置 OPENAI_API_KEY 环境变量或在 .env 文件中配置")

        if AsyncOpenAI is None:
            raise RuntimeError("缺少 openai 依赖，请先安装 openai>=1.14.0") from _IMPORT_ERROR

        self.base_url = base_url or get_openai_base_url()
        self.default_temperature = default_temperature
        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def call(
        self,
        prompt: str,
        model: str = "gpt-3.5-turbo",
        max_tokens: int = 1024,
        temperature: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        调用 Chat Completions 接口。

        Args:
            prompt: 用户输入的提示词。
            model: 模型名称。
            max_tokens: 最多生成 token 数。
            temperature: 采样温度，默认为初始化时设定。

        Returns:
            包含 'text' 与 'usage' 字段的响应字典，失败时返回 None。
        """
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=self.default_temperature if temperature is None else temperature,
            )

            text = ""
            if response.choices:
                message = response.choices[0].message
                if message and getattr(message, "content", None):
                    text = message.content

            usage: Dict[str, Any] = {}
            usage_payload = getattr(response, "usage", None)
            if usage_payload:
                if hasattr(usage_payload, "model_dump"):
                    usage = usage_payload.model_dump()
                elif isinstance(usage_payload, dict):
                    usage = usage_payload
                else:
                    usage = {
                        key: getattr(usage_payload, key)
                        for key in dir(usage_payload)
                        if not key.startswith("_") and not callable(getattr(usage_payload, key))
                    }

            return {"text": text, "usage": usage}
        except OpenAIError:
            return None
        except Exception:
            return None


_openai_client: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """
    获取全局 OpenAI 客户端（懒加载）

    Returns:
        OpenAIClient: 全局客户端实例。
    """
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client
