"""Persistent queue and worker coordination for NetInsight tasks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from filelock import FileLock

from ..project import get_project_manager
from ..utils.setting.paths import get_data_root
from .planner import normalize_keywords, normalize_platforms

STATE_ROOT = get_data_root() / "_netinsight"
TASK_STATE_DIR = STATE_ROOT / "tasks"
WORKER_STATUS_PATH = STATE_ROOT / "worker.json"
LOGIN_STATE_PATH = STATE_ROOT / "login_state.json"
SESSION_STATE_PATH = STATE_ROOT / "session_state.json"
_TASK_EVENTS_LIMIT = 60
OUTPUT_FILE_NAMES = {
    "csv": "records.csv",
    "jsonl": "records.jsonl",
    "meta": "meta.json",
}


def create_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    project_name, project_id = _resolve_project(payload.get("project"))
    keywords = normalize_keywords(payload.get("keywords"))
    if not keywords:
        raise ValueError("请至少提供一个检索关键词")

    platforms = normalize_platforms(payload.get("platforms"))
    if not platforms:
        raise ValueError("请至少选择一个平台")

    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("任务标题不能为空")

    start_date = str(payload.get("start_date") or "").strip()
    end_date = str(payload.get("end_date") or "").strip()
    if not start_date or not end_date:
        raise ValueError("请提供开始日期和结束日期")
    start_value = _parse_iso_date(start_date, label="开始日期")
    end_value = _parse_iso_date(end_date, label="结束日期")
    if start_value > end_value:
        raise ValueError("开始日期不能晚于结束日期")

    task_id = _new_task_id()
    now = _utc_now()
    task = {
        "id": task_id,
        "title": title,
        "summary": str(payload.get("summary") or "").strip(),
        "query": str(payload.get("query") or "").strip(),
        "project": project_name,
        "project_id": project_id,
        "status": "queued",
        "cancel_requested": False,
        "keywords": keywords,
        "platforms": platforms,
        "config": {
            "start_date": start_date,
            "end_date": end_date,
            "time_range": f"{start_date} 00:00:00;{end_date} 23:59:59",
            "total_limit": _safe_int(payload.get("total_limit"), 500, minimum=1),
            "page_size": _safe_int(payload.get("page_size"), 50, minimum=10),
            "sort": str(payload.get("sort") or "comments_desc").strip() or "comments_desc",
            "info_type": str(payload.get("info_type") or "2").strip() or "2",
            "dedupe_by_content": _safe_bool(payload.get("dedupe_by_content", True)),
            "allocate_by_platform": _safe_bool(payload.get("allocate_by_platform", False)),
        },
        "planner": {
            "source": str(payload.get("planner_source") or "").strip() or "manual",
        },
        "progress": {
            "phase": "queued",
            "message": "等待 NetInsight worker 接单",
            "percentage": 0,
            "counts_completed": 0,
            "counts_total": len(keywords) * len(platforms),
            "planned_total": 0,
            "fetched_total": 0,
            "deduped_total": 0,
            "current_platform": "",
            "current_keyword": "",
        },
        "search_plan": {},
        "output": {
            "dir": str(output_dir_for_task({"id": task_id, "project_id": project_id})),
            "files": [],
            "record_count": 0,
            "deduplicated_count": 0,
            "removed_duplicates": 0,
        },
        "error": "",
        "events": [],
        "created_at": now,
        "updated_at": now,
        "started_at": "",
        "finished_at": "",
    }
    _append_event(task, "info", "任务已创建，等待执行")
    _save_task(task)
    return task


def list_tasks(*, project: str = "", status: str = "", limit: int = 100) -> Dict[str, Any]:
    worker = load_worker_status()
    _reconcile_orphaned_running_tasks(worker)

    tasks = _load_all_tasks()
    if project:
        tasks = [task for task in tasks if str(task.get("project") or "") == project]
    if status:
        tasks = [task for task in tasks if str(task.get("status") or "") == status]
    tasks.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    tasks = tasks[: max(limit, 1)]
    return {
        "tasks": tasks,
        "summary": _summarise_tasks(tasks),
        "worker": load_worker_status(),
    }


def get_task(task_id: str) -> Dict[str, Any]:
    task = _load_task(task_id)
    if not task:
        raise LookupError("未找到指定的 NetInsight 任务")
    return task


def cancel_task(task_id: str) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        status = str(task.get("status") or "")
        if status == "queued":
            task["status"] = "cancelled"
            task["finished_at"] = _utc_now()
            task["progress"]["phase"] = "cancelled"
            task["progress"]["message"] = "任务已取消"
            task["progress"]["percentage"] = 100
            _append_event(task, "warning", "任务在排队阶段被取消")
        elif status == "running":
            task["cancel_requested"] = True
            _append_event(task, "warning", "已请求取消，等待 worker 安全停止")
        else:
            raise ValueError("当前任务状态不支持取消")

    return _update_task(task_id, _mutate)


def retry_task(task_id: str) -> Dict[str, Any]:
    task = get_task(task_id)
    next_payload = {
        "title": task.get("title"),
        "summary": task.get("summary"),
        "query": task.get("query"),
        "project": task.get("project"),
        "keywords": task.get("keywords"),
        "platforms": task.get("platforms"),
        "start_date": task.get("config", {}).get("start_date"),
        "end_date": task.get("config", {}).get("end_date"),
        "total_limit": task.get("config", {}).get("total_limit"),
        "page_size": task.get("config", {}).get("page_size"),
        "sort": task.get("config", {}).get("sort"),
        "info_type": task.get("config", {}).get("info_type"),
        "dedupe_by_content": task.get("config", {}).get("dedupe_by_content", True),
        "allocate_by_platform": task.get("config", {}).get("allocate_by_platform", False),
        "planner_source": "retry",
    }
    retried = create_task(next_payload)
    _update_task(
        task_id,
        lambda current: _append_event(
            current,
            "info",
            f"已创建重试任务 {retried['id']}",
        ),
    )
    return retried


def delete_task(task_id: str) -> None:
    task = get_task(task_id)
    if str(task.get("status") or "") == "running":
        raise ValueError("运行中的任务不能直接删除")

    output_dir = Path(str(task.get("output", {}).get("dir") or "")).resolve()
    path = task_state_path(task_id)
    lock = FileLock(str(path) + ".lock")
    with lock:
        if path.exists():
            path.unlink()
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)


def ensure_worker_running() -> Dict[str, Any]:
    _ensure_state_dirs()
    worker_lock = FileLock(str(WORKER_STATUS_PATH) + ".lock")
    with worker_lock:
        current = _load_json(WORKER_STATUS_PATH, {})
        pid = _safe_int(current.get("pid"), 0)
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


def reserve_next_task() -> Optional[Dict[str, Any]]:
    candidates = sorted(
        (
            task for task in _load_all_tasks()
            if str(task.get("status") or "") == "queued"
        ),
        key=lambda item: item.get("created_at") or "",
    )
    if not candidates:
        return None
    task_id = str(candidates[0].get("id") or "")

    def _mutate(task: Dict[str, Any]) -> None:
        if str(task.get("status") or "") != "queued":
            raise ValueError("任务已被其他 worker 占用")
        task["status"] = "running"
        task["started_at"] = task.get("started_at") or _utc_now()
        task["error"] = ""
        task["progress"]["phase"] = "starting"
        task["progress"]["message"] = "worker 已接单，准备登录 NetInsight"
        task["progress"]["percentage"] = max(_safe_int(task["progress"].get("percentage"), 0), 1)
        _append_event(task, "info", "worker 已接单")

    try:
        return _update_task(task_id, _mutate)
    except ValueError:
        return None


def should_cancel(task_id: str) -> bool:
    task = _load_task(task_id)
    return bool(task and task.get("cancel_requested"))


def mark_task_progress(
    task_id: str,
    *,
    phase: str,
    message: str,
    percentage: Optional[int] = None,
    current_platform: str = "",
    current_keyword: str = "",
    counts_completed: Optional[int] = None,
    counts_total: Optional[int] = None,
    planned_total: Optional[int] = None,
    fetched_total: Optional[int] = None,
    deduped_total: Optional[int] = None,
    event_level: str = "",
) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        progress = task.setdefault("progress", {})
        progress["phase"] = phase
        progress["message"] = message
        if percentage is not None:
            progress["percentage"] = max(0, min(100, int(percentage)))
        if current_platform:
            progress["current_platform"] = current_platform
        if current_keyword:
            progress["current_keyword"] = current_keyword
        if counts_completed is not None:
            progress["counts_completed"] = counts_completed
        if counts_total is not None:
            progress["counts_total"] = counts_total
        if planned_total is not None:
            progress["planned_total"] = planned_total
        if fetched_total is not None:
            progress["fetched_total"] = fetched_total
        if deduped_total is not None:
            progress["deduped_total"] = deduped_total
        if event_level:
            _append_event(task, event_level, message)

    return _update_task(task_id, _mutate)


def store_search_plan(task_id: str, search_plan: Dict[str, Any]) -> Dict[str, Any]:
    return _update_task(task_id, lambda task: task.update({"search_plan": search_plan}))


def mark_task_completed(task_id: str, output: Dict[str, Any], message: str) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        task["status"] = "completed"
        task["cancel_requested"] = False
        task["finished_at"] = _utc_now()
        task["error"] = ""
        task["output"] = output
        progress = task.setdefault("progress", {})
        progress["phase"] = "completed"
        progress["message"] = message
        progress["percentage"] = 100
        progress["deduped_total"] = int(output.get("deduplicated_count") or 0)
        _append_event(task, "success", message)

    return _update_task(task_id, _mutate)


def mark_task_failed(task_id: str, message: str) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        task["status"] = "failed"
        task["finished_at"] = _utc_now()
        task["error"] = message
        progress = task.setdefault("progress", {})
        progress["phase"] = "failed"
        progress["message"] = message
        progress["percentage"] = min(_safe_int(progress.get("percentage"), 0), 99)
        _append_event(task, "error", message)

    return _update_task(task_id, _mutate)


def mark_task_cancelled(task_id: str, message: str) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        task["status"] = "cancelled"
        task["finished_at"] = _utc_now()
        task["cancel_requested"] = False
        task["error"] = ""
        progress = task.setdefault("progress", {})
        progress["phase"] = "cancelled"
        progress["message"] = message
        progress["percentage"] = 100
        _append_event(task, "warning", message)

    return _update_task(task_id, _mutate)


def write_worker_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_state_dirs()
    status = dict(payload or {})
    status["updated_at"] = _utc_now()
    _atomic_write_json(WORKER_STATUS_PATH, status)
    return status


def read_login_state() -> Dict[str, Any]:
    try:
        if LOGIN_STATE_PATH.exists():
            return json.loads(LOGIN_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"status": "idle", "logged_in_at": None, "error": None, "username": ""}


def write_login_state(state: Dict[str, Any]) -> None:
    _ensure_state_dirs()
    _atomic_write_json(LOGIN_STATE_PATH, state)


def read_session_state() -> Dict[str, Any]:
    _ensure_state_dirs()
    payload = _load_json(SESSION_STATE_PATH, {})
    return payload if isinstance(payload, dict) else {}


def write_session_state(state: Dict[str, Any]) -> None:
    _ensure_state_dirs()
    _atomic_write_json(SESSION_STATE_PATH, state)


def output_dir_for_task(task: Dict[str, Any]) -> Path:
    task_id = str(task.get("id") or "").strip()
    project_id = str(task.get("project_id") or "").strip()
    if project_id:
        root = get_data_root() / "projects" / project_id / "netinsight"
    else:
        root = get_data_root() / "netinsight" / "outputs"
    path = root / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_task_output_file(task_id: str, file_kind: str) -> Path:
    task = get_task(task_id)
    filename = OUTPUT_FILE_NAMES.get(str(file_kind or "").strip().lower())
    if not filename:
        raise ValueError("仅支持下载 csv / jsonl / meta 文件")

    output = task.get("output", {})
    output_dir_raw = str(output.get("dir") or "").strip()
    if not output_dir_raw:
        raise LookupError("任务还没有输出目录")
    output_dir = Path(output_dir_raw).resolve()

    candidate = (output_dir / filename).resolve()
    try:
        candidate.relative_to(output_dir)
    except ValueError as exc:
        raise LookupError("任务输出路径异常，拒绝访问") from exc
    if not candidate.exists() or not candidate.is_file():
        raise LookupError("请求的输出文件尚未生成")
    return candidate


def task_state_path(task_id: str) -> Path:
    _ensure_state_dirs()
    return TASK_STATE_DIR / f"{task_id}.json"


def _ensure_state_dirs() -> None:
    TASK_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load_all_tasks() -> List[Dict[str, Any]]:
    _ensure_state_dirs()
    tasks: List[Dict[str, Any]] = []
    for path in TASK_STATE_DIR.glob("*.json"):
        payload = _load_json(path, {})
        if isinstance(payload, dict) and payload.get("id"):
            tasks.append(payload)
    return tasks


def _load_task(task_id: str) -> Optional[Dict[str, Any]]:
    path = task_state_path(task_id)
    if not path.exists():
        return None
    payload = _load_json(path, {})
    return payload if isinstance(payload, dict) else None


def _save_task(task: Dict[str, Any]) -> None:
    path = task_state_path(str(task.get("id") or ""))
    lock = FileLock(str(path) + ".lock")
    with lock:
        task["updated_at"] = _utc_now()
        _atomic_write_json(path, task)


def _update_task(task_id: str, mutate: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    path = task_state_path(task_id)
    if not path.exists():
        raise LookupError("未找到指定的 NetInsight 任务")
    lock = FileLock(str(path) + ".lock")
    with lock:
        task = _load_json(path, {})
        if not isinstance(task, dict):
            raise LookupError("任务状态文件损坏")
        mutate(task)
        task["updated_at"] = _utc_now()
        _atomic_write_json(path, task)
        return task


def _summarise_tasks(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for task in tasks:
        status = str(task.get("status") or "")
        if status in counts:
            counts[status] += 1
    counts["total"] = len(tasks)
    return counts


def _append_event(task: Dict[str, Any], level: str, message: str) -> None:
    events = task.setdefault("events", [])
    events.append(
        {
            "timestamp": _utc_now(),
            "level": level,
            "message": message,
        }
    )
    task["events"] = events[-_TASK_EVENTS_LIMIT:]


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
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def _resolve_project(project_name: Any) -> Tuple[str, str]:
    name = str(project_name or "").strip()
    if not name:
        return "", ""
    manager = get_project_manager()
    record = manager.get_project(name)
    if not record:
        raise ValueError("关联项目不存在，请先创建项目或取消关联")
    return name, str(record.get("id") or "")


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
            mark_task_cancelled(task_id, "worker 已停止，取消请求已生效")
        else:
            mark_task_failed(task_id, "worker 中断，任务已被标记为失败")


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid,
            )
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


def _new_task_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"ni-{timestamp}-{uuid4().hex[:6]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError as exc:
        raise ValueError(f"{label}必须是 YYYY-MM-DD") from exc


def _safe_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


__all__ = [
    "cancel_task",
    "create_task",
    "delete_task",
    "ensure_worker_running",
    "get_task",
    "list_tasks",
    "load_worker_status",
    "mark_task_cancelled",
    "mark_task_completed",
    "mark_task_failed",
    "mark_task_progress",
    "output_dir_for_task",
    "read_session_state",
    "reserve_next_task",
    "resolve_task_output_file",
    "retry_task",
    "should_cancel",
    "store_search_plan",
    "write_session_state",
    "write_worker_status",
]
