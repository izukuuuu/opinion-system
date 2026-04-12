from __future__ import annotations

from functools import lru_cache
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import yaml

from .schemas import (
    ChartGrammarSpec,
    DocumentComposerOutput,
    FigureApprovalRecord,
    FigureArtifactRecord,
    FigureBlock,
    FigureDatasetArtifact,
    FigureIntentDecision,
    FigureMetricSource,
    FigureOptionArtifact,
    MetricBundle,
    PlacementAnchor,
    PlacementPlan,
    ReportAppendix,
    ReportDataBundle,
    ReportDocument,
    ReportHero,
    ReportSection,
)


ANALYSIS_META = {
    "attitude": {"label": "情绪与舆论质量", "description": "用于判断正负倾向、情绪分布和舆情强度。"},
    "bertopic": {"label": "BERTopic 主题演化", "description": "查看主题簇、主题迁移与时间序列上的讨论主线变化。"},
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
SUMMARY_SECTION_IDS = {"summary", "overview", "executive-summary"}
CONFIG_ROOT = Path(__file__).resolve().parents[3] / "configs"
REPORT_BLUEPRINT_ROOT = CONFIG_ROOT / "report_blueprints"
REPORT_SECTION_ROOT = CONFIG_ROOT / "report_sections"
CHART_ALIAS_PATH = CONFIG_ROOT / "chart_aliases.yaml"


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


@lru_cache(maxsize=None)
def _load_yaml_config(path_text: str) -> Dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


@lru_cache(maxsize=None)
def _load_chart_alias_registry() -> Dict[str, List[str]]:
    payload = _load_yaml_config(str(CHART_ALIAS_PATH))
    aliases = payload.get("aliases") if isinstance(payload.get("aliases"), dict) else {}
    normalized: Dict[str, List[str]] = {}
    for alias, value in aliases.items():
        key = str(alias or "").strip()
        if not key:
            continue
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = [str(item).strip() for item in value if str(item or "").strip()]
        else:
            candidates = []
        normalized[key] = candidates
    return normalized


@lru_cache(maxsize=None)
def load_report_blueprint(document_type: str) -> Dict[str, Any]:
    doc_type = str(document_type or "analysis_report").strip() or "analysis_report"
    payload = _load_yaml_config(str(REPORT_BLUEPRINT_ROOT / f"{doc_type}.yaml"))
    if payload:
        return payload
    return {
        "document_type": doc_type,
        "layout": {"sanitize_missing_figure_refs": True},
        "sections": [
            {"section_id": "core-dimensions", "source": "composer_or_factory", "factory": "core_dimensions", "required": True},
            {"section_id": "lifecycle", "source": "composer_or_factory", "factory": "lifecycle", "required": True},
            {"section_id": "subjects-and-stance", "source": "composer_or_factory", "factory": "subjects_and_stance", "required": True},
            {"section_id": "propagation-and-response", "source": "composer_or_factory", "factory": "propagation_and_response", "required": True},
        ],
        "appendix": {"source": "default_or_composer"},
    }


@lru_cache(maxsize=None)
def _load_section_template(factory_name: str) -> Dict[str, Any]:
    key = str(factory_name or "").strip()
    if not key:
        return {}
    return _load_yaml_config(str(REPORT_SECTION_ROOT / f"{key}.yaml"))


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


def _chart_target_alias(target: str) -> str:
    compact = _compact_key(target)
    if compact in {"overall", "summary", "total", "总体"}:
        return "overall"
    return _slug(target)


def _chart_aliases_for_item(func_name: str, target: str, chart_id: str) -> List[str]:
    aliases = [f"{func_name}.{_chart_target_alias(target)}"]
    if chart_id == "trends:trend-flow":
        aliases.append("trends.trend-flow")
    if chart_id == "trends:trend-share":
        aliases.append("trends.trend-share")
    if chart_id == "bertopic:summary":
        aliases.append("bertopic.summary")
    if chart_id == "bertopic:clusters":
        aliases.append("bertopic.clusters")
    if chart_id == "bertopic:temporal":
        aliases.append("bertopic.temporal")
    aliases.append(chart_id.replace(":", ".", 1))
    return [item for item in dict.fromkeys(str(alias).strip() for alias in aliases if str(alias or "").strip())]


def _bertopic_bar_option(rows: List[dict], *, title: str) -> dict:
    ordered = sorted(rows, key=lambda item: float(item.get("value") or item.get("count") or 0), reverse=True)
    normalized = [{"name": str(item.get("name") or item.get("label") or "").strip(), "value": float(item.get("value") or item.get("count") or 0)} for item in ordered]
    return _bar_option(title, normalized, horizontal=True)


def _bertopic_line_option(rows: List[dict], *, title: str) -> dict:
    normalized = [{"name": str(item.get("label") or item.get("name") or "").strip(), "value": float(item.get("value") or item.get("count") or 0)} for item in rows]
    return _line_option(title, normalized)


def _legacy_chart_item(
    *,
    chart_id: str,
    function_name: str,
    target: str,
    title: str,
    subtitle: str,
    option: dict,
    rows: List[dict],
    all_rows: List[dict],
    has_data: bool,
    empty_message: str,
    chart_aliases: List[str] | None = None,
) -> dict:
    return {
        "chart_id": str(chart_id or "").strip(),
        "chart_aliases": [str(item).strip() for item in (chart_aliases or []) if str(item or "").strip()],
        "function_name": str(function_name or "").strip(),
        "target": str(target or "").strip(),
        "title": str(title or "").strip(),
        "subtitle": str(subtitle or "").strip(),
        "option": option if isinstance(option, dict) else {},
        "rows": list(rows or []),
        "all_rows": list(all_rows or []),
        "has_data": bool(has_data),
        "empty_message": str(empty_message or "暂无可视化数据").strip() or "暂无可视化数据",
    }


def _build_bertopic_chart_catalog(snapshot: Dict[str, Any]) -> List[dict]:
    if not isinstance(snapshot, dict):
        return []
    catalog: List[dict] = []
    raw_topics = [item for item in (snapshot.get("raw_topics") or []) if isinstance(item, dict)]
    llm_clusters = [item for item in (snapshot.get("llm_clusters") or []) if isinstance(item, dict)]
    temporal_points = [item for item in (snapshot.get("temporal_points") or []) if isinstance(item, dict)]
    if raw_topics:
        catalog.append(
            _legacy_chart_item(
                chart_id="bertopic:summary",
                function_name="bertopic",
                target="summary",
                title="BERTopic 原始主题统计",
                subtitle="按原始主题的文档量查看主题分布。",
                option=_bertopic_bar_option(raw_topics[:12], title="BERTopic 原始主题统计"),
                rows=[{"name": str(item.get("name") or "").strip(), "value": int(item.get("count") or 0)} for item in raw_topics[:12]],
                all_rows=[{"name": str(item.get("name") or "").strip(), "value": int(item.get("count") or 0)} for item in raw_topics],
                has_data=True,
                empty_message="暂无 BERTopic 原始主题统计",
                chart_aliases=_chart_aliases_for_item("bertopic", "summary", "bertopic:summary"),
            )
        )
    if llm_clusters:
        catalog.append(
            _legacy_chart_item(
                chart_id="bertopic:clusters",
                function_name="bertopic",
                target="clusters",
                title="BERTopic 高层主题簇",
                subtitle="按再聚类后的主题簇文档量查看当前主要讨论主线。",
                option=_bertopic_bar_option(llm_clusters[:12], title="BERTopic 高层主题簇"),
                rows=[{"name": str(item.get("name") or "").strip(), "value": int(item.get("count") or 0)} for item in llm_clusters[:12]],
                all_rows=[{"name": str(item.get("name") or "").strip(), "value": int(item.get("count") or 0)} for item in llm_clusters],
                has_data=True,
                empty_message="暂无 BERTopic 高层主题簇数据",
                chart_aliases=_chart_aliases_for_item("bertopic", "clusters", "bertopic:clusters"),
            )
        )
    if temporal_points:
        catalog.append(
            _legacy_chart_item(
                chart_id="bertopic:temporal",
                function_name="bertopic",
                target="temporal",
                title="BERTopic 主题时间趋势",
                subtitle="按时间节点查看主题热度的迁移与切换。",
                option=_bertopic_line_option(temporal_points, title="BERTopic 主题时间趋势"),
                rows=[{"name": str(item.get("label") or "").strip(), "value": int(item.get("value") or 0)} for item in temporal_points[:12]],
                all_rows=[{"name": str(item.get("label") or "").strip(), "value": int(item.get("value") or 0)} for item in temporal_points],
                has_data=True,
                empty_message="暂无 BERTopic 时间趋势数据",
                chart_aliases=_chart_aliases_for_item("bertopic", "temporal", "bertopic:temporal"),
            )
        )
    return catalog


def build_chart_catalog(functions_payload: List[dict], bertopic_snapshot: Dict[str, Any] | None = None) -> List[dict]:
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
            catalog.append(
                _legacy_chart_item(
                    chart_id=f"{func_name}:{_slug(target_label)}",
                    chart_aliases=_chart_aliases_for_item(func_name, target_label, f"{func_name}:{_slug(target_label)}"),
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
            )
        if func_name == "trends":
            dataset = _trend_flow_dataset(targets)
            if dataset:
                catalog.insert(
                    len(catalog),
                    _legacy_chart_item(
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
                        chart_aliases=_chart_aliases_for_item("trends", "__trend_flow__", "trends:trend-flow"),
                    ),
                )
                catalog.insert(
                    len(catalog),
                    _legacy_chart_item(
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
                        chart_aliases=_chart_aliases_for_item("trends", "__trend_share__", "trends:trend-share"),
                    ),
                )
    catalog.extend(_build_bertopic_chart_catalog(bertopic_snapshot or {}))
    return catalog


FIGURE_POLICY_VERSION = "figure-policy.v1"
REVIEW_REQUIRED_INTENTS = {"network", "geo"}
DOC_SECTION_BY_ROLE = {
    "claims": "core-dimensions",
    "timeline": "lifecycle",
    "actors": "subjects-and-stance",
    "agenda": "bertopic-evolution",
    "mechanism": "propagation-and-response",
    "risks": "propagation-and-response",
    "recommendations": "propagation-and-response",
}
DOC_BLOCK_BY_ROLE = {
    "claims": "core-summary",
    "timeline": "lifecycle-summary",
    "actors": "subjects-summary",
    "agenda": "bertopic-summary",
    "mechanism": "propagation-summary",
    "risks": "propagation-risks",
    "recommendations": "propagation-actions",
}


def _metric_family_for_function(function_name: str) -> str:
    if function_name in {"trends", "bertopic_timeline", "timeline"}:
        return "temporal"
    if function_name in {"volume", "publishers", "geography"}:
        return "platform"
    return "overview"


def _sum_rows(rows: List[dict]) -> float:
    return round(sum(float(item.get("value") or 0) for item in rows if isinstance(item, dict)), 4)


def _figure_id_for_chart(chart_id: str) -> str:
    return f"fig:{str(chart_id or '').strip()}"


def _source_claim_ids(bundle: ReportDataBundle, *, limit: int = 6) -> List[str]:
    claim_ids = [f"claim:{item.evidence_id}" for item in bundle.key_evidence[:limit] if str(item.evidence_id or "").strip()]
    claim_ids.extend(
        f"claim:{item.item_id}"
        for item in bundle.unverified_points[:limit]
        if str(item.item_id or "").strip()
    )
    return list(dict.fromkeys(claim_ids))


def _distribution_source(bundle: ReportDataBundle) -> FigureMetricSource | None:
    buckets: Dict[str, int] = defaultdict(int)
    for item in bundle.key_evidence:
        buckets[str(item.confidence or "medium").strip() or "medium"] += 1
    rows = [{"name": name, "value": count} for name, count in buckets.items() if count]
    if not rows:
        return None
    return FigureMetricSource(
        metric_id="metric:distribution:evidence-confidence",
        function_name="distribution",
        target="evidence-confidence",
        label="证据置信度分布",
        metric_family="overview",
        rows=rows[:12],
        all_rows=rows,
        meta={"subtitle": "用于观察当前证据强度是否过度集中。"},
    )


def _timeline_source(bundle: ReportDataBundle) -> FigureMetricSource | None:
    rows = [
        {
            "name": str(item.date or "").strip(),
            "value": index + 1,
            "label": str(item.title or "").strip(),
            "description": str(item.description or "").strip(),
        }
        for index, item in enumerate(bundle.timeline)
        if str(item.event_id or "").strip()
    ]
    if not rows:
        return None
    return FigureMetricSource(
        metric_id="metric:timeline:events",
        function_name="timeline",
        target="events",
        label="事件时间带",
        metric_family="temporal",
        rows=rows[:12],
        all_rows=rows,
        meta={"subtitle": "用时间带显示关键节点和阶段顺序。"},
    )


def _network_source(bundle: ReportDataBundle) -> FigureMetricSource | None:
    edges: List[dict] = []
    mechanism = bundle.mechanism_summary
    if mechanism:
        for item in mechanism.cross_platform_bridges[:12]:
            edges.append(
                {
                    "source": str(item.from_platform or "").strip(),
                    "target": str(item.to_platform or "").strip(),
                    "value": float(item.confidence or 0),
                }
            )
        for item in mechanism.amplification_paths[:12]:
            sequence = [str(value).strip() for value in (item.platform_sequence or []) if str(value or "").strip()]
            for index in range(len(sequence) - 1):
                edges.append({"source": sequence[index], "target": sequence[index + 1], "value": float(item.confidence or 0)})
    edges = [item for item in edges if str(item.get("source") or "").strip() and str(item.get("target") or "").strip()]
    if not edges:
        return None
    return FigureMetricSource(
        metric_id="metric:network:propagation",
        function_name="network",
        target="propagation",
        label="传播桥接网络",
        metric_family="overview",
        rows=edges[:20],
        all_rows=edges,
        meta={"subtitle": "显示跨平台桥接和放大路径。"},
    )


def build_metric_bundle(
    functions_payload: List[dict],
    *,
    bundle: ReportDataBundle | None = None,
    bertopic_snapshot: Dict[str, Any] | None = None,
) -> MetricBundle:
    legacy_catalog = build_chart_catalog(functions_payload, bertopic_snapshot=bertopic_snapshot)
    metrics: List[dict] = []
    sources: List[FigureMetricSource] = []
    for item in legacy_catalog:
        rows = [dict(row) for row in (item.get("rows") or []) if isinstance(row, dict)]
        all_rows = [dict(row) for row in (item.get("all_rows") or item.get("rows") or []) if isinstance(row, dict)]
        metric_id = f"metric:{str(item.get('chart_id') or '').strip()}"
        metrics.append(
            {
                "metric_id": metric_id,
                "label": str(item.get("title") or "").strip(),
                "value": _sum_rows(all_rows),
                "dimension": str(item.get("target") or "").strip(),
                "detail": str(item.get("subtitle") or "").strip(),
                "metric_family": _metric_family_for_function(str(item.get("function_name") or "").strip()),
            }
        )
        sources.append(
            FigureMetricSource(
                metric_id=metric_id,
                function_name=str(item.get("function_name") or "").strip(),
                target=str(item.get("target") or "").strip(),
                label=str(item.get("title") or "").strip(),
                metric_family=_metric_family_for_function(str(item.get("function_name") or "").strip()),
                rows=rows,
                all_rows=all_rows,
                meta={
                    "chart_id": str(item.get("chart_id") or "").strip(),
                    "subtitle": str(item.get("subtitle") or "").strip(),
                    "chart_aliases": list(item.get("chart_aliases") or []),
                    "legacy_option": item.get("option") if isinstance(item.get("option"), dict) else {},
                },
            )
        )
    if bundle is not None:
        for extra in [_distribution_source(bundle), _timeline_source(bundle), _network_source(bundle)]:
            if extra is not None:
                sources.append(extra)
                metrics.append(
                    {
                        "metric_id": extra.metric_id,
                        "label": extra.label,
                        "value": _sum_rows(extra.all_rows),
                        "dimension": extra.target,
                        "detail": str((extra.meta or {}).get("subtitle") or "").strip(),
                        "metric_family": extra.metric_family,
                    }
                )
    return MetricBundle.model_validate({"policy_version": FIGURE_POLICY_VERSION, "metrics": metrics, "sources": [item.model_dump() for item in sources]})


def _intent_and_chart_type(source: FigureMetricSource) -> Tuple[str, str]:
    function_name = str(source.function_name or "").strip()
    target = str(source.target or "").strip()
    if function_name == "attitude":
        return "composition", "donut"
    if function_name == "trends" and target == "__trend_flow__":
        return "trend", "stacked-area"
    if function_name == "trends" and target == "__trend_share__":
        return "composition", "100%-stacked-area"
    if function_name in {"trends", "bertopic"} and "temporal" in target:
        return "trend", "line"
    if function_name == "timeline":
        return "timeline", "event-band"
    if function_name == "network":
        return "network", "graph"
    if function_name == "distribution":
        return "distribution", "histogram"
    if function_name == "geography":
        return "geo", "region-choropleth"
    if function_name in {"classification", "keywords", "publishers"}:
        return "ranking", "sorted-bar"
    if function_name == "volume":
        return "comparison", "grouped-bar"
    return "comparison", "grouped-bar"


def _section_role_for_source(source: FigureMetricSource) -> str:
    function_name = str(source.function_name or "").strip()
    if function_name in {"trends", "timeline"}:
        return "timeline"
    if function_name == "bertopic":
        return "agenda"
    if function_name in {"publishers", "geography"}:
        return "actors"
    if function_name == "network":
        return "mechanism"
    if function_name == "distribution":
        return "risks"
    return "claims"


def plan_figure_intents(metric_bundle: MetricBundle, *, bundle: ReportDataBundle | None = None) -> List[FigureIntentDecision]:
    source_claim_ids = _source_claim_ids(bundle) if bundle is not None else []
    decisions: List[FigureIntentDecision] = []
    for source in metric_bundle.sources:
        if not source.all_rows:
            continue
        intent, chart_type = _intent_and_chart_type(source)
        figure_id = _figure_id_for_chart(str((source.meta or {}).get("chart_id") or source.metric_id))
        requires_review = intent in REVIEW_REQUIRED_INTENTS or (intent == "trend" and str(source.target or "").strip() in {"总体", "__trend_flow__", "__trend_share__"})
        decisions.append(
            FigureIntentDecision(
                figure_id=figure_id,
                section_role=_section_role_for_source(source),
                metric_id=source.metric_id,
                function_name=source.function_name,
                target=source.target,
                intent=intent,
                chart_type=chart_type,
                caption=str(source.label or source.metric_id).strip(),
                requires_review=requires_review,
                review_reasons=["high_risk_visualization"] if requires_review else [],
                source_claim_ids=source_claim_ids[:6],
                source_metric_ids=[source.metric_id],
            )
        )
    return decisions


def _histogram_option(title: str, rows: List[dict]) -> dict:
    ordered = _sort_rows(rows)
    return {
        "animation": False,
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 40, "right": 24, "top": 24, "bottom": 40, "containLabel": True},
        "xAxis": {"type": "category", "data": [_row_name(item) for item in ordered], "axisLabel": {"color": "#475569"}},
        "yAxis": {"type": "value", "axisLabel": {"color": "#475569"}, "splitLine": {"lineStyle": {"color": "#e2e8f0"}}},
        "series": [{"type": "bar", "data": [float(item.get("value") or 0) for item in ordered], "barMaxWidth": 32, "itemStyle": {"borderRadius": [8, 8, 0, 0]}}],
    }


def _network_option(rows: List[dict]) -> dict:
    nodes = []
    node_ids: set[str] = set()
    links = []
    for item in rows:
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        value = float(item.get("value") or 0)
        if not source or not target:
            continue
        for name in [source, target]:
            if name not in node_ids:
                node_ids.add(name)
                nodes.append({"name": name, "value": 1})
        links.append({"source": source, "target": target, "value": value})
    return {
        "animation": False,
        "tooltip": {},
        "series": [
            {
                "type": "graph",
                "layout": "force",
                "roam": True,
                "label": {"show": True},
                "data": nodes,
                "links": links,
                "force": {"repulsion": 180, "edgeLength": 120},
            }
        ],
    }


def _timeline_option(rows: List[dict]) -> dict:
    ordered = list(rows)
    return {
        "animation": False,
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 40, "right": 24, "top": 24, "bottom": 40, "containLabel": True},
        "xAxis": {"type": "category", "data": [_row_name(item) for item in ordered], "axisLabel": {"color": "#475569"}},
        "yAxis": {"type": "value", "show": False},
        "series": [
            {
                "type": "line",
                "smooth": False,
                "symbol": "diamond",
                "symbolSize": 10,
                "data": [float(item.get("value") or 0) for item in ordered],
                "lineStyle": {"width": 2},
                "label": {"show": False},
            }
        ],
    }


