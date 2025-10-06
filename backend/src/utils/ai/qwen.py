"""
千问API连接器
"""
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from ..setting.env_loader import get_api_key

# API配置
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

class QwenClient:
    """千问API客户端"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化千问客户端

        Args:
            api_key (Optional[str]): API密钥
        """
        self.api_key = api_key or get_api_key()

        if not self.api_key:
            raise ValueError("千问API密钥未配置，请设置环境变量 DASHSCOPE_API_KEY 或编辑 .env 文件")

    async def call(self, prompt: str, model: str = "qwen-plus", max_tokens: int = 10000) -> Optional[Dict[str, Any]]:
        """
        调用千问API

        Args:
            prompt (str): 提示词
            model (str): 模型名称
            max_tokens (int): 最大token数

        Returns:
            Optional[Dict[str, Any]]: API响应数据，包含text和usage信息，失败时返回None
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            "parameters": {
                "max_tokens": max_tokens
            }
        }

        try:
            # 增加超时时间和连接池配置
            timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post(API_URL, json=data, headers=headers) as resp:
                    if resp.status == 200:
                        response_data = await resp.json()
                        return {
                            'text': response_data.get('output', {}).get('text', ''),
                            'usage': response_data.get('usage', {})
                        }
                    elif resp.status == 429:  # 限流错误
                        return None
                    elif resp.status >= 500:  # 服务器错误
                        return None
                    else:
                        return None
        except asyncio.TimeoutError:
            return None
        except aiohttp.ClientError:
            return None
        except Exception:
            return None

# 全局千问客户端实例（延迟初始化）
_qwen_client = None

def get_qwen_client() -> QwenClient:
    """
    获取千问客户端实例（延迟初始化）

    Returns:
        QwenClient: 千问客户端实例
    """
    global _qwen_client
    if _qwen_client is None:
        _qwen_client = QwenClient()
    return _qwen_client
