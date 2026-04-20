from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict

from .graph_runtime import run_report_compilation_graph
from .report_ir import summarize_report_ir


def _report_source(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_data = payload.get("report_data")
    if isinstance(report_data, dict):
        return report_data
    return payload


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _non_empty_strings(values: Any, *, limit: int = 6) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item or "").strip()][:limit]


def _extract_function_top_items(snapshot: Dict[str, Any], function_name: str) -> list[dict[str, Any]]:
    functions = snapshot.get("functions")
    if not isinstance(functions, list):
        return []
    for item in functions:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").strip() != function_name:
            continue
        top_items = item.get("top_items")
        if isinstance(top_items, list):
            return [row for row in top_items if isinstance(row, dict)]
    return []


def _load_snapshot_function_rows(snapshot: Dict[str, Any], function_name: str) -> list[dict[str, Any]]:
    source_root = str(snapshot.get("source_root") or "").strip()
    if not source_root:
        return []
    filename_map = {
        "keywords": ("keywords", "keywords.json"),
        "attitude": ("attitude", "attitude.json"),
    }
    function_folder, filename = filename_map.get(function_name, ("", ""))
    if not function_folder or not filename:
        return []
    path = Path(source_root) / function_folder / "总体" / filename
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _load_bertopic_time_nodes(snapshot: Dict[str, Any]) -> list[dict[str, Any]]:
    source_root = str(snapshot.get("source_root") or "").strip()
    if not source_root:
        return []
    path = Path(source_root) / "6主题时间趋势.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    time_nodes = payload.get("time_nodes") if isinstance(payload, dict) else None
    if isinstance(time_nodes, list):
        return [item for item in time_nodes if isinstance(item, dict)]
    return []


def _normalize_sentiment_rows(snapshot: Dict[str, Any]) -> list[dict[str, Any]]:
    overview = snapshot.get("overview") if isinstance(snapshot.get("overview"), dict) else {}
    sentiment = overview.get("sentiment") if isinstance(overview, dict) and isinstance(overview.get("sentiment"), dict) else {}
    rows = [
        {"name": str(key).strip().lower(), "value": float(value)}
        for key, value in sentiment.items()
        if str(key or "").strip() and isinstance(value, (int, float)) and float(value) > 0
    ]
    if not rows:
        fallback_rows = _extract_function_top_items(snapshot, "attitude") or _load_snapshot_function_rows(snapshot, "attitude")
        rows = []
        for item in fallback_rows:
            name = str(item.get("name") or item.get("label") or "").strip().lower()
            value = item.get("value") or item.get("count")
            if name and isinstance(value, (int, float)) and float(value) > 0:
                rows.append({"name": name, "value": float(value)})
    label_map = {
        "positive": "positive",
        "正向": "positive",
        "积极": "positive",
        "neutral": "neutral",
        "中性": "neutral",
        "negative": "negative",
        "负向": "negative",
        "消极": "negative",
    }
    normalized: dict[str, float] = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
    for item in rows:
        label = label_map.get(str(item.get("name") or "").strip(), str(item.get("name") or "").strip())
        if label in normalized:
            normalized[label] = max(normalized[label], float(item.get("value") or 0.0))
    return [{"name": key, "value": normalized[key]} for key in ("positive", "neutral", "negative") if normalized[key] > 0]


