from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from ..capability_adapters import (
    build_basic_analysis_insight,
    build_bertopic_insight,
    collect_basic_analysis_snapshot,
    collect_bertopic_snapshot,
)
from ..evidence_retriever import iter_filtered_records, resolve_source_scope, search_raw_records, verify_claim_with_records
from ...utils.setting.paths import get_data_root
from .schemas import (
    AgendaFrameMap,
    ActorPosition,
    AmplificationPath,
    ArgumentUnit,
    AttackEdge,
    AttributeNode,
    BridgeNode,
    CauseCandidate,
    ClaimRecord,
    ConflictEdge,
    ConflictMap,
    CrossPlatformBridge,
    CrossPlatformTransfer,
    DispatchQualityEntry,
    FrameCarrierActor,
    FrameRecord,
    FrameShift,
    CounterFrame,
    IssueAttributeEdge,
    IssueNode,
    MechanismSummary,
    NarrativeCarrier,
    PhaseShift,
    RefutationLag,
    ResolutionStatus,
    RouterDispatch,
    RouterDispatchPlan,
    RouterFacet,
    SupportEdge,
    TargetObject,
    TriggerEvent,
    UtilityAssessment,
    UtilityFailure,
    UtilityImprovementStep,
    V2_SCHEMA_VERSION,
    _utc_now,
)

_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,24}")

# 句子片段特征：包含动词/连接词等，用于 fallback 过滤
_SENTENCE_FRAGMENT_MARKERS = (
    "监测", "分析", "包括", "维度", "动态", "解读", "进行", "研究",
    "调查", "评估", "追踪", "观察", "统计", "汇总", "梳理", "整理",
    "以及", "其中", "针对", "围绕", "聚焦", "涵盖", "涉及", "相关",
)

_RISK_HINTS = ("辟谣", "不实", "谣言", "误读", "维权", "投诉", "冲突", "争议", "扩散", "爆发", "失控")
_STANCE_REFUTE_HINTS = ("辟谣", "不实", "误读", "谣言")
_ISSUE_HINTS = ("政策", "执法", "回应", "谣言", "争议", "风险", "传播", "平台", "治理")
_ATTRIBUTE_HINTS = {
    "risk": ("风险", "争议", "冲突", "辟谣"),
    "responsibility": ("责任", "回应", "处置", "治理"),
    "impact": ("影响", "扩散", "放大", "热度"),
    "execution": ("执行", "落地", "执法", "规则"),
}
_CLAIMABILITY_RULES = {
    "time_fact": ("发布", "回应", "发生", "时间"),
    "actor_position": ("回应", "表态", "支持", "反对", "质疑"),
    "propagation_change": ("扩散", "热度", "峰值", "传播"),
    "risk_signal": ("辟谣", "冲突", "争议", "投诉"),
}
_OFFICIAL_AUTHOR_HINTS = (
    "卫健委", "政府", "公安", "法院", "检察院", "铁路", "医院", "学校", "协会", "委员会", "办公室", "中心", "发布", "政务", "融媒",
)
_MEDIA_AUTHOR_HINTS = (
    "日报", "晚报", "新闻", "电视台", "广播", "传媒", "客户端", "晨报", "商报", "观察", "网", "报业", "澎湃", "界面", "九派", "红星",
)
_GENERIC_INFO_HINTS = (
    "科普", "知识", "危害", "建议", "提醒", "方法", "为什么", "为何", "怎么办", "健康提示", "戒烟建议", "小知识",
)
_EVENT_ACTION_HINTS = (
    "发布", "出台", "通报", "回应", "处罚", "查处", "启动", "开展", "实施", "生效", "宣布", "引发", "举报", "投诉", "维权", "辟谣",
)
_RISK_FACET_HINTS: Dict[str, tuple[str, ...]] = {
    "complaint": ("投诉", "举报", "反映"),
    "dispute": ("质疑", "争议", "争执", "分歧"),
    "refute": ("辟谣", "不实", "谣言", "误读", "网传"),
    "sanction": ("处罚", "罚款", "查处", "问责"),
    "conflict": ("冲突", "维权", "对立", "矛盾"),
    "spread": ("扩散", "发酵", "爆发", "失控"),
}
_METRIC_SCOPE_ALLOWED = {"volume", "platform", "temporal", "overview"}
_CONTRACT_REGISTRY_SUBDIR = "_report/contracts"
_TOOL_INTENT_ALLOWED = ("overview", "timeline", "actors", "risk", "claim_support", "claim_counter")
_DISPLAY_TO_EVIDENCE_NEED = {
    "传播总览": "overview",
    "传播演化": "timeline",
    "时间线": "timeline",
    "主体立场": "actors",
    "争议焦点": "controversy",
    "风险信号": "risk",
}
_EVIDENCE_NEED_ALIASES = {
    "overview": "overview",
    "传播总览": "overview",
    "timeline": "timeline",
    "传播演化": "timeline",
    "time": "timeline",
    "actors": "actors",
    "主体立场": "actors",
    "actor": "actors",
    "controversy": "controversy",
    "争议焦点": "controversy",
    "claims": "controversy",
    "risk": "risk",
    "风险信号": "risk",
}
_SEMANTIC_ENTITY_CATEGORIES = {"policy", "organization", "event", "concept", "location", "person", "other"}
_SEMANTIC_KEYWORD_RELEVANCE = {"primary", "secondary", "contextual"}
_REPORT_TYPE_ALLOWED = {"propagation", "analysis", "risk", "comprehensive"}
_EVIDENCE_NEED_TO_TOOL_INTENTS = {
    "overview": ["overview"],
    "timeline": ["timeline"],
    "actors": ["actors"],
    "controversy": ["claim_support", "claim_counter"],
    "risk": ["risk"],
}
_EVIDENCE_NEED_TO_DISPLAY = {
    "overview": "传播总览",
    "timeline": "传播演化",
    "actors": "主体立场",
    "controversy": "争议焦点",
    "risk": "风险信号",
}


