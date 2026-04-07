from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.utils.setting.paths import get_data_root  # type: ignore

from .fetch_refresh_jobs import (
    list_fetch_refresh_jobs,
    load_fetch_refresh_worker_status,
)
from .deduplicate_jobs import list_deduplicate_jobs
from .postclean_jobs import list_postclean_jobs
from .publisher_detection import load_worker_status as load_publisher_detection_worker_status
from .rebuild_fetch_jobs import list_rebuild_fetch_jobs
from .stopword_suggestions import load_worker_status as load_stopword_worker_status

ACTIVE_STATUSES = {"queued", "running"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "error"}
_DEFAULT_LIMIT = 20
_HEARTBEAT_STALE_SECONDS = 45

REPORT_PHASE_LABELS = {
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

GENERIC_PHASE_LABELS = {
    "queued": "等待中",
    "prepare": "准备中",
    "starting": "启动中",
    "login": "登录中",
    "count": "规模预估",
    "collect": "数据采集",
    "dedupe": "去重整理",
    "persist": "写入结果",
    "analyze": "处理中",
    "completed": "已完成",
    "failed": "已失败",
    "cancelled": "已取消",
    "error": "异常",
}


def collect_background_task_payload(*, active_only: bool = True, limit: int = _DEFAULT_LIMIT) -> Dict[str, Any]:
    tasks: List[Dict[str, Any]] = []
    workers: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for collector in (
        _collect_report_tasks,
        _collect_netinsight_tasks,
        _collect_stopword_tasks,
        _collect_publisher_detection_tasks,
        _collect_postclean_tasks,
        _collect_deduplicate_tasks,
        _collect_fetch_refresh_tasks,
        _collect_rebuild_fetch_tasks,
    ):
        try:
            collector_tasks, collector_workers = collector(active_only=active_only)
            tasks.extend(collector_tasks)
            workers.extend(collector_workers)
        except Exception as exc:
            warnings.append(str(exc))

    tasks.sort(key=_task_sort_key)
    workers.sort(key=_worker_sort_key)

    limited_tasks = tasks[: max(1, int(limit or _DEFAULT_LIMIT))]
    active_count = sum(1 for task in tasks if str(task.get("status") or "") in ACTIVE_STATUSES)
    running_count = sum(1 for task in tasks if str(task.get("status") or "") == "running")
    queued_count = sum(1 for task in tasks if str(task.get("status") or "") == "queued")

    return {
        "summary": {
            "active_count": active_count,
            "running_count": running_count,
            "queued_count": queued_count,
            "total_count": len(tasks),
            "updated_at": _utc_now(),
        },
        "tasks": limited_tasks,
        "workers": workers,
        "warnings": warnings,
    }


def _collect_report_tasks(*, active_only: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from src.report.task_queue import list_tasks as list_report_tasks  # type: ignore

    payload = list_report_tasks(limit=80)
    raw_tasks = payload.get("tasks") if isinstance(payload, dict) else []
    worker = payload.get("worker") if isinstance(payload, dict) else {}
    worker_payload = _normalise_worker(
        source="report",
        source_label="报告 Worker",
        payload=worker if isinstance(worker, dict) else {},
    )
    tasks = [
        _normalise_report_task(task, worker_payload)
        for task in (raw_tasks or [])
        if isinstance(task, dict) and _include_task(task, active_only=active_only)
    ]
    workers = [worker_payload]
    return tasks, workers


def _collect_netinsight_tasks(*, active_only: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from src.netinsight.task_queue import list_tasks as list_netinsight_tasks  # type: ignore

    payload = list_netinsight_tasks(limit=80)
    raw_tasks = payload.get("tasks") if isinstance(payload, dict) else []
    worker = payload.get("worker") if isinstance(payload, dict) else {}
    worker_payload = _normalise_worker(
        source="netinsight",
        source_label="采集 Worker",
        payload=worker if isinstance(worker, dict) else {},
    )
    tasks = [
        _normalise_netinsight_task(task, worker_payload)
        for task in (raw_tasks or [])
        if isinstance(task, dict) and _include_task(task, active_only=active_only)
    ]
    workers = [worker_payload]
    return tasks, workers


def _collect_stopword_tasks(*, active_only: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    task_dir = get_data_root() / "_stopword_suggestions" / "tasks"
    raw_worker = load_stopword_worker_status()
    worker_payload = _normalise_worker(
        source="stopword",
        source_label="排除词 Worker",
        payload=raw_worker,
    )
    tasks: List[Dict[str, Any]] = []
    for path in sorted(task_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        if not _include_task(payload, active_only=active_only):
            continue
        tasks.append(_normalise_stopword_task(payload, worker_payload))
    return tasks, [worker_payload]


def _collect_publisher_detection_tasks(*, active_only: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    task_dir = get_data_root() / "_publisher_detection" / "tasks"
    raw_worker = load_publisher_detection_worker_status()
    worker_payload = _normalise_worker(
        source="publisher-detection",
        source_label="异常发布者识别 Worker",
        payload=raw_worker,
    )
    tasks: List[Dict[str, Any]] = []
    for path in sorted(task_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        if not _include_task(payload, active_only=active_only):
            continue
        tasks.append(_normalise_publisher_detection_task(payload, worker_payload))
    return tasks, [worker_payload]


def _collect_postclean_tasks(*, active_only: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    jobs = list_postclean_jobs()
    tasks = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if not _include_task(job, active_only=active_only):
            continue
        tasks.append(_normalise_postclean_task(job))
    return tasks, []


def _collect_deduplicate_tasks(*, active_only: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    jobs = list_deduplicate_jobs()
    tasks = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if not _include_task(job, active_only=active_only):
            continue
        tasks.append(_normalise_deduplicate_task(job))
    return tasks, []


def _collect_fetch_refresh_tasks(*, active_only: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    jobs = list_fetch_refresh_jobs()
    worker_payload = _normalise_worker(
        source="fetch-refresh",
        source_label="缓存刷新 Worker",
        payload=load_fetch_refresh_worker_status(),
    )
    tasks = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if not _include_task(job, active_only=active_only):
            continue
        tasks.append(_normalise_fetch_refresh_task(job, worker_payload))
    return tasks, [worker_payload]


def _collect_rebuild_fetch_tasks(*, active_only: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    jobs = list_rebuild_fetch_jobs()
    tasks = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if not _include_task(job, active_only=active_only):
            continue
        tasks.append(_normalise_rebuild_fetch_task(job))
    return tasks, []


def _normalise_rebuild_fetch_task(task: Dict[str, Any]) -> Dict[str, Any]:
    progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    percentage = _safe_int(progress.get("percentage"), 0)
    total_tables = _safe_int(progress.get("total_tables"), 0)
    completed_tables = _safe_int(progress.get("completed_tables"), 0)
    uploaded_rows = _safe_int(progress.get("uploaded_rows"), 0)
    progress_text = f"{completed_tables} / {total_tables} 表" if total_tables > 0 else f"{percentage}%"
    if uploaded_rows > 0:
        progress_text = f"{progress_text} · {uploaded_rows} 条记录"
    status = _normalise_status(task.get("status"))
    return {
        "id": f"rebuild-fetch:{str(task.get('topic') or '').strip()}:{str(task.get('database') or '').strip()}:{str(task.get('fetch_date') or '').strip()}",
        "task_id": "",
        "source": "rebuild-fetch",
        "source_label": "缓存重建",
        "title": f"{str(task.get('database') or '数据库').strip()} 缓存重建",
        "scope": f"{str(task.get('fetch_date') or '').strip()}",
        "status": "failed" if status == "error" else status,
        "phase": "persist" if status == "running" else status,
        "phase_label": "重建中" if status == "running" else GENERIC_PHASE_LABELS.get(status, status or "处理中"),
        "message": str(task.get("message") or "").strip() or "等待处理。",
        "percentage": percentage,
        "progress_text": progress_text,
        "detail_text": str(progress.get("current_table") or "").strip(),
        "updated_at": str(task.get("updated_at") or "").strip(),
        "started_at": str(task.get("created_at") or "").strip(),
        "finished_at": str(task.get("finished_at") or "").strip(),
        "heartbeat_at": str(task.get("last_heartbeat") or task.get("updated_at") or "").strip(),
        "heartbeat_stale": _is_stale_timestamp(task.get("last_heartbeat") or task.get("updated_at")),
        "worker_pid": 0,
    }


def _normalise_report_task(task: Dict[str, Any], worker: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(task.get("id") or "").strip()
    topic = str(task.get("topic") or task.get("topic_identifier") or "").strip() or "报告任务"
    start = str(task.get("start") or "").strip()
    end = str(task.get("end") or start).strip() or start
    phase = str(task.get("phase") or "").strip() or "prepare"
    percentage = _safe_int(task.get("percentage"), 0)
    current_worker_task = str(worker.get("current_task_id") or "").strip()
    heartbeat_at = str(worker.get("last_heartbeat") or "").strip() if current_worker_task == task_id else str(task.get("updated_at") or "").strip()
    mode = str(task.get("mode") or "").strip() or "fast"
    return {
        "id": f"report:{task_id}",
        "task_id": task_id,
        "source": "report",
        "source_label": "报告生成",
        "title": f"{topic} 报告生成",
        "scope": f"{start} 至 {end}",
        "status": _normalise_status(task.get("status")),
        "phase": phase,
        "phase_label": REPORT_PHASE_LABELS.get(phase, phase or "处理中"),
        "message": str(task.get("message") or "").strip() or "等待处理。",
        "percentage": percentage,
        "progress_text": f"{percentage}%",
        "detail_text": mode == "research" and "research 模式" or "fast 模式",
        "updated_at": str(task.get("updated_at") or "").strip(),
        "started_at": str(task.get("started_at") or "").strip(),
        "finished_at": str(task.get("finished_at") or "").strip(),
        "heartbeat_at": heartbeat_at,
        "heartbeat_stale": _is_stale_timestamp(heartbeat_at),
        "worker_pid": _safe_int(task.get("worker_pid"), 0),
    }


def _normalise_netinsight_task(task: Dict[str, Any], worker: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(task.get("id") or "").strip()
    progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    phase = str(progress.get("phase") or task.get("status") or "").strip() or "queued"
    percentage = _safe_int(progress.get("percentage"), 0)
    fetched_total = _safe_int(progress.get("fetched_total"), 0)
    planned_total = _safe_int(progress.get("planned_total"), 0)
    counts_completed = _safe_int(progress.get("counts_completed"), 0)
    counts_total = _safe_int(progress.get("counts_total"), 0)
    progress_text = ""
    if planned_total > 0:
        progress_text = f"{fetched_total} / {planned_total}"
    elif counts_total > 0:
        progress_text = f"{counts_completed} / {counts_total}"
    else:
        progress_text = f"{percentage}%"
    config = task.get("config") if isinstance(task.get("config"), dict) else {}
    start = str(config.get("start_date") or "").strip()
    end = str(config.get("end_date") or "").strip()
    current_worker_task = str(worker.get("current_task_id") or "").strip()
    heartbeat_at = str(worker.get("last_heartbeat") or "").strip() if current_worker_task == task_id else str(task.get("updated_at") or "").strip()
    return {
        "id": f"netinsight:{task_id}",
        "task_id": task_id,
        "source": "netinsight",
        "source_label": "平台采集",
        "title": str(task.get("title") or task_id).strip() or "平台采集",
        "scope": f"{start} 至 {end}" if start and end else str(task.get("project") or "").strip(),
        "status": _normalise_status(task.get("status")),
        "phase": phase,
        "phase_label": GENERIC_PHASE_LABELS.get(phase, phase or "处理中"),
        "message": str(progress.get("message") or "").strip() or "等待处理。",
        "percentage": percentage,
        "progress_text": progress_text,
        "detail_text": str(task.get("project") or "").strip(),
        "updated_at": str(task.get("updated_at") or "").strip(),
        "started_at": str(task.get("started_at") or "").strip(),
        "finished_at": str(task.get("finished_at") or "").strip(),
        "heartbeat_at": heartbeat_at,
        "heartbeat_stale": _is_stale_timestamp(heartbeat_at),
        "worker_pid": _safe_int(worker.get("pid"), 0),
    }


def _normalise_stopword_task(task: Dict[str, Any], worker: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(task.get("id") or "").strip()
    summary = task.get("summary") if isinstance(task.get("summary"), dict) else {}
    phase = str(task.get("phase") or task.get("status") or "").strip() or "queued"
    percentage = _safe_int(task.get("percentage"), 0)
    processed_docs = _safe_int(summary.get("processed_docs"), 0)
    total_docs = _safe_int(summary.get("total_docs"), 0)
    processed_files = _safe_int(summary.get("processed_files"), 0)
    total_files = _safe_int(summary.get("total_files"), 0)
    if total_docs > 0:
        progress_text = f"{processed_docs} / {total_docs} 文档"
    elif total_files > 0:
        progress_text = f"{processed_files} / {total_files} 文件"
    else:
        progress_text = f"{percentage}%"
    stage = str(task.get("stage") or "pre").strip().lower() or "pre"
    current_worker_task = str(worker.get("current_task_id") or "").strip()
    heartbeat_at = str(worker.get("last_heartbeat") or "").strip() if current_worker_task == task_id else str(task.get("updated_at") or "").strip()
    return {
        "id": f"stopword:{task_id}",
        "task_id": task_id,
        "source": "stopword",
        "source_label": "排除词建议",
        "title": f"{str(task.get('topic_identifier') or '专题').strip()} 高频排除词",
        "scope": f"{str(task.get('date') or '').strip()} · {'预过滤' if stage == 'pre' else '后过滤'}",
        "status": _normalise_status(task.get("status")),
        "phase": phase,
        "phase_label": GENERIC_PHASE_LABELS.get(phase, phase or "处理中"),
        "message": str(task.get("message") or "").strip() or "等待处理。",
        "percentage": percentage,
        "progress_text": progress_text,
        "detail_text": str(summary.get("source_layer") or "").strip(),
        "updated_at": str(task.get("updated_at") or "").strip(),
        "started_at": str(task.get("started_at") or "").strip(),
        "finished_at": str(task.get("finished_at") or "").strip(),
        "heartbeat_at": heartbeat_at,
        "heartbeat_stale": _is_stale_timestamp(heartbeat_at),
        "worker_pid": _safe_int(task.get("worker_pid"), 0),
    }


def _normalise_postclean_task(task: Dict[str, Any]) -> Dict[str, Any]:
    progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    percentage = _safe_int(progress.get("percentage"), 0)
    total_tables = _safe_int(progress.get("total_tables"), 0)
    completed_tables = _safe_int(progress.get("completed_tables"), 0)
    deleted_rows = _safe_int(progress.get("deleted_rows"), 0)
    progress_text = f"{completed_tables} / {total_tables} 表" if total_tables > 0 else f"{percentage}%"
    if deleted_rows > 0:
        progress_text = f"{progress_text} · 删除 {deleted_rows} 条"
    status = _normalise_status(task.get("status"))
    return {
        "id": f"postclean:{str(task.get('topic') or '').strip()}:{str(task.get('database') or '').strip()}",
        "task_id": "",
        "source": "postclean",
        "source_label": "数据库后清洗",
        "title": f"{str(task.get('database') or '数据库').strip()} 后清洗",
        "scope": str(task.get("topic") or "").strip(),
        "status": "failed" if status == "error" else status,
        "phase": "persist" if status == "running" else status,
        "phase_label": "后清洗中" if status == "running" else GENERIC_PHASE_LABELS.get(status, status or "处理中"),
        "message": str(task.get("message") or "").strip() or "等待处理。",
        "percentage": percentage,
        "progress_text": progress_text,
        "detail_text": str(progress.get("current_table") or "").strip(),
        "updated_at": str(task.get("updated_at") or "").strip(),
        "started_at": str(task.get("started_at") or "").strip(),
        "finished_at": "",
        "heartbeat_at": str(task.get("last_heartbeat") or task.get("updated_at") or "").strip(),
        "heartbeat_stale": _is_stale_timestamp(task.get("last_heartbeat") or task.get("updated_at")),
        "worker_pid": 0,
    }


def _normalise_publisher_detection_task(task: Dict[str, Any], worker: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(task.get("id") or "").strip()
    progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    phase = str(task.get("phase") or task.get("status") or "").strip() or "queued"
    percentage = _safe_int(progress.get("percentage"), _safe_int(task.get("percentage"), 0))
    total_tables = _safe_int(progress.get("total_tables"), 0)
    completed_tables = _safe_int(progress.get("completed_tables"), 0)
    progress_text = f"{completed_tables} / {total_tables} 表" if total_tables > 0 else f"{percentage}%"
    publishers = result.get("publishers") if isinstance(result.get("publishers"), list) else []
    current_worker_task = str(worker.get("current_task_id") or "").strip()
    heartbeat_at = str(worker.get("last_heartbeat") or "").strip() if current_worker_task == task_id else str(task.get("updated_at") or "").strip()
    return {
        "id": f"publisher-detection:{task_id}",
        "task_id": task_id,
        "source": "publisher-detection",
        "source_label": "异常发布者识别",
        "title": f"{str(task.get('database') or '数据库').strip()} 发布者识别",
        "scope": str(task.get("topic_identifier") or "").strip(),
        "status": _normalise_status(task.get("status")),
        "phase": phase,
        "phase_label": "发布者识别中" if str(task.get("status") or "") == "running" else GENERIC_PHASE_LABELS.get(phase, phase or "处理中"),
        "message": str(task.get("message") or "").strip() or "等待处理。",
        "percentage": percentage,
        "progress_text": progress_text,
        "detail_text": str(progress.get("current_table") or "").strip() or (publishers and f"{len(publishers)} 个候选发布者" or ""),
        "updated_at": str(task.get("updated_at") or "").strip(),
        "started_at": str(task.get("started_at") or "").strip(),
        "finished_at": str(task.get("finished_at") or "").strip(),
        "heartbeat_at": heartbeat_at,
        "heartbeat_stale": _is_stale_timestamp(heartbeat_at),
        "worker_pid": _safe_int(task.get("worker_pid"), 0) or _safe_int(worker.get("pid"), 0),
    }


def _normalise_fetch_refresh_task(task: Dict[str, Any], worker: Dict[str, Any]) -> Dict[str, Any]:
    progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    percentage = _safe_int(progress.get("percentage"), 0)
    total_ranges = _safe_int(progress.get("total_ranges"), 0)
    completed_ranges = _safe_int(progress.get("completed_ranges"), 0)
    refreshed_rows = _safe_int(progress.get("refreshed_rows"), 0)
    progress_text = f"{completed_ranges} / {total_ranges} 批" if total_ranges > 0 else f"{percentage}%"
    if refreshed_rows > 0:
        progress_text = f"{progress_text} · {refreshed_rows} 条"
    status = _normalise_status(task.get("status"))
    current_worker_task = str(worker.get("current_task_id") or "").strip()
    task_id = f"{str(task.get('topic') or '').strip()}:{str(task.get('database') or '').strip()}"
    heartbeat_at = (
        str(worker.get("last_heartbeat") or "").strip()
        if current_worker_task == task_id
        else str(task.get("last_heartbeat") or task.get("updated_at") or "").strip()
    )
    return {
        "id": f"fetch-refresh:{task_id}",
        "task_id": task_id,
        "source": "fetch-refresh",
        "source_label": "本地缓存同步",
        "title": f"{str(task.get('database') or '数据库').strip()} 缓存刷新",
        "scope": str(task.get("topic") or "").strip(),
        "status": "failed" if status == "error" else status,
        "phase": "persist" if status == "running" else status,
        "phase_label": "刷新缓存中" if status == "running" else GENERIC_PHASE_LABELS.get(status, status or "处理中"),
        "message": str(task.get("message") or "").strip() or "等待处理。",
        "percentage": percentage,
        "progress_text": progress_text,
        "detail_text": str(progress.get("current_range") or "").strip(),
        "updated_at": str(task.get("updated_at") or "").strip(),
        "started_at": str(task.get("started_at") or "").strip(),
        "finished_at": str(task.get("finished_at") or "").strip(),
        "heartbeat_at": heartbeat_at,
        "heartbeat_stale": _is_stale_timestamp(heartbeat_at),
        "worker_pid": _safe_int(worker.get("pid"), 0),
    }


def _normalise_deduplicate_task(task: Dict[str, Any]) -> Dict[str, Any]:
    progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    percentage = _safe_int(progress.get("percentage"), 0)
    total_tables = _safe_int(progress.get("total_tables"), 0)
    completed_tables = _safe_int(progress.get("completed_tables"), 0)
    deleted_rows = _safe_int(progress.get("deleted_rows"), 0)
    restored_rows = _safe_int(progress.get("restored_rows"), 0)
    operation = str(task.get("operation") or "deduplicate").strip() or "deduplicate"
    progress_text = f"{completed_tables} / {total_tables} 表" if total_tables > 0 else f"{percentage}%"
    if operation == "restore" and restored_rows > 0:
        progress_text = f"{progress_text} · 恢复 {restored_rows} 条"
    elif deleted_rows > 0:
        progress_text = f"{progress_text} · 删除 {deleted_rows} 条"
    status = _normalise_status(task.get("status"))
    return {
        "id": f"deduplicate:{str(task.get('topic') or '').strip()}:{str(task.get('database') or '').strip()}",
        "task_id": "",
        "source": "deduplicate",
        "source_label": "数据库恢复" if operation == "restore" else "数据库去重",
        "title": f"{str(task.get('database') or '数据库').strip()} {'恢复' if operation == 'restore' else '去重'}",
        "scope": str(task.get("topic") or "").strip(),
        "status": "failed" if status == "error" else status,
        "phase": "restore" if operation == "restore" and status == "running" else "dedupe" if status == "running" else status,
        "phase_label": ("恢复处理中" if operation == "restore" else "去重处理中") if status == "running" else GENERIC_PHASE_LABELS.get(status, status or "处理中"),
        "message": str(task.get("message") or "").strip() or "等待处理。",
        "percentage": percentage,
        "progress_text": progress_text,
        "detail_text": str(progress.get("current_table") or "").strip(),
        "updated_at": str(task.get("updated_at") or "").strip(),
        "started_at": str(task.get("started_at") or "").strip(),
        "finished_at": "",
        "heartbeat_at": str(task.get("last_heartbeat") or task.get("updated_at") or "").strip(),
        "heartbeat_stale": _is_stale_timestamp(task.get("last_heartbeat") or task.get("updated_at")),
        "worker_pid": 0,
    }


def _normalise_worker(*, source: str, source_label: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    status = str(payload.get("status") or "").strip() or "idle"
    last_heartbeat = str(payload.get("last_heartbeat") or "").strip()
    return {
        "source": source,
        "source_label": source_label,
        "status": status,
        "running": bool(payload.get("running")),
        "pid": _safe_int(payload.get("pid"), 0),
        "current_task_id": str(payload.get("current_task_id") or "").strip(),
        "last_heartbeat": last_heartbeat,
        "heartbeat_stale": _is_stale_timestamp(last_heartbeat),
        "updated_at": str(payload.get("updated_at") or "").strip(),
    }


def _include_task(task: Dict[str, Any], *, active_only: bool) -> bool:
    status = _normalise_status(task.get("status"))
    if active_only:
        return status in ACTIVE_STATUSES
    return status in ACTIVE_STATUSES or status in TERMINAL_STATUSES


def _task_sort_key(task: Dict[str, Any]) -> Tuple[int, float]:
    status = str(task.get("status") or "")
    priority = 0
    if status == "running":
        priority = 0
    elif status == "queued":
        priority = 1
    elif status in {"failed", "error"}:
        priority = 2
    else:
        priority = 3
    return (priority, -_timestamp_to_sort_value(task.get("updated_at") or task.get("started_at") or ""))


def _worker_sort_key(worker: Dict[str, Any]) -> Tuple[int, float]:
    priority = 0 if worker.get("running") else 1
    return (priority, -_timestamp_to_sort_value(worker.get("last_heartbeat") or worker.get("updated_at") or ""))


def _normalise_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status or "queued"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return {}


def _timestamp_to_sort_value(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _is_stale_timestamp(value: Any) -> bool:
    timestamp = _timestamp_to_sort_value(value)
    if timestamp <= 0:
        return False
    return (datetime.now(timezone.utc).timestamp() - timestamp) > _HEARTBEAT_STALE_SECONDS
