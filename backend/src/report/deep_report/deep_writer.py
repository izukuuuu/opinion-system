"""
deep_report/deep_writer.py
===========================
LLM深度写作模块，复刻BettaFish的章节生成能力。

核心能力：
- 每章节独立调用LLM，而非确定性数据拼接
- 使用模板和证据构建写作prompt
- 内容密度验证（最少字数约束）
- JSON解析修复机制
- 输出DraftUnitV2结构化单元
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from .payloads import (
    build_agenda_frame_map_payload,
    build_event_timeline_payload,
    build_mechanism_summary_payload,
    build_section_packet_payload,
    compute_report_metrics_payload,
    detect_risk_signals_payload,
    extract_actor_positions_payload,
    normalize_task_payload,
    retrieve_evidence_cards_payload,
)
from .schemas import (
    DraftBundleV2,
    DraftUnitV2,
    TraceRef,
    SectionPlan,
    CompilerSectionPlanItem,
    CompilerSceneProfile,
)
from .report_ir import ReportIR

logger = logging.getLogger(__name__)


# 内容密度阈值（借鉴BettaFish，已增强）
_MIN_SECTION_BODY_CHARACTERS = 320
_MIN_NARRATIVE_CHARACTERS = 180
_MIN_QUOTE_COUNT = 5                  # 最少5条具体引用
_MIN_DATA_POINTS = 10                 # 最少10个数据点
_MAX_RETRY_ATTEMPTS = 3               # 最大重试次数（从2提升到3）
_MAX_REFLECTION_ROUNDS = 2            # 反思循环轮数（借鉴BettaFish）
# BettaFish 关键章节必须含表格
_REQUIRED_TABLE_SECTIONS = {
    "事件演变", "传播路径", "舆论立场与结构", "影响与动作", "附录",
    "timeline", "mechanism", "actors", "risks", "ledger",
}

_SECTION_INTENT_KEYWORDS = {
    "timeline": ["事件", "演变", "时间", "节点", "timeline", "脉络"],
    "actors": ["主体", "立场", "群体", "actor", "叙事竞争"],
    "risk": ["风险", "应对", "动作", "影响", "危机", "研判"],
    "mechanism": ["传播", "扩散", "路径", "放大", "机制", "platform"],
    "focus": ["焦点", "情绪", "争议", "态度", "议题", "frame"],
    "appendix": ["附录", "证据", "台账", "来源", "样本"],
}

_TOOL_RECALL_PLAYBOOK = {
    "timeline": ["retrieve_evidence_cards(intent=timeline)", "build_event_timeline"],
    "actors": ["retrieve_evidence_cards(intent=actors)", "extract_actor_positions"],
    "risk": ["retrieve_evidence_cards(intent=risk)", "detect_risk_signals", "judge_decision_utility"],
    "mechanism": ["retrieve_evidence_cards(intent=overview)", "build_mechanism_summary", "compute_report_metrics"],
    "focus": ["retrieve_evidence_cards(intent=overview)", "build_agenda_frame_map"],
    "appendix": ["retrieve_evidence_cards(intent=overview)", "build_section_packet"],
}

_WRITER_RETRIEVE_INTENT = {
    "timeline": "timeline",
    "actors": "actors",
    "risk": "risk",
    "mechanism": "overview",
    "focus": "overview",
    "appendix": "overview",
}

_WRITER_SECTION_PACKET_ID = {
    "timeline": "timeline",
    "actors": "actors",
    "risk": "risk",
    "mechanism": "mechanism",
    "focus": "overview",
    "appendix": "overview",
}


def _tokenize_query(text: str) -> List[str]:
    parts = re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", str(text or "").lower())
    return [part for part in parts if len(part.strip()) >= 2]


def _infer_section_intents(section_title: str, section_goal: str) -> List[str]:
    query = f"{section_title} {section_goal}".lower()
    intents: List[str] = []
    for intent, keywords in _SECTION_INTENT_KEYWORDS.items():
        if any(keyword in query for keyword in keywords):
            intents.append(intent)
    if not intents:
        intents.append("focus")
    if "appendix" not in intents and ("附录" in section_title or "appendix" in section_title.lower()):
        intents.append("appendix")
    return list(dict.fromkeys(intents))


def _score_text_match(query_tokens: List[str], text: str) -> int:
    haystack = str(text or "").lower()
    score = 0
    for token in query_tokens:
        if token in haystack:
            score += 2 if len(token) >= 4 else 1
    return score


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _to_result_count(payload: Dict[str, Any]) -> int:
    result = payload.get("result")
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        return len(result)
    return 0


def _build_tool_receipt(tool_name: str, payload: Dict[str, Any], *, note: str = "") -> Dict[str, Any]:
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    return {
        "tool_name": tool_name,
        "status": "ok" if _to_result_count(payload) or _to_result_count({"result": payload.get("section_packet")}) else "empty",
        "result_count": _to_result_count(payload) or _to_result_count({"result": payload.get("section_packet")}),
        "coverage": coverage,
        "trace": trace,
        "confidence": float(payload.get("confidence") or 0.0),
        "error_hint": str(payload.get("error_hint") or "").strip(),
        "note": str(note or "").strip(),
    }


def _build_writer_normalized_task(
    report_ir: ReportIR,
    section: CompilerSectionPlanItem,
) -> Dict[str, Any]:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    hints = {
        "topic": str(payload.meta.topic_label or payload.meta.topic_identifier or "").strip(),
        "entities": list(payload.topic_scope.entities or []),
        "keywords": list(payload.topic_scope.keywords or []),
        "platform_scope": list(payload.topic_scope.platforms or []),
        "analysis_question_set": list(payload.topic_scope.analysis_question_set or []),
        "mandatory_sections": [section.section_id],
    }
    normalized = normalize_task_payload(
        task_text=f"{payload.meta.topic_label} {section.title} {section.goal}",
        topic_identifier=str(payload.meta.topic_identifier or "").strip(),
        start=str(payload.meta.time_scope.start or "").strip(),
        end=str(payload.meta.time_scope.end or payload.meta.time_scope.start or "").strip(),
        mode=str(payload.meta.mode or "fast").strip() or "fast",
        hints_json=_json_dumps(hints),
    )
    result = normalized.get("normalized_task") if isinstance(normalized.get("normalized_task"), dict) else {}
    return result if isinstance(result, dict) else {}


def _collect_section_tool_context(
    section: CompilerSectionPlanItem,
    report_ir: ReportIR,
) -> Dict[str, Any]:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    intents = _infer_section_intents(section.title, section.goal)
    primary_intent = intents[0] if intents else "focus"
    normalized_task = _build_writer_normalized_task(payload, section)
    normalized_task_json = _json_dumps(normalized_task)
    retrieve_payload = retrieve_evidence_cards_payload(
        normalized_task_json=normalized_task_json,
        intent=_WRITER_RETRIEVE_INTENT.get(primary_intent, "overview"),
        limit=12,
    )
    evidence_cards = retrieve_payload.get("result") if isinstance(retrieve_payload.get("result"), list) else []
    receipts = [_build_tool_receipt("retrieve_evidence_cards", retrieve_payload, note=f"intent={primary_intent}")]

    claim_candidates = _extract_claims_for_section(payload, f"{section.title} {section.goal}")
    packet_section_id = _WRITER_SECTION_PACKET_ID.get(primary_intent, "overview")
    section_packet_payload = build_section_packet_payload(
        normalized_task_json=normalized_task_json,
        section_id=packet_section_id,
        section_goal=str(section.goal or "").strip(),
        evidence_ids_json=_json_dumps(evidence_cards),
        claim_ids_json=_json_dumps([item.get("claim_id") for item in claim_candidates if isinstance(item, dict) and item.get("claim_id")]),
    )
    section_packet = section_packet_payload.get("result") if isinstance(section_packet_payload.get("result"), dict) else {}
    receipts.append(_build_tool_receipt("build_section_packet", section_packet_payload, note=f"section_id={packet_section_id}"))

    metrics_payload: Dict[str, Any] = {}
    actor_payload: Dict[str, Any] = {}
    timeline_payload: Dict[str, Any] = {}
    mechanism_payload: Dict[str, Any] = {}
    risk_payload: Dict[str, Any] = {}
    agenda_payload: Dict[str, Any] = {}

    if any(intent in intents for intent in ("timeline", "mechanism", "risk")):
        timeline_payload = build_event_timeline_payload(
            normalized_task_json=normalized_task_json,
            evidence_ids_json=_json_dumps(evidence_cards),
            max_nodes=8,
        )
        receipts.append(_build_tool_receipt("build_event_timeline", timeline_payload))
    if any(intent in intents for intent in ("actors", "focus", "risk")):
        actor_payload = extract_actor_positions_payload(
            normalized_task_json=normalized_task_json,
            evidence_ids_json=_json_dumps(evidence_cards),
            actor_limit=10,
        )
        receipts.append(_build_tool_receipt("extract_actor_positions", actor_payload))
    if any(intent in intents for intent in ("mechanism", "risk")):
        metrics_payload = compute_report_metrics_payload(
            normalized_task_json=normalized_task_json,
            metric_scope="overview",
            evidence_ids_json=_json_dumps(evidence_cards),
        )
        receipts.append(_build_tool_receipt("compute_report_metrics", metrics_payload))
    if "mechanism" in intents:
        mechanism_payload = build_mechanism_summary_payload(
            normalized_task_json=normalized_task_json,
            evidence_ids_json=_json_dumps(evidence_cards),
            timeline_nodes_json=_json_dumps(timeline_payload.get("result") if isinstance(timeline_payload.get("result"), list) else []),
            conflict_map_json=_json_dumps(payload.conflict_map.model_dump()),
            metric_refs_json=_json_dumps(metrics_payload.get("result") if isinstance(metrics_payload.get("result"), list) else []),
        )
        receipts.append(_build_tool_receipt("build_mechanism_summary", mechanism_payload))
    if "risk" in intents:
        risk_payload = detect_risk_signals_payload(
            normalized_task_json=normalized_task_json,
            evidence_ids_json=_json_dumps(evidence_cards),
            metric_refs_json=_json_dumps(metrics_payload.get("result") if isinstance(metrics_payload.get("result"), list) else []),
            discourse_conflict_map_json=_json_dumps(payload.conflict_map.model_dump()),
            actor_positions_json=_json_dumps(actor_payload.get("result") if isinstance(actor_payload.get("result"), list) else []),
        )
        receipts.append(_build_tool_receipt("detect_risk_signals", risk_payload))
    if "focus" in intents:
        agenda_payload = build_agenda_frame_map_payload(
            normalized_task_json=normalized_task_json,
            evidence_ids_json=_json_dumps(evidence_cards),
            actor_positions_json=_json_dumps(actor_payload.get("result") if isinstance(actor_payload.get("result"), list) else []),
            conflict_map_json=_json_dumps(payload.conflict_map.model_dump()),
            timeline_nodes_json=_json_dumps(timeline_payload.get("result") if isinstance(timeline_payload.get("result"), list) else []),
        )
        receipts.append(_build_tool_receipt("build_agenda_frame_map", agenda_payload))

    return {
        "normalized_task": normalized_task,
        "primary_intent": primary_intent,
        "intents": intents,
        "evidence_cards": evidence_cards,
        "section_packet": section_packet,
        "timeline_nodes": timeline_payload.get("result") if isinstance(timeline_payload.get("result"), list) else [],
        "actor_positions": actor_payload.get("result") if isinstance(actor_payload.get("result"), list) else [],
        "metrics": metrics_payload.get("result") if isinstance(metrics_payload.get("result"), list) else [],
        "mechanism_summary": mechanism_payload.get("result") if isinstance(mechanism_payload.get("result"), dict) else {},
        "risk_signals": risk_payload.get("result") if isinstance(risk_payload.get("result"), list) else [],
        "agenda_frame_map": agenda_payload.get("result") if isinstance(agenda_payload.get("result"), dict) else {},
        "receipts": receipts,
    }


class DeepWriterError(Exception):
    """深度写作失败异常"""
    pass


class SectionContentTooSparseError(DeepWriterError):
    """章节内容稀疏异常"""
    def __init__(self, section_id: str, body_chars: int, narrative_chars: int, quote_count: int):
        super().__init__(
            f"章节 {section_id} 内容密度不足: "
            f"正文{body_chars}字（要求≥{_MIN_SECTION_BODY_CHARACTERS}），"
            f"叙事{narrative_chars}字（要求≥{_MIN_NARRATIVE_CHARACTERS}），"
            f"引用{quote_count}条（要求≥{_MIN_QUOTE_COUNT})"
        )
        self.section_id = section_id
        self.body_chars = body_chars
        self.narrative_chars = narrative_chars
        self.quote_count = quote_count


class InsufficientQuotesError(DeepWriterError):
    """引用不足异常"""
    def __init__(self, section_id: str, quote_count: int):
        super().__init__(
            f"章节 {section_id} 引用不足: 仅{quote_count}条引用（要求≥{_MIN_QUOTE_COUNT}）"
        )
        self.section_id = section_id
        self.quote_count = quote_count


def _get_llm_client() -> Any:
    """获取报告写作LLM客户端（使用项目统一的LangChain配置）"""
    from ...utils.ai import build_langchain_chat_model
    llm, _ = build_langchain_chat_model(task="report", model_role="report", temperature=0.2, max_tokens=2000)
    if llm is None:
        raise DeepWriterError("未找到可用的 LangChain 模型配置")
    return llm


def _load_skill_instructions(skill_keys: List[str]) -> str:
    """加载skill指导内容"""
    from ..skills import resolve_report_skill
    instructions = []
    for key in skill_keys:
        try:
            skill = resolve_report_skill(key)
            if isinstance(skill, dict):
                content = skill.get("instructionsMarkdown", "") or skill.get("instructions_markdown", "")
                if content:
                    instructions.append(f"【{key}】\n{content[:2000]}")
        except Exception as e:
            logger.warning(f"加载skill {key} 失败: {e}")
    return "\n\n".join(instructions) if instructions else ""


def _extract_evidence_for_section(
    report_ir: ReportIR,
    section_query: str,
) -> List[Dict[str, Any]]:
    """按章节语义自由检索证据卡（非固定 section_id 映射）。"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    query_tokens = _tokenize_query(section_query)

    relevant_evidence = []
    for entry in payload.evidence_ledger.entries[:20]:
        text_blob = " ".join(
            [
                str(getattr(entry, "title", "") or ""),
                str(getattr(entry, "finding", "") or ""),
                str(getattr(entry, "snippet", "") or ""),
                str(getattr(entry, "raw_quote", "") or ""),
                str(getattr(entry, "source_summary", "") or ""),
                str(getattr(entry, "platform", "") or ""),
            ]
        )
        evidence_dict = {
            "evidence_id": entry.evidence_id,
            "finding": getattr(entry, "finding", ""),
            "subject": getattr(entry, "subject", ""),
            "stance": getattr(entry, "stance", ""),
            "time_label": getattr(entry, "time_label", ""),
            "source_summary": getattr(entry, "source_summary", ""),
            "confidence": entry.confidence,
            "snippet": getattr(entry, "snippet", ""),
            "platform": getattr(entry, "platform", ""),
            # BettaFish 深度引证字段
            "author": getattr(entry, "author", ""),
            "sentiment_label": getattr(entry, "sentiment_label", ""),
            "raw_quote": getattr(entry, "raw_quote", ""),
            "emotion_signals": getattr(entry, "emotion_signals", []),
            "engagement_views": getattr(entry, "engagement_views", 0),
            "match_score": _score_text_match(query_tokens, text_blob) if query_tokens else 0,
        }
        relevant_evidence.append(evidence_dict)
    relevant_evidence.sort(
        key=lambda item: (
            int(item.get("match_score") or 0),
            int(item.get("engagement_views") or 0),
        ),
        reverse=True,
    )
    return relevant_evidence[:12]


