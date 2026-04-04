from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from langchain.agents.structured_output import AutoStrategy
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ...utils.ai import build_langchain_chat_model, call_langchain_chat
from ...utils.setting.paths import get_data_root
from ..agent_runtime import ensure_langchain_uuid_compat
from .assets import RUNTIME_STORE, build_artifacts_root, build_runtime_assets, ensure_memory_seed
from .deterministic import build_base_context, build_workspace_files, ensure_cache_dir
from .presenter import build_full_payload, render_markdown
from .schemas import (
    DraftDocument,
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
REPORT_CACHE_VERSION = 1
AI_FULL_REPORT_CACHE_FILENAME = "ai_full_report_payload.json"
AI_FULL_REPORT_CACHE_VERSION = 8
DEEP_AGENT_CHECKPOINTER = InMemorySaver()
_NAMESPACE_COMPONENT = re.compile(r"[^A-Za-z0-9._@:+~-]+")

SPECIALIST_SKILLS = {
    "retrieval_router": ["retrieval-router-rules"],
    "evidence_organizer": ["evidence-source-credibility"],
    "timeline_analyst": ["timeline-alignment-slicing"],
    "stance_conflict": ["subject-stance-merging"],
    "propagation_analyst": ["propagation-explanation-framework", "chart-interpretation-guidelines"],
    "validator": ["quality-validation-backlink"],
}


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


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
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            task="report",
            model_role="report",
            temperature=0.2,
            max_tokens=2800,
        )
    )
    return str(text or "").strip()


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


def _build_todos() -> List[Dict[str, Any]]:
    return [
        {"id": "scope", "label": "范围确认", "status": "completed"},
        {"id": "retrieval", "label": "检索路由", "status": "pending"},
        {"id": "evidence", "label": "证据整理", "status": "pending"},
        {"id": "structure", "label": "结构分析", "status": "pending"},
        {"id": "writing", "label": "文稿生成", "status": "pending"},
        {"id": "validation", "label": "质量校验", "status": "pending"},
        {"id": "persist", "label": "审批与落盘", "status": "pending"},
    ]


def _set_todo_status(todos: List[Dict[str, Any]], todo_id: str, status: str) -> List[Dict[str, Any]]:
    output = []
    for item in todos:
        row = dict(item)
        if row.get("id") == todo_id:
            row["status"] = status
        output.append(row)
    return output


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
    llm, _client_cfg = build_langchain_chat_model(task="report", model_role="report", temperature=0.2, max_tokens=2200)
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


