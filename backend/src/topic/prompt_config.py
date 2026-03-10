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
DEFAULT_TOPIC_BERTOPIC_MIN_TOPICS = 3
DEFAULT_RECLUSTER_TOPIC_LIMIT = 80
DEFAULT_TOPIC_SAMPLE_SIZE = 4
DEFAULT_JUDGE_SAMPLE_PER_TOPIC = 3
DEFAULT_LARGE_CLUSTER_DOC_SHARE = 0.08
DEFAULT_LARGE_CLUSTER_DOC_COUNT = 0
DEFAULT_MAX_DROP_RATIO = 0.45

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

DEFAULT_DROP_RULE_PROMPT = """
【无关主题丢弃规则（必须执行）】
请先判断每个候选主题是否与专题“{FOCUS_TOPIC}”相关。

判定标准（满足任一可判为无关）：
1. 关键词与专题核心语义没有直接关联；
2. 主要讨论对象偏离专题目标（例如泛娱乐、泛生活、广告噪声）；
3. 无法给出与专题有因果或场景关联的解释。

输出要求（每个聚类条目都必须包含）：
- drop: true/false
- drop_reason: 当 drop=true 时，写明剔除原因；当 drop=false 时可为空字符串

注意：
- 被判定为无关的条目必须单独标记 drop=true，不要混入正常主题；
- 不要省略字段，不要输出额外解释文字。
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
    if parsed < 3:
        return 3
    if parsed > 50:
        return 50
    return parsed


def _coerce_positive_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def _coerce_ratio(value: Any, default: float, minimum: float = 0.0, maximum: float = 0.95) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def topic_bertopic_prompt_path(topic: str) -> Path:
    """Return YAML path for a topic-specific BERTopic prompt config."""

    normalised = _normalise_topic(topic)
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    return PROMPT_DIR / f"{normalised}.yaml"


def _normalise_custom_filters(raw: Any) -> list:
    """Coerce raw value into a list of {category, description} dicts."""
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cat = str(item.get("category") or "").strip()
        desc = str(item.get("description") or "").strip()
        if cat or desc:
            result.append({"category": cat, "description": desc})
    return result


def _default_payload(topic: str, path: Path, exists: bool = False) -> Dict[str, Any]:
    return {
        "topic": topic,
        "exists": exists,
        "path": str(path),
        "target_topics": DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS,
        "max_topics": DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS,
        "min_topics": DEFAULT_TOPIC_BERTOPIC_MIN_TOPICS,
        "recluster_topic_limit": DEFAULT_RECLUSTER_TOPIC_LIMIT,
        "topic_sample_size": DEFAULT_TOPIC_SAMPLE_SIZE,
        "judge_sample_per_topic": DEFAULT_JUDGE_SAMPLE_PER_TOPIC,
        "large_cluster_doc_share": DEFAULT_LARGE_CLUSTER_DOC_SHARE,
        "large_cluster_doc_count": DEFAULT_LARGE_CLUSTER_DOC_COUNT,
        "max_drop_ratio": DEFAULT_MAX_DROP_RATIO,
        "use_multi_agent": True,
        "default_drop_rule_prompt": DEFAULT_DROP_RULE_PROMPT,
        "recluster_system_prompt": DEFAULT_RECLUSTER_SYSTEM_PROMPT,
        "recluster_user_prompt": DEFAULT_RECLUSTER_USER_PROMPT,
        "keyword_system_prompt": DEFAULT_KEYWORDS_SYSTEM_PROMPT,
        "keyword_user_prompt": DEFAULT_KEYWORDS_USER_PROMPT,
        "drop_rule_prompt": DEFAULT_DROP_RULE_PROMPT,
        "custom_filters": [],
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

    resolved_topics = _coerce_target_topics(
        settings.get("max_topics") or settings.get("target_topics", DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS)
    )
    use_multi_agent_val = settings.get("use_multi_agent")
    if use_multi_agent_val is None:
        use_multi_agent = True
    elif isinstance(use_multi_agent_val, bool):
        use_multi_agent = use_multi_agent_val
    else:
        use_multi_agent = str(use_multi_agent_val).lower().strip() not in ("false", "0", "no")

    payload.update(
        {
            "exists": True,
            "target_topics": resolved_topics,
            "max_topics": resolved_topics,
            "min_topics": _coerce_positive_int(
                settings.get("min_topics", DEFAULT_TOPIC_BERTOPIC_MIN_TOPICS),
                DEFAULT_TOPIC_BERTOPIC_MIN_TOPICS,
                3,
                50,
            ),
            "recluster_topic_limit": _coerce_positive_int(
                settings.get("recluster_topic_limit", DEFAULT_RECLUSTER_TOPIC_LIMIT),
                DEFAULT_RECLUSTER_TOPIC_LIMIT,
                20,
                200,
            ),
            "topic_sample_size": _coerce_positive_int(
                settings.get("topic_sample_size", DEFAULT_TOPIC_SAMPLE_SIZE),
                DEFAULT_TOPIC_SAMPLE_SIZE,
                2,
                8,
            ),
            "judge_sample_per_topic": _coerce_positive_int(
                settings.get("judge_sample_per_topic", DEFAULT_JUDGE_SAMPLE_PER_TOPIC),
                DEFAULT_JUDGE_SAMPLE_PER_TOPIC,
                2,
                6,
            ),
            "large_cluster_doc_share": _coerce_ratio(
                settings.get("large_cluster_doc_share", DEFAULT_LARGE_CLUSTER_DOC_SHARE),
                DEFAULT_LARGE_CLUSTER_DOC_SHARE,
                0.01,
                0.9,
            ),
            "large_cluster_doc_count": _coerce_positive_int(
                settings.get("large_cluster_doc_count", DEFAULT_LARGE_CLUSTER_DOC_COUNT),
                DEFAULT_LARGE_CLUSTER_DOC_COUNT,
                0,
                10_000_000,
            ),
            "max_drop_ratio": _coerce_ratio(
                settings.get("max_drop_ratio", DEFAULT_MAX_DROP_RATIO),
                DEFAULT_MAX_DROP_RATIO,
                0.0,
                0.9,
            ),
            "use_multi_agent": use_multi_agent,
            "drop_rule_prompt": str(
                settings.get("drop_rule_prompt") or DEFAULT_DROP_RULE_PROMPT
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
            "custom_filters": _normalise_custom_filters(
                settings.get("custom_filters")
            ),
            "metadata": metadata,
        }
    )
    return payload


def persist_topic_bertopic_prompt_config(
    topic: str,
    target_topics: Any,
    drop_rule_prompt: str,
    recluster_system_prompt: str,
    recluster_user_prompt: str,
    keyword_system_prompt: str,
    keyword_user_prompt: str,
    custom_filters: Any = None,
) -> Dict[str, Any]:
    """Persist BERTopic prompt config and return refreshed payload."""

    path = topic_bertopic_prompt_path(topic)
    final_target_topics = _coerce_target_topics(target_topics)

    final_recluster_system = (
        str(recluster_system_prompt or "").rstrip() or DEFAULT_RECLUSTER_SYSTEM_PROMPT
    )
    final_drop_rule_prompt = (
        str(drop_rule_prompt or "").rstrip() or DEFAULT_DROP_RULE_PROMPT
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
            "max_topics": final_target_topics,
            "min_topics": DEFAULT_TOPIC_BERTOPIC_MIN_TOPICS,
            "recluster_topic_limit": DEFAULT_RECLUSTER_TOPIC_LIMIT,
            "topic_sample_size": DEFAULT_TOPIC_SAMPLE_SIZE,
            "judge_sample_per_topic": DEFAULT_JUDGE_SAMPLE_PER_TOPIC,
            "large_cluster_doc_share": DEFAULT_LARGE_CLUSTER_DOC_SHARE,
            "large_cluster_doc_count": DEFAULT_LARGE_CLUSTER_DOC_COUNT,
            "max_drop_ratio": DEFAULT_MAX_DROP_RATIO,
            "use_multi_agent": True,
            "drop_rule_prompt": final_drop_rule_prompt,
            "custom_filters": _normalise_custom_filters(custom_filters),
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
            "version": 3,
        },
    }

    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(yaml_payload, fh, allow_unicode=True, sort_keys=False)

    return load_topic_bertopic_prompt_config(topic)


__all__ = [
    "DEFAULT_DROP_RULE_PROMPT",
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
