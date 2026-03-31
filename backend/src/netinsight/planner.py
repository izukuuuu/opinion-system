"""Task planning helpers for the NetInsight acquisition queue."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from ..utils.ai import call_langchain_chat
from .config import load_netinsight_config

DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})"),
]

PLATFORM_ALIASES = {
    "微博": ["微博", "weibo"],
    "微信": ["微信", "公众号", "公号"],
    "新闻网站": ["新闻网站", "门户", "媒体", "新闻", "网站"],
    "新闻APP": ["新闻app", "客户端", "新闻客户端", "app"],
    "论坛": ["论坛", "贴吧", "知乎", "豆瓣", "问答"],
    "视频": ["视频", "抖音", "快手", "b站", "哔哩哔哩", "西瓜视频"],
    "自媒体号": ["自媒体", "小红书", "头条号", "百家号", "网易号", "搜狐号"],
    "全部": ["全部平台", "全平台", "所有平台", "全部"],
}

KEYWORD_SPLIT_RE = re.compile(r"[\n,，;；、|/]+")
JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def normalize_keywords(values: Any) -> List[str]:
    if isinstance(values, str):
        raw_items = KEYWORD_SPLIT_RE.split(values)
    elif isinstance(values, list):
        raw_items = [str(item) for item in values]
    else:
        raw_items = [str(values or "")]

    deduped: List[str] = []
    seen = set()
    for item in raw_items:
        cleaned = _clean_keyword(item)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def normalize_platforms(values: Any) -> List[str]:
    if isinstance(values, str):
        candidates = KEYWORD_SPLIT_RE.split(values)
    elif isinstance(values, list):
        candidates = [str(item) for item in values]
    else:
        candidates = []

    resolved: List[str] = []
    seen = set()
    for item in candidates:
        lowered = str(item or "").strip().lower()
        if not lowered:
            continue
        matched = None
        for canonical, aliases in PLATFORM_ALIASES.items():
            if lowered == canonical.lower() or any(lowered == alias.lower() for alias in aliases):
                matched = canonical
                break
        if matched is None:
            matched = str(item).strip()
        if matched and matched not in seen:
            seen.add(matched)
            resolved.append(matched)
    if "全部" in resolved:
        return ["全部"]
    return resolved


def plan_task_from_brief(brief: str) -> Dict[str, Any]:
    settings_config = load_netinsight_config()
    planner_cfg = settings_config.get("planner", {})
    runtime_cfg = settings_config.get("runtime", {})

    heuristic = _heuristic_plan(brief, planner_cfg, runtime_cfg)
    llm_plan = _llm_plan(brief)
    if llm_plan:
        merged = dict(heuristic)
        for key, value in llm_plan.items():
            if value not in (None, "", [], {}):
                merged[key] = value
        heuristic = merged
        heuristic["planner_source"] = "llm"
    else:
        heuristic["planner_source"] = "heuristic"

    heuristic["keywords"] = normalize_keywords(heuristic.get("keywords"))
    if not heuristic["keywords"]:
        heuristic["keywords"] = _heuristic_keywords(brief)

    heuristic["platforms"] = normalize_platforms(heuristic.get("platforms"))
    if not heuristic["platforms"]:
        heuristic["platforms"] = list(planner_cfg.get("default_platforms") or ["微博"])

    start_date, end_date = _normalise_dates(
        heuristic.get("start_date"),
        heuristic.get("end_date"),
        default_days=int(planner_cfg.get("default_days") or 30),
    )
    heuristic["start_date"] = start_date
    heuristic["end_date"] = end_date
    heuristic["time_range"] = f"{start_date} 00:00:00;{end_date} 23:59:59"

    heuristic["total_limit"] = _safe_int(
        heuristic.get("total_limit"),
        int(planner_cfg.get("default_total_limit") or 500),
        minimum=1,
    )
    heuristic["page_size"] = _safe_int(
        heuristic.get("page_size"),
        int(runtime_cfg.get("page_size") or 50),
        minimum=10,
    )
    heuristic["sort"] = str(heuristic.get("sort") or runtime_cfg.get("sort") or "comments_desc").strip()
    heuristic["info_type"] = str(heuristic.get("info_type") or runtime_cfg.get("info_type") or "2").strip()
    heuristic["dedupe_by_content"] = bool(heuristic.get("dedupe_by_content", True))
    heuristic["title"] = str(heuristic.get("title") or _default_title(brief, heuristic["keywords"])).strip()
    heuristic["summary"] = str(heuristic.get("summary") or brief or heuristic["title"]).strip()
    return heuristic


def _heuristic_plan(
    brief: str,
    planner_cfg: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    keywords = _heuristic_keywords(brief)
    platforms = _heuristic_platforms(brief, planner_cfg)
    start_date, end_date = _heuristic_dates(brief, int(planner_cfg.get("default_days") or 30))
    return {
        "title": _default_title(brief, keywords),
        "summary": str(brief or "").strip(),
        "keywords": keywords,
        "platforms": platforms,
        "start_date": start_date,
        "end_date": end_date,
        "total_limit": int(planner_cfg.get("default_total_limit") or 500),
        "page_size": int(runtime_cfg.get("page_size") or 50),
        "sort": str(runtime_cfg.get("sort") or "comments_desc"),
        "info_type": str(runtime_cfg.get("info_type") or "2"),
        "dedupe_by_content": True,
    }


def _llm_plan(brief: str) -> Optional[Dict[str, Any]]:
    text = str(brief or "").strip()
    if not text:
        return None

    today = date.today().isoformat()
    system_prompt = (
        "你是 NetInsight 采集任务规划器。"
        "请把用户的自然语言需求整理为 JSON，不要输出任何额外解释。"
        "JSON 字段固定为："
        '{"title":"","summary":"","keywords":[],"platforms":[],"start_date":"","end_date":"","total_limit":500,'
        '"page_size":50,"sort":"comments_desc","info_type":"2","dedupe_by_content":true}.'
        "关键词要尽量短，适合直接在 NetInsight 里检索。日期必须是 YYYY-MM-DD。"
        "如无法判断平台，留空数组。"
    )
    user_prompt = f"今天是 {today}。请为下面的需求生成 NetInsight 采集建议：\n{text}"

    try:
        response = asyncio.run(
            call_langchain_chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                task="default",
                temperature=0.1,
                max_tokens=600,
            )
        )
    except Exception:
        response = None
    if not response:
        return None

    match = JSON_BLOCK_RE.search(response)
    raw_json = match.group(0) if match else response
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _heuristic_keywords(brief: str) -> List[str]:
    text = str(brief or "").strip()
    if not text:
        return []

    keyword_hint = re.search(r"(关键词|检索词)\s*[:：]\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
    if keyword_hint:
        hinted = normalize_keywords(keyword_hint.group(2))
        if hinted:
            return hinted[:10]

    quoted = re.findall(r"[\"“”']([^\"“”']{2,40})[\"“”']", text)
    if quoted:
        result = normalize_keywords(quoted)
        if result:
            return result[:10]

    hashtags = re.findall(r"#([^#]{1,40})#", text)
    if hashtags:
        result = normalize_keywords(hashtags)
        if result:
            return result[:10]

    pieces = normalize_keywords(text)
    if len(pieces) >= 2:
        return pieces[:10]

    cleaned = _clean_keyword(text)
    if cleaned:
        return [cleaned]
    return []


def _heuristic_platforms(brief: str, planner_cfg: Dict[str, Any]) -> List[str]:
    text = str(brief or "").strip().lower()
    matched: List[str] = []
    for canonical, aliases in PLATFORM_ALIASES.items():
        if canonical == "全部":
            continue
        if canonical.lower() in text or any(alias.lower() in text for alias in aliases):
            matched.append(canonical)
    if matched:
        return matched
    return list(planner_cfg.get("default_platforms") or ["微博"])


def _heuristic_dates(brief: str, default_days: int) -> tuple[str, str]:
    text = str(brief or "").strip()
    explicit = _extract_explicit_dates(text)
    if len(explicit) >= 2:
        return _normalise_dates(explicit[0], explicit[1], default_days=default_days)

    today = date.today()
    lowered = text.lower()
    if "今天" in text:
        return today.isoformat(), today.isoformat()
    if "昨天" in text:
        yesterday = today - timedelta(days=1)
        return yesterday.isoformat(), yesterday.isoformat()
    if "本月" in text:
        return today.replace(day=1).isoformat(), today.isoformat()
    if "上个月" in text:
        first_this_month = today.replace(day=1)
        last_prev_month = first_this_month - timedelta(days=1)
        return last_prev_month.replace(day=1).isoformat(), last_prev_month.isoformat()

    days = _days_from_relative_text(lowered)
    if days is None:
        days = default_days
    start = today - timedelta(days=max(days - 1, 0))
    return start.isoformat(), today.isoformat()


def _extract_explicit_dates(text: str) -> List[str]:
    results: List[str] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                parsed = date(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                )
            except ValueError:
                continue
            results.append(parsed.isoformat())
    return results


def _days_from_relative_text(lowered: str) -> Optional[int]:
    numeric_match = re.search(r"(近|最近)(\d+)(天|日|周|个月|月)", lowered)
    if numeric_match:
        amount = int(numeric_match.group(2))
        unit = numeric_match.group(3)
        if unit in {"天", "日"}:
            return amount
        if unit == "周":
            return amount * 7
        return amount * 30

    named = {
        "最近一周": 7,
        "近一周": 7,
        "最近7天": 7,
        "近7天": 7,
        "最近半个月": 15,
        "近半个月": 15,
        "最近一个月": 30,
        "近一个月": 30,
        "最近三个月": 90,
        "近三个月": 90,
        "最近半年": 180,
        "近半年": 180,
    }
    for phrase, days in named.items():
        if phrase in lowered:
            return days
    return None


def _default_title(brief: str, keywords: List[str]) -> str:
    if keywords:
        return f"NetInsight · {keywords[0]}"
    text = re.sub(r"\s+", " ", str(brief or "").strip())
    return f"NetInsight · {text[:24]}" if text else "NetInsight 采集任务"


def _clean_keyword(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(请|帮我|帮忙|关注|分析|监测|采集)[:：]?", "", text)
    text = re.sub(r"(最近|近)\d+(天|日|周|个月|月)", "", text)
    return text.strip("，。；;、 ")


def _normalise_dates(
    start_value: Any,
    end_value: Any,
    *,
    default_days: int,
) -> tuple[str, str]:
    today = date.today()
    start = _coerce_date(start_value)
    end = _coerce_date(end_value)

    if start and not end:
        end = start
    if end and not start:
        start = end - timedelta(days=max(default_days - 1, 0))
    if not start or not end:
        end = end or today
        start = start or (end - timedelta(days=max(default_days - 1, 0)))

    if start > end:
        start, end = end, start
    return start.isoformat(), end.isoformat()


def _coerce_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    extracted = _extract_explicit_dates(text)
    if extracted:
        return datetime.strptime(extracted[0], "%Y-%m-%d").date()
    return None


def _safe_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


__all__ = [
    "normalize_keywords",
    "normalize_platforms",
    "plan_task_from_brief",
]
