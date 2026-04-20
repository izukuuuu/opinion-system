from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from server_support.archive_locator import ArchiveLocator, compose_folder_name
from server_support.topic_context import TopicContext

from ..capability_adapters import (
    build_basic_analysis_insight,
    build_bertopic_insight,
    collect_basic_analysis_snapshot,
    collect_bertopic_snapshot,
    ensure_bertopic_results,
)
from ...utils.setting.paths import bucket, ensure_bucket, get_data_root
from ..knowledge_loader import load_report_knowledge
from ..runtime_bootstrap import ANALYZE_FILE_MAP, collect_explain_outputs, ensure_analyze_results, ensure_explain_results
from ..skills import load_report_skill_context
from .runtime_contract import RUNTIME_CONTRACT_VERSION


TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,24}")
_RUNTIME_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._@:+~-]+")


def _safe_runtime_component(value: str, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    normalized = _RUNTIME_COMPONENT_RE.sub("-", text).strip("-")
    return normalized or fallback


@dataclass(frozen=True)
class RuntimeWorkspaceLayout:
    project_identifier: str
    topic_identifier: str
    start: str
    end: str

    @property
    def project_component(self) -> str:
        source = self.project_identifier or self.topic_identifier
        return _safe_runtime_component(source, fallback="topic")

    @property
    def range_component(self) -> str:
        start = _safe_runtime_component(self.start, fallback="start")
        end = _safe_runtime_component(self.end or self.start, fallback=start)
        return f"{start}_{end}"

    @property
    def workspace_root(self) -> str:
        return f"/workspace/projects/{self.project_component}/reports/{self.range_component}"

    @property
    def state_root(self) -> str:
        return f"{self.workspace_root}/state"

    @property
    def section_packets_root(self) -> str:
        return f"{self.state_root}/section_packets"

    @property
    def section_drafts_root(self) -> str:
        return f"{self.state_root}/section_drafts"

    @property
    def base_context_path(self) -> str:
        return f"{self.workspace_root}/base_context.json"

    @property
    def summary_path(self) -> str:
        return f"{self.workspace_root}/summary.md"

    def state_file(self, relative_path: str) -> str:
        rel = str(relative_path or "").strip().lstrip("/")
        return f"{self.state_root}/{rel}"

    def state_glob(self, relative_glob: str) -> str:
        rel = str(relative_glob or "").strip().lstrip("/")
        return f"{self.state_root}/{rel}"


def build_runtime_workspace_layout(
    *,
    project_identifier: str,
    topic_identifier: str,
    start: str,
    end: str,
) -> RuntimeWorkspaceLayout:
    return RuntimeWorkspaceLayout(
        project_identifier=str(project_identifier or "").strip(),
        topic_identifier=str(topic_identifier or "").strip(),
        start=str(start or "").strip(),
        end=str(end or start or "").strip() or str(start or "").strip(),
    )


def _safe_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _iter_numbers(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_numbers(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_numbers(item)


def _iter_records(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        if any(key in value for key in ("date", "day", "name", "value", "count", "label")):
            yield value
        for item in value.values():
            yield from _iter_records(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_records(item)


def _guess_total_volume(volume_payload: Any) -> int:
    if not isinstance(volume_payload, dict):
        return 0
    candidates = [
        volume_payload.get("total"),
        volume_payload.get("total_count"),
        volume_payload.get("volume"),
        volume_payload.get("count"),
        volume_payload.get("summary"),
    ]
    values = [int(num) for item in candidates for num in _iter_numbers(item)]
    if values:
        return max(values)
    flat = [int(num) for num in _iter_numbers(volume_payload)]
    return max(flat) if flat else 0


def _guess_peak_from_trends(trends_payload: Any) -> Dict[str, Any]:
    best = {"date": "", "value": 0}
    for item in _iter_records(trends_payload):
        label = str(item.get("date") or item.get("day") or item.get("name") or item.get("label") or "").strip()
        values = [int(num) for num in _iter_numbers(item.get("value") if "value" in item else item.get("count") if "count" in item else item)]
        if not values:
            continue
        current = max(values)
        if current > int(best["value"] or 0):
            best = {"date": label, "value": current}
    return best


def _guess_sentiment(attitude_payload: Any) -> Dict[str, int]:
    out = {"positive": 0, "neutral": 0, "negative": 0}
    if isinstance(attitude_payload, dict):
        iterable: Iterable[Tuple[Any, Any]] = attitude_payload.items()
    else:
        iterable = []
    for key, value in iterable:
        lowered = str(key or "").lower()
        total = max((int(num) for num in _iter_numbers(value)), default=0)
        if any(token in lowered for token in ("positive", "积极", "正向")):
            out["positive"] = max(out["positive"], total)
        elif any(token in lowered for token in ("neutral", "中性")):
            out["neutral"] = max(out["neutral"], total)
        elif any(token in lowered for token in ("negative", "消极", "负向")):
            out["negative"] = max(out["negative"], total)
    for item in _iter_records(attitude_payload):
        label = str(
            item.get("name")
            or item.get("label")
            or item.get("sentiment")
            or item.get("polarity")
            or ""
        ).strip().lower()
        total = max((int(num) for num in _iter_numbers(item.get("value") if "value" in item else item.get("count") if "count" in item else item)), default=0)
        if any(token in label for token in ("positive", "积极", "正向")):
            out["positive"] = max(out["positive"], total)
        elif any(token in label for token in ("neutral", "中性")):
            out["neutral"] = max(out["neutral"], total)
        elif any(token in label for token in ("negative", "消极", "负向")):
            out["negative"] = max(out["negative"], total)
    return out


def _collect_top_labels(payload: Any, *, max_items: int = 8) -> List[Dict[str, Any]]:
    ranked: List[Tuple[int, str]] = []
    for item in _iter_records(payload):
        label = str(
            item.get("name")
            or item.get("label")
            or item.get("keyword")
            or item.get("topic")
            or item.get("classification")
            or ""
        ).strip()
        if not label:
            continue
        value = max((int(num) for num in _iter_numbers(item.get("value") if "value" in item else item.get("count") if "count" in item else item)), default=0)
        ranked.append((value, label))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [{"label": label, "value": value} for value, label in ranked[: max(1, max_items)]]


def _iter_source_rows(topic_identifier: str, start: str, end: str) -> Iterable[Dict[str, Any]]:
    folder = compose_folder_name(start, end)
    overall = bucket("fetch", topic_identifier, folder) / "总体.jsonl"
    candidates: List[Path] = [overall]
    uploads_dir = get_data_root() / "projects" / topic_identifier / "uploads" / "jsonl"
    if uploads_dir.exists():
        candidates.extend(sorted(path for path in uploads_dir.glob("*.jsonl") if path.is_file()))
    for file_path in candidates:
        if not file_path.exists():
            continue
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        yield payload
        except Exception:
            continue


def _make_snippet(row: Dict[str, Any], max_chars: int = 140) -> str:
    text = " ".join(
        [
            str(row.get("title") or "").strip(),
            str(row.get("content") or row.get("contents") or "").strip(),
        ]
    ).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _extract_date_text(row: Dict[str, Any]) -> str:
    text = str(row.get("published_at") or row.get("publish_time") or row.get("date") or "").strip()
    matched = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    return matched.group(1) if matched else text[:10]


def _build_raw_row_digest(topic_identifier: str, start: str, end: str, *, max_items: int = 40) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    platform_counter: Counter[str] = Counter()
    token_counter: Counter[str] = Counter()
    total = 0
    for row in _iter_source_rows(topic_identifier, start, end):
        total += 1
        platform = str(row.get("platform") or "").strip()
        if platform:
            platform_counter[platform] += 1
        for token in TOKEN_RE.findall(str(row.get("title") or ""))[:6]:
            token_counter[token] += 1
        if len(items) < max_items:
            items.append(
                {
                    "title": str(row.get("title") or "").strip(),
                    "url": str(row.get("url") or "").strip(),
                    "platform": platform,
                    "published_at": _extract_date_text(row),
                    "snippet": _make_snippet(row),
                }
            )
    return {
        "sample_items": items,
        "sample_count": len(items),
        "raw_count": total,
        "top_platforms": [{"label": name, "value": count} for name, count in platform_counter.most_common(8)],
        "top_tokens": [{"label": name, "value": count} for name, count in token_counter.most_common(12)],
    }


def build_base_context(
    topic_identifier: str,
    start: str,
    end: str,
    *,
    topic_label: str,
    mode: str,
    thread_id: str = "",
) -> Dict[str, Any]:
    ctx = TopicContext(identifier=topic_identifier, display_name=topic_label, aliases=[])
    skill_context = load_report_skill_context(topic_label)
    document_type = str(skill_context.get("documentType") or "analysis_report").strip() or "analysis_report"
    ensure_analyze_results(topic_identifier, start=start, end=end, ctx=ctx)
    ensure_explain_results(topic_identifier, start=start, end=end, ctx=ctx)
    bertopic_state = ensure_bertopic_results(
        topic_identifier,
        start=start,
        end=end,
        ctx=ctx,
        run_if_missing=document_type == "analysis_report" or str(mode or "").strip().lower() == "research",
    )
    analyze_root = ArchiveLocator(ctx).resolve_result_dir("analyze", start, end)
    if not analyze_root:
        folder = compose_folder_name(start, end)
        analyze_root = bucket("analyze", topic_identifier, folder)

    modules: Dict[str, Any] = {}
    for module_name, filename in ANALYZE_FILE_MAP.items():
        candidate = analyze_root / module_name / "总体" / filename
        modules[module_name] = _safe_json(candidate)

    raw_digest = _build_raw_row_digest(topic_identifier, start, end)
    explain_state = collect_explain_outputs(ctx, start, end)
    knowledge_context = load_report_knowledge(topic_label)
    basic_analysis_snapshot = collect_basic_analysis_snapshot(
        topic_identifier,
        start,
        end,
        topic_label=topic_label,
        ctx=ctx,
    )
    bertopic_snapshot = collect_bertopic_snapshot(
        topic_identifier,
        start,
        end,
        topic_label=topic_label,
        ctx=ctx,
    )
    overview = {
        "total_volume": _guess_total_volume(modules.get("volume")),
        "peak": _guess_peak_from_trends(modules.get("trends")),
        "sentiment": _guess_sentiment(modules.get("attitude")),
        "top_themes": _collect_top_labels(modules.get("classification")),
        "top_keywords": _collect_top_labels(modules.get("keywords")),
        "top_publishers": _collect_top_labels(modules.get("publishers")),
        "top_platforms": raw_digest.get("top_platforms") or _collect_top_labels(modules.get("publishers")),
    }
    return {
        "topic_identifier": topic_identifier,
        "topic_label": topic_label,
        "time_range": {"start": start, "end": end},
        "mode": mode,
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        "task_contract": {
            "contract_id": f"{topic_identifier}:{start}:{end or start}",
            "topic_identifier": topic_identifier,
            "topic_label": topic_label,
            "start": start,
            "end": end,
            "mode": mode,
            "thread_id": str(thread_id or "").strip(),
        },
        "analyze_root": str(analyze_root),
        "analysis_modules": modules,
        "overview": overview,
        "raw_digest": raw_digest,
        "explain_state": explain_state,
        "knowledge_context": knowledge_context,
        "skill_context": skill_context,
        "document_type": document_type,
        "bertopic_state": bertopic_state,
        "basic_analysis_snapshot": basic_analysis_snapshot,
        "basic_analysis_insight": build_basic_analysis_insight(basic_analysis_snapshot),
        "bertopic_snapshot": bertopic_snapshot,
        "bertopic_insight": build_bertopic_insight(bertopic_snapshot),
    }


def build_analyze_results_payload(
    topic_identifier: str,
    start: str,
    end: str,
    *,
    topic_label: str,
) -> Dict[str, Any]:
    ctx = TopicContext(identifier=topic_identifier, display_name=topic_label, aliases=[])
    ensure_analyze_results(topic_identifier, start=start, end=end, ctx=ctx)
    analyze_root = ArchiveLocator(ctx).resolve_result_dir("analyze", start, end)
    if not analyze_root:
        folder = compose_folder_name(start, end)
        analyze_root = bucket("analyze", topic_identifier, folder)
    results: List[Dict[str, Any]] = []
    for func_name in sorted(path.name for path in analyze_root.iterdir() if path.is_dir()):
        func_dir = analyze_root / func_name
        targets: List[Dict[str, Any]] = []
        for target_dir in sorted(path for path in func_dir.iterdir() if path.is_dir()):
            filename = ANALYZE_FILE_MAP.get(func_name, "result.json")
            file_path = target_dir / filename
            if not file_path.exists():
                candidates = sorted(target_dir.glob("*.json"))
                if not candidates:
                    continue
                file_path = candidates[0]
            data = _safe_json(file_path)
            targets.append({"target": target_dir.name, "file": file_path.name, "data": data})
        if targets:
            results.append({"name": func_name, "targets": targets})
    return {
        "topic": topic_label,
        "range": {"start": start, "end": end or start},
        "functions": results,
    }


def build_workspace_files(
    base_context: Dict[str, Any],
    *,
    layout: RuntimeWorkspaceLayout | None = None,
) -> Dict[str, Dict[str, Any]]:
    from deepagents.backends.utils import create_file_data

    task_contract = base_context.get("task_contract") if isinstance(base_context.get("task_contract"), dict) else {}
    resolved_layout = layout or build_runtime_workspace_layout(
        project_identifier=str(base_context.get("project_identifier") or task_contract.get("project_identifier") or "").strip(),
        topic_identifier=str(base_context.get("topic_identifier") or task_contract.get("topic_identifier") or "").strip(),
        start=str((base_context.get("time_range") or {}).get("start") or task_contract.get("start") or "").strip(),
        end=str((base_context.get("time_range") or {}).get("end") or task_contract.get("end") or "").strip(),
    )

    files: Dict[str, Dict[str, Any]] = {}
    files[resolved_layout.base_context_path] = create_file_data(json.dumps(base_context, ensure_ascii=False, indent=2))
    if task_contract:
        task_contract_text = json.dumps(task_contract, ensure_ascii=False, indent=2)
        files[resolved_layout.state_file("task_contract.json")] = create_file_data(task_contract_text)
    overview = base_context.get("overview") if isinstance(base_context.get("overview"), dict) else {}
    raw_digest = base_context.get("raw_digest") if isinstance(base_context.get("raw_digest"), dict) else {}
    sample_lines = []
    for item in raw_digest.get("sample_items") or []:
        if not isinstance(item, dict):
            continue
        sample_lines.append(
            f"- {str(item.get('published_at') or '').strip()} | {str(item.get('platform') or '').strip()} | {str(item.get('title') or '').strip()}\n"
            f"  {str(item.get('snippet') or '').strip()}"
        )
    summary_md = [
        f"# {str(base_context.get('topic_label') or '').strip()}",
        "",
        f"- 区间：{str(base_context.get('time_range', {}).get('start') or '').strip()} -> {str(base_context.get('time_range', {}).get('end') or '').strip()}",
        f"- 模式：{str(base_context.get('mode') or '').strip()}",
        f"- 总声量：{int(overview.get('total_volume') or 0)}",
        f"- 峰值：{str((overview.get('peak') or {}).get('date') or '').strip()} / {int((overview.get('peak') or {}).get('value') or 0)}",
        "",
        "## 样本摘录",
        *sample_lines[:12],
    ]
    summary_text = "\n".join(summary_md).strip()
    files[resolved_layout.summary_path] = create_file_data(summary_text)
    # Keep the state directory available for agent writes without pre-creating
    # individual payload files that can trigger "already exists" write errors.
    files[resolved_layout.state_file(".keep")] = create_file_data("")
    return files


def ensure_cache_dir(topic_identifier: str, start: str, end: str) -> Path:
    return ensure_cache_dir_v2(topic_identifier, start, end)


def _safe_storage_component(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # Disallow path separators to avoid escaping the data root.
    return text.replace("\\", "-").replace("/", "-").strip("-")


def resolve_report_storage_topic(*, topic_identifier: str, project_identifier: str = "") -> str:
    """Build the storage topic for report artifacts.

    New format (preferred): <project_identifier>-<topic_identifier>
    Legacy format: <topic_identifier>
    """
    topic = _safe_storage_component(topic_identifier)
    project = _safe_storage_component(project_identifier)
    if project and topic and not topic.startswith(f"{project}-"):
        return f"{project}-{topic}"
    return topic or project or "topic"


def ensure_cache_dir_v2(topic_identifier: str, start: str, end: str, *, project_identifier: str = "") -> Path:
    project_component = _safe_storage_component(project_identifier) or _safe_storage_component(topic_identifier) or "topic"
    report_dir = get_data_root() / "projects" / project_component / "reports" / compose_folder_name(start, end)
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir
