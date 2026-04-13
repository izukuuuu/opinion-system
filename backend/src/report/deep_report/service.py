from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from deepagents.backends.utils import create_file_data
from langchain.agents.middleware.types import wrap_tool_call
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain.tools import tool
from langgraph.types import Command
from pydantic import ValidationError

from ...utils.ai import build_langchain_chat_model, call_langchain_chat
from ...utils.setting.paths import get_data_root
from ...utils.setting.settings import settings
from ..agent_runtime import ensure_langchain_uuid_compat
from ..deepagents_backends import build_report_backend
from ..runtime_infra import (
    BACKEND_SQLITE,
    build_report_runnable_config,
    build_runtime_diagnostics,
    get_shared_report_checkpointer,
    resolve_runtime_profile,
)
from ..skills import select_report_skill_sources
from ..tools import select_report_tools
from .assets import RUNTIME_STORE, build_artifacts_root, build_runtime_assets, ensure_memory_seed
from .deterministic import build_analyze_results_payload, build_base_context, build_workspace_files, ensure_cache_dir
from .document import (
    assemble_report_document,
    build_data_summary_for_composer,
    build_figure_pipeline,
    build_report_document,
    load_report_blueprint,
)
from .presenter import build_full_payload, compile_markdown_artifacts
from .builder import build_report_deep_agent
from .orchestrator_graph import run_report_orchestrator_graph
from .report_ir import attach_report_ir, build_artifact_manifest, summarize_report_ir
from .runtime_contract import RUNTIME_CONTRACT_VERSION
from .payloads import (
    build_basic_analysis_insight_payload,
    build_bertopic_insight_payload,
    build_agenda_frame_map_payload,
    build_claim_actor_conflict_payload,
    build_mechanism_summary_payload,
    build_retrieval_plan_payload,
    build_discourse_conflict_map_payload,
    build_event_timeline_payload,
    get_basic_analysis_snapshot_payload,
    get_bertopic_snapshot_payload,
    build_section_packet_payload,
    compute_report_metrics_payload,
    detect_risk_signals_payload,
    extract_actor_positions_payload,
    get_corpus_coverage_payload,
    judge_decision_utility_payload,
    normalize_task_payload,
    persist_task_contract_bundle,
    retrieve_evidence_cards_payload,
    verify_claim_payload,
)
from .schemas import (
    AgendaFrameMapResult,
    ApprovalRecord,
    ExplorationBundle,
    ExplorationArtifactStatus,
    ExplorationTaskResult,
    GraphApprovalRecord,
    ActorPositionResult,
    BasicAnalysisInsightResult,
    BasicAnalysisSnapshotResult,
    BertopicInsightResult,
    BertopicSnapshotResult,
    ClaimActorConflictResult,
    ClaimVerificationPage,
    CorpusCoverageResult,
    DocumentComposerOutput,
    EvidenceCardPage,
    MechanismSummaryResult,
    MetricBundleResult,
    NormalizedTaskResult,
    SectionPacketResult,
    RiskSignalResult,
    ReportDataBundle,
    SemanticInterruptPayload,
    StructuredReport,
    StructuredReportSeed,
    TimelineBuildResult,
    UtilityAssessmentResult,
)


REPORT_CACHE_FILENAME = "report_payload.json"
REPORT_CACHE_VERSION = 3
AI_FULL_REPORT_CACHE_FILENAME = "ai_full_report_payload.json"
AI_FULL_REPORT_CACHE_VERSION = 11
RUN_STATE_VERSION = "run-state.v1"
RESUME_PAYLOAD_VERSION = "resume-payload.v1"
SEMANTIC_REVIEW_FILENAME = "full_report_semantic_review.json"
_NAMESPACE_COMPONENT = re.compile(r"[^A-Za-z0-9._@:+~-]+")

EXPLORATION_ARTIFACT_OWNERS = {
    "/workspace/state/normalized_task.json": "retrieval_router",
    "/workspace/state/corpus_coverage.json": "retrieval_router",
    "/workspace/state/evidence_cards.json": "archive_evidence_organizer",
    "/workspace/state/timeline_nodes.json": "timeline_analyst",
    "/workspace/state/actor_positions.json": "stance_conflict",
    "/workspace/state/conflict_map.json": "claim_actor_conflict",
    "/workspace/state/mechanism_summary.json": "propagation_analyst",
    "/workspace/state/risk_signals.json": "propagation_analyst",
    "/workspace/state/bertopic_insight.json": "bertopic_evolution_analyst",
    "/workspace/state/utility_assessment.json": "decision_utility_judge",
    "/workspace/state/section_packets/overview.json": "report_coordinator",
    "/workspace/state/section_packets/timeline.json": "report_coordinator",
    "/workspace/state/section_packets/risk.json": "report_coordinator",
}

FAST_EXPLORATION_ARTIFACTS = [
    "/workspace/state/normalized_task.json",
    "/workspace/state/corpus_coverage.json",
    "/workspace/state/evidence_cards.json",
    "/workspace/state/timeline_nodes.json",
    "/workspace/state/actor_positions.json",
    "/workspace/state/conflict_map.json",
    "/workspace/state/mechanism_summary.json",
    "/workspace/state/risk_signals.json",
    "/workspace/state/utility_assessment.json",
    "/workspace/state/section_packets/overview.json",
    "/workspace/state/section_packets/timeline.json",
    "/workspace/state/section_packets/risk.json",
]

RESEARCH_EXPLORATION_ARTIFACTS = [*FAST_EXPLORATION_ARTIFACTS, "/workspace/state/bertopic_insight.json"]