def _build_subagents(tools: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "name": "retrieval_router",
            "description": "负责选择检索路径、梳理优先问题，并把结果写入 /workspace/state/retrieval_plan.md。",
            "system_prompt": (
                "你是检索路由代理。请先阅读 /workspace/base_context.json 和 /workspace/summary.md，"
                "决定应优先走哪些检索路径、要查哪些问题。把结论写入 /workspace/state/retrieval_plan.md，"
                "并返回简短总结。"
            ),
            "tools": tools,
            "skills": ["/skills/retrieval-router-rules/"],
        },
        {
            "name": "evidence_organizer",
            "description": "负责清洗检索结果、去重并整理证据块，写入 /workspace/state/evidence_bundle.md。",
            "system_prompt": (
                "你是证据整理代理。请读取 /workspace/base_context.json 和 /workspace/state/retrieval_plan.md，"
                "必要时调用检索工具，压缩出统一的证据块、来源摘要和引用索引。"
                "把整理结果写入 /workspace/state/evidence_bundle.md，并返回摘要。"
            ),
            "tools": tools,
            "skills": ["/skills/evidence-source-credibility/"],
        },
        {
            "name": "timeline_analyst",
            "description": "负责构建事件时间线、触发机制和因果链，写入 /workspace/state/timeline_bundle.md。",
            "system_prompt": (
                "你是时间线与因果链代理。请根据已有证据梳理事件顺序、关键触发因素和影响，"
                "把结果写入 /workspace/state/timeline_bundle.md，并返回简短总结。"
            ),
            "tools": tools,
            "skills": ["/skills/timeline-alignment-slicing/"],
        },
        {
            "name": "stance_conflict",
            "description": "负责识别主体、立场矩阵和冲突点，写入 /workspace/state/stance_bundle.md。",
            "system_prompt": (
                "你是立场冲突代理。请整理主体列表、立场归并和冲突结构，"
                "把结果写入 /workspace/state/stance_bundle.md，并返回简短总结。"
            ),
            "tools": tools,
            "skills": ["/skills/subject-stance-merging/"],
        },
        {
            "name": "propagation_analyst",
            "description": "负责解释传播规模、扩散节奏、平台差异和关键影响点，写入 /workspace/state/propagation_bundle.md。",
            "system_prompt": (
                "你是传播结构代理。请结合已有证据与分析结果，解释传播特征、平台差异和风险外溢，"
                "把结果写入 /workspace/state/propagation_bundle.md，并返回简短总结。"
            ),
            "tools": tools,
            "skills": ["/skills/propagation-explanation-framework/", "/skills/chart-interpretation-guidelines/"],
        },
        {
            "name": "writer",
            "description": "负责根据结构化对象生成正式 Markdown 草稿，写入 /workspace/state/report_draft.md。",
            "system_prompt": (
                "你是写作代理。请在结构已经确定后，根据 /workspace/state/structured_report.json 生成正式 Markdown 草稿。"
                "不要暴露内部字段名，把草稿写入 /workspace/state/report_draft.md，并返回简短总结。"
            ),
            "tools": [],
            "skills": ["/skills/report-writing-framework/"],
        },
        {
            "name": "validator",
            "description": "负责检查事实一致性、时间错位和主体混淆，写入 /workspace/state/validation_notes.md。",
            "system_prompt": (
                "你是校验代理。请读取结构化对象和草稿，重点检查无证据判断、时间错位和跨主体混淆。"
                "把校验意见写入 /workspace/state/validation_notes.md，并返回简短总结。"
            ),
            "tools": [],
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
    llm, _client_cfg = build_langchain_chat_model(task="report", model_role="report", temperature=0.2, max_tokens=2600)
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
        output["meta"] = output["metadata"]
        _write_json(cache_path, output)
        runtime_files["/workspace/state/structured_report.json"] = {
            "content": json.dumps(output, ensure_ascii=False, indent=2).split("\n")
        }
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
    def save_structured_report(payload_json: str) -> str:
        """验证并写入结构化报告对象。payload_json 必须是完整 JSON 字符串。"""
        payload = _parse_json_object(payload_json)
        if not payload:
            raise ValueError("payload_json 不是有效的 JSON 对象。")
        _persist_structured_report(payload, source="tool")
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
    agent = create_deep_agent(
        model=llm,
        tools=agent_tools,
        system_prompt=(
            "你是舆情报告总控代理。你的职责是规划任务、调用合适的子代理、整理结构化结果，并在审批通过后写入正式文稿。"
            "你不能跳过证据回链，也不能在没有结构化对象的情况下直接写正式文稿。"
            "你必须优先使用 task 工具委派给专业子代理，而不是自己直接完成所有分析。"
            "除非因为 human-in-the-loop 中断等待审批，否则在 save_structured_report 和 overwrite_report_cache 成功前，你不能结束本次运行。"
        ),
        subagents=_build_subagents(core_tools),
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
        "请先使用 write_todos 建立任务清单，然后完成以下流程：\n"
        "1. 使用 task 工具委派 retrieval_router、evidence_organizer、timeline_analyst、stance_conflict、propagation_analyst。\n"
        "2. 读取这些子代理写入 /workspace/state/ 下的结果，汇总成完整结构化报告对象。\n"
        "3. 调用 save_structured_report 保存结构化对象，参数 payload_json 必须是完整 JSON 字符串。对象必须包含：task、conclusion、timeline、subjects、stance_matrix、"
        "key_evidence、conflict_points、propagation_features、risk_judgement、unverified_points、suggested_actions、citations、validation_notes。\n"
        "4. 使用 writer 子代理基于 /workspace/state/structured_report.json 生成正式 Markdown 草稿，并写入 /workspace/state/report_draft.md。\n"
        "5. 使用 validator 子代理检查草稿与结构化对象，并在必要时改写 /workspace/state/report_draft.md。\n"
        "6. 读取最终草稿，调用 write_final_report，再调用 overwrite_report_cache。\n"
        "所有关键判断都要尽量带 citation_ids；如果证据不足，请进入 unverified_points。"
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
    for attempt in range(3):
        result = _invoke_once(pending_input)
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        if interrupts:
            return _build_interrupt_response(result)

        structured_payload = _load_current_structured_payload()
        full_payload = _load_current_full_payload()
        if not structured_payload:
            structured_candidate = _extract_structured_response(result)
            if structured_candidate:
                structured_payload = _persist_structured_report(structured_candidate, source="structured_response")

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
            _emit(
                event_callback,
                {
                    "type": "phase.progress",
                    "phase": "write",
                    "title": "补写结构化结果",
                    "message": "代理尚未保存本次结构化结果，正在要求其继续完成结构化输出。",
                    "payload": {"thread_id": active_thread_id, "attempt": attempt + 2},
                },
            )
            pending_input = {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "你尚未把本次任务的结构化结果保存为当前运行产物。"
                            "请读取工作区已有内容，立即产出完整结构化对象，并调用 save_structured_report。"
                            "调用时请把完整 JSON 放进 payload_json 字符串参数。"
                            "不要直接结束，也不要只输出自然语言。"
                        ),
                    }
                ]
            }
            continue

        _emit(
            event_callback,
            {
                "type": "phase.progress",
                "phase": "persist",
                "title": "补写正式文稿",
                "message": "结构化结果已存在，但正式文稿尚未完成写入，正在要求代理继续执行写入流程。",
                "payload": {"thread_id": active_thread_id, "attempt": attempt + 2},
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
            ]
        }

    return {
        "status": "completed",
        "message": "深度代理执行完成。",
        "approvals": [],
        "structured_payload": _load_current_structured_payload(),
        "full_payload": _load_current_full_payload(),
        "thread_id": active_thread_id,
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
    markdown_prompt = (
        "请把下面的结构化对象渲染为正式 Markdown 文稿，保持条理清晰，适合直接展示给业务用户：\n"
        f"{json.dumps(structured, ensure_ascii=False, indent=2)}"
    )
    markdown = _call_writer_markdown(markdown_prompt)
    if not markdown:
        markdown = render_markdown(structured)
    draft = DraftDocument(title=str(topic_label or topic_identifier).strip() or topic_identifier, subtitle="结构化研判文稿", markdown=markdown)
    full_payload = build_full_payload(structured, draft.markdown, cache_version=AI_FULL_REPORT_CACHE_VERSION)
    _write_json(cache_path, full_payload)
    return full_payload
