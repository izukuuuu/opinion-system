from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from .schemas import (
    ChartCatalogItem,
    DocumentComposerOutput,
    ReportAppendix,
    ReportDataBundle,
    ReportDocument,
    ReportHero,
    ReportSection,
)


ANALYSIS_META = {
    "attitude": {"label": "情绪与舆论质量", "description": "用于判断正负倾向、情绪分布和舆情强度。"},
    "classification": {"label": "议题与话题聚类", "description": "查看讨论究竟围绕哪些议题展开。"},
    "geography": {"label": "地域与话语场分布", "description": "用来补充不同区域的话语场差异。"},
    "keywords": {"label": "高频表达与关注焦点", "description": "补充用户最常提到的关键词和叙事中心。"},
    "publishers": {"label": "发布者与关键发声者", "description": "查看谁在带动讨论，哪些账号或媒体更活跃。"},
    "trends": {"label": "趋势与阶段演化", "description": "把时间维度图表嵌入这一章，用来判断传播节奏与阶段变化。"},
    "volume": {"label": "声量与渠道概览", "description": "把总量、渠道结构和峰值变化直接插进报告正文。"},
}
HORIZONTAL_BAR_FUNCTIONS = {"geography", "publishers", "keywords", "classification"}
LABEL_TRANSLATIONS = {
    "overall": "总体",
    "total": "总体",
    "summary": "总体",
    "positive": "正面",
    "negative": "负面",
    "neutral": "中性",
    "unknown": "未知",
    "weibo": "微博",
    "wechat": "微信",
    "weixin": "微信",
    "douyin": "抖音",
    "kuaishou": "快手",
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "zhihu": "知乎",
    "forum": "论坛",
    "newsapp": "新闻APP",
    "newswebsite": "新闻网站",
    "news": "新闻",
    "video": "视频",
    "selfmedia": "自媒体号",
    "officialmedia": "官方媒体",
}


def _slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", str(value or "").strip()).strip("-").lower()
    return text or "unknown"


def _compact_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower().replace("_", "").replace("-", ""))


def _translate_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未命名"
    if re.search(r"[\u4e00-\u9fff]", text):
        return text
    return LABEL_TRANSLATIONS.get(_compact_key(text), text)


