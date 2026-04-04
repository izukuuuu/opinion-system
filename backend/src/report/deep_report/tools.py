from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

from langchain.tools import tool

from ...utils.setting.paths import bucket
from ..evidence_retriever import search_raw_records, verify_claim_with_records


def _safe_load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _iter_rows(topic_identifier: str, start: str, end: str) -> Iterable[Dict[str, Any]]:
    folder = f"{start}_{end}" if end and end != start else start
    overall_path = bucket("fetch", topic_identifier, folder) / "总体.jsonl"
    rows: List[Dict[str, Any]] = []
    if not overall_path.exists():
        return rows
    try:
        with overall_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return rows


def _clean_list(raw_text: str) -> List[str]:
    text = str(raw_text or "").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except Exception:
        value = [item.strip() for item in text.split(",")]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


@tool
def query_documents(
    topic_identifier: str,
    start: str,
    end: str,
    query: str,
    entities_json: str = "[]",
    platforms_json: str = "[]",
    time_start: str = "",
    time_end: str = "",
    top_k: int = 12,
) -> str:
    """回查原始舆情条目，用于证据整理和引用索引。"""
    payload = search_raw_records(
        topic_identifier=str(topic_identifier or "").strip(),
        start=str(start or "").strip(),
        end=str(end or "").strip(),
        query=str(query or "").strip(),
        entities=_clean_list(entities_json),
        platforms=_clean_list(platforms_json),
        time_start=str(time_start or "").strip(),
        time_end=str(time_end or "").strip(),
        top_k=max(1, min(int(top_k or 12), 30)),
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def verify_claim(
    topic_identifier: str,
    start: str,
    end: str,
    claim: str,
    entities_json: str = "[]",
    platforms_json: str = "[]",
    top_k: int = 20,
) -> str:
    """验证某条判断是否有足够直接证据支撑。"""
    payload = verify_claim_with_records(
        topic_identifier=str(topic_identifier or "").strip(),
        start=str(start or "").strip(),
        end=str(end or "").strip(),
        claim=str(claim or "").strip(),
        entities=_clean_list(entities_json),
        platforms=_clean_list(platforms_json),
        retrieve_mode="claim_verification",
        top_k=max(5, min(int(top_k or 20), 40)),
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def build_timeline(
    topic_identifier: str,
    start: str,
    end: str,
    query: str = "",
    top_k: int = 10,
) -> str:
    """按日期聚合原始条目，生成事件时间线候选。"""
    query_tokens = [token.lower() for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,}", str(query or ""))]
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in _iter_rows(topic_identifier, start, end):
        title = str(row.get("title") or "").strip()
        content = str(row.get("content") or row.get("contents") or "").strip()
        haystack = f"{title}\n{content}".lower()
        if query_tokens and not any(token in haystack for token in query_tokens):
            continue
        date_text = str(row.get("published_at") or row.get("publish_time") or row.get("date") or "").strip()[:10]
        if not date_text:
            continue
        grouped.setdefault(date_text, []).append(
            {
                "title": title,
                "platform": str(row.get("platform") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "snippet": re.sub(r"\s+", " ", content)[:140],
            }
        )
    output = []
    for date_text in sorted(grouped.keys())[: max(1, min(int(top_k or 10), 20))]:
        rows = grouped[date_text]
        output.append(
            {
                "date": date_text,
                "count": len(rows),
                "headline": str(rows[0].get("title") or "").strip(),
                "supporting_items": rows[:4],
            }
        )
    return json.dumps({"timeline": output}, ensure_ascii=False, indent=2)


@tool
def build_entity_graph(
    topic_identifier: str,
    start: str,
    end: str,
    query: str = "",
    top_k: int = 12,
) -> str:
    """抽取主体候选和平台分布，用于传播结构和主体视图。"""
    query_tokens = [token.lower() for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,}", str(query or ""))]
    subject_counter: Counter[str] = Counter()
    platform_counter: Counter[str] = Counter()
    for row in _iter_rows(topic_identifier, start, end):
        title = str(row.get("title") or "").strip()
        content = str(row.get("content") or row.get("contents") or "").strip()
        haystack = f"{title}\n{content}".lower()
        if query_tokens and not any(token in haystack for token in query_tokens):
            continue
        platform = str(row.get("platform") or "").strip()
        author = str(row.get("author") or "").strip()
        if platform:
            platform_counter[platform] += 1
        if author:
            subject_counter[author] += 1
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,12}", title)[:4]:
            subject_counter[token] += 1
    payload = {
        "subjects": [{"name": name, "count": count} for name, count in subject_counter.most_common(max(1, min(int(top_k or 12), 20)))],
        "platforms": [{"name": name, "count": count} for name, count in platform_counter.most_common(8)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def run_volume_analysis(topic_identifier: str, start: str, end: str) -> str:
    """读取基础分析概览，返回声量与趋势摘要。"""
    folder = f"{start}_{end}" if end and end != start else start
    volume_path = bucket("analyze", topic_identifier, folder) / "volume" / "总体" / "volume.json"
    trends_path = bucket("analyze", topic_identifier, folder) / "trends" / "总体" / "trends.json"
    payload = {
        "volume": _safe_load_json(volume_path) or {},
        "trends": _safe_load_json(trends_path) or {},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_persistence_tools(
    *,
    draft_writer: Callable[[str], Dict[str, Any]],
    cache_writer: Callable[[Dict[str, Any]], Dict[str, Any]],
    publish_writer: Callable[[Dict[str, Any]], Dict[str, Any]],
    production_writer: Callable[[Dict[str, Any]], Dict[str, Any]],
    delete_writer: Callable[[str], Dict[str, Any]],
) -> List[Any]:
    @tool("write_final_report")
    def write_final_report(markdown: str) -> str:
        """将最终文稿写入运行时产物目录。"""
        return json.dumps(draft_writer(str(markdown or "")), ensure_ascii=False, indent=2)

    @tool("overwrite_report_cache")
    def overwrite_report_cache(payload_json: str) -> str:
        """覆盖写入正式报告缓存。"""
        try:
            payload = json.loads(str(payload_json or "{}"))
        except Exception:
            payload = {}
        return json.dumps(cache_writer(payload if isinstance(payload, dict) else {}), ensure_ascii=False, indent=2)

    @tool("publish_report")
    def publish_report(payload_json: str) -> str:
        """预留的外发动作。"""
        try:
            payload = json.loads(str(payload_json or "{}"))
        except Exception:
            payload = {}
        return json.dumps(publish_writer(payload if isinstance(payload, dict) else {}), ensure_ascii=False, indent=2)

    @tool("persist_production_record")
    def persist_production_record(payload_json: str) -> str:
        """预留的生产侧写入动作。"""
        try:
            payload = json.loads(str(payload_json or "{}"))
        except Exception:
            payload = {}
        return json.dumps(production_writer(payload if isinstance(payload, dict) else {}), ensure_ascii=False, indent=2)

    @tool("delete_workspace_artifact")
    def delete_workspace_artifact(path: str) -> str:
        """删除运行时产物。"""
        return json.dumps(delete_writer(str(path or "")), ensure_ascii=False, indent=2)

    return [
        write_final_report,
        overwrite_report_cache,
        publish_report,
        persist_production_record,
        delete_workspace_artifact,
    ]
