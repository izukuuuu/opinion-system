"""
统一专题上下文模型

将分散在 pipeline / analyze / topic / report 各模块的"专题身份"解析逻辑统一收敛到
一个 TopicContext dataclass，提供 resolve_context() 工厂函数。
所有路由只拿 TopicContext，不再自己拼 candidates。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.project import normalise_project_name  # type: ignore

from .dataset_files import iter_unique_strings, resolve_dataset_payload
from .paths import DATA_PROJECTS_ROOT


@dataclass
class TopicContext:
    """Canonical representation of a "topic" across the entire system.

    Attributes:
        project_identifier: Canonical project id (used for project-scoped storage).
        identifier:   Resolved local directory name (the canonical truth).
        display_name: User-facing label for UI and logs.
        db_topic:     Remote database name used for SQL queries.
        log_project:  Name recorded in operation logs.
        aliases:      All candidate strings collected during resolution,
                      useful for cross-identity directory scanning.
        dataset_meta: Raw dataset metadata dict (may be empty).
    """

    identifier: str
    project_identifier: str = ""
    display_name: str = ""
    db_topic: str = ""
    log_project: str = ""
    aliases: List[str] = field(default_factory=list)
    dataset_meta: Dict[str, Any] = field(default_factory=dict)


def resolve_context(
    payload: Dict[str, Any],
    project_manager,
) -> TopicContext:
    """Build a TopicContext from an API payload.

    This consolidates the candidate expansion logic previously duplicated in
    ``server_support.pipeline.resolve_topic_identifier``,
    ``src.analyze.api._collect_analyze_history``,
    ``src.topic.api._build_topic_identifier_candidates``, and
    ``src.report.api._collect_report_history``.
    """

    project_name = str(payload.get("project") or "").strip()
    topic_value = str(payload.get("topic") or "").strip()
    topic_label = str(payload.get("topic_label") or "").strip()
    dataset_meta = resolve_dataset_payload(project_name, payload.get("dataset_id"))

    # ── Collect candidates (same order as the original resolve_topic_identifier) ──
    candidates: List[str] = []

    if dataset_meta:
        for key in ("project_id", "project_slug", "project", "topic_label"):
            value = dataset_meta.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())

    resolved_project_identifier = ""
    if project_name:
        resolved_id = project_manager.resolve_identifier(project_name)
        if resolved_id:
            resolved_project_identifier = str(resolved_id).strip()
            candidates.append(resolved_project_identifier)
        candidates.append(normalise_project_name(project_name))
        candidates.append(project_name)

    if not resolved_project_identifier and dataset_meta:
        for key in ("project_id", "project_slug", "project"):
            value = dataset_meta.get(key)
            if isinstance(value, str) and value.strip():
                candidate = str(project_manager.resolve_identifier(value) or value).strip()
                if candidate:
                    resolved_project_identifier = candidate
                    break

    if topic_value:
        candidates.append(topic_value)

    if topic_label:
        candidates.append(topic_label)

    ordered_candidates = iter_unique_strings(candidates)
    if not ordered_candidates:
        raise ValueError("Missing required field(s): topic or project")

    # ── Resolve to an existing directory ──
    # 1. Direct match
    resolved_topic = next(
        (c for c in ordered_candidates if (DATA_PROJECTS_ROOT / c).exists()),
        None,
    )

    # 2. Suffix match: find directories ending with any candidate
    if not resolved_topic and DATA_PROJECTS_ROOT.exists():
        for candidate in ordered_candidates:
            suffix = f"-{candidate}"
            for dir_name in DATA_PROJECTS_ROOT.iterdir():
                if dir_name.is_dir() and dir_name.name.endswith(suffix):
                    resolved_topic = dir_name.name
                    break
            if resolved_topic:
                break

    if not resolved_topic:
        resolved_topic = ordered_candidates[0]

    canonical_topic = project_manager.resolve_identifier(resolved_topic)
    if canonical_topic:
        resolved_topic = canonical_topic

    # ── Derive display / db / log names ──
    dataset_topic_label = (
        dataset_meta.get("topic_label")
        if isinstance(dataset_meta.get("topic_label"), str)
        else None
    )
    display_name = (
        topic_label
        or dataset_topic_label
        or project_name
        or topic_value
        or resolved_topic
    )
    db_topic = topic_value or display_name or resolved_topic
    log_project = project_name or dataset_meta.get("project") or resolved_topic

    # ── Build full aliases list (superset used by ArchiveLocator) ──
    from src.utils.setting.paths import _normalise_topic  # type: ignore

    alias_seeds = list(ordered_candidates)
    if resolved_topic not in alias_seeds:
        alias_seeds.insert(0, resolved_topic)

    normalised_extras = [_normalise_topic(v) for v in alias_seeds if v]
    full_aliases = iter_unique_strings(alias_seeds + normalised_extras)

    return TopicContext(
        project_identifier=resolved_project_identifier,
        identifier=resolved_topic,
        display_name=display_name,
        db_topic=db_topic,
        log_project=str(log_project),
        aliases=full_aliases,
        dataset_meta=dataset_meta,
    )


def context_to_tuple(ctx: TopicContext) -> Tuple[str, str, str, Dict[str, Any]]:
    """Convert a TopicContext back to the legacy 4-tuple for backward compat."""
    return ctx.identifier, ctx.display_name, ctx.log_project, ctx.dataset_meta


__all__ = [
    "TopicContext",
    "context_to_tuple",
    "resolve_context",
]
