from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from deepagents.backends.utils import create_file_data
from langchain.agents.middleware.types import wrap_tool_call
from langchain.agents.structured_output import AutoStrategy
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import ValidationError

from ...utils.ai import build_langchain_chat_model, call_langchain_chat
from ...utils.setting.paths import get_data_root
from ...utils.setting.settings import settings
from ..agent_runtime import ensure_langchain_uuid_compat
from .assets import RUNTIME_STORE, build_artifacts_root, build_runtime_assets, ensure_memory_seed
from .deterministic import build_analyze_results_payload, build_base_context, build_workspace_files, ensure_cache_dir
from .document import (
    assemble_report_document,
    build_chart_catalog,
    build_chart_summary_for_composer,
    build_data_summary_for_composer,
    build_report_document,
)
from .presenter import build_full_payload, render_markdown
from .schemas import (
    DocumentComposerOutput,
    ReportDataBundle,
    EvidenceBundle,
    PropagationBundle,
    RetrievalPlan,
    StructuredReport,
    StanceBundle,
    TimelineBundle,
    ValidationBundle,
)
from .tools import build_entity_graph, build_timeline, query_documents, run_volume_analysis, verify_claim


REPORT_CACHE_FILENAME = "report_payload.json"
REPORT_CACHE_VERSION = 2
AI_FULL_REPORT_CACHE_FILENAME = "ai_full_report_payload.json"
AI_FULL_REPORT_CACHE_VERSION = 9
DEEP_AGENT_CHECKPOINTER = InMemorySaver()
_NAMESPACE_COMPONENT = re.compile(r"[^A-Za-z0-9._@:+~-]+")

SPECIALIST_SKILLS = {
    "retrieval_router": ["retrieval-router-rules"],
    "evidence_organizer": ["evidence-source-credibility"],
    "timeline_analyst": ["timeline-alignment-slicing"],
    "stance_conflict": ["subject-stance-merging"],
    "propagation_analyst": ["propagation-explanation-framework", "chart-interpretation-guidelines"],
    "validator": ["quality-validation-backlink"],
    "document_composer": ["chart-interpretation-guidelines"],
}


class ReportRuntimeFailure(RuntimeError):
    def __init__(self, message: str, diagnostic: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.task_diagnostic = diagnostic if isinstance(diagnostic, dict) else {}


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def _safe_tool_round_limit(key: str, default: Optional[int]) -> Optional[int]:
    try:
        value = settings.get(key, default)
        if value is None:
            return None
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else None


def _resolve_report_tool_round_limits() -> Dict[str, Optional[int]]:
    default_limit = _safe_tool_round_limit("llm.langchain.max_tool_rounds", None)
    coordinator_limit = _safe_tool_round_limit("llm.langchain.report_max_tool_rounds", default_limit)
    subagent_limit = _safe_tool_round_limit("llm.langchain.report_subagent_max_tool_rounds", coordinator_limit)
    return {
        "default": default_limit,
        "coordinator": coordinator_limit,
        "subagent": subagent_limit,
    }


def _safe_async(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _emit(callback: Optional[Callable[[Dict[str, Any]], None]], payload: Dict[str, Any]) -> None:
    if not callable(callback):
        return
    try:
        callback(payload)
    except Exception:
        return


def _default_thread_id(topic_identifier: str, start: str, end: str) -> str:
    return f"report::{topic_identifier}::{start}::{end or start}"


def _safe_namespace_component(value: str, *, fallback: str) -> str:
    text = _NAMESPACE_COMPONENT.sub("-", str(value or "").strip()).strip("-")
    return text or fallback


def _namespace_factory(topic_identifier: str, task_id: str, bucket_name: str):
    safe_topic = _safe_namespace_component(topic_identifier, fallback="topic")
    safe_task = _safe_namespace_component(task_id, fallback="task")
    safe_bucket = _safe_namespace_component(bucket_name, fallback="bucket")
    return lambda _ctx: ("report", safe_topic, safe_task, safe_bucket)


def _build_backend_factory(
    *,
    task_id: str,
    topic_identifier: str,
    topic_label: str,
    seed_files: Dict[str, Dict[str, Any]],
) -> Tuple[Callable[[Any], CompositeBackend], Dict[str, Dict[str, Any]], List[str], List[str]]:
    runtime_files, skill_sources, memory_paths = build_runtime_assets(topic_label)
    merged_files: Dict[str, Dict[str, Any]] = {}
    merged_files.update(runtime_files)
    merged_files.update(seed_files)
    artifacts_root = build_artifacts_root(task_id, get_data_root())
    ensure_memory_seed(_namespace_factory(topic_identifier, task_id, "memories")(None), topic_label)

    def factory(runtime: Any) -> CompositeBackend:
        default_backend = StateBackend(runtime)
        memory_backend = StoreBackend(runtime, namespace=_namespace_factory(topic_identifier, task_id, "memories"))
        artifacts_backend = FilesystemBackend(root_dir=artifacts_root, virtual_mode=False)
        return CompositeBackend(
            default=default_backend,
            routes={
                "/memories/": memory_backend,
                "/artifacts/": artifacts_backend,
            },
        )

    return factory, merged_files, skill_sources, memory_paths


def _seed_invoke_payload(files: Dict[str, Dict[str, Any]], prompt: str) -> Dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": prompt}],
        "files": files,
    }


def _structured_to_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value if isinstance(value, dict) else {}


def _call_writer_markdown(prompt: str) -> str:
    text = _safe_async(
        call_langchain_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是一名舆情报告写作代理。请把给定结构化对象渲染成正式 Markdown，"
                        "只写用户可读内容，不暴露内部字段名、工具名、缓存结构。"
                        "不需要刻意节省 token，优先保证成稿逻辑、论证完整、结构扎实。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            task="report",
            model_role="report",
            temperature=0.15,
            max_tokens=4200,
        )
    )
    return str(text or "").strip()


def _invoke_document_composer(
    bundle: "ReportDataBundle",
    chart_catalog: List[Dict[str, Any]],
    *,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Optional["DocumentComposerOutput"]:
    """Call the AI document composer to produce an intelligent report layout.

    The composer receives a compact chart catalog + structured data summary and
    returns a DocumentComposerOutput describing sections, block types, AI-written
    narrative, and chart_slot references.  On any failure returns None so the
    caller can fall back to the deterministic document builder.
    """
    llm, _ = build_langchain_chat_model(task="report", model_role="report", temperature=0.15, max_tokens=4800)
    if llm is None:
        return None

    chart_summary = build_chart_summary_for_composer(chart_catalog)
    data_summary = build_data_summary_for_composer(bundle)

    available_chart_ids = [item["chart_id"] for item in chart_summary if item.get("has_data")]
    available_ids_note = (
        f"可用图表 ID（共 {len(available_chart_ids)} 个，has_data=true）：{json.dumps(available_chart_ids, ensure_ascii=False)}"
        if available_chart_ids
        else "当前没有有效图表数据（has_data=false），不要在 chart_slot 中引用任何 chart_id。"
    )

    system_prompt = (
        "你是一名舆情报告文档编排代理。"
        "你的任务是根据给定的结构化分析结果和图表目录，设计并输出一份完整的报告文档结构（DocumentComposerOutput）。\n\n"
        "【核心规则】\n"
        "1. chart_slot 的 chart_ids 字段中的每一个 ID，必须来自下面提供的“可用图表目录”，不能自造。\n"
        "2. 每个 narrative block 的 content 必须是基于数据写出的有判断性的文字（不少于 80 字），不要复制字段名，不要写空洞句子。\n"
        "3. chart_slot 的 description 要说明这张图在本章节的分析价值（如：'该图展示了各渠道声量峰值，可用于判断传播节点'）。\n"
        "4. 章节数量建议 3-4 个，覆盖：核心维度、生命周期、主体与立场、传播/风险/建议。\n"
        "5. 每章节把相关的图表放入 chart_slot，再配合 narrative 解释图表含义与判断依据。\n"
        "6. evidence_list、timeline_list、subject_cards、stance_matrix、risk_list、action_list 只能引用数据摘要中提供的 ID。\n"
        "7. 附录（appendix）包含 citation_refs 和一个 callout；也可以不设附录（留 null），系统会自动生成默认附录。\n"
        "8. 如果某类数据为空（如 evidence_ids 为空列表），不要在章节中强行添加对应的 block。\n"
    )

    user_content = (
        f"{available_ids_note}\n\n"
        f"图表目录详情：\n{json.dumps(chart_summary, ensure_ascii=False, indent=2)}\n\n"
        f"结构化数据摘要：\n{json.dumps(data_summary, ensure_ascii=False, indent=2)}"
    )

    _emit(
        event_callback,
        {
            "type": "subagent.started",
            "phase": "write",
            "agent": "document_composer",
            "title": "文档编排代理已启动",
            "message": "正在根据图表目录和结构化数据设计报告章节与图文编排。",
            "payload": {"agent_name": "document_composer", "available_charts": len(available_chart_ids)},
        },
    )

    try:
        structured_llm = llm.with_structured_output(DocumentComposerOutput)
        result = _safe_async(structured_llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]))
        if result is None or not isinstance(result, DocumentComposerOutput):
            return None
        _emit(
            event_callback,
            {
                "type": "subagent.completed",
                "phase": "write",
                "agent": "document_composer",
                "title": "文档编排代理已完成",
                "message": f"AI 设计了 {len(result.sections)} 个章节。",
                "payload": {"section_count": len(result.sections)},
            },
        )
        return result
    except Exception as exc:
        _emit(
            event_callback,
            {
                "type": "agent.memo",
                "phase": "write",
                "agent": "document_composer",
                "title": "文档编排代理异常，已降级为确定性布局",
                "message": str(exc)[:200],
                "payload": {},
            },
        )
        return None


