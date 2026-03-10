"""
数据预处理流水线相关服务辅助函数

本模块为舆情分析系统后端的流水线（pipeline）相关操作提供统一的参数解析、主题/项目标识解析、数据集元数据处理等工具，主要功能包括：

1. 解析API请求中的主题、项目、标签等多种标识，自动推断标准化的topic identifier。
2. 支持结合数据集元数据、项目管理器等多源信息，提升兼容性与健壮性。
3. 提供流水线各阶段（如merge/clean等）参数准备与校验，自动检查原始数据集文件可用性。
4. 支持主题标签的标准化处理，便于后续流程统一展示与日志记录。
5. 适用于后端接口、自动化流水线编排、管理后台等场景。

主要导出函数：
- resolve_topic_identifier：解析主题标识与项目上下文
- prepare_pipeline_args：校验并准备pipeline参数
- normalise_topic_label：标准化主题标签

适用场景：
- 流水线API参数解析
- 后端服务编排
- 数据处理自动化
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .dataset_files import (
    ensure_raw_dataset_availability,
)
from .topic_context import TopicContext, context_to_tuple, resolve_context


def resolve_topic_identifier(
    payload: Dict[str, Any],
    project_manager,
) -> Tuple[str, str, str, Dict[str, Any]]:
    """Resolve topic identifiers and project context from the API payload.

    This is a thin backward-compatible wrapper around
    :func:`topic_context.resolve_context`.  New code should prefer
    ``resolve_context()`` directly and work with :class:`TopicContext`.
    """

    ctx = resolve_context(payload, project_manager)
    return context_to_tuple(ctx)


def prepare_pipeline_args(
    payload: Dict[str, Any],
    project_manager,
    *,
    allow_missing_date: bool = False,
) -> Tuple[str, str, str]:
    """Validate payload and prepare merge/clean pipeline arguments."""

    topic_identifier, display_name, log_project, dataset_meta = resolve_topic_identifier(payload, project_manager)
    date = str(payload.get("date") or "").strip()
    if not date and not allow_missing_date:
        raise ValueError("Missing required field(s): date")
    if date:
        ensure_raw_dataset_availability(topic_identifier, date, dataset_meta)
    return topic_identifier, date, display_name or topic_identifier, log_project or topic_identifier


def normalise_topic_label(value: Any) -> str:
    """Normalise optional topic label strings."""

    if isinstance(value, str):
        return value.strip()
    return ""


__all__ = [
    "normalise_topic_label",
    "prepare_pipeline_args",
    "resolve_topic_identifier",
]