def _geo_option(rows: List[dict]) -> Tuple[str, str, dict]:
    return "ranking", "sorted-bar", _bar_option("地域排序", rows, horizontal=True)


def _digest_rows(rows: List[dict]) -> str:
    if not rows:
        return "rows:0"
    return f"rows:{len(rows)}:sum:{_sum_rows(rows)}"


def _compile_option_from_source(decision: FigureIntentDecision, source: FigureMetricSource) -> Tuple[str, str, dict]:
    rows = [dict(item) for item in (source.all_rows or source.rows or []) if isinstance(item, dict)]
    if decision.intent == "composition":
        if decision.chart_type == "100%-stacked-area":
            return decision.intent, decision.chart_type, source.meta.get("legacy_option") if isinstance(source.meta.get("legacy_option"), dict) else _stacked_share_option({"dates": [], "series_names": [], "matrix": {}})
        return decision.intent, decision.chart_type, _pie_option(source.label, rows)
    if decision.intent == "trend":
        if decision.chart_type == "stacked-area":
            return decision.intent, decision.chart_type, source.meta.get("legacy_option") if isinstance(source.meta.get("legacy_option"), dict) else _line_option(source.label, rows)
        return decision.intent, decision.chart_type, _line_option(source.label, rows)
    if decision.intent == "ranking":
        return decision.intent, decision.chart_type, _bar_option(source.label, rows, horizontal=True)
    if decision.intent == "comparison":
        return decision.intent, decision.chart_type, _bar_option(source.label, rows, horizontal=False)
    if decision.intent == "distribution":
        return decision.intent, decision.chart_type, _histogram_option(source.label, rows)
    if decision.intent == "network":
        return decision.intent, decision.chart_type, _network_option(rows)
    if decision.intent == "timeline":
        return decision.intent, decision.chart_type, _timeline_option(rows)
    if decision.intent == "geo":
        return _geo_option(rows)
    return decision.intent, decision.chart_type, source.meta.get("legacy_option") if isinstance(source.meta.get("legacy_option"), dict) else {}


