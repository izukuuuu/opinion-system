"""Helpers for managing RouterRAG retrieval prompts."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from ..paths import CONFIGS_DIR


# Define the prompt directory for RouterRAG
ROUTER_PROMPT_DIR = CONFIGS_DIR / "prompt" / "router_retrieve"



DEFAULT_ROUTER_PROMPT_CONFIG = {
    "query_expansion": {
        "prompt": """你是一个专业的查询扩展助手。请将用户查询扩展为更适合信息检索的查询文本。

要求：
1. 保持原查询的核心意图不变
2. 补充相关的同义词、近义词和相关概念
3. 将口语化表达转换为更规范的检索查询
4. 如果查询已经很完整，可以保持原样或稍作优化
5. 扩展后的查询应该更有利于在知识库中检索到相关信息

用户查询：{query}

请直接返回扩展后的查询文本，不要添加任何解释或说明。"""
    },
    "time_extraction": {
        "prompt": """请分析用户查询中的时间信息。

用户查询：{query}

请提取查询中包含的时间描述（如"去年"、"2023年"、"近三个月"等）。
如果查询中包含明确的时间范围或时间点，请返回has_time=true。

请返回JSON格式：
{{
    "has_time": boolean,
    "time_text": "提取的时间文本，如果没有则为空字符串"
}}"""
    },
    "time_matching": {
        "prompt": """请判断查询时间与文档时间是否匹配。

查询时间：{query_time}

文档时间列表：
{doc_time_list}

请判断哪些文档的时间在查询时间范围内。
请返回JSON格式：
{{
    "matched_doc_ids": ["匹配的doc_id1", "匹配的doc_id2"]
}}"""
    },
    "result_summary_strict": {
        "prompt": """请基于以下参考资料回答用户问题。
请严格仅使用提供的参考资料，不要使用你的外部知识。如果参考资料不足以回答问题，请说明。

用户问题：{query}

参考资料：
{context}

请生成回答："""
    },
    "result_summary_supplement": {
        "prompt": """请回答用户问题。
主要基于提供的参考资料，但可以适当结合你的通用知识进行补充和完善，使回答更加通顺和完整。

用户问题：{query}

参考资料：
{context}

请生成回答："""
    }
}


def get_router_prompt_config_path(topic: str) -> Path:
    """Get the path to the RouterRAG prompt config file for a given topic."""
    filename = f"{topic}.yaml"
    return ROUTER_PROMPT_DIR / filename


def load_router_prompt_config(topic: str) -> Dict[str, Any]:
    """Load the RouterRAG prompt configuration for a topic."""
    path = get_router_prompt_config_path(topic)
    
    # If specific topic config doesn't exist, create it with default config
    if not path.exists():
        persist_router_prompt_config(topic, DEFAULT_ROUTER_PROMPT_CONFIG)
        return DEFAULT_ROUTER_PROMPT_CONFIG

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        # If load fails, return default but don't overwrite user's broken file
        return DEFAULT_ROUTER_PROMPT_CONFIG


def persist_router_prompt_config(topic: str, config: Dict[str, Any]) -> None:
    """Save the RouterRAG prompt configuration for a topic."""
    path = get_router_prompt_config_path(topic)
    
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