def _normalize_keyword_rows(snapshot: Dict[str, Any], *, limit: int = 30) -> list[dict[str, Any]]:
    overview = snapshot.get("overview") if isinstance(snapshot.get("overview"), dict) else {}
    keywords = overview.get("top_keywords") if isinstance(overview, dict) else None
    rows: list[dict[str, Any]] = []
    if isinstance(keywords, list):
        for item in keywords:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("word") or item.get("label") or "").strip()
            value = item.get("value") or item.get("count") or item.get("weight")
            if name and isinstance(value, (int, float)):
                rows.append({"name": name, "value": float(value)})
    elif isinstance(keywords, dict):
        rows = [{"name": str(key).strip(), "value": float(value)} for key, value in keywords.items() if str(key or "").strip() and isinstance(value, (int, float))]
    if len(rows) < limit:
        fallback_rows = _load_snapshot_function_rows(snapshot, "keywords") or _extract_function_top_items(snapshot, "keywords")
        if fallback_rows:
            rows = []
            for item in fallback_rows:
                name = str(item.get("name") or item.get("word") or item.get("label") or "").strip()
                value = item.get("value") or item.get("count") or item.get("weight")
                if name and isinstance(value, (int, float)):
                    rows.append({"name": name, "value": float(value)})
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(rows, key=lambda row: float(row.get("value") or 0.0), reverse=True):
        key = str(item.get("name") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append({"name": key, "value": float(item.get("value") or 0.0)})
        if len(deduped) >= limit:
            break
    return deduped


def _build_sentiment_figure(snapshot: Dict[str, Any], insight: Dict[str, Any]) -> Dict[str, Any]:
    rows = _normalize_sentiment_rows(snapshot)
    if not rows:
        return {}
    figure_id = "fig:basic-analysis:sentiment-overview"
    option = {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 36, "right": 16, "top": 28, "bottom": 28},
        "xAxis": {"type": "category", "data": [row["name"] for row in rows]},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": [row["value"] for row in rows], "barMaxWidth": 48}],
    }
    return {
        "figure": {
            "figure_id": figure_id,
            "intent": "comparison",
            "chart_type": "bar",
            "dataset_ref": f"dataset:{figure_id}",
            "option_ref": f"option:{figure_id}",
            "caption": "图1 情感分析总体",
            "placement_anchor": "basic_analysis_insight",
            "source_claim_ids": [],
            "source_metric_ids": ["basic_analysis.sentiment"],
            "policy_version": "figure-policy.v1",
            "render_status": "ready",
        },
        "artifact": {
            "figure_id": figure_id,
            "version": 1,
            "status": "ready",
            "dataset_ref": f"dataset:{figure_id}",
            "option_ref": f"option:{figure_id}",
            "caption": "图1 情感分析总体",
            "placement_anchor": "basic_analysis_insight",
            "source_claim_ids": [],
            "source_metric_ids": ["basic_analysis.sentiment"],
            "policy_version": "figure-policy.v1",
            "render_status": "ready",
            "chart_spec": {
                "chart_type": "bar",
                "dataset_ref": f"dataset:{figure_id}",
                "option_ref": f"option:{figure_id}",
                "caption": "图1 情感分析总体",
                "blocked_reason": "",
                "renderer": "echarts",
                "option": option,
            },
            "dataset": {
                "dataset_ref": f"dataset:{figure_id}",
                "rows": rows,
                "preview_rows": rows[:12],
                "digest": str((insight.get("summary") or "") or "basic-analysis-sentiment"),
            },
            "option": {
                "option_ref": f"option:{figure_id}",
                "renderer": "echarts",
                "option": option,
            },
            "approval_records": [],
        },
    }