def _clean_dict(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _safe_parse_json(raw_text: str, fallback: Any) -> Any:
    text = str(raw_text or "").strip()
    if not text:
        return fallback
    try:
        value = json.loads(text)
    except Exception:
        return fallback
    return value


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_key(value: Any) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", _normalize_text(value).lower()).strip("-")
    return text or "item"


def _safe_int(value: Any) -> int:
    """安全转换为整数，处理 None、字符串、浮点数等"""
    if value is None:
        return 0
    try:
        return int(float(str(value or "0").strip()))
    except (ValueError, TypeError):
        return 0


def _unique_strings(values: List[str], *, max_items: int) -> List[str]:
    output: List[str] = []
    seen = set()
    for item in values:
        text = _normalize_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= max_items:
            break
    return output


def _tokenize(text: str, *, max_items: int = 16) -> List[str]:
    """Fallback: 从文本中提取关键词候选（简单过滤句子片段）"""
    output: List[str] = []
    seen = set()
    for token in _TOKEN_RE.findall(str(text or "")):
        if token in seen:
            continue
        # 简单过滤：超过10字符或包含句子片段标记，大概率不是关键词
        if len(token) > 10 or any(marker in token for marker in _SENTENCE_FRAGMENT_MARKERS):
            continue
        seen.add(token)
        output.append(token)
        if len(output) >= max_items:
            break
    return output


def _extract_entities(text: str, *, max_items: int = 10) -> List[str]:
    """Fallback: 从文本中提取实体候选（允许复合名词，过滤句子片段）"""
    output: List[str] = []
    seen = set()
    for token in _TOKEN_RE.findall(str(text or "")):
        if token in seen:
            continue
        # 实体允许更长（复合名词），但仍然过滤句子片段
        if len(token) > 20 or any(marker in token for marker in _SENTENCE_FRAGMENT_MARKERS):
            continue
        seen.add(token)
        output.append(token)
        if len(output) >= max_items:
            break
    return output


def _normalize_evidence_need(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    return _EVIDENCE_NEED_ALIASES.get(text, _EVIDENCE_NEED_ALIASES.get(text.lower(), ""))


def _display_label_for_evidence_need(evidence_need: str, fallback: Any = "") -> str:
    normalized = _normalize_evidence_need(evidence_need)
    if normalized:
        return _EVIDENCE_NEED_TO_DISPLAY.get(normalized, normalized)
    return _normalize_text(fallback)


def _compile_evidence_need_to_tool_intents(evidence_need: str) -> List[str]:
    normalized = _normalize_evidence_need(evidence_need)
    return list(_EVIDENCE_NEED_TO_TOOL_INTENTS.get(normalized, []))


def _normalize_tool_intent(value: Any) -> tuple[str, str]:
    text = _normalize_text(value)
    if not text:
        return "", ""
    if text in _TOOL_INTENT_ALLOWED:
        return text, text
    if text.lower() in _TOOL_INTENT_ALLOWED:
        return text.lower(), text
    mapped_need = _normalize_evidence_need(text)
    if mapped_need and len(_compile_evidence_need_to_tool_intents(mapped_need)) == 1:
        return _compile_evidence_need_to_tool_intents(mapped_need)[0], text
    return "", text


def _extract_date(value: Any) -> str:
    text = str(value or "").strip()
    matched = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    return matched.group(1) if matched else text[:10]


def _proposition_slots(text: str) -> Dict[str, str]:
    cleaned = _normalize_text(text)
    tokens = _tokenize(cleaned, max_items=8)
    subject = tokens[0] if tokens else ""
    predicate = tokens[1] if len(tokens) >= 2 else ""
    obj = tokens[2] if len(tokens) >= 3 else ""
    qualifier = "negative" if any(token in cleaned for token in ("不实", "谣言", "质疑", "冲突", "争议")) else "neutral"
    polarity = "refute" if any(token in cleaned for token in ("辟谣", "不实", "误读")) else "assert"
    return {
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "qualifier": qualifier,
        "polarity": polarity,
    }


def _frame_components(text: str, *, topic: str) -> Dict[str, str]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return {"problem": "", "cause": "", "judgment": "", "remedy": ""}
    problem = cleaned
    cause = "信息解释差异导致争议持续" if any(token in cleaned for token in ("误读", "辟谣", "争议", "冲突")) else f"{topic or '议题'}进入持续讨论阶段"
    judgment = "当前叙事强调治理压力与传播风险" if any(token in cleaned for token in _RISK_HINTS) else "当前叙事更偏向事实界定与回应解释"
    remedy = "补充回应、澄清关键事实并持续监测扩散节点" if any(token in cleaned for token in ("回应", "辟谣", "风险", "争议")) else "持续观察议题属性与主体表达变化"
    return {"problem": problem[:120], "cause": cause[:120], "judgment": judgment[:120], "remedy": remedy[:120]}


def _attribute_labels(text: str) -> List[tuple[str, str]]:
    cleaned = _normalize_text(text)
    labels: List[tuple[str, str]] = []
    for attribute_type, hints in _ATTRIBUTE_HINTS.items():
        if any(token in cleaned for token in hints):
            label = next((token for token in hints if token in cleaned), attribute_type)
            labels.append((attribute_type, label))
    if not labels:
        labels.append(("general", "讨论焦点"))
    return labels[:4]


def _issue_label(text: str, topic: str) -> str:
    cleaned = _normalize_text(text)
    for token in _ISSUE_HINTS:
        if token in cleaned:
            return token
    return topic or "核心议题"


def _evidence_type(card: Dict[str, Any]) -> str:
    author_type = str(card.get("author_type") or "").strip()
    title = _normalize_text(card.get("title"))
    if "官方" in author_type or "政务" in author_type:
        return "official_notice"
    if any(token in title for token in ("截图", "图片")):
        return "screenshot"
    if "转发" in title or "转载" in title:
        return "relay"
    if any(token in str(card.get("platform") or "") for token in ("新闻", "媒体")):
        return "report"
    return "statement"


def _source_type_for_platform(platform: str) -> str:
    text = str(platform or "").strip()
    if not text:
        return "general"
    if any(token in text for token in ("微博", "社交", "论坛")):
        return "social"
    if any(token in text for token in ("新闻", "媒体", "报")):
        return "media"
    if any(token in text for token in ("政务", "官网", "官方")):
        return "official"
    return "general"


def _applied_scope_payload(normalized_task: Dict[str, Any]) -> Dict[str, Any]:
    time_range = normalized_task.get("time_range") if isinstance(normalized_task.get("time_range"), dict) else {}
    return {
        "topic": str(normalized_task.get("topic") or normalized_task.get("topic_identifier") or "").strip(),
        "time_range": {
            "start": str(time_range.get("start") or "").strip(),
            "end": str(time_range.get("end") or "").strip(),
        },
        "platforms": [str(item).strip() for item in (normalized_task.get("platform_scope") or []) if str(item or "").strip()],
        "entities": [str(item).strip() for item in (normalized_task.get("entities") or []) if str(item or "").strip()],
        "report_type": str(normalized_task.get("report_type") or "").strip(),
        "mode": str(normalized_task.get("mode") or "fast").strip() or "fast",
    }


def _coverage_payload(
    *,
    matched_count: int,
    sampled_count: int,
    raw_matched_count: int | None = None,
    deduped_candidate_count: int | None = None,
    returned_card_count: int | None = None,
    source_resolution: str = "",
    resolved_fetch_range: Dict[str, str] | None = None,
    resolved_source_files: List[str] | None = None,
    requested_time_range: Dict[str, str] | None = None,
    effective_time_range: Dict[str, str] | None = None,
    contract_topic_identifier: str = "",
    effective_topic_identifier: str = "",
    contract_mismatch: bool = False,
    platform_counts: Dict[str, int] | None = None,
    date_span: Dict[str, str] | None = None,
    field_gaps: List[str] | None = None,
    missing_sources: List[str] | None = None,
    source_quality_flags: List[str] | None = None,
    readiness_flags: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "matched_count": int(matched_count or 0),
        "sampled_count": int(sampled_count or 0),
        "raw_matched_count": int(raw_matched_count if raw_matched_count is not None else matched_count or 0),
        "deduped_candidate_count": int(deduped_candidate_count if deduped_candidate_count is not None else matched_count or 0),
        "returned_card_count": int(returned_card_count if returned_card_count is not None else sampled_count or 0),
        "platform_counts": dict(platform_counts or {}),
        "date_span": dict(date_span or {}),
        "source_resolution": str(source_resolution or "").strip(),
        "resolved_fetch_range": dict(resolved_fetch_range or {}),
        "resolved_source_files": list(resolved_source_files or []),
        "requested_time_range": dict(requested_time_range or {}),
        "effective_time_range": dict(effective_time_range or {}),
        "contract_topic_identifier": str(contract_topic_identifier or "").strip(),
        "effective_topic_identifier": str(effective_topic_identifier or "").strip(),
        "contract_mismatch": bool(contract_mismatch),
        "field_gaps": list(field_gaps or []),
        "missing_sources": list(missing_sources or []),
        "source_quality_flags": list(source_quality_flags or []),
        "readiness_flags": list(readiness_flags or []),
    }


def _trace_payload(
    items: List[Dict[str, Any]],
    *,
    offset: int,
    total: int,
    retrieval_strategy: str = "",
    rewrite_queries: List[str] | None = None,
    compression_applied: bool = False,
    contract_id: str = "",
    derivation_id: str = "",
    requested_scope: Dict[str, Any] | None = None,
    effective_scope: Dict[str, Any] | None = None,
    display_label: str = "",
    evidence_need: str = "",
    compiled_tool_intents: List[str] | None = None,
    requested_intent: str = "",
    allowed_intents: List[str] | None = None,
    rerank_policy: str = "",
    dominant_signals: List[str] | None = None,
) -> Dict[str, Any]:
    next_cursor = str(offset + len(items)) if offset + len(items) < max(total, 0) else ""
    return {
        "source_ids": [str(item.get("source_id") or "").strip() for item in items if str(item.get("source_id") or "").strip()],
        "dedupe_keys": [str(item.get("dedupe_key") or "").strip() for item in items if str(item.get("dedupe_key") or "").strip()],
        "truncated": bool(next_cursor),
        "next_cursor": next_cursor,
        "retrieval_strategy": str(retrieval_strategy or "").strip(),
        "rewrite_queries": list(rewrite_queries or []),
        "compression_applied": bool(compression_applied),
        "contract_id": str(contract_id or "").strip(),
        "derivation_id": str(derivation_id or "").strip(),
        "requested_scope": dict(requested_scope or {}),
        "effective_scope": dict(effective_scope or {}),
        "display_label": str(display_label or "").strip(),
        "evidence_need": str(evidence_need or "").strip(),
        "compiled_tool_intents": [str(item).strip() for item in (compiled_tool_intents or []) if str(item or "").strip()],
        "requested_intent": str(requested_intent or "").strip(),
        "allowed_intents": [str(item).strip() for item in (allowed_intents or []) if str(item or "").strip()],
        "rerank_policy": str(rerank_policy or "").strip(),
        "dominant_signals": [str(item).strip() for item in (dominant_signals or []) if str(item or "").strip()],
    }


def _base_result(
    *,
    normalized_task: Dict[str, Any],
    tool_name: str,
    coverage: Dict[str, Any] | None = None,
    counterevidence: List[Dict[str, Any]] | None = None,
    confidence: float = 0.0,
    trace: Dict[str, Any] | None = None,
    error_hint: str | None = None,
) -> Dict[str, Any]:
    return {
        "schema_version": V2_SCHEMA_VERSION,
        "tool_name": tool_name,
        "generated_at": _utc_now(),
        "applied_scope": _applied_scope_payload(normalized_task),
        "coverage": coverage or _coverage_payload(matched_count=0, sampled_count=0),
        "counterevidence": list(counterevidence or []),
        "confidence": round(float(confidence or 0.0), 4),
        "trace": trace
        or {
            "source_ids": [],
            "dedupe_keys": [],
            "truncated": False,
            "next_cursor": "",
            "retrieval_strategy": "",
            "rewrite_queries": [],
            "compression_applied": False,
            "display_label": "",
            "evidence_need": "",
            "compiled_tool_intents": [],
            "requested_intent": "",
            "allowed_intents": [],
            "rerank_policy": "",
            "dominant_signals": [],
        },
        "error_hint": str(error_hint or "").strip() or None,
    }


def _capability_result(
    *,
    tool_name: str,
    generated_at: str,
    payload_key: str,
    result: Dict[str, Any],
    error_hint: str | None = None,
) -> Dict[str, Any]:
    trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
    return {
        "schema_version": V2_SCHEMA_VERSION,
        "tool_name": tool_name,
        "generated_at": generated_at,
        payload_key: result,
        "result": result,
        "trace": trace,
        "error_hint": str(error_hint or "").strip() or None,
    }


def _load_normalized_task(normalized_task_json: str) -> Dict[str, Any]:
    payload = _clean_dict(normalized_task_json)
    task_contract = payload.get("task_contract") if isinstance(payload.get("task_contract"), dict) else {}
    task_derivation = payload.get("task_derivation") if isinstance(payload.get("task_derivation"), dict) else {}
    if task_contract and task_derivation and not isinstance(payload.get("normalized_task"), dict):
        payload["normalized_task"] = _build_normalized_task_view(task_contract, task_derivation)
    if isinstance(payload.get("normalized_task"), dict):
        payload = dict(payload.get("normalized_task") or {})
    time_range = payload.get("time_range") if isinstance(payload.get("time_range"), dict) else {}
    payload["time_range"] = {
        "start": str(time_range.get("start") or payload.get("start") or "").strip(),
        "end": str(time_range.get("end") or payload.get("end") or payload.get("start") or "").strip(),
    }
    payload["topic_identifier"] = str(payload.get("topic_identifier") or "").strip()
    payload["topic"] = str(payload.get("topic") or payload.get("topic_identifier") or "").strip()
    payload["mode"] = str(payload.get("mode") or "fast").strip().lower() or "fast"
    payload["task_contract"] = payload.get("task_contract") if isinstance(payload.get("task_contract"), dict) else {}
    for key in (
        "platform_scope",
        "mandatory_sections",
        "risk_policy",
        "analysis_question_set",
        "coverage_expectation",
        "inference_policy",
        "contract_overrides_applied",
    ):
        payload[key] = [str(item).strip() for item in (payload.get(key) or []) if str(item or "").strip()]
    payload["entities"] = _extract_semantic_entity_names(payload.get("entities") or [])
    payload["keywords"] = _extract_semantic_keyword_terms(payload.get("keywords") or [])
    attempted_overrides = payload.get("attempted_overrides") if isinstance(payload.get("attempted_overrides"), dict) else {}
    payload["attempted_overrides"] = {str(key).strip(): str(value).strip() for key, value in attempted_overrides.items() if str(key or "").strip()}
    topic_aliases = payload.get("topic_aliases") if isinstance(payload.get("topic_aliases"), list) else []
    payload["topic_aliases"] = [str(item).strip() for item in topic_aliases if str(item or "").strip()]
    return payload


def _task_contract_from_hints(hints: Dict[str, Any]) -> Dict[str, str]:
    contract = hints.get("task_contract") if isinstance(hints.get("task_contract"), dict) else {}
    return {
        "topic_identifier": str(contract.get("topic_identifier") or "").strip(),
        "topic_label": str(contract.get("topic_label") or "").strip(),
        "start": str(contract.get("start") or "").strip(),
        "end": str(contract.get("end") or "").strip(),
        "mode": str(contract.get("mode") or "").strip().lower(),
        "thread_id": str(contract.get("thread_id") or "").strip(),
    }


def _build_task_contract(*, topic_identifier: str, topic_label: str, start: str, end: str, mode: str, thread_id: str) -> Dict[str, str]:
    safe_start = str(start or "").strip()
    safe_end = str(end or safe_start).strip()
    safe_topic_identifier = str(topic_identifier or "").strip()
    return {
        "contract_id": f"{safe_topic_identifier}:{safe_start}:{safe_end}",
        "topic_identifier": safe_topic_identifier,
        "topic_label": str(topic_label or safe_topic_identifier).strip(),
        "start": safe_start,
        "end": safe_end,
        "mode": str(mode or "fast").strip().lower() or "fast",
        "thread_id": str(thread_id or "").strip(),
    }


def _coerce_topic_label_payload(topic_label: Any, *, fallback: str = "", full_description_fallback: str = "") -> Dict[str, str]:
    if isinstance(topic_label, dict):
        label = str(topic_label.get("label") or fallback).strip()
        full_description = str(topic_label.get("full_description") or full_description_fallback).strip()
    else:
        label = str(topic_label or fallback).strip()
        full_description = str(full_description_fallback or "").strip()
    label = label[:30] if label else str(fallback or "")[:30].strip()
    return {
        "label": label or "待确定",
        "full_description": full_description[:200],
    }


def _coerce_semantic_entity_list(values: Any) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    for item in (values or []):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            category = str(item.get("category") or "other").strip().lower() or "other"
        else:
            name = str(item or "").strip()
            category = "other"
        if not name:
            continue
        output.append(
            {
                "name": name,
                "category": category if category in _SEMANTIC_ENTITY_CATEGORIES else "other",
            }
        )
    return output


def _coerce_semantic_keyword_list(values: Any) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    for item in (values or []):
        if isinstance(item, dict):
            term = str(item.get("term") or "").strip()
            relevance = str(item.get("relevance") or "primary").strip().lower() or "primary"
        else:
            term = str(item or "").strip()
            relevance = "primary"
        if not term:
            continue
        output.append(
            {
                "term": term,
                "relevance": relevance if relevance in _SEMANTIC_KEYWORD_RELEVANCE else "primary",
            }
        )
    return output


def _extract_semantic_entity_names(values: Any) -> List[str]:
    return [str(item.get("name") or "").strip() for item in _coerce_semantic_entity_list(values) if str(item.get("name") or "").strip()]


def _extract_semantic_keyword_terms(values: Any) -> List[str]:
    return [str(item.get("term") or "").strip() for item in _coerce_semantic_keyword_list(values) if str(item.get("term") or "").strip()]


def _build_normalized_task_view(task_contract: Dict[str, Any], task_derivation: Dict[str, Any]) -> Dict[str, Any]:
    contract = task_contract if isinstance(task_contract, dict) else {}
    derivation = task_derivation if isinstance(task_derivation, dict) else {}
    start = str(contract.get("start") or "").strip()
    end = str(contract.get("end") or start).strip()
    topic_identifier = str(contract.get("topic_identifier") or "").strip()
    attempted_overrides = derivation.get("attempted_overrides") if isinstance(derivation.get("attempted_overrides"), dict) else {}
    entity_names = _extract_semantic_entity_names(derivation.get("entities") or [])
    keyword_terms = _extract_semantic_keyword_terms(derivation.get("keywords") or [])
    return {
        "task_id": f"{topic_identifier}:{start}:{end or start}",
        "topic": str(derivation.get("topic") or contract.get("topic_label") or topic_identifier).strip(),
        "topic_identifier": topic_identifier,
        "topic_label": str(contract.get("topic_label") or "").strip(),
        "contract_id": str(contract.get("contract_id") or f"{topic_identifier}:{start}:{end}").strip(),
        "task_contract": {
            "contract_id": str(contract.get("contract_id") or f"{topic_identifier}:{start}:{end}").strip(),
            "topic_identifier": topic_identifier,
            "topic_label": str(contract.get("topic_label") or "").strip(),
            "start": start,
            "end": end,
            "mode": str(contract.get("mode") or "fast").strip().lower() or "fast",
            "thread_id": str(contract.get("thread_id") or "").strip(),
        },
        "entities": entity_names,
        "keywords": keyword_terms,
        "time_range": {"start": start, "end": end},
        "platform_scope": [str(item).strip() for item in (derivation.get("platform_scope") or []) if str(item or "").strip()],
        "report_type": str(derivation.get("report_type") or "analysis").strip() or "analysis",
        "mandatory_sections": [str(item).strip() for item in (derivation.get("mandatory_sections") or []) if str(item or "").strip()],
        "risk_policy": [str(item).strip() for item in (derivation.get("risk_policy") or []) if str(item or "").strip()],
        "mode": str(contract.get("mode") or "fast").strip().lower() or "fast",
        "analysis_question_set": [str(item).strip() for item in (derivation.get("analysis_question_set") or []) if str(item or "").strip()],
        "coverage_expectation": [str(item).strip() for item in (derivation.get("coverage_expectation") or []) if str(item or "").strip()],
        "inference_policy": [str(item).strip() for item in (derivation.get("inference_policy") or []) if str(item or "").strip()],
        "topic_aliases": [str(item).strip() for item in (derivation.get("topic_aliases") or []) if str(item or "").strip()],
        "attempted_overrides": {str(key).strip(): str(value).strip() for key, value in attempted_overrides.items() if str(key or "").strip()},
        "contract_overrides_applied": [str(item).strip() for item in (derivation.get("contract_overrides_applied") or []) if str(item or "").strip()],
    }


def _load_task_contract_payload(task_contract_json: str) -> Dict[str, Any]:
    payload = _clean_dict(task_contract_json)
    if isinstance(payload.get("task_contract"), dict):
        payload = dict(payload.get("task_contract") or {})
    topic_identifier = str(payload.get("topic_identifier") or "").strip()
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or start).strip()
    if not topic_identifier or not start:
        return {}
    return {
        "contract_id": str(payload.get("contract_id") or f"{topic_identifier}:{start}:{end}").strip(),
        "topic_identifier": topic_identifier,
        "topic_label": str(payload.get("topic_label") or topic_identifier).strip(),
        "start": start,
        "end": end,
        "mode": str(payload.get("mode") or "fast").strip().lower() or "fast",
        "thread_id": str(payload.get("thread_id") or "").strip(),
    }


def _load_task_derivation_payload(task_derivation_json: str) -> Dict[str, Any]:
    payload = _clean_dict(task_derivation_json)
    if isinstance(payload.get("task_derivation"), dict):
        payload = dict(payload.get("task_derivation") or {})
    topic_identifier = str(payload.get("topic_identifier") or "").strip()
    topic = str(payload.get("topic") or "").strip()
    return {
        "derivation_id": str(payload.get("derivation_id") or "").strip(),
        "topic": topic,
        "topic_identifier": topic_identifier,
        "topic_label": _coerce_topic_label_payload(
            payload.get("topic_label"),
            fallback=topic or topic_identifier,
            full_description_fallback=topic,
        ),
        "topic_aliases": [str(item).strip() for item in (payload.get("topic_aliases") or []) if str(item or "").strip()],
        "entities": _coerce_semantic_entity_list(payload.get("entities") or []),
        "keywords": _coerce_semantic_keyword_list(payload.get("keywords") or []),
        "platform_scope": [str(item).strip() for item in (payload.get("platform_scope") or []) if str(item or "").strip()],
        "report_type": (
            str(payload.get("report_type") or "analysis").strip().lower()
            if str(payload.get("report_type") or "").strip().lower() in _REPORT_TYPE_ALLOWED
            else "analysis"
        ),
        "mandatory_sections": [str(item).strip() for item in (payload.get("mandatory_sections") or []) if str(item or "").strip()],
        "risk_policy": [str(item).strip() for item in (payload.get("risk_policy") or []) if str(item or "").strip()],
        "analysis_question_set": [str(item).strip() for item in (payload.get("analysis_question_set") or []) if str(item or "").strip()],
        "coverage_expectation": [str(item).strip() for item in (payload.get("coverage_expectation") or []) if str(item or "").strip()],
        "inference_policy": [str(item).strip() for item in (payload.get("inference_policy") or []) if str(item or "").strip()],
        "attempted_overrides": {
            str(key).strip(): str(value).strip()
            for key, value in ((payload.get("attempted_overrides") or {}) if isinstance(payload.get("attempted_overrides"), dict) else {}).items()
            if str(key or "").strip()
        },
        "contract_overrides_applied": [str(item).strip() for item in (payload.get("contract_overrides_applied") or []) if str(item or "").strip()],
    }


def _contract_registry_dir() -> Path:
    return get_data_root() / _CONTRACT_REGISTRY_SUBDIR


def _contract_registry_path(contract_id: str) -> Path:
    digest = hashlib.sha1(str(contract_id or "").strip().encode("utf-8")).hexdigest()
    return _contract_registry_dir() / f"{digest}.json"


def persist_task_contract_bundle(
    *,
    task_contract: Dict[str, Any],
    task_derivation: Dict[str, Any] | None = None,
    proposal_snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    contract = _load_task_contract_payload(json.dumps(task_contract or {}, ensure_ascii=False))
    if not contract:
        return {}
    derivation = _load_task_derivation_payload(json.dumps(task_derivation or {}, ensure_ascii=False))
    path = _contract_registry_path(contract.get("contract_id") or "")
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}
    existing_contract = existing.get("task_contract") if isinstance(existing.get("task_contract"), dict) else {}
    if existing_contract:
        current_authority = {
            "topic_identifier": str(existing_contract.get("topic_identifier") or "").strip(),
            "start": str(existing_contract.get("start") or "").strip(),
            "end": str(existing_contract.get("end") or "").strip(),
            "mode": str(existing_contract.get("mode") or "").strip(),
        }
        incoming_authority = {
            "topic_identifier": str(contract.get("topic_identifier") or "").strip(),
            "start": str(contract.get("start") or "").strip(),
            "end": str(contract.get("end") or "").strip(),
            "mode": str(contract.get("mode") or "").strip(),
        }
        if current_authority != incoming_authority:
            contract = existing_contract
    derivation_history = existing.get("task_derivations") if isinstance(existing.get("task_derivations"), list) else []
    derivation_entries = [dict(item) for item in derivation_history if isinstance(item, dict)]
    if derivation:
        derivation_id = str(derivation.get("derivation_id") or "").strip()
        derivation_entries = [item for item in derivation_entries if str(item.get("derivation_id") or "").strip() != derivation_id]
        derivation_entries.append(derivation)
    bundle = {
        "task_contract": contract,
        "task_derivation": derivation,
        "task_derivations": derivation_entries,
        "proposal_snapshot": proposal_snapshot if isinstance(proposal_snapshot, dict) else {},
        "updated_at": _utc_now(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=2)
    return bundle


def _load_task_contract_bundle(contract_id: str) -> Dict[str, Any]:
    raw_contract_id = str(contract_id or "").strip()
    if not raw_contract_id:
        return {}
    path = _contract_registry_path(raw_contract_id)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    task_contract = _load_task_contract_payload(json.dumps(payload.get("task_contract") or {}, ensure_ascii=False))
    task_derivation = _load_task_derivation_payload(json.dumps(payload.get("task_derivation") or {}, ensure_ascii=False))
    task_derivations = [dict(item) for item in (payload.get("task_derivations") or []) if isinstance(item, dict)]
    proposal_snapshot = payload.get("proposal_snapshot") if isinstance(payload.get("proposal_snapshot"), dict) else {}
    if not task_contract:
        return {}
    if not task_derivation and task_derivations:
        latest = task_derivations[-1]
        task_derivation = _load_task_derivation_payload(json.dumps(latest, ensure_ascii=False))
    return {
        "task_contract": task_contract,
        "task_derivation": task_derivation,
        "task_derivations": task_derivations,
        "proposal_snapshot": proposal_snapshot,
    }


def _resolve_scope_within_contract(task_contract: Dict[str, Any], retrieval_scope_json: str) -> Dict[str, Any]:
    contract = task_contract if isinstance(task_contract, dict) else {}
    contract_start = str(contract.get("start") or "").strip()
    contract_end = str(contract.get("end") or contract_start).strip()
    scope = _clean_dict(retrieval_scope_json)
    policy = str(scope.get("policy") or scope.get("time_mode") or "contract_default").strip() or "contract_default"
    requested_start = str(scope.get("start") or "").strip()
    requested_end = str(scope.get("end") or requested_start).strip()
    if policy in {"contract_default", "default"} or not requested_start:
        return {
            "policy": "contract_default",
            "requested_time_range": {"start": contract_start, "end": contract_end},
            "effective_time_range": {"start": contract_start, "end": contract_end},
            "scope_flags": [],
        }
    effective_start = requested_start or contract_start
    effective_end = requested_end or effective_start or contract_end
    scope_flags: List[str] = []
    if contract_start and effective_start < contract_start:
        effective_start = contract_start
        scope_flags.append("scope_clipped_to_contract")
    if contract_end and effective_end > contract_end:
        effective_end = contract_end
        if "scope_clipped_to_contract" not in scope_flags:
            scope_flags.append("scope_clipped_to_contract")
    if effective_start and effective_end and effective_start > effective_end:
        effective_start = contract_start
        effective_end = contract_end
        scope_flags.append("scope_policy_violation")
    return {
        "policy": "within_contract",
        "requested_time_range": {"start": requested_start or contract_start, "end": requested_end or requested_start or contract_end},
        "effective_time_range": {"start": effective_start or contract_start, "end": effective_end or contract_end},
        "scope_flags": scope_flags,
    }


def _resolve_task_execution_view(
    *,
    contract_id: str = "",
    normalized_task_json: str = "",
    task_contract_json: str = "",
    task_derivation_json: str = "",
    retrieval_scope_json: str = "{}",
) -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json) if str(normalized_task_json or "").strip() else {}
    # 优先从 normalized_task.task_contract.contract_id 或显式 contract_id 参数获取
    normalized_contract_id = str(((normalized_task.get("task_contract") or {}).get("contract_id") or contract_id or "").strip())
    contract_bundle = _load_task_contract_bundle(normalized_contract_id) if normalized_contract_id else {}
    legacy_input_kind: List[str] = []
    if str(normalized_task_json or "").strip():
        legacy_input_kind.append("normalized_task_json")
    if str(task_contract_json or "").strip():
        legacy_input_kind.append("task_contract_json")
    if str(task_derivation_json or "").strip():
        legacy_input_kind.append("task_derivation_json")
    task_contract = contract_bundle.get("task_contract") if isinstance(contract_bundle.get("task_contract"), dict) else _load_task_contract_payload(task_contract_json)
    task_derivation = contract_bundle.get("task_derivation") if isinstance(contract_bundle.get("task_derivation"), dict) else _load_task_derivation_payload(task_derivation_json)
    # 优先从 normalized_task.task_contract 加载（携带正确的 contract_id）
    if not task_contract and isinstance(normalized_task.get("task_contract"), dict):
        task_contract = _load_task_contract_payload(json.dumps(normalized_task.get("task_contract") or {}, ensure_ascii=False))
    if not task_derivation and isinstance(normalized_task.get("task_derivation"), dict):
        task_derivation = _load_task_derivation_payload(json.dumps(normalized_task.get("task_derivation") or {}, ensure_ascii=False))
    # 如果仍未找到 task_contract，从 normalized_task 直接构建（确保 contract_id 来自 normalized_task）
    if not task_contract and normalized_contract_id:
        topic_identifier = str(normalized_task.get("topic_identifier") or "").strip()
        start = str(((normalized_task.get("time_range") or {}).get("start") or "").strip())
        end = str(((normalized_task.get("time_range") or {}).get("end") or start).strip())
        if topic_identifier and start:
            task_contract = {
                "contract_id": normalized_contract_id,
                "topic_identifier": topic_identifier,
                "topic_label": str(normalized_task.get("topic") or topic_identifier).strip(),
                "start": start,
                "end": end,
                "mode": str(normalized_task.get("mode") or "fast").strip().lower() or "fast",
                "thread_id": "",
            }
    if not task_derivation:
        task_derivation = {
            "derivation_id": str(normalized_task.get("derivation_id") or "").strip(),
            "topic": str(normalized_task.get("topic") or "").strip(),
            "topic_aliases": [str(item).strip() for item in (normalized_task.get("topic_aliases") or []) if str(item or "").strip()],
            "entities": [str(item).strip() for item in (normalized_task.get("entities") or []) if str(item or "").strip()],
            "keywords": [str(item).strip() for item in (normalized_task.get("keywords") or []) if str(item or "").strip()],
            "platform_scope": [str(item).strip() for item in (normalized_task.get("platform_scope") or []) if str(item or "").strip()],
            "report_type": str(normalized_task.get("report_type") or "analysis").strip() or "analysis",
            "mandatory_sections": [str(item).strip() for item in (normalized_task.get("mandatory_sections") or []) if str(item or "").strip()],
            "risk_policy": [str(item).strip() for item in (normalized_task.get("risk_policy") or []) if str(item or "").strip()],
            "analysis_question_set": [str(item).strip() for item in (normalized_task.get("analysis_question_set") or []) if str(item or "").strip()],
            "coverage_expectation": [str(item).strip() for item in (normalized_task.get("coverage_expectation") or []) if str(item or "").strip()],
            "inference_policy": [str(item).strip() for item in (normalized_task.get("inference_policy") or []) if str(item or "").strip()],
            "attempted_overrides": {
                str(key).strip(): str(value).strip()
                for key, value in ((normalized_task.get("attempted_overrides") or {}) if isinstance(normalized_task.get("attempted_overrides"), dict) else {}).items()
                if str(key or "").strip()
            },
            "contract_overrides_applied": [str(item).strip() for item in (normalized_task.get("contract_overrides_applied") or []) if str(item or "").strip()],
        }
    if task_contract and task_derivation:
        execution_task = _build_normalized_task_view(task_contract, task_derivation)
    else:
        execution_task = dict(normalized_task or {})
    contract_binding_failed = not bool(task_contract)
    scope_meta = _resolve_scope_within_contract(task_contract, retrieval_scope_json) if task_contract else {
        "policy": "contract_default",
        "requested_time_range": dict((execution_task.get("time_range") or {})) if isinstance(execution_task.get("time_range"), dict) else {},
        "effective_time_range": dict((execution_task.get("time_range") or {})) if isinstance(execution_task.get("time_range"), dict) else {},
        "scope_flags": [],
    }
    if isinstance(execution_task.get("time_range"), dict):
        execution_task["time_range"] = dict(scope_meta.get("effective_time_range") or execution_task.get("time_range") or {})
    proposal_snapshot = contract_bundle.get("proposal_snapshot") if isinstance(contract_bundle.get("proposal_snapshot"), dict) else {}
    requested_execution_fields = proposal_snapshot.get("requested_execution_fields") if isinstance(proposal_snapshot.get("requested_execution_fields"), dict) else {}
    # requested_execution_fields 仅用于审计追踪（记录 AI 提议值），实际执行必须使用 contract_value
    if not requested_execution_fields and normalized_task:
        requested_execution_fields = {
            "topic_identifier": str(normalized_task.get("topic_identifier") or "").strip(),
            "start": str(((normalized_task.get("time_range") or {}).get("start")) or "").strip(),
            "end": str(((normalized_task.get("time_range") or {}).get("end")) or "").strip(),
            "mode": str(normalized_task.get("mode") or "").strip(),
        }
    contract_value = {
        "contract_id": str((task_contract or {}).get("contract_id") or contract_id or "").strip(),
        "topic_identifier": str((task_contract or {}).get("topic_identifier") or "").strip(),
        "start": str((task_contract or {}).get("start") or "").strip(),
        "end": str((task_contract or {}).get("end") or "").strip(),
        "mode": str((task_contract or {}).get("mode") or "").strip(),
    }
    # 检测 AI 提议值与契约值的差异，用于诊断和告警
    validation_warnings: List[str] = []
    if requested_execution_fields:
        ai_topic = str(requested_execution_fields.get("topic_identifier") or "").strip()
        contract_topic = str(contract_value.get("topic_identifier") or "").strip()
        if ai_topic and contract_topic and ai_topic != contract_topic:
            validation_warnings.append(f"AI提议topic_identifier '{ai_topic}' 与契约值 '{contract_topic}' 不一致")
        ai_start = str(requested_execution_fields.get("start") or "").strip()
        contract_start = str(contract_value.get("start") or "").strip()
        if ai_start and contract_start and ai_start != contract_start:
            validation_warnings.append(f"AI提议start '{ai_start}' 与契约值 '{contract_start}' 不一致")
        ai_end = str(requested_execution_fields.get("end") or "").strip()
        contract_end = str(contract_value.get("end") or "").strip()
        if ai_end and contract_end and ai_end != contract_end:
            validation_warnings.append(f"AI提议end '{ai_end}' 与契约值 '{contract_end}' 不一致")
    effective_value = {
        "contract_id": str((task_contract or {}).get("contract_id") or contract_id or "").strip(),
        "topic_identifier": str((execution_task.get("topic_identifier") or (task_contract or {}).get("topic_identifier") or "").strip()),
        "start": str(((scope_meta.get("effective_time_range") or {}).get("start") or "").strip()),
        "end": str(((scope_meta.get("effective_time_range") or {}).get("end") or "").strip()),
        "mode": str((execution_task.get("mode") or (task_contract or {}).get("mode") or "").strip()),
    }
    # 确保 effective_value 使用契约值作为权威来源
    if contract_value.get("topic_identifier"):
        effective_value["topic_identifier"] = contract_value["topic_identifier"]
    if contract_value.get("contract_id"):
        effective_value["contract_id"] = contract_value["contract_id"]
    return {
        "contract_id": str((task_contract or {}).get("contract_id") or contract_id or "").strip(),
        "task_contract": task_contract,
        "task_derivation": task_derivation,
        "proposal_snapshot": proposal_snapshot,
        "normalized_task": execution_task,
        "scope_meta": scope_meta,
        "legacy_adapter_hit": bool(legacy_input_kind),
        "legacy_input_kind": legacy_input_kind,
        "contract_binding_failed": contract_binding_failed,
        "violation_origin": "payload_adapter" if legacy_input_kind else "",
        "repair_action": "mapped_legacy_fields" if legacy_input_kind else "none",
        "contract_value": contract_value,
        "agent_proposed_value": requested_execution_fields,
        "effective_value": effective_value,
        "validation_warnings": validation_warnings,
        "_audit_note": "agent_proposed_value 仅用于审计追踪，实际执行请使用 contract_value 或 effective_value",
    }


def get_basic_analysis_snapshot_payload(*, topic_identifier: str, start: str, end: str, topic_label: str = "") -> Dict[str, Any]:
    snapshot = collect_basic_analysis_snapshot(
        str(topic_identifier or "").strip(),
        str(start or "").strip(),
        str(end or "").strip() or str(start or "").strip(),
        topic_label=str(topic_label or "").strip(),
    )
    return _capability_result(
        tool_name="get_basic_analysis_snapshot",
        generated_at=_utc_now(),
        payload_key="snapshot",
        result=snapshot,
        error_hint=None,
    )


def build_basic_analysis_insight_payload(*, snapshot_json: str) -> Dict[str, Any]:
    raw = _clean_dict(snapshot_json)
    snapshot = raw.get("snapshot") if isinstance(raw.get("snapshot"), dict) else raw.get("result") if isinstance(raw.get("result"), dict) else raw
    insight = build_basic_analysis_insight(snapshot if isinstance(snapshot, dict) else {})
    return _capability_result(
        tool_name="build_basic_analysis_insight",
        generated_at=_utc_now(),
        payload_key="insight",
        result=insight,
        error_hint=None,
    )


def get_bertopic_snapshot_payload(*, topic_identifier: str, start: str, end: str, topic_label: str = "") -> Dict[str, Any]:
    snapshot = collect_bertopic_snapshot(
        str(topic_identifier or "").strip(),
        str(start or "").strip(),
        str(end or "").strip() or str(start or "").strip(),
        topic_label=str(topic_label or "").strip(),
    )
    return _capability_result(
        tool_name="get_bertopic_snapshot",
        generated_at=_utc_now(),
        payload_key="snapshot",
        result=snapshot,
        error_hint=None,
    )


def build_bertopic_insight_payload(*, snapshot_json: str) -> Dict[str, Any]:
    raw = _clean_dict(snapshot_json)
    snapshot = raw.get("snapshot") if isinstance(raw.get("snapshot"), dict) else raw.get("result") if isinstance(raw.get("result"), dict) else raw
    insight = build_bertopic_insight(snapshot if isinstance(snapshot, dict) else {})
    return _capability_result(
        tool_name="build_bertopic_insight",
        generated_at=_utc_now(),
        payload_key="insight",
        result=insight,
        error_hint=None,
    )


def _card_stance_hint(title: str, snippet: str) -> str:
    text = f"{title} {snippet}"
    if any(hint in text for hint in _STANCE_REFUTE_HINTS):
        return "refute"
    if any(hint in text for hint in ("回应", "表态", "发布")):
        return "official_signal"
    if any(hint in text for hint in ("质疑", "担忧", "投诉")):
        return "concern"
    return "neutral"


def _card_claimability(title: str, snippet: str) -> List[str]:
    text = f"{title} {snippet}"
    output: List[str] = []
    for label, hints in _CLAIMABILITY_RULES.items():
        if any(hint in text for hint in hints):
            output.append(label)
    return output or ["time_fact"]


def _strip_title_prefix(text: str) -> str:
    return re.sub(r"^\s*title:\s*", "", str(text or "").strip(), flags=re.IGNORECASE).strip()


def _normalize_compact_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip()).lower()