def _extract_rows(payload: Any) -> List[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload.get("data") or []
    return []


def _row_name(row: dict) -> str:
    return str(row.get("displayName") or row.get("name") or row.get("label") or row.get("key") or "未命名").strip() or "未命名"


def _row_value(row: dict) -> float:
    for key in ("displayValue", "value", "count", "total"):
        value = row.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return 0.0


def _normalize_rows(payload: Any) -> List[dict]:
    rows: List[dict] = []
    for row in _extract_rows(payload):
        if not isinstance(row, dict):
            continue
        label = _translate_label(_row_name(row))
        value = _row_value(row)
        rows.append(
            {
                **row,
                "name": label,
                "label": label,
                "rawName": str(row.get("name") or row.get("label") or row.get("key") or "").strip(),
                "value": value,
                "displayValue": int(value) if float(value).is_integer() else round(value, 2),
            }
        )
    return rows


def _sort_rows(rows: List[dict]) -> List[dict]:
    return sorted(rows, key=lambda item: float(item.get("value") or 0), reverse=True)


def _bar_option(title: str, rows: List[dict], *, horizontal: bool) -> dict:
    ordered = _sort_rows(rows)
    categories = [_row_name(item) for item in ordered]
    values = [float(item.get("value") or 0) for item in ordered]
    category_axis = {
        "type": "category",
        "data": categories,
        "axisLabel": {"color": "#475569", "interval": 0},
        "axisLine": {"lineStyle": {"color": "#cbd5e1"}},
    }
    value_axis = {
        "type": "value",
        "axisLabel": {"color": "#475569"},
        "splitLine": {"lineStyle": {"color": "#e2e8f0"}},
    }
    return {
        "animation": False,
        "color": ["#4f46e5"],
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": 40 if not horizontal else 120, "right": 24, "top": 24, "bottom": 40, "containLabel": True},
        "xAxis": value_axis if horizontal else category_axis,
        "yAxis": {
            **category_axis,
            "inverse": True,
            "axisLabel": {"color": "#475569", "width": 96, "overflow": "truncate"},
        }
        if horizontal
        else value_axis,
        "series": [
            {
                "type": "bar",
                "data": values,
                "barMaxWidth": 28,
                "itemStyle": {"borderRadius": [8, 8, 0, 0] if not horizontal else [0, 8, 8, 0]},
            }
        ],
    }


def _line_option(title: str, rows: List[dict]) -> dict:
    ordered = list(rows)
    categories = [_row_name(item) for item in ordered]
    values = [float(item.get("value") or 0) for item in ordered]
    return {
        "animation": False,
        "color": ["#2563eb"],
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 40, "right": 24, "top": 24, "bottom": 40, "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": categories,
            "axisLabel": {"color": "#475569", "interval": 0},
            "axisLine": {"lineStyle": {"color": "#cbd5e1"}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#475569"},
            "splitLine": {"lineStyle": {"color": "#e2e8f0"}},
        },
        "series": [
            {
                "type": "line",
                "smooth": True,
                "data": values,
                "symbol": "circle",
                "symbolSize": 6,
                "lineStyle": {"width": 3},
                "areaStyle": {"opacity": 0.12},
            }
        ],
    }


def _pie_option(title: str, rows: List[dict]) -> dict:
    ordered = _sort_rows(rows)
    return {
        "animation": False,
        "tooltip": {"trigger": "item"},
        "legend": {"bottom": 0, "textStyle": {"color": "#475569"}},
        "series": [
            {
                "type": "pie",
                "radius": ["42%", "72%"],
                "center": ["50%", "44%"],
                "data": [{"name": _row_name(item), "value": float(item.get("value") or 0)} for item in ordered],
                "label": {"formatter": "{b}: {d}%"},
            }
        ],
    }


def _trend_flow_dataset(targets: List[dict]) -> dict:
    per_target: List[Tuple[str, List[dict]]] = []
    all_dates: set[str] = set()
    for target in targets:
        target_name = _translate_label(target.get("target"))
        rows = _normalize_rows(target.get("data"))
        if not rows:
            continue
        per_target.append((target_name, rows))
        for row in rows:
            all_dates.add(_row_name(row))
    if len(per_target) < 2 or not all_dates:
        return {}
    dates = sorted(all_dates)
    matrix: Dict[str, List[float]] = {}
    for target_name, rows in per_target:
        row_map = {_row_name(row): float(row.get("value") or 0) for row in rows}
        matrix[target_name] = [row_map.get(date, 0.0) for date in dates]
    summary_rows = [{"name": date, "label": date, "value": sum(matrix[name][idx] for name in matrix)} for idx, date in enumerate(dates)]
    return {
        "dates": dates,
        "series_names": list(matrix.keys()),
        "matrix": matrix,
        "summary_rows": summary_rows,
    }


def _stacked_area_option(dataset: dict) -> dict:
    return {
        "animation": False,
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0, "textStyle": {"color": "#475569"}},
        "grid": {"left": 40, "right": 24, "top": 24, "bottom": 50, "containLabel": True},
        "xAxis": {"type": "category", "data": dataset.get("dates") or [], "axisLabel": {"color": "#475569"}},
        "yAxis": {"type": "value", "axisLabel": {"color": "#475569"}, "splitLine": {"lineStyle": {"color": "#e2e8f0"}}},
        "series": [
            {
                "name": series_name,
                "type": "line",
                "stack": "total",
                "areaStyle": {"opacity": 0.16},
                "smooth": True,
                "data": dataset.get("matrix", {}).get(series_name) or [],
            }
            for series_name in dataset.get("series_names") or []
        ],
    }


