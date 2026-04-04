from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import heapq
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..utils.setting.paths import bucket, get_data_root


_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,16}")
_NEGATION_HINTS = ("辟谣", "不实", "并非", "未发布", "网传", "谣言", "假的", "误读", "未经证实")


def _extract_date_text(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    matched = re.search(r"(20\d{2}-\d{2}-\d{2})", raw)
    return matched.group(1) if matched else ""


def _extract_date_obj(value: Any) -> Optional[datetime]:
    date_text = _extract_date_text(value)
    if not date_text:
        return None
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except Exception:
        return None


def _tokenize(text: Any, *, max_items: int = 18) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    tokens: List[str] = []
    seen = set()
    for token in _TOKEN_RE.findall(raw):
        token = str(token or "").strip()
        if len(token) < 2:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(token)
        if len(tokens) >= max_items:
            break
    return tokens


def _resolve_overall_jsonl(topic_identifier: str, start: str, end: str) -> Optional[Path]:
    folder = f"{start}_{end}" if end and end != start else start
    candidate = bucket("fetch", topic_identifier, folder) / "总体.jsonl"
    if candidate.exists():
        return candidate
    return None


def _iter_upload_jsonl_files(topic_identifier: str) -> List[Path]:
    uploads_dir = get_data_root() / "projects" / topic_identifier / "uploads" / "jsonl"
    if not uploads_dir.exists() or not uploads_dir.is_dir():
        return []
    return sorted([path for path in uploads_dir.glob("*.jsonl") if path.is_file()])


def _iter_source_rows(topic_identifier: str, start: str, end: str) -> Iterable[Dict[str, Any]]:
    overall_path = _resolve_overall_jsonl(topic_identifier, start, end)
    source_files = [overall_path] if overall_path else _iter_upload_jsonl_files(topic_identifier)
    for file_path in source_files:
        if not file_path or not file_path.exists():
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


def _record_text(row: Dict[str, Any]) -> str:
    parts = [
        str(row.get("title") or "").strip(),
        str(row.get("contents") or row.get("content") or "").strip(),
        str(row.get("author") or "").strip(),
        str(row.get("hit_words") or "").strip(),
        str(row.get("classification") or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def _make_snippet(text: str, tokens: List[str], max_chars: int = 120) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw:
        return ""
    position = -1
    chosen = ""
    for token in tokens:
        idx = raw.find(token)
        if idx >= 0 and (position < 0 or idx < position):
            position = idx
            chosen = token
    if position < 0:
        return raw[:max_chars]
    start = max(0, position - 24)
    end = min(len(raw), position + max_chars - 24)
    snippet = raw[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(raw):
        snippet = snippet + "..."
    return snippet or chosen


def _score_row(text: str, title: str, tokens: List[str]) -> Tuple[float, List[str]]:
    matched: List[str] = []
    score = 0.0
    lowered_text = text.lower()
    lowered_title = title.lower()
    for token in tokens:
        lowered = token.lower()
        if lowered in lowered_title:
            matched.append(token)
            score += 2.2
        elif lowered in lowered_text:
            matched.append(token)
            score += 1.0
    return score, matched


def _normalise_platforms(platforms: Any) -> List[str]:
    if not isinstance(platforms, list):
        return []
    return [str(item).strip() for item in platforms if str(item or "").strip()]


def _normalise_terms(values: Any, *, max_items: int = 18) -> List[str]:
    if not isinstance(values, list):
        return []
    terms: List[str] = []
    seen = set()
    for item in values:
        token = str(item or "").strip()
        if len(token) < 2:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(token)
        if len(terms) >= max_items:
            break
    return terms


def _build_query_terms(query: str, entities: Optional[List[str]] = None, *, max_items: int = 18) -> List[str]:
    entity_terms = _normalise_terms(entities, max_items=max_items)
    query_terms = entity_terms + [token for token in _tokenize(query) if token not in entity_terms]
    return query_terms[:max_items]


def _within_range(date_text: str, start: str = "", end: str = "") -> bool:
    if start and date_text and date_text < start:
        return False
    if end and date_text and date_text > end:
        return False
    return True


def _iter_filtered_rows(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
) -> Iterable[Dict[str, Any]]:
    allowed_platforms = set(_normalise_platforms(platforms))
    lower_bound = str(time_start or "").strip() or str(start or "").strip()
    upper_bound = str(time_end or "").strip() or str(end or "").strip()
    for row in _iter_source_rows(topic_identifier, start, end):
        date_text = _extract_date_text(row.get("published_at") or row.get("publish_time") or row.get("date"))
        if not _within_range(date_text, lower_bound, upper_bound):
            continue
        platform = str(row.get("platform") or "").strip()
        if allowed_platforms and platform and platform not in allowed_platforms:
            continue
        yield row


def _build_scored_item(row: Dict[str, Any], *, matched_terms: List[str], score: float) -> Dict[str, Any]:
    title = str(row.get("title") or "").strip()
    platform = str(row.get("platform") or "").strip()
    text = _record_text(row)
    return {
        "title": title,
        "snippet": _make_snippet(text, matched_terms or _tokenize(title or text)),
        "url": str(row.get("url") or "").strip(),
        "published_at": str(row.get("published_at") or row.get("publish_time") or row.get("date") or "").strip(),
        "platform": platform,
        "author": str(row.get("author") or "").strip(),
        "matched_terms": matched_terms[:6],
        "score": round(score, 3),
    }


def verify_claim_with_records(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    claim: str,
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    retrieve_mode: str = "claim_verification",
    top_k: int = 20,
) -> Dict[str, Any]:
    claim_text = str(claim or "").strip()
    entity_terms = [str(item).strip() for item in (entities or []) if str(item or "").strip()]
    query_terms = entity_terms + [token for token in _tokenize(claim_text) if token not in entity_terms]
    query_terms = query_terms[:18]
    allowed_platforms = set(_normalise_platforms(platforms))
    safe_top_k = max(3, min(int(top_k or 20), 50))

    supporting_heap: List[Tuple[float, int, Dict[str, Any]]] = []
    contradicting_heap: List[Tuple[float, int, Dict[str, Any]]] = []
    source_distribution: Dict[str, int] = {}
    scanned = 0
    matched = 0
    sequence = 0

    for row in _iter_source_rows(topic_identifier, start, end):
        scanned += 1
        date_text = _extract_date_text(row.get("published_at") or row.get("publish_time") or row.get("date"))
        if start and date_text and date_text < start:
            continue
        if end and date_text and date_text > end:
            continue

        platform = str(row.get("platform") or "").strip()
        if allowed_platforms and platform and platform not in allowed_platforms:
            continue

        title = str(row.get("title") or "").strip()
        text = _record_text(row)
        if not text:
            continue
        score, matched_terms = _score_row(text, title, query_terms)
        if score <= 0:
            continue
        matched += 1
        source_distribution[platform or "未知"] = source_distribution.get(platform or "未知", 0) + 1
        snippet = _make_snippet(text, matched_terms or query_terms)
        item = {
            "title": title,
            "snippet": snippet,
            "url": str(row.get("url") or "").strip(),
            "published_at": str(row.get("published_at") or row.get("publish_time") or row.get("date") or "").strip(),
            "platform": platform,
            "author": str(row.get("author") or "").strip(),
            "matched_terms": matched_terms[:6],
            "score": round(score, 3),
        }
        lowered_text = text.lower()
        target_heap = contradicting_heap if any(hint in lowered_text for hint in _NEGATION_HINTS) else supporting_heap
        sequence += 1
        if len(target_heap) < safe_top_k:
            heapq.heappush(target_heap, (score, sequence, item))
        else:
            heapq.heappushpop(target_heap, (score, sequence, item))

    supporting_items = [item for _, _, item in sorted(supporting_heap, key=lambda pair: pair[0], reverse=True)]
    contradicting_items = [item for _, _, item in sorted(contradicting_heap, key=lambda pair: pair[0], reverse=True)]

    representative_quotes = [
        {
            "quote": str(item.get("snippet") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "platform": str(item.get("platform") or "").strip(),
        }
        for item in supporting_items[:3]
        if str(item.get("snippet") or "").strip()
    ]

    if supporting_items and contradicting_items:
        verification_status = "conflicting"
    elif len(supporting_items) >= 3:
        verification_status = "supported"
    elif supporting_items:
        verification_status = "partially_supported"
    else:
        verification_status = "unverified"

    return {
        "claim": claim_text,
        "retrieve_mode": str(retrieve_mode or "claim_verification").strip(),
        "query_terms": query_terms[:10],
        "supporting_items": supporting_items[:safe_top_k],
        "contradicting_items": contradicting_items[: max(3, min(8, safe_top_k // 2))],
        "insufficient_evidence": verification_status in {"unverified", "partially_supported"},
        "representative_quotes": representative_quotes,
        "source_distribution": source_distribution,
        "verification_status": verification_status,
        "scanned_records": scanned,
        "matched_records": matched,
    }


def search_raw_records(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    query: str,
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
    top_k: int = 20,
) -> Dict[str, Any]:
    query_text = str(query or "").strip()
    query_terms = _build_query_terms(query_text, entities)
    safe_top_k = max(3, min(int(top_k or 20), 50))
    items_heap: List[Tuple[float, int, Dict[str, Any]]] = []
    source_distribution: Dict[str, int] = {}
    time_distribution: Dict[str, int] = {}
    matched_terms_counter: Counter[str] = Counter()
    scanned = 0
    matched = 0
    sequence = 0

    for row in _iter_filtered_rows(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        platforms=platforms,
        time_start=time_start,
        time_end=time_end,
    ):
        scanned += 1
        title = str(row.get("title") or "").strip()
        text = _record_text(row)
        if not text:
            continue
        if query_terms:
            score, matched_terms = _score_row(text, title, query_terms)
            if score <= 0:
                continue
        else:
            score = 1.0
            matched_terms = []
        matched += 1
        platform = str(row.get("platform") or "").strip() or "未知"
        date_text = _extract_date_text(row.get("published_at") or row.get("publish_time") or row.get("date")) or "未知"
        source_distribution[platform] = source_distribution.get(platform, 0) + 1
        time_distribution[date_text] = time_distribution.get(date_text, 0) + 1
        matched_terms_counter.update(matched_terms)
        item = _build_scored_item(row, matched_terms=matched_terms, score=score)
        sequence += 1
        if len(items_heap) < safe_top_k:
            heapq.heappush(items_heap, (score, sequence, item))
        else:
            heapq.heappushpop(items_heap, (score, sequence, item))

    items = [item for _, _, item in sorted(items_heap, key=lambda pair: pair[0], reverse=True)]
    return {
        "query": query_text,
        "query_terms": query_terms[:10],
        "time_start": str(time_start or start or "").strip(),
        "time_end": str(time_end or end or "").strip(),
        "items": items,
        "source_distribution": source_distribution,
        "time_distribution": dict(sorted(time_distribution.items(), key=lambda pair: pair[0])),
        "high_signal_terms": [term for term, _ in matched_terms_counter.most_common(8)],
        "scanned_records": scanned,
        "matched_records": matched,
    }


def summarize_source_scope(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    top_platforms: int = 6,
    top_authors: int = 8,
) -> Dict[str, Any]:
    platform_counter: Counter[str] = Counter()
    author_counter: Counter[str] = Counter()
    scanned = 0
    platform_present = 0
    author_present = 0
    org_present = 0
    official_present = 0

    for row in _iter_filtered_rows(topic_identifier=topic_identifier, start=start, end=end):
        scanned += 1
        platform = str(row.get("platform") or "").strip()
        author = str(row.get("author") or "").strip()
        organization = str(row.get("organization") or row.get("org") or "").strip()
        author_type = str(row.get("author_type") or row.get("account_type") or row.get("publisher_type") or "").strip()
        source_type = str(row.get("source_type") or "").strip()
        is_official = row.get("is_official")

        if platform:
            platform_present += 1
            platform_counter[platform] += 1
        if author:
            author_present += 1
            author_counter[author] += 1
        if organization:
            org_present += 1
        if author_type or source_type or is_official not in (None, "", False, 0, "0", "false", "False"):
            official_present += 1

    available_dimensions = ["platform"]
    if author_present:
        available_dimensions.append("author")
    if org_present:
        available_dimensions.append("organization")
    if official_present:
        available_dimensions.extend(
            item for item in ("author_type", "official_source_flag") if item not in available_dimensions
        )

    missing_dimensions = []
    if not official_present:
        missing_dimensions.extend(["author_type", "official_source_flag", "official_posting_record"])
    if not org_present:
        missing_dimensions.append("organization")

    writable_subjects = ["平台分布"]
    if author_present:
        writable_subjects.append("作者署名或头部发布者")
    if org_present:
        writable_subjects.append("组织名称")

    prohibited_inference = []
    if not official_present:
        prohibited_inference.append("不能从当前数据直接推导政务、官方或机构账号是否缺位、是否同步发布、是否响应迟缓。")
    if not org_present:
        prohibited_inference.append("不能从当前数据直接推导具体机构之间的分工或责任链。")

    return {
        "scanned_records": scanned,
        "platforms": [{"name": name, "count": count} for name, count in platform_counter.most_common(max(1, top_platforms))],
        "authors": [{"name": name, "count": count} for name, count in author_counter.most_common(max(1, top_authors))],
        "coverage": {
            "platform_ratio": round(platform_present / scanned, 4) if scanned else 0.0,
            "author_ratio": round(author_present / scanned, 4) if scanned else 0.0,
            "organization_ratio": round(org_present / scanned, 4) if scanned else 0.0,
            "official_signal_ratio": round(official_present / scanned, 4) if scanned else 0.0,
        },
        "available_dimensions": available_dimensions,
        "missing_dimensions": missing_dimensions,
        "writable_subjects": writable_subjects,
        "prohibited_inference": prohibited_inference,
        "boundary_summary": (
            "当前主体范围直接来自原始条目字段统计，只能支撑平台、作者和已显式存在的组织/主体字段判断；"
            "缺失维度不得被扩写成机构行为结论。"
        ),
    }


def analyze_temporal_event_window(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    anchor_date: str,
    query: str = "",
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    window_days: int = 7,
    top_k: int = 6,
) -> Dict[str, Any]:
    anchor_dt = _extract_date_obj(anchor_date)
    if anchor_dt is None:
        return {
            "anchor_date": str(anchor_date or "").strip(),
            "verification_status": "invalid_anchor_date",
            "windows": {},
            "shift_summary": "时间锚点格式无效，无法进行时窗比较。",
        }

    safe_window_days = max(1, min(int(window_days or 7), 30))
    query_terms = _build_query_terms(str(query or "").strip(), entities)
    safe_top_k = max(2, min(int(top_k or 6), 12))
    windows: Dict[str, Dict[str, Any]] = {
        "pre_window": {"count": 0, "term_counter": Counter(), "items_heap": []},
        "anchor_window": {"count": 0, "term_counter": Counter(), "items_heap": []},
        "post_window": {"count": 0, "term_counter": Counter(), "items_heap": []},
    }
    sequence = 0

    for row in _iter_filtered_rows(topic_identifier=topic_identifier, start=start, end=end, platforms=platforms):
        row_dt = _extract_date_obj(row.get("published_at") or row.get("publish_time") or row.get("date"))
        if row_dt is None:
            continue
        delta_days = (row_dt.date() - anchor_dt.date()).days
        if delta_days < -safe_window_days or delta_days > safe_window_days:
            continue
        if delta_days < 0:
            bucket_key = "pre_window"
        elif delta_days == 0:
            bucket_key = "anchor_window"
        else:
            bucket_key = "post_window"

        title = str(row.get("title") or "").strip()
        text = _record_text(row)
        if not text:
            continue
        if query_terms:
            score, matched_terms = _score_row(text, title, query_terms)
            if score <= 0:
                continue
        else:
            score = 1.0
            matched_terms = _tokenize(title or text, max_items=6)

        bucket = windows[bucket_key]
        bucket["count"] += 1
        bucket["term_counter"].update(matched_terms)
        item = _build_scored_item(row, matched_terms=matched_terms, score=score)
        sequence += 1
        heap: List[Tuple[float, int, Dict[str, Any]]] = bucket["items_heap"]
        if len(heap) < safe_top_k:
            heapq.heappush(heap, (score, sequence, item))
        else:
            heapq.heappushpop(heap, (score, sequence, item))

    normalized_windows: Dict[str, Any] = {}
    for bucket_key, bucket in windows.items():
        items = [item for _, _, item in sorted(bucket["items_heap"], key=lambda pair: pair[0], reverse=True)]
        normalized_windows[bucket_key] = {
            "count": int(bucket.get("count") or 0),
            "top_terms": [term for term, _ in bucket["term_counter"].most_common(6)],
            "sample_items": items,
        }

    pre_count = int(normalized_windows["pre_window"]["count"] or 0)
    anchor_count = int(normalized_windows["anchor_window"]["count"] or 0)
    post_count = int(normalized_windows["post_window"]["count"] or 0)
    if anchor_count > max(pre_count, post_count):
        shift_summary = "锚点日期附近讨论最集中，说明该时间点与传播放大存在明显同步关系。"
    elif post_count > pre_count:
        shift_summary = "锚点后窗口的相关讨论继续扩散，说明事件效应并未止于单日峰值。"
    elif pre_count > 0:
        shift_summary = "锚点前已存在较强铺垫，当前节点更像累积放量而非单点凭空触发。"
    else:
        shift_summary = "当前时间窗内的有效样本有限，只能做弱趋势判断。"

    return {
        "anchor_date": anchor_dt.strftime("%Y-%m-%d"),
        "query_terms": query_terms[:10],
        "window_days": safe_window_days,
        "verification_status": "ok",
        "windows": normalized_windows,
        "shift_summary": shift_summary,
    }


def compare_content_focus(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    bucket_a_terms: List[str],
    bucket_b_terms: List[str],
    query: str = "",
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
    top_k: int = 8,
) -> Dict[str, Any]:
    query_terms = _build_query_terms(str(query or "").strip(), entities)
    bucket_a = _normalise_terms(bucket_a_terms, max_items=16)
    bucket_b = _normalise_terms(bucket_b_terms, max_items=16)
    safe_top_k = max(2, min(int(top_k or 8), 12))

    def _empty_bucket(label: str) -> Dict[str, Any]:
        return {"label": label, "count": 0, "top_terms": [], "sample_items": [], "total_score": 0.0}

    bucket_stats: Dict[str, Dict[str, Any]] = {
        "bucket_a": _empty_bucket("bucket_a"),
        "bucket_b": _empty_bucket("bucket_b"),
    }
    sequence = 0

    for row in _iter_filtered_rows(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        platforms=platforms,
        time_start=time_start,
        time_end=time_end,
    ):
        title = str(row.get("title") or "").strip()
        text = _record_text(row)
        if not text:
            continue
        if query_terms:
            base_score, _ = _score_row(text, title, query_terms)
            if base_score <= 0:
                continue
        else:
            base_score = 1.0
        a_score, a_terms = _score_row(text, title, bucket_a)
        b_score, b_terms = _score_row(text, title, bucket_b)
        if a_score <= 0 and b_score <= 0:
            continue

        bucket_key = "bucket_a" if a_score >= b_score else "bucket_b"
        matched_terms = a_terms if bucket_key == "bucket_a" else b_terms
        score = base_score + max(a_score, b_score)
        bucket = bucket_stats[bucket_key]
        bucket["count"] += 1
        bucket["total_score"] = round(float(bucket.get("total_score") or 0.0) + score, 3)
        term_counter: Counter[str] = bucket.setdefault("term_counter", Counter())
        term_counter.update(matched_terms)
        item = _build_scored_item(row, matched_terms=matched_terms, score=score)
        sequence += 1
        heap: List[Tuple[float, int, Dict[str, Any]]] = bucket.setdefault("items_heap", [])
        if len(heap) < safe_top_k:
            heapq.heappush(heap, (score, sequence, item))
        else:
            heapq.heappushpop(heap, (score, sequence, item))

    normalized_buckets: Dict[str, Any] = {}
    for bucket_key, bucket in bucket_stats.items():
        items = [item for _, _, item in sorted(bucket.get("items_heap") or [], key=lambda pair: pair[0], reverse=True)]
        normalized_buckets[bucket_key] = {
            "label": str(bucket.get("label") or bucket_key).strip(),
            "count": int(bucket.get("count") or 0),
            "top_terms": [term for term, _ in (bucket.get("term_counter") or Counter()).most_common(6)],
            "sample_items": items,
            "total_score": round(float(bucket.get("total_score") or 0.0), 3),
        }

    a_count = int(normalized_buckets["bucket_a"]["count"] or 0)
    b_count = int(normalized_buckets["bucket_b"]["count"] or 0)
    if a_count > b_count:
        dominant_focus = "bucket_a"
        comparison = "相关讨论更偏向第一组语义桶。"
    elif b_count > a_count:
        dominant_focus = "bucket_b"
        comparison = "相关讨论更偏向第二组语义桶。"
    else:
        dominant_focus = "balanced"
        comparison = "两组语义桶在当前样本中的讨论强度接近。"

    return {
        "query_terms": query_terms[:10],
        "time_start": str(time_start or start or "").strip(),
        "time_end": str(time_end or end or "").strip(),
        "bucket_a_terms": bucket_a[:10],
        "bucket_b_terms": bucket_b[:10],
        "bucket_a": normalized_buckets["bucket_a"],
        "bucket_b": normalized_buckets["bucket_b"],
        "dominant_focus": dominant_focus,
        "comparison": comparison,
    }