def _content_quality_hint(title: str, raw_contents: str) -> str:
    title_key = _normalize_compact_text(title)
    contents_key = _normalize_compact_text(_strip_title_prefix(raw_contents))
    if title_key and contents_key and title_key == contents_key:
        return "title_echo"
    return "short_excerpt"


def _effective_text_payload(title: str, raw_contents: str, content_quality_hint: str) -> str:
    stripped = _strip_title_prefix(raw_contents)
    if stripped and content_quality_hint != "title_echo":
        return stripped
    return str(title or "").strip()


def _is_placeholder_author(author: str) -> bool:
    text = str(author or "").strip()
    if not text or text in {"-", "未知", "null", "None"}:
        return True
    lowered = text.lower()
    return lowered.startswith("user") or text.startswith("用户") or bool(re.fullmatch(r"\d{6,}", text))


def _infer_official_source_hint(author: str, title: str, effective_text: str, platform: str) -> str:
    author_text = str(author or "").strip()
    label_haystack = f"{author_text} {title}".strip()
    if any(hint in label_haystack for hint in _OFFICIAL_AUTHOR_HINTS):
        return "official_like"
    if platform == "新闻" or any(hint in label_haystack for hint in _MEDIA_AUTHOR_HINTS):
        return "media_like"
    if _is_placeholder_author(author_text):
        return "unknown"
    return "public_like"


def _infer_source_kind_hint(author: str, platform: str, official_source_hint: str) -> str:
    if official_source_hint == "official_like":
        return "official_account"
    if official_source_hint == "media_like":
        return "news_media"
    if _is_placeholder_author(author):
        return "anonymous_account"
    return {
        "微博": "social_account",
        "视频": "video_account",
        "论坛": "forum_user",
        "自媒体号": "self_media_account",
    }.get(str(platform or "").strip(), "named_account")


def _eventness_score(title: str, effective_text: str, published_at: str, official_source_hint: str) -> float:
    haystack = f"{title} {effective_text}"
    score = 0.12
    if str(published_at or "").strip():
        score += 0.16
    if any(hint in haystack for hint in _EVENT_ACTION_HINTS):
        score += 0.34
    if official_source_hint in {"official_like", "media_like"}:
        score += 0.12
    if any(hint in haystack for hint in _GENERIC_INFO_HINTS):
        score -= 0.24
    return round(min(1.0, max(0.0, score)), 4)


def _actor_salience_score(
    author: str,
    title: str,
    effective_text: str,
    official_source_hint: str,
    matched_terms: List[str],
    published_at: str,
) -> float:
    score = 0.08
    if not _is_placeholder_author(author):
        score += 0.22
    if official_source_hint == "official_like":
        score += 0.28
    elif official_source_hint == "media_like":
        score += 0.18
    if any(hint in f"{title} {effective_text}" for hint in ("回应", "表态", "发布", "通报")):
        score += 0.2
    if len([term for term in matched_terms if str(term or "").strip()]) >= 2:
        score += 0.08
    if str(published_at or "").strip():
        score += 0.06
    return round(min(1.0, max(0.0, score)), 4)


def _risk_facets(title: str, effective_text: str, author: str) -> List[str]:
    haystack = f"{title} {effective_text} {author}".strip()
    facets = [facet for facet, hints in _RISK_FACET_HINTS.items() if any(hint in haystack for hint in hints)]
    return _unique_strings(facets, max_items=6)


def _contradiction_signal(title: str, effective_text: str, raw_polarity: str, risk_facets: List[str]) -> float:
    score = 0.18
    if "refute" in risk_facets:
        score += 0.48
    if str(raw_polarity or "").strip() == "负面" and any(facet in risk_facets for facet in ("dispute", "conflict")):
        score += 0.12
    return round(min(0.92, max(0.0, score)), 4)


def _risk_salience_score(
    title: str,
    effective_text: str,
    raw_polarity: str,
    risk_facets: List[str],
    contradiction_signal: float,
    eventness_score: float,
) -> float:
    haystack = f"{title} {effective_text}"
    score = 0.06 + min(0.52, len(risk_facets) * 0.13)
    if str(raw_polarity or "").strip() == "负面":
        score += 0.16
    if contradiction_signal >= 0.65:
        score += 0.14
    if eventness_score >= 0.45:
        score += 0.08
    if any(hint in haystack for hint in _GENERIC_INFO_HINTS) and not risk_facets:
        score -= 0.24
    return round(min(1.0, max(0.0, score)), 4)


def _candidate_semantic_profile(item: Dict[str, Any], normalized_task: Dict[str, Any]) -> Dict[str, Any]:
    title = _normalize_text(item.get("title"))
    raw_contents = str(item.get("contents") or item.get("content") or "").strip()
    author = str(item.get("author") or "").strip()
    platform = str(item.get("platform") or "").strip()
    published_at = str(item.get("published_at") or "").strip()
    matched_terms = [str(term).strip() for term in (item.get("matched_terms") or []) if str(term or "").strip()]
    raw_polarity = str(item.get("polarity") or item.get("sentiment_raw") or "").strip()
    content_quality_hint = str(item.get("content_quality_hint") or "").strip() or _content_quality_hint(title, raw_contents)
    effective_text = _effective_text_payload(title, raw_contents, content_quality_hint)
    official_source_hint = _infer_official_source_hint(author, title, effective_text, platform)
    source_kind_hint = _infer_source_kind_hint(author, platform, official_source_hint)
    eventness = _eventness_score(title, effective_text, published_at, official_source_hint)
    actor_salience = _actor_salience_score(author, title, effective_text, official_source_hint, matched_terms, published_at)
    risk_facets = _risk_facets(title, effective_text, author)
    contradiction_signal = _contradiction_signal(title, effective_text, raw_polarity, risk_facets)
    risk_salience = _risk_salience_score(title, effective_text, raw_polarity, risk_facets, contradiction_signal, eventness)
    generic_explainer = any(hint in f"{title} {effective_text}" for hint in _GENERIC_INFO_HINTS)
    dominant_signals = []
    if official_source_hint == "official_like":
        dominant_signals.append("official_like")
    elif official_source_hint == "media_like":
        dominant_signals.append("media_like")
    if eventness >= 0.45:
        dominant_signals.append("event_dense")
    if actor_salience >= 0.4:
        dominant_signals.append("actor_dense")
    if risk_salience >= 0.4:
        dominant_signals.append("risk_dense")
    dominant_signals.extend(risk_facets[:3])
    return {
        "raw_contents": raw_contents,
        "raw_polarity": raw_polarity,
        "region": str(item.get("region") or "").strip(),
        "matched_terms": matched_terms,
        "content_quality_hint": content_quality_hint,
        "effective_text": effective_text,
        "official_source_hint": official_source_hint,
        "source_kind_hint": source_kind_hint,
        "actor_salience_score": actor_salience,
        "eventness_score": eventness,
        "risk_salience_score": risk_salience,
        "risk_facets": risk_facets,
        "contradiction_signal": contradiction_signal,
        "generic_explainer": generic_explainer,
        "dominant_signals": _unique_strings(dominant_signals, max_items=6),
    }


def _intent_rerank_score(item: Dict[str, Any], intent: str) -> tuple[float, List[str]]:
    profile = item.get("_semantic_profile") if isinstance(item.get("_semantic_profile"), dict) else {}
    base_score = float(item.get("score") or 0.0)
    score_breakdown = item.get("score_breakdown") if isinstance(item.get("score_breakdown"), dict) else {}
    policy_context = float(score_breakdown.get("policy_context") or 0.0)
    eventness = float(profile.get("eventness_score") or 0.0)
    actor_salience = float(profile.get("actor_salience_score") or 0.0)
    risk_salience = float(profile.get("risk_salience_score") or 0.0)
    contradiction_signal = float(profile.get("contradiction_signal") or 0.0)
    official_source_hint = str(profile.get("official_source_hint") or "").strip()
    generic_explainer = bool(profile.get("generic_explainer"))
    raw_polarity = str(profile.get("raw_polarity") or "").strip()
    signals = list(profile.get("dominant_signals") or [])
    if intent == "timeline":
        score = base_score * 0.65 + eventness * 3.1 + policy_context * 0.25 - (0.85 if generic_explainer else 0.0)
        return score, _unique_strings(signals + ["timeline_rerank"], max_items=6)
    if intent == "actors":
        score = base_score * 0.6 + actor_salience * 3.2 + eventness * 0.7 + (0.28 if official_source_hint in {"official_like", "media_like"} else 0.0)
        return score, _unique_strings(signals + ["actors_rerank"], max_items=6)
    if intent == "risk":
        score = (
            base_score * 0.52
            + risk_salience * 3.6
            + contradiction_signal * 1.5
            + (0.24 if raw_polarity == "负面" else 0.0)
            - (0.9 if generic_explainer and risk_salience < 0.35 else 0.0)
        )
        return score, _unique_strings(signals + ["risk_rerank"], max_items=6)
    score = base_score * 0.78 + eventness * 0.9 + actor_salience * 0.45 + min(0.65, risk_salience * 0.25) + policy_context * 0.2
    return score, _unique_strings(signals + ["overview_rerank"], max_items=6)


def _select_intent_diverse_items(items: List[Dict[str, Any]], *, intent: str, total_needed: int) -> List[Dict[str, Any]]:
    remaining = list(items)
    selected: List[Dict[str, Any]] = []
    platform_counts: Counter[str] = Counter()
    date_counts: Counter[str] = Counter()
    author_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    facet_counts: Counter[str] = Counter()
    while remaining and len(selected) < max(1, int(total_needed or 1)):
        best_index = 0
        best_score = -10**9
        for index, candidate in enumerate(remaining[:160]):
            adjusted = float(candidate.get("_intent_score") or 0.0)
            profile = candidate.get("_semantic_profile") if isinstance(candidate.get("_semantic_profile"), dict) else {}
            platform = str(candidate.get("platform") or "未知").strip() or "未知"
            date_text = _extract_date(candidate.get("published_at")) or "未知"
            author = str(candidate.get("author") or "").strip() or "匿名"
            source_kind = str(profile.get("source_kind_hint") or "unknown").strip()
            facet_signature = "|".join(list(profile.get("risk_facets") or [])[:2]) or "none"
            if intent == "timeline":
                adjusted -= 0.42 * date_counts.get(date_text, 0)
                adjusted -= 0.18 * platform_counts.get(platform, 0)
            elif intent == "actors":
                adjusted -= 0.35 * author_counts.get(author, 0)
                adjusted -= 0.22 * kind_counts.get(source_kind, 0)
            elif intent == "risk":
                adjusted -= 0.28 * facet_counts.get(facet_signature, 0)
                adjusted -= 0.18 * author_counts.get(author, 0)
                adjusted -= 0.12 * platform_counts.get(platform, 0)
            else:
                adjusted -= 0.24 * platform_counts.get(platform, 0)
                adjusted -= 0.18 * date_counts.get(date_text, 0)
                adjusted -= 0.12 * kind_counts.get(source_kind, 0)
            if adjusted > best_score:
                best_score = adjusted
                best_index = index
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        profile = chosen.get("_semantic_profile") if isinstance(chosen.get("_semantic_profile"), dict) else {}
        platform_counts[str(chosen.get("platform") or "未知").strip() or "未知"] += 1
        date_counts[_extract_date(chosen.get("published_at")) or "未知"] += 1
        author_counts[str(chosen.get("author") or "").strip() or "匿名"] += 1
        kind_counts[str(profile.get("source_kind_hint") or "unknown").strip()] += 1
        facet_signature = "|".join(list(profile.get("risk_facets") or [])[:2]) or "none"
        facet_counts[facet_signature] += 1
    return selected


def _build_rewrite_queries(normalized_task: Dict[str, Any], *, intent: str, filters: Dict[str, Any]) -> List[str]:
    topic = str(normalized_task.get("topic") or normalized_task.get("topic_identifier") or "").strip()
    entities = [str(item).strip() for item in (normalized_task.get("entities") or []) if str(item or "").strip()]
    keywords = [str(item).strip() for item in (normalized_task.get("keywords") or []) if str(item or "").strip()]
    explicit_query = _normalize_text(filters.get("query"))
    intent_terms = {
        "overview": ["概览", "舆情", "讨论"],
        "timeline": ["时间", "事件", "经过", "节点"],
        "actors": ["回应", "表态", "主体", "立场"],
        "risk": ["风险", "争议", "辟谣", "扩散"],
        "claim_support": ["证据", "支持", "事实"],
        "claim_counter": ["反证", "辟谣", "误读"],
    }.get(intent, ["概览"])
    time_range = normalized_task.get("time_range") if isinstance(normalized_task.get("time_range"), dict) else {}
    time_hint = " ".join([str(time_range.get("start") or "").strip(), str(time_range.get("end") or "").strip()]).strip()
    query_candidates = [
        explicit_query,
        " ".join([topic, *entities[:3], *keywords[:4], *intent_terms[:2]]).strip(),
        " ".join([topic, *keywords[:6], *intent_terms[:3]]).strip(),
        " ".join([topic, *entities[:2], time_hint, *intent_terms[:2]]).strip(),
    ]
    return _unique_strings(query_candidates, max_items=4)


def _infer_task_goal(intent: str) -> str:
    return {
        "overview": "build_summary_objects",
        "timeline": "build_timeline_objects",
        "actors": "build_conflict_objects",
        "risk": "build_risk_objects",
        "claim_support": "verify_claim_support",
        "claim_counter": "find_counterevidence",
    }.get(intent, "build_summary_objects")


def _infer_risk_sensitivity(normalized_task: Dict[str, Any], intent: str) -> str:
    policy = " ".join(str(item).strip() for item in (normalized_task.get("risk_policy") or []) if str(item or "").strip())
    if any(token in policy for token in ("高敏", "严格", "从严")) or intent in {"risk", "claim_counter"}:
        return "high"
    if intent == "timeline":
        return "moderate"
    return "baseline"


def build_retrieval_plan_payload(*, normalized_task_json: str, intent: str = "overview", filters_json: str = "{}") -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    filters = _clean_dict(filters_json)
    safe_intent = str(intent or "overview").strip() or "overview"
    query_variants = _build_rewrite_queries(normalized_task, intent=safe_intent, filters=filters)
    platforms = [str(item).strip() for item in (filters.get("platforms") or normalized_task.get("platform_scope") or []) if str(item or "").strip()]
    entities = [str(item).strip() for item in (filters.get("entities") or normalized_task.get("entities") or []) if str(item or "").strip()]
    time_start = str(filters.get("time_start") or normalized_task.get("time_range", {}).get("start") or "").strip()
    time_end = str(filters.get("time_end") or normalized_task.get("time_range", {}).get("end") or "").strip()
    event_stage = (
        "propagation"
        if safe_intent in {"overview", "risk"}
        else "timeline"
        if safe_intent == "timeline"
        else "actors"
        if safe_intent == "actors"
        else "verification"
    )
    output_goal = "counterevidence" if safe_intent == "claim_counter" else "evidence"
    source_types = _unique_strings(
        [str(item).strip() for item in (filters.get("source_types") or []) if str(item or "").strip()]
        or [_source_type_for_platform(item) for item in platforms],
        max_items=4,
    )
    facet = RouterFacet(
        facet_id=f"facet:{safe_intent}",
        intent=safe_intent,
        platforms=platforms,
        entities=entities,
        source_types=source_types,
        time_start=time_start,
        time_end=time_end,
        event_stage=event_stage,
        source_credibility="balanced",
        risk_sensitivity=_infer_risk_sensitivity(normalized_task, safe_intent),
        task_goal=_infer_task_goal(safe_intent),
        output_goal=output_goal,
    )
    specialist_target = (
        "agenda_frame_builder"
        if safe_intent == "overview"
        else "evidence_organizer"
        if safe_intent in {"claim_support", "claim_counter"}
        else "timeline_analyst"
        if safe_intent == "timeline"
        else "claim_actor_conflict"
        if safe_intent == "actors"
        else "propagation_analyst"
    )
    expected_artifacts = (
        ["agenda_frame_map", "evidence_cards"]
        if specialist_target == "agenda_frame_builder"
        else ["evidence_cards"]
        if specialist_target == "evidence_organizer"
        else ["timeline_nodes", "metrics_bundle"]
        if specialist_target == "timeline_analyst"
        else ["actor_positions", "conflict_map"]
        if specialist_target == "claim_actor_conflict"
        else ["mechanism_summary", "risk_signals"]
    )
    dispatch_plan = RouterDispatchPlan(
        router_version="router.v1",
        policy_version="policy.v2",
        facets=[facet],
        dispatches=[
            RouterDispatch(
                facet_id=facet.facet_id,
                specialist_target=specialist_target,
                aggregation_strategy="merge_by_trace",
                lineage_tags=[safe_intent, output_goal, event_stage],
                expected_artifacts=expected_artifacts,
                contribution_weight=1.0,
            )
        ],
        quality_ledger=[
            DispatchQualityEntry(
                facet_id=facet.facet_id,
                specialist_target=specialist_target,
                expected_artifacts=expected_artifacts,
                actual_artifacts=[],
                contributed_artifacts=[],
                contribution_status="planned",
            )
        ],
    )
    result = {
        "intent": safe_intent,
        "query_variants": query_variants,
        "filters": {
            "platforms": platforms,
            "entities": entities,
            "time_start": time_start,
            "time_end": time_end,
        },
        "retrieval_strategy": "hybrid_lexical_semantic",
        "rerank_policy": "score_then_diversify_then_compress",
        "compression_policy": "keep_high_novelty_counterevidence_and_cross_platform_cards",
        "router_facets": [facet.model_dump()],
        "dispatch_plan": dispatch_plan.model_dump(),
        "dispatch_quality_ledger": [item.model_dump() for item in dispatch_plan.quality_ledger],
    }
    return {
        "result": result,
        **_base_result(
            normalized_task=normalized_task,
            tool_name="build_retrieval_plan",
            confidence=0.84,
            trace=_trace_payload([], offset=0, total=0, retrieval_strategy="hybrid_lexical_semantic", rewrite_queries=query_variants, compression_applied=False),
        ),
    }


