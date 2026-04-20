"""
deep_report/deep_writer.py
===========================
Section-markdown-first Deep Writer.

The compile path is intentionally single-track:
- build template brief
- write markdown one section at a time
- derive DraftBundleV2 deterministically from section markdown
- apply a light editorial pass
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.tools import tool
from pydantic import BaseModel, Field

from .agent_tools import get_report_template
from .payloads import build_section_packet_payload, normalize_task_payload
from .report_ir import ReportIR
from .schemas import (
    CompilerSceneProfile,
    CompilerSectionPlanItem,
    DraftBundleV2,
    DraftUnitV2,
    SectionPlan,
    TraceRef,
)

logger = logging.getLogger(__name__)

_INSIGHT_SECTION_GUIDANCE: Dict[str, Dict[str, str]] = {
    "basic_analysis_insight": {
        "summary_key": "basic_analysis_insight",
        "snapshot_key": "basic_analysis_snapshot",
        "writing_rule": "这一节先给出总体判断，再解释情感分析总体图与词云图，不要写成统计项清单、字段说明或技术说明。",
    },
    "bertopic_insight": {
        "summary_key": "bertopic_insight",
        "snapshot_key": "bertopic_snapshot",
        "writing_rule": "这一节先给出主题主线判断，再解释主题演变图中的阶段切换与迁移节奏，不要写成模型说明或主题编号列表。",
    },
}


def _is_attitude_section(section: CompilerSectionPlanItem) -> bool:
    text = " ".join(
        [
            str(section.section_id or "").strip(),
            str(section.title or "").strip(),
            str(section.goal or "").strip(),
        ]
    )
    return any(token in text for token in ["公众态度", "议题反应", "舆论焦点", "态度", "情绪"])


class DeepWriterError(Exception):
    """Section-markdown-first deep writer failure."""


class SectionMarkdownResult(BaseModel):
    section_id: str = Field(default="")
    title: str = Field(default="")
    markdown_body: str = Field(default="")
    artifact_search_receipts: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_search_receipts: List[Dict[str, Any]] = Field(default_factory=list)
    packet_receipts: List[Dict[str, Any]] = Field(default_factory=list)
    degraded_reason: str = Field(default="")


class SectionTraceAnnotation(BaseModel):
    section_id: str = Field(default="")
    status: str = Field(default="ready")
    degraded_reason: str = Field(default="")
    trace_binding_mode: str = Field(default="direct")
    claim_refs: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    provisional_claim_refs: List[str] = Field(default_factory=list)
    provisional_evidence_refs: List[str] = Field(default_factory=list)
    notes: str = Field(default="")
    confidence: float = Field(default=0.0)


def _tokenize_query(text: str) -> List[str]:
    parts = re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", str(text or "").lower())
    return [part for part in parts if len(part.strip()) >= 2]


def _score_text_match(query_tokens: List[str], text: str) -> int:
    haystack = str(text or "").lower()
    score = 0
    for token in query_tokens:
        if token in haystack:
            score += 2 if len(token) >= 4 else 1
    return score


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


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


def _canonical_section_intent(section: CompilerSectionPlanItem) -> str:
    text = f"{section.section_id} {section.title} {section.goal}".lower()
    if any(token in text for token in ["timeline", "事件", "时间线", "演变", "脉络"]):
        return "timeline"
    if any(token in text for token in ["actor", "stance", "主体", "立场", "舆论"]):
        return "actors"
    if any(token in text for token in ["mechanism", "propagation", "传播", "动因", "扩散", "议程"]):
        return "mechanism"
    if any(token in text for token in ["risk", "影响", "风险", "应对", "动作", "建议"]):
        return "risk"
    return "overview"


def _build_section_intent_alias_registry(plan: SectionPlan) -> Dict[str, Dict[str, str]]:
    registry: Dict[str, Dict[str, str]] = {}
    for section in plan.sections:
        canonical = _canonical_section_intent(section)
        aliases = {
            str(section.section_id or "").strip(),
            str(section.title or "").strip(),
            str(section.template_title or "").strip(),
        }
        normalized_aliases = {
            re.sub(r"\s+", "", alias).lower()
            for alias in aliases
            if str(alias or "").strip()
        }
        registry[str(section.section_id or "").strip()] = {
            "canonical_intent": canonical,
            "title": str(section.title or "").strip(),
            "template_title": str(section.template_title or "").strip(),
            "aliases": [alias for alias in sorted(normalized_aliases) if alias],
        }
    return registry


def _get_llm_client() -> Any:
    """Get report-writing LLM via the project LangChain config."""
    from ...utils.ai import build_langchain_chat_model

    llm, _ = build_langchain_chat_model(task="report", model_role="report", temperature=0.2, max_tokens=2000)
    if llm is None:
        raise DeepWriterError("未找到可用的 LangChain 模型配置")
    return llm


def _extract_evidence_for_section(
    report_ir: ReportIR,
    section_query: str,
) -> List[Dict[str, Any]]:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    query_tokens = _tokenize_query(section_query)

    relevant_evidence: List[Dict[str, Any]] = []
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
        relevant_evidence.append(
            {
                "evidence_id": entry.evidence_id,
                "finding": getattr(entry, "finding", ""),
                "subject": getattr(entry, "subject", ""),
                "stance": getattr(entry, "stance", ""),
                "time_label": getattr(entry, "time_label", ""),
                "source_summary": getattr(entry, "source_summary", ""),
                "confidence": entry.confidence,
                "snippet": getattr(entry, "snippet", ""),
                "platform": getattr(entry, "platform", ""),
                "author": getattr(entry, "author", ""),
                "sentiment_label": getattr(entry, "sentiment_label", ""),
                "raw_quote": getattr(entry, "raw_quote", ""),
                "emotion_signals": getattr(entry, "emotion_signals", []),
                "engagement_views": getattr(entry, "engagement_views", 0),
                "match_score": _score_text_match(query_tokens, text_blob) if query_tokens else 0,
            }
        )
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
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    query_tokens = _tokenize_query(section_query)

    claims: List[Dict[str, Any]] = []
    for claim in payload.claim_set.claims[:15]:
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
        text_blob = " ".join([proposition, str(getattr(claim, "text", "") or ""), " ".join(source_ids)])
        claims.append(
            {
                "claim_id": claim.claim_id,
                "proposition": proposition,
                "verification_status": verification_status,
                "source_ids": source_ids,
                "match_score": _score_text_match(query_tokens, text_blob) if query_tokens else 0,
            }
        )
    claims.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
    return claims[:8]


def _selected_template_metadata(scene_profile: CompilerSceneProfile) -> Dict[str, Any]:
    return {
        "template_id": str(scene_profile.template_id or "").strip(),
        "template_name": str(scene_profile.template_name or "").strip(),
        "template_path": str(scene_profile.template_path or "").strip(),
        "scene_id": str(scene_profile.scene_id or "").strip(),
        "scene_label": str(scene_profile.scene_label or "").strip(),
        "score": float(scene_profile.selection_score or 0.0),
        "matched_reasons": list(scene_profile.matched_reasons or []),
    }


def _split_must_cover_points(*texts: str) -> List[str]:
    points: List[str] = []
    for raw in texts:
        for chunk in re.split(r"[\n\r]+|(?<=[。；;])", str(raw or "").strip()):
            text = re.sub(r"^\s*[-*•]\s*", "", str(chunk or "").strip())
            if len(text) < 4:
                continue
            if text not in points:
                points.append(text)
    return points[:8]


def build_template_brief(
    section_plan: SectionPlan | Dict[str, Any],
    scene_profile: CompilerSceneProfile | Dict[str, Any],
    writer_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan or {})
    scene = scene_profile if isinstance(scene_profile, CompilerSceneProfile) else CompilerSceneProfile.model_validate(scene_profile or {})
    context = writer_context if isinstance(writer_context, dict) else {}
    sections = [
        {
            "section_id": str(section.section_id or "").strip(),
            "title": str(section.title or "").strip(),
            "goal": str(section.goal or "").strip(),
            "target_words": int(section.target_words or 0),
            "template_title": str(section.template_title or section.title or "").strip(),
            "writing_instruction": str(section.writing_instruction or "").strip(),
            "must_cover": _split_must_cover_points(section.goal, section.writing_instruction),
        }
        for section in plan.sections
        if str(section.section_id or "").strip()
    ]
    return {
        "writing_mode": "section_markdown_first",
        "template": _selected_template_metadata(scene),
        "section_count": len(sections),
        "section_order": [item["section_id"] for item in sections],
        "sections": sections,
        "global_requirements": [
            "必须按模板章节顺序输出，章节标题由系统统一写入。",
            "优先通过工具系统检索 JSON 产物、模板和证据卡，再组织章节正文。",
            "每个章节只负责本节内容，不要试图一次性输出整篇报告。",
            "不要把工具名、模块名、字段名直接写进正文。",
        ],
        "topic": str(context.get("topic") or "").strip(),
        "counts": dict(context.get("counts") or {}),
        "basic_analysis_insight": dict(context.get("basic_analysis_insight") or {}),
        "bertopic_insight": dict(context.get("bertopic_insight") or {}),
    }


def build_section_write_prompt(
    report_ir: ReportIR | Dict[str, Any],
    section: CompilerSectionPlanItem | Dict[str, Any],
    template_brief: Dict[str, Any],
    writer_context: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    section_item = section if isinstance(section, CompilerSectionPlanItem) else CompilerSectionPlanItem.model_validate(section or {})
    context = writer_context if isinstance(writer_context, dict) else {}
    section_brief = next(
        (
            item for item in (template_brief.get("sections") or [])
            if isinstance(item, dict) and str(item.get("section_id") or "").strip() == str(section_item.section_id or "").strip()
        ),
        {
            "section_id": section_item.section_id,
            "title": section_item.title,
            "goal": section_item.goal,
            "target_words": int(section_item.target_words or 0),
            "template_title": section_item.template_title or section_item.title,
            "writing_instruction": section_item.writing_instruction,
            "must_cover": _split_must_cover_points(section_item.goal, section_item.writing_instruction),
        },
    )
    section_insight_context: Dict[str, Any] = {}
    guidance = _INSIGHT_SECTION_GUIDANCE.get(str(section_item.section_id or "").strip())
    if guidance:
        insight_payload = context.get(str(guidance.get("summary_key") or "")) if isinstance(context, dict) else {}
        snapshot_payload = context.get(str(guidance.get("snapshot_key") or "")) if isinstance(context, dict) else {}
        section_insight_context = {
            "summary": str((insight_payload or {}).get("summary") or "").strip(),
            "key_findings": [str(item).strip() for item in ((insight_payload or {}).get("key_findings") or []) if str(item or "").strip()][:6],
            "uncertainty_notes": [str(item).strip() for item in ((insight_payload or {}).get("uncertainty_notes") or []) if str(item or "").strip()][:4],
            "theme_profiles": list((insight_payload or {}).get("theme_profiles") or [])[:5],
            "temporal_highlights": list((insight_payload or {}).get("temporal_highlights") or [])[:4],
            "dominant_phases": list((insight_payload or {}).get("dominant_phases") or [])[:4],
            "overview": dict((snapshot_payload or {}).get("overview") or {}),
            "writing_rule": str(guidance.get("writing_rule") or "").strip(),
        }
    system_prompt = (
        "你是舆情深度报告章节写作代理。"
        "你一次只负责一个章节正文。"
        "必须主动使用工具检索证据和结构化产物，再完成写作。"
        "正文只输出 markdown 内容，不要输出 JSON，不要重复章节标题。"
        "不要暴露工具名、字段名、模块名。"
    )
    extra_output_rules: List[str] = []
    if _is_attitude_section(section_item):
        extra_output_rules.extend(
            [
                "5. 对“公众态度/议题反应”类章节，必须先通过 evidence_search 检索代表性表达，再组织概括，不能只靠抽象三分法空写。",
                "6. 若已检索到 raw_quote 或 snippet，可穿插少量代表性表达并标明平台或主体来源；没有可回链样本时，只写已知数量结构和争议焦点，不得脑补评论内容。",
                "7. 公众态度必须附着在具体争议问题上，例如政策目标、执行方式、适用场景、主体权责、历史符号，不得只写“支持、质疑、担忧”三个情绪标签。",
            ]
        )
    extra_output_text = ""
    if extra_output_rules:
        extra_output_text = "\n".join(extra_output_rules) + "\n"
    user_prompt = (
        "请完成以下章节正文。\n\n"
        f"章节约束：\n{json.dumps(section_brief, ensure_ascii=False, indent=2)}\n\n"
        f"专题信息：\n{json.dumps({'topic_label': payload.meta.topic_label, 'topic_identifier': payload.meta.topic_identifier, 'time_scope': payload.meta.time_scope.model_dump(), 'mode': str(payload.meta.mode or 'fast')}, ensure_ascii=False, indent=2)}\n\n"
        f"写作上下文：\n{json.dumps({'topic': context.get('topic') or '', 'counts': context.get('counts') or {}, 'section_insight_context': section_insight_context}, ensure_ascii=False, indent=2)}\n\n"
        "输出要求：\n"
        "1. 只输出当前章节正文 markdown，不要输出标题行，不要输出 JSON。\n"
        "2. 若证据不足，请保留审慎边界，用条件性表达说明限制。\n"
        "3. 优先引用 evidence_search 与 artifact_search 返回的内容组织判断。\n"
        "4. 尽量覆盖 must_cover 中的点，但不要为了凑点数硬写结论。\n"
        f"{extra_output_text}"
    )
    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def _report_mode_for_template(scene_profile: CompilerSceneProfile) -> str:
    scene_id = str(scene_profile.scene_id or scene_profile.template_id or "").strip().lower()
    if scene_id in {"public_hotspot", "crisis_response", "policy_dynamics"}:
        return scene_id
    return "public_hotspot"


def _safe_json_loads(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _strip_code_fences(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = re.sub(r"^```(?:json|markdown|md|text)?\s*", "", stripped, flags=re.I)
    stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _ensure_string_content(response: Any) -> str:
    def _flatten_text_part(part: Any, depth: int = 0) -> str:
        if depth > 5:
            return str(part)
        if isinstance(part, str):
            return part
        if isinstance(part, list):
            return "\n".join(_flatten_text_part(item, depth + 1) for item in part)
        if isinstance(part, dict):
            for key in ("text", "content", "value"):
                if key in part:
                    return _flatten_text_part(part[key], depth + 1)
            return str(part)
        return str(part)

    if hasattr(response, "content"):
        content = response.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(_flatten_text_part(item) for item in content)
        return str(content)
    return str(response)


def _deep_agent_output_text(result: Any) -> str:
    if isinstance(result, dict):
        messages = result.get("messages") if isinstance(result.get("messages"), list) else []
        saw_messages = bool(messages)
        for item in reversed(messages):
            content = _ensure_string_content(item.get("content")) if isinstance(item, dict) else _ensure_string_content(item)
            if content.strip():
                return content
        if saw_messages:
            return ""
        return _ensure_string_content(result.get("output") or result.get("final_output") or result)
    return _ensure_string_content(result)


def _artifact_candidates(
    payload: ReportIR,
    plan: SectionPlan,
    scene_profile: CompilerSceneProfile,
    template_brief: Dict[str, Any],
    writer_context: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    context = writer_context if isinstance(writer_context, dict) else {}
    roots: List[Tuple[str, Any]] = [
        ("report_ir.meta", payload.meta.model_dump()),
        ("report_ir.claim_set", payload.claim_set.model_dump()),
        ("report_ir.evidence_ledger", payload.evidence_ledger.model_dump()),
        ("report_ir.timeline", payload.timeline.model_dump()),
        ("report_ir.actor_registry", payload.actor_registry.model_dump()),
        ("report_ir.conflict_map", payload.conflict_map.model_dump()),
        ("report_ir.agenda_frame_map", payload.agenda_frame_map.model_dump()),
        ("report_ir.mechanism_summary", payload.mechanism_summary.model_dump()),
        ("report_ir.risk_register", payload.risk_register.model_dump()),
        ("report_ir.recommendation_candidates", payload.recommendation_candidates.model_dump()),
        ("report_ir.unresolved_points", payload.unresolved_points.model_dump()),
        ("section_plan", plan.model_dump()),
        ("template_brief", template_brief),
        ("selected_template", _selected_template_metadata(scene_profile)),
        ("writer_context", context),
    ]
    candidates: List[Dict[str, Any]] = []

    def _walk(prefix: str, value: Any, depth: int = 0) -> None:
        if depth > 4:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                _walk(f"{prefix}.{key}" if prefix else str(key), child, depth + 1)
            return
        if isinstance(value, list):
            for index, child in enumerate(value[:20]):
                _walk(f"{prefix}[{index}]", child, depth + 1)
            return
        text = str(value or "").strip()
        if not text:
            return
        artifact = prefix.split(".", 1)[0]
        candidates.append(
            {
                "artifact": artifact,
                "json_path": prefix,
                "snippet": text[:260],
                "search_text": f"{prefix} {text}".lower(),
            }
        )

    for root_name, root_value in roots:
        _walk(root_name, root_value)
    return candidates


def _token_match_score(query_tokens: List[str], path: str, text: str) -> int:
    score = _score_text_match(query_tokens, text)
    score += _score_text_match(query_tokens, path) * 2
    return score


def _known_trace_ids(report_ir: ReportIR) -> Dict[str, set[str]]:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    return {
        "claim": {c.claim_id for c in payload.claim_set.claims},
        "evidence": {e.evidence_id for e in payload.evidence_ledger.entries},
        "risk": {r.risk_id for r in payload.risk_register.risks},
        "timeline": {t.event_id for t in payload.timeline.events},
    }


def _normalize_section_markdown_body(raw: Any, *, title: str) -> str:
    text = _strip_code_fences(_ensure_string_content(raw))
    if not text:
        return ""
    lines = str(text).splitlines()
    if lines:
        first = str(lines[0] or "").strip()
        normalized_title = _normalize_heading(title)
        if first.startswith("#") and _normalize_heading(first.lstrip("#").strip()) == normalized_title:
            lines = lines[1:]
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _inject_section_figure_refs(markdown_body: str, section_id: str, writer_context: Dict[str, Any] | None) -> str:
    text = str(markdown_body or "").strip()
    if not text:
        return text
    context = writer_context if isinstance(writer_context, dict) else {}
    figure_map = context.get("section_figure_refs") if isinstance(context.get("section_figure_refs"), dict) else {}
    refs = figure_map.get(str(section_id or "").strip()) if isinstance(figure_map, dict) else None
    figure_ids = [
        str(item.get("figure_id") or "").strip()
        for item in (refs or [])
        if isinstance(item, dict) and str(item.get("figure_id") or "").strip()
    ]
    missing_directives = [figure_id for figure_id in figure_ids if f'::figure{{ref="{figure_id}"}}' not in text]
    if not missing_directives:
        return text
    directives = "\n\n".join([f'::figure{{ref="{figure_id}"}}' for figure_id in missing_directives])
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if str(part or "").strip()]
    if not paragraphs:
        return f"{text}\n\n{directives}".strip()
    paragraphs.insert(1 if len(paragraphs) >= 1 else len(paragraphs), directives)
    return "\n\n".join(paragraphs).strip()


def _build_section_writer_tools(
    payload: ReportIR,
    plan: SectionPlan,
    scene: CompilerSceneProfile,
    brief: Dict[str, Any],
    writer_context: Dict[str, Any] | None,
    artifact_search_receipts: List[Dict[str, Any]],
    evidence_search_receipts: List[Dict[str, Any]],
    packet_receipts: List[Dict[str, Any]],
) -> List[Any]:
    context = writer_context if isinstance(writer_context, dict) else {}
    artifact_index = _artifact_candidates(payload, plan, scene, brief, context)
    section_map = {str(section.section_id or "").strip(): section for section in plan.sections}
    section_intent_registry = _build_section_intent_alias_registry(plan)

    @tool
    def artifact_search(query: str, scope: str = "", section_goal: str = "", limit: int = 6) -> str:
        """Search report_ir, section plan, template brief, and writer context."""
        query_text = f"{query} {section_goal}".strip()
        query_tokens = _tokenize_query(query_text)
        scope_tokens = {item.strip().lower() for item in re.split(r"[,，\s]+", str(scope or "").strip()) if item.strip()}
        matches: List[Dict[str, Any]] = []
        for item in artifact_index:
            artifact_name = str(item.get("artifact") or "").lower()
            if scope_tokens and artifact_name not in scope_tokens and not any(token in artifact_name for token in scope_tokens):
                continue
            score = _token_match_score(query_tokens, str(item.get("json_path") or ""), str(item.get("snippet") or "")) if query_tokens else 0
            if score <= 0 and query_tokens:
                continue
            matches.append(
                {
                    "artifact": item.get("artifact"),
                    "json_path": item.get("json_path"),
                    "snippet": item.get("snippet"),
                    "score": score,
                }
            )
        matches.sort(key=lambda row: int(row.get("score") or 0), reverse=True)
        result = matches[: max(1, int(limit or 6))]
        artifact_search_receipts.append(
            {
                "query": str(query or "").strip(),
                "scope": str(scope or "").strip(),
                "section_goal": str(section_goal or "").strip(),
                "result_count": len(result),
            }
        )
        return json.dumps({"status": "ok" if result else "empty", "query": str(query or "").strip(), "result": result}, ensure_ascii=False)

    @tool
    def evidence_search(
        query: str,
        section_goal: str = "",
        platforms: str = "",
        sentiments: str = "",
        time_range: str = "",
        limit: int = 8,
    ) -> str:
        """Search evidence cards for the current section."""
        query_text = f"{query} {section_goal}".strip()
        query_tokens = _tokenize_query(query_text)
        platform_tokens = {item.strip().lower() for item in re.split(r"[,，\s]+", str(platforms or "").strip()) if item.strip()}
        sentiment_tokens = {
            item.strip().lower()
            for item in re.split(r"[,，\s]+", str(sentiments or "").strip())
            if item.strip()
        }
        start_text = ""
        end_text = ""
        if str(time_range or "").strip():
            if ":" in str(time_range or ""):
                start_text, end_text = [part.strip() for part in str(time_range or "").split(":", 1)]
            else:
                parsed_range = _safe_json_loads(time_range)
                start_text = str(parsed_range.get("start") or "").strip()
                end_text = str(parsed_range.get("end") or "").strip()
        hits: List[Dict[str, Any]] = []
        for entry in payload.evidence_ledger.entries[:80]:
            platform_name = str(getattr(entry, "platform", "") or "").strip()
            if platform_tokens and platform_name.lower() not in platform_tokens:
                continue
            sentiment_label = str(getattr(entry, "sentiment_label", "") or "").strip()
            if sentiment_tokens and sentiment_label.lower() not in sentiment_tokens:
                continue
            time_label = str(getattr(entry, "time_label", "") or "").strip()
            if start_text and time_label and time_label < start_text:
                continue
            if end_text and time_label and time_label > end_text:
                continue
            text_blob = " ".join(
                [
                    str(getattr(entry, "title", "") or ""),
                    str(getattr(entry, "finding", "") or ""),
                    str(getattr(entry, "snippet", "") or ""),
                    str(getattr(entry, "raw_quote", "") or ""),
                    str(getattr(entry, "subject", "") or ""),
                    platform_name,
                ]
            )
            score = _score_text_match(query_tokens, text_blob) if query_tokens else 0
            if score <= 0 and query_tokens:
                continue
            hits.append(
                {
                    "evidence_id": str(getattr(entry, "evidence_id", "") or "").strip(),
                    "platform": platform_name,
                    "author": str(getattr(entry, "author", "") or "").strip(),
                    "time_label": time_label,
                    "snippet": str(getattr(entry, "snippet", "") or getattr(entry, "finding", "") or "").strip()[:240],
                    "raw_quote": str(getattr(entry, "raw_quote", "") or "").strip()[:240],
                    "subject": str(getattr(entry, "subject", "") or "").strip(),
                    "sentiment_label": sentiment_label,
                    "confidence": float(getattr(entry, "confidence", 0.0) or 0.0),
                    "score": score,
                }
            )
        hits.sort(key=lambda row: (int(row.get("score") or 0), float(row.get("confidence") or 0.0)), reverse=True)
        result = hits[: max(1, int(limit or 8))]
        evidence_search_receipts.append(
            {
                "query": str(query or "").strip(),
                "section_goal": str(section_goal or "").strip(),
                "platforms": str(platforms or "").strip(),
                "sentiments": str(sentiments or "").strip(),
                "time_range": str(time_range or "").strip(),
                "result_count": len(result),
            }
        )
        return json.dumps({"status": "ok" if result else "empty", "query": str(query or "").strip(), "result": result}, ensure_ascii=False)

    @tool
    def build_section_packet(section_id: str, section_goal: str = "", evidence_ids_json: str = "[]", claim_ids_json: str = "[]") -> str:
        """Assemble a section packet for a planned section."""
        matched_section = section_map.get(str(section_id or "").strip())
        if matched_section is None:
            section_key = str(section_id or "").strip()
            matched_section = next((section for section in plan.sections if str(section.title or "").strip() == section_key), None)
        goal_text = str(section_goal or (matched_section.goal if matched_section else "") or "").strip()
        section_for_task = matched_section or next(iter(plan.sections), None)
        normalized_task = _build_writer_normalized_task(payload, section_for_task) if section_for_task is not None else {
            "topic_label": str(payload.meta.topic_label or payload.meta.topic_identifier or "").strip()
        }
        if isinstance(normalized_task, dict):
            normalized_task["section_intent_alias_registry"] = section_intent_registry
        canonical_intent = ""
        if matched_section is not None:
            canonical_intent = str((section_intent_registry.get(str(matched_section.section_id or "").strip()) or {}).get("canonical_intent") or "").strip()
        packet_payload = build_section_packet_payload(
            normalized_task_json=_json_dumps(normalized_task),
            section_id=str(canonical_intent or (matched_section.section_id if matched_section else section_id) or "").strip() or "overview",
            section_goal=goal_text,
            evidence_ids_json=str(evidence_ids_json or "[]"),
            claim_ids_json=str(claim_ids_json or "[]"),
            original_section_id=str((matched_section.section_id if matched_section else section_id) or "").strip(),
            original_section_title=str((matched_section.title if matched_section else section_id) or "").strip(),
        )
        packet_receipts.append(
            {
                "section_id": str((matched_section.section_id if matched_section else section_id) or "").strip(),
                "canonical_intent": canonical_intent,
                "section_goal": goal_text,
                "status": str(packet_payload.get("status") or "").strip() or "ok",
                "degraded_reason": str(packet_payload.get("degraded_reason") or "").strip(),
                "verified_claim_ids": [
                    str(item.get("claim_id") or "").strip()
                    for item in (((packet_payload.get("section_packet") or {}).get("verified_claims")) or [])
                    if isinstance(item, dict) and str(item.get("claim_id") or "").strip()
                ][:6],
                "evidence_ids": [
                    str(item.get("evidence_id") or "").strip()
                    for item in (((packet_payload.get("section_packet") or {}).get("evidence_cards")) or [])
                    if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
                ][:8],
            }
        )
        return json.dumps(packet_payload, ensure_ascii=False)

    return [artifact_search, evidence_search, build_section_packet, get_report_template]


def _default_annotation_for_section(payload: ReportIR, section: CompilerSectionPlanItem) -> SectionTraceAnnotation:
    claim_refs = [
        str(item.get("claim_id") or "").strip()
        for item in _extract_claims_for_section(payload, f"{section.title} {section.goal}")
        if str(item.get("claim_id") or "").strip()
    ][:3]
    evidence_refs = [
        str(item.get("evidence_id") or "").strip()
        for item in _extract_evidence_for_section(payload, f"{section.title} {section.goal}")
        if str(item.get("evidence_id") or "").strip()
    ][:6]
    return SectionTraceAnnotation(
        section_id=str(section.section_id or "").strip(),
        status="ready",
        trace_binding_mode="candidate_only",
        claim_refs=claim_refs,
        evidence_refs=evidence_refs,
        provisional_claim_refs=list(claim_refs),
        provisional_evidence_refs=list(evidence_refs),
        notes="",
        confidence=0.35 if (claim_refs or evidence_refs) else 0.0,
    )


def _merge_annotation_candidates(
    base: SectionTraceAnnotation,
    packet_receipts: List[Dict[str, Any]],
) -> SectionTraceAnnotation:
    claim_refs = list(base.claim_refs)
    evidence_refs = list(base.evidence_refs)
    for receipt in packet_receipts:
        if not isinstance(receipt, dict):
            continue
        claim_refs.extend(
            [
                str(item).strip()
                for item in (receipt.get("verified_claim_ids") or [])
                if str(item or "").strip()
            ]
        )
        evidence_refs.extend(
            [
                str(item).strip()
                for item in (receipt.get("evidence_ids") or [])
                if str(item or "").strip()
            ]
        )
    dedup_claims = list(dict.fromkeys(claim_refs))[:6]
    dedup_evidences = list(dict.fromkeys(evidence_refs))[:10]
    confidence = 0.4 if (dedup_claims or dedup_evidences) else 0.0
    return base.model_copy(
        update={
            "claim_refs": dedup_claims,
            "evidence_refs": dedup_evidences,
            "provisional_claim_refs": dedup_claims,
            "provisional_evidence_refs": dedup_evidences,
            "confidence": max(float(base.confidence or 0.0), confidence),
        }
    )


def write_section_markdown(
    report_ir: ReportIR | Dict[str, Any],
    section: CompilerSectionPlanItem | Dict[str, Any],
    scene_profile: CompilerSceneProfile | Dict[str, Any],
    *,
    template_brief: Dict[str, Any] | None = None,
    writer_context: Dict[str, Any] | None = None,
    section_plan: SectionPlan | Dict[str, Any] | None = None,
) -> SectionMarkdownResult:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    section_item = section if isinstance(section, CompilerSectionPlanItem) else CompilerSectionPlanItem.model_validate(section or {})
    scene = scene_profile if isinstance(scene_profile, CompilerSceneProfile) else CompilerSceneProfile.model_validate(scene_profile or {})
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan or {"sections": [section_item.model_dump()]})
    brief = template_brief if isinstance(template_brief, dict) and template_brief else build_template_brief(plan, scene, writer_context)
    prompts = build_section_write_prompt(payload, section_item, brief, writer_context)
    artifact_search_receipts: List[Dict[str, Any]] = []
    evidence_search_receipts: List[Dict[str, Any]] = []
    packet_receipts: List[Dict[str, Any]] = []
    tools = _build_section_writer_tools(payload, plan, scene, brief, writer_context, artifact_search_receipts, evidence_search_receipts, packet_receipts)
    llm = _get_llm_client()
    thread_id = f"deep-report-section-writer:{payload.meta.topic_identifier or payload.meta.topic_label or 'topic'}:{section_item.section_id}:{uuid.uuid4().hex}"
    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=str(prompts.get("system_prompt") or "").strip(),
        name=f"deep-report-section-writer:{section_item.section_id}",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": str(prompts.get("user_prompt") or "").strip()}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    markdown_body = _normalize_section_markdown_body(_deep_agent_output_text(result), title=str(section_item.title or "").strip())
    markdown_body = _inject_section_figure_refs(markdown_body, str(section_item.section_id or "").strip(), writer_context)
    degraded_reason = ""
    if not markdown_body:
        degraded_reason = "empty_markdown_body"
    return SectionMarkdownResult(
        section_id=str(section_item.section_id or "").strip(),
        title=str(section_item.title or "").strip(),
        markdown_body=markdown_body,
        artifact_search_receipts=artifact_search_receipts,
        evidence_search_receipts=evidence_search_receipts,
        packet_receipts=packet_receipts,
        degraded_reason=degraded_reason,
    )


def compose_bundle_from_section_markdowns(
    report_ir: ReportIR | Dict[str, Any],
    section_plan: SectionPlan | Dict[str, Any],
    scene_profile: CompilerSceneProfile | Dict[str, Any],
    section_results: List[SectionMarkdownResult | Dict[str, Any]],
    *,
    template_brief: Dict[str, Any] | None = None,
) -> DraftBundleV2:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan or {})
    scene = scene_profile if isinstance(scene_profile, CompilerSceneProfile) else CompilerSceneProfile.model_validate(scene_profile or {})
    result_map = {
        str((item.section_id if isinstance(item, SectionMarkdownResult) else (item or {}).get("section_id") or "")).strip(): (
            item if isinstance(item, SectionMarkdownResult) else SectionMarkdownResult.model_validate(item or {})
        )
        for item in section_results
        if str((item.section_id if isinstance(item, SectionMarkdownResult) else (item or {}).get("section_id") or "")).strip()
    }
    all_units: List[DraftUnitV2] = []
    section_receipts: List[Dict[str, Any]] = []
    degraded_sections: List[Dict[str, Any]] = []
    all_artifact_receipts: List[Dict[str, Any]] = []
    all_evidence_receipts: List[Dict[str, Any]] = []
    all_packet_receipts: List[Dict[str, Any]] = []
    annotations: List[Dict[str, Any]] = []
    for index, section in enumerate(plan.sections):
        result = result_map.get(str(section.section_id or "").strip()) or SectionMarkdownResult(section_id=section.section_id, title=section.title, degraded_reason="missing_section_result")
        default_annotation = _merge_annotation_candidates(
            _default_annotation_for_section(payload, section),
            list(result.packet_receipts or []),
        )
        annotations.append(default_annotation.model_dump())
        all_units.append(
            DraftUnitV2(
                unit_id=f"unit:{section.section_id}:heading",
                section_id=section.section_id,
                unit_type="heading",
                text=f"## {section.title}",
                trace_refs=[TraceRef(trace_id=section.section_id, trace_kind="section_context", support_level="structural")],
                derived_from=[],
                support_level="structural",
                context_ref=section.section_id,
                render_template_id=f"{section.section_id}:heading",
                validation_status="pending",
                metadata={"compose_source": "section_markdowns", "template_title": section.template_title or section.title},
            )
        )
        body = str(result.markdown_body or "").strip()
        if body:
            trace_refs = [
                TraceRef(trace_id=claim_id, trace_kind="claim", support_level="direct")
                for claim_id in default_annotation.claim_refs
                if claim_id
            ]
            trace_refs.extend(
                TraceRef(trace_id=evidence_id, trace_kind="evidence", support_level="direct")
                for evidence_id in default_annotation.evidence_refs
                if evidence_id
            )
            if not trace_refs:
                trace_refs = [TraceRef(trace_id=section.section_id, trace_kind="section_context", support_level="structural")]
            all_units.append(
                DraftUnitV2(
                    unit_id=f"unit:{section.section_id}:finding",
                    section_id=section.section_id,
                    unit_type="finding",
                    text=body,
                    trace_refs=trace_refs,
                    derived_from=list(default_annotation.claim_refs),
                    support_level="aggregated",
                    context_ref=section.section_id,
                    render_template_id=f"{section.section_id}:finding",
                    validation_status="pending",
                    metadata={"compose_source": "section_markdowns", "section_index": index, "notes": default_annotation.notes},
                )
            )
        else:
            reason = str(result.degraded_reason or "empty_markdown_body").strip() or "empty_markdown_body"
            degraded_sections.append({"section_id": section.section_id, "title": section.title, "reason": reason, "template_id": section.template_id})
            all_units.append(
                DraftUnitV2(
                    unit_id=f"unit:{section.section_id}:unresolved",
                    section_id=section.section_id,
                    unit_type="unresolved",
                    text="（该章节正文暂未产出，需补写或人工确认。）",
                    trace_refs=[TraceRef(trace_id=section.section_id, trace_kind="section_context", support_level="structural")],
                    derived_from=[],
                    support_level="structural",
                    context_ref=section.section_id,
                    render_template_id=f"{section.section_id}:unresolved",
                    validation_status="failed",
                    metadata={"degraded": True, "compose_source": "section_markdowns", "degraded_reason": reason},
                )
            )
        all_artifact_receipts.extend(result.artifact_search_receipts)
        all_evidence_receipts.extend(result.evidence_search_receipts)
        all_packet_receipts.extend(result.packet_receipts)
        section_receipts.append(
            {
                "section_id": section.section_id,
                "title": section.title,
                "template_id": section.template_id,
                "template_title": section.template_title or section.title,
                "writing_instruction": section.writing_instruction,
                "tool_receipts": [],
                "tool_names": ["get_report_template", "artifact_search", "evidence_search", "build_section_packet"],
                "artifact_query_count": len(result.artifact_search_receipts),
                "evidence_query_count": len(result.evidence_search_receipts),
                "packet_receipt_count": len(result.packet_receipts),
                "trace_candidate_claim_count": len(default_annotation.claim_refs),
                "trace_candidate_evidence_count": len(default_annotation.evidence_refs),
                "degraded": not bool(body),
                "degraded_reason": str(result.degraded_reason or "").strip(),
                "compose_source": "section_markdowns",
            }
        )
    brief = template_brief if isinstance(template_brief, dict) and template_brief else build_template_brief(plan, scene)
    section_markdown_manifest = {
        "section_order": [section.section_id for section in plan.sections],
        "items": [
            {
                "section_id": section.section_id,
                "title": section.title,
                "has_markdown": bool(str((result_map.get(section.section_id) or SectionMarkdownResult()).markdown_body or "").strip()),
                "degraded_reason": str((result_map.get(section.section_id) or SectionMarkdownResult()).degraded_reason or "").strip(),
            }
            for section in plan.sections
        ],
    }
    return DraftBundleV2(
        source_artifact_id="draft_bundle.section_markdown.v2",
        policy_version="policy.v2",
        schema_version="draft-bundle.section-markdown.v2",
        units=all_units,
        section_order=[section.section_id for section in plan.sections],
        metadata={
            "generation_mode": "llm_section_writer",
            "writing_mode": "section_markdown_first",
            "section_count": len(plan.sections),
            "unit_count": len(all_units),
            "section_generation_receipts": section_receipts,
            "degraded_sections": degraded_sections,
            "selected_template": _selected_template_metadata(scene),
            "template_brief": brief,
            "artifact_search_receipts": all_artifact_receipts,
            "evidence_search_receipts": all_evidence_receipts,
            "packet_receipts": all_packet_receipts,
            "section_markdown_manifest": section_markdown_manifest,
            "section_trace_annotations": annotations,
        },
    )


def extract_section_trace_annotations(
    report_ir: ReportIR | Dict[str, Any],
    section_plan: SectionPlan | Dict[str, Any],
    section_results: List[SectionMarkdownResult | Dict[str, Any]],
) -> List[Dict[str, Any]]:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan or {})
    result_map = {
        str((item.section_id if isinstance(item, SectionMarkdownResult) else (item or {}).get("section_id") or "")).strip(): (
            item if isinstance(item, SectionMarkdownResult) else SectionMarkdownResult.model_validate(item or {})
        )
        for item in section_results
        if str((item.section_id if isinstance(item, SectionMarkdownResult) else (item or {}).get("section_id") or "")).strip()
    }
    llm = _get_llm_client()
    try:
        structured_llm = llm.with_structured_output(SectionTraceAnnotation)
    except Exception:
        structured_llm = None
    annotations: List[Dict[str, Any]] = []
    for section in plan.sections:
        result = result_map.get(str(section.section_id or "").strip()) or SectionMarkdownResult(section_id=section.section_id, title=section.title)
        default_annotation = _merge_annotation_candidates(
            _default_annotation_for_section(payload, section),
            list(result.packet_receipts or []),
        )
        body = str(result.markdown_body or "").strip()
        if not body:
            fallback = default_annotation.model_copy(
                update={
                    "status": "degraded",
                    "degraded_reason": "empty_markdown_body",
                    "trace_binding_mode": "structural_only" if not (default_annotation.claim_refs or default_annotation.evidence_refs) else "provisional",
                    "notes": "章节正文为空，使用默认候选 trace。",
                }
            )
            annotations.append(fallback.model_dump())
            continue
        prompt = (
            "请从以下章节正文中抽取最相关的 claim_refs 和 evidence_refs。"
            "只允许从候选列表中选择，不要编造新的 ID。\n\n"
            f"section_id={section.section_id}\n"
            f"title={section.title}\n"
            f"正文：\n{body}\n\n"
            f"候选 claims: {json.dumps(default_annotation.claim_refs, ensure_ascii=False)}\n"
            f"候选 evidences: {json.dumps(default_annotation.evidence_refs, ensure_ascii=False)}\n"
        )
        try:
            if structured_llm is None:
                raise DeepWriterError("structured_output_unavailable")
            parsed = structured_llm.invoke(
                [
                    SystemMessage(content="你是章节 trace 抽取器。返回小结构，不要扩写正文。"),
                    HumanMessage(content=prompt),
                ]
            )
            annotation = parsed if isinstance(parsed, SectionTraceAnnotation) else SectionTraceAnnotation.model_validate(parsed)
            annotation = annotation.model_copy(
                update={
                    "section_id": section.section_id,
                    "status": "ready",
                    "degraded_reason": "",
                    "trace_binding_mode": "direct",
                    "provisional_claim_refs": list(default_annotation.claim_refs),
                    "provisional_evidence_refs": list(default_annotation.evidence_refs),
                }
            )
            annotations.append(annotation.model_dump())
        except Exception:
            has_candidates = bool(default_annotation.claim_refs or default_annotation.evidence_refs)
            fallback = default_annotation.model_copy(
                update={
                    "status": "degraded",
                    "degraded_reason": "trace_extraction_failed" if has_candidates else "no_trace_candidates",
                    "trace_binding_mode": "provisional" if has_candidates else "structural_only",
                    "notes": "trace_extraction_failed" if has_candidates else "no_trace_candidates",
                    "claim_refs": [],
                    "evidence_refs": [],
                }
            )
            annotations.append(fallback.model_dump())
    return annotations


def apply_section_trace_annotations(
    draft_bundle_v2: DraftBundleV2 | Dict[str, Any],
    section_annotations: List[Dict[str, Any]],
) -> DraftBundleV2:
    bundle = draft_bundle_v2 if isinstance(draft_bundle_v2, DraftBundleV2) else DraftBundleV2.model_validate(draft_bundle_v2 or {})
    annotation_map = {
        str(item.get("section_id") or "").strip(): item
        for item in section_annotations
        if isinstance(item, dict) and str(item.get("section_id") or "").strip()
    }
    updated_units: List[DraftUnitV2] = []
    degraded_sections = list(bundle.metadata.get("degraded_sections") or []) if isinstance(bundle.metadata, dict) else []
    degraded_index = {str(item.get("section_id") or "").strip(): item for item in degraded_sections if isinstance(item, dict)}
    for unit in bundle.units:
        if unit.unit_type != "finding":
            updated_units.append(unit)
            continue
        annotation = annotation_map.get(str(unit.section_id or "").strip()) or {}
        claim_refs = [str(item).strip() for item in (annotation.get("claim_refs") or []) if str(item or "").strip()]
        evidence_refs = [str(item).strip() for item in (annotation.get("evidence_refs") or []) if str(item or "").strip()]
        trace_binding_mode = str(annotation.get("trace_binding_mode") or "direct").strip() or "direct"
        if trace_binding_mode == "provisional" and not (claim_refs or evidence_refs):
            claim_refs = [str(item).strip() for item in (annotation.get("provisional_claim_refs") or []) if str(item or "").strip()]
            evidence_refs = [str(item).strip() for item in (annotation.get("provisional_evidence_refs") or []) if str(item or "").strip()]
        trace_refs: List[TraceRef] = [
            TraceRef(trace_id=claim_id, trace_kind="claim", support_level="direct")
            for claim_id in claim_refs
        ]
        trace_refs.extend(
            TraceRef(trace_id=evidence_id, trace_kind="evidence", support_level="direct")
            for evidence_id in evidence_refs
        )
        if not trace_refs:
            trace_refs = list(unit.trace_refs)
        updated_units.append(
            unit.model_copy(
                update={
                    "trace_refs": trace_refs,
                    "derived_from": claim_refs or list(unit.derived_from or []),
                    "metadata": {
                        **dict(unit.metadata or {}),
                        "section_trace_notes": str(annotation.get("notes") or "").strip(),
                        "trace_annotation_confidence": float(annotation.get("confidence") or 0.0),
                        "trace_annotation_status": str(annotation.get("status") or "ready").strip() or "ready",
                        "trace_binding_mode": trace_binding_mode,
                        "provisional_claim_refs": [str(item).strip() for item in (annotation.get("provisional_claim_refs") or []) if str(item or "").strip()],
                        "provisional_evidence_refs": [str(item).strip() for item in (annotation.get("provisional_evidence_refs") or []) if str(item or "").strip()],
                    },
                }
            )
        )
        if str(annotation.get("status") or "").strip() == "degraded" and unit.section_id not in degraded_index:
            degraded_sections.append(
                {
                    "section_id": unit.section_id,
                    "title": "",
                    "reason": str(annotation.get("degraded_reason") or "trace_extraction_failed").strip() or "trace_extraction_failed",
                }
            )
            degraded_index[unit.section_id] = degraded_sections[-1]
    metadata = dict(bundle.metadata or {})
    metadata["section_trace_annotations"] = list(section_annotations or [])
    metadata["degraded_sections"] = degraded_sections
    metadata["unit_count"] = len(updated_units)
    return bundle.model_copy(update={"units": updated_units, "metadata": metadata})


def _normalize_heading(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").replace("#", "").strip().lower())


def light_edit_draft_bundle(
    draft_bundle_v2: DraftBundleV2 | Dict[str, Any],
    section_plan: SectionPlan | Dict[str, Any],
) -> DraftBundleV2:
    bundle = draft_bundle_v2 if isinstance(draft_bundle_v2, DraftBundleV2) else DraftBundleV2.model_validate(draft_bundle_v2 or {})
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan or {})
    title_map = {section.section_id: section.title for section in plan.sections}
    existing_ids = {unit.unit_id for unit in bundle.units}
    edited_units: List[DraftUnitV2] = []
    inserted_transitions = 0
    seen_findings: set[str] = set()
    prev_title_by_section = {plan.sections[index].section_id: plan.sections[index - 1].title for index in range(1, len(plan.sections))}
    for unit in bundle.units:
        if unit.unit_type == "heading":
            normalized_title = title_map.get(unit.section_id, unit.text.replace("#", "").strip())
            unit = unit.model_copy(update={"text": f"## {normalized_title}"})
        if unit.unit_type == "finding" and unit.section_id in prev_title_by_section and unit.section_id not in seen_findings:
            transition_id = f"unit:{unit.section_id}:transition"
            if transition_id not in existing_ids:
                edited_units.append(
                    DraftUnitV2(
                        unit_id=transition_id,
                        section_id=unit.section_id,
                        unit_type="transition",
                        text=f"承接前文对{prev_title_by_section[unit.section_id]}的梳理，下面转向{title_map.get(unit.section_id, unit.section_id)}。",
                        trace_refs=[TraceRef(trace_id=unit.section_id, trace_kind="section_context", support_level="structural")],
                        derived_from=[],
                        support_level="structural",
                        context_ref=unit.section_id,
                        render_template_id=f"{unit.section_id}:transition",
                        validation_status="pending",
                        metadata={"editor_added": True},
                    )
                )
                inserted_transitions += 1
                existing_ids.add(transition_id)
            seen_findings.add(unit.section_id)
        edited_units.append(unit)
    metadata = dict(bundle.metadata or {})
    metadata["editor_receipt"] = {
        "editor_mode": "light_transition_editor",
        "transition_inserted": inserted_transitions,
        "heading_standardized": True,
    }
    metadata["unit_count"] = len(edited_units)
    return bundle.model_copy(update={"units": edited_units, "metadata": metadata})


def compile_draft_units_with_llm(
    report_ir: ReportIR,
    section_plan: SectionPlan,
    scene_profile: CompilerSceneProfile,
) -> DraftBundleV2:
    payload = report_ir if isinstance(report_ir, ReportIR) else ReportIR.model_validate(report_ir)
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan)
    template_brief = build_template_brief(plan, scene_profile)
    section_results = [
        write_section_markdown(
            payload,
            section,
            scene_profile,
            template_brief=template_brief,
            section_plan=plan,
        )
        for section in plan.sections
    ]
    bundle = compose_bundle_from_section_markdowns(
        payload,
        plan,
        scene_profile,
        section_results,
        template_brief=template_brief,
    )
    annotations = extract_section_trace_annotations(payload, plan, section_results)
    bundle = apply_section_trace_annotations(bundle, annotations)
    return light_edit_draft_bundle(bundle, plan)