def _stacked_share_option(dataset: dict) -> dict:
    dates = dataset.get("dates") or []
    matrix = dataset.get("matrix", {})
    series_names = dataset.get("series_names") or []
    totals = [sum(float(matrix.get(name, [0.0] * len(dates))[idx]) for name in series_names) for idx in range(len(dates))]
    return {
        "animation": False,
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0, "textStyle": {"color": "#475569"}},
        "grid": {"left": 40, "right": 24, "top": 24, "bottom": 50, "containLabel": True},
        "xAxis": {"type": "category", "data": dates, "axisLabel": {"color": "#475569"}},
        "yAxis": {
            "type": "value",
            "min": 0,
            "max": 100,
            "axisLabel": {"formatter": "{value}%", "color": "#475569"},
            "splitLine": {"lineStyle": {"color": "#e2e8f0"}},
        },
        "series": [
            {
                "name": series_name,
                "type": "line",
                "stack": "share",
                "areaStyle": {"opacity": 0.16},
                "smooth": True,
                "data": [
                    round(float(matrix.get(series_name, [0.0] * len(dates))[idx]) / totals[idx] * 100, 2) if totals[idx] else 0
                    for idx in range(len(dates))
                ],
            }
            for series_name in series_names
        ],
    }


def build_chart_catalog(functions_payload: List[dict]) -> List[dict]:
    catalog: List[dict] = []
    for section in functions_payload:
        func_name = str(section.get("name") or "").strip()
        meta = ANALYSIS_META.get(func_name, {})
        targets = list(section.get("targets") or [])
        for target in targets:
            target_label = _translate_label(target.get("target"))
            rows = _normalize_rows(target.get("data"))
            option = {}
            if rows:
                if func_name == "attitude":
                    option = _pie_option(meta.get("label") or func_name, rows)
                elif func_name == "trends":
                    option = _line_option(meta.get("label") or func_name, rows)
                else:
                    option = _bar_option(meta.get("label") or func_name, rows, horizontal=func_name in HORIZONTAL_BAR_FUNCTIONS)
            item = ChartCatalogItem(
                chart_id=f"{func_name}:{_slug(target_label)}",
                function_name=func_name,
                target=target_label,
                title=f"{meta.get('label') or func_name} · {target_label}",
                subtitle=str(meta.get("description") or "").strip(),
                option=option,
                rows=rows[:12],
                all_rows=rows,
                has_data=bool(rows),
                empty_message="暂无可视化数据",
            )
            catalog.append(item.model_dump())
        if func_name == "trends":
            dataset = _trend_flow_dataset(targets)
            if dataset:
                catalog.insert(
                    len(catalog),
                    ChartCatalogItem(
                        chart_id="trends:trend-flow",
                        function_name="trends",
                        target="__trend_flow__",
                        title="趋势与阶段演化 · 渠道声量堆叠",
                        subtitle="按日期对齐各渠道趋势，查看声量在时间轴上的流动与累积变化。",
                        option=_stacked_area_option(dataset),
                        rows=dataset.get("summary_rows")[:12],
                        all_rows=dataset.get("summary_rows"),
                        has_data=True,
                        empty_message="暂无可视化数据",
                    ).model_dump(),
                )
                catalog.insert(
                    len(catalog),
                    ChartCatalogItem(
                        chart_id="trends:trend-share",
                        function_name="trends",
                        target="__trend_share__",
                        title="趋势与阶段演化 · 渠道占比堆叠",
                        subtitle="100% 堆叠占比图，查看各渠道在不同日期的相对份额变化。",
                        option=_stacked_share_option(dataset),
                        rows=dataset.get("summary_rows")[:12],
                        all_rows=dataset.get("summary_rows"),
                        has_data=True,
                        empty_message="暂无可视化数据",
                    ).model_dump(),
                )
    return catalog