def _build_wordcloud_figure(snapshot: Dict[str, Any], insight: Dict[str, Any]) -> Dict[str, Any]:
    rows = _normalize_keyword_rows(snapshot, limit=30)
    if not rows:
        return {}
    figure_id = "fig:basic-analysis:keywords-wordcloud"
    option = {
        "tooltip": {},
        "series": [
            {
                "type": "wordCloud",
                "shape": "circle",
                "width": "100%",
                "height": "100%",
                "sizeRange": [14, 42],
                "gridSize": 8,
                "drawOutOfBound": False,
                "data": rows,
            }
        ],
    }
    return {
        "figure": {
            "figure_id": figure_id,
            "intent": "distribution",
            "chart_type": "word-cloud",
            "dataset_ref": f"dataset:{figure_id}",
            "option_ref": f"option:{figure_id}",
            "caption": "图2 高频关键词词云",
            "placement_anchor": "basic_analysis_insight",
            "source_claim_ids": [],
            "source_metric_ids": ["basic_analysis.keywords"],
            "policy_version": "figure-policy.v1",
            "render_status": "ready",
        },
        "artifact": {
            "figure_id": figure_id,
            "version": 1,
            "status": "ready",
            "dataset_ref": f"dataset:{figure_id}",
            "option_ref": f"option:{figure_id}",
            "caption": "图2 高频关键词词云",
            "placement_anchor": "basic_analysis_insight",
            "source_claim_ids": [],
            "source_metric_ids": ["basic_analysis.keywords"],
            "policy_version": "figure-policy.v1",
            "render_status": "ready",
            "chart_spec": {
                "chart_type": "word-cloud",
                "dataset_ref": f"dataset:{figure_id}",
                "option_ref": f"option:{figure_id}",
                "caption": "图2 高频关键词词云",
                "blocked_reason": "",
                "renderer": "echarts",
                "option": option,
            },
            "dataset": {
                "dataset_ref": f"dataset:{figure_id}",
                "rows": rows,
                "preview_rows": rows[:20],
                "digest": str((insight.get("summary") or "") or "basic-analysis-keywords"),
            },
            "option": {
                "option_ref": f"option:{figure_id}",
                "renderer": "echarts",
                "option": option,
            },
            "approval_records": [],
        },
    }


def _build_bertopic_figure(snapshot: Dict[str, Any], insight: Dict[str, Any]) -> Dict[str, Any]:
    temporal_points = snapshot.get("temporal_points")
    llm_clusters = snapshot.get("llm_clusters")
    if not isinstance(temporal_points, list):
        temporal_points = []
    if not any(isinstance(item, dict) and isinstance(item.get("themes"), list) for item in temporal_points):
        temporal_points = _load_bertopic_time_nodes(snapshot) or temporal_points
    cluster_names: list[str] = []
    if isinstance(llm_clusters, list):
        for item in llm_clusters[:5]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                cluster_names.append(name)
    theme_totals: dict[str, float] = {name: 0.0 for name in cluster_names}
    rows = []
    for item in temporal_points[:120]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("date") or item.get("time_label") or item.get("period") or "").strip()
        themes = item.get("themes")
        if not label or not isinstance(themes, list):
            continue
        theme_map: dict[str, float] = {}
        for theme in themes:
            if not isinstance(theme, dict):
                continue
            name = str(theme.get("name") or theme.get("label") or "").strip()
            value = theme.get("value") or theme.get("score") or theme.get("count")
            if not name or not isinstance(value, (int, float)):
                continue
            numeric = float(value)
            theme_map[name] = numeric
            theme_totals[name] = theme_totals.get(name, 0.0) + numeric
        if theme_map:
            rows.append({"name": label, "themes": theme_map})
    if not rows:
        # Fallback to total-volume trend only when theme-level data is unavailable.
        for item in temporal_points[:120]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("date") or item.get("time_label") or item.get("period") or "").strip()
            value = item.get("value") or item.get("score") or item.get("count")
            if label and isinstance(value, (int, float)):
                rows.append({"name": label, "themes": {"主题热度": float(value)}})
                theme_totals["主题热度"] = theme_totals.get("主题热度", 0.0) + float(value)
    if not rows:
        return {}
    ordered_theme_names = [name for name in cluster_names if theme_totals.get(name, 0.0) > 0][:5]
    for name, _ in sorted(theme_totals.items(), key=lambda item: item[1], reverse=True):
        if len(ordered_theme_names) >= 5:
            break
        if not name or name in ordered_theme_names:
            continue
        ordered_theme_names.append(name)
    if not ordered_theme_names:
        ordered_theme_names = ["主题热度"]
    figure_id = "fig:bertopic:temporal-evolution"
    labels = [row["name"] for row in rows]
    series = []
    for name in ordered_theme_names:
        series.append(
            {
                "name": name,
                "type": "line",
                "smooth": True,
                "showSymbol": False,
                "data": [float((row.get("themes") or {}).get(name) or 0.0) for row in rows],
            }
        )
    option = {
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 0},
        "grid": {"left": 36, "right": 16, "top": 28, "bottom": 28},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value"},
        "series": series,
    }
    return {
        "figure": {
            "figure_id": figure_id,
            "intent": "trend",
            "chart_type": "line",
            "dataset_ref": f"dataset:{figure_id}",
            "option_ref": f"option:{figure_id}",
            "caption": "图3 主题演变图",
            "placement_anchor": "bertopic_insight",
            "source_claim_ids": [],
            "source_metric_ids": ["bertopic.temporal_points"],
            "policy_version": "figure-policy.v1",
            "render_status": "ready",
        },
        "artifact": {
            "figure_id": figure_id,
            "version": 1,
            "status": "ready",
            "dataset_ref": f"dataset:{figure_id}",
            "option_ref": f"option:{figure_id}",
            "caption": "图3 主题演变图",
            "placement_anchor": "bertopic_insight",
            "source_claim_ids": [],
            "source_metric_ids": ["bertopic.temporal_points"],
            "policy_version": "figure-policy.v1",
            "render_status": "ready",
            "chart_spec": {
                "chart_type": "line",
                "dataset_ref": f"dataset:{figure_id}",
                "option_ref": f"option:{figure_id}",
                "caption": "图3 主题演变图",
                "blocked_reason": "",
                "renderer": "echarts",
                "option": option,
            },
            "dataset": {
                "dataset_ref": f"dataset:{figure_id}",
                "rows": rows,
                "preview_rows": rows[:16],
                "digest": str((insight.get("summary") or "") or "bertopic-temporal"),
            },
            "option": {
                "option_ref": f"option:{figure_id}",
                "renderer": "echarts",
                "option": option,
            },
            "approval_records": [],
        },
    }