def _extract_claims_for_section(
    report_ir: ReportIR,
    section_query: str,
) -> List[Dict[str, Any]]:
    """按章节语义自由检索断言（非固定 section_id 映射）。"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    query_tokens = _tokenize_query(section_query)

    claims = []
    for claim in payload.claim_set.claims[:15]:  # 最多15条
        proposition = str(
            getattr(claim, "proposition", "")
            or getattr(claim, "claim_text", "")
            or getattr(claim, "text", "")
            or ""
        ).strip()
        verification_status = str(
            getattr(claim, "verification_status", "")
            or getattr(claim, "status", "")
            or "supported"
        ).strip() or "supported"
        source_ids = [
            str(item).strip()
            for item in (
                getattr(claim, "source_ids", None)
                or getattr(claim, "support_evidence_ids", None)
                or []
            )
            if str(item or "").strip()
        ]
        text_blob = " ".join(
            [
                proposition,
                str(getattr(claim, "text", "") or ""),
                " ".join(source_ids),
            ]
        )
        claim_dict = {
            "claim_id": claim.claim_id,
            "proposition": proposition,
            "verification_status": verification_status,
            "source_ids": source_ids,
            "match_score": _score_text_match(query_tokens, text_blob) if query_tokens else 0,
        }
        claims.append(claim_dict)
    claims.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
    return claims[:8]


def _normalize_claim_entries(claims: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, claim in enumerate(claims):
        if isinstance(claim, dict):
            claim_id = str(claim.get("claim_id") or f"claim-candidate-{index + 1}").strip()
            proposition = str(
                claim.get("proposition")
                or claim.get("claim_text")
                or claim.get("text")
                or ""
            ).strip()
            source_ids = [
                str(item).strip()
                for item in (claim.get("source_ids") or claim.get("support_ids") or [])
                if str(item or "").strip()
            ]
            normalized.append(
                {
                    "claim_id": claim_id,
                    "proposition": proposition or claim_id,
                    "verification_status": str(
                        claim.get("verification_status") or claim.get("status") or "supported"
                    ).strip() or "supported",
                    "source_ids": source_ids,
                    "match_score": int(claim.get("match_score") or 0),
                }
            )
            continue
        text = str(claim or "").strip()
        if text:
            normalized.append(
                {
                    "claim_id": f"claim-candidate-{index + 1}",
                    "proposition": text,
                    "verification_status": "candidate",
                    "source_ids": [],
                    "match_score": 0,
                }
            )
    return normalized


def _extract_bettafish_context(
    report_ir: ReportIR,
    section_title: str,
    section_id: str,
) -> Dict[str, Any]:
    """
    按章节标题/ID 按需提取 BettaFish 数据结构，注入写作 prompt。
    返回结构化字典，key 对应各 BettaFish 数据类型。
    """
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    ctx: Dict[str, Any] = {}

    title_lower = section_title.lower()
    id_lower = section_id.lower()

    is_timeline = any(k in title_lower or k in id_lower for k in ["事件演变", "timeline", "事件脉络"])
    is_mechanism = any(k in title_lower or k in id_lower for k in ["传播路径", "mechanism", "传播链"])
    is_actors = any(k in title_lower or k in id_lower for k in ["舆论立场", "actors", "group", "群体", "主体"])
    is_risk = any(k in title_lower or k in id_lower for k in ["影响与动作", "风险", "risk", "recommendations", "建议"])

    # 1. 事件爆点（事件演变章节）
    if is_timeline and payload.event_flashpoints:
        ctx["flashpoints"] = [
            {
                "time": f.time_label,
                "event": f.event_title,
                "peak_readership": f.peak_readership,
                "emotion_keywords": f.core_emotion_keywords,
            }
            for f in payload.event_flashpoints[:8]
        ]

    # 2. 平台情绪雷达（传播路径章节 + 概览所有章节）
    if payload.platform_emotion_profiles:
        ctx["platform_profiles"] = [
            {
                "platform": p.platform,
                "dominant_emotion": p.dominant_emotion,
                "representative_quotes": p.representative_quotes[:2],
                "discussion_style": p.discussion_style,
                "emotion_dist": p.emotion_distribution,
            }
            for p in payload.platform_emotion_profiles[:6]
        ]

    # 3. 情绪传导公式（传播路径章节）
    if is_mechanism and payload.emotion_conduction_formula:
        ctx["emotion_formula"] = payload.emotion_conduction_formula

    # 4. 群体诉求（舆论立场章节）
    if is_actors and payload.group_demands:
        ctx["group_demands"] = [
            {
                "group": g.group_name,
                "demands": g.high_freq_demands,
                "golden_quotes": g.golden_quotes[:2],
            }
            for g in payload.group_demands[:8]
        ]

    # 5. 风险三色灯（影响与动作章节）
    if is_risk and payload.risk_traffic_lights:
        color_map = {"red": "🔴红灯", "yellow": "🟡黄灯", "green": "🟢绿灯"}
        ctx["traffic_lights"] = [
            {
                "color_label": color_map.get(t.light_color, t.light_color),
                "prediction": t.flashpoint_prediction,
                "threshold": t.trigger_threshold,
                "action": t.preemptive_action,
                "risk_id": t.risk_id,
            }
            for t in payload.risk_traffic_lights[:5]
        ]

    # 6. 网民金句（所有章节可用）
    if payload.netizen_quotes:
        ctx["netizen_quotes"] = payload.netizen_quotes[:8]

    return ctx


def _build_section_writer_prompt(
    section: CompilerSectionPlanItem,
    report_ir: ReportIR,
    scene_profile: CompilerSceneProfile,
    skill_instructions: str,
    runtime_context: Dict[str, Any] | None = None,
) -> tuple:
    """构建 BettaFish 质量章节写作 prompt（含结构化表格数据注入）"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    runtime = runtime_context if isinstance(runtime_context, dict) else {}

    section_query = f"{section.title} {section.goal}"
    evidence = runtime.get("evidence_cards") if isinstance(runtime.get("evidence_cards"), list) else []
    if not evidence:
        evidence = _extract_evidence_for_section(payload, section_query)
    packet = runtime.get("section_packet") if isinstance(runtime.get("section_packet"), dict) else {}
    packet_claims = packet.get("claim_candidates") if isinstance(packet.get("claim_candidates"), list) else []
    claims = _normalize_claim_entries(packet_claims) or _extract_claims_for_section(payload, section_query)
    bettafish_ctx = _extract_bettafish_context(payload, section.title, section.section_id)
    section_intents = runtime.get("intents") if isinstance(runtime.get("intents"), list) else _infer_section_intents(section.title, section.goal)
    tool_hints: List[str] = []
    for intent in section_intents:
        tool_hints.extend(_TOOL_RECALL_PLAYBOOK.get(intent, []))
    tool_hints = list(dict.fromkeys(tool_hints))

    system_prompt = """你是舆情报告深度写作代理，负责产出媲美BettaFish的专业舆情分析报告章节。

**写作原则（必须严格遵守）**：
1. 锚定现象 → 交代机制 → 点出含义（禁止单纯数据堆砌）
2. 证据校准：语气强度匹配证据确定性
3. 必须嵌入具体原文引用（格式: > "原文..." —— 来源/平台/作者）
4. 提供了表格数据时，必须输出对应 Markdown 表格
5. 禁止伪造数据（无数据的列留空或省略该列，不得捏造数字）
6. 禁止暴露系统字段名、工具名、模块名
7. 禁止写"网友认为"，必须直接引用具体原文

**输出格式（JSON）**：
```json
{
  "section_id": "xxx",
  "title": "章节标题",
  "blocks": [
    {"type": "heading", "text": "二级标题", "anchor": "anchor-id"},
    {"type": "paragraph", "text": "完整段落正文（≥80字）..."},
    {"type": "table", "markdown": "| 列1 | 列2 |\\n|---|---|\\n| 值1 | 值2 |"},
    {"type": "quote", "text": "引用原文内容", "attribution": "来源/作者/平台"},
    {"type": "list", "items": ["条目1", "条目2"]},
    {"type": "callout", "text": "风险提示", "tone": "warning"},
    {"type": "hr"}
  ],
  "evidence_refs": ["ev-xxx"],
  "claim_refs": ["claim-xxx"]
}
```
block类型: heading / paragraph(≥80字) / table(Markdown格式) / quote(原文+归因) / list / callout / hr
"""

    parts: List[str] = [
        "## 章节写作任务",
        f"- section_id: {section.section_id}",
        f"- 标题: {section.title}",
        f"- 目标字数: {section.target_words}字",
        f"- 模板标题: {section.template_title or section.title}",
        "",
        "## 章节写作要求（必须满足）",
        section.goal or "按模板要求进行深度分析",
        "",
    ]

    if section.writing_instruction:
        parts.extend([
            "## 模板章节 guide（必须落实到正文）",
            section.writing_instruction,
            "",
        ])

    receipts = runtime.get("receipts") if isinstance(runtime.get("receipts"), list) else []
    if receipts:
        parts.append("## 已执行工具与产物摘要（必须基于这些结果写作）")
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            tool_name = str(receipt.get("tool_name") or "").strip()
            result_count = int(receipt.get("result_count") or 0)
            note = str(receipt.get("note") or "").strip()
            parts.append(f"- {tool_name}: 返回 {result_count} 条/项" + (f"；{note}" if note else ""))
        parts.append("")

    if tool_hints:
        parts.append("## 工具召回与证据组合建议（按需自由选择）")
        for hint in tool_hints[:6]:
            parts.append(f"- {hint}")
        parts.append("说明：优先先检索证据，再组合结构化对象，最后落地正文。")
        parts.append("")

    # --- 注入 BettaFish 结构化数据 ---

    if bettafish_ctx.get("flashpoints"):
        parts.append("## 事件爆点数据（必须生成事件全景速览表格）")
        parts.append("| 时间 | 爆点事件 | 传播量级 | 核心情绪关键词 |")
        parts.append("|---|---|---|---|")
        for f in bettafish_ctx["flashpoints"]:
            kw = "、".join(f["emotion_keywords"]) if f["emotion_keywords"] else "—"
            peak = f["peak_readership"] or "—"
            parts.append(f"| {f['time'] or '—'} | {f['event'] or '—'} | {peak} | {kw} |")
        parts.append("")

    if bettafish_ctx.get("platform_profiles"):
        parts.append("## 平台情绪数据（必须生成平台情绪雷达表格）")
        parts.append("| 平台 | 主导情绪 | 代表性评论（引用原文） | 讨论风格 |")
        parts.append("|---|---|---|---|")
        for p in bettafish_ctx["platform_profiles"]:
            quote_sample = ""
            if p["representative_quotes"]:
                quote_sample = p["representative_quotes"][0][:60].replace("|", "｜")
            parts.append(
                f"| {p['platform']} | {p['dominant_emotion'] or '—'} "
                f"| {quote_sample or '—'} | {p['discussion_style'] or '—'} |"
            )
        parts.append("")

    if bettafish_ctx.get("emotion_formula"):
        parts.append("## 情绪传导公式（必须引用到传播路径分析中）")
        parts.append(bettafish_ctx["emotion_formula"])
        parts.append("")

    if bettafish_ctx.get("group_demands"):
        parts.append("## 群体诉求数据（必须生成多元群体诉求清单表格）")
        parts.append("| 群体 | 高频诉求 | 金句（引用原文） |")
        parts.append("|---|---|---|")
        for g in bettafish_ctx["group_demands"]:
            demands = "；".join(g["demands"][:2]) if g["demands"] else "—"
            quote = g["golden_quotes"][0][:60].replace("|", "｜") if g["golden_quotes"] else "—"
            parts.append(f"| {g['group']} | {demands} | {quote} |")
        parts.append("")

    if bettafish_ctx.get("traffic_lights"):
        parts.append("## 风险三色灯数据（必须生成高风险三色灯表格）")
        parts.append("| 等级 | 风险描述 | 爆点预测 | 触发阈值 | 提前干预 |")
        parts.append("|---|---|---|---|---|")
        for t in bettafish_ctx["traffic_lights"]:
            prediction = (t["prediction"] or "待分析")[:60].replace("|", "｜")
            threshold = (t["threshold"] or "待分析")[:40].replace("|", "｜")
            action = (t["action"] or "待补充")[:60].replace("|", "｜")
            parts.append(
                f"| {t['color_label']} | {prediction} | {prediction} | {threshold} | {action} |"
            )
        parts.append("")

    # --- 注入网民金句（所有章节均可嵌入）---
    if bettafish_ctx.get("netizen_quotes"):
        parts.append("## 可用网民金句（必须在正文中直接引用，使用 > '原文' —— 来源 格式）")
        for q in bettafish_ctx["netizen_quotes"][:6]:
            parts.append(f'> "{q}"')
        parts.append("")

    if packet:
        parts.append("## 章节材料包（优先使用）")
        for hint in [str(item).strip() for item in (packet.get("writing_hints") or []) if str(item or "").strip()][:6]:
            parts.append(f"- 写作提示: {hint}")
        for note in [str(item).strip() for item in (packet.get("uncertainty_notes") or []) if str(item or "").strip()][:4]:
            parts.append(f"- 边界说明: {note}")
        parts.append("")

    if runtime.get("timeline_nodes"):
        parts.append("## 时间线节点（可直接转化为叙事）")
        for node in runtime.get("timeline_nodes")[:6]:
            if not isinstance(node, dict):
                continue
            parts.append(f"- {str(node.get('time_label') or '—').strip()}：{str(node.get('summary') or '').strip()}")
        parts.append("")

    if runtime.get("actor_positions"):
        parts.append("## 主体立场对象")
        for actor in runtime.get("actor_positions")[:6]:
            if not isinstance(actor, dict):
                continue
            parts.append(f"- {str(actor.get('name') or '').strip()}：{str(actor.get('stance') or '').strip()}；{str(actor.get('stance_shift') or actor.get('summary') or '').strip()}")
        parts.append("")

    if runtime.get("risk_signals"):
        parts.append("## 风险信号对象")
        for risk in runtime.get("risk_signals")[:5]:
            if not isinstance(risk, dict):
                continue
            parts.append(f"- {str(risk.get('risk_type') or risk.get('label') or '').strip()}：{str(risk.get('spread_condition') or risk.get('summary') or '').strip()}")
        parts.append("")

    if runtime.get("mechanism_summary"):
        mechanism_summary = runtime.get("mechanism_summary") if isinstance(runtime.get("mechanism_summary"), dict) else {}
        confidence_summary = str(mechanism_summary.get("confidence_summary") or "").strip()
        if confidence_summary:
            parts.extend([
                "## 传播机制摘要",
                confidence_summary,
                "",
            ])

    if runtime.get("agenda_frame_map"):
        agenda_map = runtime.get("agenda_frame_map") if isinstance(runtime.get("agenda_frame_map"), dict) else {}
        frames = agenda_map.get("frames") if isinstance(agenda_map.get("frames"), list) else []
        if frames:
            parts.append("## 议题-框架对象")
            for frame in frames[:4]:
                if not isinstance(frame, dict):
                    continue
                parts.append(
                    f"- problem={str(frame.get('problem') or '').strip()}；cause={str(frame.get('cause') or '').strip()}；judgment={str(frame.get('judgment') or '').strip()}"
                )
            parts.append("")

    # --- 证据素材 ---
    parts.append("## 证据素材（必须引用，在正文中嵌入原文）")
    for ev in evidence[:10]:
        raw_q = ev.get("raw_quote") or ev.get("snippet") or ""
        if len(raw_q) > 120:
            raw_q = raw_q[:120] + "..."
        sentiment = f"[{ev['sentiment_label']}]" if ev.get("sentiment_label") else ""
        platform = f"@{ev['platform']}" if ev.get("platform") else ""
        author = f" —— {ev['author']}" if ev.get("author") else ""
        parts.append(
            f"- [{ev['evidence_id']}]{sentiment}{platform}: {raw_q}{author}"
        )
    parts.append("")

    # --- 相关断言 ---
    if claims:
        parts.append("## 相关断言（判断依据）")
        for c in claims[:5]:
            parts.append(f"- [{c['claim_id']}] {c['proposition']}")
        parts.append("")

    # --- 写作方法论 ---
    if skill_instructions:
        parts.append("## 写作方法论指导（参考执行）")
        parts.append(skill_instructions[:2000])
        parts.append("")

    # --- 专题背景 ---
    task = payload.meta
    topic_label = getattr(task, "topic_label", "") or getattr(task, "topic_identifier", "")
    time_scope = getattr(task, "time_scope", None)
    if time_scope:
        start = getattr(time_scope, "start", "") or ""
        end = getattr(time_scope, "end", "") or ""
    else:
        start = end = ""
    parts.extend([
        "## 专题背景",
        f"- 专题: {topic_label}",
        f"- 时间范围: {start} 至 {end}",
        "",
        "请输出符合上述格式的JSON章节内容，务必包含表格（若有数据）和原文金句引用。",
    ])

    return system_prompt, "\n".join(parts)