def _write_json(path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _load_json(path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _extract_structured_response(result: Any) -> Dict[str, Any]:
    payload = result if isinstance(result, dict) else getattr(result, "value", result)
    if not isinstance(payload, dict):
        return {}
    structured = payload.get("structured_response")
    return _structured_to_dict(structured)


def _result_diagnostic_summary(result: Any) -> Dict[str, Any]:
    payload = result if isinstance(result, dict) else getattr(result, "value", result)
    if not isinstance(payload, dict):
        return {"result_type": type(result).__name__}
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    last_message_preview = ""
    if messages:
        last_message = messages[-1]
        content = getattr(last_message, "content", None)
        if isinstance(content, str):
            last_message_preview = content.strip()[:300]
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item.get("text", "").strip())
            last_message_preview = "\n".join(parts).strip()[:300]
        else:
            last_message_preview = str(content or "").strip()[:300]
    return {
        "payload_keys": sorted(payload.keys()),
        "has_structured_response": bool(payload.get("structured_response")),
        "message_count": len(messages),
        "last_message_preview": last_message_preview,
        "interrupt_count": len(payload.get("__interrupt__") or []) if isinstance(payload.get("__interrupt__"), list) else 0,
    }


def _payload_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if metadata:
        return metadata
    return payload.get("meta") if isinstance(payload.get("meta"), dict) else {}


def _matches_current_run(payload: Dict[str, Any], *, runtime_task_id: str, thread_id: str) -> bool:
    metadata = _payload_meta(payload)
    if not metadata:
        return False
    payload_task_id = str(metadata.get("runtime_task_id") or metadata.get("task_id") or "").strip()
    payload_thread_id = str(metadata.get("thread_id") or "").strip()
    return payload_task_id == runtime_task_id and payload_thread_id == thread_id


def _parse_json_object(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    text = str(raw_value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _pick_first(source: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in source and source.get(key) not in (None, ""):
            return source.get(key)
    return default


def _normalize_string_list(value: Any) -> List[str]:
    output: List[str] = []
    for item in _as_list(value):
        text = str(item or "").strip()
        if text:
            output.append(text)
    return output


def _normalize_choice(value: Any, allowed: List[str], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _normalize_citation_ids(value: Any) -> List[str]:
    output: List[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            text = str(
                item.get("citation_id")
                or item.get("id")
                or item.get("ref_id")
                or item.get("source_id")
                or ""
            ).strip()
        else:
            text = str(item or "").strip()
        if text:
            output.append(text)
    return output


def _normalize_object_list(value: Any) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            output.append(dict(item))
    return output


def _unwrap_structured_payload(raw_payload: Any) -> Dict[str, Any]:
    if not isinstance(raw_payload, dict):
        return {}
    for key in ("payload", "report", "structured_report", "data", "result"):
        nested = raw_payload.get(key)
        if isinstance(nested, dict):
            return nested
    return raw_payload


def _normalize_structured_report_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(_unwrap_structured_payload(raw_payload) or {})
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    conclusion = payload.get("conclusion") if isinstance(payload.get("conclusion"), dict) else {}
    if not conclusion and isinstance(payload.get("summary"), dict):
        conclusion = dict(payload.get("summary") or {})

    normalized: Dict[str, Any] = {
        "task": {
            **task,
            "topic_identifier": str(_pick_first(task, "topic_identifier", "topic_id")).strip(),
            "topic_label": str(_pick_first(task, "topic_label", "topic_name", "topic")).strip(),
            "start": str(_pick_first(task, "start", default=task.get("time_range", {}).get("start") if isinstance(task.get("time_range"), dict) else "")).strip(),
            "end": str(_pick_first(task, "end", default=task.get("time_range", {}).get("end") if isinstance(task.get("time_range"), dict) else "")).strip(),
            "mode": str(_pick_first(task, "mode", "analysis_mode", default="fast")).strip() or "fast",
            "thread_id": str(_pick_first(task, "thread_id")).strip(),
        },
        "conclusion": {
            "executive_summary": str(_pick_first(conclusion, "executive_summary", "summary", "overview")).strip(),
            "key_findings": _normalize_string_list(_pick_first(conclusion, "key_findings", "findings", "highlights", default=[])),
            "key_risks": _normalize_string_list(_pick_first(conclusion, "key_risks", "risks", "risk_points", default=[])),
            "confidence_label": str(_pick_first(conclusion, "confidence_label", "confidence", "confidence_level", default="待评估")).strip() or "待评估",
        },
        "timeline": [],
        "subjects": [],
        "stance_matrix": [],
        "key_evidence": [],
        "conflict_points": [],
        "propagation_features": [],
        "risk_judgement": [],
        "unverified_points": [],
        "suggested_actions": [],
        "citations": [],
        "validation_notes": [],
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }

    for index, item in enumerate(_normalize_object_list(payload.get("timeline"))):
        normalized["timeline"].append(
            {
                "event_id": str(_pick_first(item, "event_id", "id", default=f"event-{index + 1}")).strip() or f"event-{index + 1}",
                "date": str(_pick_first(item, "date", "time", "time_label")).strip(),
                "title": str(_pick_first(item, "title", "name", "label", default=f"事件 {index + 1}")).strip() or f"事件 {index + 1}",
                "description": str(_pick_first(item, "description", "summary", "content")).strip(),
                "trigger": str(_pick_first(item, "trigger", "reason")).strip(),
                "impact": str(_pick_first(item, "impact", "effect", "result")).strip(),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", "citation_refs", default=[])),
                "causal_links": _normalize_string_list(_pick_first(item, "causal_links", "links", "related_events", default=[])),
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("subjects"))):
        normalized["subjects"].append(
            {
                "subject_id": str(_pick_first(item, "subject_id", "id", default=f"subject-{index + 1}")).strip() or f"subject-{index + 1}",
                "name": str(_pick_first(item, "name", "subject", default=f"主体 {index + 1}")).strip() or f"主体 {index + 1}",
                "category": str(_pick_first(item, "category", "type")).strip(),
                "role": str(_pick_first(item, "role", "position")).strip(),
                "summary": str(_pick_first(item, "summary", "description", "finding")).strip(),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", default=[])),
            }
        )

    for item in _normalize_object_list(payload.get("stance_matrix")):
        normalized["stance_matrix"].append(
            {
                "subject": str(_pick_first(item, "subject", "name", "subject_name")).strip(),
                "stance": str(_pick_first(item, "stance", "position", "view")).strip(),
                "summary": str(_pick_first(item, "summary", "description", "reason")).strip(),
                "conflict_with": _normalize_string_list(_pick_first(item, "conflict_with", "conflicts", "conflict_subjects", default=[])),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", default=[])),
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("key_evidence"))):
        normalized["key_evidence"].append(
            {
                "evidence_id": str(_pick_first(item, "evidence_id", "id", default=f"evidence-{index + 1}")).strip() or f"evidence-{index + 1}",
                "finding": str(_pick_first(item, "finding", "claim", "summary", "text", default=f"证据 {index + 1}")).strip() or f"证据 {index + 1}",
                "subject": str(_pick_first(item, "subject", "name")).strip(),
                "stance": str(_pick_first(item, "stance", "position")).strip(),
                "time_label": str(_pick_first(item, "time_label", "date", "time")).strip(),
                "source_summary": str(_pick_first(item, "source_summary", "source", "source_title", "title")).strip(),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", default=[])),
                "confidence": _normalize_choice(_pick_first(item, "confidence", default="medium"), ["high", "medium", "low"], "medium"),
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("conflict_points"))):
        normalized["conflict_points"].append(
            {
                "conflict_id": str(_pick_first(item, "conflict_id", "id", default=f"conflict-{index + 1}")).strip() or f"conflict-{index + 1}",
                "title": str(_pick_first(item, "title", "label", default=f"冲突点 {index + 1}")).strip() or f"冲突点 {index + 1}",
                "description": str(_pick_first(item, "description", "summary", "finding")).strip(),
                "subjects": _normalize_string_list(_pick_first(item, "subjects", "participants", "actors", default=[])),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", default=[])),
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("propagation_features"))):
        normalized["propagation_features"].append(
            {
                "feature_id": str(_pick_first(item, "feature_id", "id", default=f"feature-{index + 1}")).strip() or f"feature-{index + 1}",
                "dimension": str(_pick_first(item, "dimension", "label", "category", default=f"维度 {index + 1}")).strip() or f"维度 {index + 1}",
                "finding": str(_pick_first(item, "finding", "summary", "conclusion", default=f"传播特征 {index + 1}")).strip() or f"传播特征 {index + 1}",
                "explanation": str(_pick_first(item, "explanation", "reason", "description")).strip(),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", default=[])),
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("risk_judgement"))):
        normalized["risk_judgement"].append(
            {
                "risk_id": str(_pick_first(item, "risk_id", "id", default=f"risk-{index + 1}")).strip() or f"risk-{index + 1}",
                "label": str(_pick_first(item, "label", "title", "risk", default=f"风险 {index + 1}")).strip() or f"风险 {index + 1}",
                "level": _normalize_choice(_pick_first(item, "level", "severity", default="medium"), ["high", "medium", "low"], "medium"),
                "summary": str(_pick_first(item, "summary", "description", "finding")).strip(),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", default=[])),
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("unverified_points"))):
        normalized["unverified_points"].append(
            {
                "item_id": str(_pick_first(item, "item_id", "id", default=f"unverified-{index + 1}")).strip() or f"unverified-{index + 1}",
                "statement": str(_pick_first(item, "statement", "claim", "text", default=f"待核验点 {index + 1}")).strip() or f"待核验点 {index + 1}",
                "reason": str(_pick_first(item, "reason", "summary", "description")).strip(),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", default=[])),
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("suggested_actions"))):
        normalized["suggested_actions"].append(
            {
                "action_id": str(_pick_first(item, "action_id", "id", default=f"action-{index + 1}")).strip() or f"action-{index + 1}",
                "action": str(_pick_first(item, "action", "title", "label", "suggestion", default=f"建议动作 {index + 1}")).strip() or f"建议动作 {index + 1}",
                "rationale": str(_pick_first(item, "rationale", "reason", "summary")).strip(),
                "priority": _normalize_choice(_pick_first(item, "priority", "level", default="medium"), ["high", "medium", "low"], "medium"),
                "citation_ids": _normalize_citation_ids(_pick_first(item, "citation_ids", "citations", default=[])),
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("citations"))):
        normalized["citations"].append(
            {
                "citation_id": str(_pick_first(item, "citation_id", "id", "ref_id", default=f"E{index + 1:03d}")).strip() or f"E{index + 1:03d}",
                "title": str(_pick_first(item, "title", "headline", "source_title")).strip(),
                "url": str(_pick_first(item, "url", "link", "source_url")).strip(),
                "published_at": str(_pick_first(item, "published_at", "date", "time")).strip(),
                "platform": str(_pick_first(item, "platform", "site", "channel", "media")).strip(),
                "snippet": str(_pick_first(item, "snippet", "excerpt", "summary", "text")).strip(),
                "source_type": str(_pick_first(item, "source_type", "type", "source", default="document")).strip() or "document",
            }
        )

    for index, item in enumerate(_normalize_object_list(payload.get("validation_notes"))):
        normalized["validation_notes"].append(
            {
                "note_id": str(_pick_first(item, "note_id", "id", default=f"note-{index + 1}")).strip() or f"note-{index + 1}",
                "category": _normalize_choice(_pick_first(item, "category", "type", "kind", default="coverage"), ["fact", "timeline", "subject", "coverage"], "coverage"),
                "severity": _normalize_choice(_pick_first(item, "severity", "level", default="medium"), ["high", "medium", "low"], "medium"),
                "message": str(_pick_first(item, "message", "summary", "text", default=f"校验说明 {index + 1}")).strip() or f"校验说明 {index + 1}",
                "related_ids": _normalize_string_list(_pick_first(item, "related_ids", "related", default=[])),
            }
        )

    normalized["metadata"].update(payload.get("meta") if isinstance(payload.get("meta"), dict) else {})
    return normalized


def _build_structured_seed_payload(
    *,
    topic_identifier: str,
    topic_label: str,
    start_text: str,
    end_text: str,
    mode: str,
    thread_id: str,
) -> Dict[str, Any]:
    return {
        "task": {
            "topic_identifier": topic_identifier,
            "topic_label": topic_label,
            "start": start_text,
            "end": end_text,
            "mode": mode,
            "thread_id": thread_id,
        },
        "conclusion": {
            "executive_summary": "",
            "key_findings": [],
            "key_risks": [],
            "confidence_label": "待评估",
        },
        "timeline": [],
        "subjects": [],
        "stance_matrix": [],
        "key_evidence": [],
        "conflict_points": [],
        "propagation_features": [],
        "risk_judgement": [],
        "unverified_points": [],
        "suggested_actions": [],
        "citations": [],
        "validation_notes": [],
        "metadata": {},
    }


def _merge_structured_payload(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in (overlay or {}).items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_structured_payload(existing, value)
            continue
        if isinstance(existing, list) and isinstance(value, list):
            merged[key] = value if value else existing
            continue
        if isinstance(value, str):
            merged[key] = value if value.strip() else existing
            continue
        if value not in (None, ""):
            merged[key] = value
    return merged


def _finalize_structured_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    output = _normalize_structured_report_payload(payload)
    conclusion = output.get("conclusion") if isinstance(output.get("conclusion"), dict) else {}
    if not str(conclusion.get("executive_summary") or "").strip():
        findings = _normalize_string_list(conclusion.get("key_findings"))
        risks = _normalize_string_list(conclusion.get("key_risks"))
        evidence = output.get("key_evidence") if isinstance(output.get("key_evidence"), list) else []
        propagation = output.get("propagation_features") if isinstance(output.get("propagation_features"), list) else []
        candidates = [
            findings[0] if findings else "",
            risks[0] if risks else "",
            str(evidence[0].get("finding") or "").strip() if evidence and isinstance(evidence[0], dict) else "",
            str(propagation[0].get("finding") or "").strip() if propagation and isinstance(propagation[0], dict) else "",
        ]
        summary = next((item for item in candidates if item), "")
        if summary:
            conclusion["executive_summary"] = summary
    return output


def _hydrate_render_layers(
    payload: Dict[str, Any],
    *,
    topic_identifier: str,
    topic_label: str,
    start_text: str,
    end_text: str,
    composer_output: Optional["DocumentComposerOutput"] = None,
) -> Dict[str, Any]:
    output = dict(payload or {})
    report_data = ReportDataBundle.model_validate(
        {
            "task": output.get("task") or {},
            "conclusion": output.get("conclusion") or {},
            "timeline": output.get("timeline") or [],
            "subjects": output.get("subjects") or [],
            "stance_matrix": output.get("stance_matrix") or [],
            "key_evidence": output.get("key_evidence") or [],
            "conflict_points": output.get("conflict_points") or [],
            "propagation_features": output.get("propagation_features") or [],
            "risk_judgement": output.get("risk_judgement") or [],
            "unverified_points": output.get("unverified_points") or [],
            "suggested_actions": output.get("suggested_actions") or [],
            "citations": output.get("citations") or [],
            "validation_notes": output.get("validation_notes") or [],
        }
    )
    analyze_results = build_analyze_results_payload(
        topic_identifier,
        start_text,
        end_text,
        topic_label=topic_label,
    )
    functions_payload = analyze_results.get("functions") if isinstance(analyze_results.get("functions"), list) else []
    chart_catalog = build_chart_catalog(functions_payload)
    base_context = build_base_context(
        topic_identifier,
        start_text,
        end_text,
        topic_label=topic_label,
        mode=str(((output.get("task") or {}).get("mode")) or "fast"),
    )
    overview = base_context.get("overview") if isinstance(base_context.get("overview"), dict) else {}
    if composer_output is not None:
        report_document = assemble_report_document(composer_output, report_data, chart_catalog, overview)
    else:
        report_document = build_report_document(report_data, chart_catalog, overview)
    output["report_data"] = report_data.model_dump()
    output["chart_catalog"] = chart_catalog
    output["report_document"] = report_document
    output["chart_catalog_version"] = int(report_document.get("chart_catalog_version") or 1)
    return output


def _summarize_validation_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        if errors:
            first = errors[0]
            location = ".".join(str(item) for item in (first.get("loc") or []) if str(item).strip())
            message = str(first.get("msg") or "字段不合法").strip()
            return f"{location or 'root'}: {message}"
    text = str(exc or "").strip()
    return text or exc.__class__.__name__


def _upsert_runtime_json_file(files: Optional[Dict[str, Dict[str, Any]]], path: str, payload: Dict[str, Any]) -> None:
    if not isinstance(files, dict) or not path:
        return
    files[path] = create_file_data(json.dumps(payload or {}, ensure_ascii=False, indent=2))


def _build_todos() -> List[Dict[str, Any]]:
    return [
        {"id": "scope", "label": "范围确认", "status": "completed"},
        {"id": "retrieval", "label": "检索路由", "status": "pending"},
        {"id": "evidence", "label": "证据整理", "status": "pending"},
        {"id": "structure", "label": "结构分析", "status": "pending"},
        {"id": "writing", "label": "文稿生成", "status": "pending"},
        {"id": "validation", "label": "质量校验", "status": "pending"},
        {"id": "persist", "label": "审批与存储", "status": "pending"},
    ]


def _set_todo_status(todos: List[Dict[str, Any]], todo_id: str, status: str) -> List[Dict[str, Any]]:
    output = []
    for item in todos:
        row = dict(item)
        if row.get("id") == todo_id:
            row["status"] = status
        output.append(row)
    return output


def _phase_for_subagent(agent_name: str) -> str:
    key = str(agent_name or "").strip()
    mapping = {
        "retrieval_router": "interpret",
        "evidence_organizer": "interpret",
        "timeline_analyst": "interpret",
        "stance_conflict": "interpret",
        "propagation_analyst": "interpret",
        "writer": "write",
        "validator": "review",
    }
    return mapping.get(key, "interpret")


def _normalize_deep_todos(raw_todos: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_todos, list):
        return []
    normalized: List[Dict[str, Any]] = []
    status_map = {"pending": "pending", "in_progress": "running", "completed": "completed"}
    for index, item in enumerate(raw_todos):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        status = status_map.get(str(item.get("status") or "").strip().lower(), "pending")
        slug = _safe_namespace_component(content.lower(), fallback=f"todo-{index + 1}")
        normalized.append(
            {
                "id": f"todo-{index + 1}-{slug}",
                "label": content,
                "status": status,
            }
        )
    return normalized


def _tool_result_preview(result: Any) -> str:
    if isinstance(result, ToolMessage):
        return str(result.content or "").strip()[:300]
    if isinstance(result, Command):
        update = result.update if isinstance(result.update, dict) else {}
        messages = update.get("messages") if isinstance(update.get("messages"), list) else []
        if messages:
            last = messages[-1]
            content = getattr(last, "content", None)
            if content is None:
                content = getattr(last, "text", None)
            return str(content or "").strip()[:300]
    return ""


def _build_lifecycle_middleware(
    *,
    event_callback: Optional[Callable[[Dict[str, Any]], None]],
    actor_name: str,
    default_phase: str,
    tracker: Optional[Dict[str, Any]] = None,
    task_tool_mode: bool = False,
    max_tool_rounds: Optional[int] = None,
) -> Any:
    @wrap_tool_call(name="DeepReportLifecycleMiddleware")
    def _intercept(request, handler):
        tool_call = request.tool_call if isinstance(request.tool_call, dict) else {}
        tool_name = str(tool_call.get("name") or "").strip()
        args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
        tool_call_id = str(tool_call.get("id") or "").strip()
        shared = tracker if isinstance(tracker, dict) else None
        current_rounds = 0
        if shared is not None and tool_name:
            tool_calls = shared.setdefault("tool_calls", [])
            if tool_name not in tool_calls:
                tool_calls.append(tool_name)
            tool_round_counts = shared.setdefault("tool_round_counts", {})
            current_rounds = int(tool_round_counts.get(actor_name) or 0) + 1
            tool_round_counts[actor_name] = current_rounds
            if max_tool_rounds is not None:
                tool_round_limits = shared.setdefault("tool_round_limits", {})
                tool_round_limits[actor_name] = int(max_tool_rounds)

        if tool_name:
            _emit(
                event_callback,
                {
                    "type": "tool.called",
                    "phase": default_phase,
                    "agent": actor_name,
                    "title": f"调用工具：{tool_name}",
                    "message": f"{actor_name} 正在调用工具。",
                    "payload": {
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "tool_round_count": current_rounds,
                        "tool_round_limit": int(max_tool_rounds) if max_tool_rounds is not None else None,
                        "args_preview": json.dumps(args, ensure_ascii=False)[:300] if args else "",
                    },
                },
            )
            if max_tool_rounds is not None and current_rounds > int(max_tool_rounds):
                limit_message = (
                    "总控代理已达到最大工具回合限制。"
                    if actor_name == "report_coordinator"
                    else f"{actor_name} 子代理已达到最大工具回合限制。"
                )
                _emit(
                    event_callback,
                    {
                        "type": "agent.memo",
                        "phase": default_phase,
                        "agent": actor_name,
                        "title": "达到工具回合上限",
                        "message": limit_message,
                        "payload": {
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "tool_round_count": current_rounds,
                            "tool_round_limit": int(max_tool_rounds),
                        },
                    },
                )
                raise RuntimeError(
                    f"{'总控代理' if actor_name == 'report_coordinator' else f'{actor_name} 子代理'} "
                    f"已达到最大工具回合限制（{int(max_tool_rounds)}）。"
                )

        if tool_name == "write_todos":
            todos = _normalize_deep_todos(args.get("todos"))
            if todos:
                _emit(
                    event_callback,
                    {
                        "type": "todo.updated",
                        "phase": default_phase,
                        "title": "任务清单已更新",
                        "message": f"总控代理更新了任务清单（{len(todos)} 项）。",
                        "payload": {"todos": todos},
                    },
                )

        subagent_type = ""
        subagent_phase = default_phase
        if task_tool_mode and tool_name == "task":
            subagent_type = str(args.get("subagent_type") or "").strip()
            subagent_phase = _phase_for_subagent(subagent_type)
            task_preview = str(args.get("description") or "").strip()[:240]
            if shared is not None and subagent_type:
                started = shared.setdefault("subagents_started", [])
                started.append(subagent_type)
            _emit(
                event_callback,
                {
                    "type": "subagent.started",
                    "phase": subagent_phase,
                    "agent": subagent_type or "runtime",
                    "title": f"{subagent_type or '子代理'} 已启动",
                    "message": "子代理开始执行分配任务。",
                    "payload": {
                        "agent_name": subagent_type,
                        "tool_call_id": tool_call_id,
                        "task_preview": task_preview,
                    },
                },
            )

        try:
            result = handler(request)
        except Exception as exc:
            if task_tool_mode and tool_name == "task":
                _emit(
                    event_callback,
                    {
                        "type": "agent.memo",
                        "phase": subagent_phase,
                        "agent": actor_name,
                        "title": "子代理调用失败",
                        "message": f"子代理 {subagent_type or '未知'} 调用异常。",
                        "payload": {"tool_call_id": tool_call_id, "error": str(exc)},
                    },
                )
            raise

        if task_tool_mode and tool_name == "task":
            preview = _tool_result_preview(result)
            if shared is not None and subagent_type:
                completed = shared.setdefault("subagents_completed", [])
                completed.append(subagent_type)
            _emit(
                event_callback,
                {
                    "type": "subagent.completed",
                    "phase": subagent_phase,
                    "agent": subagent_type or "runtime",
                    "title": f"{subagent_type or '子代理'} 已完成",
                    "message": "子代理已返回结果。",
                    "payload": {
                        "agent_name": subagent_type,
                        "tool_call_id": tool_call_id,
                        "result_preview": preview,
                    },
                },
            )

        _emit(
            event_callback,
            {
                "type": "tool.result",
                "phase": default_phase,
                "agent": actor_name,
                "title": f"工具返回：{tool_name}",
                "message": "已收到工具回执。",
                "payload": {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "result_preview": _tool_result_preview(result),
                },
            },
        )

        return result

    return _intercept


def _read_runtime_file(files: Dict[str, Any], path: str) -> str:
    if not isinstance(files, dict):
        return ""
    payload = files.get(path)
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    if isinstance(content, list):
        return "\n".join(str(line) for line in content)
    return str(content or "")


def _state_file_diagnostics(files: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    targets = (
        "/workspace/state/retrieval_plan.md",
        "/workspace/state/evidence_bundle.md",
        "/workspace/state/timeline_bundle.md",
        "/workspace/state/stance_bundle.md",
        "/workspace/state/propagation_bundle.md",
        "/workspace/base_context.json",
    )
    output: Dict[str, Dict[str, Any]] = {}
    for path in targets:
        payload = files.get(path) if isinstance(files, dict) else None
        content = _read_runtime_file(files, path)
        output[path] = {
            "exists": isinstance(payload, dict),
            "chars": len(content),
            "empty": not bool(content.strip()),
        }
    return output


def _extend_closure_diagnostic(
    diagnostic: Dict[str, Any],
    *,
    files: Optional[Dict[str, Dict[str, Any]]] = None,
    closure_stage: str = "",
    fallback_attempted: Optional[bool] = None,
    fallback_error: Optional[Exception] = None,
    fallback_error_message: str = "",
    validation_error: Optional[Exception] = None,
) -> Dict[str, Any]:
    output = dict(diagnostic or {})
    if closure_stage:
        output["closure_stage"] = closure_stage
    if files is not None:
        output["state_files"] = _state_file_diagnostics(files)
    if fallback_attempted is not None:
        output["fallback_attempted"] = bool(fallback_attempted)
    if fallback_error is not None:
        output["fallback_error_type"] = type(fallback_error).__name__
        output["fallback_error_message"] = str(fallback_error or "").strip()
    elif fallback_error_message:
        output["fallback_error_message"] = str(fallback_error_message).strip()
    if validation_error is not None:
        output["validation_error_message"] = str(validation_error or "").strip()
    return output


def _lifecycle_diagnostic(tracker: Dict[str, Any], result: Any) -> Dict[str, Any]:
    diagnostic = _result_diagnostic_summary(result)
    tool_calls = tracker.get("tool_calls") if isinstance(tracker.get("tool_calls"), list) else []
    subagents_started = tracker.get("subagents_started") if isinstance(tracker.get("subagents_started"), list) else []
    subagents_completed = tracker.get("subagents_completed") if isinstance(tracker.get("subagents_completed"), list) else []
    tool_round_counts = tracker.get("tool_round_counts") if isinstance(tracker.get("tool_round_counts"), dict) else {}
    tool_round_limits = tracker.get("tool_round_limits") if isinstance(tracker.get("tool_round_limits"), dict) else {}
    diagnostic.update(
        {
            "tool_calls": tool_calls,
            "tool_round_counts": tool_round_counts,
            "tool_round_limits": tool_round_limits,
            "required_tools_hit": {
                "task": "task" in tool_calls,
                "write_todos": "write_todos" in tool_calls,
                "save_structured_report": "save_structured_report" in tool_calls,
                "write_final_report": "write_final_report" in tool_calls,
                "overwrite_report_cache": "overwrite_report_cache" in tool_calls,
            },
            "subagents_started": subagents_started,
            "subagents_completed": subagents_completed,
        }
    )
    return diagnostic


def _synthesize_structured_report_from_files(
    *,
    files: Dict[str, Dict[str, Any]],
    topic_identifier: str,
    topic_label: str,
    start_text: str,
    end_text: str,
    mode: str,
    thread_id: str,
) -> Dict[str, Any]:
    prompt_parts = [
        "你是报告结构化汇总代理。请根据工作区中的中间产物生成完整 StructuredReport JSON。",
        "必须返回一个合法 JSON 对象，不要输出 Markdown，不要解释。",
        "缺失信息允许谨慎留空，但必须保证字段完整并通过结构校验。",
        f"topic_identifier={topic_identifier}",
        f"topic_label={topic_label}",
        f"start={start_text}",
        f"end={end_text}",
        f"mode={mode}",
        f"thread_id={thread_id}",
    ]
    for path in (
        "/workspace/state/retrieval_plan.md",
        "/workspace/state/evidence_bundle.md",
        "/workspace/state/timeline_bundle.md",
        "/workspace/state/stance_bundle.md",
        "/workspace/state/propagation_bundle.md",
        "/workspace/state/structured_report.json",
        "/workspace/base_context.json",
    ):
        text = _read_runtime_file(files, path).strip()
        if text:
            prompt_parts.append(f"\n## {path}\n{text[:12000]}")
    raw = _safe_async(
        call_langchain_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你负责生成结构化舆情报告 JSON。"
                        "输出必须是单个 JSON 对象，字段必须匹配 StructuredReport。"
                        "不需要节省 token，优先一次性补齐完整字段，减少反复试探。"
                    ),
                },
                {"role": "user", "content": "\n".join(prompt_parts)},
            ],
            task="report",
            model_role="report",
            temperature=0.1,
            max_tokens=6200,
        )
    )
    return _parse_json_object(raw)


def _invoke_agent(
    *,
    name: str,
    schema: Type[Any],
    prompt: str,
    system_prompt: str,
    task_context: Dict[str, Any],
    tools: List[Any],
    files: Dict[str, Dict[str, Any]],
    skill_sources: List[str],
    memory_paths: List[str],
    backend_factory: Callable[[Any], CompositeBackend],
    thread_id: str,
    event_callback: Optional[Callable[[Dict[str, Any]], None]],
    specialist_skills: Optional[List[str]] = None,
) -> Dict[str, Any]:
    ensure_langchain_uuid_compat()
    llm, _client_cfg = build_langchain_chat_model(task="report", model_role="report", temperature=0.15, max_tokens=3600)
    if llm is None:
        raise ValueError("未找到可用的 LangChain 模型配置")
    filtered_sources = list(skill_sources)
    if specialist_skills:
        filtered_sources = [path for path in filtered_sources if any(skill in path for skill in specialist_skills)]
    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        skills=filtered_sources or skill_sources or None,
        memory=memory_paths or None,
        response_format=AutoStrategy(schema),
        context_schema=dict,
        checkpointer=InMemorySaver(),
        store=RUNTIME_STORE,
        backend=backend_factory,
        debug=False,
        name=name,
    )
    _emit(
        event_callback,
        {
            "type": "subagent.started",
            "phase": task_context.get("phase") or "interpret",
            "agent": name,
            "title": f"{name} 已启动",
            "message": task_context.get("message") or "",
            "payload": {"agent_name": name, "thread_id": thread_id},
        },
    )
    result = agent.invoke(
        _seed_invoke_payload(files, prompt),
        config={"configurable": {"thread_id": thread_id}},
        context=task_context,
        version="v2",
    )
    payload = result if isinstance(result, dict) else getattr(result, "value", result)
    structured = payload.get("structured_response") if isinstance(payload, dict) else payload
    structured_dict = _structured_to_dict(structured)
    if not structured_dict:
        raise ValueError(f"{name} 未返回结构化结果")
    _emit(
        event_callback,
        {
            "type": "subagent.completed",
            "phase": task_context.get("phase") or "interpret",
            "agent": name,
            "title": f"{name} 已完成",
            "message": f"{name} 已产出结构化结果。",
            "payload": {"agent_name": name, "result_keys": list(structured_dict.keys())},
        },
    )
    return structured_dict


def _prepare_runtime(
    topic_identifier: str,
    start_text: str,
    end_text: str,
    *,
    topic_label: str,
    mode: str,
    thread_id: str,
    task_id: str,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Callable[[Any], CompositeBackend], List[str], List[str]]:
    base_context = build_base_context(
        topic_identifier,
        start_text,
        end_text,
        topic_label=topic_label,
        mode=mode,
    )
    workspace_files = build_workspace_files(base_context)
    backend_factory, runtime_files, skill_sources, memory_paths = _build_backend_factory(
        task_id=task_id,
        topic_identifier=topic_identifier,
        topic_label=topic_label,
        seed_files=workspace_files,
    )
    common_context = {
        "topic_identifier": topic_identifier,
        "topic_label": topic_label,
        "start": start_text,
        "end": end_text,
        "mode": mode,
        "thread_id": thread_id,
        "base_context_path": "/workspace/base_context.json",
    }
    return common_context, runtime_files, backend_factory, skill_sources, memory_paths


def _build_interrupt_config(summary: str, *, allow_edit: bool) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "allowed_decisions": ["approve", "reject"] if not allow_edit else ["approve", "edit", "reject"],
        "description": summary,
    }
    if allow_edit:
        config["args_schema"] = {
            "type": "object",
            "properties": {
                "markdown": {
                    "type": "string",
                    "description": "审核后允许写入的 Markdown 文稿内容。",
                }
            },
            "required": ["markdown"],
        }
    return config


def _build_subagents(
    tools: List[Any],
    *,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    tracker: Optional[Dict[str, Any]] = None,
    max_tool_rounds: Optional[int] = None,
) -> List[Dict[str, Any]]:
    def _middleware_for(name: str) -> List[Any]:
        return [
            _build_lifecycle_middleware(
                event_callback=event_callback,
                actor_name=name,
                default_phase=_phase_for_subagent(name),
                tracker=tracker,
                task_tool_mode=False,
                max_tool_rounds=max_tool_rounds,
            )
        ]

    return [
        {
            "name": "retrieval_router",
            "description": "负责选择检索路径、梳理优先问题，并把结果写入 /workspace/state/retrieval_plan.md。",
            "system_prompt": (
                "你是检索路由代理。请先阅读 /workspace/base_context.json 和 /workspace/summary.md，"
                "决定应优先走哪些检索路径、要查哪些问题。把结论写入 /workspace/state/retrieval_plan.md，"
                "并返回简短总结。默认策略是少调用、重研判：先把问题框架想完整，再进行必要调用，尽量在一次回复中完成更深的判断。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": tools,
            "middleware": _middleware_for("retrieval_router"),
            "skills": ["/skills/retrieval-router-rules/"],
        },
        {
            "name": "evidence_organizer",
            "description": "负责清洗检索结果、去重并整理证据块，写入 /workspace/state/evidence_bundle.md。",
            "system_prompt": (
                "你是证据整理代理。请读取 /workspace/base_context.json 和 /workspace/state/retrieval_plan.md，"
                "必要时调用检索工具，压缩出统一的证据块、来源摘要和引用索引。"
                "把整理结果写入 /workspace/state/evidence_bundle.md，并返回摘要。"
                "默认策略是少调用、重研判：不要把判断拆成很多次零散小调用，优先做高价值检索并一次性整理出完整证据束。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": tools,
            "middleware": _middleware_for("evidence_organizer"),
            "skills": ["/skills/evidence-source-credibility/"],
        },
        {
            "name": "timeline_analyst",
            "description": "负责构建事件时间线、触发机制和因果链，写入 /workspace/state/timeline_bundle.md。",
            "system_prompt": (
                "你是时间线与因果链代理。请根据已有证据梳理事件顺序、关键触发因素和影响，"
                "把结果写入 /workspace/state/timeline_bundle.md，并返回简短总结。"
                "默认策略是少调用、重研判：优先一次性整理完整时序和因果链，不要反复做碎片化补充。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": tools,
            "middleware": _middleware_for("timeline_analyst"),
            "skills": ["/skills/timeline-alignment-slicing/"],
        },
        {
            "name": "stance_conflict",
            "description": "负责识别主体、立场矩阵和冲突点，写入 /workspace/state/stance_bundle.md。",
            "system_prompt": (
                "你是立场冲突代理。请整理主体列表、立场归并和冲突结构，"
                "把结果写入 /workspace/state/stance_bundle.md，并返回简短总结。"
                "默认策略是少调用、重研判：优先一次性完成主体归并、立场判断和冲突抽象，不要拆成多轮浅层输出。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": tools,
            "middleware": _middleware_for("stance_conflict"),
            "skills": ["/skills/subject-stance-merging/"],
        },
        {
            "name": "propagation_analyst",
            "description": "负责解释传播规模、扩散节奏、平台差异和关键影响点，写入 /workspace/state/propagation_bundle.md。",
            "system_prompt": (
                "你是传播结构代理。请结合已有证据与分析结果，解释传播特征、平台差异和风险外溢，"
                "把结果写入 /workspace/state/propagation_bundle.md，并返回简短总结。"
                "默认策略是少调用、重研判：优先形成完整传播解释和风险判断，再决定是否追加少量必要调用。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": tools,
            "middleware": _middleware_for("propagation_analyst"),
            "skills": ["/skills/propagation-explanation-framework/", "/skills/chart-interpretation-guidelines/"],
        },
        {
            "name": "writer",
            "description": "负责根据结构化对象生成正式 Markdown 草稿，写入 /workspace/state/report_draft.md。",
            "system_prompt": (
                "你是写作代理。请在结构已经确定后，根据 /workspace/state/structured_report.json 生成正式 Markdown 草稿。"
                "不要暴露内部字段名，把草稿写入 /workspace/state/report_draft.md，并返回简短总结。"
                "不需要刻意压缩篇幅，优先单次成稿、论证完整、表达稳健。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": [],
            "middleware": _middleware_for("writer"),
            "skills": ["/skills/report-writing-framework/"],
        },
        {
            "name": "validator",
            "description": "负责检查事实一致性、时间错位和主体混淆，写入 /workspace/state/validation_notes.md。",
            "system_prompt": (
                "你是校验代理。请读取结构化对象和草稿，重点检查无证据判断、时间错位和跨主体混淆。"
                "把校验意见写入 /workspace/state/validation_notes.md，并返回简短总结。"
                "优先一次性完成深度校验，减少反复小修。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": [],
            "middleware": _middleware_for("validator"),
            "skills": ["/skills/quality-validation-backlink/"],
        },
    ]


def run_or_resume_deep_report_task(
    topic_identifier: str,
    start: str,
    end: Optional[str] = None,
    *,
    topic_label: Optional[str] = None,
    mode: str = "fast",
    thread_id: Optional[str] = None,
    task_id: str = "",
    resume_payload: Optional[Any] = None,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip() or start_text
    if not start_text:
        raise ValueError("Missing required field(s): start")
    ensure_langchain_uuid_compat()

    display_name = str(topic_label or topic_identifier).strip() or topic_identifier
    active_thread_id = str(thread_id or _default_thread_id(topic_identifier, start_text, end_text)).strip()
    runtime_task_id = str(task_id or f"rp-runtime-{uuid.uuid4().hex[:8]}").strip()
    cache_dir = ensure_cache_dir(topic_identifier, start_text, end_text)
    cache_path = cache_dir / REPORT_CACHE_FILENAME
    full_cache_path = cache_dir / AI_FULL_REPORT_CACHE_FILENAME
    runtime_artifact_path = build_artifacts_root(runtime_task_id, get_data_root()) / "report.md"
    common_context, runtime_files, backend_factory, skill_sources, memory_paths = _prepare_runtime(
        topic_identifier,
        start_text,
        end_text,
        topic_label=display_name,
        mode=mode,
        thread_id=active_thread_id,
        task_id=runtime_task_id,
    )
    core_tools = [query_documents, verify_claim, build_timeline, build_entity_graph, run_volume_analysis]
    llm, _client_cfg = build_langchain_chat_model(task="report", model_role="report", temperature=0.15, max_tokens=4200)
    if llm is None:
        raise ValueError("未找到可用的 LangChain 模型配置")

    def _persist_structured_report(payload: dict[str, Any], *, source: str) -> Dict[str, Any]:
        report_data = dict(payload or {})
        task_payload = report_data.get("task") if isinstance(report_data.get("task"), dict) else {}
        report_data["task"] = {
            **task_payload,
            "topic_identifier": topic_identifier,
            "topic_label": display_name,
            "start": start_text,
            "end": end_text,
            "mode": mode,
            "thread_id": active_thread_id,
        }
        validated = StructuredReport.model_validate(report_data)
        output = validated.model_dump()
        output["metadata"] = dict(output.get("metadata") or {})
        output["metadata"].update(
            {
                "cache_version": REPORT_CACHE_VERSION,
                "generated_at": _utc_now(),
                "thread_id": active_thread_id,
                "runtime_task_id": runtime_task_id,
            }
        )
        output = _hydrate_render_layers(
            output,
            topic_identifier=topic_identifier,
            topic_label=display_name,
            start_text=start_text,
            end_text=end_text,
        )
        output["meta"] = output["metadata"]
        _write_json(cache_path, output)
        _upsert_runtime_json_file(runtime_files, "/workspace/state/structured_report.json", output)
        _emit(
            event_callback,
            {
                "type": "artifact.updated",
                "phase": "write",
                "title": "结构化结果已保存",
                "message": f"结构化结果已写入当前任务缓存（来源：{source}）。",
                "payload": {"report_cache_path": str(cache_path), "runtime_task_id": runtime_task_id},
            },
        )
        return output

    def _load_current_structured_payload() -> Dict[str, Any]:
        payload = _load_json(cache_path)
        return payload if _matches_current_run(payload, runtime_task_id=runtime_task_id, thread_id=active_thread_id) else {}

    def _load_current_full_payload() -> Dict[str, Any]:
        payload = _load_json(full_cache_path)
        return payload if _matches_current_run(payload, runtime_task_id=runtime_task_id, thread_id=active_thread_id) else {}

    @tool
    def save_structured_report(payload: Optional[Dict[str, Any]] = None, payload_json: str = "") -> str:
        """验证并写入结构化报告对象。优先直接传 payload 对象；payload_json 仅兼容旧调用。"""
        raw_payload = payload if isinstance(payload, dict) else _parse_json_object(payload_json)
        if not raw_payload:
            raise ValueError("结构化结果不是有效 JSON 对象。优先直接传 payload 对象，不要把整个 JSON 再包成字符串。")
        seed_payload = _build_structured_seed_payload(
            topic_identifier=topic_identifier,
            topic_label=display_name,
            start_text=start_text,
            end_text=end_text,
            mode=mode,
            thread_id=active_thread_id,
        )
        existing_payload = _load_current_structured_payload()
        normalized_payload = _finalize_structured_payload(
            _merge_structured_payload(
                _merge_structured_payload(seed_payload, existing_payload),
                raw_payload,
            )
        )
        try:
            _persist_structured_report(normalized_payload, source="tool")
        except Exception as exc:
            try:
                synthesized_payload = _synthesize_structured_report_from_files(
                    files=runtime_files,
                    topic_identifier=topic_identifier,
                    topic_label=display_name,
                    start_text=start_text,
                    end_text=end_text,
                    mode=mode,
                    thread_id=active_thread_id,
                )
                repaired_payload = _finalize_structured_payload(
                    _merge_structured_payload(
                        _merge_structured_payload(seed_payload, synthesized_payload),
                        raw_payload,
                    )
                )
                _persist_structured_report(repaired_payload, source="tool_autofix")
                _emit(
                    event_callback,
                    {
                        "type": "agent.memo",
                        "phase": "interpret",
                        "agent": "report_coordinator",
                        "title": "结构化结果已自动补齐",
                        "message": "这次提交不够完整，系统已结合中间结果补齐后保存。",
                        "payload": {"agent_name": "report_coordinator"},
                    },
                )
            except Exception:
                raise ValueError(f"结构化结果校验失败：{_summarize_validation_error(exc)}") from exc
        return "structured-report-saved"

    @tool
    def write_final_report(markdown: str) -> str:
        """写入本次任务的正式文稿草稿。"""
        runtime_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_artifact_path.write_text(str(markdown or "").strip(), encoding="utf-8")
        _emit(
            event_callback,
            {
                "type": "artifact.updated",
                "phase": "persist",
                "title": "正式文稿已写入",
                "message": "正式文稿草稿已写入本次任务产物目录。",
                "payload": {"report_runtime_artifact": str(runtime_artifact_path)},
            },
        )
        return str(runtime_artifact_path)

    @tool
    def overwrite_report_cache(markdown: str) -> str:
        """覆盖正式报告缓存，生成完整文稿缓存。"""
        structured_payload = _load_current_structured_payload()
        if not structured_payload:
            raise ValueError("尚未生成结构化结果，无法覆盖报告缓存。")
        final_payload = build_full_payload(
            structured_payload,
            str(markdown or "").strip(),
            cache_version=AI_FULL_REPORT_CACHE_VERSION,
        )
        final_payload["meta"] = dict(final_payload.get("meta") or {})
        final_payload["meta"].update(
            {
                "thread_id": active_thread_id,
                "runtime_task_id": runtime_task_id,
            }
        )
        _write_json(full_cache_path, final_payload)
        _emit(
            event_callback,
            {
                "type": "artifact.ready",
                "phase": "persist",
                "title": "正式缓存已更新",
                "message": "结构化结果和正式文稿缓存均已写入。",
                "payload": {
                    "report_ready": True,
                    "report_cache_path": str(cache_path),
                    "full_report_ready": True,
                    "full_report_cache_path": str(full_cache_path),
                    "report_runtime_artifact": str(runtime_artifact_path),
                },
            },
        )
        return str(full_cache_path)

    agent_tools = [*core_tools, save_structured_report, write_final_report, overwrite_report_cache]
    lifecycle_tracker: Dict[str, Any] = {
        "tool_calls": [],
        "subagents_started": [],
        "subagents_completed": [],
        "tool_round_counts": {},
        "tool_round_limits": {},
    }
    tool_round_limits = _resolve_report_tool_round_limits()
    coordinator_tool_round_limit = tool_round_limits["coordinator"]
    subagent_tool_round_limit = tool_round_limits["subagent"]
    coordinator_limit_text = (
        f"本次总控允许的最大工具回合为 {int(coordinator_tool_round_limit)}，请把调用压缩在这个范围内。"
        if coordinator_tool_round_limit is not None
        else "本次总控默认不限制工具回合，但仍应尽量减少无效调用。"
    )
    subagent_limit_text = (
        f"各子代理默认工具回合上限为 {int(subagent_tool_round_limit)}。"
        if subagent_tool_round_limit is not None
        else "各子代理默认不限制工具回合，但仍应优先少调用、深研判。"
    )
    agent = create_deep_agent(
        model=llm,
        tools=agent_tools,
        system_prompt=(
            "你是舆情报告总控代理。你的职责是规划任务、调用合适的子代理、整理结构化结果，并在审批通过后写入正式文稿。"
            "你不能跳过证据回链，也不能在没有结构化对象的情况下直接写正式文稿。"
            "你必须优先使用 task 工具委派给专业子代理，而不是自己直接完成所有分析。"
            "默认策略是少调用、重研判：不必节省 token，但要控制调用次数，优先在单次回复里完成更深、更完整的归纳和判断。"
            "完成必要取证后，尽量减少碎片化 read_file / 重复小调用，优先一次性收口成完整结构化对象。"
            "调用 save_structured_report 前，先在单次回复里把对象整理完整；不要连续提交多个试探版本。"
            f"{coordinator_limit_text}"
            f"{subagent_limit_text}"
            "除非因为 human-in-the-loop 中断等待审批，否则在 save_structured_report 和 overwrite_report_cache 成功前，你不能结束本次运行。"
        ),
        middleware=[
            _build_lifecycle_middleware(
                event_callback=event_callback,
                actor_name="report_coordinator",
                default_phase="interpret",
                tracker=lifecycle_tracker,
                task_tool_mode=True,
                max_tool_rounds=coordinator_tool_round_limit,
            )
        ],
        subagents=_build_subagents(
            core_tools,
            event_callback=event_callback,
            tracker=lifecycle_tracker,
            max_tool_rounds=subagent_tool_round_limit,
        ),
        skills=skill_sources or None,
        memory=memory_paths or None,
        context_schema=dict,
        checkpointer=DEEP_AGENT_CHECKPOINTER,
        store=RUNTIME_STORE,
        backend=backend_factory,
        interrupt_on={
            "write_final_report": _build_interrupt_config("写入正式文稿前需要人工确认。", allow_edit=True),
            "overwrite_report_cache": _build_interrupt_config("覆盖正式报告缓存前需要人工确认。", allow_edit=False),
        },
        debug=False,
        name="deep-report-coordinator",
    )

    prompt = (
        "请先使用 write_todos 建立总计划，再严格按以下流程执行，不要跳步，也不要在未调用工具的情况下直接结束：\n"
        "1. 使用 task 工具委派 retrieval_router，再继续委派 evidence_organizer、timeline_analyst、stance_conflict、propagation_analyst。\n"
        "2. 读取这些子代理写入 /workspace/state/ 下的结果，汇总成完整结构化报告对象。\n"
        "3. 调用 save_structured_report 保存结构化对象。优先直接传 payload 对象，不要把整个结构化 JSON 再包成字符串。先整理好完整对象，再一次性提交，不要连续试探多个版本。对象必须包含：task、conclusion、timeline、subjects、stance_matrix、"
        "key_evidence、conflict_points、propagation_features、risk_judgement、unverified_points、suggested_actions、citations、validation_notes。\n"
        "4. 使用 writer 子代理基于 /workspace/state/structured_report.json 生成正式 Markdown 草稿，并写入 /workspace/state/report_draft.md。\n"
        "5. 使用 validator 子代理检查草稿与结构化对象，并在必要时改写 /workspace/state/report_draft.md。\n"
        "6. 读取最终草稿，调用 write_final_report，再调用 overwrite_report_cache。\n"
        "默认风格：单次回复尽量研判深刻，不必节省 token，但要尽量减少调用次数。"
        f"本次总控最大工具回合：{int(coordinator_tool_round_limit) if coordinator_tool_round_limit is not None else '不限制'}；"
        f"子代理最大工具回合：{int(subagent_tool_round_limit) if subagent_tool_round_limit is not None else '不限制'}。"
        "完成必要读取后，优先一次性输出更完整的分析和结构，不要拆成很多次浅层补充。"
        "所有关键判断都要尽量带 citation_ids；如果证据不足，请进入 unverified_points。"
    )
    _emit(
        event_callback,
        {
            "type": "agent.started",
            "phase": "interpret",
            "agent": "report_coordinator",
            "title": "总控代理已启动",
            "message": "总控代理开始调度子代理并协调结构化产出。",
            "payload": {"agent_name": "report_coordinator", "thread_id": active_thread_id},
        },
    )
    _emit(
        event_callback,
        {
            "type": "phase.progress",
            "phase": "interpret",
            "title": "深度代理开始执行",
            "message": "总控代理正在调度子代理并整合中间结果。",
            "payload": {"thread_id": active_thread_id},
        },
    )
    def _invoke_once(agent_input: Any) -> Any:
        return agent.invoke(
            agent_input,
            config={"configurable": {"thread_id": active_thread_id}},
            context=common_context,
            version="v2",
        )

    def _build_interrupt_response(result: Dict[str, Any]) -> Dict[str, Any]:
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        approvals: List[Dict[str, Any]] = []
        for interrupt in interrupts or []:
            interrupt_id = str(getattr(interrupt, "id", "") or "").strip() or uuid.uuid4().hex
            request = getattr(interrupt, "value", {}) or {}
            action_requests = request.get("action_requests") if isinstance(request, dict) else []
            review_configs = request.get("review_configs") if isinstance(request, dict) else []
            for index, action_request in enumerate(action_requests if isinstance(action_requests, list) else []):
                if not isinstance(action_request, dict):
                    continue
                review_config = review_configs[index] if index < len(review_configs) and isinstance(review_configs[index], dict) else {}
                tool_name = str(action_request.get("name") or "").strip()
                approvals.append(
                    {
                        "approval_id": f"{interrupt_id}:{index}",
                        "interrupt_id": interrupt_id,
                        "decision_index": index,
                        "tool_name": tool_name,
                        "title": "写入正式文稿" if tool_name == "write_final_report" else "覆盖报告缓存",
                        "summary": str(action_request.get("description") or f"工具 {tool_name} 等待人工确认。").strip(),
                        "status": "pending",
                        "allowed_decisions": review_config.get("allowed_decisions") if isinstance(review_config.get("allowed_decisions"), list) else ["approve", "reject"],
                        "action": {
                            **({"markdown_preview": str(((action_request.get("args") or {}).get("markdown") or "")).strip()[:1600]} if tool_name == "write_final_report" else {}),
                            **({"artifact_path": str(runtime_artifact_path)} if tool_name == "write_final_report" else {}),
                            **({"report_cache_path": str(cache_path), "full_report_cache_path": str(full_cache_path)} if tool_name == "overwrite_report_cache" else {}),
                            "tool_args": action_request.get("args") if isinstance(action_request.get("args"), dict) else {},
                        },
                        "requested_at": _utc_now(),
                    }
                )
        return {
            "status": "interrupted",
            "message": "文稿写入前需要人工确认。",
            "approvals": approvals,
            "structured_payload": _load_current_structured_payload(),
            "full_payload": _load_current_full_payload(),
            "thread_id": active_thread_id,
        }

    pending_input: Any = Command(resume=resume_payload) if resume_payload is not None else _seed_invoke_payload(runtime_files, prompt)
    last_diagnostic: Dict[str, Any] = {}
    latest_runtime_files: Dict[str, Dict[str, Any]] = runtime_files
    fallback_attempted = False
    for attempt in range(3):
        try:
            result = _invoke_once(pending_input)
        except Exception as exc:
            last_diagnostic = _extend_closure_diagnostic(
                _lifecycle_diagnostic(lifecycle_tracker, {}),
                files=latest_runtime_files,
                closure_stage="tool_round_limit_reached" if "最大工具回合限制" in str(exc or "") else "",
                fallback_attempted=fallback_attempted,
            )
            raise ReportRuntimeFailure(str(exc or "深度代理执行失败。").strip() or "深度代理执行失败。", last_diagnostic) from exc
        result_payload = result if isinstance(result, dict) else getattr(result, "value", result)
        runtime_result_files = result_payload.get("files") if isinstance(result_payload, dict) and isinstance(result_payload.get("files"), dict) else {}
        if runtime_result_files:
            latest_runtime_files = runtime_result_files
        last_diagnostic = _extend_closure_diagnostic(
            _lifecycle_diagnostic(lifecycle_tracker, result),
            files=latest_runtime_files,
            fallback_attempted=fallback_attempted,
        )
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        if interrupts:
            return _build_interrupt_response(result)

        structured_payload = _load_current_structured_payload()
        full_payload = _load_current_full_payload()
        if not structured_payload:
            structured_candidate = _extract_structured_response(result)
            if structured_candidate:
                try:
                    structured_payload = _persist_structured_report(structured_candidate, source="structured_response")
                except Exception as exc:
                    last_diagnostic = _extend_closure_diagnostic(
                        last_diagnostic,
                        files=latest_runtime_files,
                        fallback_attempted=fallback_attempted,
                        validation_error=exc,
                    )
        if structured_payload:
            _upsert_runtime_json_file(latest_runtime_files, "/workspace/state/structured_report.json", structured_payload)
        full_payload = _load_current_full_payload()
        if structured_payload and not full_payload:
            try:
                markdown = render_markdown(structured_payload)
                full_payload = build_full_payload(
                    structured_payload,
                    markdown,
                    cache_version=AI_FULL_REPORT_CACHE_VERSION,
                )
                full_payload["meta"] = dict(full_payload.get("meta") or {})
                full_payload["meta"].update(
                    {
                        "thread_id": active_thread_id,
                        "runtime_task_id": runtime_task_id,
                    }
                )
                _write_json(full_cache_path, full_payload)
                _emit(
                    event_callback,
                    {
                        "type": "artifact.updated",
                        "phase": "persist",
                        "title": "统一报告缓存已更新",
                        "message": "结构化结果和统一阅读视图缓存均已写入。",
                        "payload": {
                            "report_ready": True,
                            "report_cache_path": str(cache_path),
                            "full_report_ready": True,
                            "full_report_cache_path": str(full_cache_path),
                        },
                    },
                )
            except Exception as exc:
                last_diagnostic = _extend_closure_diagnostic(
                    last_diagnostic,
                    files=latest_runtime_files,
                    fallback_attempted=fallback_attempted,
                    fallback_error=exc,
                    closure_stage="full_payload_build_failed",
                )
        if not structured_payload:
            last_diagnostic = _extend_closure_diagnostic(
                last_diagnostic,
                files=latest_runtime_files,
                closure_stage="agent_save_missing",
                fallback_attempted=fallback_attempted,
            )
            if attempt == 0:
                _emit(
                    event_callback,
                    {
                        "type": "phase.progress",
                        "phase": "write",
                        "title": "自动补写结构化结果",
                        "message": "总控尚未保存结构化结果，系统正在根据已完成的调研产物补写。",
                        "payload": {
                            "thread_id": active_thread_id,
                            "attempt": attempt + 1,
                            "diagnostic": last_diagnostic,
                        },
                    },
                )
                _emit(
                    event_callback,
                    {
                        "type": "agent.memo",
                        "phase": "write",
                        "agent": "report_coordinator",
                        "title": "总控未保存结构化结果",
                        "message": "总控未调用结构化保存，系统已转入自动补写。",
                        "payload": last_diagnostic,
                    },
                )
                fallback_attempted = True
                try:
                    synthesized = _synthesize_structured_report_from_files(
                        files=latest_runtime_files,
                        topic_identifier=topic_identifier,
                        topic_label=display_name,
                        start_text=start_text,
                        end_text=end_text,
                        mode=mode,
                        thread_id=active_thread_id,
                    )
                except Exception as exc:
                    last_diagnostic = _extend_closure_diagnostic(
                        last_diagnostic,
                        files=latest_runtime_files,
                        closure_stage="fallback_synthesis_failed",
                        fallback_attempted=True,
                        fallback_error=exc,
                    )
                    break
                if not synthesized:
                    last_diagnostic = _extend_closure_diagnostic(
                        last_diagnostic,
                        files=latest_runtime_files,
                        closure_stage="fallback_synthesis_failed",
                        fallback_attempted=True,
                        fallback_error_message="自动补写没有生成可保存的结构化对象。",
                    )
                    break
                try:
                    structured_payload = _persist_structured_report(synthesized, source="fallback_synthesis")
                except Exception as exc:
                    last_diagnostic = _extend_closure_diagnostic(
                        last_diagnostic,
                        files=latest_runtime_files,
                        closure_stage="structured_validation_failed",
                        fallback_attempted=True,
                        validation_error=exc,
                    )
                    break
                last_diagnostic = _extend_closure_diagnostic(
                    last_diagnostic,
                    files=latest_runtime_files,
                    closure_stage="agent_save_missing",
                    fallback_attempted=True,
                )
                _emit(
                    event_callback,
                    {
                        "type": "agent.memo",
                        "phase": "write",
                        "agent": "report_coordinator",
                        "title": "触发结构化补写",
                        "message": "总控未调用保存工具，已根据工作区产物完成结构化补写。",
                        "payload": last_diagnostic,
                    },
                )
            else:
                break

        full_payload = _load_current_full_payload()
        if structured_payload and full_payload:
            return {
                "status": "completed",
                "message": "深度代理执行完成。",
                "approvals": [],
                "structured_payload": structured_payload,
                "full_payload": full_payload,
                "thread_id": active_thread_id,
            }

        if attempt >= 2:
            break

        if not structured_payload:
            break

        _emit(
            event_callback,
            {
                "type": "phase.progress",
                "phase": "persist",
                "title": "补写正式文稿",
                "message": "结构化结果已存在，但正式文稿尚未完成写入，正在要求代理继续执行写入流程。",
                "payload": {
                    "thread_id": active_thread_id,
                    "attempt": attempt + 2,
                    "diagnostic": last_diagnostic,
                },
            },
        )
        pending_input = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "结构化结果已经保存为当前任务产物。"
                        "现在你必须读取 /workspace/state/structured_report.json；如有必要先生成或修订 /workspace/state/report_draft.md，"
                        "随后调用 write_final_report，再调用 overwrite_report_cache。"
                        "如果需要人工确认，请正常触发 human-in-the-loop；不要只输出文字。"
                    ),
                }
            ],
            "files": latest_runtime_files,
        }

    structured_payload = _load_current_structured_payload()
    full_payload = _load_current_full_payload()
    if structured_payload and full_payload:
        return {
            "status": "completed",
            "message": "深度代理执行完成。",
            "approvals": [],
            "structured_payload": structured_payload,
            "full_payload": full_payload,
            "thread_id": active_thread_id,
        }

    _emit(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "write" if not structured_payload else "persist",
            "agent": "report_coordinator",
            "title": "总控代理结束但产物不完整",
            "message": "总控代理本轮结束时没有留下完整产物，已记录诊断信息。",
            "payload": last_diagnostic,
        },
    )
    failure_message = "总控未保存结构化结果，服务端补写失败。"
    if structured_payload:
        failure_message = "结构化结果已生成，但正式文稿尚未完成写入。"
    elif str(last_diagnostic.get("closure_stage") or "").strip() == "structured_validation_failed":
        failure_message = "结构化结果已生成，但字段校验未通过。"
    return {
        "status": "failed",
        "message": failure_message,
        "approvals": [],
        "structured_payload": structured_payload,
        "full_payload": full_payload,
        "thread_id": active_thread_id,
        "diagnostic": last_diagnostic,
    }


def generate_report_payload(
    topic_identifier: str,
    start: str,
    end: Optional[str] = None,
    *,
    topic_label: Optional[str] = None,
    regenerate: bool = False,
    mode: str = "fast",
    thread_id: Optional[str] = None,
    task_id: str = "",
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip() or start_text
    if not start_text:
        raise ValueError("Missing required field(s): start")
    display_name = str(topic_label or topic_identifier).strip() or topic_identifier
    cache_dir = ensure_cache_dir(topic_identifier, start_text, end_text)
    cache_path = cache_dir / REPORT_CACHE_FILENAME
    if cache_path.exists() and not regenerate:
        cached = _load_json(cache_path)
        if int(((cached.get("meta") or {}).get("cache_version") or 0)) == REPORT_CACHE_VERSION:
            return cached
        if cached:
            upgraded = _finalize_structured_payload(cached)
            upgraded.setdefault("metadata", {})
            upgraded["metadata"].update(
                {
                    "cache_version": REPORT_CACHE_VERSION,
                    "generated_at": upgraded["metadata"].get("generated_at") or _utc_now(),
                    "thread_id": str(((upgraded.get("task") or {}).get("thread_id")) or thread_id or _default_thread_id(topic_identifier, start_text, end_text)).strip(),
                }
            )
            upgraded = _hydrate_render_layers(
                upgraded,
                topic_identifier=topic_identifier,
                topic_label=display_name,
                start_text=start_text,
                end_text=end_text,
            )
            upgraded["meta"] = upgraded["metadata"]
            _write_json(cache_path, upgraded)
            return upgraded

    active_thread_id = str(thread_id or _default_thread_id(topic_identifier, start_text, end_text)).strip()
    runtime_task_id = str(task_id or f"rp-runtime-{uuid.uuid4().hex[:8]}").strip()
    common_context, runtime_files, backend_factory, skill_sources, memory_paths = _prepare_runtime(
        topic_identifier,
        start_text,
        end_text,
        topic_label=display_name,
        mode=mode,
        thread_id=active_thread_id,
        task_id=runtime_task_id,
    )
    todos = _build_todos()
    _emit(event_callback, {"type": "todo.updated", "phase": "prepare", "title": "任务计划已创建", "message": "已建立本次报告的执行清单。", "payload": {"todos": todos}})

    tools = [query_documents, verify_claim, build_timeline, build_entity_graph, run_volume_analysis]

    todos = _set_todo_status(todos, "retrieval", "running")
    _emit(event_callback, {"type": "todo.updated", "phase": "interpret", "title": "开始检索路由", "message": "正在判断本次任务的优先检索路径。", "payload": {"todos": todos}})
    retrieval = _invoke_agent(
        name="retrieval_router",
        schema=RetrievalPlan,
        prompt="请阅读 /workspace/base_context.json 和 /workspace/summary.md，为本次舆情任务给出检索路由计划。",
        system_prompt="你是检索路由代理，负责决定应该优先走哪些检索路径和哪些问题值得先查。",
        task_context={**common_context, "phase": "interpret", "message": "正在制定检索路由。"},
        tools=tools,
        files=runtime_files,
        skill_sources=skill_sources,
        memory_paths=memory_paths,
        backend_factory=backend_factory,
        thread_id=f"{active_thread_id}:retrieval",
        event_callback=event_callback,
        specialist_skills=SPECIALIST_SKILLS["retrieval_router"],
    )
    runtime_files["/workspace/state/retrieval_plan.json"]["content"] = json.dumps(retrieval, ensure_ascii=False, indent=2).split("\n")

    todos = _set_todo_status(todos, "retrieval", "completed")
    todos = _set_todo_status(todos, "evidence", "running")
    _emit(event_callback, {"type": "todo.updated", "phase": "interpret", "title": "开始证据整理", "message": "正在压缩原始命中结果并统一证据格式。", "payload": {"todos": todos}})
    evidence_bundle = _invoke_agent(
        name="evidence_organizer",
        schema=EvidenceBundle,
        prompt="请根据 /workspace/base_context.json 与 /workspace/state/retrieval_plan.json 组织关键证据，你可以调用 query_documents 和 verify_claim。",
        system_prompt="你是证据整理代理，负责把原始检索结果压缩成统一的证据块与引用索引。",
        task_context={**common_context, "phase": "interpret", "message": "正在整理关键证据。"},
        tools=tools,
        files=runtime_files,
        skill_sources=skill_sources,
        memory_paths=memory_paths,
        backend_factory=backend_factory,
        thread_id=f"{active_thread_id}:evidence",
        event_callback=event_callback,
        specialist_skills=SPECIALIST_SKILLS["evidence_organizer"],
    )
    runtime_files["/workspace/state/evidence_bundle.json"]["content"] = json.dumps(evidence_bundle, ensure_ascii=False, indent=2).split("\n")

    todos = _set_todo_status(todos, "evidence", "completed")
    todos = _set_todo_status(todos, "structure", "running")
    _emit(event_callback, {"type": "todo.updated", "phase": "interpret", "title": "开始结构分析", "message": "正在构建时间线、主体立场与传播结构。", "payload": {"todos": todos}})
    timeline_bundle = _invoke_agent(
        name="timeline_analyst",
        schema=TimelineBundle,
        prompt="请使用 /workspace/base_context.json、/workspace/state/retrieval_plan.json 和 /workspace/state/evidence_bundle.json 生成事件时间线和因果链说明。",
        system_prompt="你是时间线与因果链代理，负责把证据串成事件序列与触发机制。",
        task_context={**common_context, "phase": "interpret", "message": "正在梳理时间线。"},
        tools=tools,
        files=runtime_files,
        skill_sources=skill_sources,
        memory_paths=memory_paths,
        backend_factory=backend_factory,
        thread_id=f"{active_thread_id}:timeline",
        event_callback=event_callback,
        specialist_skills=SPECIALIST_SKILLS["timeline_analyst"],
    )
    runtime_files["/workspace/state/timeline_bundle.json"]["content"] = json.dumps(timeline_bundle, ensure_ascii=False, indent=2).split("\n")

    stance_bundle = _invoke_agent(
        name="stance_conflict",
        schema=StanceBundle,
        prompt="请读取 /workspace/base_context.json、/workspace/state/evidence_bundle.json，输出主体列表、立场矩阵和冲突点。",
        system_prompt="你是立场冲突代理，负责识别主体、观点聚合与冲突结构。",
        task_context={**common_context, "phase": "interpret", "message": "正在整理主体与立场。"},
        tools=tools,
        files=runtime_files,
        skill_sources=skill_sources,
        memory_paths=memory_paths,
        backend_factory=backend_factory,
        thread_id=f"{active_thread_id}:stance",
        event_callback=event_callback,
        specialist_skills=SPECIALIST_SKILLS["stance_conflict"],
    )
    runtime_files["/workspace/state/stance_bundle.json"]["content"] = json.dumps(stance_bundle, ensure_ascii=False, indent=2).split("\n")

    propagation_bundle = _invoke_agent(
        name="propagation_analyst",
        schema=PropagationBundle,
        prompt="请阅读 /workspace/base_context.json、/workspace/state/evidence_bundle.json 和 /workspace/state/timeline_bundle.json，输出传播结构、平台差异、扩散节奏和风险判断。",
        system_prompt="你是传播结构代理，负责解释平台差异、扩散节奏和关键节点影响。",
        task_context={**common_context, "phase": "interpret", "message": "正在分析传播结构。"},
        tools=tools,
        files=runtime_files,
        skill_sources=skill_sources,
        memory_paths=memory_paths,
        backend_factory=backend_factory,
        thread_id=f"{active_thread_id}:propagation",
        event_callback=event_callback,
        specialist_skills=SPECIALIST_SKILLS["propagation_analyst"],
    )
    runtime_files["/workspace/state/propagation_bundle.json"]["content"] = json.dumps(propagation_bundle, ensure_ascii=False, indent=2).split("\n")

    structured = _invoke_agent(
        name="report_coordinator",
        schema=StructuredReport,
        prompt=(
            "请汇总 /workspace/base_context.json、/workspace/state/retrieval_plan.json、/workspace/state/evidence_bundle.json、"
            "/workspace/state/timeline_bundle.json、/workspace/state/stance_bundle.json、/workspace/state/propagation_bundle.json，"
            "产出完整的结构化报告对象。要求：所有关键判断尽量映射 citation_ids；未证实点单独列出。"
        ),
        system_prompt="你是总控代理，负责维护报告结构、汇总各子代理产物，并输出最终结构化报告。",
        task_context={**common_context, "phase": "write", "message": "正在汇总结构化报告。"},
        tools=tools,
        files=runtime_files,
        skill_sources=skill_sources,
        memory_paths=memory_paths,
        backend_factory=backend_factory,
        thread_id=f"{active_thread_id}:coordinator",
        event_callback=event_callback,
        specialist_skills=None,
    )
    structured.setdefault("metadata", {})
    structured["metadata"].update(
        {
            "cache_version": REPORT_CACHE_VERSION,
            "generated_at": _utc_now(),
            "thread_id": active_thread_id,
            "todos": todos,
            "retrieval_summary": retrieval.get("overview") if isinstance(retrieval, dict) else "",
            "evidence_summary": evidence_bundle.get("summary") if isinstance(evidence_bundle, dict) else "",
            "timeline_summary": timeline_bundle.get("summary") if isinstance(timeline_bundle, dict) else "",
            "stance_summary": stance_bundle.get("summary") if isinstance(stance_bundle, dict) else "",
            "propagation_summary": propagation_bundle.get("summary") if isinstance(propagation_bundle, dict) else "",
        }
    )

    # Build chart catalog first so the document composer knows what's available
    analyze_results_for_doc = build_analyze_results_payload(
        topic_identifier, start_text, end_text, topic_label=display_name,
    )
    functions_payload_for_doc = analyze_results_for_doc.get("functions") if isinstance(analyze_results_for_doc.get("functions"), list) else []
    chart_catalog_for_composer = build_chart_catalog(functions_payload_for_doc)

    # Build the ReportDataBundle so the composer can reference data IDs
    report_data_for_composer = ReportDataBundle.model_validate(
        {
            "task": structured.get("task") or {},
            "conclusion": structured.get("conclusion") or {},
            "timeline": structured.get("timeline") or [],
            "subjects": structured.get("subjects") or [],
            "stance_matrix": structured.get("stance_matrix") or [],
            "key_evidence": structured.get("key_evidence") or [],
            "conflict_points": structured.get("conflict_points") or [],
            "propagation_features": structured.get("propagation_features") or [],
            "risk_judgement": structured.get("risk_judgement") or [],
            "unverified_points": structured.get("unverified_points") or [],
            "suggested_actions": structured.get("suggested_actions") or [],
            "citations": structured.get("citations") or [],
            "validation_notes": structured.get("validation_notes") or [],
        }
    )

    todos = _set_todo_status(todos, "writing", "running")
    _emit(event_callback, {"type": "todo.updated", "phase": "write", "title": "开始文档编排", "message": "AI 正在根据图表目录与分析结果设计报告章节与图文编排。", "payload": {"todos": todos}})
    composer_output = _invoke_document_composer(
        report_data_for_composer,
        chart_catalog_for_composer,
        event_callback=event_callback,
    )

    structured = _hydrate_render_layers(
        structured,
        topic_identifier=topic_identifier,
        topic_label=display_name,
        start_text=start_text,
        end_text=end_text,
        composer_output=composer_output,
    )
    structured["meta"] = structured["metadata"]
    _write_json(cache_path, structured)
    return structured


def generate_full_report_payload(
    topic_identifier: str,
    start: str,
    end: Optional[str] = None,
    *,
    topic_label: Optional[str] = None,
    regenerate: bool = False,
    structured_payload: Optional[Dict[str, Any]] = None,
    mode: str = "fast",
    thread_id: Optional[str] = None,
    task_id: str = "",
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip() or start_text
    cache_dir = ensure_cache_dir(topic_identifier, start_text, end_text)
    cache_path = cache_dir / AI_FULL_REPORT_CACHE_FILENAME
    if cache_path.exists() and not regenerate:
        cached = _load_json(cache_path)
        if int(((cached.get("meta") or {}).get("cache_version") or 0)) == AI_FULL_REPORT_CACHE_VERSION:
            return cached
    structured = structured_payload if isinstance(structured_payload, dict) else generate_report_payload(
        topic_identifier,
        start_text,
        end_text,
        topic_label=topic_label,
        regenerate=regenerate,
        mode=mode,
        thread_id=thread_id,
        task_id=task_id,
        event_callback=event_callback,
    )
    # The full-report view shares the same report_document as the structured view.
    # render_markdown is kept only as a compat field; the canonical rendering path
    # is ReportDocumentRenderer consuming report_document + chart_catalog.
    markdown = render_markdown(structured)
    full_payload = build_full_payload(structured, markdown, cache_version=AI_FULL_REPORT_CACHE_VERSION)
    _write_json(cache_path, full_payload)
    return full_payload