def _build_dynamic_figures(structured_payload: Dict[str, Any]) -> Dict[str, Any]:
    source = _report_source(structured_payload)
    basic_snapshot = _first_dict(
        structured_payload.get("basic_analysis_snapshot"),
        source.get("basic_analysis_snapshot"),
    )
    basic_insight = _first_dict(
        structured_payload.get("basic_analysis_insight"),
        source.get("basic_analysis_insight"),
    )
    bertopic_snapshot = _first_dict(
        structured_payload.get("bertopic_snapshot"),
        source.get("bertopic_snapshot"),
    )
    bertopic_insight = _first_dict(
        structured_payload.get("bertopic_insight"),
        source.get("bertopic_insight"),
    )
    built = [
        _build_sentiment_figure(basic_snapshot, basic_insight),
        _build_wordcloud_figure(basic_snapshot, basic_insight),
        _build_bertopic_figure(bertopic_snapshot, bertopic_insight),
    ]
    figures = [item["figure"] for item in built if isinstance(item, dict) and isinstance(item.get("figure"), dict)]
    artifacts = [item["artifact"] for item in built if isinstance(item, dict) and isinstance(item.get("artifact"), dict)]
    return {"figures": figures, "artifacts": artifacts}


def render_markdown(payload: Dict[str, Any]) -> str:
    compiled = compile_markdown_artifacts(payload)
    return str(compiled.get("markdown") or "").strip()


