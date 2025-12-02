"""
项目归档辅助工具

本模块用于舆情分析系统的数据归档与阶段处理相关的元数据汇总与日期解析，主要功能包括：

1. 汇总指定主题下各数据处理层（如 raw, merge, clean, filter 等）的归档目录和文件信息，统计文件数量、总大小、更新时间等元数据。
2. 按层级（layer）和数据集ID（dataset_id）筛选归档信息，便于前端或接口快速获取项目各阶段的数据状态。

主要导出函数：
- collect_layer_archives: 获取单层归档元数据列表
- collect_project_archives: 获取多层归档元数据字典
- resolve_stage_processing_date: 解析阶段处理日期（含依赖关系）

依赖说明：
- 依赖 DATA_PROJECTS_ROOT 作为项目数据根目录
- 支持自定义层级和数据集ID筛选
- 兼容异常处理，保证接口健壮性

适用场景：
- 后台归档浏览
- 流程编排与自动化
- 阶段依赖检查与提示
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .paths import DATA_PROJECTS_ROOT

__all__ = [
    "collect_layer_archives",
    "collect_project_archives",
    "resolve_stage_processing_date",
]

_DEFAULT_LAYERS: Tuple[str, ...] = ("raw", "merge", "clean", "filter")
_ALLOWED_LAYERS: Tuple[str, ...] = _DEFAULT_LAYERS + ("fetch", "analyze", "reports", "results")
_STAGE_DEPENDENCIES = {
    "clean": "merge",
    "filter": "clean",
}


def _layer_dir(topic_identifier: str, layer: str) -> Path:
    return DATA_PROJECTS_ROOT / topic_identifier / layer


def _iter_layer_dates(topic_identifier: str, layer: str) -> Iterable[Path]:
    base_dir = _layer_dir(topic_identifier, layer)
    if not base_dir.exists():
        return []
    try:
        entries = [path for path in base_dir.iterdir() if path.is_dir()]
    except OSError:
        return []
    return sorted(entries, key=lambda path: path.name, reverse=True)


def _format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _summarise_date_dir(layer: str, date_dir: Path, dataset_id: Optional[str]) -> Dict[str, Any]:
    file_count = 0
    total_size = 0
    latest_mtime = date_dir.stat().st_mtime
    dataset_hit = False
    files: List[str] = []
    channels: List[str] = []

    try:
        children = list(date_dir.iterdir())
    except OSError:
        children = []

    for child in children:
        if not child.is_file():
            continue
        file_count += 1
        try:
            stat = child.stat()
        except OSError:
            continue
        total_size += stat.st_size
        latest_mtime = max(latest_mtime, stat.st_mtime)
        files.append(child.name)
        if dataset_id and dataset_id in child.name:
            dataset_hit = True
        if child.suffix.lower() == ".jsonl":
            channels.append(child.stem)

    summary: Dict[str, Optional[str]] = {
        "date": date_dir.name,
        "file_count": file_count,
        "total_size": total_size,
        "updated_at": _format_timestamp(latest_mtime),
    }
    summary["path"] = str(date_dir)
    if dataset_id:
        summary["matches_dataset"] = dataset_hit

    if layer in {"raw", "fetch"}:
        summary["files"] = files
    if layer != "raw":
        summary["channels"] = sorted(channels)
    return summary


def collect_layer_archives(
    topic_identifier: str,
    layer: str,
    *,
    dataset_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return archive metadata for a single layer."""

    archives: List[Dict[str, Optional[str]]] = []
    for date_dir in _iter_layer_dates(topic_identifier, layer):
        try:
            archives.append(_summarise_date_dir(layer, date_dir, dataset_id))
        except OSError:
            continue
    return archives


def collect_project_archives(
    topic_identifier: str,
    *,
    layers: Optional[Sequence[str]] = None,
    dataset_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return archive metadata for multiple layers of a project."""

    selected_layers = tuple(item for item in (layers or _DEFAULT_LAYERS) if item in _ALLOWED_LAYERS)
    data: Dict[str, List[Dict[str, Optional[str]]]] = {}
    for layer in selected_layers:
        data[layer] = collect_layer_archives(topic_identifier, layer, dataset_id=dataset_id)
    return data


def resolve_stage_processing_date(
    topic_identifier: str,
    stage: str,
    requested_date: Optional[str],
) -> Tuple[str, Optional[str]]:
    """Resolve the effective processing date for a stage, falling back to the latest archive."""

    stage_lower = stage.lower()
    dependency_layer = _STAGE_DEPENDENCIES.get(stage_lower)
    date_value = (requested_date or "").strip()
    if not dependency_layer:
        if not date_value:
            raise ValueError("Missing required field(s): date")
        return date_value, None

    available_archives = collect_layer_archives(topic_identifier, dependency_layer)
    if not available_archives:
        display = dependency_layer.capitalize()
        raise ValueError(f"未找到可用的 {display} 存档，请先执行上一阶段。")

    available_dates = [archive.get("date") for archive in available_archives if archive.get("date")]

    if date_value and date_value in available_dates:
        return date_value, None

    fallback_date = available_dates[0]
    return fallback_date or date_value, (date_value or None)