def _citation_ids(bundle: ReportDataBundle, item_ids: Iterable[str], *, kind: str) -> List[str]:
    source_map = {
        "evidence": {item.evidence_id: item for item in bundle.key_evidence},
        "timeline": {item.event_id: item for item in bundle.timeline},
        "subjects": {item.subject_id: item for item in bundle.subjects},
        "risks": {item.risk_id: item for item in bundle.risk_judgement},
        "actions": {item.action_id: item for item in bundle.suggested_actions},
    }.get(kind, {})
    ids: List[str] = []
    for item_id in item_ids:
        target = source_map.get(item_id)
        if not target:
            continue
        for citation_id in getattr(target, "citation_ids", []) or []:
            if citation_id and citation_id not in ids:
                ids.append(citation_id)
    return ids


def _section_chart_ids(chart_catalog: List[dict], function_name: str) -> List[str]:
    return [
        str(item.get("chart_id") or "").strip()
        for item in chart_catalog
        if str(item.get("function_name") or "").strip() == function_name and str(item.get("chart_id") or "").strip()
    ]


def build_hero(bundle: ReportDataBundle, overview: Dict[str, Any]) -> ReportHero:
    """Deterministically build the ReportHero from structured data and overview stats."""
    total_volume = int(overview.get("total_volume") or 0)
    return ReportHero(
        title=str(bundle.task.topic_label or bundle.task.topic_identifier).strip() or "结构化报告",
        subtitle=f"{bundle.task.start} → {bundle.task.end}",
        summary=str(bundle.conclusion.executive_summary or "").strip(),
        highlights=[str(item).strip() for item in bundle.conclusion.key_findings[:4] if str(item or "").strip()],
        risks=[str(item).strip() for item in bundle.conclusion.key_risks[:4] if str(item or "").strip()],
        metrics=[
            {"metric_id": "volume", "label": "总声量", "value": f"{total_volume}" if total_volume else "--", "detail": "基础分析统计"},
            {"metric_id": "evidence", "label": "证据数", "value": str(len(bundle.key_evidence)), "detail": "结构化证据条目"},
            {"metric_id": "subjects", "label": "主体数", "value": str(len(bundle.subjects)), "detail": "涉及主体与发声角色"},
            {"metric_id": "risks", "label": "风险数", "value": str(len(bundle.risk_judgement)), "detail": "当前需重点关注的风险"},
        ],
    )


