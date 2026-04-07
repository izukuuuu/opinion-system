from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from filelock import FileLock

from src.utils.setting.paths import get_data_root  # type: ignore

LOGGER = logging.getLogger(__name__)

STATE_ROOT = get_data_root() / "_publisher_detection"
TASK_STATE_DIR = STATE_ROOT / "tasks"
WORKER_STATUS_PATH = STATE_ROOT / "worker.json"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
CANCELABLE_STATUSES = {"queued", "running"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
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
        tmp_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
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


def _normalise_tables(tables: Optional[Sequence[str]]) -> List[str]:
    values: List[str] = []
    seen: set[str] = set()
    for item in tables or []:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return sorted(values)


def _scope_key(topic_identifier: str, database: str, tables: Optional[Sequence[str]]) -> str:
    table_key = "|".join(_normalise_tables(tables)) or "*"
    return f"{str(topic_identifier or '').strip()}::{str(database or '').strip()}::{table_key}"


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


def _update_task(task_id: str, mutate) -> Dict[str, Any]:
    path = task_state_path(task_id)
    lock = FileLock(str(path) + ".lock")
    with lock:
        task = _load_json(path, {})
        if not isinstance(task, dict) or not task.get("id"):
            raise LookupError("未找到异常发布者识别任务")
        mutate(task)
        task["updated_at"] = _utc_now()
        _atomic_write_json(path, task)
        return task


def _new_task_id() -> str:
    return f"pd-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"


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
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
    limit: int = 50,
    sample_limit: int = 3,
) -> Dict[str, Any]:
    task_id = _new_task_id()
    now = _utc_now()
    normalised_tables = _normalise_tables(tables)
    task = {
        "id": task_id,
        "scope_key": _scope_key(topic_identifier, database, normalised_tables),
        "topic_identifier": str(topic_identifier or "").strip(),
        "database": str(database or "").strip(),
        "tables": normalised_tables,
        "limit": max(_safe_int(limit, 50), 1),
        "sample_limit": max(_safe_int(sample_limit, 3), 1),
        "status": "queued",
        "phase": "queued",
        "percentage": 0,
        "message": "异常发布者识别任务已提交，等待 worker 处理。",
        "worker_pid": 0,
        "error": "",
        "progress": {
            "total_tables": len(normalised_tables),
            "completed_tables": 0,
            "percentage": 0,
            "current_table": "",
            "scanned_tables": [],
            "skipped_tables": [],
            "missing_tables": [],
        },
        "result": None,
        "created_at": now,
        "updated_at": now,
        "started_at": "",
        "finished_at": "",
    }
    _save_task(task)
    return task


def get_task(task_id: str) -> Dict[str, Any]:
    task = _load_task(task_id)
    if not task:
        raise LookupError("未找到异常发布者识别任务")
    return task


