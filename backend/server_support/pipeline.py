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

from src.project import normalise_project_name  # type: ignore

from .dataset_files import (
    ensure_raw_dataset_availability,
    iter_unique_strings,
    resolve_dataset_payload,
)
from .paths import DATA_PROJECTS_ROOT


def resolve_topic_identifier(
    payload: Dict[str, Any],
    project_manager,
) -> Tuple[str, str, str, Dict[str, Any]]:
    """Resolve topic identifiers and project context from the API payload."""

    project_name = str(payload.get("project") or "").strip()
    topic_value = str(payload.get("topic") or "").strip()
    topic_label = str(payload.get("topic_label") or "").strip()
    dataset_meta = resolve_dataset_payload(project_name, payload.get("dataset_id"))

    candidates = []
    if dataset_meta:
        project_id = dataset_meta.get("project_id")
        if isinstance(project_id, str):
            candidates.append(project_id)
        slug = dataset_meta.get("project_slug")
        if isinstance(slug, str):
            candidates.append(slug)
        meta_project = dataset_meta.get("project")
        if isinstance(meta_project, str):
            candidates.append(meta_project)
        meta_topic = dataset_meta.get("topic_label")
        if isinstance(meta_topic, str):
            candidates.append(meta_topic)

    if project_name:
        resolved_id = project_manager.resolve_identifier(project_name)
        if resolved_id:
            candidates.append(resolved_id)
        candidates.append(normalise_project_name(project_name))
        candidates.append(project_name)

    if topic_value:
        candidates.append(topic_value)

    if topic_label:
        candidates.append(topic_label)

    ordered_candidates = iter_unique_strings(candidates)
    if not ordered_candidates:
        raise ValueError("Missing required field(s): topic or project")

    resolved_topic = next(
        (candidate for candidate in ordered_candidates if (DATA_PROJECTS_ROOT / candidate).exists()),
        None,
    )
    if not resolved_topic:
        resolved_topic = ordered_candidates[0]

    canonical_topic = project_manager.resolve_identifier(resolved_topic)
    if canonical_topic:
        resolved_topic = canonical_topic

    dataset_topic_label = dataset_meta.get("topic_label") if isinstance(dataset_meta.get("topic_label"), str) else None
    display_name = topic_label or dataset_topic_label or project_name or topic_value or resolved_topic

    log_project = project_name or dataset_meta.get("project") or resolved_topic

    return resolved_topic, display_name, str(log_project), dataset_meta


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
