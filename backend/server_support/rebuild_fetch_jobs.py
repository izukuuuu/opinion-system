"""
Fetch 重建任务管理 - 供前端轮询展示统一的 worker / heartbeat 视图。
"""

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

# Global in-memory job store
_REBUILD_FETCH_JOBS: Dict[str, Dict[str, Any]] = {}
_REBUILD_FETCH_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_key(topic: str, database: str, fetch_date: str) -> str:
    return f"{topic}::{database}::{fetch_date}"


def create_rebuild_fetch_job(
    topic: str,
    database: str,
    fetch_date: str,
    *,
    message: str = "任务已创建，等待执行...",
    progress: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """创建一个新的 fetch 重建任务记录"""
    key = _make_key(topic, database, fetch_date)
    now = _utc_now()
    payload: Dict[str, Any] = {
        "topic": topic,
        "database": database,
        "fetch_date": fetch_date,
        "status": "queued",
        "message": message,
        "created_at": now,
        "updated_at": now,
        "last_heartbeat": "",
        "progress": progress or {"percentage": 0},
        "result": None,
    }
    with _REBUILD_FETCH_LOCK:
        _REBUILD_FETCH_JOBS[key] = payload
    return dict(payload)


def get_rebuild_fetch_job(topic: str, database: str, fetch_date: str) -> Optional[Dict[str, Any]]:
    """获取指定任务的状态"""
    key = _make_key(topic, database, fetch_date)
    with _REBUILD_FETCH_LOCK:
        job = _REBUILD_FETCH_JOBS.get(key)
        return dict(job) if job else None


def list_rebuild_fetch_jobs() -> List[Dict[str, Any]]:
    """列出所有 fetch 重建任务"""
    with _REBUILD_FETCH_LOCK:
        return [dict(job) for job in _REBUILD_FETCH_JOBS.values()]


def update_rebuild_fetch_job(
    topic: str,
    database: str,
    fetch_date: str,
    *,
    status: Optional[str] = None,
    message: Optional[str] = None,
    progress: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    log_message: Optional[str] = None,
    log_event: Optional[str] = None,
    log_level: str = "info",
) -> Dict[str, Any]:
    """更新任务状态"""
    key = _make_key(topic, database, fetch_date)
    with _REBUILD_FETCH_LOCK:
        payload = _REBUILD_FETCH_JOBS.get(key)
        if payload is None:
            payload = {
                "topic": topic,
                "database": database,
                "fetch_date": fetch_date,
                "status": "unknown",
                "message": "",
                "created_at": _utc_now(),
                "updated_at": "",
                "last_heartbeat": "",
                "progress": {"percentage": 0},
                "result": None,
            }
            _REBUILD_FETCH_JOBS[key] = payload

        now = _utc_now()
        if status is not None:
            payload["status"] = status
        if message is not None:
            payload["message"] = message
        if progress is not None:
            payload["progress"] = progress
        if result is not None:
            payload["result"] = result
        payload["updated_at"] = now

    return dict(payload)


def heartbeat_rebuild_fetch_job(topic: str, database: str, fetch_date: str) -> Dict[str, Any]:
    """发送任务心跳"""
    key = _make_key(topic, database, fetch_date)
    with _REBUILD_FETCH_LOCK:
        payload = _REBUILD_FETCH_JOBS.get(key)
        if payload is None:
            payload = {
                "topic": topic,
                "database": database,
                "fetch_date": fetch_date,
                "status": "unknown",
                "message": "",
                "created_at": _utc_now(),
                "updated_at": "",
                "last_heartbeat": "",
                "progress": {"percentage": 0},
                "result": None,
            }
            _REBUILD_FETCH_JOBS[key] = payload
        payload["last_heartbeat"] = _utc_now()
        payload["updated_at"] = payload["last_heartbeat"]

    return dict(payload)


def delete_rebuild_fetch_job(topic: str, database: str, fetch_date: str) -> bool:
    """删除任务记录"""
    key = _make_key(topic, database, fetch_date)
    with _REBUILD_FETCH_LOCK:
        if key in _REBUILD_FETCH_JOBS:
            del _REBUILD_FETCH_JOBS[key]
            return True
        return False