def compile_figure_specs(metric_bundle: MetricBundle, decisions: List[FigureIntentDecision]) -> Tuple[List[FigureBlock], List[FigureArtifactRecord]]:
    source_map = {source.metric_id: source for source in metric_bundle.sources}
    figure_blocks: List[FigureBlock] = []
    artifacts: List[FigureArtifactRecord] = []
    for decision in decisions:
        source = source_map.get(decision.metric_id)
        if source is None:
            continue
        resolved_intent, resolved_chart_type, option = _compile_option_from_source(decision, source)
        dataset_ref = f"{decision.figure_id}:dataset"
        option_ref = f"{decision.figure_id}:option"
        render_status = "review_required" if decision.requires_review else "ready"
        dataset = FigureDatasetArtifact(
            dataset_ref=dataset_ref,
            dimensions=list((source.all_rows or source.rows or [{}])[0].keys()) if (source.all_rows or source.rows) else [],
            rows=[dict(item) for item in (source.all_rows or source.rows or []) if isinstance(item, dict)],
            preview_rows=[dict(item) for item in (source.rows or []) if isinstance(item, dict)],
            digest=_digest_rows(source.all_rows or source.rows or []),
        )
        chart_spec = ChartGrammarSpec(
            chart_type=resolved_chart_type,
            dataset_ref=dataset_ref,
            option_ref=option_ref,
            encode={"x": "name", "y": "value"},
            axes={"x": "category", "y": "value"},
            series=[{"type": resolved_chart_type}],
            components={"legend": True, "tooltip": True, "grid": True},
            degraded_from=decision.chart_type if resolved_intent != decision.intent else "",
            blocked_reason="missing_map_asset" if decision.intent == "geo" and resolved_intent != "geo" else "",
        )
        option_artifact = FigureOptionArtifact(option_ref=option_ref, option=option if isinstance(option, dict) else {})
        approval_records = [
            FigureApprovalRecord(
                figure_id=decision.figure_id,
                required=decision.requires_review,
                status="pending" if decision.requires_review else "not_required",
                reason="；".join(decision.review_reasons) if decision.review_reasons else "",
            )
        ]
        figure_blocks.append(
            FigureBlock(
                figure_id=decision.figure_id,
                intent=resolved_intent,
                chart_type=resolved_chart_type,
                dataset_ref=dataset_ref,
                option_ref=option_ref,
                caption=decision.caption,
                placement_anchor=f"inside:section:{decision.section_role}",
                source_claim_ids=decision.source_claim_ids,
                source_metric_ids=decision.source_metric_ids,
                policy_version=FIGURE_POLICY_VERSION,
                render_status=render_status,
            )
        )
        artifacts.append(
            FigureArtifactRecord(
                figure_id=decision.figure_id,
                version=1,
                status="ready",
                dataset_ref=dataset_ref,
                option_ref=option_ref,
                caption=decision.caption,
                placement_anchor=f"inside:section:{decision.section_role}",
                source_claim_ids=decision.source_claim_ids,
                source_metric_ids=decision.source_metric_ids,
                policy_version=FIGURE_POLICY_VERSION,
                render_status=render_status,
                chart_spec=chart_spec,
                dataset=dataset,
                option=option_artifact,
                approval_records=approval_records,
            )
        )
    return figure_blocks, artifacts