def build_agenda_frame_map_payload(
    *,
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    actor_positions_json: str = "[]",
    conflict_map_json: str = "{}",
    timeline_nodes_json: str = "[]",
) -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="overview", fallback_limit=18)
    actors = _safe_parse_json(actor_positions_json, [])
    if isinstance(actors, dict):
        actors = actors.get("result") if isinstance(actors.get("result"), list) else actors.get("actors", [])
    if not isinstance(actors, list):
        actors = []
    conflict_map = _safe_parse_json(conflict_map_json, {})
    if not isinstance(conflict_map, dict):
        conflict_map = {}
    timeline_nodes = _safe_parse_json(timeline_nodes_json, [])
    if isinstance(timeline_nodes, dict):
        timeline_nodes = timeline_nodes.get("result") if isinstance(timeline_nodes.get("result"), list) else []
    if not isinstance(timeline_nodes, list):
        timeline_nodes = []

    topic = str(normalized_task.get("topic") or normalized_task.get("topic_identifier") or "").strip()
    issue_nodes: List[IssueNode] = []
    attribute_nodes: List[AttributeNode] = []
    issue_attribute_edges: List[IssueAttributeEdge] = []
    frames: List[FrameRecord] = []
    frame_carriers: List[FrameCarrierActor] = []
    frame_shifts: List[FrameShift] = []
    counter_frames: List[CounterFrame] = []

    issue_index: Dict[str, str] = {}
    attribute_index: Dict[str, str] = {}
    frame_index: Dict[str, str] = {}

    for index, card in enumerate(cards[:8], start=1):
        title = _normalize_text(card.get("title") or card.get("snippet"))
        evidence_id = str(card.get("evidence_id") or "").strip()
        if not title or not evidence_id:
            continue
        issue_label = _issue_label(title, topic)
        issue_id = issue_index.setdefault(issue_label, f"issue-{_normalize_key(issue_label)}")
        if not any(item.issue_id == issue_id for item in issue_nodes):
            issue_nodes.append(
                IssueNode(
                    issue_id=issue_id,
                    label=issue_label,
                    salience=round(min(1.0, 0.45 + float(card.get("relevance") or 0.0) / 12.0), 4),
                    time_scope=[_extract_date(card.get("published_at"))] if _extract_date(card.get("published_at")) else [],
                    source_refs=[evidence_id],
                )
            )
        for attr_type, attr_label in _attribute_labels(title):
            attribute_id = attribute_index.setdefault(attr_label, f"attribute-{_normalize_key(attr_label)}")
            if not any(item.attribute_id == attribute_id for item in attribute_nodes):
                attribute_nodes.append(
                    AttributeNode(
                        attribute_id=attribute_id,
                        label=attr_label,
                        attribute_type=attr_type,
                        salience=round(min(1.0, 0.4 + float(card.get("novelty_score") or 0.0)), 4),
                        source_refs=[evidence_id],
                    )
                )
            issue_attribute_edges.append(
                IssueAttributeEdge(
                    edge_id=f"issue-attr-{index}-{_normalize_key(issue_label)}-{_normalize_key(attr_label)}",
                    issue_id=issue_id,
                    attribute_id=attribute_id,
                    weight=round(min(1.0, 0.45 + float(card.get("confidence") or 0.0)), 4),
                    time_scope=[_extract_date(card.get("published_at"))] if _extract_date(card.get("published_at")) else [],
                    source_refs=[evidence_id],
                )
            )

        components = _frame_components(title, topic=topic)
        frame_key = _normalize_key("|".join(components.values()))
        frame_id = frame_index.setdefault(frame_key, f"frame-{frame_key}")
        if not any(item.frame_id == frame_id for item in frames):
            frames.append(
                FrameRecord(
                    frame_id=frame_id,
                    problem=components["problem"],
                    cause=components["cause"],
                    judgment=components["judgment"],
                    remedy=components["remedy"],
                    confidence=round(min(0.92, 0.5 + float(card.get("confidence") or 0.0) * 0.4), 4),
                    source_refs=[evidence_id],
                )
            )

    for actor in actors[:6]:
        if not isinstance(actor, dict):
            continue
        actor_id = str(actor.get("actor_id") or "").strip()
        if not actor_id or not frames:
            continue
        frame_carriers.append(
            FrameCarrierActor(
                actor_id=actor_id,
                frame_ids=[frame.frame_id for frame in frames[:2]],
                role=str(actor.get("speaker_role") or actor.get("role_type") or "carrier").strip(),
            )
        )

    if len(frames) >= 2:
        shift_anchor = ""
        trigger_refs: List[str] = []
        for node in timeline_nodes[:1]:
            if isinstance(node, dict):
                shift_anchor = str(node.get("time_label") or "").strip()
                trigger_refs = [str(item).strip() for item in (node.get("support_evidence_ids") or []) if str(item or "").strip()][:4]
                break
        frame_shifts.append(
            FrameShift(
                shift_id="frame-shift-1",
                from_frame_id=frames[0].frame_id,
                to_frame_id=frames[1].frame_id,
                time_anchor=shift_anchor,
                trigger_refs=trigger_refs,
            )
        )

    for edge in (conflict_map.get("edges") or [])[:2]:
        if not isinstance(edge, dict) or not frames:
            continue
        counter_frames.append(
            CounterFrame(
                frame_id=frames[min(1, len(frames) - 1)].frame_id,
                counter_to_frame_id=frames[0].frame_id,
                support_refs=[str(item).strip() for item in (edge.get("evidence_refs") or []) if str(item or "").strip()][:4],
            )
        )

    agenda_frame_map = AgendaFrameMap(
        issues=issue_nodes,
        attributes=attribute_nodes,
        issue_attribute_edges=issue_attribute_edges,
        frames=frames,
        frame_carriers=frame_carriers,
        frame_shifts=frame_shifts,
        counter_frames=counter_frames,
        summary="；".join(
            _unique_strings(
                [
                    f"识别 {len(issue_nodes)} 个议题节点",
                    f"{len(attribute_nodes)} 个属性节点",
                    f"{len(frames)} 条框架记录",
                ],
                max_items=3,
            )
        ),
    )
    coverage = _coverage_payload(
        matched_count=len(cards),
        sampled_count=len(issue_nodes) + len(frames),
        platform_counts=dict(Counter(str(card.get("platform") or "未知").strip() for card in cards)),
        readiness_flags=["agenda_frame_ready"] if issue_nodes or frames else ["agenda_frame_empty"],
    )
    return {
        "agenda_frame_map": agenda_frame_map.model_dump(),
        "result": agenda_frame_map.model_dump(),
        **_base_result(
            normalized_task=normalized_task,
            tool_name="build_agenda_frame_map",
            coverage=coverage,
            confidence=min(0.92, 0.42 + len(issue_nodes) * 0.06 + len(frames) * 0.05),
            trace=_trace_payload(cards, offset=0, total=len(cards)),
        ),
    }


def _map_item_to_card(item: Dict[str, Any], normalized_task: Dict[str, Any], index: int) -> Dict[str, Any]:
    source_file = str(item.get("source_file") or "").strip()
    source_row_index = str(item.get("source_row_index") or index).strip()
    source_id = f"{source_file}:{source_row_index}" if source_file else f"source:{index}"
    title = _normalize_text(item.get("title"))
    snippet = _normalize_text(item.get("snippet"))
    url = str(item.get("url") or "").strip()
    dedupe_key = url.lower() if url else _normalize_key(title or snippet or source_id)
    semantic_profile = item.get("_semantic_profile") if isinstance(item.get("_semantic_profile"), dict) else _candidate_semantic_profile(item, normalized_task)
    raw_contents = str(semantic_profile.get("raw_contents") or item.get("contents") or item.get("content") or "").strip()
    raw_polarity = str(semantic_profile.get("raw_polarity") or item.get("polarity") or item.get("sentiment_raw") or "").strip()
    content_quality_hint = str(semantic_profile.get("content_quality_hint") or "").strip() or _content_quality_hint(title, raw_contents)
    effective_text = str(semantic_profile.get("effective_text") or "").strip() or title

    # 当前 fetch 数据里 title 可能就是短平台正文，contents 多为 title_echo；因此 content 以有效文本为主。
    content = effective_text or (snippet or title)

    entity_tags = [
        entity
        for entity in [str(row).strip() for row in (normalized_task.get("entities") or []) if str(row or "").strip()]
        if entity and (entity in title or entity in snippet or entity in content)
    ]
    author = str(item.get("author") or "").strip()
    if author and author not in entity_tags:
        entity_tags.append(author)
    keywords = [str(row).strip() for row in (normalized_task.get("keywords") or []) if str(row or "").strip()]
    topic_cluster = next((keyword for keyword in keywords if keyword in f"{title} {snippet}"), keywords[0] if keywords else "general")
    matched_terms = [str(term).strip() for term in (semantic_profile.get("matched_terms") or item.get("matched_terms") or []) if str(term or "").strip()]
    relevance = float(item.get("score") or 0.0)
    novelty_score = round(min(1.0, 0.35 + (0.08 * len(_tokenize(f"{title} {snippet}", max_items=8)))), 4)
    contradiction_signal = float(semantic_profile.get("contradiction_signal") or 0.18)

    # 提取情感标签（优先使用从 retrieval pipeline 传递的 sentiment_raw，其次尝试原始字段）
    sentiment_label = str(
        item.get("sentiment_raw") or  # 来自 evidence_retriever 的传递
        item.get("sentiment") or item.get("emotion") or item.get("sentiment_label") or
        item.get("情感") or item.get("情感倾向") or ""
    ).strip()

    # 提取关键词
    extracted_keywords = _tokenize(f"{title} {effective_text}", max_items=8)

    # 提取互动数据（优先使用从 retrieval pipeline 传递的字段，其次尝试原始字段名）
    engagement = {
        "likes": _safe_int(
            item.get("engagement_likes") or  # 来自 evidence_retriever 的传递
            item.get("likes") or item.get("like_count") or item.get("点赞数")
        ),
        "comments": _safe_int(
            item.get("engagement_comments") or
            item.get("comments") or item.get("comment_count") or item.get("评论数")
        ),
        "shares": _safe_int(
            item.get("engagement_shares") or
            item.get("shares") or item.get("share_count") or item.get("转发数") or item.get("转发")
        ),
        "views": _safe_int(
            item.get("engagement_views") or
            item.get("views") or item.get("view_count") or item.get("播放量") or item.get("阅读量")
        ),
    }
    # 热度评分：优先使用原始数据热度，其次 retrieval pipeline 传递的，最后使用 relevance
    hotness_score = float(
        item.get("hotness_raw") or  # 来自 evidence_retriever 的传递
        item.get("hotness_score") or item.get("热度") or 0.0
    )
    if hotness_score == 0.0:
        hotness_score = relevance  # fallback 使用 relevance

    # 格式化时间标签（用于引用时的时间标注）
    time_label = str(item.get("published_at") or item.get("publish_time") or "").strip()
    if time_label and len(time_label) > 10:
        # 尝试格式化为更友好的日期
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(time_label.replace("Z", "+00:00"))
            time_label = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    return {
        "evidence_id": f"ev-{_normalize_key(source_id)}",
        "source_id": source_id,
        "platform": str(item.get("platform") or "").strip(),
        "published_at": str(item.get("published_at") or "").strip(),
        "time_label": time_label,  # 新增：友好的时间标签
        "author": author,
        "author_type": str(item.get("author_type") or item.get("account_type") or item.get("publisher_type") or "").strip(),
        "entity_tags": entity_tags[:6],
        "topic_cluster": topic_cluster,
        "title": title,
        "snippet": snippet,
        "content": content[:2000] if content else "",
        "raw_contents": raw_contents[:2000] if raw_contents else "",
        "raw_polarity": raw_polarity,
        "region": str(semantic_profile.get("region") or item.get("region") or "").strip(),
        "matched_terms": matched_terms[:8],
        "sentiment_label": sentiment_label,
        "keywords": extracted_keywords,
        "engagement": engagement,  # 互动数据（可能为空）
        "hotness_score": round(hotness_score, 2),  # 热度评分
        "relevance": round(relevance, 4),
        "confidence": round(min(1.0, max(0.05, relevance / 10.0)), 4),
        "dedupe_key": dedupe_key,
        "url": url,
        "stance_hint": _card_stance_hint(title, effective_text),
        "stance": _card_stance_hint(title, effective_text),
        "subject": entity_tags[0] if entity_tags else "",  # 新增：主体字段（用于引用）
        "finding": snippet[:150] if snippet else title[:150],  # 新增：核心发现字段
        "claimability": _card_claimability(title, effective_text),
        "novelty_score": novelty_score,
        "contradiction_signal": round(contradiction_signal, 4),
        "content_quality_hint": content_quality_hint,
        "official_source_hint": str(semantic_profile.get("official_source_hint") or "").strip(),
        "source_kind_hint": str(semantic_profile.get("source_kind_hint") or "").strip(),
        "actor_salience_score": round(float(semantic_profile.get("actor_salience_score") or 0.0), 4),
        "eventness_score": round(float(semantic_profile.get("eventness_score") or 0.0), 4),
        "risk_salience_score": round(float(semantic_profile.get("risk_salience_score") or 0.0), 4),
        "risk_facets": [str(facet).strip() for facet in (semantic_profile.get("risk_facets") or []) if str(facet or "").strip()],
    }


def _cards_from_input(normalized_task: Dict[str, Any], evidence_ids_json: str, *, intent: str, fallback_limit: int) -> List[Dict[str, Any]]:
    raw_items = _safe_parse_json(evidence_ids_json, [])
    if isinstance(raw_items, list) and raw_items and isinstance(raw_items[0], dict):
        return [dict(item) for item in raw_items if isinstance(item, dict)]
    payload = retrieve_evidence_cards_payload(
        normalized_task_json=json.dumps(normalized_task, ensure_ascii=False),
        intent=intent,
        limit=fallback_limit,
    )
    return [dict(item) for item in (payload.get("result") or []) if isinstance(item, dict)]


def normalize_task_payload(*, task_text: str, topic_identifier: str, start: str, end: str, mode: str, hints_json: str = "{}") -> Dict[str, Any]:
    hints = _clean_dict(hints_json)
    hinted_contract = _task_contract_from_hints(hints)
    requested_topic_identifier = str(topic_identifier or "").strip()
    requested_start = str(start or "").strip()
    requested_end = str(end or start or "").strip()
    requested_mode = str(mode or "fast").strip().lower() or "fast"
    effective_topic_identifier = hinted_contract["topic_identifier"] or requested_topic_identifier
    effective_start = hinted_contract["start"] or requested_start
    effective_end = hinted_contract["end"] or requested_end or effective_start
    effective_mode = hinted_contract["mode"] or requested_mode
    contract_overrides_applied: List[str] = []
    if hinted_contract["topic_identifier"] and hinted_contract["topic_identifier"] != requested_topic_identifier:
        contract_overrides_applied.append("topic_identifier")
    if hinted_contract["start"] and hinted_contract["start"] != requested_start:
        contract_overrides_applied.append("start")
    if hinted_contract["end"] and hinted_contract["end"] != requested_end:
        contract_overrides_applied.append("end")
    if hinted_contract["mode"] and hinted_contract["mode"] != requested_mode:
        contract_overrides_applied.append("mode")
    text = _normalize_text(task_text)
    topic = str(hinted_contract["topic_label"] or hints.get("topic") or text or effective_topic_identifier).strip() or effective_topic_identifier
    # 使用语义提取函数，而非简单 tokenize
    entity_names = _extract_semantic_entity_names(hints.get("entities") or []) or _extract_entities(text, max_items=6)
    keyword_terms = _extract_semantic_keyword_terms(hints.get("keywords") or []) or _tokenize(text, max_items=10)
    platform_scope = [str(item).strip() for item in (hints.get("platform_scope") or []) if str(item or "").strip()]
    report_type = str(hints.get("report_type") or "").strip()
    if not report_type:
        report_type = "risk" if "风险" in text else "propagation" if "传播" in text or "走势" in text else "analysis"
    if report_type not in _REPORT_TYPE_ALLOWED:
        report_type = "analysis"
    mandatory_sections = [str(item).strip() for item in (hints.get("mandatory_sections") or []) if str(item or "").strip()] or ["overview", "timeline", "actors", "propagation", "risk"]
    risk_policy = [str(item).strip() for item in (hints.get("risk_policy") or []) if str(item or "").strip()] or ["evidence_first", "prefer_counterevidence", "keep_uncertainty_visible"]
    analysis_question_set = [str(item).strip() for item in (hints.get("analysis_question_set") or []) if str(item or "").strip()] or ["传播演化", "主体立场", "争议焦点", "风险信号"]
    coverage_expectation = [str(item).strip() for item in (hints.get("coverage_expectation") or []) if str(item or "").strip()] or ["raw_posts", "media_reports", "platform_distribution"]
    inference_policy = [str(item).strip() for item in (hints.get("inference_policy") or []) if str(item or "").strip()] or ["risk_trend_can_be_weak_inference", "actor_shift_requires_multi_period_evidence", "claim_requires_backlink"]
    task_contract = _build_task_contract(
        topic_identifier=effective_topic_identifier,
        topic_label=str(hinted_contract["topic_label"] or topic).strip(),
        start=effective_start,
        end=effective_end,
        mode=effective_mode,
        thread_id=hinted_contract["thread_id"],
    )
    attempted_overrides = {
        key: value
        for key, value in {
            "topic_identifier": requested_topic_identifier,
            "start": requested_start,
            "end": requested_end,
            "mode": requested_mode,
        }.items()
        if value and key in contract_overrides_applied
    }
    task_derivation = {
        "derivation_id": f"drv:{task_contract['contract_id']}",
        "topic": topic,
        "topic_identifier": effective_topic_identifier,
        "topic_label": _coerce_topic_label_payload(
            hinted_contract["topic_label"] or topic,
            fallback=hinted_contract["topic_label"] or topic or effective_topic_identifier,
            full_description_fallback=topic,
        ),
        "topic_aliases": _unique_strings([text, requested_topic_identifier, hints.get("topic")], max_items=4),
        "entities": _coerce_semantic_entity_list(entity_names),
        "keywords": _coerce_semantic_keyword_list(keyword_terms),
        "platform_scope": platform_scope,
        "report_type": report_type,
        "mandatory_sections": mandatory_sections,
        "risk_policy": risk_policy,
        "analysis_question_set": analysis_question_set,
        "coverage_expectation": coverage_expectation,
        "inference_policy": inference_policy,
        "attempted_overrides": attempted_overrides,
        "contract_overrides_applied": contract_overrides_applied,
    }
    normalized_task = _build_normalized_task_view(task_contract, task_derivation)
    proposal_snapshot = {
        "task_text": text,
        # requested_execution_fields 仅用于审计追踪（记录原始请求参数），实际执行必须使用 effective_contract
        "_audit_note": "requested_execution_fields 仅用于审计追踪，实际执行请使用 effective_contract",
        "requested_execution_fields": {
            "topic_identifier": requested_topic_identifier,
            "start": requested_start,
            "end": requested_end,
            "mode": requested_mode,
        },
        # effective_contract 是权威契约值，所有下游执行必须使用此契约而非 requested_execution_fields
        "effective_contract": task_contract,
        "agent_semantic_fields": {
            "topic": topic,
            "entities": entity_names,
            "keywords": keyword_terms,
            "platform_scope": platform_scope,
            "mandatory_sections": mandatory_sections,
        },
        "attempted_overrides": attempted_overrides,
        "repair_action": "override" if contract_overrides_applied else "none",
        "contract_overrides_applied": contract_overrides_applied,
    }
    return {
        "task_contract": task_contract,
        "task_derivation": task_derivation,
        "proposal_snapshot": proposal_snapshot,
        "normalized_task": normalized_task,
        "result": normalized_task,
        **_base_result(normalized_task=normalized_task, tool_name="normalize_task", confidence=0.92),
    }


