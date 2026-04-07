"""
数据库去重任务状态管理

用于在内存中跟踪数据库去重任务的运行状态、心跳、简要日志与结果，
供前端轮询展示统一的后台任务视图。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

_lock = threading.Lock()
_jobs: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
_LOG_LIMIT = 40


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_tables(tables: Optional[Sequence[str]]) -> Tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(item or "").strip()
                for item in (tables or [])
                if str(item or "").strip()
            }
        )
    )


def _job_key(topic: str, database: str, tables: Optional[Sequence[str]] = None) -> Tuple[str, str, str]:
    table_sig = "|".join(_normalise_tables(tables))
    return (str(topic or "").strip(), str(database or "").strip(), table_sig)


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


def create_deduplicate_job(
    topic: str,
    database: str,
    tables: Optional[Sequence[str]] = None,
    *,
    operation: str = "deduplicate",
    initial_message: Optional[str] = None,
) -> Dict[str, Any]:
    key = _job_key(topic, database, tables)
    with _lock:
        existing = _jobs.get(key)
        if existing and existing.get("status") == "running":
            return dict(existing)
        now = _utc_now()
        message = str(initial_message or "数据库去重任务已提交，等待 worker 执行。").strip()
        payload = {
            "topic": key[0],
            "database": key[1],
            "tables": list(_normalise_tables(tables)),
            "operation": str(operation or "deduplicate").strip() or "deduplicate",
            "status": "running",
            "message": message,
            "started_at": now,
            "updated_at": now,
            "last_heartbeat": now,
            "progress": {
                "total_tables": 0,
                "completed_tables": 0,
                "deleted_rows": 0,
                "restored_rows": 0,
                "current_table": "",
                "percentage": 0,
            },
            "logs": [],
            "result": None,
        }
        _append_log(payload, payload["message"], event="task.created")
        _jobs[key] = payload
        return dict(payload)


def get_deduplicate_job(topic: str, database: str, tables: Optional[Sequence[str]] = None) -> Optional[Dict[str, Any]]:
    key = _job_key(topic, database, tables)
    with _lock:
        payload = _jobs.get(key)
        return dict(payload) if payload else None


def list_deduplicate_jobs() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(payload) for payload in _jobs.values()]


def update_deduplicate_job(
    topic: str,
    database: str,
    tables: Optional[Sequence[str]] = None,
    *,
    status: Optional[str] = None,
    message: Optional[str] = None,
    progress: Optional[Dict[str, Any]] = None,
    result: Any = None,
    log_message: Optional[str] = None,
    log_level: str = "info",
    log_event: str = "progress",
    operation: Optional[str] = None,
) -> Dict[str, Any]:
    key = _job_key(topic, database, tables)
    with _lock:
        payload = _jobs.get(key)
        if payload is None:
            now = _utc_now()
            payload = {
                "topic": key[0],
                "database": key[1],
                "tables": list(_normalise_tables(tables)),
                "operation": "deduplicate",
                "status": "idle",
                "message": "",
                "started_at": now,
                "updated_at": now,
                "last_heartbeat": "",
                "progress": {
                    "total_tables": 0,
                    "completed_tables": 0,
                    "deleted_rows": 0,
                    "restored_rows": 0,
                    "current_table": "",
                    "percentage": 0,
                },
                "logs": [],
                "result": None,
            }
        if status:
            payload["status"] = str(status).strip()
        if operation is not None:
            payload["operation"] = str(operation or "").strip() or payload.get("operation") or "deduplicate"
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


def heartbeat_deduplicate_job(topic: str, database: str, tables: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    key = _job_key(topic, database, tables)
    with _lock:
        payload = _jobs.get(key)
        if payload is None:
            now = _utc_now()
            payload = {
                "topic": key[0],
                "database": key[1],
                "tables": list(_normalise_tables(tables)),
                "operation": "deduplicate",
                "status": "idle",
                "message": "",
                "started_at": now,
                "updated_at": now,
                "last_heartbeat": "",
                "progress": {
                    "total_tables": 0,
                    "completed_tables": 0,
                    "deleted_rows": 0,
                    "restored_rows": 0,
                    "current_table": "",
                    "percentage": 0,
                },
                "logs": [],
                "result": None,
            }
        payload["last_heartbeat"] = _utc_now()
        payload["updated_at"] = payload["last_heartbeat"]
        _jobs[key] = payload
        return dict(payload)


def cancel_deduplicate_job(
    topic: str,
    database: str,
    tables: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """取消数据库去重任务"""
    key = _job_key(topic, database, tables)
    with _lock:
        payload = _jobs.get(key)
        if payload is None:
            return None
        status = str(payload.get("status") or "")
        if status == "queued":
            payload["status"] = "cancelled"
            payload["message"] = "任务已取消"
            _append_log(payload, "任务在排队阶段被取消", level="warning", event="task.cancelled")
            _jobs[key] = payload
            return dict(payload)
        elif status == "running":
            payload["cancel_requested"] = True
            payload["message"] = "已请求取消，等待 worker 安全停止"
            _append_log(payload, "已请求取消，等待 worker 安全停止", level="warning", event="task.cancel_requested")
            _jobs[key] = payload
            return dict(payload)
        else:
            raise ValueError(f"当前任务状态 '{status}' 不支持取消")


def delete_deduplicate_job(
    topic: str,
    database: str,
    tables: Optional[Sequence[str]] = None,
) -> bool:
    """删除数据库去重任务记录"""
    key = _job_key(topic, database, tables)
    with _lock:
        payload = _jobs.get(key)
        if payload is None:
            return False
        status = str(payload.get("status") or "")
        if status not in {"completed", "failed", "cancelled", "error"}:
            raise ValueError("只能删除已结束的任务")
        del _jobs[key]
        return True


__all__ = [
    "cancel_deduplicate_job",
    "create_deduplicate_job",
    "delete_deduplicate_job",
    "get_deduplicate_job",
    "heartbeat_deduplicate_job",
    "list_deduplicate_jobs",
    "update_deduplicate_job",
]