def plan_figure_placements(figures: List[FigureBlock], decisions: List[FigureIntentDecision]) -> PlacementPlan:
    decision_map = {item.figure_id: item for item in decisions}
    entries: List[PlacementAnchor] = []
    for figure in figures:
        decision = decision_map.get(figure.figure_id)
        section_role = str((decision.section_role if decision else "") or "claims").strip() or "claims"
        entries.append(
            PlacementAnchor(
                figure_id=figure.figure_id,
                section_role=section_role,
                block_id=DOC_BLOCK_BY_ROLE.get(section_role, ""),
                placement_anchor=f"inside:section:{section_role}",
                position="after",
            )
        )
    return PlacementPlan(entries=entries)


def build_figure_pipeline(
    functions_payload: List[dict],
    *,
    bundle: ReportDataBundle,
    bertopic_snapshot: Dict[str, Any] | None = None,
) -> Tuple[MetricBundle, List[FigureBlock], List[FigureArtifactRecord], PlacementPlan]:
    metric_bundle = build_metric_bundle(functions_payload, bundle=bundle, bertopic_snapshot=bertopic_snapshot)
    decisions = plan_figure_intents(metric_bundle, bundle=bundle)
    figures, artifacts = compile_figure_specs(metric_bundle, decisions)
    placement_plan = plan_figure_placements(figures, decisions)
    return metric_bundle, figures, artifacts, placement_plan


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
            "chart_aliases": [str(alias).strip() for alias in (item.get("chart_aliases") or []) if str(alias or "").strip()],
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
        "basic_analysis_summary": str((bundle.basic_analysis_insight.summary if bundle.basic_analysis_insight else "") or "").strip(),
        "bertopic_summary": str((bundle.bertopic_insight.summary if bundle.bertopic_insight else "") or "").strip(),
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