def get_corpus_coverage_payload(
    *,
    contract_id: str = "",
    normalized_task_json: str = "",
    task_contract_json: str = "",
    task_derivation_json: str = "",
    retrieval_scope_json: str = "{}",
    filters_json: str = "{}",
    include_samples: bool = False,
    limit: int = 20,
) -> Dict[str, Any]:
    execution_view = _resolve_task_execution_view(
        contract_id=contract_id,
        normalized_task_json=normalized_task_json,
        task_contract_json=task_contract_json,
        task_derivation_json=task_derivation_json,
        retrieval_scope_json=retrieval_scope_json,
    )
    normalized_task = execution_view["normalized_task"] if isinstance(execution_view.get("normalized_task"), dict) else {}
    scope_meta = execution_view["scope_meta"] if isinstance(execution_view.get("scope_meta"), dict) else {}
    contract_binding_failed = bool(execution_view.get("contract_binding_failed"))
    legacy_adapter_hit = bool(execution_view.get("legacy_adapter_hit"))
    legacy_input_kind = [str(item).strip() for item in (execution_view.get("legacy_input_kind") or []) if str(item or "").strip()]
    filters = _clean_dict(filters_json)
    topic_identifier = str(normalized_task.get("topic_identifier") or "").strip()
    time_range = normalized_task.get("time_range") if isinstance(normalized_task.get("time_range"), dict) else {}
    start = str(time_range.get("start") or "").strip()
    end = str(time_range.get("end") or start).strip()
    platforms = [str(item).strip() for item in (filters.get("platforms") or normalized_task.get("platform_scope") or []) if str(item or "").strip()]
    task_contract = normalized_task.get("task_contract") if isinstance(normalized_task.get("task_contract"), dict) else {}
    contract_topic_identifier = str(task_contract.get("topic_identifier") or topic_identifier).strip()
    contract_start = str(task_contract.get("start") or start).strip()
    contract_end = str(task_contract.get("end") or end).strip()
    requested_time_range = scope_meta.get("requested_time_range") if isinstance(scope_meta.get("requested_time_range"), dict) else {"start": contract_start, "end": contract_end or contract_start}
    effective_time_range = scope_meta.get("effective_time_range") if isinstance(scope_meta.get("effective_time_range"), dict) else {"start": start, "end": end or start}
    if contract_binding_failed:
        coverage = _coverage_payload(
            matched_count=0,
            sampled_count=0,
            source_resolution="contract_binding_failed",
            requested_time_range=requested_time_range,
            effective_time_range=effective_time_range,
            contract_topic_identifier=str((execution_view.get("contract_value") or {}).get("topic_identifier") or "").strip(),
            effective_topic_identifier=topic_identifier,
            field_gaps=["contract_id"],
            source_quality_flags=(["legacy_adapter_hit"] if legacy_adapter_hit else []),
            readiness_flags=["contract_binding_failed"],
        )
        return {
            "result": {
                "platform_counts": {},
                "date_span": {},
                "field_gaps": ["contract_id"],
                "missing_sources": [],
                "source_quality_flags": list(coverage.get("source_quality_flags") or []),
                "readiness_flags": ["contract_binding_failed"],
                "samples": [],
                "source_resolution": "contract_binding_failed",
                "resolved_fetch_range": {},
                "resolved_source_files": [],
                "requested_time_range": requested_time_range,
                "effective_time_range": effective_time_range,
                "contract_topic_identifier": str((execution_view.get("contract_value") or {}).get("topic_identifier") or "").strip(),
                "effective_topic_identifier": topic_identifier,
                "contract_mismatch": False,
            },
            "legacy_adapter_hit": legacy_adapter_hit,
            "legacy_input_kind": legacy_input_kind,
            "contract_binding_failed": True,
            "violation_origin": "payload_adapter",
            "repair_action": "reject_missing_contract",
            "contract_value": execution_view.get("contract_value") or {},
            "agent_proposed_value": execution_view.get("agent_proposed_value") or {},
            "effective_value": execution_view.get("effective_value") or {},
            **_base_result(
                normalized_task=normalized_task,
                tool_name="get_corpus_coverage",
                coverage=coverage,
                confidence=0.0,
                trace=_trace_payload(
                    [],
                    offset=0,
                    total=0,
                    contract_id=str(execution_view.get("contract_id") or "").strip(),
                    derivation_id=str((execution_view.get("task_derivation") or {}).get("derivation_id") or "").strip(),
                    requested_scope=requested_time_range,
                    effective_scope=effective_time_range,
                ),
                error_hint="contract_id 缺失或无法绑定到 registry，已阻止继续检索。",
            ),
        }
    source_scope = resolve_source_scope(topic_identifier, start, end)
    source_resolution = str(source_scope.get("source_resolution") or "").strip()
    resolved_fetch_range = source_scope.get("resolved_fetch_range") if isinstance(source_scope.get("resolved_fetch_range"), dict) else {}
    resolved_source_files = [str(item).strip() for item in (source_scope.get("source_files") or []) if str(item or "").strip()]
    contract_mismatch = bool(
        contract_topic_identifier and contract_topic_identifier != topic_identifier
        or contract_start and contract_start != start
        or contract_end and contract_end != end
    )
    rows = list(iter_filtered_records(topic_identifier=topic_identifier, start=start, end=end, platforms=platforms or None))
    platform_counts: Counter[str] = Counter()
    dates: List[str] = []
    field_gaps: List[str] = []
    missing_sources: List[str] = []
    source_quality_flags: List[str] = []
    readiness_flags: List[str] = []
    url_missing = 0
    author_missing = 0
    for row in rows:
        platform = str(row.get("platform") or "").strip() or "未知"
        platform_counts[platform] += 1
        date_text = _extract_date(row.get("published_at") or row.get("publish_time") or row.get("date"))
        if date_text:
            dates.append(date_text)
        if not str(row.get("url") or "").strip():
            url_missing += 1
        if not str(row.get("author") or "").strip():
            author_missing += 1
    if rows:
        readiness_flags.append("records_available")
    elif contract_mismatch:
        readiness_flags.append("contract_violation")
    elif bool(source_scope.get("partial_range_coverage")):
        readiness_flags.append("partial_range_coverage")
    elif source_resolution == "unavailable":
        missing_sources.append("raw_documents")
        readiness_flags.append("source_unavailable")
    else:
        missing_sources.append("raw_documents")
        readiness_flags.append("no_records_in_scope")
    expected = set(normalized_task.get("coverage_expectation") or [])
    if "media_reports" in expected and "新闻" not in platform_counts:
        missing_sources.append("media_reports")
    if rows and url_missing == len(rows):
        field_gaps.append("url")
    if rows and author_missing == len(rows):
        field_gaps.append("author")
    if len(platform_counts) <= 1 and rows:
        source_quality_flags.append("single_platform_skew")
    if bool(source_scope.get("partial_range_coverage")):
        source_quality_flags.append("partial_range_coverage")
    if legacy_adapter_hit and "legacy_adapter_hit" not in source_quality_flags:
        source_quality_flags.append("legacy_adapter_hit")
    for flag in [str(item).strip() for item in (scope_meta.get("scope_flags") or []) if str(item or "").strip()]:
        if flag not in source_quality_flags:
            source_quality_flags.append(flag)
    date_span = {"start": min(dates, default=""), "end": max(dates, default="")}
    samples: List[Dict[str, Any]] = []
    if include_samples:
        for row in rows[: max(1, min(int(limit or 20), 20))]:
            samples.append({"title": _normalize_text(row.get("title")), "platform": str(row.get("platform") or "").strip(), "published_at": _extract_date(row.get("published_at") or row.get("publish_time") or row.get("date")), "snippet": _normalize_text(row.get("content") or row.get("contents"))[:140]})
    coverage = _coverage_payload(
        matched_count=len(rows),
        sampled_count=len(samples) if include_samples else min(len(rows), max(1, min(int(limit or 20), 20))),
        source_resolution=source_resolution,
        resolved_fetch_range=resolved_fetch_range,
        resolved_source_files=resolved_source_files,
        requested_time_range=requested_time_range,
        effective_time_range=effective_time_range,
        contract_topic_identifier=contract_topic_identifier,
        effective_topic_identifier=topic_identifier,
        contract_mismatch=contract_mismatch,
        platform_counts=dict(platform_counts),
        date_span=date_span,
        field_gaps=field_gaps,
        missing_sources=missing_sources,
        source_quality_flags=source_quality_flags,
        readiness_flags=readiness_flags,
    )
    return {
        "result": {
            "platform_counts": dict(platform_counts),
            "date_span": date_span,
            "field_gaps": field_gaps,
            "missing_sources": missing_sources,
            "source_quality_flags": source_quality_flags,
            "readiness_flags": readiness_flags,
            "samples": samples,
            "source_resolution": source_resolution,
            "resolved_fetch_range": resolved_fetch_range,
            "resolved_source_files": resolved_source_files,
            "requested_time_range": requested_time_range,
            "effective_time_range": effective_time_range,
            "contract_topic_identifier": contract_topic_identifier,
            "effective_topic_identifier": topic_identifier,
            "contract_mismatch": contract_mismatch,
        },
        "legacy_adapter_hit": legacy_adapter_hit,
        "legacy_input_kind": legacy_input_kind,
        "contract_binding_failed": False,
        "violation_origin": execution_view.get("violation_origin") or "",
        "repair_action": execution_view.get("repair_action") or "none",
        "contract_value": execution_view.get("contract_value") or {},
        "agent_proposed_value": execution_view.get("agent_proposed_value") or {},
        "effective_value": execution_view.get("effective_value") or {},
        **_base_result(
            normalized_task=normalized_task,
            tool_name="get_corpus_coverage",
            coverage=coverage,
            confidence=0.88,
            trace=_trace_payload(
                [],
                offset=0,
                total=len(rows),
                retrieval_strategy="source_resolution",
                contract_id=str(execution_view.get("contract_id") or "").strip(),
                derivation_id=str((execution_view.get("task_derivation") or {}).get("derivation_id") or "").strip(),
                requested_scope=requested_time_range,
                effective_scope=effective_time_range,
            ),
        ),
    }


def retrieve_evidence_cards_payload(
    *,
    contract_id: str = "",
    normalized_task_json: str = "",
    task_contract_json: str = "",
    task_derivation_json: str = "",
    retrieval_scope_json: str = "{}",
    intent: str,
    filters_json: str = "{}",
    sort_by: str = "relevance",
    limit: int = 12,
    cursor: str = "",
) -> Dict[str, Any]:
    execution_view = _resolve_task_execution_view(
        contract_id=contract_id,
        normalized_task_json=normalized_task_json,
        task_contract_json=task_contract_json,
        task_derivation_json=task_derivation_json,
        retrieval_scope_json=retrieval_scope_json,
    )
    normalized_task = execution_view["normalized_task"] if isinstance(execution_view.get("normalized_task"), dict) else {}
    scope_meta = execution_view["scope_meta"] if isinstance(execution_view.get("scope_meta"), dict) else {}
    contract_binding_failed = bool(execution_view.get("contract_binding_failed"))
    legacy_adapter_hit = bool(execution_view.get("legacy_adapter_hit"))
    legacy_input_kind = [str(item).strip() for item in (execution_view.get("legacy_input_kind") or []) if str(item or "").strip()]
    safe_intent, requested_intent = _normalize_tool_intent(intent)
    allowed_intents = list(_TOOL_INTENT_ALLOWED)
    if not safe_intent:
        invalid_coverage = _coverage_payload(
            matched_count=0,
            sampled_count=0,
            source_resolution="invalid_intent",
            requested_time_range=scope_meta.get("requested_time_range") if isinstance(scope_meta.get("requested_time_range"), dict) else {},
            effective_time_range=scope_meta.get("effective_time_range") if isinstance(scope_meta.get("effective_time_range"), dict) else {},
            contract_topic_identifier=str((execution_view.get("contract_value") or {}).get("topic_identifier") or "").strip(),
            effective_topic_identifier=str(normalized_task.get("topic_identifier") or "").strip(),
            field_gaps=["intent"],
            readiness_flags=["invalid_intent"],
        )
        return {
            "result": [],
            "legacy_adapter_hit": legacy_adapter_hit,
            "legacy_input_kind": legacy_input_kind,
            "contract_binding_failed": False,
            "violation_origin": execution_view.get("violation_origin") or "",
            "repair_action": "reject_invalid_intent",
            "contract_value": execution_view.get("contract_value") or {},
            "agent_proposed_value": execution_view.get("agent_proposed_value") or {},
            "effective_value": execution_view.get("effective_value") or {},
            **_base_result(
                normalized_task=normalized_task,
                tool_name="retrieve_evidence_cards",
                coverage=invalid_coverage,
                confidence=0.0,
                trace=_trace_payload(
                    [],
                    offset=0,
                    total=0,
                    contract_id=str(execution_view.get("contract_id") or "").strip(),
                    derivation_id=str((execution_view.get("task_derivation") or {}).get("derivation_id") or "").strip(),
                    requested_scope=scope_meta.get("requested_time_range") if isinstance(scope_meta.get("requested_time_range"), dict) else {},
                    effective_scope=scope_meta.get("effective_time_range") if isinstance(scope_meta.get("effective_time_range"), dict) else {},
                    requested_intent=requested_intent,
                    allowed_intents=allowed_intents,
                ),
                error_hint="intent 不合法；工具层仅接受 overview|timeline|actors|risk|claim_support|claim_counter。",
            ),
        }
    filters = _clean_dict(filters_json)
    time_range = normalized_task.get("time_range") if isinstance(normalized_task.get("time_range"), dict) else {}
    scope_range = scope_meta.get("effective_time_range") if isinstance(scope_meta.get("effective_time_range"), dict) else {}
    if contract_binding_failed:
        coverage = _coverage_payload(
            matched_count=0,
            sampled_count=0,
            source_resolution="contract_binding_failed",
            requested_time_range=scope_meta.get("requested_time_range") if isinstance(scope_meta.get("requested_time_range"), dict) else {},
            effective_time_range=scope_range,
            contract_topic_identifier=str((execution_view.get("contract_value") or {}).get("topic_identifier") or "").strip(),
            effective_topic_identifier=str(normalized_task.get("topic_identifier") or "").strip(),
            field_gaps=["contract_id"],
            source_quality_flags=(["legacy_adapter_hit"] if legacy_adapter_hit else []),
            readiness_flags=["contract_binding_failed"],
        )
        return {
            "result": [],
            "legacy_adapter_hit": legacy_adapter_hit,
            "legacy_input_kind": legacy_input_kind,
            "contract_binding_failed": True,
            "violation_origin": "payload_adapter",
            "repair_action": "reject_missing_contract",
            "contract_value": execution_view.get("contract_value") or {},
            "agent_proposed_value": execution_view.get("agent_proposed_value") or {},
            "effective_value": execution_view.get("effective_value") or {},
            **_base_result(
                normalized_task=normalized_task,
                tool_name="retrieve_evidence_cards",
                coverage=coverage,
                confidence=0.0,
                trace=_trace_payload(
                    [],
                    offset=0,
                    total=0,
                contract_id=str(execution_view.get("contract_id") or "").strip(),
                derivation_id=str((execution_view.get("task_derivation") or {}).get("derivation_id") or "").strip(),
                requested_scope=scope_meta.get("requested_time_range") if isinstance(scope_meta.get("requested_time_range"), dict) else {},
                effective_scope=scope_range,
                requested_intent=requested_intent,
                allowed_intents=allowed_intents,
            ),
            error_hint="contract_id 缺失或无法绑定到 registry，已阻止继续召回证据卡。",
        ),
        }
    query_variants = _build_rewrite_queries(normalized_task, intent=safe_intent, filters=filters)
    effective_platforms = [str(item).strip() for item in (filters.get("platforms") or normalized_task.get("platform_scope") or []) if str(item or "").strip()]
    effective_entities = [str(item).strip() for item in (filters.get("entities") or normalized_task.get("entities") or []) if str(item or "").strip()]
    requested_limit = max(1, min(int(limit or 12), 20))
    offset = max(0, int(str(cursor or "0").strip() or 0))
    retrieval_runs: List[Dict[str, Any]] = []
    merged: Dict[str, Dict[str, Any]] = {}
    source_distribution: Counter[str] = Counter()
    scanned_records = 0
    matched_records = 0
    retrieval_modes = set()
    for variant_index, variant_query in enumerate(query_variants[:3]):
        retrieval = search_raw_records(
            topic_identifier=str(normalized_task.get("topic_identifier") or "").strip(),
            start=str(time_range.get("start") or "").strip(),
            end=str(time_range.get("end") or "").strip(),
            query=variant_query,
            entities=effective_entities,
            platforms=effective_platforms,
            time_start=str(filters.get("time_start") or scope_range.get("start") or "").strip(),
            time_end=str(filters.get("time_end") or scope_range.get("end") or "").strip(),
            top_k=max(requested_limit + offset + 6, 12),
            mode=str(normalized_task.get("mode") or "fast").strip().lower() or "fast",
        )
        retrieval_runs.append(retrieval)
        retrieval_modes.add(str(retrieval.get("retrieval_strategy") or "").strip())
        scanned_records += int(retrieval.get("scanned_records") or 0)
        matched_records += int(retrieval.get("matched_records") or 0)
        source_distribution.update({str(key): int(value) for key, value in (retrieval.get("source_distribution") or {}).items()})
        for item in [dict(row) for row in (retrieval.get("items") or []) if isinstance(row, dict)]:
            dedupe_key = str(item.get("url") or "").strip().lower() or f"{str(item.get('source_file') or '').strip()}:{str(item.get('source_row_index') or '').strip()}"
            item["score"] = round(float(item.get("score") or 0.0) + max(0.0, 0.18 - variant_index * 0.05), 4)
            existing = merged.get(dedupe_key)
            if existing is None or float(item.get("score") or 0.0) > float(existing.get("score") or 0.0):
                merged[dedupe_key] = item
    items = list(merged.values())
    rerank_policy = f"intent_balanced_v1:{safe_intent}"
    for item in items:
        profile = _candidate_semantic_profile(item, normalized_task)
        intent_score, rerank_signals = _intent_rerank_score({**item, "_semantic_profile": profile}, safe_intent)
        item["_semantic_profile"] = profile
        item["_intent_score"] = round(float(intent_score), 4)
        item["_rerank_signals"] = rerank_signals
    if str(sort_by or "").strip() == "time_desc":
        items.sort(key=lambda item: (str(item.get("published_at") or ""), float(item.get("_intent_score") or 0.0)), reverse=True)
        selected_items = items[: offset + requested_limit]
    elif str(sort_by or "").strip() == "time_asc":
        items.sort(key=lambda item: (str(item.get("published_at") or ""), -float(item.get("_intent_score") or 0.0)))
        selected_items = items[: offset + requested_limit]
    else:
        items.sort(key=lambda item: (-float(item.get("_intent_score") or 0.0), -float(item.get("score") or 0.0)))
        selected_items = _select_intent_diverse_items(items, intent=safe_intent, total_needed=offset + requested_limit)
    page_items = selected_items[offset : offset + requested_limit]
    cards = [_map_item_to_card(item, normalized_task, index + offset) for index, item in enumerate(page_items)]
    source_scope = resolve_source_scope(
        str(normalized_task.get("topic_identifier") or "").strip(),
        str(scope_range.get("start") or time_range.get("start") or "").strip(),
        str(scope_range.get("end") or time_range.get("end") or "").strip(),
    )
    source_quality_flags = ["query_rewrite_enabled"] if len(query_variants) > 1 else []
    if legacy_adapter_hit and "legacy_adapter_hit" not in source_quality_flags:
        source_quality_flags.append("legacy_adapter_hit")
    for flag in [str(item).strip() for item in (scope_meta.get("scope_flags") or []) if str(item or "").strip()]:
        if flag not in source_quality_flags:
            source_quality_flags.append(flag)
    coverage = _coverage_payload(
        matched_count=len(items),
        sampled_count=len(cards),
        raw_matched_count=matched_records,
        deduped_candidate_count=len(items),
        returned_card_count=len(cards),
        source_resolution=str(source_scope.get("source_resolution") or "").strip(),
        resolved_fetch_range=source_scope.get("resolved_fetch_range") if isinstance(source_scope.get("resolved_fetch_range"), dict) else {},
        resolved_source_files=[str(item).strip() for item in (source_scope.get("source_files") or []) if str(item or "").strip()],
        requested_time_range=scope_meta.get("requested_time_range") if isinstance(scope_meta.get("requested_time_range"), dict) else {},
        effective_time_range=scope_meta.get("effective_time_range") if isinstance(scope_meta.get("effective_time_range"), dict) else {},
        contract_topic_identifier=str((normalized_task.get("task_contract") or {}).get("topic_identifier") or normalized_task.get("topic_identifier") or "").strip(),
        effective_topic_identifier=str(normalized_task.get("topic_identifier") or "").strip(),
        contract_mismatch=False,
        platform_counts=dict(source_distribution),
        date_span={"start": min((_extract_date(card.get("published_at")) for card in cards), default=""), "end": max((_extract_date(card.get("published_at")) for card in cards), default="")},
        readiness_flags=["cards_available"] if cards else ["no_cards"],
        source_quality_flags=source_quality_flags,
    )
    counterevidence = [card for card in cards if float(card.get("contradiction_signal") or 0.0) >= 0.7][:4]
    retrieval_strategy = "+".join(sorted([mode for mode in retrieval_modes if mode])) or "hybrid_lexical_semantic"
    dominant_signals = _unique_strings(
        [signal for item in page_items for signal in (item.get("_rerank_signals") or []) if str(signal or "").strip()],
        max_items=10,
    )
    return {
        "result": cards,
        "legacy_adapter_hit": legacy_adapter_hit,
        "legacy_input_kind": legacy_input_kind,
        "contract_binding_failed": False,
        "violation_origin": execution_view.get("violation_origin") or "",
        "repair_action": execution_view.get("repair_action") or "none",
        "contract_value": execution_view.get("contract_value") or {},
        "agent_proposed_value": execution_view.get("agent_proposed_value") or {},
        "effective_value": execution_view.get("effective_value") or {},
        **_base_result(
            normalized_task=normalized_task,
            tool_name="retrieve_evidence_cards",
            coverage=coverage,
            counterevidence=counterevidence,
            confidence=min(0.98, 0.55 + len(cards) * 0.03),
            trace=_trace_payload(
                cards,
                offset=offset,
                total=len(items),
                retrieval_strategy=retrieval_strategy,
                rewrite_queries=query_variants,
                compression_applied=True,
                contract_id=str(execution_view.get("contract_id") or "").strip(),
                derivation_id=str((execution_view.get("task_derivation") or {}).get("derivation_id") or "").strip(),
                requested_scope=scope_meta.get("requested_time_range") if isinstance(scope_meta.get("requested_time_range"), dict) else {},
                effective_scope=scope_range,
                requested_intent=requested_intent,
                allowed_intents=allowed_intents,
                compiled_tool_intents=[safe_intent],
                rerank_policy=rerank_policy,
                dominant_signals=dominant_signals,
            ),
            error_hint=None,
        ),
    }


