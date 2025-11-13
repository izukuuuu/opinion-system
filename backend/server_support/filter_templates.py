"""
过滤提示词模板管理辅助模块

本模块为舆情分析系统的过滤（filter）环节提供提示词模板的生成、加载、保存与规范化等工具，主要功能包括：

1. 生成默认的过滤提示词模板文本，支持自定义主题和分类。
2. 读取和持久化每个专题的过滤模板配置（YAML格式），包含模板内容、主题、分类、元数据等。
3. 支持模板的自动路径规范化，保证不同专题模板文件互不冲突。
4. 提供模板的元数据结构化读取，便于前端展示和后端接口调用。
5. 兼容异常处理，保证配置读写健壮性。

主要导出函数：
- build_filter_template_text：生成默认过滤模板文本
- filter_template_path：获取专题模板文件路径
- load_filter_template_config：加载过滤模板配置
- persist_filter_template_config：保存过滤模板配置
- utc_now：获取当前UTC时间戳

适用场景：
- 过滤提示词模板管理
- 后端接口与管理后台
- 专题自定义筛选规则
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .paths import FILTER_PROMPT_DIR


def utc_now() -> str:
    """Return the current UTC timestamp as an ISO 8601 string."""

    return datetime.now(timezone.utc).isoformat()


def filter_template_path(topic: str) -> Path:
    """Return the file path for a topic-specific filter template."""

    safe_topic = str(topic or "").strip()
    if not safe_topic:
        raise ValueError("Missing topic identifier")
    normalised = safe_topic.replace("/", "_").replace("\\", "_")
    FILTER_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    return FILTER_PROMPT_DIR / f"{normalised}.yaml"


def build_filter_template_text(theme: str, categories: List[str]) -> str:
    """Generate a default filter template text."""

    subject = (theme or "").strip() or "该专题"
    cleaned_categories = [str(item).strip() for item in categories if str(item or "").strip()]

    lines = [
        f"你是一名舆情筛选助手，请判断以下文本是否与“{subject}”专题相关，并输出 JSON 结果：",
        "规则：",
        f"1. 判断文本是否与{subject}相关，相关返回true，否则返回false；",
    ]
    if cleaned_categories:
        option_text = "、".join(cleaned_categories)
        lines.append(f"2. 如果文本相关，请从以下分类中选择最贴切的一项：{option_text}。")
        lines.append('返回格式: {"相关": true或false, "分类": "<分类名称，必须来自上述列表>"}')
    else:
        lines.append("2. 如果文本相关，请给出合适的分类描述。")
        lines.append('返回格式: {"相关": true或false, "分类": "分类名称"}')
    lines.append("文本：{text}")
    return "\n".join(lines)


def load_filter_template_config(topic: str) -> Dict[str, Any]:
    """Load persisted filter template metadata for a topic."""

    path = filter_template_path(topic)
    if not path.exists():
        return {
            "topic": topic,
            "exists": False,
            "template": "",
            "topic_theme": "",
            "categories": [],
            "metadata": {},
        }
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover - defensive for invalid YAML
        raise ValueError(f"读取提示词配置失败: {exc}") from exc

    template = str(payload.get("template") or "")
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    theme = str(metadata.get("topic_theme") or metadata.get("theme") or "")
    categories = metadata.get("categories") or []
    if not isinstance(categories, list):
        categories = []
    parsed_categories = [str(item).strip() for item in categories if str(item or "").strip()]

    return {
        "topic": topic,
        "exists": True,
        "template": template,
        "topic_theme": theme,
        "categories": parsed_categories,
        "metadata": metadata,
        "updated_at": metadata.get("updated_at"),
        "path": str(path),
    }


def persist_filter_template_config(
    topic: str,
    theme: str,
    categories: List[str],
    template_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist the filter template metadata and return the refreshed payload."""

    path = filter_template_path(topic)
    clean_theme = (theme or "").strip()
    clean_categories = [str(item).strip() for item in categories if str(item or "").strip()]
    final_template = (
        str(template_text).strip()
        if isinstance(template_text, str) and str(template_text).strip()
        else build_filter_template_text(clean_theme, clean_categories)
    )

    payload = {
        "template": final_template,
        "metadata": {
            "topic_theme": clean_theme,
            "categories": clean_categories,
            "updated_at": utc_now(),
            "version": 1,
        },
    }

    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)

    return load_filter_template_config(topic)


__all__ = [
    "build_filter_template_text",
    "filter_template_path",
    "load_filter_template_config",
    "persist_filter_template_config",
    "utc_now",
]
