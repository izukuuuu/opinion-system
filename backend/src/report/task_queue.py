"""Persistent queue and event log for report generation tasks."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from filelock import FileLock

from ..utils.setting.paths import get_data_root

LOGGER = logging.getLogger(__name__)

STATE_ROOT = get_data_root() / "_report"
TASK_STATE_DIR = STATE_ROOT / "tasks"
WORKER_STATUS_PATH = STATE_ROOT / "worker.json"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
AGENT_DEFS = [
    ("researcher", "Researcher"),
    ("interpreter", "Interpreter"),
    ("theme_analyst", "Theme Analyst"),
    ("integrator", "Integrator"),
    ("writer", "Writer"),
    ("reviser", "Reviser"),
    ("reviewer", "Reviewer"),
]
PHASE_LABELS = {
    "prepare": "准备数据",
    "analyze": "基础分析",
    "explain": "总体解读",
    "interpret": "综合研判",
    "write": "报告编排",
    "review": "复核裁判",
    "persist": "写入结果",
    "completed": "已完成",
    "failed": "已失败",
    "cancelled": "已取消",
}


def create_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    topic_identifier = str(payload.get("topic_identifier") or "").strip()
    topic = str(payload.get("topic") or "").strip()
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip() or start
    mode = str(payload.get("mode") or "fast").strip().lower() or "fast"
    if mode not in {"fast", "research"}:
        raise ValueError("mode 仅支持 fast 或 research")
    if not topic_identifier or not topic or not start:
        raise ValueError("创建报告任务缺少必要字段")

    now = _utc_now()
    task = {
        "id": _new_task_id(),
        "topic": topic,
        "topic_identifier": topic_identifier,
        "start": start,
        "end": end,
        "mode": mode,
        "status": "queued",
        "phase": "prepare",
        "percentage": 0,
        "message": "等待报告 worker 接单。",
        "cancel_requested": False,
        "worker_pid": 0,
        "child_pid": 0,
        "error": "",
        "request": {
            "topic": topic,
            "topic_identifier": topic_identifier,
            "start": start,
            "end": end,
            "mode": mode,
            "project": str(payload.get("project") or "").strip(),
            "dataset_id": str(payload.get("dataset_id") or "").strip(),
            "aliases": [
                str(item).strip()
                for item in (payload.get("aliases") or [])
                if str(item or "").strip()
            ],
        },
        "agents": _initial_agents(),
        "trust": _initial_trust(),
        "artifacts": {
            "report_ready": False,
            "report_cache_path": "",
            "report_title": "",
            "full_report_ready": False,
            "full_report_cache_path": "",
            "full_report_title": "",
            "view": {
                "topic": topic,
                "topic_identifier": topic_identifier,
                "start": start,
                "end": end,
            },
        },
        "event_seq": 0,
        "event_count": 0,
        "created_at": now,
        "updated_at": now,
        "started_at": "",
        "finished_at": "",
    }
    _save_task(task)
    append_event(
        task["id"],
        event_type="task.created",
        phase="prepare",
        title="任务已创建",
        message="报告任务已入队，等待 worker 执行。",
    )
    return get_task(task["id"])


def list_tasks(*, topic: str = "", status: str = "", limit: int = 50) -> Dict[str, Any]:
    worker = load_worker_status()
    _reconcile_orphaned_running_tasks(worker)
    tasks = _load_all_tasks()
    if topic:
        tasks = [
            item
            for item in tasks
            if str(item.get("topic_identifier") or "") == topic
            or str(item.get("topic") or "") == topic
        ]
    if status:
        tasks = [item for item in tasks if str(item.get("status") or "") == status]
    tasks.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    sliced = [attach_recent_events(item, limit=20) for item in tasks[: max(limit, 1)]]
    return {"tasks": sliced, "summary": _summarise_tasks(sliced), "worker": worker}


def get_task(task_id: str) -> Dict[str, Any]:
    task = _load_task(task_id)
    if not task:
        raise LookupError("未找到指定的报告任务")
    return attach_recent_events(task, limit=80)


def find_existing_task(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    mode: str,
    statuses: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    return find_latest_task(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        mode=mode,
        statuses=statuses or ["queued", "running"],
    )


def find_latest_task(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    mode: Optional[str] = None,
    statuses: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    desired_statuses = set(statuses or [])
    matches = []
    for task in _load_all_tasks():
        if str(task.get("topic_identifier") or "") != topic_identifier:
            continue
        if str(task.get("start") or "") != start:
            continue
        if str(task.get("end") or "") != end:
            continue
        if mode is not None and str(task.get("mode") or "fast") != str(mode):
            continue
        if desired_statuses and str(task.get("status") or "") not in desired_statuses:
            continue
        matches.append(task)
    if not matches:
        return None
    matches.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return attach_recent_events(matches[0], limit=40)


def attach_recent_events(task: Dict[str, Any], *, limit: int = 60) -> Dict[str, Any]:
    payload = dict(task or {})
    payload["recent_events"] = tail_events(str(payload.get("id") or ""), limit=limit)
    return payload


def tail_events(task_id: str, *, limit: int = 60) -> List[Dict[str, Any]]:
    events = load_events_since(task_id, 0)
    return events[-max(limit, 1):]


def load_events_since(task_id: str, since_id: int) -> List[Dict[str, Any]]:
    path = task_events_path(task_id)
    if not path.exists():
        return []
    results: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                event_id = _safe_int((payload or {}).get("event_id"), 0)
                if isinstance(payload, dict) and event_id > since_id:
                    results.append(payload)
    except Exception:
        return []
    return results


def cancel_task(task_id: str) -> Dict[str, Any]:
    task = _load_task(task_id)
    if not task:
        raise LookupError("未找到指定的报告任务")
    status = str(task.get("status") or "")
    if status == "queued":
        return _mutate_task_with_event(
            task_id,
            mutate=lambda current: _apply_terminal_state(
                current,
                status="cancelled",
                phase="cancelled",
                message="任务已在排队阶段取消。",
                error="",
            ),
            event_type="task.cancelled",
            phase="cancelled",
            title="任务已取消",
            message="任务已在排队阶段取消。",
        )
    if status != "running":
        raise ValueError("当前任务状态不支持取消")
    return _mutate_task_with_event(
        task_id,
        mutate=lambda current: current.update(
            {
                "cancel_requested": True,
                "message": "已请求取消，等待 worker 安全停止。",
            }
        ),
        event_type="phase.progress",
        phase=str(task.get("phase") or "prepare"),
        title="收到取消请求",
        message="已请求取消，等待 worker 安全停止。",
    )


def retry_task(task_id: str) -> Dict[str, Any]:
    task = get_task(task_id)
    request = dict(task.get("request") or {})
    request.setdefault("topic", task.get("topic"))
    request.setdefault("topic_identifier", task.get("topic_identifier"))
    request.setdefault("start", task.get("start"))
    request.setdefault("end", task.get("end"))
    request.setdefault("mode", task.get("mode"))
    retried = create_task(request)
    append_event(
        task_id,
        event_type="phase.progress",
        phase=str(task.get("phase") or "completed"),
        title="已创建重试任务",
        message=f"已创建重试任务 {retried['id']}。",
        payload={"retry_task_id": retried["id"]},
    )
    return retried


def should_cancel(task_id: str) -> bool:
    task = _load_task(task_id)
    return bool(task and task.get("cancel_requested"))


def reserve_next_task() -> Optional[Dict[str, Any]]:
    queued = sorted(
        (item for item in _load_all_tasks() if str(item.get("status") or "") == "queued"),
        key=lambda item: item.get("created_at") or "",
    )
    if not queued:
        return None
    task_id = str(queued[0].get("id") or "")
    if not task_id:
        return None
    try:
        return mark_task_started(
            task_id,
            phase="prepare",
            percentage=1,
            message="worker 已接单，准备检查基础数据。",
        )
    except ValueError:
        return None


def ensure_worker_running() -> Dict[str, Any]:
    _ensure_state_dirs()
    worker_lock = FileLock(str(WORKER_STATUS_PATH) + ".lock")
    with worker_lock:
        current = _load_json(WORKER_STATUS_PATH, {})
        pid = _safe_int((current or {}).get("pid"), 0)
        if pid > 0 and _is_process_alive(pid):
            current["running"] = True
            return current

        _reconcile_orphaned_running_tasks({"running": False})
        worker_script = Path(__file__).resolve().parent / "worker.py"
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [sys.executable, str(worker_script)],
            cwd=str(Path(__file__).resolve().parents[2]),
            creationflags=creation_flags,
        )
        status = {
            "pid": process.pid,
            "status": "starting",
            "running": True,
            "current_task_id": "",
            "last_heartbeat": _utc_now(),
            "started_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        _atomic_write_json(WORKER_STATUS_PATH, status)
        return status


def load_worker_status() -> Dict[str, Any]:
    _ensure_state_dirs()
    status = _load_json(WORKER_STATUS_PATH, {})
    if not isinstance(status, dict):
        status = {}
    pid = _safe_int(status.get("pid"), 0)
    running = pid > 0 and _is_process_alive(pid)
    status["running"] = running
    if not running and status.get("status") in {"starting", "idle", "running"}:
        status["status"] = "stopped"
    return status


def write_worker_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_state_dirs()
    status = dict(payload or {})
    status["updated_at"] = _utc_now()
    _atomic_write_json(WORKER_STATUS_PATH, status)
    return status


def mark_task_started(task_id: str, *, phase: str, percentage: int, message: str) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        if str(task.get("status") or "") == "queued":
            task["status"] = "running"
            task["started_at"] = task.get("started_at") or _utc_now()
        elif str(task.get("status") or "") != "running":
            raise ValueError("任务状态不支持启动")
        task["phase"] = phase
        task["percentage"] = max(0, min(100, int(percentage)))
        task["message"] = message
        task["error"] = ""
        task["worker_pid"] = _safe_int(task.get("worker_pid"), 0) or os.getpid()

    return _mutate_task_with_event(
        task_id,
        mutate=_mutate,
        event_type="phase.started",
        phase=phase,
        title=_phase_label(phase),
        message=message,
    )


def mark_task_progress(task_id: str, *, phase: str, percentage: int, message: str) -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: task.update(
            {
                "status": "running",
                "phase": phase,
                "percentage": max(0, min(100, int(percentage))),
                "message": message,
                "worker_pid": _safe_int(task.get("worker_pid"), 0) or os.getpid(),
            }
        ),
        event_type="phase.progress",
        phase=phase,
        title=_phase_label(phase),
        message=message,
    )


def set_worker_pid(task_id: str, worker_pid: int) -> Dict[str, Any]:
    return _update_task(task_id, lambda task: task.update({"worker_pid": _safe_int(worker_pid, 0)}))


def set_child_pid(task_id: str, child_pid: int) -> Dict[str, Any]:
    return _update_task(task_id, lambda task: task.update({"child_pid": _safe_int(child_pid, 0)}))


def mark_agent_started(task_id: str, *, agent: str, phase: str, message: str, title: str = "") -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: _update_agent(
            task,
            agent,
            status="running",
            message=message,
        ),
        event_type="agent.started",
        phase=phase,
        agent=agent,
        title=title or f"{_agent_name(agent)} 已启动",
        message=message,
    )


def append_agent_memo(
    task_id: str,
    *,
    agent: str,
    phase: str,
    message: str,
    title: str = "",
    delta: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: _update_agent(task, agent, status="running", message=message, memo=delta or message),
        event_type="agent.memo",
        phase=phase,
        agent=agent,
        title=title or f"{_agent_name(agent)} 公开备忘录",
        message=message,
        delta=delta,
        payload=payload or {},
    )


def record_tool_call(task_id: str, *, agent: str, phase: str, title: str, message: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: _update_agent(task, agent, tool_call_inc=1, message=message),
        event_type="tool.called",
        phase=phase,
        agent=agent,
        title=title,
        message=message,
        payload=payload,
    )


def record_tool_result(task_id: str, *, agent: str, phase: str, title: str, message: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: _update_agent(task, agent, tool_result_inc=1, message=message),
        event_type="tool.result",
        phase=phase,
        agent=agent,
        title=title,
        message=message,
        payload=payload,
    )


def mark_review_verdict(task_id: str, *, message: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        trust = task.setdefault("trust", _initial_trust())
        trust.update(payload or {})
        issue_count = len(trust.get("issues") or [])
        trust["issue_count"] = issue_count
        trust["requires_manual_review"] = bool(trust.get("requires_manual_review") or issue_count > 0)
        _update_agent(task, "reviewer", status="done", message=message, memo=message)

    return _mutate_task_with_event(
        task_id,
        mutate=_mutate,
        event_type="review.verdict",
        phase="review",
        agent="reviewer",
        title="Reviewer 裁决",
        message=message,
        payload=payload,
    )


def mark_artifact_ready(task_id: str, *, message: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        artifacts = task.setdefault("artifacts", {})
        artifacts.update(payload or {})
        if payload.get("report_cache_path"):
            artifacts["report_ready"] = True
        if payload.get("full_report_cache_path"):
            artifacts["full_report_ready"] = True

    return _mutate_task_with_event(
        task_id,
        mutate=_mutate,
        event_type="artifact.ready",
        phase="persist",
        title="报告产物已写入",
        message=message,
        payload=payload,
    )


def mark_task_completed(task_id: str, *, message: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: _apply_terminal_state(
            task,
            status="completed",
            phase="completed",
            message=message,
            error="",
            payload=payload or {},
        ),
        event_type="task.completed",
        phase="completed",
        title="任务完成",
        message=message,
        payload=payload or {},
    )


def mark_task_failed(task_id: str, message: str) -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: _apply_terminal_state(
            task,
            status="failed",
            phase="failed",
            message=message,
            error=message,
        ),
        event_type="task.failed",
        phase="failed",
        title="任务失败",
        message=message,
    )


def mark_task_cancelled(task_id: str, message: str) -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: _apply_terminal_state(
            task,
            status="cancelled",
            phase="cancelled",
            message=message,
            error="",
        ),
        event_type="task.cancelled",
        phase="cancelled",
        title="任务已取消",
        message=message,
    )


def append_event(
    task_id: str,
    *,
    event_type: str,
    phase: str = "",
    agent: str = "",
    title: str = "",
    message: str = "",
    delta: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _mutate_task_with_event(
        task_id,
        mutate=lambda task: None,
        event_type=event_type,
        phase=phase,
        agent=agent,
        title=title,
        message=message,
        delta=delta,
        payload=payload or {},
    )


def task_state_path(task_id: str) -> Path:
    _ensure_state_dirs()
    return TASK_STATE_DIR / f"{task_id}.json"


def task_events_path(task_id: str) -> Path:
    _ensure_state_dirs()
    return TASK_STATE_DIR / f"{task_id}.events.jsonl"


def _ensure_state_dirs() -> None:
    TASK_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load_all_tasks() -> List[Dict[str, Any]]:
    _ensure_state_dirs()
    items: List[Dict[str, Any]] = []
    for path in TASK_STATE_DIR.glob("*.json"):
        if path.name.endswith(".events.json"):
            continue
        payload = _load_json(path, {})
        if isinstance(payload, dict) and payload.get("id"):
            items.append(payload)
    return items


def _load_task(task_id: str) -> Optional[Dict[str, Any]]:
    payload = _load_json(task_state_path(task_id), {})
    return payload if isinstance(payload, dict) and payload.get("id") else None


def _save_task(task: Dict[str, Any]) -> None:
    path = task_state_path(str(task.get("id") or ""))
    lock = FileLock(str(path) + ".lock")
    with lock:
        task["updated_at"] = _utc_now()
        _atomic_write_json(path, task)


def _update_task(task_id: str, mutate: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    path = task_state_path(task_id)
    lock = FileLock(str(path) + ".lock")
    with lock:
        task = _load_json(path, {})
        if not isinstance(task, dict) or not task.get("id"):
            raise LookupError("未找到指定的报告任务")
        mutate(task)
        task["updated_at"] = _utc_now()
        _atomic_write_json(path, task)
        return task


def _mutate_task_with_event(
    task_id: str,
    *,
    mutate: Callable[[Dict[str, Any]], None],
    event_type: str,
    phase: str = "",
    agent: str = "",
    title: str = "",
    message: str = "",
    delta: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state_path = task_state_path(task_id)
    event_path = task_events_path(task_id)
    lock = FileLock(str(state_path) + ".lock")
    with lock:
        task = _load_json(state_path, {})
        if not isinstance(task, dict) or not task.get("id"):
            raise LookupError("未找到指定的报告任务")
        mutate(task)
        now = _utc_now()
        event_id = _safe_int(task.get("event_seq"), 0) + 1
        task["event_seq"] = event_id
        task["event_count"] = _safe_int(task.get("event_count"), 0) + 1
        task["updated_at"] = now
        event = {
            "event_id": event_id,
            "task_id": task_id,
            "ts": now,
            "type": event_type,
            "phase": phase or str(task.get("phase") or ""),
            "agent": agent,
            "title": title,
            "message": message,
            "delta": delta,
            "payload": payload or {},
        }
        _atomic_write_json(state_path, task)
        _append_jsonl_line(event_path, event)
        return attach_recent_events(task, limit=80)


def _apply_terminal_state(
    task: Dict[str, Any],
    *,
    status: str,
    phase: str,
    message: str,
    error: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    task["status"] = status
    task["phase"] = phase
    task["percentage"] = 100 if status != "failed" else max(_safe_int(task.get("percentage"), 0), 1)
    task["message"] = message
    task["error"] = error
    task["cancel_requested"] = False
    task["child_pid"] = 0
    task["finished_at"] = _utc_now()
    if payload:
        task.setdefault("artifacts", {}).update(payload)


def _update_agent(
    task: Dict[str, Any],
    agent_id: str,
    *,
    status: Optional[str] = None,
    message: str = "",
    memo: str = "",
    tool_call_inc: int = 0,
    tool_result_inc: int = 0,
) -> None:
    agent = _ensure_agent_slot(task, agent_id)
    if status:
        agent["status"] = status
    if message:
        agent["message"] = message
    if memo:
        memos = agent.setdefault("memos", [])
        memos.append({"ts": _utc_now(), "text": memo})
        agent["memos"] = memos[-8:]
    agent["tool_call_count"] = _safe_int(agent.get("tool_call_count"), 0) + max(tool_call_inc, 0)
    agent["tool_result_count"] = _safe_int(agent.get("tool_result_count"), 0) + max(tool_result_inc, 0)
    if status == "running" and not agent.get("started_at"):
        agent["started_at"] = _utc_now()
    agent["updated_at"] = _utc_now()


def _ensure_agent_slot(task: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
    agents = task.setdefault("agents", _initial_agents())
    if isinstance(agents, list):
        for item in agents:
            if isinstance(item, dict) and str(item.get("id") or "") == agent_id:
                return item
    slot = {
        "id": agent_id,
        "name": _agent_name(agent_id),
        "status": "idle",
        "message": "",
        "tool_call_count": 0,
        "tool_result_count": 0,
        "memos": [],
        "started_at": "",
        "updated_at": "",
    }
    if isinstance(agents, list):
        agents.append(slot)
    else:
        task["agents"] = [slot]
    return slot


def _initial_agents() -> List[Dict[str, Any]]:
    return [
        {
            "id": agent_id,
            "name": label,
            "status": "idle",
            "message": "",
            "tool_call_count": 0,
            "tool_result_count": 0,
            "memos": [],
            "started_at": "",
            "updated_at": "",
        }
        for agent_id, label in AGENT_DEFS
    ]


def _initial_trust() -> Dict[str, Any]:
    return {
        "status": "pending",
        "verdict": "",
        "confidence_label": "待评估",
        "issues": [],
        "issue_count": 0,
        "requires_manual_review": False,
        "evidence_coverage": 0.0,
        "corroborated_coverage": 0.0,
        "official_source_coverage": 0.0,
        "avg_signal": 0.0,
    }


def _phase_label(phase: str) -> str:
    return PHASE_LABELS.get(str(phase or "").strip(), str(phase or "").strip() or "执行中")


def _agent_name(agent_id: str) -> str:
    for key, label in AGENT_DEFS:
        if key == agent_id:
            return label
    return agent_id or "Agent"


def _summarise_tasks(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0}
    for task in tasks:
        status = str(task.get("status") or "")
        if status in counts:
            counts[status] += 1
    counts["total"] = len(tasks)
    return counts


def _reconcile_orphaned_running_tasks(worker_status: Dict[str, Any]) -> None:
    if worker_status.get("running"):
        return
    for task in _load_all_tasks():
        if str(task.get("status") or "") != "running":
            continue
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        if bool(task.get("cancel_requested")):
            mark_task_cancelled(task_id, "worker 已停止，取消请求已生效。")
        else:
            mark_task_failed(task_id, "worker 已停止，运行中的任务被标记为失败。")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return default


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Optional[Exception] = None
    for attempt in range(6):
        tmp_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            os.replace(str(tmp_path), str(path))
            return
        except PermissionError as exc:
            last_error = exc
            LOGGER.warning(
                "report task queue | atomic write permission retry | path=%s attempt=%s error=%s",
                path,
                attempt + 1,
                exc,
            )
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            time.sleep(0.05 * (attempt + 1))
        except OSError as exc:
            last_error = exc
            LOGGER.warning(
                "report task queue | atomic write os error retry | path=%s attempt=%s error=%s",
                path,
                attempt + 1,
                exc,
            )
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            if attempt >= 5:
                break
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        LOGGER.error(
            "report task queue | atomic write failed after retries | path=%s error=%s",
            path,
            last_error,
        )
        raise last_error


def _append_jsonl_line(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False))
        stream.write("\n")


def _new_task_id() -> str:
    return f"rp-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


__all__ = [
    "append_agent_memo",
    "append_event",
    "attach_recent_events",
    "cancel_task",
    "create_task",
    "ensure_worker_running",
    "find_existing_task",
    "find_latest_task",
    "get_task",
    "list_tasks",
    "load_events_since",
    "load_worker_status",
    "mark_agent_started",
    "mark_artifact_ready",
    "mark_review_verdict",
    "mark_task_cancelled",
    "mark_task_completed",
    "mark_task_failed",
    "mark_task_progress",
    "mark_task_started",
    "record_tool_call",
    "record_tool_result",
    "reserve_next_task",
    "retry_task",
    "set_child_pid",
    "set_worker_pid",
    "should_cancel",
    "tail_events",
    "task_events_path",
    "task_state_path",
    "write_worker_status",
]