def retrieve_evidence_bundle_payload(
    *,
    contract_id: str = "",
    evidence_need: str,
    display_label: str = "",
    retrieval_scope_json: str = "{}",
    filters_json: str = "{}",
    sort_by: str = "relevance",
    limit: int = 12,
    cursor: str = "",
) -> Dict[str, Any]:
    normalized_need = _normalize_evidence_need(evidence_need)
    compiled_tool_intents = _compile_evidence_need_to_tool_intents(normalized_need)
    normalized_task = _resolve_task_execution_view(
        contract_id=contract_id,
        retrieval_scope_json=retrieval_scope_json,
    ).get("normalized_task")
    normalized_task = normalized_task if isinstance(normalized_task, dict) else {}
    effective_display_label = _display_label_for_evidence_need(normalized_need, display_label or evidence_need)
    requested_scope = _resolve_task_execution_view(
        contract_id=contract_id,
        retrieval_scope_json=retrieval_scope_json,
    ).get("scope_meta")
    requested_scope = requested_scope if isinstance(requested_scope, dict) else {}
    if not normalized_need or not compiled_tool_intents:
        coverage = _coverage_payload(
            matched_count=0,
            sampled_count=0,
            source_resolution="invalid_evidence_need",
            requested_time_range=requested_scope.get("requested_time_range") if isinstance(requested_scope.get("requested_time_range"), dict) else {},
            effective_time_range=requested_scope.get("effective_time_range") if isinstance(requested_scope.get("effective_time_range"), dict) else {},
            effective_topic_identifier=str(normalized_task.get("topic_identifier") or "").strip(),
            field_gaps=["evidence_need"],
            readiness_flags=["invalid_evidence_need"],
        )
        return {
            "result": [],
            **_base_result(
                normalized_task=normalized_task,
                tool_name="retrieve_evidence_bundle",
                coverage=coverage,
                confidence=0.0,
                trace=_trace_payload(
                    [],
                    offset=0,
                    total=0,
                    contract_id=str(contract_id or "").strip(),
                    requested_scope=requested_scope.get("requested_time_range") if isinstance(requested_scope.get("requested_time_range"), dict) else {},
                    effective_scope=requested_scope.get("effective_time_range") if isinstance(requested_scope.get("effective_time_range"), dict) else {},
                    display_label=effective_display_label,
                    evidence_need=_normalize_text(evidence_need),
                    compiled_tool_intents=[],
                    allowed_intents=list(_TOOL_INTENT_ALLOWED),
                ),
                error_hint="evidence_need 不合法；编排层仅接受 overview|timeline|actors|controversy|risk。",
            ),
        }
    pages = [
        retrieve_evidence_cards_payload(
            contract_id=contract_id,
            retrieval_scope_json=retrieval_scope_json,
            intent=tool_intent,
            filters_json=filters_json,
            sort_by=sort_by,
            limit=limit,
            cursor=cursor,
        )
        for tool_intent in compiled_tool_intents
    ]
    merged_cards: Dict[str, Dict[str, Any]] = {}
    merged_counterevidence: Dict[str, Dict[str, Any]] = {}
    platform_counts: Counter[str] = Counter()
    matched_count = 0
    invalid_flags: List[str] = []
    coverage_template: Dict[str, Any] = {}
    rewrite_queries: List[str] = []
    retrieval_strategies: List[str] = []
    for page in pages:
        coverage = page.get("coverage") if isinstance(page.get("coverage"), dict) else {}
        trace = page.get("trace") if isinstance(page.get("trace"), dict) else {}
        if not coverage_template:
            coverage_template = coverage
        matched_count += int(coverage.get("matched_count") or 0)
        platform_counts.update({str(key): int(value) for key, value in (coverage.get("platform_counts") or {}).items()})
        for flag in [str(item).strip() for item in (coverage.get("readiness_flags") or []) if str(item or "").strip()]:
            if flag.startswith("invalid_") and flag not in invalid_flags:
                invalid_flags.append(flag)
        for query in [str(item).strip() for item in (trace.get("rewrite_queries") or []) if str(item or "").strip()]:
            if query not in rewrite_queries:
                rewrite_queries.append(query)
        strategy = str(trace.get("retrieval_strategy") or "").strip()
        if strategy and strategy not in retrieval_strategies:
            retrieval_strategies.append(strategy)
        for collection, target in ((page.get("result"), merged_cards), (page.get("counterevidence"), merged_counterevidence)):
            for item in [dict(row) for row in (collection or []) if isinstance(row, dict)]:
                dedupe_key = str(item.get("source_id") or item.get("evidence_id") or "").strip() or json.dumps(item, ensure_ascii=False, sort_keys=True)
                existing = target.get(dedupe_key)
                if existing is None or float(item.get("score") or 0.0) > float(existing.get("score") or 0.0):
                    target[dedupe_key] = item
    cards = list(merged_cards.values())
    counterevidence = list(merged_counterevidence.values())
    cards.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item.get("published_at") or "")), reverse=False)
    if str(sort_by or "").strip() == "time_desc":
        cards.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
    elif str(sort_by or "").strip() == "time_asc":
        cards.sort(key=lambda item: str(item.get("published_at") or ""))
    if invalid_flags:
        return {
            "result": [],
            **_base_result(
                normalized_task=normalized_task,
                tool_name="retrieve_evidence_bundle",
                coverage=_coverage_payload(
                    matched_count=0,
                    sampled_count=0,
                    source_resolution=coverage_template.get("source_resolution") or "invalid_intent",
                    requested_time_range=coverage_template.get("requested_time_range") if isinstance(coverage_template.get("requested_time_range"), dict) else {},
                    effective_time_range=coverage_template.get("effective_time_range") if isinstance(coverage_template.get("effective_time_range"), dict) else {},
                    contract_topic_identifier=str(coverage_template.get("contract_topic_identifier") or "").strip(),
                    effective_topic_identifier=str(coverage_template.get("effective_topic_identifier") or "").strip(),
                    field_gaps=["intent"],
                    readiness_flags=invalid_flags,
                ),
                confidence=0.0,
                trace=_trace_payload(
                    [],
                    offset=0,
                    total=0,
                    retrieval_strategy="+".join(retrieval_strategies),
                    rewrite_queries=rewrite_queries,
                    compression_applied=True,
                    contract_id=str(contract_id or "").strip(),
                    requested_scope=coverage_template.get("requested_time_range") if isinstance(coverage_template.get("requested_time_range"), dict) else {},
                    effective_scope=coverage_template.get("effective_time_range") if isinstance(coverage_template.get("effective_time_range"), dict) else {},
                    display_label=effective_display_label,
                    evidence_need=normalized_need,
                    compiled_tool_intents=compiled_tool_intents,
                    allowed_intents=list(_TOOL_INTENT_ALLOWED),
                ),
                error_hint="编排层需求已展开，但某个工具层 intent 非法，已阻止继续把 ABI 错误伪装成空召回。",
            ),
        }
    coverage = _coverage_payload(
        matched_count=matched_count,
        sampled_count=len(cards),
        source_resolution=str(coverage_template.get("source_resolution") or "").strip(),
        resolved_fetch_range=coverage_template.get("resolved_fetch_range") if isinstance(coverage_template.get("resolved_fetch_range"), dict) else {},
        resolved_source_files=[str(item).strip() for item in (coverage_template.get("resolved_source_files") or []) if str(item or "").strip()],
        requested_time_range=coverage_template.get("requested_time_range") if isinstance(coverage_template.get("requested_time_range"), dict) else {},
        effective_time_range=coverage_template.get("effective_time_range") if isinstance(coverage_template.get("effective_time_range"), dict) else {},
        contract_topic_identifier=str(coverage_template.get("contract_topic_identifier") or "").strip(),
        effective_topic_identifier=str(coverage_template.get("effective_topic_identifier") or "").strip(),
        contract_mismatch=bool(coverage_template.get("contract_mismatch")),
        platform_counts=dict(platform_counts),
        date_span={"start": min((_extract_date(card.get("published_at")) for card in cards), default=""), "end": max((_extract_date(card.get("published_at")) for card in cards), default="")},
        field_gaps=[str(item).strip() for item in (coverage_template.get("field_gaps") or []) if str(item or "").strip()],
        missing_sources=[str(item).strip() for item in (coverage_template.get("missing_sources") or []) if str(item or "").strip()],
        source_quality_flags=list(dict.fromkeys(
            [str(item).strip() for item in (coverage_template.get("source_quality_flags") or []) if str(item or "").strip()]
            + (["compiled_multi_intent"] if len(compiled_tool_intents) > 1 else [])
        )),
        readiness_flags=["cards_available"] if cards else ["true_empty_evidence"],
    )
    return {
        "result": cards,
        "counterevidence": counterevidence,
        **_base_result(
            normalized_task=normalized_task,
            tool_name="retrieve_evidence_bundle",
            coverage=coverage,
            confidence=min(0.98, 0.55 + len(cards) * 0.03),
            trace=_trace_payload(
                cards,
                offset=0,
                total=len(cards),
                retrieval_strategy="+".join(retrieval_strategies),
                rewrite_queries=rewrite_queries,
                compression_applied=True,
                contract_id=str(contract_id or "").strip(),
                requested_scope=coverage_template.get("requested_time_range") if isinstance(coverage_template.get("requested_time_range"), dict) else {},
                effective_scope=coverage_template.get("effective_time_range") if isinstance(coverage_template.get("effective_time_range"), dict) else {},
                display_label=effective_display_label,
                evidence_need=normalized_need,
                compiled_tool_intents=compiled_tool_intents,
                allowed_intents=list(_TOOL_INTENT_ALLOWED),
            ),
            error_hint=None,
        ),
    }


def build_event_timeline_payload(*, normalized_task_json: str, evidence_ids_json: str = "[]", max_nodes: int = 8) -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="timeline", fallback_limit=max(8, max_nodes * 2))
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for card in cards:
        grouped.setdefault(_extract_date(card.get("published_at")) or "未知", []).append(card)
    nodes: List[Dict[str, Any]] = []
    for index, date_text in enumerate(sorted(grouped.keys())[: max(1, min(int(max_nodes or 8), 12))]):
        bucket = grouped[date_text]
        support_ids = [str(card.get("evidence_id") or "").strip() for card in bucket if str(card.get("evidence_id") or "").strip()]
        conflict_ids = [str(card.get("evidence_id") or "").strip() for card in bucket if float(card.get("contradiction_signal") or 0.0) >= 0.7]
        lead = bucket[0] if bucket else {}
        nodes.append({"node_id": f"timeline-{index + 1}", "time_label": date_text, "summary": _normalize_text(lead.get("title") or lead.get("snippet")), "support_evidence_ids": support_ids, "conflict_evidence_ids": conflict_ids, "confidence": round(min(0.98, 0.4 + len(bucket) * 0.08), 4), "event_type": "peak" if len(bucket) > 1 else "event"})
    coverage = _coverage_payload(matched_count=len(cards), sampled_count=len(nodes), date_span={"start": min(grouped.keys(), default=""), "end": max(grouped.keys(), default="")}, readiness_flags=["timeline_ready"] if nodes else ["timeline_empty"])
    error_hint = None
    if not nodes:
        if evidence_ids_json == "[]" or not str(evidence_ids_json or "").strip() or str(evidence_ids_json or "").strip() in {"[]", "{}", "null"}:
            error_hint = "build_event_timeline 需要传入 evidence_ids_json 参数。请将 evidence_cards.json 中的 result 数组作为 evidence_ids_json 参数传入，不能为空或默认值。"
        elif not cards:
            error_hint = "传入的 evidence_ids_json 无法解析或 contract 绑定失败。请确保传入有效的证据卡数组，并确保 normalized_task_json 包含完整的 task_contract（含 topic_identifier 和 start 字段）。"
    return {"result": nodes, **_base_result(normalized_task=normalized_task, tool_name="build_event_timeline", coverage=coverage, confidence=min(0.96, 0.5 + len(nodes) * 0.06), trace=_trace_payload(cards, offset=0, total=len(cards)), error_hint=error_hint)}


def compute_report_metrics_payload(*, normalized_task_json: str, metric_scope: str = "overview", evidence_ids_json: str = "[]") -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    safe_scope = str(metric_scope or "overview").strip().lower()
    if safe_scope not in _METRIC_SCOPE_ALLOWED:
        safe_scope = "overview"
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="overview", fallback_limit=18)
    platform_counts: Counter[str] = Counter(str(card.get("platform") or "未知").strip() or "未知" for card in cards)
    date_counts: Counter[str] = Counter(_extract_date(card.get("published_at")) or "未知" for card in cards)
    metrics: List[Dict[str, Any]] = []
    if safe_scope in {"overview", "volume"}:
        metrics.append({"metric_id": f"{safe_scope}-total", "label": "evidence_count", "value": float(len(cards)), "dimension": safe_scope, "detail": "当前指标范围内的证据卡数量", "metric_family": "volume"})
    if safe_scope in {"overview", "platform"}:
        metrics.append({"metric_id": f"{safe_scope}-platforms", "label": "platform_count", "value": float(len([name for name, count in platform_counts.items() if count > 0])), "dimension": safe_scope, "detail": "覆盖到的平台数量", "metric_family": "platform"})
    if safe_scope in {"overview", "temporal"}:
        metrics.append({"metric_id": f"{safe_scope}-peak-day", "label": "peak_day_volume", "value": float(max(date_counts.values(), default=0)), "dimension": safe_scope, "detail": "单日证据峰值", "metric_family": "temporal"})
    chart_data_refs: List[Dict[str, Any]] = []
    if safe_scope in {"overview", "platform"}:
        chart_data_refs.append({"chart_id": f"{safe_scope}:platform-share", "type": "bar", "metric_family": "platform", "rows": [{"name": name, "value": count} for name, count in platform_counts.most_common(8)]})
    if safe_scope in {"overview", "temporal"}:
        chart_data_refs.append({"chart_id": f"{safe_scope}:timeline-count", "type": "line", "metric_family": "temporal", "rows": [{"name": name, "value": count} for name, count in sorted(date_counts.items())]})
    coverage = _coverage_payload(matched_count=len(cards), sampled_count=len(metrics), platform_counts=dict(platform_counts), date_span={"start": min(date_counts.keys(), default=""), "end": max(date_counts.keys(), default="")}, readiness_flags=["metric_ready"] if cards else ["metric_empty"])
    error_hint = None
    if not cards:
        if evidence_ids_json == "[]" or not str(evidence_ids_json or "").strip() or str(evidence_ids_json or "").strip() in {"[]", "{}", "null"}:
            error_hint = "compute_report_metrics 需要传入 evidence_ids_json 参数。请将 evidence_cards.json 中的 result 数组作为参数传入，不能为空或默认值。"
        else:
            error_hint = "传入的 evidence_ids_json 无法解析或 contract 绑定失败。请确保传入有效的证据卡数组。"
    return {"result": metrics, "metric_scope": safe_scope, "chart_data_refs": chart_data_refs, **_base_result(normalized_task=normalized_task, tool_name="compute_report_metrics", coverage=coverage, confidence=min(0.94, 0.45 + len(cards) * 0.03), trace=_trace_payload(cards, offset=0, total=len(cards)), error_hint=error_hint)}


def extract_actor_positions_payload(*, normalized_task_json: str, evidence_ids_json: str = "[]", actor_limit: int = 10) -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="overview", fallback_limit=max(12, actor_limit * 2))
    actor_counter: Dict[str, Dict[str, Any]] = {}
    for card in cards:
        actor_names = [tag for tag in (card.get("entity_tags") or []) if str(tag or "").strip()] or [str(card.get("platform") or "未知").strip()]
        for name in actor_names[:2]:
            current = actor_counter.setdefault(name, {"actor_id": f"actor-{_normalize_key(name)}", "name": name, "stance": str(card.get("stance_hint") or "neutral"), "stance_shift": "stable", "representative_evidence_ids": [], "conflict_actor_ids": [], "confidence": 0.0})
            current["representative_evidence_ids"].append(str(card.get("evidence_id") or "").strip())
            current["confidence"] = round(min(0.98, float(current["confidence"]) + 0.18), 4)
    actors = sorted(actor_counter.values(), key=lambda item: (-len(item["representative_evidence_ids"]), item["name"]))[: max(1, min(int(actor_limit or 10), 16))]
    if len(actors) >= 2:
        leader_id = str(actors[0].get("actor_id") or "").strip()
        for actor in actors[1:3]:
            actor["conflict_actor_ids"] = [leader_id] if leader_id else []
    coverage = _coverage_payload(matched_count=len(cards), sampled_count=len(actors), platform_counts=dict(Counter(str(card.get("platform") or "未知").strip() for card in cards)), readiness_flags=["actor_ready"] if actors else ["actor_empty"])
    return {"actors": actors, "result": actors, **_base_result(normalized_task=normalized_task, tool_name="extract_actor_positions", coverage=coverage, confidence=min(0.9, 0.4 + len(actors) * 0.06), trace=_trace_payload(cards, offset=0, total=len(cards)), error_hint=None)}


def build_discourse_conflict_map_payload(*, normalized_task_json: str, evidence_ids_json: str = "[]", actor_positions_json: str = "[]") -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="risk", fallback_limit=16)
    actors = _safe_parse_json(actor_positions_json, [])
    if isinstance(actors, dict):
        actors = actors.get("result") if isinstance(actors.get("result"), list) else []
    if not isinstance(actors, list):
        actors = []
    refute_cards = [card for card in cards if float(card.get("contradiction_signal") or 0.0) >= 0.7]
    actor_names = [str(item.get("name") or "").strip() for item in actors if isinstance(item, dict) and str(item.get("name") or "").strip()]
    axes: List[Dict[str, Any]] = []
    if refute_cards or len(actor_names) >= 2:
        axes.append({"axis_id": "axis-main", "title": "官方叙事与质疑叙事的冲突", "opposing_sides": actor_names[:2] or ["传播方", "反驳方"], "focus_shift_path": ["事实发布", "争议扩散", "辟谣/反驳"], "intensity": round(min(0.95, 0.35 + len(refute_cards) * 0.12 + len(actor_names) * 0.04), 4), "trigger_evidence_ids": [str(card.get("evidence_id") or "").strip() for card in refute_cards[:5]]})
    coverage = _coverage_payload(matched_count=len(cards), sampled_count=len(axes), readiness_flags=["conflict_map_ready"] if axes else ["conflict_map_thin"])
    return {"axes": axes, "summary": "；".join([axis["title"] for axis in axes]) if axes else "当前证据中尚未形成稳定的争议轴。", **_base_result(normalized_task=normalized_task, tool_name="build_discourse_conflict_map", coverage=coverage, confidence=min(0.9, 0.4 + len(axes) * 0.12), trace=_trace_payload(cards, offset=0, total=len(cards)))}


def _infer_actor_role_type(cards: List[Dict[str, Any]], actor_name: str) -> str:
    text = " ".join(
        [
            str(card.get("author_type") or "").strip()
            for card in cards
            if actor_name in [str(tag).strip() for tag in (card.get("entity_tags") or [])]
        ]
    )
    if any(token in text for token in ("官方", "政务", "政府", "机构")):
        return "official"
    if any(token in text for token in ("媒体", "记者", "报")):
        return "media"
    return "public"


def _infer_actor_facets(cards: List[Dict[str, Any]], actor_name: str) -> Dict[str, str]:
    text = " ".join(
        [
            " ".join(
                [
                    str(card.get("author_type") or "").strip(),
                    str(card.get("platform") or "").strip(),
                    str(card.get("title") or "").strip(),
                ]
            )
            for card in cards
            if actor_name in [str(tag).strip() for tag in (card.get("entity_tags") or [])]
        ]
    )
    role_type = _infer_actor_role_type(cards, actor_name)
    organization_type = "government" if any(token in text for token in ("政府", "卫健委", "官方", "政务")) else "media" if role_type == "media" else "community"
    speaker_role = "primary" if role_type in {"official", "media"} else "observer"
    relay_role = "bridge" if any(token in text for token in ("转发", "转载", "搬运", "扩散")) else "origin"
    return {
        "role_type": role_type,
        "organization_type": organization_type,
        "speaker_role": speaker_role,
        "relay_role": relay_role,
    }


