"""BERTopic prompt configuration helpers.

This module centralizes prompt loading/saving for BERTopic + LLM reclustering.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml

from ..utils.setting.paths import get_configs_root

PROMPT_DIR = get_configs_root() / "prompt" / "topic_bertopic"
PROMPT_RECLUSTER_KEY = "topic_bertopic_recluster"
PROMPT_KEYWORDS_KEY = "topic_bertopic_keywords"
DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS = 8

DEFAULT_RECLUSTER_SYSTEM_PROMPT = (
    "你是一个专业的文本分析专家，擅长对主题进行归纳、命名和聚类。"
)

DEFAULT_RECLUSTER_USER_PROMPT = """
请将以下 BERTopic 主题结果合并为 {TARGET_TOPICS} 个更高层级的类别。

输入数据：
{input_data}

要求：
1. 优先合并语义相近、关键词重叠高的主题；
2. 每个原始主题都必须被分配到某个类别；
3. 类别名称应清晰、简洁，避免空泛词；
4. 仅输出 JSON，不要输出解释文字。

输出 JSON 格式：
{{
  "clusters": [
    {{
      "cluster_name": "类别名称",
      "topics": ["原始主题1", "原始主题2"],
      "description": "该类别的简要描述"
    }}
  ]
}}
""".strip()

DEFAULT_KEYWORDS_SYSTEM_PROMPT = "你是一个专业的文本分析专家。"

DEFAULT_KEYWORDS_USER_PROMPT = """
为以下主题类别生成 5-8 个核心关键词：

类别名称：{cluster_name}
包含主题：{topics}
描述：{description}

请直接输出关键词列表，使用逗号分隔，不要输出额外说明。
""".strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_topic(topic: str) -> str:
    safe_topic = str(topic or "").strip()
    if not safe_topic:
        raise ValueError("Missing topic identifier")
    return safe_topic.replace("/", "_").replace("\\", "_")


def _coerce_target_topics(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS
    if parsed < 2:
        return 2
    if parsed > 50:
        return 50
    return parsed


def topic_bertopic_prompt_path(topic: str) -> Path:
    """Return YAML path for a topic-specific BERTopic prompt config."""

    normalised = _normalise_topic(topic)
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    return PROMPT_DIR / f"{normalised}.yaml"


def _default_payload(topic: str, path: Path, exists: bool = False) -> Dict[str, Any]:
    return {
        "topic": topic,
        "exists": exists,
        "path": str(path),
        "target_topics": DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS,
        "recluster_system_prompt": DEFAULT_RECLUSTER_SYSTEM_PROMPT,
        "recluster_user_prompt": DEFAULT_RECLUSTER_USER_PROMPT,
        "keyword_system_prompt": DEFAULT_KEYWORDS_SYSTEM_PROMPT,
        "keyword_user_prompt": DEFAULT_KEYWORDS_USER_PROMPT,
        "metadata": {},
    }


def load_topic_bertopic_prompt_config(topic: str) -> Dict[str, Any]:
    """Load BERTopic prompt config for a topic, with defaults."""

    path = topic_bertopic_prompt_path(topic)
    payload = _default_payload(topic, path, exists=False)
    if not path.exists():
        return payload

    try:
        with path.open("r", encoding="utf-8") as fh:
            yaml_payload = yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover - defensive for malformed YAML
        raise ValueError(f"读取 BERTopic 提示词配置失败: {exc}") from exc

    prompts = yaml_payload.get("prompts")
    if not isinstance(prompts, dict):
        prompts = {}
    settings = yaml_payload.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    metadata = yaml_payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    recluster_prompt = prompts.get(PROMPT_RECLUSTER_KEY)
    if not isinstance(recluster_prompt, dict):
        recluster_prompt = {}
    keywords_prompt = prompts.get(PROMPT_KEYWORDS_KEY)
    if not isinstance(keywords_prompt, dict):
        keywords_prompt = {}

    payload.update(
        {
            "exists": True,
            "target_topics": _coerce_target_topics(
                settings.get("target_topics", DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS)
            ),
            "recluster_system_prompt": str(
                recluster_prompt.get("system") or DEFAULT_RECLUSTER_SYSTEM_PROMPT
            ),
            "recluster_user_prompt": str(
                recluster_prompt.get("user") or DEFAULT_RECLUSTER_USER_PROMPT
            ),
            "keyword_system_prompt": str(
                keywords_prompt.get("system") or DEFAULT_KEYWORDS_SYSTEM_PROMPT
            ),
            "keyword_user_prompt": str(
                keywords_prompt.get("user") or DEFAULT_KEYWORDS_USER_PROMPT
            ),
            "metadata": metadata,
        }
    )
    return payload


def persist_topic_bertopic_prompt_config(
    topic: str,
    target_topics: Any,
    recluster_system_prompt: str,
    recluster_user_prompt: str,
    keyword_system_prompt: str,
    keyword_user_prompt: str,
) -> Dict[str, Any]:
    """Persist BERTopic prompt config and return refreshed payload."""

    path = topic_bertopic_prompt_path(topic)
    final_target_topics = _coerce_target_topics(target_topics)

    final_recluster_system = (
        str(recluster_system_prompt or "").rstrip() or DEFAULT_RECLUSTER_SYSTEM_PROMPT
    )
    final_recluster_user = (
        str(recluster_user_prompt or "").rstrip() or DEFAULT_RECLUSTER_USER_PROMPT
    )
    final_keyword_system = (
        str(keyword_system_prompt or "").rstrip() or DEFAULT_KEYWORDS_SYSTEM_PROMPT
    )
    final_keyword_user = (
        str(keyword_user_prompt or "").rstrip() or DEFAULT_KEYWORDS_USER_PROMPT
    )

    yaml_payload: Dict[str, Any] = {
        "settings": {
            "target_topics": final_target_topics,
        },
        "prompts": {
            PROMPT_RECLUSTER_KEY: {
                "system": final_recluster_system,
                "user": final_recluster_user,
            },
            PROMPT_KEYWORDS_KEY: {
                "system": final_keyword_system,
                "user": final_keyword_user,
            },
        },
        "metadata": {
            "updated_at": _utc_now(),
            "version": 2,
        },
    }

    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(yaml_payload, fh, allow_unicode=True, sort_keys=False)

    return load_topic_bertopic_prompt_config(topic)


__all__ = [
    "DEFAULT_KEYWORDS_SYSTEM_PROMPT",
    "DEFAULT_KEYWORDS_USER_PROMPT",
    "DEFAULT_RECLUSTER_SYSTEM_PROMPT",
    "DEFAULT_RECLUSTER_USER_PROMPT",
    "DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS",
    "PROMPT_KEYWORDS_KEY",
    "PROMPT_RECLUSTER_KEY",
    "load_topic_bertopic_prompt_config",
    "persist_topic_bertopic_prompt_config",
    "topic_bertopic_prompt_path",
]