def build_chart_summary_for_composer(chart_catalog: List[dict]) -> List[dict]:
    """Return a compact chart catalog summary suitable for inclusion in an AI prompt.

    Keeps only the fields the composer agent needs: chart_id, function_name, title,
    subtitle, has_data, and the first 5 rows (name + value only).
    """
    result = []
    for item in chart_catalog:
        if not isinstance(item, dict):
            continue
        rows_preview = []
        for row in (item.get("rows") or [])[:5]:
            if not isinstance(row, dict):
                continue
            rows_preview.append({
                "name": str(row.get("name") or row.get("label") or row.get("key") or "").strip(),
                "value": row.get("displayValue") if row.get("displayValue") is not None else row.get("value"),
            })
        result.append({
            "chart_id": str(item.get("chart_id") or "").strip(),
            "function_name": str(item.get("function_name") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "subtitle": str(item.get("subtitle") or "").strip(),
            "has_data": bool(item.get("has_data") or item.get("hasData")),
            "sample_rows": rows_preview,
        })
    return result


def build_data_summary_for_composer(bundle: ReportDataBundle) -> dict:
    """Return a compact structured-data summary for the AI document composer prompt."""
    return {
        "topic": str(bundle.task.topic_label or bundle.task.topic_identifier).strip(),
        "start": bundle.task.start,
        "end": bundle.task.end,
        "executive_summary": str(bundle.conclusion.executive_summary or "").strip(),
        "key_findings": [str(item).strip() for item in bundle.conclusion.key_findings[:8] if str(item or "").strip()],
        "key_risks": [str(item).strip() for item in bundle.conclusion.key_risks[:6] if str(item or "").strip()],
        "evidence_ids": [item.evidence_id for item in bundle.key_evidence[:16]],
        "event_ids": [item.event_id for item in bundle.timeline[:16]],
        "subject_ids": [item.subject_id for item in bundle.subjects[:12]],
        "subject_names": [item.subject for item in bundle.stance_matrix[:12]],
        "risk_ids": [item.risk_id for item in bundle.risk_judgement],
        "action_ids": [item.action_id for item in bundle.suggested_actions],
        "citation_ids": [item.citation_id for item in bundle.citations[:30]],
    }


def assemble_report_document(
    composer_output: DocumentComposerOutput,
    bundle: ReportDataBundle,
    chart_catalog: List[dict],
    overview: Dict[str, Any],
) -> dict:
    """Merge AI composer output with deterministic hero + appendix, then sanitize chart refs.

    If the AI produced an appendix use it; otherwise generate a default one with citations.
    """
    hero = build_hero(bundle, overview)
    appendix = composer_output.appendix
    if appendix is None:
        appendix = ReportAppendix(
            title="引用与校验",
            blocks=[
                {
                    "type": "citation_refs",
                    "block_id": "appendix-citations",
                    "title": "引用索引",
                    "citation_ids": [item.citation_id for item in bundle.citations],
                },
                {
                    "type": "callout",
                    "block_id": "appendix-validation",
                    "title": "校验记录",
                    "tone": "warning" if bundle.validation_notes else "info",
                    "content": "；".join([str(item.message).strip() for item in bundle.validation_notes[:6] if str(item.message or "").strip()])
                    or "当前结果没有独立的校验记录。",
                },
            ],
        )
    document = ReportDocument(
        hero=hero,
        sections=composer_output.sections,
        appendix=appendix,
        chart_catalog_version=1,
    )
    return sanitize_report_document(document.model_dump(), chart_catalog)


def build_report_document(bundle: ReportDataBundle, chart_catalog: List[dict], overview: Dict[str, Any]) -> dict:
    """Deterministic fallback: build a fixed 4-section document from structured data.

    This is used when the AI document composer is unavailable or fails.
    """
    total_volume = int(overview.get("total_volume") or 0)
    hero = ReportHero(
        title=str(bundle.task.topic_label or bundle.task.topic_identifier).strip() or "结构化报告",
        subtitle=f"{bundle.task.start} → {bundle.task.end}",
        summary=str(bundle.conclusion.executive_summary or "").strip(),
        highlights=[str(item).strip() for item in bundle.conclusion.key_findings[:4] if str(item or "").strip()],
        risks=[str(item).strip() for item in bundle.conclusion.key_risks[:4] if str(item or "").strip()],
        metrics=[
            {"metric_id": "volume", "label": "总声量", "value": f"{total_volume}" if total_volume else "--", "detail": "基础分析统计"},
            {"metric_id": "evidence", "label": "证据数", "value": str(len(bundle.key_evidence)), "detail": "结构化证据条目"},
            {"metric_id": "subjects", "label": "主体数", "value": str(len(bundle.subjects)), "detail": "涉及主体与发声角色"},
            {"metric_id": "risks", "label": "风险数", "value": str(len(bundle.risk_judgement)), "detail": "当前需重点关注的风险"},
        ],
    )
    sections: List[ReportSection] = [
        ReportSection(
            section_id="core-dimensions",
            kicker="舆情分析核心维度",
            title="量、质、人、场、效综合判断",
            summary=str(bundle.conclusion.executive_summary or "").strip(),
            blocks=[
                {
                    "type": "narrative",
                    "block_id": "core-summary",
                    "title": "章节判断",
                    "content": str(bundle.conclusion.executive_summary or "").strip() or "当前结果尚未形成完整摘要。",
                    "citation_ids": _citation_ids(bundle, [item.evidence_id for item in bundle.key_evidence[:4]], kind="evidence"),
                },
                {
                    "type": "bullets",
                    "block_id": "core-highlights",
                    "title": "核心要点",
                    "items": [str(item).strip() for item in bundle.conclusion.key_findings[:6] if str(item or "").strip()],
                },
                {
                    "type": "chart_slot",
                    "block_id": "core-volume-charts",
                    "title": "声量与渠道概览",
                    "description": ANALYSIS_META["volume"]["description"],
                    "chart_ids": _section_chart_ids(chart_catalog, "volume"),
                },
                {
                    "type": "chart_slot",
                    "block_id": "core-attitude-charts",
                    "title": "情绪与舆论质量",
                    "description": ANALYSIS_META["attitude"]["description"],
                    "chart_ids": _section_chart_ids(chart_catalog, "attitude"),
                },
                {
                    "type": "chart_slot",
                    "block_id": "core-classification-charts",
                    "title": "议题与话题聚类",
                    "description": ANALYSIS_META["classification"]["description"],
                    "chart_ids": _section_chart_ids(chart_catalog, "classification"),
                },
                {
                    "type": "chart_slot",
                    "block_id": "core-keywords-charts",
                    "title": "高频表达与关注焦点",
                    "description": ANALYSIS_META["keywords"]["description"],
                    "chart_ids": _section_chart_ids(chart_catalog, "keywords"),
                },
                {
                    "type": "evidence_list",
                    "block_id": "core-evidence",
                    "title": "关键证据",
                    "evidence_ids": [item.evidence_id for item in bundle.key_evidence[:8]],
                },
            ],
        ),
        ReportSection(
            section_id="lifecycle",
            kicker="舆情生命周期阶段",
            title="阶段演化与关键节点",
            summary=str(bundle.timeline[0].description if bundle.timeline else "").strip(),
            blocks=[
                {
                    "type": "narrative",
                    "block_id": "lifecycle-summary",
                    "title": "阶段判断",
                    "content": str(bundle.timeline[0].description if bundle.timeline else bundle.conclusion.executive_summary or "").strip()
                    or "当前结果尚未抽出独立阶段摘要。",
                    "citation_ids": _citation_ids(bundle, [item.event_id for item in bundle.timeline[:4]], kind="timeline"),
                },
                {
                    "type": "chart_slot",
                    "block_id": "lifecycle-trends",
                    "title": "趋势与阶段演化",
                    "description": ANALYSIS_META["trends"]["description"],
                    "chart_ids": _section_chart_ids(chart_catalog, "trends"),
                },
                {
                    "type": "timeline_list",
                    "block_id": "lifecycle-events",
                    "title": "关键节点",
                    "event_ids": [item.event_id for item in bundle.timeline],
                },
            ],
        ),
        ReportSection(
            section_id="subjects-and-stance",
            kicker="主体与立场",
            title="主体结构、发声角色与立场分化",
            summary=str(bundle.stance_matrix[0].summary if bundle.stance_matrix else (bundle.subjects[0].summary if bundle.subjects else "")).strip(),
            blocks=[
                {
                    "type": "narrative",
                    "block_id": "subjects-summary",
                    "title": "主体结构判断",
                    "content": str(bundle.stance_matrix[0].summary if bundle.stance_matrix else (bundle.subjects[0].summary if bundle.subjects else "")).strip()
                    or "当前结果尚未形成独立的主体结构摘要。",
                    "citation_ids": _citation_ids(bundle, [item.subject_id for item in bundle.subjects[:4]], kind="subjects"),
                },
                {
                    "type": "chart_slot",
                    "block_id": "subjects-publishers",
                    "title": "发布者与关键发声者",
                    "description": ANALYSIS_META["publishers"]["description"],
                    "chart_ids": _section_chart_ids(chart_catalog, "publishers"),
                },
                {
                    "type": "chart_slot",
                    "block_id": "subjects-geography",
                    "title": "地域与话语场分布",
                    "description": ANALYSIS_META["geography"]["description"],
                    "chart_ids": _section_chart_ids(chart_catalog, "geography"),
                },
                {
                    "type": "subject_cards",
                    "block_id": "subjects-cards",
                    "title": "主体列表",
                    "subject_ids": [item.subject_id for item in bundle.subjects[:12]],
                },
                {
                    "type": "stance_matrix",
                    "block_id": "subjects-stance",
                    "title": "立场矩阵",
                    "subject_names": [item.subject for item in bundle.stance_matrix[:12]],
                },
            ],
        ),
        ReportSection(
            section_id="propagation-and-response",
            kicker="传播、风险与建议",
            title="传播结构、风险边界与建议动作",
            summary=str(bundle.propagation_features[0].explanation if bundle.propagation_features else (bundle.risk_judgement[0].summary if bundle.risk_judgement else "")).strip(),
            blocks=[
                {
                    "type": "narrative",
                    "block_id": "propagation-summary",
                    "title": "传播与回应观察",
                    "content": str(bundle.propagation_features[0].explanation if bundle.propagation_features else (bundle.risk_judgement[0].summary if bundle.risk_judgement else "")).strip()
                    or "当前结果尚未形成独立的传播结构摘要。",
                    "citation_ids": [citation_id for item in bundle.propagation_features[:4] for citation_id in item.citation_ids][:12],
                },
                {
                    "type": "bullets",
                    "block_id": "propagation-findings",
                    "title": "传播特征",
                    "items": [str(item.finding).strip() for item in bundle.propagation_features[:6] if str(item.finding or "").strip()],
                },
                {
                    "type": "risk_list",
                    "block_id": "propagation-risks",
                    "title": "风险判断",
                    "risk_ids": [item.risk_id for item in bundle.risk_judgement],
                },
                {
                    "type": "action_list",
                    "block_id": "propagation-actions",
                    "title": "建议动作",
                    "action_ids": [item.action_id for item in bundle.suggested_actions],
                },
                {
                    "type": "callout",
                    "block_id": "propagation-unverified",
                    "title": "待核验提醒",
                    "tone": "warning" if bundle.unverified_points else "info",
                    "content": "；".join([str(item.statement).strip() for item in bundle.unverified_points[:4] if str(item.statement or "").strip()])
                    or "当前结果没有单独列出待核验点。",
                },
            ],
        ),
    ]
    appendix = ReportAppendix(
        title="引用与校验",
        blocks=[
            {
                "type": "citation_refs",
                "block_id": "appendix-citations",
                "title": "引用索引",
                "citation_ids": [item.citation_id for item in bundle.citations],
            },
            {
                "type": "callout",
                "block_id": "appendix-validation",
                "title": "校验记录",
                "tone": "warning" if bundle.validation_notes else "info",
                "content": "；".join([str(item.message).strip() for item in bundle.validation_notes[:6] if str(item.message or "").strip()])
                or "当前结果没有独立的校验记录。",
            },
        ],
    )
    document = ReportDocument(hero=hero, sections=sections, appendix=appendix, chart_catalog_version=1)
    return sanitize_report_document(document.model_dump(), chart_catalog)


def sanitize_report_document(document: Dict[str, Any], chart_catalog: List[dict]) -> dict:
    valid_chart_ids = {str(item.get("chart_id") or "").strip() for item in chart_catalog if str(item.get("chart_id") or "").strip()}
    sections = document.get("sections") if isinstance(document.get("sections"), list) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        blocks = section.get("blocks") if isinstance(section.get("blocks"), list) else []
        for index, block in enumerate(list(blocks)):
            if not isinstance(block, dict) or block.get("type") != "chart_slot":
                continue
            original_chart_ids = [str(item).strip() for item in block.get("chart_ids") or [] if str(item or "").strip()]
            present = [item for item in original_chart_ids if item in valid_chart_ids]
            missing = [item for item in original_chart_ids if item not in valid_chart_ids]
            if present:
                block["chart_ids"] = present
                if missing:
                    block["chart_ids_missing"] = missing
                continue
            blocks[index] = {
                "type": "callout",
                "block_id": str(block.get("block_id") or f"chart-missing-{index}").strip() or f"chart-missing-{index}",
                "title": str(block.get("title") or "图表暂缺").strip() or "图表暂缺",
                "tone": "warning",
                "content": "当前章节引用的图表未能在本次分析结果中解析出来，已自动降级为说明提示。",
            }
    return document
