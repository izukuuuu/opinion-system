"""
ECharts 配置构建工具：根据分析结果快速生成可视化配置。
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple


def _coerce_number(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _split_series(data: Sequence[Dict[str, Any]], name_key: str = "name", value_key: str = "value") -> Tuple[List[str], List[float]]:
    categories: List[str] = []
    values: List[float] = []
    for item in data:
        label = item.get(name_key)
        categories.append(str(label) if label is not None else "")
        values.append(_coerce_number(item.get(value_key)))
    return categories, values


def build_bar_option(
    title: str,
    data: Sequence[Dict[str, Any]],
    *,
    orientation: str = "vertical",
    category_label: str = "类别",
    value_label: str = "数量",
    sort_desc: bool = False,
) -> Dict[str, Any]:
    # 横向条形图统一按数值降序排列，便于高值居上展示
    is_vertical = orientation != "horizontal"
    ordered_data = list(data)
    if sort_desc or not is_vertical:
        ordered_data = sorted(ordered_data, key=lambda item: _coerce_number(item.get("value")), reverse=True)

    categories, values = _split_series(ordered_data)

    x_axis = {
        "type": "category",
        "data": categories,
        "axisLabel": {"interval": 0, "color": "#475569"},
        "axisLine": {"lineStyle": {"color": "#cbd5f5"}},
    }
    y_axis = {
        "type": "value",
        "axisLabel": {"color": "#475569"},
        "splitLine": {"lineStyle": {"color": "#e2e8f0"}},
    }

    if not is_vertical:
        x_axis, y_axis = y_axis, x_axis
        y_axis["inverse"] = True

    return {
        "color": ["#6366f1"],
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": 60, "right": 30, "top": 70, "bottom": 60, "containLabel": True},
        "xAxis": x_axis,
        "yAxis": y_axis,
        "series": [
            {
                "type": "bar",
                "data": values,
                "label": {"show": True, "position": "top", "color": "#0f172a"},
            }
        ],
        "dataset": {
            "dimensions": [category_label, value_label],
            "source": [{"name": c, "value": v} for c, v in zip(categories, values)],
        },
    }


def build_line_option(
    title: str,
    data: Sequence[Dict[str, Any]],
    *,
    category_label: str = "日期",
    value_label: str = "数量",
) -> Dict[str, Any]:
    categories, values = _split_series(data)
    return {
        "color": ["#0ea5e9"],
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 50, "right": 30, "top": 70, "bottom": 60, "containLabel": True},
        "xAxis": {
            "type": "category",
            "boundaryGap": False,
            "data": categories,
            "axisLabel": {"color": "#475569"},
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
                "areaStyle": {"opacity": 0.1},
                "data": values,
            }
        ],
        "dataset": {
            "dimensions": [category_label, value_label],
            "source": [{"name": c, "value": v} for c, v in zip(categories, values)],
        },
    }


def build_pie_option(title: str, data: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item"},
        "legend": {"bottom": 0, "type": "scroll"},
        "series": [
            {
                "type": "pie",
                "radius": ["40%", "68%"],
                "center": ["50%", "48%"],
                "data": data,
                "label": {"formatter": "{b}: {d}%"},
            }
        ],
    }


__all__ = ["build_bar_option", "build_line_option", "build_pie_option"]