def _document_type(bundle: ReportDataBundle) -> str:
    metadata = bundle.metadata if isinstance(bundle.metadata, dict) else {}
    return str(metadata.get("document_type") or "analysis_report").strip() or "analysis_report"


def _chart_alias_index(chart_catalog: List[dict]) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = defaultdict(list)
    for item in chart_catalog:
        if not isinstance(item, dict):
            continue
        chart_id = str(item.get("chart_id") or "").strip()
        if not chart_id:
            continue
        aliases = [chart_id]
        aliases.extend(str(alias).strip() for alias in (item.get("chart_aliases") or []) if str(alias or "").strip())
        for alias in aliases:
            if chart_id not in index[alias]:
                index[alias].append(chart_id)
    return dict(index)


def _resolve_chart_ids(chart_catalog: List[dict], aliases: List[str]) -> List[str]:
    index = _chart_alias_index(chart_catalog)
    registry = _load_chart_alias_registry()
    resolved: List[str] = []
    for alias in aliases:
        alias_text = str(alias or "").strip()
        if not alias_text:
            continue
        candidates = list(index.get(alias_text, []))
        if not candidates:
            for mapped_id in registry.get(alias_text, []):
                candidates.extend(index.get(mapped_id, []))
        for chart_id in candidates:
            if chart_id and chart_id not in resolved:
                resolved.append(chart_id)
    return resolved