def build_claim_actor_conflict_payload(
    *,
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    actor_positions_json: str = "[]",
    timeline_nodes_json: str = "[]",
) -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="overview", fallback_limit=18)
    actors = _safe_parse_json(actor_positions_json, [])
    if isinstance(actors, dict):
        actors = actors.get("result") if isinstance(actors.get("result"), list) else actors.get("actors", [])
    if not isinstance(actors, list):
        actors = []
    timeline_nodes = _safe_parse_json(timeline_nodes_json, [])
    if isinstance(timeline_nodes, dict):
        timeline_nodes = timeline_nodes.get("result") if isinstance(timeline_nodes.get("result"), list) else []
    if not isinstance(timeline_nodes, list):
        timeline_nodes = []

    claim_records: List[ClaimRecord] = []
    claim_ids_by_evidence: Dict[str, str] = {}
    for index, card in enumerate(cards[:10], start=1):
        evidence_id = str(card.get("evidence_id") or "").strip()
        proposition = _normalize_text(card.get("title") or card.get("snippet"))
        if not evidence_id or not proposition:
            continue
        contradiction_signal = float(card.get("contradiction_signal") or 0.0)
        verification_status = (
            "sustained_conflict"
            if contradiction_signal >= 0.8
            else "converged"
            if float(card.get("confidence") or 0.0) >= 0.65
            else "pending_verification"
        )
        claim = ClaimRecord(
            claim_id=f"claimrec-{index}",
            proposition=proposition,
            proposition_slots=_proposition_slots(proposition),
            raw_spans=_unique_strings([str(card.get("title") or ""), str(card.get("snippet") or "")], max_items=2),
            time_anchor=_extract_date(card.get("published_at")),
            source_ids=_unique_strings([str(card.get("source_id") or ""), str(card.get("platform") or "")], max_items=4),
            verification_status=verification_status,
            evidence_coverage="high" if float(card.get("confidence") or 0.0) >= 0.7 else "partial",
            source_diversity=len(_unique_strings([str(card.get("platform") or ""), str(card.get("author_type") or ""), str(card.get("source_id") or "")], max_items=6)),
            temporal_confidence=1.0 if _extract_date(card.get("published_at")) else 0.4,
            evidence_density=round(min(1.0, 0.3 + float(card.get("confidence") or 0.0) + contradiction_signal * 0.2), 4),
        )
        claim_records.append(claim)
        claim_ids_by_evidence[evidence_id] = claim.claim_id

    actor_models: List[ActorPosition] = []
    for item in actors[:10]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        evidence_refs = [str(value).strip() for value in (item.get("representative_evidence_ids") or []) if str(value or "").strip()]
        claim_ids = [claim_ids_by_evidence[evidence_id] for evidence_id in evidence_refs if claim_ids_by_evidence.get(evidence_id)]
        facets = _infer_actor_facets(cards, name)
        actor_models.append(
            ActorPosition(
                actor_id=str(item.get("actor_id") or f"actor-{_normalize_key(name)}").strip(),
                name=name,
                aliases=_unique_strings([name, *([str(alias).strip() for alias in (item.get("aliases") or []) if str(alias or "").strip()])], max_items=4),
                role_type=str(item.get("role_type") or facets["role_type"]).strip(),
                organization_type=str(item.get("organization_type") or facets["organization_type"]).strip(),
                speaker_role=str(item.get("speaker_role") or facets["speaker_role"]).strip(),
                relay_role=str(item.get("relay_role") or facets["relay_role"]).strip(),
                account_tier=str(item.get("account_tier") or ("primary" if len(evidence_refs) >= 2 else "secondary")).strip(),
                is_official=bool(item.get("is_official")) or str(item.get("role_type") or facets["role_type"]).strip() == "official",
                stance=str(item.get("stance") or "neutral").strip(),
                stance_shift=str(item.get("stance_shift") or "stable").strip(),
                claim_ids=_unique_strings(claim_ids, max_items=6),
                representative_evidence_ids=evidence_refs[:6],
                conflict_actor_ids=[str(value).strip() for value in (item.get("conflict_actor_ids") or []) if str(value or "").strip()][:4],
                confidence=round(float(item.get("confidence") or 0.0), 4),
            )
        )

    targets: List[TargetObject] = []
    target_ids_by_key: Dict[str, str] = {}
    arguments: List[ArgumentUnit] = []
    support_edges: List[SupportEdge] = []
    attack_edges: List[AttackEdge] = []
    for index, claim in enumerate(claim_records, start=1):
        slots = claim.proposition_slots or {}
        target_label = str(slots.get("object") or slots.get("subject") or claim.proposition).strip()[:80]
        if not target_label:
            continue
        target_key = _normalize_key(target_label)
        target_id = target_ids_by_key.setdefault(target_key, f"target-{target_key}")
        if not any(item.target_id == target_id for item in targets):
            targets.append(
                TargetObject(
                    target_id=target_id,
                    target_type="policy_subject" if any(token in target_label for token in ("政策", "规则", "通知", "安排")) else "discussion_target",
                    label=target_label,
                    scope="public" if claim.source_diversity >= 2 else "specific",
                )
            )
        evidence_refs = [evidence_id for evidence_id, claim_id in claim_ids_by_evidence.items() if claim_id == claim.claim_id][:4]
        argument_type = "attack" if str(slots.get("polarity") or "") == "refute" or str(slots.get("qualifier") or "") == "negative" else "support"
        argument_id = f"argument-{index}"
        argument_unit = ArgumentUnit(
            argument_id=argument_id,
            claim_id=claim.claim_id,
            target_id=target_id,
            argument_type=argument_type,
            raw_span=(claim.raw_spans[0] if claim.raw_spans else claim.proposition),
            evidence_refs=evidence_refs,
            evidence_type=_evidence_type(next((card for card in cards if str(card.get('evidence_id') or '').strip() in evidence_refs), {})),
            conversation_position={
                "thread_scope": "report_scope",
                "reply_role": "origin" if argument_type == "support" else "reply",
                "turn_index": index,
            },
        )
        arguments.append(argument_unit)
        relation_confidence = round(min(0.94, 0.48 + claim.evidence_density * 0.4), 4)
        if argument_type == "support":
            support_edges.append(
                SupportEdge(
                    edge_id=f"support-{index}",
                    argument_id=argument_id,
                    target_claim_id=claim.claim_id,
                    confidence=relation_confidence,
                )
            )
        else:
            attack_edges.append(
                AttackEdge(
                    edge_id=f"attack-{index}",
                    argument_id=argument_id,
                    target_claim_id=claim.claim_id,
                    confidence=relation_confidence,
                )
            )

    edges: List[ConflictEdge] = []
    for index, claim in enumerate(claim_records, start=1):
        linked_evidence = next((card for card in cards if claim_ids_by_evidence.get(str(card.get("evidence_id") or "").strip()) == claim.claim_id), {})
        contradiction_signal = float(linked_evidence.get("contradiction_signal") or 0.0)
        conflict_type = (
            "direct_contradiction"
            if contradiction_signal >= 0.85
            else "evidence_conflict"
            if contradiction_signal >= 0.7
            else "temporal_misalignment"
            if claim.time_anchor and any(str(node.get("time_label") or "").strip() and str(node.get("time_label") or "").strip() != claim.time_anchor for node in timeline_nodes[:2])
            else "actor_mismatch"
            if len([actor for actor in actor_models if claim.claim_id in actor.claim_ids]) >= 2
            else "attribution_conflict"
        )
        if claim.verification_status == "converged" and contradiction_signal < 0.7:
            continue
        actor_scope = [actor.actor_id for actor in actor_models if claim.claim_id in actor.claim_ids][:4]
        edges.append(
            ConflictEdge(
                edge_id=f"edge-{index}",
                claim_a_id=claim.claim_id,
                claim_b_id=claim.claim_id,
                conflict_type=conflict_type,
                actor_scope=actor_scope,
                time_scope=[claim.time_anchor] if claim.time_anchor else [],
                evidence_refs=[
                    str(linked_evidence.get("evidence_id") or "").strip()
                ]
                if str(linked_evidence.get("evidence_id") or "").strip()
                else [],
                evidence_density=claim.evidence_density,
                confidence=round(min(1.0, 0.45 + contradiction_signal * 0.5 + len(actor_scope) * 0.05), 4),
            )
        )

    resolution_summary: List[ResolutionStatus] = []
    for claim in claim_records:
        linked_edges = [edge for edge in edges if edge.claim_a_id == claim.claim_id or edge.claim_b_id == claim.claim_id]
        status = claim.verification_status
        resolution_summary.append(
            ResolutionStatus(
                claim_id=claim.claim_id,
                status=status,
                reason="证据已收敛" if status == "converged" else "仍存在互相冲突或覆盖不足的来源",
                supporting_claim_ids=[claim.claim_id],
                unresolved_reason="" if status == "converged" else "需要更多跨平台、跨主体证据完成收敛",
                resolution_confidence=round(0.82 if status == "converged" else 0.46 if status == "pending_verification" else 0.38, 4),
            )
        )

    conflict_map = ConflictMap(
        claims=claim_records,
        actor_positions=actor_models,
        targets=targets,
        arguments=arguments,
        support_edges=support_edges,
        attack_edges=attack_edges,
        edges=edges,
        resolution_summary=resolution_summary,
        summary=(
            "当前未形成可回链争议轴。"
            if not claim_records
            else "；".join(
                _unique_strings(
                    [
                        f"共识别 {len(claim_records)} 条断言命题",
                        f"涉及 {len(actor_models)} 个主体位置",
                        f"绑定 {len(targets)} 个目标对象",
                        f"形成 {len(edges)} 条冲突边",
                    ],
                    max_items=4,
                )
            )
        ),
        evidence_density=round(sum(item.evidence_density for item in claim_records) / len(claim_records), 4) if claim_records else 0.0,
        source_diversity=len(_unique_strings([source_id for claim in claim_records for source_id in claim.source_ids], max_items=40)),
    )
    coverage = _coverage_payload(
        matched_count=len(cards),
        sampled_count=len(claim_records),
        platform_counts=dict(Counter(str(card.get("platform") or "未知").strip() for card in cards)),
        readiness_flags=["conflict_map_ready"] if claim_records else ["conflict_map_empty"],
    )
    error_hint = None
    if not claim_records:
        if not cards:
            if evidence_ids_json == "[]" or not str(evidence_ids_json or "").strip() or str(evidence_ids_json or "").strip() in {"[]", "{}", "null"}:
                error_hint = "build_claim_actor_conflict 需要传入 evidence_ids_json 参数。请将 evidence_cards.json 中的 result 数组作为参数传入，不能为空或默认值。"
            else:
                error_hint = "传入的 evidence_ids_json 无法解析或 contract 绑定失败。请确保传入有效的证据卡数组。"
        elif cards and not claim_records:
            error_hint = "证据卡存在但无法生成 claims。请检查证据卡是否包含有效的 title/snippet 字段。"
    return {
        "conflict_map": conflict_map.model_dump(),
        "result": conflict_map.model_dump(),
        **_base_result(
            normalized_task=normalized_task,
            tool_name="build_claim_actor_conflict",
            coverage=coverage,
            confidence=min(0.92, 0.42 + len(claim_records) * 0.05 + len(edges) * 0.04),
            trace=_trace_payload(cards, offset=0, total=len(cards)),
            error_hint=error_hint,
        ),
    }


def build_mechanism_summary_payload(
    *,
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    timeline_nodes_json: str = "[]",
    conflict_map_json: str = "{}",
    metric_refs_json: str = "[]",
) -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="overview", fallback_limit=18)
    timeline_nodes = _safe_parse_json(timeline_nodes_json, [])
    if isinstance(timeline_nodes, dict):
        timeline_nodes = timeline_nodes.get("result") if isinstance(timeline_nodes.get("result"), list) else []
    if not isinstance(timeline_nodes, list):
        timeline_nodes = []
    conflict_map = _safe_parse_json(conflict_map_json, {})
    claims = conflict_map.get("claims") if isinstance(conflict_map.get("claims"), list) else []
    actor_positions = conflict_map.get("actor_positions") if isinstance(conflict_map.get("actor_positions"), list) else []
    metrics = _safe_parse_json(metric_refs_json, [])
    if not isinstance(metrics, list):
        metrics = []

    platforms = _unique_strings([str(card.get("platform") or "").strip() for card in cards if str(card.get("platform") or "").strip()], max_items=6)
    source_actor_ids = _unique_strings(
        [str(actor.get("actor_id") or "").strip() for actor in actor_positions if isinstance(actor, dict)],
        max_items=4,
    )
    bridge_actor_ids = _unique_strings(
        [
            str(actor.get("actor_id") or "").strip()
            for actor in actor_positions
            if isinstance(actor, dict) and len([item for item in (actor.get("representative_evidence_ids") or []) if str(item or "").strip()]) >= 2
        ],
        max_items=4,
    )
    amplification_paths = [
        AmplificationPath(
            path_id="path-main",
            source_actor_ids=source_actor_ids[:2],
            bridge_actor_ids=bridge_actor_ids[:2],
            platform_sequence=platforms[:4],
            linked_claim_ids=[str(item.get("claim_id") or "").strip() for item in claims[:3] if isinstance(item, dict)],
            evidence_refs=[str(card.get("evidence_id") or "").strip() for card in cards[:4] if str(card.get("evidence_id") or "").strip()],
            amplifier_type="cross_platform_bridge" if len(platforms) >= 2 else "media_pickup",
            confidence=round(min(0.92, 0.45 + len(platforms) * 0.07 + len(bridge_actor_ids) * 0.08), 4),
        )
    ] if cards else []

    trigger_events = [
        TriggerEvent(
            event_id=str(node.get("node_id") or f"event-{index}").strip(),
            time_anchor=str(node.get("time_label") or "").strip(),
            description=str(node.get("summary") or "").strip(),
            linked_claim_ids=[str(item.get("claim_id") or "").strip() for item in claims[:2] if isinstance(item, dict)],
            linked_actor_ids=bridge_actor_ids[:2],
            evidence_refs=[str(item).strip() for item in (node.get("support_evidence_ids") or []) if str(item or "").strip()][:4],
            confidence=round(min(0.9, 0.4 + len([str(item).strip() for item in (node.get("support_evidence_ids") or []) if str(item or "").strip()]) * 0.1), 4),
        )
        for index, node in enumerate(timeline_nodes[:3], start=1)
        if isinstance(node, dict)
    ]

    phase_shifts: List[PhaseShift] = []
    if len(trigger_events) >= 2:
        phase_shifts.append(
            PhaseShift(
                phase_id="phase-shift-1",
                from_phase="initial_attention",
                to_phase="conflict_escalation",
                reason="事件节点与冲突命题开始叠加，议题从信息披露转向立场对立。",
                linked_claim_ids=[str(item.get("claim_id") or "").strip() for item in claims[:2] if isinstance(item, dict)],
                evidence_refs=_unique_strings(
                    [*trigger_events[0].evidence_refs[:2], *trigger_events[1].evidence_refs[:2]],
                    max_items=4,
                ),
                confidence=round(min(0.9, 0.5 + len(trigger_events) * 0.08), 4),
            )
        )

    cross_platform_bridges: List[CrossPlatformBridge] = []
    if len(platforms) >= 2:
        cross_platform_bridges.append(
            CrossPlatformBridge(
                bridge_id="bridge-main",
                from_platform=platforms[0],
                to_platform=platforms[1],
                bridge_actor_ids=bridge_actor_ids[:2],
                linked_claim_ids=[str(item.get("claim_id") or "").strip() for item in claims[:2] if isinstance(item, dict)],
                evidence_refs=[str(card.get("evidence_id") or "").strip() for card in cards[:4] if str(card.get("evidence_id") or "").strip()],
                confidence=round(min(0.88, 0.44 + len(bridge_actor_ids) * 0.1), 4),
            )
        )
    bridge_nodes: List[BridgeNode] = [
        BridgeNode(
            node_id=f"bridge-node-{index}",
            actor_id=actor_id,
            platform=platforms[min(index - 1, len(platforms) - 1)] if platforms else "",
            bridge_role="cross_platform_bridge",
            linked_claim_ids=[str(item.get("claim_id") or "").strip() for item in claims[:2] if isinstance(item, dict)],
            evidence_refs=[str(card.get("evidence_id") or "").strip() for card in cards[:3] if str(card.get("evidence_id") or "").strip()],
            confidence=round(min(0.9, 0.46 + index * 0.08), 4),
        )
        for index, actor_id in enumerate(bridge_actor_ids[:3], start=1)
    ]
    cause_candidates: List[CauseCandidate] = []
    if len(trigger_events) >= 2:
        cause_candidates.append(
            CauseCandidate(
                cause_event_id=trigger_events[0].event_id,
                effect_event_id=trigger_events[1].event_id,
                causality_type="event_to_attention_shift",
                confidence=round(min(0.9, 0.5 + len(trigger_events) * 0.08), 4),
                evidence_refs=_unique_strings([*trigger_events[0].evidence_refs, *trigger_events[1].evidence_refs], max_items=4),
            )
        )
    elif trigger_events:
        cause_candidates.append(
            CauseCandidate(
                cause_event_id=trigger_events[0].event_id,
                effect_event_id=trigger_events[0].event_id,
                causality_type="single_event_attention_spike",
                confidence=trigger_events[0].confidence,
                evidence_refs=list(trigger_events[0].evidence_refs[:4]),
            )
        )
    cross_platform_transfers: List[CrossPlatformTransfer] = [
        CrossPlatformTransfer(
            transfer_id=f"transfer-{index}",
            from_platform=bridge.from_platform,
            to_platform=bridge.to_platform,
            bridge_node_ids=[node.node_id for node in bridge_nodes[:2]],
            evidence_refs=list(bridge.evidence_refs[:4]),
        )
        for index, bridge in enumerate(cross_platform_bridges[:2], start=1)
    ]
    narrative_carriers: List[NarrativeCarrier] = [
        NarrativeCarrier(
            carrier_id=f"carrier-{index}",
            actor_id=node.actor_id,
            platform_id=node.platform,
            frame_ids=[],
            transport_role=node.bridge_role or "bridge",
        )
        for index, node in enumerate(bridge_nodes[:3], start=1)
    ]
    refutation_lags: List[RefutationLag] = []
    refute_claim = next(
        (
            item
            for item in claims
            if isinstance(item, dict) and str((item.get("proposition_slots") or {}).get("polarity") or "").strip() == "refute"
        ),
        None,
    )
    if refute_claim and trigger_events:
        refutation_lags.append(
            RefutationLag(
                refutation_id="refutation-lag-1",
                claim_id=str(refute_claim.get("claim_id") or "").strip(),
                refutation_event_id=trigger_events[-1].event_id,
                lag_window="within_range",
                impact_summary="反驳性信息进入传播链后，对原有讨论节奏形成纠偏滞后。",
            )
        )

    confidence_summary = (
        "机制判断因证据不足跳过。"
        if not cards
        else (
            f"基于 {len(cards)} 张证据卡、{len(trigger_events)} 个时间节点、"
            f"{len(metrics)} 组指标与 {len(claims)} 条冲突命题整理传播机制，"
            f"桥接节点 {len(bridge_nodes)} 个，因果候选 {len(cause_candidates)} 条。"
        )
    )
    mechanism_summary = MechanismSummary(
        amplification_paths=amplification_paths,
        trigger_events=trigger_events,
        phase_shifts=phase_shifts,
        cross_platform_bridges=cross_platform_bridges,
        bridge_nodes=bridge_nodes,
        cause_candidates=cause_candidates,
        cross_platform_transfers=cross_platform_transfers,
        narrative_carriers=narrative_carriers,
        refutation_lags=refutation_lags,
        confidence_summary=confidence_summary,
    )
    coverage = _coverage_payload(
        matched_count=len(cards),
        sampled_count=len(amplification_paths) + len(trigger_events) + len(phase_shifts) + len(bridge_nodes) + len(cause_candidates),
        platform_counts=dict(Counter(str(card.get("platform") or "未知").strip() for card in cards)),
        readiness_flags=["mechanism_ready"] if cards else ["mechanism_empty"],
    )
    error_hint = None
    if not cards and not timeline_nodes:
        missing_params = []
        if evidence_ids_json == "[]" or not str(evidence_ids_json or "").strip() or str(evidence_ids_json or "").strip() in {"[]", "{}", "null"}:
            missing_params.append("evidence_ids_json")
        if timeline_nodes_json == "[]" or not str(timeline_nodes_json or "").strip() or str(timeline_nodes_json or "").strip() in {"[]", "{}", "null"}:
            missing_params.append("timeline_nodes_json")
        if missing_params:
            error_hint = f"build_mechanism_summary 需要传入有效的 {', '.join(missing_params)} 参数。请将对应文件的 result 数组作为参数传入，不能为空或默认值。"
        else:
            error_hint = "传入参数无法解析或 contract 绑定失败。请确保 normalized_task_json 包含完整的 task_contract，并传入有效的证据卡和时间节点数组。"
    elif not trigger_events and cards:
        error_hint = "timeline_nodes 为空导致 trigger_events 无法生成。请确保 timeline_nodes_json 传入有效的时间线节点数组（非空 result）。"
    return {
        "mechanism_summary": mechanism_summary.model_dump(),
        "result": mechanism_summary.model_dump(),
        **_base_result(
            normalized_task=normalized_task,
            tool_name="build_mechanism_summary",
            coverage=coverage,
            confidence=min(0.9, 0.4 + len(trigger_events) * 0.08 + len(cross_platform_bridges) * 0.08),
            trace=_trace_payload(cards, offset=0, total=len(cards)),
            error_hint=error_hint,
        ),
    }


