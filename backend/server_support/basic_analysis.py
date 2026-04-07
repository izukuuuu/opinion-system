"""Basic analysis background task queue management."""
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

from src.utils.setting.paths import get_data_root  # type: ignore

LOGGER = logging.getLogger(__name__)

STATE_ROOT = get_data_root() / "_basic_analysis"
TASK_STATE_DIR = STATE_ROOT / "tasks"
WORKER_STATUS_PATH = STATE_ROOT / "worker.json"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_STATUSES = {"queued", "running"}
_HEARTBEAT_INTERVAL_SECONDS = 12
_IDLE_TIMEOUT_SECONDS = 90


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _ensure_state_dirs() -> None:
    TASK_STATE_DIR.mkdir(parents=True, exist_ok=True)


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
        tmp_path = path.with_suffix(f"{path.suffix}.{uuid4().hex[:8]}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            os.replace(str(tmp_path), str(path))
            return
        except Exception as exc:
            last_error = exc
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


def task_state_path(task_id: str) -> Path:
    _ensure_state_dirs()
    return TASK_STATE_DIR / f"{task_id}.json"


def _load_all_tasks() -> List[Dict[str, Any]]:
    _ensure_state_dirs()
    tasks: List[Dict[str, Any]] = []
    for path in TASK_STATE_DIR.glob("*.json"):
        payload = _load_json(path, {})
        if isinstance(payload, dict) and payload.get("id"):
            tasks.append(payload)
    return tasks


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
            raise LookupError("未找到基础分析任务")
        mutate(task)
        task["updated_at"] = _utc_now()
        _atomic_write_json(path, task)
        return task


def _new_task_id() -> str:
    return f"az-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"


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


def create_task(
    topic_identifier: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
    only_function: Optional[str] = None,
) -> Dict[str, Any]:
    """创建基础分析任务。"""
    now = _utc_now()
    date_range = f"{start_date}_{end_date}" if end_date else start_date
    task = {
        "id": _new_task_id(),
        "topic_identifier": str(topic_identifier or "").strip(),
        "start_date": str(start_date or "").strip(),
        "end_date": str(end_date or "").strip(),
        "date_range": date_range,
        "only_function": str(only_function or "").strip() if only_function else "",
        "status": "queued",
        "phase": "queued",
        "percentage": 0,
        "message": "等待基础分析 worker 接单。",
        "worker_pid": 0,
        "cancel_requested": False,
        "error": "",
        "progress": {
            "total_functions": 0,
            "completed_functions": 0,
            "current_function": "",
            "current_target": "",
            "sentiment_phase": "",        # 情感分析阶段：空|normalize|classify|done
            "sentiment_total": 0,         # AI 分类总数
            "sentiment_processed": 0,     # AI 分类已处理数
            "sentiment_classified": 0,    # 成功分类数
            "sentiment_remaining": 0,     # 剩余 unknown 数
        },
        "result": {
            "analyze_root": "",
            "success_count": 0,
        },
        "created_at": now,
        "updated_at": now,
        "started_at": "",
        "finished_at": "",
        "last_heartbeat": "",
    }
    _save_task(task)
    return task


def get_task(task_id: str) -> Dict[str, Any]:
    """获取任务详情。"""
    task = _load_task(task_id)
    if not task:
        raise LookupError("未找到基础分析任务")
    return task


def find_latest_task(
    topic_identifier: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
    statuses: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """查找最近的任务。"""
    desired_statuses = set(statuses or [])
    matches = []
    for task in _load_all_tasks():
        if str(task.get("topic_identifier") or "") != topic_identifier:
            continue
        if str(task.get("start_date") or "") != start_date:
            continue
        if end_date and str(task.get("end_date") or "") != end_date:
            continue
        if desired_statuses and str(task.get("status") or "") not in desired_statuses:
            continue
        matches.append(task)
    if not matches:
        return None
    matches.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return matches[0]


def create_or_reuse_task(
    topic_identifier: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
    only_function: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """创建或复用任务。"""
    running_task = find_latest_task(
        topic_identifier, start_date, end_date=end_date, statuses=["queued", "running"]
    )
    if running_task:
        return running_task
    if not force:
        completed_task = find_latest_task(
            topic_identifier, start_date, end_date=end_date, statuses=["completed"]
        )
        if completed_task:
            return completed_task
    task = create_task(
        topic_identifier, start_date, end_date=end_date, only_function=only_function
    )
    ensure_worker_running()
    return task


def get_latest_task(
    topic_identifier: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """获取最近的任务状态。"""
    return find_latest_task(topic_identifier, start_date, end_date=end_date)


def reserve_next_task() -> Optional[Dict[str, Any]]:
    """预留下一个待处理任务。"""
    queued = sorted(
        (item for item in _load_all_tasks() if str(item.get("status") or "") == "queued"),
        key=lambda item: item.get("created_at") or "",
    )
    if not queued:
        return None
    task_id = str(queued[0].get("id") or "")
    if not task_id:
        return None
    return mark_task_progress(
        task_id,
        status="running",
        phase="prepare",
        percentage=1,
        message="worker 已接单，正在检查数据目录。",
    )


def should_cancel(task_id: str) -> bool:
    """检查任务是否请求取消。"""
    task = _load_task(task_id)
    return bool(task and task.get("cancel_requested"))


def load_worker_status() -> Dict[str, Any]:
    """加载 worker 状态。"""
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
    """写入 worker 状态。"""
    _ensure_state_dirs()
    status = dict(payload or {})
    status["updated_at"] = _utc_now()
    _atomic_write_json(WORKER_STATUS_PATH, status)
    return status


def ensure_worker_running() -> Dict[str, Any]:
    """确保 worker 正在运行。"""
    _ensure_state_dirs()
    worker_lock = FileLock(str(WORKER_STATUS_PATH) + ".lock")
    with worker_lock:
        current = _load_json(WORKER_STATUS_PATH, {})
        pid = _safe_int((current or {}).get("pid"), 0)
        if pid > 0 and _is_process_alive(pid):
            current["running"] = True
            return current

        _reconcile_orphaned_running_tasks({"running": False})
        worker_script = Path(__file__).resolve().parent / "analyze_indicator_worker.py"
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [sys.executable, str(worker_script)],
            cwd=str(Path(__file__).resolve().parents[1]),
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
        LOGGER.info("analyze indicator worker started | pid=%s", process.pid)
        return status


def mark_task_progress(
    task_id: str,
    *,
    status: str,
    phase: str,
    percentage: int,
    message: str,
    progress: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    """更新任务进度。"""
    def _mutate(task: Dict[str, Any]) -> None:
        current_status = str(task.get("status") or "")
        if status == "running" and current_status == "queued":
            task["started_at"] = task.get("started_at") or _utc_now()
        task["status"] = status
        task["phase"] = phase
        task["percentage"] = max(0, min(100, int(percentage)))
        task["message"] = message
        task["worker_pid"] = _safe_int(task.get("worker_pid"), 0) or os.getpid()
        task["error"] = error
        task["last_heartbeat"] = _utc_now()
        if isinstance(progress, dict):
            merged = dict(task.get("progress") or {})
            merged.update(progress)
            task["progress"] = merged
        if isinstance(result, dict):
            merged_result = dict(task.get("result") or {})
            merged_result.update(result)
            task["result"] = merged_result
        if status in TERMINAL_STATUSES:
            task["finished_at"] = _utc_now()

    return _update_task(task_id, _mutate)


def mark_task_completed(
    task_id: str,
    *,
    message: str,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """标记任务完成。"""
    return mark_task_progress(
        task_id,
        status="completed",
        phase="completed",
        percentage=100,
        message=message,
        result=result,
    )


def mark_task_failed(task_id: str, message: str) -> Dict[str, Any]:
    """标记任务失败。"""
    task = _load_task(task_id)
    percentage = _safe_int(task.get("percentage") if task else None, 0)
    return mark_task_progress(
        task_id,
        status="failed",
        phase="failed",
        percentage=min(percentage, 99),
        message=message,
        error=message,
    )


def mark_task_cancelled(task_id: str, message: str) -> Dict[str, Any]:
    """标记任务已取消。"""
    return mark_task_progress(
        task_id,
        status="cancelled",
        phase="cancelled",
        percentage=100,
        message=message,
        error=message,
    )


def cancel_task(task_id: str) -> Dict[str, Any]:
    """取消任务。"""
    def _mutate(task: Dict[str, Any]) -> None:
        status = str(task.get("status") or "")
        if status == "queued":
            task["status"] = "cancelled"
            task["phase"] = "cancelled"
            task["finished_at"] = _utc_now()
            task["message"] = "任务已取消"
            task["percentage"] = 0
        elif status == "running":
            task["cancel_requested"] = True
            task["message"] = "已请求取消，等待 worker 安全停止"
        else:
            raise ValueError(f"当前任务状态 '{status}' 不支持取消")

    return _update_task(task_id, _mutate)


def delete_task(task_id: str) -> None:
    """删除任务文件。"""
    task = _load_task(task_id)
    if not task:
        raise LookupError("未找到基础分析任务")
    status = str(task.get("status") or "")
    if status not in TERMINAL_STATUSES:
        raise ValueError("只能删除已结束的任务")
    path = task_state_path(task_id)
    lock = FileLock(str(path) + ".lock")
    with lock:
        if path.exists():
            path.unlink()


def _reconcile_orphaned_running_tasks(worker_status: Dict[str, Any]) -> None:
    """清理孤儿任务。"""
    if worker_status.get("running"):
        return
    for task in _load_all_tasks():
        if str(task.get("status") or "") != "running":
            continue
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        if bool(task.get("cancel_requested")):
            mark_task_cancelled(task_id, "worker 已停止，取消请求已生效")
        else:
            mark_task_failed(task_id, "worker 中断，任务已被标记为失败")


def build_status_payload(
    topic_identifier: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """构建状态 payload。"""
    task = get_latest_task(topic_identifier, start_date, end_date=end_date)
    return {
        "topic_identifier": topic_identifier,
        "start_date": start_date,
        "end_date": end_date or "",
        "task": task,
        "worker": load_worker_status(),
    }


def list_tasks(*, limit: int = 20) -> Dict[str, Any]:
    """列出所有任务。"""
    worker = load_worker_status()
    tasks = _load_all_tasks()
    tasks.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    tasks = tasks[: max(limit, 1)]
    return {
        "tasks": tasks,
        "worker": worker,
    }


__all__ = [
    "build_status_payload",
    "cancel_task",
    "create_or_reuse_task",
    "create_task",
    "delete_task",
    "ensure_worker_running",
    "get_latest_task",
    "get_task",
    "list_tasks",
    "load_worker_status",
    "mark_task_cancelled",
    "mark_task_completed",
    "mark_task_failed",
    "mark_task_progress",
    "reserve_next_task",
    "should_cancel",
    "task_state_path",
    "write_worker_status",
]