def _section_context(bundle: ReportDataBundle) -> Dict[str, Any]:
    return {
        "basic_analysis_insight": bundle.basic_analysis_insight.model_dump() if bundle.basic_analysis_insight else {},
        "bertopic_insight": bundle.bertopic_insight.model_dump() if bundle.bertopic_insight else {},
        "basic_analysis_snapshot": bundle.basic_analysis_snapshot.model_dump() if bundle.basic_analysis_snapshot else {},
        "bertopic_snapshot": bundle.bertopic_snapshot.model_dump() if bundle.bertopic_snapshot else {},
    }


def _resolve_context_path(payload: Dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in [segment for segment in str(path or "").split(".") if segment]:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _resolve_text(payload: Dict[str, Any], path: str, *, default: str = "") -> str:
    value = _resolve_context_path(payload, path)
    text = str(value or "").strip()
    return text or str(default or "").strip()


def _resolve_text_list(payload: Dict[str, Any], path: str) -> List[str]:
    value = _resolve_context_path(payload, path)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _build_template_block(block_spec: Dict[str, Any], *, context: Dict[str, Any], chart_catalog: List[dict]) -> Dict[str, Any] | None:
    block_type = str(block_spec.get("type") or "").strip()
    block_id = str(block_spec.get("block_id") or "").strip()
    title = str(block_spec.get("title") or "").strip()
    if not block_type or not block_id:
        return None
    if block_type == "narrative":
        content = _resolve_text(context, str(block_spec.get("source_field") or "").strip(), default=str(block_spec.get("default_content") or "").strip())
        return {"type": "narrative", "block_id": block_id, "title": title, "content": content, "citation_ids": []}
    if block_type == "bullets":
        items = _resolve_text_list(context, str(block_spec.get("source_field") or "").strip())
        if not items:
            items = [str(item).strip() for item in (block_spec.get("empty_items") or []) if str(item or "").strip()]
        return {"type": "bullets", "block_id": block_id, "title": title, "items": items}
    if block_type == "chart_slot":
        return None
    if block_type == "callout":
        notes = _resolve_text_list(context, str(block_spec.get("source_field") or "").strip())
        content = str(block_spec.get("joiner") or "；").join(notes[:4]).strip() if notes else str(block_spec.get("default_content") or "").strip()
        tone = "warning" if notes and str(block_spec.get("tone_from") or "").strip() else str(block_spec.get("tone") or "info").strip() or "info"
        return {"type": "callout", "block_id": block_id, "title": title, "tone": tone, "content": content}
    return None


def _build_template_section(factory_name: str, bundle: ReportDataBundle, chart_catalog: List[dict]) -> ReportSection | None:
    template = _load_section_template(factory_name)
    if not template:
        return None
    context = _section_context(bundle)
    summary_field = str(template.get("summary_field") or "").strip()
    summary = _resolve_text(context, summary_field, default=str(template.get("default_summary") or "").strip())
    blocks = [
        block
        for block in (
            _build_template_block(block_spec, context=context, chart_catalog=chart_catalog)
            for block_spec in (template.get("blocks") or [])
            if isinstance(block_spec, dict)
        )
        if block is not None
    ]
    return ReportSection(
        section_id=str(template.get("section_id") or factory_name).strip() or factory_name,
        kicker=str(template.get("kicker") or "").strip(),
        title=str(template.get("title") or "").strip() or factory_name,
        summary=summary,
        blocks=blocks,
    )


def _build_basic_analysis_section(bundle: ReportDataBundle, chart_catalog: List[dict]) -> ReportSection:
    section = _build_template_section("basic_analysis", bundle, chart_catalog)
    return section if section is not None else ReportSection(section_id="basic-analysis-insight", kicker="平台基础能力", title="基础分析洞察", summary="", blocks=[])


def _build_bertopic_section(bundle: ReportDataBundle, chart_catalog: List[dict]) -> ReportSection:
    section = _build_template_section("bertopic", bundle, chart_catalog)
    return section if section is not None else ReportSection(section_id="bertopic-evolution", kicker="平台基础能力", title="BERTopic 主题演化", summary="", blocks=[])


def _build_core_dimensions_section(bundle: ReportDataBundle, chart_catalog: List[dict]) -> ReportSection:
    return ReportSection(
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
                "type": "evidence_list",
                "block_id": "core-evidence",
                "title": "关键证据",
                "evidence_ids": [item.evidence_id for item in bundle.key_evidence[:8]],
            },
        ],
    )