def compile_markdown_artifacts(
    payload: Dict[str, Any],
    *,
    allow_review_pending: bool = False,
    event_callback: Callable[[Dict[str, Any]], None] | None = None,
    checkpointer_path: str = "",
    graph_thread_id: str = "",
    review_decision: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    report_ir = payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {}
    if not report_ir:
        raise ValueError("render_markdown requires ReportIR and no longer accepts raw structured payload compilation.")
    utility_assessment = report_ir.get("utility_assessment") if isinstance(report_ir.get("utility_assessment"), dict) else {}
    review_decision_text = str((review_decision or {}).get("decision") or "").strip().lower()
    compiled = run_report_compilation_graph(
        payload,
        event_callback=event_callback,
        checkpointer_path=checkpointer_path,
        graph_thread_id=graph_thread_id,
        review_decision=review_decision,
    )
    if str(compiled.get("status") or "").strip() == "interrupted":
        return compiled
    markdown_conformance = compiled.get("factual_conformance") if isinstance(compiled.get("factual_conformance"), dict) else {}
    graph_review_metadata = markdown_conformance.get("metadata") if isinstance(markdown_conformance.get("metadata"), dict) else {}
    graph_review_decision_text = str(
        graph_review_metadata.get("review_decision")
        or graph_review_metadata.get("decision")
        or ""
    ).strip().lower()
    effective_review_decision_text = review_decision_text or graph_review_decision_text
    human_override_accepted = effective_review_decision_text in {"approve", "edit"}
    markdown_conformance = {
        **markdown_conformance,
        "metadata": {
            **dict(markdown_conformance.get("metadata") or {}),
            "utility_assessment": utility_assessment,
            "human_override_accepted": human_override_accepted,
            "review_decision": effective_review_decision_text,
        },
    }
    compiled["factual_conformance"] = markdown_conformance
    compiled["utility_assessment"] = utility_assessment
    compiled["review_required"] = bool(markdown_conformance.get("requires_human_review") or compiled.get("review_required"))
    return compiled


def build_structured_digest(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_ir = payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {}
    if report_ir:
        return summarize_report_ir(report_ir)
    source = _report_source(payload)
    task = source.get("task") if isinstance(source.get("task"), dict) else {}
    conclusion = source.get("conclusion") if isinstance(source.get("conclusion"), dict) else {}
    report_document = payload.get("report_document") if isinstance(payload.get("report_document"), dict) else {}
    report_ir = payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {}
    return {
        "topic": str(task.get("topic_label") or task.get("topic_identifier") or "").strip(),
        "range": {
            "start": str(task.get("start") or "").strip(),
            "end": str(task.get("end") or "").strip(),
        },
        "summary": str(conclusion.get("executive_summary") or "").strip(),
        "key_findings": [str(item).strip() for item in (conclusion.get("key_findings") or []) if str(item or "").strip()][:6],
        "key_risks": [str(item).strip() for item in (conclusion.get("key_risks") or []) if str(item or "").strip()][:6],
        "counts": {
            "timeline": len(source.get("timeline") or []),
            "subjects": len(source.get("subjects") or []),
            "evidence": len(source.get("key_evidence") or []),
            "conflicts": len(source.get("conflict_points") or []),
            "propagation": len(source.get("propagation_features") or []),
            "risks": len(source.get("risk_judgement") or []),
            "actions": len(source.get("suggested_actions") or []),
            "citations": len(source.get("citations") or []),
            "sections": len(report_document.get("sections") or []),
            "figures": len(report_ir.get("figures") or payload.get("figures") or []),
        },
    }


def _evaluate_markdown_health(markdown: str) -> Dict[str, Any]:
    text = str(markdown or "").strip()
    if not text:
        return {
            "is_healthy": False,
            "degraded_reason": "empty_markdown",
            "heading_count": 0,
            "body_line_count": 0,
        }
    lines = [line.rstrip() for line in text.splitlines()]
    heading_count = len([line for line in lines if line.lstrip().startswith("## ")])
    body_lines = [
        line.strip()
        for line in lines
        if line.strip()
        and not line.lstrip().startswith("#")
        and not line.lstrip().startswith(">")
        and line.strip() != "---"
    ]
    non_heading_chars = sum(len(line) for line in body_lines)
    only_headings = bool(heading_count) and not body_lines
    too_sparse = non_heading_chars < 120
    degraded_reason = ""
    if only_headings:
        degraded_reason = "heading_only_skeleton"
    elif too_sparse:
        degraded_reason = "markdown_body_too_sparse"
    return {
        "is_healthy": not bool(degraded_reason),
        "degraded_reason": degraded_reason,
        "heading_count": heading_count,
        "body_line_count": len(body_lines),
        "non_heading_char_count": non_heading_chars,
    }


def build_full_payload(
    structured_payload: Dict[str, Any],
    markdown: str,
    *,
    cache_version: int,
    draft_bundle: Dict[str, Any] | None = None,
    draft_bundle_v2: Dict[str, Any] | None = None,
    styled_draft_bundle: Dict[str, Any] | None = None,
    factual_conformance: Dict[str, Any] | None = None,
    scene_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    source = _report_source(structured_payload)
    task = source.get("task") if isinstance(source.get("task"), dict) else {}
    title = str(task.get("topic_label") or task.get("topic_identifier") or "AI 完整报告").strip() or "AI 完整报告"
    report_ir = structured_payload.get("report_ir") if isinstance(structured_payload.get("report_ir"), dict) else {}
    artifact_manifest = structured_payload.get("artifact_manifest") if isinstance(structured_payload.get("artifact_manifest"), dict) else {}
    dynamic_figures = _build_dynamic_figures(structured_payload)
    merged_report_ir = dict(report_ir or {})
    merged_artifact_manifest = dict(artifact_manifest or {})
    merged_report_ir["figures"] = list(dynamic_figures.get("figures") or [])
    merged_artifact_manifest["figures"] = list(dynamic_figures.get("artifacts") or [])
    utility_assessment = report_ir.get("utility_assessment") if isinstance(report_ir.get("utility_assessment"), dict) else {}
    markdown_text = str(markdown or "").strip()
    markdown_health = _evaluate_markdown_health(markdown_text)
    report_ir_summary = summarize_report_ir(merged_report_ir) if merged_report_ir else {}
    degraded_reason = str(markdown_health.get("degraded_reason") or "").strip()
    draft_bundle_v2_payload = draft_bundle_v2 if isinstance(draft_bundle_v2, dict) else {}
    draft_bundle_v2_meta = draft_bundle_v2_payload.get("metadata") if isinstance(draft_bundle_v2_payload.get("metadata"), dict) else {}
    scene_payload = scene_profile if isinstance(scene_profile, dict) else {}
    selected_template = (
        draft_bundle_v2_meta.get("selected_template")
        if isinstance(draft_bundle_v2_meta.get("selected_template"), dict)
        else {
            "template_id": str(scene_payload.get("template_id") or "").strip(),
            "template_name": str(scene_payload.get("template_name") or "").strip(),
            "template_path": str(scene_payload.get("template_path") or "").strip(),
            "scene_id": str(scene_payload.get("scene_id") or "").strip(),
            "scene_label": str(scene_payload.get("scene_label") or "").strip(),
            "score": float(scene_payload.get("selection_score") or 0.0),
            "matched_reasons": list(scene_payload.get("matched_reasons") or []),
        }
    )
    section_generation_receipts = (
        draft_bundle_v2_meta.get("section_generation_receipts")
        if isinstance(draft_bundle_v2_meta.get("section_generation_receipts"), list)
        else []
    )
    section_trace_annotations = (
        draft_bundle_v2_meta.get("section_trace_annotations")
        if isinstance(draft_bundle_v2_meta.get("section_trace_annotations"), list)
        else []
    )
    degraded_sections = (
        draft_bundle_v2_meta.get("degraded_sections")
        if isinstance(draft_bundle_v2_meta.get("degraded_sections"), list)
        else []
    )
    factual_payload = factual_conformance if isinstance(factual_conformance, dict) else {}
    factual_requires_review = bool(factual_payload.get("requires_human_review"))
    factual_issue_count = len(factual_payload.get("issues") or []) if isinstance(factual_payload.get("issues"), list) else 0
    compile_quality = "degraded" if degraded_sections or degraded_reason or factual_requires_review or factual_issue_count else "healthy"
    publish_status = "pending_review" if factual_requires_review else "ready"
    full_payload = {
        **structured_payload,
        "report_ir": merged_report_ir,
        "artifact_manifest": merged_artifact_manifest,
        "title": title,
        "rangeText": f"{str(task.get('start') or '').strip()} -> {str(task.get('end') or '').strip()}",
        "markdown": markdown_text,
        "has_markdown_output": bool(markdown_text),
        "compile_quality": compile_quality,
        "publish_status": publish_status,
        "degraded_reason": degraded_reason,
        "selected_template": selected_template,
        "template_match_reasons": list(selected_template.get("matched_reasons") or []) if isinstance(selected_template, dict) else [],
        "section_write_receipts": section_generation_receipts,
        "section_generation_receipts": section_generation_receipts,
        "section_trace_annotations": section_trace_annotations,
        "degraded_sections": degraded_sections,
        "draft_bundle": draft_bundle if isinstance(draft_bundle, dict) else {},
        "draft_bundle_v2": draft_bundle_v2_payload,
        "styled_draft_bundle": styled_draft_bundle if isinstance(styled_draft_bundle, dict) else {},
        "report_ir_summary": report_ir_summary,
        "meta": {
            "cache_version": int(cache_version),
            "thread_id": str(task.get("thread_id") or "").strip(),
            "structured_digest": build_structured_digest(structured_payload),
            "report_ir_summary": report_ir_summary,
            "artifact_manifest": merged_artifact_manifest,
            "figure_ids": [str(item.get("figure_id") or "").strip() for item in (merged_report_ir.get("figures") or []) if isinstance(item, dict)],
            "figure_policy_version": str((((merged_report_ir.get("figures") or [{}])[0] if isinstance(merged_report_ir.get("figures"), list) and merged_report_ir.get("figures") else {}).get("policy_version")) or "figure-policy.v1"),
            "draft_trace_summary": {
                "unit_count": len(((draft_bundle or {}).get("units")) or []),
                "section_order": list(((draft_bundle or {}).get("section_order")) or []),
            },
            "style_trace_summary": {
                "unit_count": len(((styled_draft_bundle or {}).get("units")) or []),
                "rewrite_ops": list(((styled_draft_bundle or {}).get("rewrite_ops")) or []),
                "policy_version": str((styled_draft_bundle or {}).get("policy_version") or ""),
            },
            "factual_conformance": factual_conformance if isinstance(factual_conformance, dict) else {},
            "markdown_health": markdown_health,
            "selected_template": selected_template,
            "template_match_reasons": list(selected_template.get("matched_reasons") or []) if isinstance(selected_template, dict) else [],
            "section_write_receipts": section_generation_receipts,
            "section_generation_receipts": section_generation_receipts,
            "section_trace_annotations": section_trace_annotations,
            "degraded_sections": degraded_sections,
            "has_markdown_output": bool(markdown_text),
            "compile_quality": compile_quality,
            "publish_status": publish_status,
            "utility_assessment": utility_assessment,
            "utility_gate_trace": {
                "decision": str(utility_assessment.get("decision") or "").strip(),
                "missing_dimensions": list(utility_assessment.get("missing_dimensions") or []),
                "fallback_trace": list(utility_assessment.get("fallback_trace") or []),
                "improvement_trace": list(utility_assessment.get("improvement_trace") or []),
            },
        },
    }
    if isinstance(structured_payload.get("meta"), dict):
        full_payload["meta"] = {**structured_payload.get("meta"), **full_payload["meta"]}
    return full_payload
