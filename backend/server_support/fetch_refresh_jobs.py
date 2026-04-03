"""
本地 fetch 缓存刷新任务状态管理

用于在内存中跟踪“根据远程数据库重新刷新本地 fetch 缓存”的后台任务，
供后台任务聚合器与后清洗后续动作复用。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

_lock = threading.Lock()
_jobs: Dict[Tuple[str, str], Dict[str, Any]] = {}
_LOG_LIMIT = 40
_worker: Dict[str, Any] = {
    "status": "idle",
    "running": False,
    "pid": 0,
    "current_task_id": "",
    "last_heartbeat": "",
    "updated_at": "",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_key(topic: str, database: str) -> Tuple[str, str]:
    return (str(topic or "").strip(), str(database or "").strip())


def _normalise_ranges(ranges: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, str]]:
    normalised: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in ranges or []:
        if not isinstance(item, dict):
            continue
        folder = str(item.get("folder") or "").strip()
        start = str(item.get("start") or "").strip()
        end = str(item.get("end") or start).strip() or start
        if not folder or not start:
            continue
        if folder in seen:
            continue
        seen.add(folder)
        normalised.append({
            "folder": folder,
            "start": start,
            "end": end,
        })
    return normalised


def _append_log(payload: Dict[str, Any], message: str, *, level: str = "info", event: str = "progress") -> None:
    logs = payload.setdefault("logs", [])
    if not isinstance(logs, list):
        logs = []
        payload["logs"] = logs
    logs.insert(0, {
        "ts": _utc_now(),
        "level": level,
        "event": event,
        "message": str(message or "").strip(),
    })
    del logs[_LOG_LIMIT:]


def create_fetch_refresh_job(
    topic: str,
    database: str,
    ranges: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    key = _job_key(topic, database)
    normalised_ranges = _normalise_ranges(ranges)
    with _lock:
        existing = _jobs.get(key)
        if existing and str(existing.get("status") or "") in {"queued", "running"}:
            return dict(existing)
        now = _utc_now()
        payload = {
            "topic": key[0],
            "database": key[1],
            "ranges": normalised_ranges,
            "status": "queued",
            "message": f"本地缓存刷新任务已提交，共 {len(normalised_ranges)} 个批次待处理。",
            "started_at": "",
            "finished_at": "",
            "updated_at": now,
            "last_heartbeat": "",
            "progress": {
                "total_ranges": len(normalised_ranges),
                "completed_ranges": 0,
                "refreshed_rows": 0,
                "current_range": "",
                "percentage": 0,
            },
            "logs": [],
            "result": None,
        }
        _append_log(payload, payload["message"], event="task.created")
        _jobs[key] = payload
        return dict(payload)


def get_fetch_refresh_job(topic: str, database: str) -> Optional[Dict[str, Any]]:
    key = _job_key(topic, database)
    with _lock:
        payload = _jobs.get(key)
        return dict(payload) if payload else None


def list_fetch_refresh_jobs() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(payload) for payload in _jobs.values()]


def update_fetch_refresh_job(
    topic: str,
    database: str,
    *,
    status: Optional[str] = None,
    message: Optional[str] = None,
    progress: Optional[Dict[str, Any]] = None,
    result: Any = None,
    ranges: Optional[Sequence[Dict[str, Any]]] = None,
    log_message: Optional[str] = None,
    log_level: str = "info",
    log_event: str = "progress",
) -> Dict[str, Any]:
    key = _job_key(topic, database)
    with _lock:
        payload = _jobs.get(key)
        if payload is None:
            now = _utc_now()
            payload = {
                "topic": key[0],
                "database": key[1],
                "ranges": [],
                "status": "idle",
                "message": "",
                "started_at": "",
                "finished_at": "",
                "updated_at": now,
                "last_heartbeat": "",
                "progress": {
                    "total_ranges": 0,
                    "completed_ranges": 0,
                    "refreshed_rows": 0,
                    "current_range": "",
                    "percentage": 0,
                },
                "logs": [],
                "result": None,
            }
        if ranges is not None:
            payload["ranges"] = _normalise_ranges(ranges)
        if status:
            payload["status"] = str(status).strip()
            if payload["status"] == "running" and not payload.get("started_at"):
                payload["started_at"] = _utc_now()
            if payload["status"] in {"completed", "failed", "cancelled", "error"}:
                payload["finished_at"] = _utc_now()
        if message is not None:
            payload["message"] = str(message or "").strip()
        if isinstance(progress, dict):
            current = payload.setdefault("progress", {})
            if not isinstance(current, dict):
                current = {}
                payload["progress"] = current
            current.update(progress)
        if result is not None:
            payload["result"] = result
        payload["updated_at"] = _utc_now()
        if log_message:
            _append_log(payload, log_message, level=log_level, event=log_event)
        _jobs[key] = payload
        return dict(payload)


def heartbeat_fetch_refresh_job(topic: str, database: str) -> Dict[str, Any]:
    key = _job_key(topic, database)
    with _lock:
        payload = _jobs.get(key)
        if payload is None:
            now = _utc_now()
            payload = {
                "topic": key[0],
                "database": key[1],
                "ranges": [],
                "status": "idle",
                "message": "",
                "started_at": "",
                "finished_at": "",
                "updated_at": now,
                "last_heartbeat": "",
                "progress": {
                    "total_ranges": 0,
                    "completed_ranges": 0,
                    "refreshed_rows": 0,
                    "current_range": "",
                    "percentage": 0,
                },
                "logs": [],
                "result": None,
            }
        payload["last_heartbeat"] = _utc_now()
        payload["updated_at"] = payload["last_heartbeat"]
        _jobs[key] = payload
        return dict(payload)


def update_fetch_refresh_worker(
    *,
    status: Optional[str] = None,
    running: Optional[bool] = None,
    pid: Optional[int] = None,
    current_task_id: Optional[str] = None,
    heartbeat: bool = False,
) -> Dict[str, Any]:
    with _lock:
        if status is not None:
            _worker["status"] = str(status or "").strip() or "idle"
        if running is not None:
            _worker["running"] = bool(running)
        if pid is not None:
            _worker["pid"] = int(pid or 0)
        if current_task_id is not None:
            _worker["current_task_id"] = str(current_task_id or "").strip()
        if heartbeat:
            _worker["last_heartbeat"] = _utc_now()
        _worker["updated_at"] = _utc_now()
        return dict(_worker)


def load_fetch_refresh_worker_status() -> Dict[str, Any]:
    with _lock:
        return dict(_worker)


__all__ = [
    "create_fetch_refresh_job",
    "get_fetch_refresh_job",
    "list_fetch_refresh_jobs",
    "update_fetch_refresh_job",
    "heartbeat_fetch_refresh_job",
    "update_fetch_refresh_worker",
    "load_fetch_refresh_worker_status",
]