def find_latest_task(
    topic_identifier: str,
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
    statuses: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    desired_statuses = set(statuses or [])
    scope_key = _scope_key(topic_identifier, database, tables)
    matches = []
    for task in _load_all_tasks():
        if str(task.get("scope_key") or "") != scope_key:
            continue
        if desired_statuses and str(task.get("status") or "") not in desired_statuses:
            continue
        matches.append(task)
    if not matches:
        return None
    matches.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return matches[0]


def get_latest_task(
    topic_identifier: str,
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    return find_latest_task(topic_identifier, database, tables=tables)


def create_or_reuse_task(
    topic_identifier: str,
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
    limit: int = 50,
    sample_limit: int = 3,
    force: bool = False,
) -> Dict[str, Any]:
    running_task = find_latest_task(
        topic_identifier,
        database,
        tables=tables,
        statuses=["queued", "running"],
    )
    if running_task:
        return running_task
    if not force:
        completed_task = find_latest_task(
            topic_identifier,
            database,
            tables=tables,
            statuses=["completed"],
        )
        if completed_task:
            return completed_task
    task = create_task(
        topic_identifier,
        database,
        tables=tables,
        limit=limit,
        sample_limit=sample_limit,
    )
    ensure_worker_running()
    return task


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
    return mark_task_progress(
        task_id,
        status="running",
        phase="prepare",
        percentage=1,
        message="worker 已接单，开始扫描数据表。",
    )


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
        worker_script = Path(__file__).resolve().parent / "publisher_detection_worker.py"
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
    def _mutate(task: Dict[str, Any]) -> None:
        current_status = str(task.get("status") or "")
        if status == "running" and current_status == "queued":
            task["started_at"] = task.get("started_at") or _utc_now()
        task["status"] = status
        task["phase"] = phase
        task["percentage"] = max(0, min(100, int(percentage)))
        task["message"] = str(message or "").strip()
        task["worker_pid"] = _safe_int(task.get("worker_pid"), 0) or os.getpid()
        task["error"] = str(error or "").strip()
        if isinstance(progress, dict):
            current_progress = task.get("progress")
            if not isinstance(current_progress, dict):
                current_progress = {}
            current_progress.update(progress)
            current_progress["percentage"] = max(
                0,
                min(100, _safe_int(current_progress.get("percentage"), task["percentage"])),
            )
            task["progress"] = current_progress
        if isinstance(result, dict):
            task["result"] = result
        if status in TERMINAL_STATUSES:
            task["finished_at"] = _utc_now()

    return _update_task(task_id, _mutate)


def _reconcile_orphaned_running_tasks(worker_status: Dict[str, Any]) -> None:
    if worker_status.get("running"):
        return
    for task in _load_all_tasks():
        if str(task.get("status") or "") != "running":
            continue
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        mark_task_progress(
            task_id,
            status="failed",
            phase="failed",
            percentage=max(_safe_int(task.get("percentage"), 0), 1),
            message="worker 已停止，任务被标记为失败。",
            error="worker 已停止，任务被标记为失败。",
        )


def build_status_payload(
    topic_identifier: str,
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    active_task = find_latest_task(
        topic_identifier,
        database,
        tables=tables,
        statuses=["queued", "running"],
    )
    latest_completed = find_latest_task(
        topic_identifier,
        database,
        tables=tables,
        statuses=["completed"],
    )
    latest_any = active_task or get_latest_task(
        topic_identifier,
        database,
        tables=tables,
    )
    latest_result = None
    if latest_completed and isinstance(latest_completed.get("result"), dict):
        latest_result = _with_current_blacklist(topic_identifier, latest_completed.get("result"))
    task_payload = _with_current_blacklist(topic_identifier, latest_any)
    return {
        "topic_identifier": topic_identifier,
        "database": str(database or "").strip(),
        "tables": _normalise_tables(tables),
        "task": task_payload,
        "worker": load_worker_status(),
        "latest_result": latest_result,
    }


def _with_current_blacklist(topic_identifier: str, payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    try:
        from src.filter.database_processing import (  # type: ignore
            _normalise_author_key,
            load_shared_publisher_blacklist,
        )

        blacklisted = set(load_shared_publisher_blacklist(topic_identifier).get("authors") or [])
    except Exception:
        blacklisted = set()

        def _normalise_author_key(value: Any) -> str:  # type: ignore
            return str(value or "").strip()

    cloned = json.loads(json.dumps(payload, ensure_ascii=False))
    if isinstance(cloned.get("result"), dict):
        _apply_publishers_blacklist(cloned["result"], blacklisted, _normalise_author_key)
    _apply_publishers_blacklist(cloned, blacklisted, _normalise_author_key)
    return cloned


def _apply_publishers_blacklist(result: Dict[str, Any], blacklisted: set[str], normalise_author_key) -> None:
    publishers = result.get("publishers")
    if not isinstance(publishers, list):
        return
    for item in publishers:
        if not isinstance(item, dict):
            continue
        item["blacklisted"] = normalise_author_key(item.get("author")) in blacklisted


def cancel_task(task_id: str) -> Dict[str, Any]:
    """取消异常发布者识别任务"""
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
    """删除异常发布者识别任务文件"""
    task = _load_task(task_id)
    if not task:
        raise LookupError("未找到异常发布者识别任务")
    status = str(task.get("status") or "")
    if status not in TERMINAL_STATUSES:
        raise ValueError("只能删除已结束的任务（已完成、失败或已取消）")
    path = task_state_path(task_id)
    lock = FileLock(str(path) + ".lock")
    with lock:
        if path.exists():
            path.unlink()


__all__ = [
    "build_status_payload",
    "cancel_task",
    "create_or_reuse_task",
    "delete_task",
    "ensure_worker_running",
    "get_task",
    "load_worker_status",
    "mark_task_progress",
    "reserve_next_task",
    "write_worker_status",
]