def _parse_llm_response_to_blocks(
    raw_response: str,
    section: CompilerSectionPlanItem,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """解析LLM响应为blocks结构"""

    # 尝试提取JSON
    json_match = re.search(r'\{[\s\S]*\}', raw_response)
    if not json_match:
        # 尝试从markdown代码块提取
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', raw_response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 创建fallback blocks
            logger.warning(f"无法从响应中提取JSON，创建fallback blocks")
            blocks = [
                {"type": "heading", "text": section.title, "anchor": section.section_id},
                {"type": "paragraph", "text": raw_response[:500] if raw_response else "（内容生成失败）"},
            ]
            return blocks, [], []
    else:
        json_str = json_match.group(0)

    # 解析JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试修复常见问题
        json_str_fixed = json_str.replace('\n', '\\n').replace('\t', '\\t')
        try:
            data = json.loads(json_str_fixed)
        except:
            logger.warning(f"JSON解析失败，创建fallback blocks")
            blocks = [
                {"type": "heading", "text": section.title, "anchor": section.section_id},
                {"type": "paragraph", "text": raw_response[:500] if raw_response else "（内容解析失败）"},
            ]
            return blocks, [], []

    # 提取blocks
    blocks = data.get("blocks", [])
    if not blocks:
        # 如果没有blocks但有content/text字段，转换为paragraph
        if data.get("content"):
            blocks = [{"type": "paragraph", "text": data["content"]}]
        elif data.get("text"):
            blocks = [{"type": "paragraph", "text": data["text"]}]

    # 确保开头有heading
    if not blocks or blocks[0].get("type") != "heading":
        blocks.insert(0, {"type": "heading", "text": section.title, "anchor": section.section_id})

    evidence_refs = data.get("evidence_refs", [])
    claim_refs = data.get("claim_refs", [])

    return blocks, evidence_refs, claim_refs


def _validate_content_density(
    blocks: List[Dict[str, Any]],
    section_id: str,
    evidence_refs: List[str] = None,
    section_title: str = "",
    target_words: int = 0,
) -> None:
    """验证内容密度（BettaFish 增强版：含表格密度、引用计数）"""
    body_chars = 0
    narrative_chars = 0
    quote_count = 0
    table_count = 0

    for block in blocks:
        block_type = block.get("type", "")
        text = block.get("text", "")

        if block_type == "paragraph":
            body_chars += len(text)
            narrative_chars += len(text)
            if ">" in text or "——" in text or "\u201c" in text or "\u201d" in text:
                quote_count += 1
        elif block_type == "list":
            for item in (block.get("items") or []):
                if isinstance(item, str):
                    body_chars += len(item)
                    narrative_chars += len(item)
                    if ">" in item or "——" in item:
                        quote_count += 1
        elif block_type == "table":
            table_count += 1
            # 表格 markdown 内容计入 body_chars
            md = block.get("markdown", "")
            body_chars += len(md)
            # table rows 格式
            for row in (block.get("rows") or []):
                for cell in (row.get("cells") or []):
                    if isinstance(cell, dict):
                        body_chars += len(cell.get("text", ""))
                    elif isinstance(cell, str):
                        body_chars += len(cell)
        elif block_type in {"quote", "callout"}:
            quote_count += 1
            body_chars += len(text)

    if evidence_refs:
        quote_count += len(evidence_refs)

    expected_body_chars = max(_MIN_SECTION_BODY_CHARACTERS, int(max(target_words, 0) * 0.8))
    expected_narrative_chars = max(_MIN_NARRATIVE_CHARACTERS, int(max(target_words, 0) * 0.4))
    if body_chars < expected_body_chars:
        raise SectionContentTooSparseError(section_id, body_chars, narrative_chars, quote_count)
    if narrative_chars < expected_narrative_chars:
        raise SectionContentTooSparseError(section_id, body_chars, narrative_chars, quote_count)
    if quote_count < _MIN_QUOTE_COUNT:
        raise InsufficientQuotesError(section_id, quote_count)

    # BettaFish 关键章节必须含表格（仅重试一次，不硬性阻塞）
    check_key = section_title or section_id
    if check_key in _REQUIRED_TABLE_SECTIONS and table_count == 0:
        logger.warning(
            f"章节 {section_id}（{section_title}）属于必须含表格的章节，"
            f"但当前 table_count=0，建议重试。"
        )
        # 不抛出异常，只警告，由调用方决定是否重试

    logger.info(
        f"章节 {section_id} 内容密度验证通过: 正文{body_chars}字, "
        f"引用{quote_count}条, 表格{table_count}个"
    )


def _has_substantive_blocks(blocks: List[Dict[str, Any]]) -> bool:
    for block in blocks:
        block_type = str(block.get("type", "") or "").strip().lower()
        if block_type in {"paragraph", "table", "quote", "list", "callout"}:
            return True
    return False


def _blocks_to_draft_units(
    blocks: List[Dict[str, Any]],
    section: CompilerSectionPlanItem,
    evidence_refs: List[str],
    claim_refs: List[str],
    report_ir: ReportIR,
) -> List[DraftUnitV2]:
    """将blocks转换为DraftUnitV2"""
    units = []
    known_ids = _known_trace_ids(report_ir)

    for idx, block in enumerate(blocks):
        block_type = str(block.get("type", "paragraph") or "paragraph").strip().lower()
        text = str(block.get("text", "") or "").strip()

        if block_type == "table":
            text = str(block.get("markdown", "") or "").strip()
        elif block_type == "list":
            items = [str(item or "").strip() for item in (block.get("items") or []) if str(item or "").strip()]
            text = "\n".join([f"- {item}" for item in items]).strip()
        elif block_type == "quote":
            attribution = str(block.get("attribution", "") or "").strip()
            if text:
                text = f'> "{text}"' + (f" —— {attribution}" if attribution else "")
        elif block_type == "callout":
            tone = str(block.get("tone", "") or "").strip()
            prefix = "提示"
            if tone in {"warning", "risk"}:
                prefix = "风险提示"
            elif tone in {"success", "positive"}:
                prefix = "正向提示"
            text = f"> {prefix}：{text}".strip()
        elif block_type == "hr":
            text = "---"

        if not text and block_type not in {"hr"}:
            continue

        # 确定unit_type
        unit_type = "finding"
        if block_type == "heading":
            unit_type = "heading"
        elif block_type in {"paragraph", "quote", "table", "list", "callout"}:
            unit_type = "finding"

        # 构建trace_refs
        trace_refs = []
        for ev_id in evidence_refs:
            if ev_id in known_ids.get("evidence", set()):
                trace_refs.append(TraceRef(
                    trace_id=ev_id,
                    trace_kind="evidence",
                    support_level="direct"
                ))
        for claim_id in claim_refs:
            if claim_id in known_ids.get("claim", set()):
                trace_refs.append(TraceRef(
                    trace_id=claim_id,
                    trace_kind="claim",
                    support_level="direct"
                ))

        # 如果没有trace_refs，添加section_context
        if not trace_refs:
            trace_refs.append(TraceRef(
                trace_id=section.section_id,
                trace_kind="section_context",
                support_level="structural"
            ))

        unit_id = f"unit:{section.section_id}:{idx}"

        units.append(DraftUnitV2(
            unit_id=unit_id,
            section_id=section.section_id,
            unit_type=unit_type,
            text=text,
            trace_refs=trace_refs,
            derived_from=list(claim_refs[:3]),
            support_level="direct" if any(ref.trace_kind != "section_context" for ref in trace_refs) else "structural",
            context_ref=section.section_id,
            render_template_id=f"{section.section_id}:{unit_type}",
            validation_status="pending",
            metadata={
                "block_type": block_type,
                "original_anchor": block.get("anchor", ""),
                "evidence_refs": evidence_refs,
                "claim_refs": claim_refs,
            },
        ))

    return units


def _known_trace_ids(report_ir: ReportIR) -> Dict[str, set[str]]:
    """获取已知trace ID集合"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    return {
        "claim": {c.claim_id for c in payload.claim_set.claims},
        "evidence": {e.evidence_id for e in payload.evidence_ledger.entries},
        "risk": {r.risk_id for r in payload.risk_register.risks},
        "timeline": {t.event_id for t in payload.timeline.events},
    }


def generate_section_with_llm(
    section: CompilerSectionPlanItem,
    report_ir: ReportIR,
    scene_profile: CompilerSceneProfile,
    skill_keys: List[str] = None,
    retry_count: int = 0,
    reflection_round: int = 0,
) -> Tuple[List[DraftUnitV2], Dict[str, Any]]:
    """使用LLM生成章节内容（带反思循环）"""

    skill_keys = skill_keys or [
        "report-writing-framework",
        "sentiment-analysis-methodology",
    ]

    skill_instructions = _load_skill_instructions(skill_keys)
    runtime_context = _collect_section_tool_context(section, report_ir)

    system_prompt, user_prompt = _build_section_writer_prompt(
        section, report_ir, scene_profile, skill_instructions, runtime_context
    )

    llm = _get_llm_client()

    # 调用LLM
    try:
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        raw_response = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        if retry_count < _MAX_RETRY_ATTEMPTS:
            logger.info(f"重试生成章节 {section.section_id}")
            return generate_section_with_llm(
                section, report_ir, scene_profile, skill_keys, retry_count + 1, reflection_round
            )
        raise DeepWriterError(f"章节 {section.section_id} LLM生成失败: {e}")

    # 解析响应
    blocks, evidence_refs, claim_refs = _parse_llm_response_to_blocks(raw_response, section)
    if not _has_substantive_blocks(blocks):
        raise DeepWriterError(f"章节 {section.section_id} 仅生成标题骨架，未形成正文。")

    # 验证内容密度（包含引用计数）
    try:
        _validate_content_density(
            blocks,
            section.section_id,
            evidence_refs,
            section.title,
            target_words=int(section.target_words or 0),
        )
    except (SectionContentTooSparseError, InsufficientQuotesError) as e:
        # 反思循环：如果内容密度不足且还有反思轮次，尝试补充
        if reflection_round < _MAX_REFLECTION_ROUNDS:
            logger.warning(f"章节 {section.section_id} 内容密度不足（反思轮{reflection_round+1}/{_MAX_REFLECTION_ROUNDS}），尝试补充写作")
            # 构建补充prompt，强调引用和密度
            supplement_prompt = user_prompt + "\n\n**补充要求**（因为上次内容密度不足）:\n- 必须增加更多具体原文引用（至少5条）\n- 正文长度必须≥800字\n- 使用引用格式：> \"原文内容\" —— 发言者（互动数据）"
            try:
                response = llm.invoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": supplement_prompt},
                ])
                raw_response = response.content if hasattr(response, 'content') else str(response)
                blocks, evidence_refs, claim_refs = _parse_llm_response_to_blocks(raw_response, section)
                if not _has_substantive_blocks(blocks):
                    raise DeepWriterError(f"章节 {section.section_id} 补充后仍只有标题骨架。")
                _validate_content_density(
                    blocks,
                    section.section_id,
                    evidence_refs,
                    section.title,
                    target_words=int(section.target_words or 0),
                )
            except Exception as supp_e:
                logger.warning(f"反思补充失败: {supp_e}")
                if retry_count < _MAX_RETRY_ATTEMPTS:
                    return generate_section_with_llm(
                        section, report_ir, scene_profile, skill_keys, retry_count + 1, reflection_round + 1
                    )
        else:
            raise DeepWriterError(f"章节 {section.section_id} 反思循环结束后仍未通过质量门槛: {e}")

    # 转换为DraftUnitV2
    units = _blocks_to_draft_units(blocks, section, evidence_refs, claim_refs, report_ir)

    return units, {
        "section_id": section.section_id,
        "title": section.title,
        "template_id": section.template_id,
        "template_title": section.template_title or section.title,
        "writing_instruction": section.writing_instruction,
        "tool_receipts": runtime_context.get("receipts") if isinstance(runtime_context.get("receipts"), list) else [],
        "tool_names": [
            str(item.get("tool_name") or "").strip()
            for item in (runtime_context.get("receipts") or [])
            if isinstance(item, dict) and str(item.get("tool_name") or "").strip()
        ],
        "evidence_ref_count": len(evidence_refs),
        "claim_ref_count": len(claim_refs),
        "trace_refs_used": list(dict.fromkeys([*evidence_refs, *claim_refs])),
        "unit_count": len(units),
        "degraded": False,
    }


def compile_draft_units_with_llm(
    report_ir: ReportIR,
    section_plan: SectionPlan,
    scene_profile: CompilerSceneProfile,
) -> DraftBundleV2:
    """使用LLM深度写作替代确定性拼接"""
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan)

    all_units: List[DraftUnitV2] = []
    section_receipts: List[Dict[str, Any]] = []
    degraded_sections: List[Dict[str, Any]] = []

    for section in plan.sections:
        try:
            logger.info(f"LLM生成章节: {section.section_id} - {section.title}")
            units, receipt = generate_section_with_llm(
                section, payload, scene_profile,
                skill_keys=[
                    "report-writing-framework",
                    "sentiment-analysis-methodology",
                    "chart-interpretation-guidelines",
                ]
            )
            all_units.extend(units)
            section_receipts.append(receipt)
            logger.info(f"章节 {section.section_id} 生成完成，{len(units)}个单元")
        except DeepWriterError as e:
            logger.error(f"章节 {section.section_id} 生成失败: {e}")
            # 创建可解释的降级单元，避免出现纯标题骨架。
            fallback_heading = DraftUnitV2(
                unit_id=f"unit:{section.section_id}:fallback-heading",
                section_id=section.section_id,
                unit_type="heading",
                text=f"## {section.title}",
                trace_refs=[TraceRef(
                    trace_id=section.section_id,
                    trace_kind="section_context",
                    support_level="structural"
                )],
                derived_from=[],
                support_level="structural",
                context_ref=section.section_id,
                render_template_id=f"{section.section_id}:heading",
                validation_status="failed",
                metadata={"error": str(e), "degraded": True},
            )
            fallback_paragraph = DraftUnitV2(
                unit_id=f"unit:{section.section_id}:fallback-body",
                section_id=section.section_id,
                unit_type="finding",
                text="（本章节自动写作未达到质量门槛，已触发降级输出。请结合证据台账人工复核后再发布。）",
                trace_refs=[TraceRef(
                    trace_id=section.section_id,
                    trace_kind="section_context",
                    support_level="structural"
                )],
                derived_from=[],
                support_level="structural",
                context_ref=section.section_id,
                render_template_id=f"{section.section_id}:finding",
                validation_status="failed",
                metadata={"error": str(e), "degraded": True},
            )
            all_units.extend([fallback_heading, fallback_paragraph])
            degraded_sections.append(
                {
                    "section_id": section.section_id,
                    "title": section.title,
                    "reason": str(e),
                    "template_id": section.template_id,
                }
            )
            section_receipts.append(
                {
                    "section_id": section.section_id,
                    "title": section.title,
                    "template_id": section.template_id,
                    "template_title": section.template_title or section.title,
                    "writing_instruction": section.writing_instruction,
                    "tool_receipts": [],
                    "tool_names": [],
                    "evidence_ref_count": 0,
                    "claim_ref_count": 0,
                    "trace_refs_used": [],
                    "unit_count": 2,
                    "degraded": True,
                    "degraded_reason": str(e),
                }
            )

    return DraftBundleV2(
        source_artifact_id="draft_bundle.llm.v2",
        policy_version="policy.v2",
        schema_version="draft-bundle.llm.v2",
        units=all_units,
        section_order=[s.section_id for s in plan.sections],
        metadata={
            "generation_mode": "llm_deep_writer",
            "section_count": len(plan.sections),
            "unit_count": len(all_units),
            "section_generation_receipts": section_receipts,
            "degraded_sections": degraded_sections,
            "selected_template": {
                "template_id": str(scene_profile.template_id or "").strip(),
                "template_name": str(scene_profile.template_name or "").strip(),
                "template_path": str(scene_profile.template_path or "").strip(),
                "scene_id": str(scene_profile.scene_id or "").strip(),
                "scene_label": str(scene_profile.scene_label or "").strip(),
                "score": float(scene_profile.selection_score or 0.0),
                "matched_reasons": list(scene_profile.matched_reasons or []),
            },
        },
    )