def _build_lifecycle_section(bundle: ReportDataBundle, chart_catalog: List[dict]) -> ReportSection:
    return ReportSection(
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
                "type": "timeline_list",
                "block_id": "lifecycle-events",
                "title": "关键节点",
                "event_ids": [item.event_id for item in bundle.timeline],
            },
        ],
    )


def _build_subjects_and_stance_section(bundle: ReportDataBundle, chart_catalog: List[dict]) -> ReportSection:
    return ReportSection(
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
    )


def _build_propagation_and_response_section(bundle: ReportDataBundle, chart_catalog: List[dict]) -> ReportSection:
    _ = chart_catalog
    return ReportSection(
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
    )


def project_figures_into_document(document: Dict[str, Any], figures: List[FigureBlock], placement_plan: PlacementPlan | Dict[str, Any]) -> dict:
    projected = dict(document or {})
    sections = projected.get("sections") if isinstance(projected.get("sections"), list) else []
    plan = placement_plan if isinstance(placement_plan, PlacementPlan) else PlacementPlan.model_validate(placement_plan or {})
    figure_map = {str(item.figure_id or "").strip(): item for item in figures if str(item.figure_id or "").strip()}
    entries_by_section: Dict[str, List[PlacementAnchor]] = defaultdict(list)
    for entry in plan.entries:
        section_id = DOC_SECTION_BY_ROLE.get(str(entry.section_role or "").strip(), "")
        if section_id:
            entries_by_section[section_id].append(entry)
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id") or "").strip()
        if not section_id or section_id not in entries_by_section:
            continue
        blocks = list(section.get("blocks") or [])
        insert_after_block = {str(item.block_id or "").strip(): item for item in entries_by_section[section_id] if str(item.block_id or "").strip()}
        new_blocks: List[dict] = []
        inserted: set[str] = set()
        for block in blocks:
            new_blocks.append(block)
            block_id = str((block or {}).get("block_id") or "").strip() if isinstance(block, dict) else ""
            if block_id and block_id in insert_after_block:
                entry = insert_after_block[block_id]
                figure = figure_map.get(entry.figure_id)
                if figure is not None and figure.figure_id not in inserted:
                    new_blocks.append(
                        {
                            "type": "figure_ref",
                            "block_id": f"figure-ref-{figure.figure_id}",
                            "figure_id": figure.figure_id,
                            "placement_anchor": figure.placement_anchor,
                            "render_hint": figure.chart_type,
                        }
                    )
                    inserted.add(figure.figure_id)
        for entry in entries_by_section[section_id]:
            if entry.figure_id in inserted:
                continue
            figure = figure_map.get(entry.figure_id)
            if figure is None:
                continue
            new_blocks.append(
                {
                    "type": "figure_ref",
                    "block_id": f"figure-ref-{figure.figure_id}",
                    "figure_id": figure.figure_id,
                    "placement_anchor": figure.placement_anchor,
                    "render_hint": figure.chart_type,
                }
            )
            inserted.add(figure.figure_id)
        section["blocks"] = new_blocks
    return projected


def _factory_section_builders() -> Dict[str, Any]:
    return {
        "basic_analysis": _build_basic_analysis_section,
        "bertopic": _build_bertopic_section,
        "core_dimensions": _build_core_dimensions_section,
        "lifecycle": _build_lifecycle_section,
        "subjects_and_stance": _build_subjects_and_stance_section,
        "propagation_and_response": _build_propagation_and_response_section,
    }


def _capability_ready(capability: str, bundle: ReportDataBundle, chart_catalog: List[dict]) -> bool:
    name = str(capability or "").strip()
    basic_snapshot = bundle.basic_analysis_snapshot
    bertopic_snapshot = bundle.bertopic_snapshot
    if name == "bertopic":
        return bool(bertopic_snapshot and bertopic_snapshot.available)
    if basic_snapshot and name in set(basic_snapshot.available_functions):
        return True
    return any(str(item.get("function_name") or "").strip() == name and bool(item.get("has_data")) for item in chart_catalog if isinstance(item, dict))


def _section_is_visible(spec: Dict[str, Any], bundle: ReportDataBundle, chart_catalog: List[dict]) -> bool:
    visible_if = spec.get("visible_if") if isinstance(spec.get("visible_if"), dict) else {}
    any_capability_ready = [str(item).strip() for item in (visible_if.get("any_capability_ready") or []) if str(item or "").strip()]
    if any_capability_ready and not any(_capability_ready(item, bundle, chart_catalog) for item in any_capability_ready):
        return False
    capability_ready = [str(item).strip() for item in (visible_if.get("capability_ready") or []) if str(item or "").strip()]
    if capability_ready and not all(_capability_ready(item, bundle, chart_catalog) for item in capability_ready):
        return False
    return True