class ReportRuntimeFailure(RuntimeError):
    def __init__(self, message: str, diagnostic: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.task_diagnostic = diagnostic if isinstance(diagnostic, dict) else {}


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def _semantic_review_path(cache_dir: Path) -> Path:
    return cache_dir / SEMANTIC_REVIEW_FILENAME


def _build_semantic_review_payload(
    *,
    thread_id: str,
    task_id: str,
    compiled: Dict[str, Any],
    artifact_manifest: Dict[str, Any],
) -> SemanticInterruptPayload:
    conformance = compiled.get("factual_conformance") if isinstance(compiled.get("factual_conformance"), dict) else {}
    issue_items = conformance.get("issues") if isinstance(conformance.get("issues"), list) else []
    semantic_deltas = conformance.get("semantic_deltas") if isinstance(conformance.get("semantic_deltas"), list) else []
    styled_bundle = compiled.get("styled_draft_bundle") if isinstance(compiled.get("styled_draft_bundle"), dict) else {}
    rewrite_ops = [str(item).strip() for item in (styled_bundle.get("rewrite_ops") or []) if str(item or "").strip()]
    summary = [
        {
            "issue_type": str(item.get("issue_type") or "").strip(),
            "message": str(item.get("message") or "").strip(),
            "section_role": str(item.get("section_role") or "").strip(),
            "semantic_dimension": str(item.get("semantic_dimension") or "").strip(),
            "before_level": str(item.get("before_level") or "").strip(),
            "after_level": str(item.get("after_level") or "").strip(),
        }
        for item in issue_items
        if isinstance(item, dict)
    ][:8]
    offending_unit_ids = list(
        dict.fromkeys(
            str(item.get("issue_id") or "").split(":", 1)[0].strip()
            for item in issue_items
            if isinstance(item, dict) and str(item.get("issue_id") or "").strip()
        )
    )
    artifact_ids = [
        key
        for key in (
            "structured_projection",
            "basic_analysis_insight",
            "bertopic_insight",
            "ir",
            "conflict_map",
            "mechanism_summary",
            "utility_assessment",
            "draft_bundle",
            "approval_records",
            "full_markdown",
        )
        if isinstance(artifact_manifest.get(key), dict)
    ]
    suggested_actions = [
        "回退到 DraftBundle 降低表述强度。",
        "保留 trace 绑定，不要新增主体、风险或建议。",
        "如需继续写入，请在审批中确认或编辑正式文稿。",
    ]
    return SemanticInterruptPayload(
        thread_id=str(thread_id or "").strip(),
        task_id=str(task_id or "").strip(),
        policy_version=str(conformance.get("policy_version") or "policy.v2").strip() or "policy.v2",
        artifact_ids=artifact_ids,
        offending_unit_ids=offending_unit_ids,
        semantic_deltas=semantic_deltas,
        allowed_rewrite_ops=rewrite_ops,
        violation_summary=summary,
        suggested_actions=suggested_actions,
        conformance=conformance if isinstance(conformance, dict) else {},
    )


def _append_approval_record(
    existing_records: List[Dict[str, Any]] | None,
    *,
    approval_id: str,
    interrupt_id: str,
    decision: str,
    policy_version: str,
    artifact_refs: List[str],
    offending_unit_ids: List[str],
    approved_deltas: List[Dict[str, Any]],
    approved_rewrite_ops: List[str],
    reason: str = "",
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = [dict(item) for item in (existing_records or []) if isinstance(item, dict)]
    record = ApprovalRecord(
        approval_id=str(approval_id or "").strip(),
        interrupt_id=str(interrupt_id or "").strip(),
        decision=str(decision or "").strip(),
        reviewer="human_review",
        reason=str(reason or "").strip(),
        policy_version=str(policy_version or "policy.v2").strip() or "policy.v2",
        artifact_refs=[str(item).strip() for item in artifact_refs if str(item or "").strip()],
        offending_unit_ids=[str(item).strip() for item in offending_unit_ids if str(item or "").strip()],
        approved_deltas=[
            item if isinstance(item, dict) else {}
            for item in approved_deltas
            if isinstance(item, dict)
        ],
        approved_rewrite_ops=[str(item).strip() for item in approved_rewrite_ops if str(item or "").strip()],
    ).model_dump()
    records.append(record)
    return records


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


def _runtime_locator_hint(*, purpose: str, task_id: str = "", sqlite_path: str = "") -> str:
    probe = resolve_runtime_profile(purpose=purpose)
    if probe.checkpointer_backend == BACKEND_SQLITE:
        return str(sqlite_path or "").strip()
    return str(task_id or purpose).strip() or purpose


def _build_runtime_backends(
    *,
    task_id: str,
    topic_identifier: str,
    topic_label: str,
    seed_files: Dict[str, Dict[str, Any]],
 ) -> Tuple[Any, Dict[str, Dict[str, Any]], Dict[str, Any], List[str]]:
    runtime_files, skill_assets, memory_paths = build_runtime_assets(topic_label)
    merged_files: Dict[str, Dict[str, Any]] = {}
    merged_files.update(runtime_files)
    merged_files.update(seed_files)
    artifacts_root = build_artifacts_root(task_id, get_data_root())
    ensure_memory_seed(_namespace_factory(topic_identifier, task_id, "memories")(None), topic_label)

    runtime_backend = build_report_backend(
        artifacts_root=artifacts_root,
        memory_namespace=_namespace_factory(topic_identifier, task_id, "memories"),
    )
    return runtime_backend, merged_files, skill_assets, memory_paths


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
    *,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Optional["DocumentComposerOutput"]:
    """Call the AI document composer to produce a text-first document layout.

    Figure planning is handled by the deterministic figure pipeline. The composer
    only decides text and structured non-figure blocks.
    """
    llm, _ = build_langchain_chat_model(task="report", model_role="report", temperature=0.15, max_tokens=4800)
    if llm is None:
        return None

    data_summary = build_data_summary_for_composer(bundle)

    system_prompt = (
        "你是一名舆情报告文档编排代理。"
        "你的任务是根据给定的结构化分析结果，设计并输出一份完整的报告文档结构（DocumentComposerOutput）。\n\n"
        "【核心规则】\n"
        "1. 不要输出任何 figure/chart 相关 block；图表位点由后续 typed workflow 注入。\n"
        "2. 每个 narrative block 的 content 必须是基于数据写出的有判断性的文字（不少于 80 字），不要复制字段名，不要写空洞句子。\n"
        "3. 章节数量建议 3-4 个，覆盖：核心维度、生命周期、主体与立场、传播/风险/建议。\n"
        "4. evidence_list、timeline_list、subject_cards、stance_matrix、risk_list、action_list 只能引用数据摘要中提供的 ID。\n"
        "5. 附录（appendix）包含 citation_refs 和一个 callout；也可以不设附录（留 null），系统会自动生成默认附录。\n"
        "6. 如果某类数据为空（如 evidence_ids 为空列表），不要在章节中强行添加对应的 block。\n"
    )

    user_content = f"结构化数据摘要：\n{json.dumps(data_summary, ensure_ascii=False, indent=2)}"

    _emit(
        event_callback,
        {
            "type": "subagent.started",
            "phase": "write",
            "agent": "document_composer",
            "title": "文档编排代理已启动",
            "message": "正在根据结构化数据设计报告章节与正文编排。",
            "payload": {"agent_name": "document_composer"},
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


def _result_payload(result: Any) -> Any:
    return result if isinstance(result, dict) else getattr(result, "value", result)


def _result_interrupts(result: Any) -> List[Any]:
    interrupts = getattr(result, "interrupts", None)
    if isinstance(interrupts, (list, tuple)):
        return list(interrupts)
    payload = _result_payload(result)
    legacy_interrupts = payload.get("__interrupt__") if isinstance(payload, dict) else None
    if isinstance(legacy_interrupts, (list, tuple)):
        return list(legacy_interrupts)
    return []


def _extract_structured_response(result: Any) -> Dict[str, Any]:
    payload = _result_payload(result)
    if not isinstance(payload, dict):
        return {}
    structured = payload.get("structured_response")
    return _structured_to_dict(structured)


def _result_diagnostic_summary(result: Any) -> Dict[str, Any]:
    payload = _result_payload(result)
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
        "interrupt_count": len(_result_interrupts(result)),
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


def _required_exploration_artifacts(mode: str) -> List[str]:
    return list(RESEARCH_EXPLORATION_ARTIFACTS if str(mode or "").strip().lower() == "research" else FAST_EXPLORATION_ARTIFACTS)


def _normalize_exploration_event(event: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    event_type = str(event.get("type") or "").strip()
    phase = str(event.get("phase") or "").strip()
    normalized_type = {
        "todo.updated": "exploration.todo.updated",
        "subagent.started": "exploration.subagent.started",
        "subagent.completed": "exploration.subagent.completed",
        "graph.node.failed": "exploration.validation.failed" if phase == "exploration" else "",
        "artifact.updated": "exploration.artifact.ready" if phase in {"exploration", "structure", "write"} else "",
    }.get(event_type, "")
    if not normalized_type:
        return None
    return {
        **event,
        "type": normalized_type,
        "phase": "exploration" if event_type != "artifact.updated" else "structure",
    }


def _emit_runtime_event(
    event_callback: Optional[Callable[[Dict[str, Any]], None]],
    event: Dict[str, Any],
    *,
    normalize_exploration: bool = False,
) -> None:
    _emit(event_callback, event)
    if normalize_exploration:
        normalized = _normalize_exploration_event(event)
        if normalized:
            _emit(event_callback, normalized)


def _runtime_file_exists(files: Dict[str, Dict[str, Any]], path: str) -> bool:
    return bool(isinstance(files, dict) and isinstance(files.get(path), dict))


def _bundle_exploration_outputs(
    *,
    runtime_files: Dict[str, Dict[str, Any]],
    structured_payload: Dict[str, Any],
    mode: str,
    root_thread_id: str,
    exploration_thread_id: str,
    compile_thread_id: str,
    message: str,
) -> Dict[str, Any]:
    required_paths = _required_exploration_artifacts(mode)
    manifest: Dict[str, ExplorationArtifactStatus] = {}
    gaps: List[str] = []
    for path in required_paths:
        owner = str(EXPLORATION_ARTIFACT_OWNERS.get(path) or "report_coordinator").strip()
        ready = _runtime_file_exists(runtime_files, path)
        status = "ready" if ready else "missing"
        if not ready:
            gaps.append(f"{owner} 未产出 {Path(path).name}")
        manifest[path] = ExplorationArtifactStatus(
            path=path,
            owner=owner,
            status=status,
            summary="ready" if ready else "missing",
        )
    metadata = _payload_meta(structured_payload)
    todos = metadata.get("todos") if isinstance(metadata.get("todos"), list) else []
    bundle = ExplorationBundle(
        root_thread_id=root_thread_id,
        exploration_thread_id=exploration_thread_id,
        compile_thread_id=compile_thread_id,
        todos=todos if isinstance(todos, list) else [],
        gap_summary=gaps,
        exploration_manifest=manifest,
        exploration_graph_state={
            "root_thread_id": root_thread_id,
            "exploration_thread_id": exploration_thread_id,
            "compile_thread_id": compile_thread_id,
            "status": "degraded" if gaps else "ready",
            "message": message,
        },
    )
    return bundle.model_dump()


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
        "basic_analysis_snapshot": payload.get("basic_analysis_snapshot") if isinstance(payload.get("basic_analysis_snapshot"), dict) else {},
        "basic_analysis_insight": payload.get("basic_analysis_insight") if isinstance(payload.get("basic_analysis_insight"), dict) else {},
        "bertopic_snapshot": payload.get("bertopic_snapshot") if isinstance(payload.get("bertopic_snapshot"), dict) else {},
        "bertopic_insight": payload.get("bertopic_insight") if isinstance(payload.get("bertopic_insight"), dict) else {},
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
                "source_id": str(_pick_first(item, "source_id", "source_ref", "raw_source_id")).strip(),
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
        "basic_analysis_snapshot": {},
        "basic_analysis_insight": {},
        "bertopic_snapshot": {},
        "bertopic_insight": {},
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
    base_context = build_base_context(
        topic_identifier,
        start_text,
        end_text,
        topic_label=topic_label,
        mode=str(((output.get("task") or {}).get("mode")) or "fast"),
    )
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
            "conflict_map": output.get("conflict_map") or {},
            "mechanism_summary": output.get("mechanism_summary") or {},
            "utility_assessment": output.get("utility_assessment") or {},
            "basic_analysis_snapshot": output.get("basic_analysis_snapshot") or base_context.get("basic_analysis_snapshot") or {},
            "basic_analysis_insight": output.get("basic_analysis_insight") or base_context.get("basic_analysis_insight") or {},
            "bertopic_snapshot": output.get("bertopic_snapshot") or base_context.get("bertopic_snapshot") or {},
            "bertopic_insight": output.get("bertopic_insight") or base_context.get("bertopic_insight") or {},
            "metadata": output.get("metadata") or {},
        }
    )
    analyze_results = build_analyze_results_payload(
        topic_identifier,
        start_text,
        end_text,
        topic_label=topic_label,
    )
    functions_payload = analyze_results.get("functions") if isinstance(analyze_results.get("functions"), list) else []
    metric_bundle, figures, figure_artifacts, placement_plan = build_figure_pipeline(
        functions_payload,
        bundle=report_data,
        bertopic_snapshot=report_data.bertopic_snapshot.model_dump() if report_data.bertopic_snapshot else {},
    )
    overview = base_context.get("overview") if isinstance(base_context.get("overview"), dict) else {}
    if composer_output is not None:
        report_document = assemble_report_document(composer_output, report_data, figures, placement_plan, overview)
    else:
        report_document = build_report_document(report_data, figures, placement_plan, overview)
    output.setdefault("metadata", {})
    output["metadata"]["document_type"] = str(base_context.get("document_type") or "analysis_report").strip() or "analysis_report"
    output["metadata"]["report_blueprint"] = load_report_blueprint(output["metadata"]["document_type"])
    output["metadata"]["figure_policy_version"] = "figure-policy.v1"
    output["metadata"]["figure_ids"] = [item.figure_id for item in figures]
    output["report_data"] = report_data.model_dump()
    output["report_document"] = report_document
    output["metric_bundle"] = metric_bundle.model_dump()
    output["figures"] = [item.model_dump() for item in figures]
    output["figure_artifacts"] = [item.model_dump() for item in figure_artifacts]
    output["placement_plan"] = placement_plan.model_dump()
    return output


def _attach_ir_layers(
    payload: Dict[str, Any],
    *,
    topic_identifier: str,
    cache_dir: Any,
    thread_id: str,
    task_id: str,
    full_cache_exists: bool = False,
    runtime_path: str = "",
) -> Dict[str, Any]:
    previous_manifest = payload.get("artifact_manifest") if isinstance(payload.get("artifact_manifest"), dict) else None
    manifest = build_artifact_manifest(
        topic_identifier=topic_identifier,
        thread_id=thread_id,
        task_id=task_id,
        structured_path=str(cache_dir / REPORT_CACHE_FILENAME),
        basic_analysis_path=str(cache_dir / "basic_analysis_insight.json"),
        bertopic_path=str(cache_dir / "bertopic_insight.json"),
        agenda_path=str(cache_dir / "agenda_frame_map.json"),
        conflict_path=str(cache_dir / "conflict_map.json"),
        mechanism_path=str(cache_dir / "mechanism_summary.json"),
        utility_path=str(cache_dir / "utility_assessment.json"),
        full_path=str(cache_dir / AI_FULL_REPORT_CACHE_FILENAME) if full_cache_exists else "",
        runtime_path=str(runtime_path or "").strip(),
        ir_path=str(cache_dir / "report_ir.json"),
        figure_artifacts=payload.get("figure_artifacts") if isinstance(payload.get("figure_artifacts"), list) else [],
        previous_manifest=previous_manifest,
    )
    enriched = attach_report_ir(payload, artifact_manifest=manifest, task_id=task_id)
    if isinstance(enriched.get("basic_analysis_insight"), dict):
        _write_json(cache_dir / "basic_analysis_insight.json", enriched.get("basic_analysis_insight") or {})
    if isinstance(enriched.get("bertopic_insight"), dict):
        _write_json(cache_dir / "bertopic_insight.json", enriched.get("bertopic_insight") or {})
    if isinstance(enriched.get("report_ir"), dict):
        _write_json(cache_dir / "report_ir.json", enriched.get("report_ir") or {})
    report_ir = enriched.get("report_ir") if isinstance(enriched.get("report_ir"), dict) else {}
    if isinstance(report_ir.get("agenda_frame_map"), dict):
        _write_json(cache_dir / "agenda_frame_map.json", report_ir.get("agenda_frame_map") or {})
    if isinstance(report_ir.get("conflict_map"), dict):
        _write_json(cache_dir / "conflict_map.json", report_ir.get("conflict_map") or {})
    if isinstance(report_ir.get("mechanism_summary"), dict):
        _write_json(cache_dir / "mechanism_summary.json", report_ir.get("mechanism_summary") or {})
    if isinstance(report_ir.get("utility_assessment"), dict):
        _write_json(cache_dir / "utility_assessment.json", report_ir.get("utility_assessment") or {})
    enriched.setdefault("metadata", {})
    enriched["metadata"]["artifact_manifest"] = manifest.model_dump()
    enriched["metadata"]["report_ir_summary"] = summarize_report_ir(enriched.get("report_ir") or {})
    enriched["meta"] = {**(enriched.get("meta") or {}), **enriched["metadata"]}
    return enriched


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
        "archive_evidence_organizer": "interpret",
        "timeline_analyst": "interpret",
        "stance_conflict": "interpret",
        "claim_actor_conflict": "interpret",
        "propagation_analyst": "interpret",
        "bertopic_evolution_analyst": "interpret",
        "decision_utility_judge": "review",
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
    if isinstance(result, str):
        return str(result or "").strip()[:300]
    return ""


def _tool_result_text(result: Any) -> str:
    if isinstance(result, ToolMessage):
        return str(result.content or "").strip()
    if isinstance(result, Command):
        update = result.update if isinstance(result.update, dict) else {}
        messages = update.get("messages") if isinstance(update.get("messages"), list) else []
        if messages:
            last = messages[-1]
            content = getattr(last, "content", None)
            if content is None:
                content = getattr(last, "text", None)
            return str(content or "").strip()
    if isinstance(result, str):
        return str(result or "").strip()
    return ""


def _parse_tool_result_payload(result: Any) -> Dict[str, Any]:
    text = _tool_result_text(result)
    if not text or not re.match(r"^\s*[\[{]", text):
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _task_contract_from_tracker(tracker: Optional[Dict[str, Any]]) -> Dict[str, str]:
    payload = tracker.get("task_contract") if isinstance(tracker, dict) and isinstance(tracker.get("task_contract"), dict) else {}
    return {
        "topic_identifier": str(payload.get("topic_identifier") or "").strip(),
        "topic_label": str(payload.get("topic_label") or "").strip(),
        "start": str(payload.get("start") or "").strip(),
        "end": str(payload.get("end") or "").strip(),
        "mode": str(payload.get("mode") or "").strip().lower(),
        "thread_id": str(payload.get("thread_id") or "").strip(),
    }


def _normalized_task_contract_violation(payload: Dict[str, Any], tracker: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    contract = _task_contract_from_tracker(tracker)
    if not any(contract.values()) or not isinstance(payload, dict):
        return payload, {}
    normalized = payload.get("normalized_task") if isinstance(payload.get("normalized_task"), dict) else payload.get("result")
    if not isinstance(normalized, dict):
        return payload, {}
    corrected = dict(normalized)
    corrected_time_range = corrected.get("time_range") if isinstance(corrected.get("time_range"), dict) else {}
    violations: Dict[str, Dict[str, str]] = {}
    current_topic_identifier = str(corrected.get("topic_identifier") or "").strip()
    current_start = str(corrected_time_range.get("start") or "").strip()
    current_end = str(corrected_time_range.get("end") or current_start).strip()
    current_mode = str(corrected.get("mode") or "fast").strip().lower() or "fast"

    def _record(field: str, actual: str, expected: str) -> None:
        if expected and actual != expected:
            violations[field] = {"actual": actual, "expected": expected}

    _record("topic_identifier", current_topic_identifier, contract["topic_identifier"])
    _record("start", current_start, contract["start"])
    _record("end", current_end, contract["end"])
    _record("mode", current_mode, contract["mode"])

    task_contract_payload = payload.get("task_contract") if isinstance(payload.get("task_contract"), dict) else {}
    task_derivation_payload = payload.get("task_derivation") if isinstance(payload.get("task_derivation"), dict) else {}
    proposal_snapshot = payload.get("proposal_snapshot") if isinstance(payload.get("proposal_snapshot"), dict) else {}

    if not violations:
        corrected["task_contract"] = {
            "topic_identifier": contract["topic_identifier"],
            "topic_label": contract["topic_label"],
            "start": contract["start"],
            "end": contract["end"],
            "mode": contract["mode"],
            "thread_id": contract["thread_id"],
        }
        if task_contract_payload:
            payload["task_contract"] = {
                **task_contract_payload,
                "contract_id": str(task_contract_payload.get("contract_id") or f"{contract['topic_identifier']}:{contract['start']}:{contract['end']}").strip(),
                "topic_identifier": contract["topic_identifier"],
                "topic_label": contract["topic_label"],
                "start": contract["start"],
                "end": contract["end"],
                "mode": contract["mode"],
                "thread_id": contract["thread_id"],
            }
        payload["normalized_task"] = corrected
        payload["result"] = corrected
        return payload, {}

    corrected["topic_identifier"] = contract["topic_identifier"] or current_topic_identifier
    corrected["topic"] = str(contract["topic_label"] or corrected.get("topic") or corrected["topic_identifier"]).strip()
    corrected["mode"] = contract["mode"] or current_mode
    corrected["time_range"] = {
        "start": contract["start"] or current_start,
        "end": contract["end"] or current_end or contract["start"] or current_start,
    }
    corrected["task_id"] = f"{corrected['topic_identifier']}:{corrected['time_range']['start']}:{corrected['time_range']['end']}"
    contract_overrides = [
        str(item).strip()
        for item in (corrected.get("contract_overrides_applied") or [])
        if str(item or "").strip()
    ]
    for field in violations:
        if field not in contract_overrides:
            contract_overrides.append(field)
    corrected["contract_overrides_applied"] = contract_overrides
    corrected["task_contract"] = {
        "topic_identifier": contract["topic_identifier"],
        "topic_label": contract["topic_label"],
        "start": contract["start"],
        "end": contract["end"],
        "mode": contract["mode"],
        "thread_id": contract["thread_id"],
    }
    if task_contract_payload:
        payload["task_contract"] = {
            **task_contract_payload,
            "contract_id": str(task_contract_payload.get("contract_id") or f"{contract['topic_identifier']}:{contract['start']}:{contract['end']}").strip(),
            "topic_identifier": contract["topic_identifier"],
            "topic_label": contract["topic_label"],
            "start": contract["start"],
            "end": contract["end"],
            "mode": contract["mode"],
            "thread_id": contract["thread_id"],
        }
    if task_derivation_payload:
        attempted = task_derivation_payload.get("attempted_overrides") if isinstance(task_derivation_payload.get("attempted_overrides"), dict) else {}
        for field, detail in violations.items():
            attempted[field] = str(detail.get("actual") or "").strip()
        payload["task_derivation"] = {
            **task_derivation_payload,
            "attempted_overrides": attempted,
            "contract_overrides_applied": contract_overrides,
        }
    if proposal_snapshot:
        requested = proposal_snapshot.get("requested_execution_fields") if isinstance(proposal_snapshot.get("requested_execution_fields"), dict) else {}
        repair_log = proposal_snapshot.get("repair_log") if isinstance(proposal_snapshot.get("repair_log"), list) else []
        for field, detail in violations.items():
            repair_log.append({"field": field, "actual": str(detail.get("actual") or "").strip(), "expected": str(detail.get("expected") or "").strip()})
            requested[field] = str(detail.get("actual") or "").strip()
        payload["proposal_snapshot"] = {
            **proposal_snapshot,
            "requested_execution_fields": requested,
            "effective_contract": {
                "contract_id": str((payload.get("task_contract") or {}).get("contract_id") or f"{contract['topic_identifier']}:{contract['start']}:{contract['end']}").strip(),
                "topic_identifier": contract["topic_identifier"],
                "topic_label": contract["topic_label"],
                "start": contract["start"],
                "end": contract["end"],
                "mode": contract["mode"],
                "thread_id": contract["thread_id"],
            },
            "repair_action": "override",
            "repair_log": repair_log,
        }
    payload["normalized_task"] = corrected
    payload["result"] = corrected
    return payload, violations


def _tool_coverage_flags(payload: Dict[str, Any]) -> List[str]:
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    return [
        str(item).strip()
        for item in (coverage.get("readiness_flags") or [])
        if str(item or "").strip()
    ]


def _tool_coverage_counts(payload: Dict[str, Any]) -> Dict[str, int]:
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    platform_counts = coverage.get("platform_counts") if isinstance(coverage.get("platform_counts"), dict) else {}
    return {
        "matched_count": int(coverage.get("matched_count") or 0),
        "sampled_count": int(coverage.get("sampled_count") or 0),
        "platform_count": len(platform_counts),
    }


def _claim_verification_counts(records: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        "checked_count": len(records),
        "supported_count": 0,
        "partially_supported_count": 0,
        "unsupported_count": 0,
        "contradicted_count": 0,
    }
    for item in records:
        status = str(item.get("status") or "").strip()
        key = f"{status}_count"
        if key in counts:
            counts[key] += 1
    return counts


def _build_validation_notes_markdown(*, topic_label: str, claim_checks: Dict[str, Any]) -> str:
    records = claim_checks.get("result") if isinstance(claim_checks.get("result"), list) else claim_checks.get("claims", [])
    records = [item for item in records if isinstance(item, dict)]
    counts = _claim_verification_counts(records)
    summary_lines = [
        "# 校验意见报告",
        "",
        f"**报告主题**：{str(topic_label or '').strip() or '当前专题'}  ",
        f"**校验时间**：{_utc_now()[:19].replace('T', ' ')}  ",
        "**校验来源**：verify_claim_v2 编译摘要",
        "",
        "---",
        "",
        "## 一、校验概要",
        "",
        f"- 已校验 {counts['checked_count']} 条关键断言",
        f"- supported：{counts['supported_count']} 条",
        f"- partially_supported：{counts['partially_supported_count']} 条",
        f"- unsupported：{counts['unsupported_count']} 条",
        f"- contradicted：{counts['contradicted_count']} 条",
        "",
        "## 二、处理建议",
        "",
    ]
    if counts["unsupported_count"] or counts["contradicted_count"]:
        summary_lines.extend(
            [
                "- 当前草稿中存在无法直接回链或存在反证的断言。",
                "- 后续正式文稿应降低结论强度，并显式保留不确定性边界。",
            ]
        )
    else:
        summary_lines.extend(
            [
                "- 当前关键断言未发现明显回链缺口。",
                "- 可继续沿既有结构进入正式文稿编译。",
            ]
        )
    gap_records = [
        item for item in records
        if str(item.get("status") or "").strip() in {"unsupported", "contradicted"}
    ]
    if gap_records:
        summary_lines.extend(["", "## 三、重点缺口", ""])
        for item in gap_records[:5]:
            claim_text = str(item.get("claim_text") or "").strip() or str(item.get("claim_id") or "").strip()
            gap_note = str(item.get("gap_note") or "").strip() or "当前证据池中没有直接支持。"
            status = str(item.get("status") or "").strip()
            summary_lines.append(f"- `{status}`：{claim_text}；{gap_note}")
    return "\n".join(summary_lines).strip()


def _upsert_runtime_text_file(files: Optional[Dict[str, Dict[str, Any]]], path: str, content: str) -> None:
    if not isinstance(files, dict) or not path:
        return
    files[path] = create_file_data(str(content or "").strip())


def _ensure_validation_notes_from_claim_checks(
    files: Optional[Dict[str, Dict[str, Any]]],
    *,
    topic_label: str,
) -> Dict[str, int]:
    raw = _read_runtime_file(files if isinstance(files, dict) else {}, "/workspace/state/claim_checks.json")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    records = parsed.get("result") if isinstance(parsed.get("result"), list) else parsed.get("claims", [])
    records = [item for item in records if isinstance(item, dict)]
    if not records:
        return {}
    counts = _claim_verification_counts(records)
    markdown = _build_validation_notes_markdown(topic_label=topic_label, claim_checks=parsed)
    _upsert_runtime_text_file(files, "/workspace/state/validation_notes.md", markdown)
    return counts


def _update_tool_tracker(shared: Dict[str, Any], tool_name: str, payload: Dict[str, Any], raw_text: str) -> None:
    if not isinstance(shared, dict) or not isinstance(payload, dict):
        return
    flags = set(_tool_coverage_flags(payload))
    runtime_files = shared.get("runtime_files") if isinstance(shared.get("runtime_files"), dict) else None
    if bool(payload.get("legacy_adapter_hit")):
        shared["legacy_adapter_hit_count"] = int(shared.get("legacy_adapter_hit_count") or 0) + 1
        legacy_hits = shared.get("legacy_adapter_hits") if isinstance(shared.get("legacy_adapter_hits"), list) else []
        legacy_hits.append(
            {
                "tool_name": tool_name,
                "legacy_input_kind": [str(item).strip() for item in (payload.get("legacy_input_kind") or []) if str(item or "").strip()],
                "violation_origin": str(payload.get("violation_origin") or "payload_adapter").strip() or "payload_adapter",
                "repair_action": str(payload.get("repair_action") or "mapped_legacy_fields").strip() or "mapped_legacy_fields",
            }
        )
        shared["legacy_adapter_hits"] = legacy_hits
    if tool_name == "normalize_task":
        task_contract = payload.get("task_contract") if isinstance(payload.get("task_contract"), dict) else {}
        task_derivation = payload.get("task_derivation") if isinstance(payload.get("task_derivation"), dict) else {}
        proposal_snapshot = payload.get("proposal_snapshot") if isinstance(payload.get("proposal_snapshot"), dict) else {}
        if task_contract:
            persist_task_contract_bundle(
                task_contract=task_contract,
                task_derivation=task_derivation,
                proposal_snapshot=proposal_snapshot,
            )
        if task_contract:
            _upsert_runtime_json_file(runtime_files, "/workspace/state/task_contract.json", task_contract)
        if task_derivation:
            _upsert_runtime_json_file(runtime_files, "/workspace/state/task_derivation.json", task_derivation)
        if proposal_snapshot:
            _upsert_runtime_json_file(runtime_files, "/workspace/state/task_derivation_proposal.json", proposal_snapshot)
        _upsert_runtime_json_file(runtime_files, "/workspace/state/normalized_task.json", payload)
    elif tool_name == "get_corpus_coverage":
        if "contract_binding_failed" in flags:
            shared["coverage_state"] = "contract_binding_failed"
        elif "contract_violation" in flags:
            shared["coverage_state"] = "contract_violation"
        elif "no_records_in_scope" in flags:
            shared["coverage_state"] = "empty_corpus"
        elif "source_unavailable" in flags:
            shared["coverage_state"] = "source_unavailable"
        else:
            shared["coverage_state"] = "ready"
        shared["coverage_flags"] = sorted(flags)
    elif tool_name == "retrieve_evidence_cards":
        cards = payload.get("result") if isinstance(payload.get("result"), list) else []
        effective_flags = set(flags)
        if not cards:
            effective_flags.add("no_cards")
        shared["evidence_state"] = "empty_evidence" if "no_cards" in effective_flags else "ready"
        shared["evidence_flags"] = sorted(effective_flags)
        if shared.get("coverage_state") == "empty_corpus" and "no_cards" in effective_flags and raw_text:
            shared["empty_evidence_result_text"] = raw_text
    elif tool_name == "verify_claim_v2":
        records = payload.get("result") if isinstance(payload.get("result"), list) else payload.get("claims", [])
        if isinstance(records, list):
            shared["claim_verification_counts"] = _claim_verification_counts([item for item in records if isinstance(item, dict)])


def _build_tool_intelligence_receipt(tool_name: str, payload: Dict[str, Any], tracker: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    counts = _tool_coverage_counts(payload)
    flags = set(_tool_coverage_flags(payload))
    tracker_state = tracker if isinstance(tracker, dict) else {}
    stage_map = {
        "normalize_task": "scope",
        "get_corpus_coverage": "scope",
        "retrieve_evidence_cards": "evidence",
        "build_event_timeline": "structure",
        "compute_report_metrics": "structure",
        "extract_actor_positions": "structure",
        "build_claim_actor_conflict": "structure",
        "build_mechanism_summary": "structure",
        "detect_risk_signals": "structure",
        "judge_decision_utility": "validation",
        "verify_claim_v2": "validation",
        "build_section_packet": "writing",
    }
    stage_id = stage_map.get(tool_name, "interpret")
    receipt = {
        "stage_id": stage_id,
        "tool_name": tool_name,
        "outcome_kind": "success",
        "decision_summary": "",
        "skip_reason": "",
        "next_action": "",
        "counts": counts,
        "contract_value": payload.get("contract_value") if isinstance(payload.get("contract_value"), dict) else {},
        "agent_proposed_value": payload.get("agent_proposed_value") if isinstance(payload.get("agent_proposed_value"), dict) else {},
        "effective_value": payload.get("effective_value") if isinstance(payload.get("effective_value"), dict) else {},
        "violation_origin": str(payload.get("violation_origin") or "").strip(),
        "repair_action": str(payload.get("repair_action") or "").strip(),
    }

    if tool_name == "normalize_task":
        receipt["counts"] = {}
        normalized_task = payload.get("normalized_task") if isinstance(payload.get("normalized_task"), dict) else payload.get("result", {})
        time_range = normalized_task.get("time_range") if isinstance(normalized_task, dict) and isinstance(normalized_task.get("time_range"), dict) else {}
        topic = str((normalized_task or {}).get("topic") or "").strip()
        start = str((time_range or {}).get("start") or "").strip()
        end = str((time_range or {}).get("end") or start).strip()
        overrides = [
            str(item).strip()
            for item in ((normalized_task or {}).get("contract_overrides_applied") or [])
            if str(item or "").strip()
        ]
        receipt["effective_range"] = {"start": start, "end": end}
        receipt["effective_topic_identifier"] = str((normalized_task or {}).get("topic_identifier") or "").strip()
        if overrides:
            contract = _task_contract_from_tracker(tracker_state)
            receipt["outcome_kind"] = "degraded"
            receipt["diagnostic_kind"] = "contract_violation"
            receipt["requested_range"] = {
                "start": str((tracker_state.get("task_contract_violation") or {}).get("start", {}).get("actual") or "").strip(),
                "end": str((tracker_state.get("task_contract_violation") or {}).get("end", {}).get("actual") or "").strip(),
            }
            receipt["decision_summary"] = (
                f"检索子代理改写了任务边界，已按真实任务合同纠正为 {topic or '当前专题'}，"
                f"时间窗 {start or '未指定'} 至 {end or start or '未指定'}。"
            )
            receipt["skip_reason"] = "contract_violation"
            receipt["next_action"] = "按纠正后的真实任务边界继续进行语料覆盖判断。"
            if contract.get("topic_identifier"):
                receipt["contract_topic_identifier"] = contract["topic_identifier"]
        else:
            receipt["decision_summary"] = f"任务范围已冻结：{topic or '当前专题'}，时间窗 {start or '未指定'} 至 {end or start or '未指定'}。"
            receipt["next_action"] = "继续进行语料覆盖判断。"
        return receipt

    if tool_name == "get_corpus_coverage":
        coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
        source_resolution = str(coverage.get("source_resolution") or "").strip()
        resolved_fetch_range = coverage.get("resolved_fetch_range") if isinstance(coverage.get("resolved_fetch_range"), dict) else {}
        requested_range = coverage.get("requested_time_range") if isinstance(coverage.get("requested_time_range"), dict) else {}
        effective_range = coverage.get("effective_time_range") if isinstance(coverage.get("effective_time_range"), dict) else {}
        effective_topic_identifier = str(coverage.get("effective_topic_identifier") or "").strip()
        contract_topic_identifier = str(coverage.get("contract_topic_identifier") or "").strip()
        receipt["requested_range"] = requested_range
        receipt["effective_range"] = effective_range
        receipt["resolved_fetch_range"] = resolved_fetch_range
        receipt["effective_topic_identifier"] = effective_topic_identifier
        receipt["contract_topic_identifier"] = contract_topic_identifier
        receipt["diagnostic_kind"] = ""
        if bool(payload.get("legacy_adapter_hit")):
            receipt["outcome_kind"] = "degraded"
            receipt["diagnostic_kind"] = "legacy_adapter_hit"
            receipt["decision_summary"] = "当前调用命中了 legacy adapter，系统已映射到新 ABI 后继续执行。"
            receipt["next_action"] = "建议尽快清理旧 JSON 入口，避免兼容层继续承接主链路。"
        if "contract_binding_failed" in flags:
            receipt["outcome_kind"] = "failed"
            receipt["diagnostic_kind"] = "contract_binding_failed"
            receipt["skip_reason"] = "contract_binding_failed"
            receipt["decision_summary"] = "contract_id 缺失或无法绑定到 registry，系统已阻止继续检索。"
            receipt["next_action"] = "请确认当前任务是否已生成 task_contract，并使用 contract_id 重新调用。"
        elif bool(coverage.get("contract_mismatch")) or "contract_violation" in flags:
            receipt["outcome_kind"] = "degraded"
            receipt["diagnostic_kind"] = "contract_violation"
            receipt["skip_reason"] = "contract_violation"
            receipt["decision_summary"] = "检索子代理改写了任务边界，已阻止继续按错误范围检索。"
            receipt["next_action"] = "请按运行时真实任务合同重新执行覆盖判断。"
        elif source_resolution == "overlap_fetch_range":
            receipt["outcome_kind"] = "degraded"
            receipt["diagnostic_kind"] = "partial_range_coverage"
            receipt["decision_summary"] = "当前请求区间与已有语料部分重叠，已按可用重叠区间继续检索。"
            receipt["next_action"] = "继续整理证据卡，但后续结论需保留区间部分覆盖说明。"
        elif "scope_clipped_to_contract" in payload.get("coverage", {}).get("source_quality_flags", []):
            receipt["outcome_kind"] = "degraded"
            receipt["diagnostic_kind"] = "scope_clipped_to_contract"
            receipt["decision_summary"] = "自定义时间窗超出了主任务范围，系统已裁剪到 contract 内继续检索。"
            receipt["next_action"] = "继续检索，但请注意当前结果只覆盖裁剪后的时间区间。"
        elif "source_unavailable" in flags or source_resolution == "unavailable":
            receipt["outcome_kind"] = "empty"
            receipt["diagnostic_kind"] = "source_unavailable"
            receipt["skip_reason"] = "source_unavailable"
            receipt["decision_summary"] = "当前没有命中的 fetch 归档或上传源。"
            receipt["next_action"] = "请先确认专题归档和时间窗是否存在可用原始语料。"
        elif "no_records_in_scope" in flags:
            receipt["outcome_kind"] = "empty"
            receipt["diagnostic_kind"] = "true_empty_corpus"
            receipt["skip_reason"] = "empty_corpus"
            receipt["decision_summary"] = "当前时间窗内没有命中语料，已进入空样本路径。"
            receipt["next_action"] = "证据整理只保留空结果，不再继续扩检。"
        elif "single_platform_skew" in payload.get("coverage", {}).get("source_quality_flags", []):
            receipt["outcome_kind"] = "degraded"
            receipt["decision_summary"] = f"已命中 {counts['matched_count']} 条记录，但来源平台偏斜。"
            receipt["next_action"] = "后续判断需降低外推强度。"
        else:
            receipt["decision_summary"] = f"已命中 {counts['matched_count']} 条记录，覆盖 {counts['platform_count']} 个平台。"
            receipt["next_action"] = "进入证据卡整理。"
        return receipt

    if tool_name == "retrieve_evidence_cards":
        cards = payload.get("result") if isinstance(payload.get("result"), list) else []
        effective_flags = set(flags)
        if not cards:
            effective_flags.add("no_cards")
        receipt["counts"] = {**counts, "cards_count": len(cards)}
        if "contract_binding_failed" in flags:
            receipt["outcome_kind"] = "failed"
            receipt["diagnostic_kind"] = "contract_binding_failed"
            receipt["skip_reason"] = "contract_binding_failed"
            receipt["decision_summary"] = "contract 绑定失败，系统没有继续召回证据卡。"
            receipt["next_action"] = "请先修复 contract registry 或重建当前任务后再检索。"
        elif "no_cards" in effective_flags:
            receipt["outcome_kind"] = "empty"
            receipt["skip_reason"] = "empty_corpus" if tracker_state.get("coverage_state") == "empty_corpus" else "empty_evidence"
            receipt["decision_summary"] = "当前 scope 下没有召回到可用证据卡。"
            receipt["next_action"] = "后续节点按空证据对象运行，不再继续多轮召回。"
        else:
            receipt["decision_summary"] = f"已召回 {len(cards)} 张证据卡，覆盖 {counts['platform_count']} 个平台。"
            receipt["next_action"] = "进入时间线、冲突图谱与机制分析。"
        return receipt

    if tool_name == "build_event_timeline":
        nodes = payload.get("result") if isinstance(payload.get("result"), list) else []
        receipt["counts"] = {**counts, "timeline_count": len(nodes)}
        if "timeline_empty" in flags or not nodes:
            receipt["outcome_kind"] = "empty"
            receipt["skip_reason"] = "insufficient_structure"
            receipt["decision_summary"] = "当前没有形成可回链的时间线节点。"
            receipt["next_action"] = "保留空时间线结果，避免继续深描。"
        else:
            receipt["decision_summary"] = f"已生成 {len(nodes)} 个时间线节点。"
            receipt["next_action"] = "继续汇总结构分析结果。"
        return receipt

    if tool_name == "compute_report_metrics":
        metrics = payload.get("result") if isinstance(payload.get("result"), list) else []
        receipt["counts"] = {**counts, "metric_count": len(metrics)}
        receipt["outcome_kind"] = "empty" if "metric_empty" in flags else "success"
        receipt["decision_summary"] = "当前没有可用于统计的证据卡。" if "metric_empty" in flags else f"已生成 {len(metrics)} 组指标对象。"
        receipt["next_action"] = "供冲突、机制和风险判断复用。"
        return receipt

    if tool_name == "extract_actor_positions":
        actors = payload.get("result") if isinstance(payload.get("result"), list) else []
        receipt["counts"] = {**counts, "actor_count": len(actors)}
        if "actor_empty" in flags or not actors:
            receipt["outcome_kind"] = "empty"
            receipt["skip_reason"] = "insufficient_structure"
            receipt["decision_summary"] = "当前没有识别到明确主体立场。"
            receipt["next_action"] = "后续争议分析需保留主体缺失边界。"
        else:
            receipt["decision_summary"] = f"已提取 {len(actors)} 个主体立场。"
            receipt["next_action"] = "进入冲突图谱构建。"
        return receipt

    if tool_name == "build_claim_actor_conflict":
        conflict_map = payload.get("result") if isinstance(payload.get("result"), dict) else payload.get("conflict_map", {})
        claim_count = len(conflict_map.get("claims") or []) if isinstance(conflict_map, dict) else 0
        actor_count = len(conflict_map.get("actor_positions") or []) if isinstance(conflict_map, dict) else 0
        edge_count = len(conflict_map.get("edges") or []) if isinstance(conflict_map, dict) else 0
        receipt["counts"] = {**counts, "claims_count": claim_count, "actors_count": actor_count, "conflicts_count": edge_count}
        if "conflict_map_empty" in flags or claim_count == 0:
            receipt["outcome_kind"] = "empty"
            receipt["skip_reason"] = "insufficient_structure"
            receipt["decision_summary"] = "当前未形成可回链争议轴，冲突图谱保持为空。"
            receipt["next_action"] = "跳过争议深描，保留空图谱说明。"
        else:
            receipt["decision_summary"] = f"冲突图谱已形成：claim {claim_count} 条，主体 {actor_count} 个，冲突边 {edge_count} 条。"
            receipt["next_action"] = "进入传播机制与风险判断。"
        return receipt

    if tool_name == "build_mechanism_summary":
        mechanism = payload.get("result") if isinstance(payload.get("result"), dict) else payload.get("mechanism_summary", {})
        path_count = len(mechanism.get("amplification_paths") or []) if isinstance(mechanism, dict) else 0
        trigger_count = len(mechanism.get("trigger_events") or []) if isinstance(mechanism, dict) else 0
        bridge_count = len(mechanism.get("bridge_nodes") or []) if isinstance(mechanism, dict) else 0
        receipt["counts"] = {**counts, "paths_count": path_count, "triggers_count": trigger_count, "bridge_nodes_count": bridge_count}
        if "mechanism_empty" in flags or (path_count == 0 and trigger_count == 0 and bridge_count == 0):
            receipt["outcome_kind"] = "empty"
            receipt["skip_reason"] = "insufficient_structure"
            receipt["decision_summary"] = "机制判断因证据不足跳过，当前传播机制对象为空。"
            receipt["next_action"] = "后续正式文稿仅保留空机制边界说明。"
        else:
            receipt["decision_summary"] = f"已识别 {path_count} 条放大路径、{trigger_count} 个触发节点、{bridge_count} 个桥接节点。"
            receipt["next_action"] = "进入风险信号与效用裁决。"
        return receipt

    if tool_name == "detect_risk_signals":
        risks = payload.get("result") if isinstance(payload.get("result"), list) else []
        receipt["counts"] = {**counts, "risks_count": len(risks)}
        if "risk_empty" in flags or not risks:
            receipt["outcome_kind"] = "empty"
            receipt["skip_reason"] = "insufficient_structure"
            receipt["decision_summary"] = "暂未识别到可独立成项的风险信号。"
            receipt["next_action"] = "风险章节需保留条件不足说明。"
        else:
            receipt["decision_summary"] = f"已识别 {len(risks)} 个风险信号。"
            receipt["next_action"] = "继续进行决策可用性裁决。"
        return receipt

    if tool_name == "judge_decision_utility":
        assessment = payload.get("result") if isinstance(payload.get("result"), dict) else payload.get("utility_assessment", {})
        decision = str(assessment.get("decision") or "").strip()
        missing_dimensions = assessment.get("missing_dimensions") if isinstance(assessment.get("missing_dimensions"), list) else []
        receipt["counts"] = {**counts, "missing_dimensions_count": len(missing_dimensions)}
        receipt["outcome_kind"] = "success" if decision == "pass" else "degraded"
        receipt["decision_summary"] = f"当前裁决为 {decision or 'fallback_recompile'}。"
        receipt["skip_reason"] = "；".join(str(item).strip() for item in missing_dimensions[:3] if str(item or "").strip())
        receipt["next_action"] = str(assessment.get("next_action") or "").strip() or "等待下一步调度。"
        return receipt

    if tool_name == "verify_claim_v2":
        records = payload.get("result") if isinstance(payload.get("result"), list) else payload.get("claims", [])
        records = [item for item in records if isinstance(item, dict)]
        counts = _claim_verification_counts(records)
        receipt["counts"] = counts
        if counts["checked_count"] == 0:
            receipt["outcome_kind"] = "empty"
            receipt["skip_reason"] = "no_claims"
            receipt["decision_summary"] = "当前没有可校验的关键断言。"
            receipt["next_action"] = "保留空校验结果。"
        elif counts["unsupported_count"] or counts["contradicted_count"]:
            receipt["outcome_kind"] = "degraded"
            receipt["decision_summary"] = (
                f"断言核验完成：supported {counts['supported_count']}，partially_supported {counts['partially_supported_count']}，"
                f"unsupported {counts['unsupported_count']}，contradicted {counts['contradicted_count']}。"
            )
            receipt["next_action"] = "降低结论强度，并显式保留不确定性边界。"
        else:
            receipt["decision_summary"] = (
                f"断言核验完成：supported {counts['supported_count']}，partially_supported {counts['partially_supported_count']}。"
            )
            receipt["next_action"] = "可继续进入正式文稿编译。"
        return receipt

    if tool_name == "build_section_packet":
        packet = payload.get("result") if isinstance(payload.get("result"), dict) else payload.get("section_packet", {})
        section_id = str(packet.get("section_id") or "").strip()
        uncertainty_count = len(packet.get("uncertainty_notes") or []) if isinstance(packet, dict) else 0
        receipt["counts"] = {**counts, "uncertainty_count": uncertainty_count}
        receipt["outcome_kind"] = "degraded" if "section_packet_thin" in flags else "success"
        receipt["decision_summary"] = f"已组装 {section_id or '当前'} 章节材料包。"
        receipt["next_action"] = "供 writer 直接生成正式草稿。"
        return receipt

    return {}


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
            if (
                actor_name == "archive_evidence_organizer"
                and tool_name == "retrieve_evidence_cards"
                and shared is not None
                and shared.get("coverage_state") == "empty_corpus"
                and str(shared.get("empty_evidence_result_text") or "").strip()
            ):
                cached_result = str(shared.get("empty_evidence_result_text") or "").strip()
                _emit(
                    event_callback,
                    {
                        "type": "agent.memo",
                        "phase": default_phase,
                        "agent": actor_name,
                        "title": "空样本已短路",
                        "message": "当前时间窗内没有命中语料，证据召回直接复用空结果。",
                        "payload": {
                            "stage_id": "evidence",
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "outcome_kind": "skipped",
                            "decision_summary": "当前时间窗内没有命中语料，证据召回直接复用空结果。",
                            "skip_reason": "empty_corpus",
                            "next_action": "后续节点按空证据对象继续生成结构化空结果。",
                            "counts": {"matched_count": 0, "sampled_count": 0, "platform_count": 0, "cards_count": 0},
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
                            "result_preview": cached_result[:300],
                        },
                    },
                )
                return ToolMessage(content=cached_result, tool_call_id=tool_call_id)

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

        result_preview = _tool_result_preview(result)
        raw_text = _tool_result_text(result)
        parsed_payload = _parse_tool_result_payload(result)
        if tool_name == "normalize_task" and parsed_payload:
            corrected_payload, violations = _normalized_task_contract_violation(parsed_payload, shared)
            raw_text = json.dumps(corrected_payload, ensure_ascii=False)
            result_preview = raw_text[:300]
            parsed_payload = corrected_payload
            result = ToolMessage(content=raw_text, tool_call_id=tool_call_id)
            if violations:
                if shared is not None:
                    shared["task_contract_violation"] = violations
            elif shared is not None:
                shared.pop("task_contract_violation", None)
        if shared is not None and tool_name and parsed_payload:
            _update_tool_tracker(shared, tool_name, parsed_payload, raw_text)
        receipt = _build_tool_intelligence_receipt(tool_name, parsed_payload, shared) if tool_name and parsed_payload else {}

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
                    "result_preview": result_preview,
                },
            },
        )
        if receipt:
            receipt_payload = {
                **receipt,
                "tool_call_id": tool_call_id,
            }
            _emit(
                event_callback,
                {
                    "type": "agent.memo",
                    "phase": default_phase,
                    "agent": actor_name,
                    "title": "阶段判断已更新",
                    "message": str(receipt.get("decision_summary") or "").strip(),
                    "payload": receipt_payload,
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
        "/workspace/state/task_contract.json",
        "/workspace/state/task_derivation.json",
        "/workspace/state/task_derivation_proposal.json",
        "/workspace/state/normalized_task.json",
        "/workspace/state/retrieval_plan.json",
        "/workspace/state/dispatch_quality.json",
        "/workspace/state/corpus_coverage.json",
        "/workspace/state/evidence_cards.json",
        "/workspace/state/timeline_nodes.json",
        "/workspace/state/metrics_bundle.json",
        "/workspace/state/actor_positions.json",
        "/workspace/state/agenda_frame_map.json",
        "/workspace/state/conflict_map.json",
        "/workspace/state/mechanism_summary.json",
        "/workspace/state/risk_signals.json",
        "/workspace/state/utility_assessment.json",
        "/workspace/state/claim_checks.json",
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


def _runtime_file_ready(files: Dict[str, Any], path: str) -> bool:
    payload = files.get(path) if isinstance(files, dict) else None
    if not isinstance(payload, dict):
        return False
    return bool(_read_runtime_file(files, path).strip())


def _ready_for_deterministic_finalize(files: Dict[str, Any]) -> bool:
    required_paths = ("/workspace/state/structured_report.json",)
    return all(_runtime_file_ready(files, path) for path in required_paths)


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
        "/workspace/state/task_contract.json",
        "/workspace/state/task_derivation.json",
        "/workspace/state/task_derivation_proposal.json",
        "/workspace/state/normalized_task.json",
        "/workspace/state/retrieval_plan.json",
        "/workspace/state/dispatch_quality.json",
        "/workspace/state/corpus_coverage.json",
        "/workspace/state/evidence_cards.json",
        "/workspace/state/timeline_nodes.json",
        "/workspace/state/metrics_bundle.json",
        "/workspace/state/actor_positions.json",
        "/workspace/state/agenda_frame_map.json",
        "/workspace/state/conflict_map.json",
        "/workspace/state/mechanism_summary.json",
        "/workspace/state/risk_signals.json",
        "/workspace/state/utility_assessment.json",
        "/workspace/state/claim_checks.json",
        "/workspace/state/discourse_conflict_map.json",
        "/workspace/state/section_packets/overview.json",
        "/workspace/state/section_packets/timeline.json",
        "/workspace/state/section_packets/risk.json",
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


def _prepare_runtime(
    topic_identifier: str,
    start_text: str,
    end_text: str,
    *,
    topic_label: str,
    mode: str,
    thread_id: str,
    task_id: str,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Any, Dict[str, Any], List[str]]:
    base_context = build_base_context(
        topic_identifier,
        start_text,
        end_text,
        topic_label=topic_label,
        mode=mode,
        thread_id=thread_id,
    )
    workspace_files = build_workspace_files(base_context)
    runtime_backend, runtime_files, skill_assets, memory_paths = _build_runtime_backends(
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
        "task_id": task_id,
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        "base_context_path": "/workspace/base_context.json",
        "task_contract": base_context.get("task_contract") if isinstance(base_context.get("task_contract"), dict) else {},
    }
    return common_context, runtime_files, runtime_backend, skill_assets, memory_paths


def _migrate_graph_state(raw: dict) -> dict:
    """迁移旧格式 graph state dict 到当前 run_state_version。"""
    if not isinstance(raw, dict):
        return {}
    migrated = dict(raw)
    if migrated.get("run_state_version") != RUN_STATE_VERSION:
        migrated["run_state_version"] = RUN_STATE_VERSION
    return migrated


def _run_deep_report_exploration_task(
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
) -> ExplorationTaskResult:
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
    review_path = _semantic_review_path(cache_dir)
    runtime_artifact_path = build_artifacts_root(runtime_task_id, get_data_root()) / "report.md"
    common_context, runtime_files, runtime_backend, skill_assets, memory_paths = _prepare_runtime(
        topic_identifier,
        start_text,
        end_text,
        topic_label=display_name,
        mode=mode,
        thread_id=active_thread_id,
        task_id=runtime_task_id,
    )
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
        output = _attach_ir_layers(
            output,
            topic_identifier=topic_identifier,
            cache_dir=cache_dir,
            thread_id=active_thread_id,
            task_id=runtime_task_id,
            full_cache_exists=full_cache_path.exists(),
            runtime_path=str(runtime_artifact_path),
        )
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
        draft_bundle_path = cache_dir / "full_report_draft_bundle.json"
        draft_v2_path = cache_dir / "draft_bundle.v2.json"
        validation_path = cache_dir / "validation_result.v2.json"
        repair_plan_path = cache_dir / "repair_plan.v2.json"
        graph_state_path = cache_dir / "graph_state.v2.json"
        compile_graph_path = cache_dir / "compile_graph.sqlite"
        compile_graph_thread_id = f"{runtime_task_id}:compile"
        compile_locator_hint = _runtime_locator_hint(
            purpose="deep-report-compile",
            task_id=runtime_task_id,
            sqlite_path=str(compile_graph_path),
        )
        structured_payload = _attach_ir_layers(
            structured_payload,
            topic_identifier=topic_identifier,
            cache_dir=cache_dir,
            thread_id=active_thread_id,
            task_id=runtime_task_id,
            full_cache_exists=True,
            runtime_path=str(runtime_artifact_path),
        )
        compiled = compile_markdown_artifacts(
            structured_payload,
            allow_review_pending=True,
            event_callback=event_callback,
            checkpointer_path=compile_locator_hint,
            graph_thread_id=compile_graph_thread_id,
        )
        _write_json(draft_bundle_path, compiled.get("draft_bundle") if isinstance(compiled.get("draft_bundle"), dict) else {})
        _write_json(draft_v2_path, compiled.get("draft_bundle_v2") if isinstance(compiled.get("draft_bundle_v2"), dict) else {})
        _write_json(validation_path, compiled.get("validation_result_v2") if isinstance(compiled.get("validation_result_v2"), dict) else {})
        _write_json(repair_plan_path, compiled.get("repair_plan_v2") if isinstance(compiled.get("repair_plan_v2"), dict) else {})
        _write_json(graph_state_path, compiled.get("graph_state_v2") if isinstance(compiled.get("graph_state_v2"), dict) else {})
        factual_conformance = compiled.get("factual_conformance") if isinstance(compiled.get("factual_conformance"), dict) else {}
        manifest = build_artifact_manifest(
            topic_identifier=topic_identifier,
            thread_id=active_thread_id,
            task_id=runtime_task_id,
            structured_path=str(cache_path),
            basic_analysis_path=str(cache_dir / "basic_analysis_insight.json"),
            bertopic_path=str(cache_dir / "bertopic_insight.json"),
            agenda_path=str(cache_dir / "agenda_frame_map.json"),
            conflict_path=str(cache_dir / "conflict_map.json"),
            mechanism_path=str(cache_dir / "mechanism_summary.json"),
            utility_path=str(cache_dir / "utility_assessment.json"),
            draft_path=str(draft_bundle_path),
            draft_v2_path=str(draft_v2_path),
            validation_path=str(validation_path),
            repair_plan_path=str(repair_plan_path),
            graph_state_path=str(graph_state_path),
            full_path=str(full_cache_path),
            runtime_path=str(runtime_artifact_path),
            ir_path=str(cache_dir / "report_ir.json"),
            figure_artifacts=structured_payload.get("figure_artifacts") if isinstance(structured_payload.get("figure_artifacts"), list) else [],
            policy_version=str(factual_conformance.get("policy_version") or "policy.v2").strip() or "policy.v2",
            graph_run_id=runtime_task_id,
            previous_manifest=structured_payload.get("artifact_manifest") if isinstance(structured_payload.get("artifact_manifest"), dict) else None,
        )
        structured_payload = attach_report_ir(structured_payload, artifact_manifest=manifest, task_id=runtime_task_id)
        structured_payload.setdefault("metadata", {})
        structured_payload["metadata"]["artifact_manifest"] = manifest.model_dump()
        structured_payload["metadata"]["report_ir_summary"] = summarize_report_ir(structured_payload.get("report_ir") or {})
        structured_payload["meta"] = {**(structured_payload.get("meta") or {}), **structured_payload["metadata"]}
        _write_json(cache_path, structured_payload)
        final_payload = build_full_payload(
            structured_payload,
            str(markdown or "").strip(),
            cache_version=AI_FULL_REPORT_CACHE_VERSION,
            draft_bundle=compiled.get("draft_bundle") if isinstance(compiled.get("draft_bundle"), dict) else {},
            styled_draft_bundle=compiled.get("styled_draft_bundle") if isinstance(compiled.get("styled_draft_bundle"), dict) else {},
            factual_conformance=factual_conformance,
        )
        final_payload["meta"] = dict(final_payload.get("meta") or {})
        final_payload["meta"].update(
            {
                "thread_id": active_thread_id,
                "runtime_task_id": runtime_task_id,
            }
        )
        final_payload["draft_bundle_v2"] = compiled.get("draft_bundle_v2") if isinstance(compiled.get("draft_bundle_v2"), dict) else {}
        final_payload["validation_result_v2"] = compiled.get("validation_result_v2") if isinstance(compiled.get("validation_result_v2"), dict) else {}
        final_payload["repair_plan_v2"] = compiled.get("repair_plan_v2") if isinstance(compiled.get("repair_plan_v2"), dict) else {}
        final_payload["graph_state_v2"] = compiled.get("graph_state_v2") if isinstance(compiled.get("graph_state_v2"), dict) else {}
        final_payload["artifact_manifest"] = manifest.model_dump()
        _write_json(full_cache_path, final_payload)
        _emit(
            event_callback,
            {
                "type": "artifact.ready",
                "phase": "persist",
                "title": "正式缓存已更新",
                "message": "结构化结果和正式文稿缓存均已写入。",
                "payload": {
                    "report_cache_path": str(cache_path),
                    "full_report_cache_path": str(full_cache_path),
                    "report_runtime_artifact": str(runtime_artifact_path),
                },
            },
        )
        return str(full_cache_path)

    tool_round_limits = _resolve_report_tool_round_limits()
    coordinator_tool_round_limit = tool_round_limits["coordinator"]
    subagent_tool_round_limit = tool_round_limits["subagent"]
    lifecycle_tracker: Dict[str, Any] = {
        "tool_calls": [],
        "subagents_started": [],
        "subagents_completed": [],
        "tool_round_counts": {},
        "tool_round_limits": {},
        "topic_label": display_name,
        "runtime_files": runtime_files,
        "task_contract": {
            "topic_identifier": topic_identifier,
            "topic_label": display_name,
            "start": start_text,
            "end": end_text,
            "mode": mode,
            "thread_id": active_thread_id,
        },
    }

    def _coordinator_middleware_factory(agent_name: str) -> List[Any]:
        is_coordinator = agent_name == "report_coordinator"
        return [
            _build_lifecycle_middleware(
                event_callback=event_callback,
                actor_name=agent_name,
                default_phase="interpret" if is_coordinator else _phase_for_subagent(agent_name),
                tracker=lifecycle_tracker,
                task_tool_mode=is_coordinator,
                max_tool_rounds=coordinator_tool_round_limit if is_coordinator else subagent_tool_round_limit,
            )
        ]

    agent_bundle = build_report_deep_agent(
        llm=llm,
        topic_identifier=topic_identifier,
        topic_label=display_name,
        start_text=start_text,
        end_text=end_text,
        mode=mode,
        thread_id=active_thread_id,
        task_id=runtime_task_id,
        skill_assets=skill_assets,
        memory_paths=memory_paths or None,
        runtime_backend=runtime_backend,
        extra_coordinator_tools=[save_structured_report],
        middleware_factory=_coordinator_middleware_factory,
        coordinator_tool_round_limit=coordinator_tool_round_limit,
        subagent_tool_round_limit=subagent_tool_round_limit,
        lifecycle_tracker=lifecycle_tracker,
    )
    agent = agent_bundle["agent"]
    coordinator_runtime_profile = agent_bundle["coordinator_runtime_profile"]
    prompt = agent_bundle["prompt"]
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
            config=build_report_runnable_config(
                thread_id=active_thread_id,
                purpose="deep-report-coordinator",
                task_id=runtime_task_id,
                tags=["report_coordinator", mode],
                metadata={
                    "runtime_diagnostics": build_runtime_diagnostics(
                        purpose="deep-report-coordinator",
                        thread_id=active_thread_id,
                        task_id=runtime_task_id,
                        locator_hint=coordinator_runtime_profile.checkpoint_locator,
                    )
                },
                locator_hint=coordinator_runtime_profile.checkpoint_locator,
            ),
            context=common_context,
            version="v2",
        )

    def _build_interrupt_response(result: Any) -> Dict[str, Any]:
        interrupts = _result_interrupts(result)
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
        return ExplorationTaskResult(
            status="interrupted",
            message="文稿写入前需要人工确认。",
            approvals=approvals,
            structured_payload=_load_current_structured_payload(),
            full_payload=_load_current_full_payload(),
            thread_id=active_thread_id,
        )

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
        result_payload = _result_payload(result)
        runtime_result_files = result_payload.get("files") if isinstance(result_payload, dict) and isinstance(result_payload.get("files"), dict) else {}
        if runtime_result_files:
            latest_runtime_files = runtime_result_files
            lifecycle_tracker["runtime_files"] = latest_runtime_files
        last_diagnostic = _extend_closure_diagnostic(
            _lifecycle_diagnostic(lifecycle_tracker, result),
            files=latest_runtime_files,
            fallback_attempted=fallback_attempted,
        )
        interrupts = _result_interrupts(result)
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
        _ensure_validation_notes_from_claim_checks(latest_runtime_files, topic_label=display_name)
        full_payload = _load_current_full_payload()
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
            return ExplorationTaskResult(
                status="completed",
                message="深度代理执行完成。",
                structured_payload=structured_payload,
                full_payload=full_payload,
                runtime_files=latest_runtime_files,
                thread_id=active_thread_id,
            )

        if structured_payload:
            _emit(
                event_callback,
                {
                    "type": "phase.progress",
                    "phase": "write",
                    "title": "移交可追溯编译图",
                    "message": "结构化结果已保存，后续正式文稿、验证与修复将由确定性编译图继续完成。",
                    "payload": {
                        "thread_id": active_thread_id,
                        "handoff": "traceable_graph_compile",
                    },
                },
            )
            return ExplorationTaskResult(
                status="completed",
                message="深度代理已完成结构化整理，后续将进入可追溯编译图。",
                structured_payload=structured_payload,
                full_payload=full_payload or {},
                runtime_files=latest_runtime_files,
                thread_id=active_thread_id,
            )

        if attempt >= 2 or not structured_payload:
            break

    structured_payload = _load_current_structured_payload()
    full_payload = _load_current_full_payload()
    if structured_payload and full_payload:
        return ExplorationTaskResult(
            status="completed",
            message="深度代理执行完成。",
            structured_payload=structured_payload,
            full_payload=full_payload,
            runtime_files=latest_runtime_files,
            thread_id=active_thread_id,
        )

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
    return ExplorationTaskResult(
        status="failed",
        message=failure_message,
        structured_payload=structured_payload or {},
        full_payload=full_payload or {},
        runtime_files=latest_runtime_files,
        thread_id=active_thread_id,
        diagnostic=last_diagnostic,
    )


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

    display_name = str(topic_label or topic_identifier).strip() or topic_identifier
    active_thread_id = str(thread_id or _default_thread_id(topic_identifier, start_text, end_text)).strip()
    runtime_task_id = str(task_id or f"rp-runtime-{uuid.uuid4().hex[:8]}").strip()
    root_thread_id = f"{runtime_task_id}:root"
    exploration_thread_id = f"{runtime_task_id}:explore"
    compile_thread_id = f"{runtime_task_id}:compile"
    cache_dir = ensure_cache_dir(topic_identifier, start_text, end_text)
    structured_cache_path = cache_dir / REPORT_CACHE_FILENAME

    def _attach_exploration_bundle(
        structured_payload: Dict[str, Any],
        runtime_files: Dict[str, Dict[str, Any]],
        *,
        message: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        structured = dict(structured_payload or {})
        bundle = _bundle_exploration_outputs(
            runtime_files=runtime_files,
            structured_payload=structured,
            mode=mode,
            root_thread_id=root_thread_id,
            exploration_thread_id=exploration_thread_id,
            compile_thread_id=compile_thread_id,
            message=message,
        )
        structured.setdefault("metadata", {})
        structured["metadata"].update(
            {
                "exploration_graph_state": bundle.get("exploration_graph_state") if isinstance(bundle.get("exploration_graph_state"), dict) else {},
                "exploration_manifest": bundle.get("exploration_manifest") if isinstance(bundle.get("exploration_manifest"), dict) else {},
                "gap_summary": bundle.get("gap_summary") if isinstance(bundle.get("gap_summary"), list) else [],
                "todos": bundle.get("todos") if isinstance(bundle.get("todos"), list) else structured.get("metadata", {}).get("todos") or [],
            }
        )
        structured["meta"] = {**(structured.get("meta") if isinstance(structured.get("meta"), dict) else {}), **structured["metadata"]}
        structured["exploration_graph_state"] = _migrate_graph_state(
            structured["metadata"].get("exploration_graph_state") or {}
        )
        structured["exploration_manifest"] = structured["metadata"].get("exploration_manifest") or {}
        structured["gap_summary"] = structured["metadata"].get("gap_summary") or []
        if structured["gap_summary"]:
            _emit_runtime_event(
                event_callback,
                {
                    "type": "exploration.validation.failed",
                    "phase": "exploration",
                    "agent": "exploration_subgraph",
                    "title": "探索产物不完整",
                    "message": f"共有 {len(structured['gap_summary'])} 项探索产物缺失，系统将带缺口继续编译。",
                    "payload": {
                        "gap_summary": structured["gap_summary"],
                        "exploration_manifest": structured["exploration_manifest"],
                    },
                },
            )
        return structured, bundle

    def _resume_structured_payload() -> Dict[str, Any]:
        payload = _load_json(structured_cache_path)
        return payload if _matches_current_run(payload, runtime_task_id=runtime_task_id, thread_id=active_thread_id) else {}

    def _run_exploration(request: Dict[str, Any]) -> Dict[str, Any]:
        # Derive config params from the explicit request dict rather than closure vars.
        # `resume_payload` and `event_callback` remain closure-bound: they are workflow
        # state / runtime callbacks, not request-level config.
        req_topic_id = str(request.get("topic_identifier") or "").strip() or topic_identifier
        req_start = str(request.get("start") or "").strip() or start_text
        req_end = str(request.get("end") or "").strip() or req_start
        req_label = str(request.get("topic_label") or "").strip() or display_name
        req_mode = str(request.get("mode") or "").strip() or mode
        req_thread_id = str(request.get("thread_id") or "").strip() or active_thread_id
        req_task_id = str(request.get("task_id") or "").strip() or runtime_task_id

        if resume_payload is not None:
            structured_payload = _resume_structured_payload()
            if not structured_payload:
                return {
                    "status": "failed",
                    "message": "恢复编译时未找到与当前任务匹配的结构化缓存。",
                    "approvals": [],
                    "structured_payload": {},
                    "full_payload": {},
                    "exploration_bundle": {},
                }
            structured_payload, exploration_bundle = _attach_exploration_bundle(
                structured_payload,
                {},
                message="已从结构化缓存恢复探索结果。",
            )
            return {
                "status": "completed",
                "message": "已从结构化缓存恢复探索结果。",
                "approvals": [],
                "structured_payload": structured_payload,
                "full_payload": {},
                "exploration_bundle": exploration_bundle,
            }

        result = _run_deep_report_exploration_task(
            req_topic_id,
            req_start,
            req_end,
            topic_label=req_label,
            mode=req_mode,
            thread_id=req_thread_id,
            task_id=req_task_id,
            resume_payload=None,
            event_callback=lambda event: _emit_runtime_event(event_callback, event, normalize_exploration=True),
        )
        structured_payload = result.structured_payload if isinstance(result.structured_payload, dict) else {}
        runtime_files = result.runtime_files if isinstance(result.runtime_files, dict) else {}
        exploration_bundle: Dict[str, Any] = {}
        if structured_payload:
            structured_payload, exploration_bundle = _attach_exploration_bundle(
                structured_payload,
                runtime_files,
                message=str(result.message or "探索阶段完成。").strip(),
            )
        output = result.model_dump()
        output["structured_payload"] = structured_payload
        output["exploration_bundle"] = exploration_bundle
        return output

    def _run_compile(structured_payload: Dict[str, Any], exploration_bundle: Dict[str, Any]) -> Dict[str, Any]:
        compile_result = generate_full_report_payload(
            topic_identifier,
            start_text,
            end_text,
            topic_label=display_name,
            regenerate=True,
            structured_payload=structured_payload,
            mode=mode,
            thread_id=active_thread_id,
            task_id=runtime_task_id,
            semantic_review_decision=resume_payload if isinstance(resume_payload, dict) else None,
            event_callback=event_callback,
        )
        payload = dict(compile_result or {})
        payload["exploration_graph_state"] = exploration_bundle.get("exploration_graph_state") if isinstance(exploration_bundle.get("exploration_graph_state"), dict) else {}
        payload["exploration_manifest"] = exploration_bundle.get("exploration_manifest") if isinstance(exploration_bundle.get("exploration_manifest"), dict) else {}
        payload["gap_summary"] = exploration_bundle.get("gap_summary") if isinstance(exploration_bundle.get("gap_summary"), list) else []
        payload["todos"] = exploration_bundle.get("todos") if isinstance(exploration_bundle.get("todos"), list) else []
        if isinstance(payload.get("meta"), dict):
            payload["meta"].update(
                {
                    "exploration_graph_state": payload["exploration_graph_state"],
                    "exploration_manifest": payload["exploration_manifest"],
                    "gap_summary": payload["gap_summary"],
                    "todos": payload["todos"],
                }
            )
        if isinstance(payload.get("metadata"), dict):
            payload["metadata"].update(
                {
                    "exploration_graph_state": payload["exploration_graph_state"],
                    "exploration_manifest": payload["exploration_manifest"],
                    "gap_summary": payload["gap_summary"],
                    "todos": payload["todos"],
                }
            )
        return payload

    def _invoke_deep_agent(request: Dict[str, Any]) -> Dict[str, Any]:
        return _run_exploration(request)

    return run_report_orchestrator_graph(
        request={
            "task_id": runtime_task_id,
            "thread_id": active_thread_id,
            "topic_identifier": topic_identifier,
            "topic_label": display_name,
            "start": start_text,
            "end": end_text,
            "mode": mode,
            "root_thread_id": root_thread_id,
            "exploration_thread_id": exploration_thread_id,
            "compile_thread_id": compile_thread_id,
        },
        root_thread_id=root_thread_id,
        invoke_deep_agent=_invoke_deep_agent,
        run_compile=_run_compile,
        event_callback=event_callback,
    )


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
            if isinstance(cached.get("report_ir"), dict) and isinstance(cached.get("artifact_manifest"), dict):
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
            upgraded = _attach_ir_layers(
                upgraded,
                topic_identifier=topic_identifier,
                cache_dir=cache_dir,
                thread_id=str(((upgraded.get("task") or {}).get("thread_id")) or thread_id or _default_thread_id(topic_identifier, start_text, end_text)).strip(),
                task_id=str(task_id or ((upgraded.get("metadata") or {}).get("runtime_task_id")) or f"rp-runtime-{uuid.uuid4().hex[:8]}").strip(),
            )
            _write_json(cache_path, upgraded)
            return upgraded

    active_thread_id = str(thread_id or _default_thread_id(topic_identifier, start_text, end_text)).strip()
    runtime_task_id = str(task_id or f"rp-runtime-{uuid.uuid4().hex[:8]}").strip()
    common_context, runtime_files, runtime_backend, skill_assets, memory_paths = _prepare_runtime(
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

    normalized_result = NormalizedTaskResult.model_validate(
        normalize_task_payload(
            task_text=f"{display_name} {common_context.get('mode') or ''} 舆情分析",
            topic_identifier=topic_identifier,
            start=start_text,
            end=end_text,
            mode=mode,
            hints_json=json.dumps(
                {
                    "topic": display_name,
                    "task_contract": {
                        "topic_identifier": topic_identifier,
                        "topic_label": display_name,
                        "start": start_text,
                        "end": end_text,
                        "mode": mode,
                        "thread_id": active_thread_id,
                    },
                },
                ensure_ascii=False,
            ),
        )
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/task_contract.json", normalized_result.task_contract.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/task_derivation.json", normalized_result.task_derivation.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/task_derivation_proposal.json", normalized_result.proposal_snapshot)
    _upsert_runtime_json_file(runtime_files, "/workspace/state/normalized_task.json", normalized_result.model_dump())
    persist_task_contract_bundle(
        task_contract=normalized_result.task_contract.model_dump(),
        task_derivation=normalized_result.task_derivation.model_dump(),
        proposal_snapshot=normalized_result.proposal_snapshot,
    )
    retrieval_plan = build_retrieval_plan_payload(
        normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
        intent="overview",
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/retrieval_plan.json", retrieval_plan)
    _upsert_runtime_json_file(
        runtime_files,
        "/workspace/state/dispatch_quality.json",
        {"quality_ledger": ((retrieval_plan.get("result") or {}) if isinstance(retrieval_plan.get("result"), dict) else {}).get("dispatch_quality_ledger") or []},
    )
    retrieval_result = (retrieval_plan.get("result") or {}) if isinstance(retrieval_plan.get("result"), dict) else {}
    dispatch_quality_ledger = retrieval_result.get("dispatch_quality_ledger") if isinstance(retrieval_result.get("dispatch_quality_ledger"), list) else []
    _emit(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "interpret",
            "agent": "retrieval_router",
            "title": "检索路由已确定",
            "message": "已固定本轮 router facets 和 specialist 分派。",
            "payload": {
                "router_facets": retrieval_result.get("router_facets") if isinstance(retrieval_result.get("router_facets"), list) else [],
                "dispatch_targets": [
                    str(item.get("specialist") or "").strip()
                    for item in dispatch_quality_ledger
                    if isinstance(item, dict) and str(item.get("specialist") or "").strip()
                ],
                "dispatch_quality_summary": {
                    "count": len(dispatch_quality_ledger),
                    "contributed_artifacts": sorted(
                        {
                            str(artifact).strip()
                            for item in dispatch_quality_ledger
                            if isinstance(item, dict)
                            for artifact in (item.get("contributed_artifacts") or [])
                            if str(artifact or "").strip()
                        }
                    ),
                },
            },
        },
    )

    todos = _set_todo_status(todos, "retrieval", "running")
    coverage_result = CorpusCoverageResult.model_validate(
        get_corpus_coverage_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            include_samples=True,
            limit=12,
        )
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/corpus_coverage.json", coverage_result.model_dump())

    evidence_result = EvidenceCardPage.model_validate(
        retrieve_evidence_cards_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            intent="overview",
            limit=12,
        )
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/evidence_cards.json", evidence_result.model_dump())
    todos = _set_todo_status(todos, "retrieval", "completed")

    todos = _set_todo_status(todos, "evidence", "completed")
    todos = _set_todo_status(todos, "structure", "running")
    timeline_result = TimelineBuildResult.model_validate(
        build_event_timeline_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            max_nodes=8,
        )
    )
    metric_result = MetricBundleResult.model_validate(
        compute_report_metrics_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            metric_scope="overview",
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
        )
    )
    actor_result = ActorPositionResult.model_validate(
        extract_actor_positions_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            actor_limit=10,
        )
    )
    conflict_result = ClaimActorConflictResult.model_validate(
        build_claim_actor_conflict_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            actor_positions_json=json.dumps([item.model_dump() for item in actor_result.result], ensure_ascii=False),
            timeline_nodes_json=json.dumps([item.model_dump() for item in timeline_result.result], ensure_ascii=False),
        )
    )
    agenda_result = AgendaFrameMapResult.model_validate(
        build_agenda_frame_map_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            actor_positions_json=json.dumps([item.model_dump() for item in actor_result.result], ensure_ascii=False),
            conflict_map_json=json.dumps(conflict_result.result.model_dump(), ensure_ascii=False),
            timeline_nodes_json=json.dumps([item.model_dump() for item in timeline_result.result], ensure_ascii=False),
        )
    )
    discourse_conflict_map = build_discourse_conflict_map_payload(
        normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
        evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
        actor_positions_json=json.dumps([item.model_dump() for item in actor_result.result], ensure_ascii=False),
    )
    mechanism_result = MechanismSummaryResult.model_validate(
        build_mechanism_summary_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            timeline_nodes_json=json.dumps([item.model_dump() for item in timeline_result.result], ensure_ascii=False),
            conflict_map_json=json.dumps(conflict_result.result.model_dump(), ensure_ascii=False),
            metric_refs_json=json.dumps(metric_result.chart_data_refs, ensure_ascii=False),
        )
    )
    risk_result = RiskSignalResult.model_validate(
        detect_risk_signals_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            metric_refs_json=json.dumps(metric_result.chart_data_refs, ensure_ascii=False),
            discourse_conflict_map_json=json.dumps(conflict_result.result.model_dump(), ensure_ascii=False),
            actor_positions_json=json.dumps([item.model_dump() for item in actor_result.result], ensure_ascii=False),
        )
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/timeline_nodes.json", timeline_result.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/metrics_bundle.json", metric_result.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/actor_positions.json", actor_result.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/agenda_frame_map.json", agenda_result.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/conflict_map.json", conflict_result.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/discourse_conflict_map.json", discourse_conflict_map)
    _upsert_runtime_json_file(runtime_files, "/workspace/state/mechanism_summary.json", mechanism_result.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/risk_signals.json", risk_result.model_dump())

    overview_packet = SectionPacketResult.model_validate(
        build_section_packet_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            section_id="overview",
            section_goal="概览当前专题的核心证据与主要判断。",
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            metric_refs_json=json.dumps([item.model_dump() for item in metric_result.result], ensure_ascii=False),
        )
    )
    timeline_packet = SectionPacketResult.model_validate(
        build_section_packet_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            section_id="timeline",
            section_goal="梳理事件演化和关键节点。",
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            metric_refs_json=json.dumps([item.model_dump() for item in metric_result.result], ensure_ascii=False),
        )
    )
    risk_packet = SectionPacketResult.model_validate(
        build_section_packet_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            section_id="risk",
            section_goal="汇总风险信号和触发条件。",
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
            metric_refs_json=json.dumps([item.model_dump() for item in metric_result.result], ensure_ascii=False),
            claim_ids_json=json.dumps([risk.risk_type for risk in risk_result.result], ensure_ascii=False),
        )
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/section_packets/overview.json", overview_packet.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/section_packets/timeline.json", timeline_packet.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/section_packets/risk.json", risk_packet.model_dump())

    claim_checks = ClaimVerificationPage.model_validate(
        verify_claim_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            claims_json=json.dumps(overview_packet.section_packet.claim_candidates[:4], ensure_ascii=False),
            evidence_ids_json=json.dumps([item.model_dump() for item in evidence_result.result], ensure_ascii=False),
        )
    )
    utility_result = UtilityAssessmentResult.model_validate(
        judge_decision_utility_payload(
            normalized_task_json=json.dumps(normalized_result.normalized_task.model_dump(), ensure_ascii=False),
            risk_signals_json=json.dumps([item.model_dump() for item in risk_result.result], ensure_ascii=False),
            recommendation_candidates_json=json.dumps(
                [
                    {
                        "action": f"持续跟踪 {risk.risk_type}",
                        "rationale": risk.spread_condition,
                        "priority": "high" if risk.severity == "high" else "medium",
                    }
                    for risk in risk_result.result[:5]
                ],
                ensure_ascii=False,
            ),
            unresolved_points_json=json.dumps(
                [
                    {
                        "item_id": claim.claim_id,
                        "statement": claim.claim_text,
                        "reason": claim.gap_note or claim.status,
                    }
                    for claim in claim_checks.result
                    if claim.status in {"unsupported", "contradicted"}
                ]
                + [
                    {
                        "item_id": f"packet-{index + 1}",
                        "statement": note,
                        "reason": "section_packet",
                    }
                    for index, note in enumerate(
                        (
                            overview_packet.section_packet.uncertainty_notes
                            + timeline_packet.section_packet.uncertainty_notes
                            + risk_packet.section_packet.uncertainty_notes
                        )[:6]
                    )
                ],
                ensure_ascii=False,
            ),
            agenda_frame_map_json=json.dumps(agenda_result.result.model_dump(), ensure_ascii=False),
            conflict_map_json=json.dumps(conflict_result.result.model_dump(), ensure_ascii=False),
            mechanism_summary_json=json.dumps(mechanism_result.result.model_dump(), ensure_ascii=False),
            actor_positions_json=json.dumps([item.model_dump() for item in actor_result.result], ensure_ascii=False),
        )
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/claim_checks.json", claim_checks.model_dump())
    _upsert_runtime_text_file(
        runtime_files,
        "/workspace/state/validation_notes.md",
        _build_validation_notes_markdown(
            topic_label=display_name,
            claim_checks=claim_checks.model_dump(),
        ),
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/utility_assessment.json", utility_result.model_dump())
    basic_analysis_snapshot = BasicAnalysisSnapshotResult.model_validate(
        get_basic_analysis_snapshot_payload(
            topic_identifier=topic_identifier,
            start=start_text,
            end=end_text,
            topic_label=display_name,
        )
    )
    basic_analysis_insight = BasicAnalysisInsightResult.model_validate(
        build_basic_analysis_insight_payload(
            snapshot_json=json.dumps(basic_analysis_snapshot.result.model_dump(), ensure_ascii=False),
        )
    )
    bertopic_snapshot = BertopicSnapshotResult.model_validate(
        get_bertopic_snapshot_payload(
            topic_identifier=topic_identifier,
            start=start_text,
            end=end_text,
            topic_label=display_name,
        )
    )
    bertopic_insight = BertopicInsightResult.model_validate(
        build_bertopic_insight_payload(
            snapshot_json=json.dumps(bertopic_snapshot.result.model_dump(), ensure_ascii=False),
        )
    )
    _upsert_runtime_json_file(runtime_files, "/workspace/state/basic_analysis_snapshot.json", basic_analysis_snapshot.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/basic_analysis_insight.json", basic_analysis_insight.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/bertopic_snapshot.json", bertopic_snapshot.model_dump())
    _upsert_runtime_json_file(runtime_files, "/workspace/state/bertopic_insight.json", bertopic_insight.model_dump())
    _emit(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "review",
            "agent": "decision_utility_judge",
            "title": "决策效用已更新",
            "message": f"当前裁决为 {str(utility_result.result.decision or '').strip() or 'pass'}。",
            "payload": {
                "utility_decision": str(utility_result.result.decision or "").strip(),
                "missing_dimensions": list(utility_result.result.missing_dimensions or []),
                "fallback_trace": [item.model_dump() for item in utility_result.result.fallback_trace],
                "next_action": str(utility_result.result.next_action or "").strip(),
            },
        },
    )
    todos = _set_todo_status(todos, "structure", "completed")
    todos = _set_todo_status(todos, "writing", "running")

    citations = []
    for index, card in enumerate(evidence_result.result[:20], start=1):
        citations.append(
            {
                "citation_id": f"C{index}",
                "title": card.title,
                "url": card.url,
                "published_at": card.published_at,
                "platform": card.platform,
                "snippet": card.snippet,
                "source_type": "evidence_card",
            }
        )
    citation_index = {card.evidence_id: f"C{idx}" for idx, card in enumerate(evidence_result.result[:20], start=1)}

    structured_seed = {
        "task": {
            "topic_identifier": topic_identifier,
            "topic_label": display_name,
            "start": start_text,
            "end": end_text,
            "mode": mode,
            "thread_id": active_thread_id,
        },
        "conclusion": {
            "executive_summary": "；".join(
                [item for item in [
                    f"当前任务覆盖到 {coverage_result.coverage.matched_count} 条原始记录。",
                    f"已整理 {len(evidence_result.result)} 张证据卡。",
                    f"识别到 {len(actor_result.result)} 个主体和 {len(risk_result.result)} 个风险信号。",
                ] if item]
            ),
            "key_findings": [
                f"时间线共形成 {len(timeline_result.result)} 个节点。",
                f"平台覆盖 {len(metric_result.coverage.platform_counts)} 个主要来源。",
                f"章节写作将基于 section packet，而不是直接消费原始命中结果。",
            ],
            "key_risks": [risk.risk_type for risk in risk_result.result[:5]],
            "confidence_label": "中高" if evidence_result.result else "低",
        },
        "timeline": [
            {
                "event_id": node.node_id,
                "date": node.time_label,
                "title": node.summary[:40] or node.node_id,
                "description": node.summary,
                "trigger": "",
                "impact": f"支持证据 {len(node.support_evidence_ids)} 条",
                "citation_ids": [citation_index.get(item_id, "") for item_id in node.support_evidence_ids if citation_index.get(item_id, "")],
                "causal_links": [],
            }
            for node in timeline_result.result
        ],
        "subjects": [
            {
                "subject_id": actor.actor_id,
                "name": actor.name,
                "category": "actor",
                "role": actor.stance,
                "summary": actor.stance_shift,
                "citation_ids": [citation_index.get(item_id, "") for item_id in actor.representative_evidence_ids if citation_index.get(item_id, "")],
            }
            for actor in actor_result.result
        ],
        "stance_matrix": [
            {
                "subject": actor.name,
                "stance": actor.stance,
                "summary": actor.stance_shift,
                "conflict_with": actor.conflict_actor_ids,
                "citation_ids": [citation_index.get(item_id, "") for item_id in actor.representative_evidence_ids if citation_index.get(item_id, "")],
            }
            for actor in actor_result.result
        ],
        "key_evidence": [
            {
                "evidence_id": card.evidence_id,
                "source_id": card.source_id,
                "finding": card.title or card.snippet,
                "subject": "、".join(card.entity_tags[:2]),
                "stance": card.topic_cluster,
                "time_label": str(card.published_at or "")[:10],
                "source_summary": card.snippet,
                "citation_ids": [citation_index.get(card.evidence_id, "")] if citation_index.get(card.evidence_id, "") else [],
                "confidence": "high" if card.confidence >= 0.7 else "medium" if card.confidence >= 0.4 else "low",
            }
            for card in evidence_result.result[:10]
        ],
        "conflict_points": [
            {
                "conflict_id": f"conflict-{index + 1}",
                "title": risk.risk_type,
                "description": risk.spread_condition,
                "subjects": [],
                "citation_ids": [citation_index.get(item_id, "") for item_id in risk.trigger_evidence_ids if citation_index.get(item_id, "")],
            }
            for index, risk in enumerate(risk_result.result[:5])
            if risk.risk_type == "rumor_conflict"
        ],
        "agenda_frame_map": agenda_result.result.model_dump(),
        "conflict_map": conflict_result.result.model_dump(),
        "propagation_features": [
            {
                "feature_id": metric.metric_id,
                "dimension": metric.dimension or "overview",
                "finding": f"{metric.label}={metric.value}",
                "explanation": metric.detail,
                "citation_ids": [],
            }
            for metric in metric_result.result
        ],
        "mechanism_summary": mechanism_result.result.model_dump(),
        "risk_judgement": [
            {
                "risk_id": risk.risk_id,
                "label": risk.risk_type,
                "level": "high" if risk.severity == "high" else "medium" if risk.severity == "medium" else "low",
                "summary": risk.spread_condition,
                "citation_ids": [citation_index.get(item_id, "") for item_id in risk.trigger_evidence_ids if citation_index.get(item_id, "")],
            }
            for risk in risk_result.result
        ],
        "unverified_points": [
            {
                "item_id": claim.claim_id,
                "statement": claim.claim_text,
                "reason": claim.gap_note or claim.status,
                "citation_ids": [citation_index.get(item_id, "") for item_id in claim.support_ids if citation_index.get(item_id, "")],
            }
            for claim in claim_checks.result
            if claim.status in {"unsupported", "contradicted"}
        ] + [
            {
                "item_id": f"packet-{index + 1}",
                "statement": note,
                "reason": "section_packet",
                "citation_ids": [],
            }
            for index, note in enumerate((overview_packet.section_packet.uncertainty_notes + timeline_packet.section_packet.uncertainty_notes + risk_packet.section_packet.uncertainty_notes)[:6])
        ],
        "suggested_actions": [
            {
                "action_id": f"action-{index + 1}",
                "action": f"持续跟踪 {risk.risk_type}",
                "rationale": risk.spread_condition,
                "priority": "high" if risk.severity == "high" else "medium",
                "citation_ids": [citation_index.get(item_id, "") for item_id in risk.trigger_evidence_ids if citation_index.get(item_id, "")],
            }
            for index, risk in enumerate(risk_result.result[:5])
        ],
        "utility_assessment": utility_result.result.model_dump(),
        "basic_analysis_snapshot": basic_analysis_snapshot.result.model_dump(),
        "basic_analysis_insight": basic_analysis_insight.result.model_dump(),
        "citations": citations,
        "bertopic_snapshot": bertopic_snapshot.result.model_dump(),
        "bertopic_insight": bertopic_insight.result.model_dump(),
        "validation_notes": [
            {
                "note_id": f"validation-{index + 1}",
                "category": "fact",
                "severity": "medium" if claim.status in {"contradicted", "unsupported"} else "low",
                "message": f"{claim.claim_text} -> {claim.status}",
                "related_ids": [claim.claim_id],
            }
            for index, claim in enumerate(claim_checks.result[:8])
        ],
        "metadata": {
            "cache_version": REPORT_CACHE_VERSION,
            "generated_at": _utc_now(),
            "thread_id": active_thread_id,
            "runtime_task_id": runtime_task_id,
            "todos": todos,
            "tool_contract_version": "deep-report-v2",
            "state_files": [
        "/workspace/state/task_contract.json",
        "/workspace/state/task_derivation.json",
        "/workspace/state/task_derivation_proposal.json",
        "/workspace/state/normalized_task.json",
                "/workspace/state/retrieval_plan.json",
                "/workspace/state/dispatch_quality.json",
                "/workspace/state/corpus_coverage.json",
                "/workspace/state/evidence_cards.json",
                "/workspace/state/timeline_nodes.json",
                "/workspace/state/metrics_bundle.json",
                "/workspace/state/actor_positions.json",
                "/workspace/state/agenda_frame_map.json",
                "/workspace/state/conflict_map.json",
                "/workspace/state/risk_signals.json",
                "/workspace/state/mechanism_summary.json",
                "/workspace/state/utility_assessment.json",
                "/workspace/state/basic_analysis_snapshot.json",
                "/workspace/state/basic_analysis_insight.json",
                "/workspace/state/bertopic_snapshot.json",
                "/workspace/state/bertopic_insight.json",
                "/workspace/state/claim_checks.json",
                "/workspace/state/discourse_conflict_map.json",
                "/workspace/state/section_packets/overview.json",
                "/workspace/state/section_packets/timeline.json",
                "/workspace/state/section_packets/risk.json",
            ],
        },
    }

    structured = StructuredReport.model_validate(structured_seed).model_dump()
    structured = _hydrate_render_layers(
        structured,
        topic_identifier=topic_identifier,
        topic_label=display_name,
        start_text=start_text,
        end_text=end_text,
    )
    todos = _set_todo_status(todos, "writing", "completed")
    structured["metadata"]["todos"] = todos
    structured = _attach_ir_layers(
        structured,
        topic_identifier=topic_identifier,
        cache_dir=cache_dir,
        thread_id=active_thread_id,
        task_id=runtime_task_id,
    )
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
    semantic_review_decision: Optional[Dict[str, Any]] = None,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip() or start_text
    cache_dir = ensure_cache_dir(topic_identifier, start_text, end_text)
    cache_path = cache_dir / AI_FULL_REPORT_CACHE_FILENAME
    draft_path = cache_dir / "full_report_draft_bundle.json"
    draft_v2_path = cache_dir / "draft_bundle.v2.json"
    validation_path = cache_dir / "validation_result.v2.json"
    repair_plan_path = cache_dir / "repair_plan.v2.json"
    graph_state_path = cache_dir / "graph_state.v2.json"
    review_path = _semantic_review_path(cache_dir)
    active_thread_id = str(thread_id or _default_thread_id(topic_identifier, start_text, end_text)).strip()
    runtime_task_id = str(task_id or f"rp-runtime-{uuid.uuid4().hex[:8]}").strip()
    if cache_path.exists() and not regenerate:
        cached = _load_json(cache_path)
        if (
            int(((cached.get("meta") or {}).get("cache_version") or 0)) == AI_FULL_REPORT_CACHE_VERSION
            and isinstance(cached.get("report_ir"), dict)
            and isinstance(cached.get("artifact_manifest"), dict)
        ):
            return cached
    if isinstance(structured_payload, dict):
        if not isinstance(structured_payload.get("report_ir"), dict):
            raise ValueError("generate_full_report_payload requires structured_payload carrying ReportIR.")
        structured = structured_payload
    else:
        structured = generate_report_payload(
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
    structured = _attach_ir_layers(
        structured,
        topic_identifier=topic_identifier,
        cache_dir=cache_dir,
        thread_id=active_thread_id,
        task_id=runtime_task_id,
        full_cache_exists=True,
    )
    semantic_review = semantic_review_decision if isinstance(semantic_review_decision, dict) else {}
    compile_graph_path = cache_dir / "compile_graph.sqlite"
    compile_graph_thread_id = f"{runtime_task_id}:compile"
    compile_locator_hint = _runtime_locator_hint(
        purpose="deep-report-compile",
        task_id=runtime_task_id,
        sqlite_path=str(compile_graph_path),
    )
    compiled = compile_markdown_artifacts(
        structured,
        allow_review_pending=True,
        event_callback=event_callback,
        checkpointer_path=compile_locator_hint,
        graph_thread_id=compile_graph_thread_id,
        review_decision=semantic_review if semantic_review else None,
    )
    draft_bundle = compiled.get("draft_bundle") if isinstance(compiled.get("draft_bundle"), dict) else {}
    draft_bundle_v2 = compiled.get("draft_bundle_v2") if isinstance(compiled.get("draft_bundle_v2"), dict) else {}
    styled_draft_bundle = compiled.get("styled_draft_bundle") if isinstance(compiled.get("styled_draft_bundle"), dict) else {}
    validation_result_v2 = compiled.get("validation_result_v2") if isinstance(compiled.get("validation_result_v2"), dict) else {}
    repair_plan_v2 = compiled.get("repair_plan_v2") if isinstance(compiled.get("repair_plan_v2"), dict) else {}
    graph_state_v2 = compiled.get("graph_state_v2") if isinstance(compiled.get("graph_state_v2"), dict) else {}
    factual_conformance = compiled.get("factual_conformance") if isinstance(compiled.get("factual_conformance"), dict) else {}
    checkpoint_backend = str(compiled.get("checkpoint_backend") or "").strip()
    checkpoint_locator = str(compiled.get("checkpoint_locator") or compile_locator_hint).strip()
    checkpoint_path = str(compiled.get("checkpoint_path") or "").strip()
    if not draft_bundle:
        raise ValueError("generate_full_report_payload requires DraftBundle before compiling final markdown.")
    _write_json(draft_path, draft_bundle)
    _write_json(draft_v2_path, draft_bundle_v2)
    _write_json(validation_path, validation_result_v2)
    _write_json(repair_plan_path, repair_plan_v2)
    _write_json(graph_state_path, graph_state_v2)
    requires_review = bool(compiled.get("review_required")) and not semantic_review
    manifest = build_artifact_manifest(
        topic_identifier=topic_identifier,
        thread_id=active_thread_id,
        task_id=runtime_task_id,
        structured_path=str(cache_dir / REPORT_CACHE_FILENAME),
        basic_analysis_path=str(cache_dir / "basic_analysis_insight.json"),
        bertopic_path=str(cache_dir / "bertopic_insight.json"),
        agenda_path=str(cache_dir / "agenda_frame_map.json"),
        conflict_path=str(cache_dir / "conflict_map.json"),
        mechanism_path=str(cache_dir / "mechanism_summary.json"),
        utility_path=str(cache_dir / "utility_assessment.json"),
        draft_path=str(draft_path),
        draft_v2_path=str(draft_v2_path),
        validation_path=str(validation_path),
        repair_plan_path=str(repair_plan_path),
        graph_state_path=str(graph_state_path),
        full_path=str(cache_path) if not requires_review else "",
        approval_path=str(review_path) if requires_review or semantic_review else "",
        ir_path=str(cache_dir / "report_ir.json"),
        figure_artifacts=structured.get("figure_artifacts") if isinstance(structured.get("figure_artifacts"), list) else [],
        policy_version=str(factual_conformance.get("policy_version") or "policy.v2").strip() or "policy.v2",
        graph_run_id=runtime_task_id,
        previous_manifest=structured.get("artifact_manifest") if isinstance(structured.get("artifact_manifest"), dict) else None,
    )
    structured = attach_report_ir(structured, artifact_manifest=manifest, task_id=runtime_task_id)
    structured.setdefault("metadata", {})
    structured["metadata"]["cache_version"] = REPORT_CACHE_VERSION
    structured["metadata"]["artifact_manifest"] = manifest.model_dump()
    structured["metadata"]["report_ir_summary"] = summarize_report_ir(structured.get("report_ir") or {})
    structured["meta"] = {**(structured.get("meta") or {}), **structured["metadata"]}
    _write_json(cache_dir / REPORT_CACHE_FILENAME, structured)
    if requires_review:
        graph_interrupts = compiled.get("interrupts") if isinstance(compiled.get("interrupts"), list) else []
        interrupt_payload = _build_semantic_review_payload(
            thread_id=active_thread_id,
            task_id=runtime_task_id,
            compiled=compiled,
            artifact_manifest=manifest.model_dump(),
        )
        approvals: List[Dict[str, Any]] = []
        for index, interrupt in enumerate(graph_interrupts or []):
            if not isinstance(interrupt, dict):
                continue
            interrupt_id = str(interrupt.get("interrupt_id") or f"graph-interrupt:{runtime_task_id}:{index}").strip() or f"graph-interrupt:{runtime_task_id}:{index}"
            interrupt_value = interrupt.get("value") if isinstance(interrupt.get("value"), dict) else {}
            markdown_preview = str(interrupt_value.get("markdown_preview") or compiled.get("markdown") or "").strip()
            approvals.append(
                GraphApprovalRecord(
                    approval_id=f"{interrupt_id}:{index}",
                    interrupt_id=interrupt_id,
                    decision_index=0,
                    title=str(interrupt_value.get("title") or "语义边界确认").strip(),
                    summary=str(interrupt_value.get("summary") or "正式文稿包含需要人工确认的语义越界，确认后才能写入正式缓存。").strip(),
                    allowed_decisions=list(interrupt_value.get("allowed_decisions") or ["approve", "edit", "reject"]),
                    action={
                        "markdown_preview": markdown_preview[:1600],
                        "artifact_path": str(review_path),
                        "tool_args": {
                            "markdown": markdown_preview,
                            "policy_version": str(factual_conformance.get("policy_version") or "policy.v2").strip() or "policy.v2",
                            "graph_thread_id": compile_graph_thread_id,
                            "checkpoint_backend": checkpoint_backend,
                            "checkpoint_locator": checkpoint_locator,
                            "checkpoint_path": checkpoint_path,
                        },
                        "graph_interrupt": {"interrupt_id": interrupt_id, "value": interrupt_value},
                        "semantic_interrupt": interrupt_payload.model_dump(),
                    },
                ).model_dump()
            )
        if not approvals:
            interrupt_id = f"graph-interrupt:{runtime_task_id}:0"
            approvals.append(
                GraphApprovalRecord(
                    approval_id=f"{interrupt_id}:0",
                    interrupt_id=interrupt_id,
                    decision_index=0,
                    title="语义边界确认",
                    summary="正式文稿包含需要人工确认的语义越界，确认后才能写入正式缓存。",
                    allowed_decisions=["approve", "edit", "reject"],
                    action={
                        "markdown_preview": str(compiled.get("markdown") or "").strip()[:1600],
                        "artifact_path": str(review_path),
                        "tool_args": {
                            "markdown": str(compiled.get("markdown") or "").strip(),
                            "policy_version": str(factual_conformance.get("policy_version") or "policy.v2").strip() or "policy.v2",
                            "graph_thread_id": compile_graph_thread_id,
                            "checkpoint_backend": checkpoint_backend,
                            "checkpoint_locator": checkpoint_locator,
                            "checkpoint_path": checkpoint_path,
                        },
                        "graph_interrupt": {"interrupt_id": interrupt_id, "value": {}},
                        "semantic_interrupt": interrupt_payload.model_dump(),
                    },
                ).model_dump()
            )
        approval_records = _append_approval_record(
            [],
            approval_id=f"semantic-review:{runtime_task_id}",
            interrupt_id=str((approvals[0] or {}).get("interrupt_id") or f"semantic-review:{runtime_task_id}").strip()
            or f"semantic-review:{runtime_task_id}",
            decision="pending",
            policy_version=interrupt_payload.policy_version,
            artifact_refs=interrupt_payload.artifact_ids,
            offending_unit_ids=interrupt_payload.offending_unit_ids,
            approved_deltas=[item.model_dump() if hasattr(item, "model_dump") else item for item in interrupt_payload.semantic_deltas],
            approved_rewrite_ops=interrupt_payload.allowed_rewrite_ops,
            reason="semantic review requested",
        )
        review_record = {
            "status": "waiting_approval",
            "message": "正式文稿触发语义边界审查，等待人工确认。",
            "thread_id": active_thread_id,
            "task_id": runtime_task_id,
            "markdown": str(compiled.get("markdown") or "").strip(),
            "draft_bundle": draft_bundle,
            "draft_bundle_v2": draft_bundle_v2,
            "styled_draft_bundle": styled_draft_bundle,
            "validation_result_v2": validation_result_v2,
            "repair_plan_v2": repair_plan_v2,
            "graph_state_v2": graph_state_v2,
            "factual_conformance": factual_conformance,
            "artifact_manifest": manifest.model_dump(),
            "report_ir_summary": summarize_report_ir(structured.get("report_ir") or {}),
            "semantic_interrupt": interrupt_payload.model_dump(),
            "graph_interrupts": graph_interrupts,
            "approval_records": approval_records,
        }
        _write_json(review_path, review_record)
        return {
            **review_record,
            "approvals": approvals,
        }
    review_record = _load_json(review_path, {}) if review_path.exists() else {}
    approved_markdown = str(compiled.get("markdown") or "").strip()
    if semantic_review:
        edited_action = semantic_review.get("edited_action") if isinstance(semantic_review.get("edited_action"), dict) else {}
        approved_markdown = str(edited_action.get("markdown") or review_record.get("markdown") or approved_markdown).strip()
    markdown = approved_markdown
    full_payload = build_full_payload(
        structured,
        markdown,
        cache_version=AI_FULL_REPORT_CACHE_VERSION,
        draft_bundle=draft_bundle,
        styled_draft_bundle=styled_draft_bundle,
        factual_conformance=factual_conformance,
    )
    full_payload["draft_bundle_v2"] = draft_bundle_v2
    full_payload["validation_result_v2"] = validation_result_v2
    full_payload["repair_plan_v2"] = repair_plan_v2
    full_payload["graph_state_v2"] = graph_state_v2
    full_payload["meta"] = dict(full_payload.get("meta") or {})
    full_payload["meta"].update(
        {
            "thread_id": active_thread_id,
            "runtime_task_id": runtime_task_id,
            **(
                {
                    "semantic_review": {
                        "decision": str(semantic_review.get("decision") or "").strip(),
                        "policy_version": str(factual_conformance.get("policy_version") or "policy.v2").strip() or "policy.v2",
                        "approved_at": _utc_now(),
                    }
                }
                if semantic_review
                else {}
            ),
        }
    )
    full_payload["artifact_manifest"] = manifest.model_dump()
    if semantic_review:
        semantic_interrupt = review_record.get("semantic_interrupt") if isinstance(review_record.get("semantic_interrupt"), dict) else {}
        approval_records = _append_approval_record(
            review_record.get("approval_records") if isinstance(review_record.get("approval_records"), list) else [],
            approval_id=f"semantic-review:{runtime_task_id}",
            interrupt_id=f"semantic-review:{runtime_task_id}",
            decision=str(semantic_review.get("decision") or "").strip() or "approve",
            policy_version=str(factual_conformance.get("policy_version") or "policy.v2").strip() or "policy.v2",
            artifact_refs=[
                str(item).strip()
                for item in (
                    semantic_interrupt.get("artifact_ids")
                    if isinstance(semantic_interrupt.get("artifact_ids"), list)
                    else []
                )
                if str(item or "").strip()
            ],
            offending_unit_ids=[
                str(item).strip()
                for item in (
                    semantic_interrupt.get("offending_unit_ids")
                    if isinstance(semantic_interrupt.get("offending_unit_ids"), list)
                    else []
                )
                if str(item or "").strip()
            ],
            approved_deltas=[
                item
                for item in (
                    semantic_interrupt.get("semantic_deltas")
                    if isinstance(semantic_interrupt.get("semantic_deltas"), list)
                    else []
                )
                if isinstance(item, dict)
            ],
            approved_rewrite_ops=[
                str(item).strip()
                for item in (
                    semantic_interrupt.get("allowed_rewrite_ops")
                    if isinstance(semantic_interrupt.get("allowed_rewrite_ops"), list)
                    else []
                )
                if str(item or "").strip()
            ],
            reason="semantic review resolved",
        )
        review_record = {
            **review_record,
            "status": "resolved",
            "approved_markdown": approved_markdown,
            "approval_records": approval_records,
        }
        _write_json(review_path, review_record)
    _write_json(cache_path, full_payload)
    return full_payload