def judge_decision_utility_payload(
    *,
    normalized_task_json: str,
    risk_signals_json: str = "[]",
    recommendation_candidates_json: str = "[]",
    unresolved_points_json: str = "[]",
    agenda_frame_map_json: str = "{}",
    conflict_map_json: str = "{}",
    mechanism_summary_json: str = "{}",
    actor_positions_json: str = "[]",
) -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)

    def _unwrap_named_result(payload: Any, *keys: str) -> Any:
        current = payload
        if not isinstance(current, dict):
            return current
        result = current.get("result")
        if isinstance(result, dict):
            current = result
        for key in keys:
            nested = current.get(key) if isinstance(current, dict) else None
            if isinstance(nested, dict):
                return nested
        return current

    risks = _safe_parse_json(risk_signals_json, [])
    if isinstance(risks, dict):
        risks = risks.get("result") if isinstance(risks.get("result"), list) else risks.get("risks", [])
    if not isinstance(risks, list):
        risks = []
    recommendations = _safe_parse_json(recommendation_candidates_json, [])
    if not isinstance(recommendations, list):
        recommendations = []
    unresolved_points = _safe_parse_json(unresolved_points_json, [])
    if not isinstance(unresolved_points, list):
        unresolved_points = []
    agenda_frame_map = _unwrap_named_result(_safe_parse_json(agenda_frame_map_json, {}), "agenda_frame_map")
    if not isinstance(agenda_frame_map, dict):
        agenda_frame_map = {}
    conflict_map = _unwrap_named_result(_safe_parse_json(conflict_map_json, {}), "conflict_map")
    if not isinstance(conflict_map, dict):
        conflict_map = {}
    mechanism_summary = _unwrap_named_result(_safe_parse_json(mechanism_summary_json, {}), "mechanism_summary")
    if not isinstance(mechanism_summary, dict):
        mechanism_summary = {}
    actor_positions = _safe_parse_json(actor_positions_json, [])
    if isinstance(actor_positions, dict):
        actor_positions = actor_positions.get("result") if isinstance(actor_positions.get("result"), list) else actor_positions.get("actors", [])
    if not isinstance(actor_positions, list):
        actor_positions = []

    has_object_scope = bool(normalized_task.get("entities") or conflict_map.get("actor_positions") or actor_positions)
    has_time_window = bool((normalized_task.get("time_range") or {}).get("start") and (normalized_task.get("time_range") or {}).get("end"))
    has_key_actors = len(actor_positions) > 0 or len(conflict_map.get("actor_positions") or []) > 0
    has_primary_contradiction = bool(conflict_map.get("edges") or conflict_map.get("claims")) or any(
        str(item.get("status") or "").strip() == "sustained_conflict"
        for item in (conflict_map.get("resolution_summary") or [])
        if isinstance(item, dict)
    )
    has_mechanism_explanation = bool(mechanism_summary.get("trigger_events") or mechanism_summary.get("amplification_paths") or mechanism_summary.get("cause_candidates"))
    has_issue_frame_context = bool(agenda_frame_map.get("issues") or agenda_frame_map.get("frames"))
    has_conditional_risk = any(str(item.get("spread_condition") or "").strip() for item in risks if isinstance(item, dict))
    has_actionable_recommendations = any(
        str(item.get("action") or "").strip() and str(item.get("rationale") or "").strip()
        for item in recommendations
        if isinstance(item, dict)
    )
    recommendation_has_object = any(
        bool(str(item.get("target") or "").strip()) or has_object_scope
        for item in recommendations
        if isinstance(item, dict)
    )
    recommendation_has_time = has_time_window or any(bool(str(item.get("time_window") or "").strip()) for item in recommendations if isinstance(item, dict))
    recommendation_has_action = any(bool(str(item.get("action") or "").strip()) for item in recommendations if isinstance(item, dict))
    recommendation_has_preconditions = any(
        bool(str(item.get("preconditions") or "").strip()) or bool(item.get("preconditions"))
        for item in recommendations
        if isinstance(item, dict)
    )
    recommendation_has_side_effects = any(
        bool(str(item.get("side_effects") or "").strip()) or bool(str(item.get("boundary") or "").strip())
        for item in recommendations
        if isinstance(item, dict)
    ) or bool(unresolved_points)
    has_uncertainty_boundary = len(unresolved_points) > 0 or any(
        str(item.get("unresolved_reason") or "").strip()
        for item in (conflict_map.get("resolution_summary") or [])
        if isinstance(item, dict)
    )
    empty_corpus = any(
        "empty_corpus" in str(item.get("reason") or "").strip()
        for item in unresolved_points
        if isinstance(item, dict)
    )
    empty_evidence = (
        not risks
        and not recommendations
        and not (conflict_map.get("claims") or [])
        and not (mechanism_summary.get("trigger_events") or mechanism_summary.get("amplification_paths") or mechanism_summary.get("cause_candidates"))
    )
    insufficient_structure = (
        not (conflict_map.get("claims") or [])
        and not (conflict_map.get("actor_positions") or actor_positions)
        and not (mechanism_summary.get("trigger_events") or mechanism_summary.get("amplification_paths") or mechanism_summary.get("cause_candidates"))
        and not (agenda_frame_map.get("issues") or agenda_frame_map.get("frames"))
    )
    missing_dimensions = [
        key
        for key, ready in (
            ("object_scope", has_object_scope),
            ("time_window", has_time_window),
            ("key_actors", has_key_actors),
            ("primary_contradiction", has_primary_contradiction),
            ("mechanism_explanation", has_mechanism_explanation),
            ("issue_frame_context", has_issue_frame_context),
            ("conditional_risk", has_conditional_risk),
            ("actionable_recommendations", has_actionable_recommendations),
            ("uncertainty_boundary", has_uncertainty_boundary),
        )
        if not ready
    ]
    structure_gaps = [
        key
        for key, ready in (
            ("recommendation_object", recommendation_has_object),
            ("recommendation_time", recommendation_has_time),
            ("recommendation_action", recommendation_has_action),
            ("recommendation_preconditions", recommendation_has_preconditions),
            ("recommendation_side_effects", recommendation_has_side_effects),
        )
        if not ready
    ]
    extra_dimensions: List[str] = []
    if empty_corpus:
        extra_dimensions.append("empty_corpus")
    if empty_evidence:
        extra_dimensions.append("empty_evidence")
    if insufficient_structure:
        extra_dimensions.append("insufficient_structure")
    missing_dimensions = _unique_strings([*missing_dimensions, *structure_gaps, *extra_dimensions], max_items=12)
    # 核心维度（不含 recommendation structure gaps）用于阈值判断
    _core_dimension_keys = {
        "object_scope", "time_window", "key_actors", "primary_contradiction",
        "mechanism_explanation", "issue_frame_context", "conditional_risk",
        "actionable_recommendations", "uncertainty_boundary",
    }
    core_missing_count = sum(1 for d in missing_dimensions if d in _core_dimension_keys)
    fallback_trace: List[UtilityFailure] = []
    for dimension, suggested_pass, reason in (
        ("empty_corpus", "compile_empty_sample_report", "当前时间窗内没有命中语料，应转入空样本报告路径。"),
        ("empty_evidence", "compile_empty_evidence_report", "当前没有可用证据卡，不应继续扩展深层分析。"),
        ("insufficient_structure", "compile_empty_structure_units", "当前结构对象为空，应保留可解释空结果而不是强行给结论。"),
        ("object_scope", "compile_recommendation_units", "建议未明确作用对象。"),
        ("time_window", "compile_recommendation_units", "建议未锚定执行时点。"),
        ("primary_contradiction", "compile_summary_units", "当前判断没有清晰说明主要矛盾。"),
        ("mechanism_explanation", "compile_transition_units", "当前判断缺少传播机制解释。"),
        ("issue_frame_context", "compile_summary_units", "当前判断缺少议题与框架上下文。"),
        ("conditional_risk", "compile_risk_statement_units", "风险判断缺少条件化触发描述。"),
        ("actionable_recommendations", "compile_recommendation_units", "建议缺动作或依据。"),
        ("uncertainty_boundary", "compile_closing_units", "输出未保留不确定性边界。"),
        ("recommendation_preconditions", "compile_recommendation_units", "建议缺少前提条件。"),
        ("recommendation_side_effects", "compile_recommendation_units", "建议未说明边界或副作用。"),
    ):
        if dimension in missing_dimensions:
            fallback_trace.append(
                UtilityFailure(
                    dimension=dimension,
                    reason=reason,
                    suggested_pass=suggested_pass,
                )
            )
    decision = "pass"
    next_action = "允许进入编译层。"
    if empty_corpus:
        decision = "fallback_recompile"
        next_action = "停止深层分析，转入空样本报告编译路径。"
    elif empty_evidence or insufficient_structure:
        decision = "fallback_recompile"
        next_action = "停止继续 fan-out，保留空证据或空结构边界并重新编译。"
    elif core_missing_count >= 3:
        decision = "fallback_recompile"
        next_action = "回退到 risk/recommendation micro-passes 补全对象、时点、动作与前提。"
    if len(unresolved_points) >= 3 and has_conditional_risk:
        decision = "require_semantic_review"
        next_action = "进入语义审批，确认在不确定性边界下是否允许输出管理建议。"
    if not has_mechanism_explanation and decision == "pass":
        decision = "fallback_recompile"
        next_action = "先补充机制层对象，再进入正式文稿编译。"
    unsupported_points = [
        item for item in unresolved_points
        if isinstance(item, dict) and str(item.get("reason") or "").strip() in {"unsupported", "contradicted"}
    ]
    if unsupported_points and decision == "pass":
        decision = "fallback_recompile"
        next_action = "存在 unsupported 或 contradicted 断言，先降低结论强度后再进入正式文稿编译。"
    improvement_trace: List[UtilityImprovementStep] = [
        UtilityImprovementStep(
            step_id=f"improve-{index}",
            triggered_by=item.dimension,
            recompiled_pass=item.suggested_pass,
            before_score=0.35,
            after_score=0.55 if decision == "fallback_recompile" else 0.68,
        )
        for index, item in enumerate(fallback_trace[:6], start=1)
    ]
    utility_confidence = 0.9 if decision == "pass" else 0.74 if decision == "require_semantic_review" else 0.66

    utility_assessment = UtilityAssessment(
        assessment_id="utility-1",
        has_object_scope=has_object_scope,
        has_time_window=has_time_window,
        has_key_actors=has_key_actors,
        has_primary_contradiction=has_primary_contradiction,
        has_mechanism_explanation=has_mechanism_explanation,
        has_issue_frame_context=has_issue_frame_context,
        has_conditional_risk=has_conditional_risk,
        has_actionable_recommendations=has_actionable_recommendations,
        has_uncertainty_boundary=has_uncertainty_boundary,
        recommendation_has_object=recommendation_has_object,
        recommendation_has_time=recommendation_has_time,
        recommendation_has_action=recommendation_has_action,
        recommendation_has_preconditions=recommendation_has_preconditions,
        recommendation_has_side_effects=recommendation_has_side_effects,
        missing_dimensions=missing_dimensions,
        fallback_trace=fallback_trace,
        improvement_trace=improvement_trace,
        decision=decision,
        next_action=next_action,
        utility_confidence=utility_confidence,
        confidence=utility_confidence,
    )
    coverage = _coverage_payload(
        matched_count=len(risks) + len(recommendations) + len(actor_positions),
        sampled_count=1,
        readiness_flags=[f"utility:{decision}"],
    )
    return {
        "utility_assessment": utility_assessment.model_dump(),
        "result": utility_assessment.model_dump(),
        **_base_result(
            normalized_task=normalized_task,
            tool_name="judge_decision_utility",
            coverage=coverage,
            confidence=utility_assessment.confidence,
            trace=_trace_payload([], offset=0, total=0, retrieval_strategy="typed_judgement", rewrite_queries=[], compression_applied=False),
        ),
    }


def detect_risk_signals_payload(*, normalized_task_json: str, evidence_ids_json: str = "[]", metric_refs_json: str = "[]", discourse_conflict_map_json: str = "", actor_positions_json: str = "[]") -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="risk", fallback_limit=16)
    metric_refs = _safe_parse_json(metric_refs_json, [])
    if not isinstance(metric_refs, list):
        metric_refs = []
    conflict_map = _safe_parse_json(discourse_conflict_map_json, {})
    if not isinstance(conflict_map, dict) or not conflict_map:
        conflict_map = build_discourse_conflict_map_payload(normalized_task_json=json.dumps(normalized_task, ensure_ascii=False), evidence_ids_json=json.dumps(cards, ensure_ascii=False), actor_positions_json=actor_positions_json)
    axes = conflict_map.get("axes") if isinstance(conflict_map.get("axes"), list) else []
    if not axes and isinstance(conflict_map.get("edges"), list):
        axes = [
            {
                "axis_id": str(item.get("edge_id") or f"axis-{index}").strip(),
                "title": str(item.get("conflict_type") or "冲突边").strip(),
                "opposing_sides": [str(value).strip() for value in (item.get("actor_scope") or []) if str(value or "").strip()],
                "focus_shift_path": ["命题对齐", "冲突识别", "收敛判断"],
                "intensity": 0.8,
                "trigger_evidence_ids": [str(value).strip() for value in (item.get("evidence_refs") or []) if str(value or "").strip()],
            }
            for index, item in enumerate(conflict_map.get("edges") or [], start=1)
            if isinstance(item, dict)
        ]
    risks: List[Dict[str, Any]] = []
    if axes:
        axis = axes[0]
        risks.append({"risk_id": "risk-discourse-escalation", "risk_type": "discourse_escalation", "trigger_evidence_ids": [str(item).strip() for item in (axis.get("trigger_evidence_ids") or []) if str(item or "").strip()][:5], "spread_condition": f"{str(axis.get('title') or '').strip()} 持续发酵时，争议会从事件事实迁移到主体冲突。", "severity": "high" if float(axis.get("intensity") or 0.0) >= 0.7 else "medium", "confidence": round(min(0.95, 0.48 + float(axis.get("intensity") or 0.0) * 0.4), 4), "time_sensitivity": "high"})
    rumor_cards = [card for card in cards if float(card.get("contradiction_signal") or 0.0) >= 0.7]
    if rumor_cards:
        risks.append({"risk_id": "risk-rumor", "risk_type": "rumor_conflict", "trigger_evidence_ids": [str(card.get("evidence_id") or "").strip() for card in rumor_cards[:4]], "spread_condition": "存在辟谣或互相冲突的信息流时，争议会被再次放大。", "severity": "high" if len(rumor_cards) >= 2 else "medium", "confidence": round(min(0.95, 0.5 + len(rumor_cards) * 0.1), 4), "time_sensitivity": "high"})
    platform_counts = Counter(str(card.get("platform") or "未知").strip() for card in cards)
    if platform_counts:
        dominant_platform, dominant_count = platform_counts.most_common(1)[0]
        if dominant_count >= max(2, len(cards) // 2):
            risks.append({"risk_id": "risk-platform-skew", "risk_type": "platform_concentration", "trigger_evidence_ids": [str(card.get("evidence_id") or "").strip() for card in cards[:4]], "spread_condition": f"当前讨论显著集中在 {dominant_platform}，单平台放大会主导传播节奏。", "severity": "medium", "confidence": 0.72, "time_sensitivity": "medium"})
    if not risks and cards:
        risks.append({"risk_id": "risk-watch", "risk_type": "attention_watch", "trigger_evidence_ids": [str(card.get("evidence_id") or "").strip() for card in cards[:3]], "spread_condition": "当前证据显示关注仍在累积，需持续跟踪新增叙事。", "severity": "low", "confidence": 0.58, "time_sensitivity": "medium"})
    coverage = _coverage_payload(matched_count=len(cards), sampled_count=len(risks), platform_counts=dict(platform_counts), readiness_flags=["risk_ready"] if cards else ["risk_empty"], source_quality_flags=["metric_refs_attached"] if metric_refs else [])
    error_hint = None
    if not cards and not risks:
        if evidence_ids_json == "[]" or not str(evidence_ids_json or "").strip() or str(evidence_ids_json or "").strip() in {"[]", "{}", "null"}:
            error_hint = "detect_risk_signals 需要传入 evidence_ids_json 参数。请将 evidence_cards.json 中的 result 数组作为参数传入，不能为空或默认值。"
        else:
            error_hint = "传入的 evidence_ids_json 无法解析或 contract 绑定失败。请确保传入有效的证据卡数组。"
    return {"discourse_conflict_map": conflict_map, "risks": risks, "result": risks, **_base_result(normalized_task=normalized_task, tool_name="detect_risk_signals", coverage=coverage, confidence=min(0.9, 0.42 + len(risks) * 0.09), trace=_trace_payload(cards, offset=0, total=len(cards)), error_hint=error_hint)}


def verify_claim_payload(*, normalized_task_json: str, claims_json: str, evidence_ids_json: str = "[]", strictness: str = "balanced") -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    claims = _safe_parse_json(claims_json, [])
    if isinstance(claims, str):
        claims = [claims]
    if not isinstance(claims, list):
        claims = []
    time_range = normalized_task.get("time_range") if isinstance(normalized_task.get("time_range"), dict) else {}
    results: List[Dict[str, Any]] = []
    counter_cards: List[Dict[str, Any]] = []
    for index, claim in enumerate([str(item).strip() for item in claims if str(item or "").strip()][:8]):
        verification = verify_claim_with_records(topic_identifier=str(normalized_task.get("topic_identifier") or "").strip(), start=str(time_range.get("start") or "").strip(), end=str(time_range.get("end") or "").strip(), claim=claim, entities=[str(item).strip() for item in (normalized_task.get("entities") or []) if str(item or "").strip()], platforms=[str(item).strip() for item in (normalized_task.get("platform_scope") or []) if str(item or "").strip()], top_k=8 if strictness == "strict" else 6, mode=str(normalized_task.get("mode") or "fast").strip().lower() or "fast")
        support_items = [dict(item) for item in (verification.get("supporting_items") or []) if isinstance(item, dict)]
        contradict_items = [dict(item) for item in (verification.get("contradicting_items") or []) if isinstance(item, dict)]
        status_map = {"supported": "supported", "partially_supported": "partially_supported", "unverified": "unsupported", "conflicting": "contradicted"}
        results.append({"claim_id": f"claim-{index + 1}", "claim_text": claim, "status": status_map.get(str(verification.get("verification_status") or "").strip(), "unsupported"), "support_ids": [f"ev-{_normalize_key((item.get('source_file') or '') + ':' + str(item.get('source_row_index') or idx))}" for idx, item in enumerate(support_items)], "contradict_ids": [f"ev-{_normalize_key((item.get('source_file') or '') + ':' + str(item.get('source_row_index') or idx))}" for idx, item in enumerate(contradict_items)], "gap_note": "" if support_items or contradict_items else "当前证据池中没有找到可直接回链的支持或反证。", "confidence": round(0.45 + min(len(support_items), 3) * 0.12 + min(len(contradict_items), 2) * 0.08, 4)})
        for item in contradict_items[:3]:
            counter_cards.append(_map_item_to_card(item, normalized_task, len(counter_cards)))
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent="claim_support", fallback_limit=12)
    coverage = _coverage_payload(matched_count=len(cards), sampled_count=len(results), readiness_flags=["claim_checked"] if results else ["claim_empty"])
    return {"claims": results, "result": results, **_base_result(normalized_task=normalized_task, tool_name="verify_claim_v2", coverage=coverage, counterevidence=counter_cards, confidence=min(0.92, 0.46 + len(results) * 0.08), trace=_trace_payload(cards, offset=0, total=len(cards)), error_hint=None)}


# section_id 前缀到 intent 的精确映射，避免子字符串误匹配（如 "risky" → "risk"）
_SECTION_ID_INTENT_MAP: Dict[str, str] = {
    "overview": "overview",
    "summary": "overview",
    "timeline": "timeline",
    "chronology": "timeline",
    "risk": "risk",
    "risk_analysis": "risk",
    "actor": "actors",
    "actors": "actors",
    "stance": "actors",
    "mechanism": "mechanism",
    "propagation": "mechanism",
}


def _resolve_section_intent(section_id: str) -> str:
    """将 section_id 映射到证据过滤 intent，精确匹配优先，未知 id 降级到 overview 并记录日志。"""
    sid = section_id.lower()
    if sid in _SECTION_ID_INTENT_MAP:
        return _SECTION_ID_INTENT_MAP[sid]
    # 前缀匹配（兼容带后缀的 section_id，如 "risk_v2"）
    for key, intent in _SECTION_ID_INTENT_MAP.items():
        if sid.startswith(key):
            return intent
    logger.warning("build_section_packet: 未知 section_id=%r，降级为 overview intent", section_id)
    return "overview"


def build_section_packet_payload(*, normalized_task_json: str, section_id: str, section_goal: str = "", evidence_ids_json: str = "[]", metric_refs_json: str = "[]", claim_ids_json: str = "[]") -> Dict[str, Any]:
    normalized_task = _load_normalized_task(normalized_task_json)
    safe_section_id = str(section_id or "").strip()
    if not safe_section_id:
        empty_packet = {"section_id": "", "section_goal": "", "claim_candidates": [], "verified_claims": [], "key_metrics": [], "evidence_cards": [], "counterevidence": [], "uncertainty_notes": [], "chart_data_refs": []}
        return {"section_packet": empty_packet, "result": empty_packet, **_base_result(normalized_task=normalized_task, tool_name="build_section_packet", error_hint=None)}
    section_intent = _resolve_section_intent(safe_section_id)
    cards = _cards_from_input(normalized_task, evidence_ids_json, intent=section_intent, fallback_limit=10)
    metrics = _safe_parse_json(metric_refs_json, [])
    if not isinstance(metrics, list):
        metrics = []
    claim_candidates = _safe_parse_json(claim_ids_json, [])
    if isinstance(claim_candidates, str):
        claim_candidates = [claim_candidates]
    if not isinstance(claim_candidates, list):
        claim_candidates = []
    if not claim_candidates:
        claim_candidates = [_normalize_text(card.get("title") or card.get("snippet")) for card in cards[:3] if _normalize_text(card.get("title") or card.get("snippet"))]
    verification = verify_claim_payload(normalized_task_json=json.dumps(normalized_task, ensure_ascii=False), claims_json=json.dumps(claim_candidates, ensure_ascii=False), evidence_ids_json=json.dumps(cards, ensure_ascii=False))
    verified_claims = [dict(item) for item in (verification.get("result") or []) if isinstance(item, dict)]
    uncertainty_notes: List[str] = []
    if not cards:
        logger.warning("build_section_packet: section_id=%r 无证据卡片，packet 将为空（section_packet_thin）", safe_section_id)
    if any(str(item.get("status") or "") in {"unsupported", "contradicted"} for item in verified_claims):
        uncertainty_notes.append("部分候选判断未获稳定支持，应保守表述并保留证据边界。")
    packet = {"section_id": safe_section_id, "section_goal": str(section_goal or "").strip() or f"围绕 {safe_section_id} 提炼可写、可核验的章节材料。", "claim_candidates": claim_candidates[:6], "verified_claims": verified_claims, "key_metrics": [dict(item) for item in metrics if isinstance(item, dict)][:8], "evidence_cards": cards, "counterevidence": [dict(item) for item in (verification.get("counterevidence") or []) if isinstance(item, dict)][:6], "uncertainty_notes": uncertainty_notes, "chart_data_refs": [dict(item) for item in metrics if isinstance(item, dict)][:8]}
    coverage = _coverage_payload(matched_count=len(cards), sampled_count=len(verified_claims), readiness_flags=["section_packet_ready"] if cards else ["section_packet_thin"])
    return {"section_packet": packet, "result": packet, **_base_result(normalized_task=normalized_task, tool_name="build_section_packet", coverage=coverage, counterevidence=packet["counterevidence"], confidence=min(0.94, 0.5 + len(cards) * 0.04), trace=_trace_payload(cards, offset=0, total=len(cards)))}