def _callout_section_from_spec(spec: Dict[str, Any]) -> ReportSection:
    title = str(spec.get("title") or spec.get("section_id") or "章节说明").strip() or "章节说明"
    section_id = str(spec.get("section_id") or "section-callout").strip() or "section-callout"
    return ReportSection(
        section_id=section_id,
        kicker=str(spec.get("kicker") or "章节降级").strip(),
        title=title,
        summary=str(spec.get("fallback_summary") or f"{title}当前按配置降级为说明提示。").strip(),
        blocks=[
            {
                "type": "callout",
                "block_id": f"{section_id}-fallback",
                "title": "能力说明",
                "tone": "warning",
                "content": str(spec.get("fallback_message") or "当前章节对应能力未就绪或结果不完整，已按报告策略降级为说明提示。").strip(),
            }
        ],
    )


def _take_composer_section(spec: Dict[str, Any], composer_sections: List[ReportSection], used_indexes: set[int]) -> ReportSection | None:
    target_id = str(spec.get("section_id") or "").strip()
    for index, section in enumerate(composer_sections):
        if index in used_indexes:
            continue
        section_id = str(section.section_id or "").strip()
        if target_id == "summary" and section_id in SUMMARY_SECTION_IDS:
            used_indexes.add(index)
            return section
        if section_id == target_id:
            used_indexes.add(index)
            return section
    return None


def _build_section_from_spec(
    spec: Dict[str, Any],
    *,
    bundle: ReportDataBundle,
    chart_catalog: List[dict],
    composer_sections: List[ReportSection],
    used_indexes: set[int],
) -> ReportSection | None:
    required = bool(spec.get("required"))
    source = str(spec.get("source") or "factory").strip() or "factory"
    if not _section_is_visible(spec, bundle, chart_catalog):
        return _callout_section_from_spec(spec) if required and str(spec.get("fallback") or "").strip() == "callout" else None
    section: ReportSection | None = None
    if source in {"composer", "composer_or_factory"}:
        section = _take_composer_section(spec, composer_sections, used_indexes)
    if section is None and source in {"factory", "composer_or_factory"}:
        builder = _factory_section_builders().get(str(spec.get("factory") or "").strip())
        if callable(builder):
            section = builder(bundle, chart_catalog)
    if section is None and required and str(spec.get("fallback") or "").strip() == "callout":
        section = _callout_section_from_spec(spec)
    return section


def _assemble_sections_from_blueprint(
    *,
    bundle: ReportDataBundle,
    chart_catalog: List[dict],
    composer_sections: List[ReportSection] | None = None,
) -> List[ReportSection]:
    blueprint = load_report_blueprint(_document_type(bundle))
    specs = [item for item in (blueprint.get("sections") or []) if isinstance(item, dict)]
    composer_items = list(composer_sections or [])
    used_indexes: set[int] = set()
    sections: List[ReportSection] = []
    blueprint_ids = {str(item.get("section_id") or "").strip() for item in specs if str(item.get("section_id") or "").strip()}
    for spec in specs:
        section = _build_section_from_spec(
            spec,
            bundle=bundle,
            chart_catalog=chart_catalog,
            composer_sections=composer_items,
            used_indexes=used_indexes,
        )
        if section is not None:
            sections.append(section)
    for index, section in enumerate(composer_items):
        if index in used_indexes:
            continue
        if str(section.section_id or "").strip() in blueprint_ids:
            continue
        sections.append(section)
    return sections


def assemble_report_document(
    composer_output: DocumentComposerOutput,
    bundle: ReportDataBundle,
    figures: List[FigureBlock],
    placement_plan: PlacementPlan | Dict[str, Any],
    overview: Dict[str, Any],
) -> dict:
    """Merge AI composer output with deterministic hero + appendix, then project figure refs.

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
    sections = _assemble_sections_from_blueprint(bundle=bundle, chart_catalog=[], composer_sections=list(composer_output.sections))
    document = ReportDocument(hero=hero, sections=sections, appendix=appendix)
    projected = project_figures_into_document(document.model_dump(), figures, placement_plan)
    return sanitize_report_document(projected, figures)


def build_report_document(
    bundle: ReportDataBundle,
    figures: List[FigureBlock],
    placement_plan: PlacementPlan | Dict[str, Any],
    overview: Dict[str, Any],
) -> dict:
    """Deterministic fallback: build document sections from blueprint + factory defaults.

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
    sections = _assemble_sections_from_blueprint(bundle=bundle, chart_catalog=[])
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
    document = ReportDocument(hero=hero, sections=sections, appendix=appendix)
    projected = project_figures_into_document(document.model_dump(), figures, placement_plan)
    return sanitize_report_document(projected, figures)


def sanitize_report_document(document: Dict[str, Any], figures: List[FigureBlock] | List[dict]) -> dict:
    valid_figure_ids = {
        str((item.figure_id if isinstance(item, FigureBlock) else item.get("figure_id")) or "").strip()
        for item in figures
        if str((item.figure_id if isinstance(item, FigureBlock) else item.get("figure_id")) or "").strip()
    }
    sections = document.get("sections") if isinstance(document.get("sections"), list) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        blocks = section.get("blocks") if isinstance(section.get("blocks"), list) else []
        for index, block in enumerate(list(blocks)):
            if not isinstance(block, dict) or block.get("type") != "figure_ref":
                continue
            figure_id = str(block.get("figure_id") or "").strip()
            if figure_id in valid_figure_ids:
                continue
            blocks[index] = {
                "type": "callout",
                "block_id": str(block.get("block_id") or f"figure-missing-{index}").strip() or f"figure-missing-{index}",
                "title": "图表暂缺",
                "tone": "warning",
                "content": "当前章节引用的图表未能在本次分析结果中解析出来，已自动降级为说明提示。",
            }
    return document
