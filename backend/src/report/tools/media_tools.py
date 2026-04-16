"""
report/tools/media_tools.py
===========================
媒体覆盖分析工具集。

工具说明
--------
提供面向 report subagents 的媒体覆盖查询能力：
- media_coverage_summary_tool：读取已打标的媒体列表，汇总官方媒体与地方媒体覆盖情况。

LangGraph 规范
--------------
- 使用 @tool decorator（LangChain 标准）
- 所有参数有类型标注
- 返回纯字符串（防止 graph 节点出错）
- FileNotFoundError 等异常转为说明字符串，不向上抛出
"""
from __future__ import annotations

import json

from langchain.tools import tool


@tool
def media_coverage_summary_tool(
    topic_identifier: str,
    start_date: str,
    end_date: str = "",
) -> str:
    """
    获取指定专题在给定时间范围内的媒体覆盖情况汇总。

    返回官方媒体（official_media）和地方媒体（local_media）的数量、
    发文总篇数、Top 媒体列表及样本标题，用于支持媒体生态分析、
    官方引导力度评估、媒体集中度研判等场景。

    参数
    ----
    topic_identifier : 专题标识符（与 normalize_task 返回的 topic_identifier 保持一致）
    start_date       : 数据起始日期，格式 YYYY-MM-DD
    end_date         : 数据截止日期，格式 YYYY-MM-DD；留空则与 start_date 相同

    返回
    ----
    纯文本摘要字符串，包含媒体统计数据。若尚未完成媒体打标，返回提示说明。
    """
    try:
        from src.media_tagging import build_labeled_media_payload  # type: ignore
    except ImportError:
        return "[media_coverage_summary_tool] 媒体打标模块不可用，跳过媒体覆盖分析。"

    topic = str(topic_identifier or "").strip()
    start = str(start_date or "").strip()
    end = str(end_date or "").strip() or None

    if not topic or not start:
        return "[media_coverage_summary_tool] 缺少必要参数 topic_identifier 或 start_date，无法查询媒体覆盖。"

    try:
        payload = build_labeled_media_payload(topic, start, end_date=end)
    except FileNotFoundError:
        return (
            f"[media_coverage_summary_tool] 未找到专题「{topic}」在 {start}"
            f"{'～' + end if end else ''} 的媒体打标结果。"
            "请先在媒体打标页面完成识别与标注，再生成报告。"
        )
    except Exception as exc:  # pragma: no cover
        return f"[media_coverage_summary_tool] 读取媒体覆盖数据时出错：{exc}"

    official: list = payload.get("official_media") or []
    local: list = payload.get("local_media") or []
    network: list = payload.get("network_media") or []
    comprehensive: list = payload.get("comprehensive_media") or []

    official_count = len(official)
    local_count = len(local)
    network_count = len(network)
    comprehensive_count = len(comprehensive)
    official_articles = sum(int(x.get("publish_count") or 0) for x in official)
    local_articles = sum(int(x.get("publish_count") or 0) for x in local)
    network_articles = sum(int(x.get("publish_count") or 0) for x in network)
    comprehensive_articles = sum(int(x.get("publish_count") or 0) for x in comprehensive)
    total_articles = official_articles + local_articles + network_articles + comprehensive_articles

    if official_count == 0 and local_count == 0 and network_count == 0 and comprehensive_count == 0:
        return (
            f"[media_coverage_summary_tool] 专题「{topic}」在 {start}"
            f"{'～' + end if end else ''} 暂无已打标媒体记录。"
            "建议在媒体打标页面完成识别与标注后再使用此工具。"
        )

    lines = [
        f"=== 媒体覆盖概况（{topic} · {start}{('～' + end) if end else ''}）===",
        "",
        f"官方媒体：{official_count} 家，发文合计 {official_articles} 篇",
        f"地方媒体：{local_count} 家，发文合计 {local_articles} 篇",
        f"网络媒体：{network_count} 家，发文合计 {network_articles} 篇",
        f"综合媒体：{comprehensive_count} 家，发文合计 {comprehensive_articles} 篇",
        f"有标注媒体总计：{official_count + local_count + network_count + comprehensive_count} 家，发文合计 {total_articles} 篇",
    ]

    if official_count > 0:
        lines.append("")
        lines.append("【官方媒体 Top 10（按发文量降序）】")
        for m in official[:10]:
            name = str(m.get("name") or "")
            cnt = int(m.get("publish_count") or 0)
            samples = m.get("sample_titles") or []
            sample_str = f"，示例：《{samples[0]}》" if samples else ""
            lines.append(f"  · {name}（{cnt} 篇）{sample_str}")

    if local_count > 0:
        lines.append("")
        lines.append("【地方媒体 Top 10（按发文量降序）】")
        for m in local[:10]:
            name = str(m.get("name") or "")
            cnt = int(m.get("publish_count") or 0)
            samples = m.get("sample_titles") or []
            sample_str = f"，示例：《{samples[0]}》" if samples else ""
            lines.append(f"  · {name}（{cnt} 篇）{sample_str}")

    if network_count > 0:
        lines.append("")
        lines.append("【网络媒体 Top 10（按发文量降序）】")
        for m in network[:10]:
            name = str(m.get("name") or "")
            cnt = int(m.get("publish_count") or 0)
            samples = m.get("sample_titles") or []
            sample_str = f"，示例：《{samples[0]}》" if samples else ""
            lines.append(f"  · {name}（{cnt} 篇）{sample_str}")

    if comprehensive_count > 0:
        lines.append("")
        lines.append("【综合媒体 Top 10（按发文量降序）】")
        for m in comprehensive[:10]:
            name = str(m.get("name") or "")
            cnt = int(m.get("publish_count") or 0)
            samples = m.get("sample_titles") or []
            sample_str = f"，示例：《{samples[0]}》" if samples else ""
            lines.append(f"  · {name}（{cnt} 篇）{sample_str}")

    if total_articles > 0:
        official_ratio = round(official_articles / total_articles * 100, 1)
        network_ratio = round(network_articles / total_articles * 100, 1)
        lines.append("")
        lines.append(f"官方媒体发文占比：{official_ratio}%，网络媒体发文占比：{network_ratio}%（参考值，不含未标注来源）")

    return "\n".join(lines)


__all__ = ["media_coverage_summary_tool"]
