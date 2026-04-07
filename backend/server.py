from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import sys
import time
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import Flask, Response, jsonify, request, send_file, stream_with_context
from flask_cors import CORS

# 注意：所有新的辅助函数请存放在 ``backend/server_support`` 包中，
# 并通过 ``from server_support import ...`` 或具体模块导入，保持 server.py 专注于路由逻辑。

BACKEND_DIR = Path(__file__).resolve().parent
SRC_DIR = BACKEND_DIR / "src"
for path in (BACKEND_DIR, SRC_DIR):
    s_path = str(path)
    if s_path not in sys.path:
        sys.path.insert(0, s_path)

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from src.project import (  # type: ignore
    get_dataset_date_summary,
    get_dataset_preview,
    get_project_manager,
    list_project_datasets,
    update_dataset_column_mapping,
    store_uploaded_dataset,
)
from src.utils.setting.paths import bucket, get_data_root, _normalise_topic  # type: ignore


from server_support import (  # type: ignore
    collect_layer_archives,
    collect_project_archives,
    collect_filter_status,
    error,
    evaluate_success,
    filter_ai_overview,
    build_settings_backup,
    restore_settings_backup,
    load_config,
    load_content_prompt_config,
    load_databases_config,
    load_filter_template_config,
    load_llm_config,
    load_rag_config,
    ensure_rag_ready,
    get_rag_build_status,
    ensure_routerrag_db,
    ensure_tagrag_db,
    list_project_routerrag_topics,
    list_project_tagrag_topics,
    start_rag_build,
    mask_api_keys,
    normalise_topic_label,
    parse_column_mapping_from_form,
    parse_column_mapping_payload,
    persist_databases_config,
    persist_content_prompt_config,
    persist_filter_template_config,
    persist_llm_config,
    persist_rag_config,
    prepare_pipeline_args,
    resolve_topic_identifier,
    resolve_stage_processing_date,
    require_fields,
    serialise_result,
    success,
    split_folder_range,
    validate_rag_config,
    DATA_PROJECTS_ROOT,
    create_deduplicate_job,
    create_fetch_refresh_job,
    create_rebuild_fetch_job,
    get_fetch_refresh_job,
    get_deduplicate_job,
    get_rebuild_fetch_job,
    heartbeat_fetch_refresh_job,
    heartbeat_deduplicate_job,
    heartbeat_rebuild_fetch_job,
    mark_filter_job_running,
    mark_filter_job_finished,
    create_postclean_job,
    get_postclean_job,
    heartbeat_postclean_job,
    update_deduplicate_job,
    update_fetch_refresh_job,
    update_fetch_refresh_worker,
    update_postclean_job,
    update_rebuild_fetch_job,
    get_default_rag_config,
)
from server_support.router_prompts.utils import (
    load_router_prompt_config,
    persist_router_prompt_config,
)
from server_support.settings_config import register_settings_endpoints
from server_support.hot_overview import (
    get_today_hot_overview,
    list_hot_overview_history,
    rollback_hot_overview_revision,
    reclassify_hot_overview,
)
from server_support.stopword_suggestions import (
    build_status_payload as build_stopword_suggestion_status_payload,
    cancel_task as cancel_stopword_task,
    create_or_reuse_task as create_stopword_suggestion_task,
    delete_task as delete_stopword_task,
)
from server_support.publisher_detection import (
    build_status_payload as build_publisher_detection_status_payload,
    cancel_task as cancel_publisher_detection_task,
    create_or_reuse_task as create_publisher_detection_task,
    delete_task as delete_publisher_detection_task,
)
from server_support.deduplicate_jobs import (
    cancel_deduplicate_job,
    delete_deduplicate_job,
)
from server_support.postclean_jobs import (
    cancel_postclean_job,
    delete_postclean_job,
)

PROJECT_MANAGER = get_project_manager()


from server_support.ops import _execute_operation, _log_with_context


def _resolve_filter_status_inputs(
    topic_param: str, project_param: str, dataset_id_param: str, date_param: str
) -> Tuple[str, str, Optional[str]]:
    if not topic_param and not project_param and not dataset_id_param:
        raise ValueError("Missing required field(s): topic/project/dataset_id")

    resolution_payload: Dict[str, Any] = {}
    if topic_param:
        resolution_payload["topic"] = topic_param
    if project_param:
        resolution_payload["project"] = project_param
    if dataset_id_param:
        resolution_payload["dataset_id"] = dataset_id_param

    topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    resolved_date, fallback_from = resolve_stage_processing_date(topic_identifier, "filter", date_param or None)
    return topic_identifier, resolved_date, fallback_from


def _build_filter_status_payload(
    topic_identifier: str,
    resolved_date: str,
    fallback_from: Optional[str],
) -> Dict[str, Any]:
    status_payload = collect_filter_status(topic_identifier, resolved_date)
    status_payload["ai_config"] = filter_ai_overview()
    if fallback_from:
        context = status_payload.setdefault("context", {})
        if isinstance(context, dict):
            context["resolved_date"] = resolved_date
            context["requested_date"] = fallback_from
    return status_payload


def _resolve_stopword_suggestion_inputs(
    topic_param: str,
    project_param: str,
    dataset_id_param: str,
    date_param: str,
    stage_param: str,
) -> Tuple[str, str, str]:
    if not topic_param and not project_param and not dataset_id_param:
        raise ValueError("Missing required field(s): topic/project/dataset_id")

    resolution_payload: Dict[str, Any] = {}
    if topic_param:
        resolution_payload["topic"] = topic_param
    if project_param:
        resolution_payload["project"] = project_param
    if dataset_id_param:
        resolution_payload["dataset_id"] = dataset_id_param

    topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    stage = stage_param if stage_param in {"pre", "post"} else "pre"
    date_value = str(date_param or "").strip()
    if date_value:
        return topic_identifier, date_value, stage

    priorities = ("clean", "fetch") if stage == "pre" else ("filter", "clean", "fetch")
    for layer in priorities:
        archives = collect_layer_archives(topic_identifier, layer)
        for archive in archives:
            candidate = str((archive or {}).get("date") or "").strip()
            if candidate:
                return topic_identifier, candidate, stage

    raise ValueError("未找到可用的数据存档，请先拉取数据或完成预处理。")


def _submit_filter_job(
    run_callable: Callable[[str, str, Optional[Any]], Any],
    *,
    topic_identifier: str,
    resolved_date: str,
    log_project: str,
    display_name: str,
) -> concurrent.futures.Future:
    """
    Execute the filter pipeline in a worker thread so that the API request
    can return immediately while streaming endpoints keep receiving updates.
    """

    def _job():
        try:
            _execute_operation(
                "filter",
                run_callable,
                topic_identifier,
                resolved_date,
                log_context={
                    "project": log_project,
                    "params": {
                        "date": resolved_date,
                        "source": "api",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
        except Exception:  # pragma: no cover - background diagnostics
            LOGGER.exception("Filter job failed for %s@%s", topic_identifier, resolved_date)
        finally:
            mark_filter_job_finished(topic_identifier, resolved_date)

    return FILTER_EXECUTOR.submit(_job)


def _submit_postclean_job(
    *,
    topic_identifier: str,
    database: str,
    tables: Optional[List[str]],
    log_project: str,
    display_name: str,
) -> concurrent.futures.Future:
    def _job():
        stop_event = threading.Event()

        def _heartbeat_loop():
            while not stop_event.wait(2.0):
                heartbeat_postclean_job(topic_identifier, database, tables)

        def _on_progress(event: str, message: str, payload: Dict[str, Any]) -> None:
            progress_payload = {
                "total_tables": int(payload.get("total_tables") or 0),
                "completed_tables": int(payload.get("completed_tables") or 0),
                "deleted_rows": int(payload.get("deleted_rows") or 0),
                "current_table": str(payload.get("table") or "").strip(),
                "percentage": int(payload.get("percentage") or 0),
            }
            update_postclean_job(
                topic_identifier,
                database,
                tables,
                message=message,
                progress=progress_payload,
                log_message=message,
                log_event=event,
                log_level="error" if event == "task.failed" else "info",
            )

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"postclean-heartbeat-{topic_identifier}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            from src.filter import run_database_postclean  # type: ignore

            result = run_database_postclean(
                topic_identifier,
                database,
                tables=tables,
                progress_callback=_on_progress,
            )
            success = evaluate_success(result)
            _log_with_context(
                "database-postclean",
                success,
                {
                    "project": log_project,
                    "params": {
                        "database": database,
                        "tables": tables or [],
                        "source": "api",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
            serialised = serialise_result(result)
            follow_up_payload: Optional[Dict[str, Any]] = None
            if success and isinstance(serialised, dict):
                deleted_rows = int(serialised.get("deleted_rows") or 0)
                if deleted_rows > 0:
                    follow_up_payload = _enqueue_fetch_refresh_job(
                        topic_identifier=topic_identifier,
                        database=database,
                        log_project=log_project,
                        display_name=display_name,
                    )
                else:
                    follow_up_payload = {
                        "status": "skipped",
                        "message": "本次后清洗未删除记录，未触发本地缓存刷新。",
                        "ranges": [],
                    }
                serialised["follow_up"] = follow_up_payload
            success_message = (
                f"后清洗完成，共删除 {int(serialised.get('deleted_rows') or 0)} 条记录。"
                if success and isinstance(serialised, dict)
                else str((serialised or {}).get("message") if isinstance(serialised, dict) else serialised or "后清洗失败")
            )
            if success and isinstance(follow_up_payload, dict):
                follow_up_message = str(follow_up_payload.get("message") or "").strip()
                if follow_up_message:
                    success_message = f"{success_message} {follow_up_message}"
            update_postclean_job(
                topic_identifier,
                database,
                tables,
                status="completed" if success else "error",
                message=success_message,
                progress={"percentage": 100 if success else 0},
                result=serialised,
                log_message=success_message,
                log_event="task.completed" if success else "task.failed",
                log_level="info" if success else "error",
            )
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Postclean job failed for %s@%s", topic_identifier, database)
            detail = str(exc)
            _log_with_context(
                "database-postclean",
                False,
                {
                    "project": log_project,
                    "params": {
                        "database": database,
                        "tables": tables or [],
                        "source": "api",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
            update_postclean_job(
                topic_identifier,
                database,
                tables,
                status="error",
                message=detail,
                log_message=detail,
                log_event="task.failed",
                log_level="error",
            )
        finally:
            stop_event.set()
            heartbeat_postclean_job(topic_identifier, database, tables)

    return POSTCLEAN_EXECUTOR.submit(_job)


def _submit_deduplicate_job(
    *,
    topic_identifier: str,
    database: str,
    tables: Optional[List[str]],
    log_project: str,
    display_name: str,
) -> concurrent.futures.Future:
    def _job():
        stop_event = threading.Event()

        def _heartbeat_loop():
            while not stop_event.wait(2.0):
                heartbeat_deduplicate_job(topic_identifier, database, tables)

        def _on_progress(event: str, message: str, payload: Dict[str, Any]) -> None:
            progress_payload = {
                "total_tables": int(payload.get("total_tables") or 0),
                "completed_tables": int(payload.get("completed_tables") or 0),
                "deleted_rows": int(payload.get("deleted_rows") or 0),
                "current_table": str(payload.get("table") or "").strip(),
                "percentage": int(payload.get("percentage") or 0),
            }
            update_deduplicate_job(
                topic_identifier,
                database,
                tables,
                message=message,
                progress=progress_payload,
                log_message=message,
                log_event=event,
                log_level="error" if event == "task.failed" else "info",
            )

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"deduplicate-heartbeat-{topic_identifier}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            from src.filter import run_database_deduplicate  # type: ignore

            result = run_database_deduplicate(
                topic_identifier,
                database,
                tables=tables,
                progress_callback=_on_progress,
            )
            success = evaluate_success(result)
            _log_with_context(
                "database-deduplicate",
                success,
                {
                    "project": log_project,
                    "params": {
                        "database": database,
                        "tables": tables or [],
                        "source": "api",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
            serialised = serialise_result(result)
            follow_up_payload: Optional[Dict[str, Any]] = None
            if success and isinstance(serialised, dict):
                deleted_rows = int(serialised.get("deleted_rows") or 0)
                if deleted_rows > 0:
                    follow_up_payload = _enqueue_fetch_refresh_job(
                        topic_identifier=topic_identifier,
                        database=database,
                        log_project=log_project,
                        display_name=display_name,
                    )
                else:
                    follow_up_payload = {
                        "status": "skipped",
                        "message": "本次数据库去重未删除记录，未触发本地缓存刷新。",
                        "ranges": [],
                    }
                serialised["follow_up"] = follow_up_payload
            success_message = (
                f"数据库去重完成，共删除 {int(serialised.get('deleted_rows') or 0)} 条重复记录。"
                if success and isinstance(serialised, dict)
                else str((serialised or {}).get("message") if isinstance(serialised, dict) else serialised or "数据库去重失败")
            )
            if success and isinstance(follow_up_payload, dict):
                follow_up_message = str(follow_up_payload.get("message") or "").strip()
                if follow_up_message:
                    success_message = f"{success_message} {follow_up_message}"
            update_deduplicate_job(
                topic_identifier,
                database,
                tables,
                status="completed" if success else "error",
                message=success_message,
                progress={"percentage": 100 if success else 0},
                result=serialised,
                log_message=success_message,
                log_event="task.completed" if success else "task.failed",
                log_level="info" if success else "error",
            )
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Deduplicate job failed for %s@%s", topic_identifier, database)
            detail = str(exc)
            _log_with_context(
                "database-deduplicate",
                False,
                {
                    "project": log_project,
                    "params": {
                        "database": database,
                        "tables": tables or [],
                        "source": "api",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
            update_deduplicate_job(
                topic_identifier,
                database,
                tables,
                status="error",
                message=detail,
                log_message=detail,
                log_event="task.failed",
                log_level="error",
            )
        finally:
            stop_event.set()
            heartbeat_deduplicate_job(topic_identifier, database, tables)

    return DEDUPLICATE_EXECUTOR.submit(_job)


def _build_fetch_refresh_ranges(topic_identifier: str) -> List[Dict[str, str]]:
    ranges: List[Dict[str, str]] = []
    seen: set[str] = set()
    for archive in collect_layer_archives(topic_identifier, "fetch"):
        folder = str((archive or {}).get("date") or "").strip()
        if not folder or folder in seen:
            continue
        start, end = split_folder_range(folder)
        if not start:
            continue
        seen.add(folder)
        ranges.append({
            "folder": folder,
            "start": start,
            "end": end or start,
        })
    return ranges


def _submit_fetch_refresh_job(
    *,
    topic_identifier: str,
    database: str,
    ranges: List[Dict[str, str]],
    log_project: str,
    display_name: str,
) -> concurrent.futures.Future:
    def _job():
        stop_event = threading.Event()
        task_id = f"{topic_identifier}:{database}"

        def _heartbeat_loop():
            while not stop_event.wait(2.0):
                heartbeat_fetch_refresh_job(topic_identifier, database)
                update_fetch_refresh_worker(
                    status="running",
                    running=True,
                    current_task_id=task_id,
                    heartbeat=True,
                )

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"fetch-refresh-heartbeat-{topic_identifier}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            from src.fetch import run_fetch  # type: ignore

            total_ranges = len(ranges)
            refreshed_rows = 0
            completed_ranges = 0
            refreshed_ranges: List[Dict[str, Any]] = []
            failed_ranges: List[Dict[str, Any]] = []

            update_fetch_refresh_worker(
                status="running",
                running=True,
                pid=os.getpid(),
                current_task_id=task_id,
                heartbeat=True,
            )
            update_fetch_refresh_job(
                topic_identifier,
                database,
                status="running",
                ranges=ranges,
                message=f"准备刷新 {total_ranges} 个本地缓存批次。",
                progress={
                    "total_ranges": total_ranges,
                    "completed_ranges": 0,
                    "refreshed_rows": 0,
                    "current_range": "",
                    "percentage": 0,
                },
                log_message=f"准备刷新 {total_ranges} 个本地缓存批次。",
                log_event="task.started",
            )

            for index, item in enumerate(ranges, start=1):
                folder = str(item.get("folder") or "").strip()
                start = str(item.get("start") or "").strip()
                end = str(item.get("end") or start).strip() or start
                update_fetch_refresh_job(
                    topic_identifier,
                    database,
                    message=f"开始刷新缓存批次 {folder}。",
                    progress={
                        "total_ranges": total_ranges,
                        "completed_ranges": completed_ranges,
                        "refreshed_rows": refreshed_rows,
                        "current_range": folder,
                        "percentage": round((completed_ranges / max(1, total_ranges)) * 100),
                    },
                    log_message=f"开始刷新缓存批次 {folder}。",
                    log_event="range.started",
                )
                result = run_fetch(
                    topic_identifier,
                    start,
                    end,
                    db_topic=database,
                )
                serialised = serialise_result(result)
                success = evaluate_success(result)
                count = int(serialised.get("count") or 0) if isinstance(serialised, dict) else 0
                completed_ranges += 1
                if success:
                    refreshed_rows += count
                    refreshed_ranges.append({
                        "folder": folder,
                        "start": start,
                        "end": end,
                        "count": count,
                    })
                    update_fetch_refresh_job(
                        topic_identifier,
                        database,
                        message=f"{folder} 刷新完成，共同步 {count} 条记录。",
                        progress={
                            "total_ranges": total_ranges,
                            "completed_ranges": completed_ranges,
                            "refreshed_rows": refreshed_rows,
                            "current_range": folder,
                            "percentage": round((completed_ranges / max(1, total_ranges)) * 100),
                        },
                        log_message=f"{folder} 刷新完成，共同步 {count} 条记录。",
                        log_event="range.completed",
                    )
                else:
                    failure_message = (
                        str(serialised.get("message") or "").strip()
                        if isinstance(serialised, dict)
                        else str(serialised or "缓存刷新失败")
                    ) or "缓存刷新失败"
                    failed_ranges.append({
                        "folder": folder,
                        "start": start,
                        "end": end,
                        "message": failure_message,
                    })
                    update_fetch_refresh_job(
                        topic_identifier,
                        database,
                        message=f"{folder} 刷新失败：{failure_message}",
                        progress={
                            "total_ranges": total_ranges,
                            "completed_ranges": completed_ranges,
                            "refreshed_rows": refreshed_rows,
                            "current_range": folder,
                            "percentage": round((completed_ranges / max(1, total_ranges)) * 100),
                        },
                        log_message=f"{folder} 刷新失败：{failure_message}",
                        log_event="range.failed",
                        log_level="error",
                    )

            overall_success = len(failed_ranges) == 0
            result_payload = {
                "topic": topic_identifier,
                "database": database,
                "ranges": ranges,
                "refreshed_ranges": refreshed_ranges,
                "failed_ranges": failed_ranges,
                "refreshed_rows": refreshed_rows,
            }
            _log_with_context(
                "fetch-refresh",
                overall_success,
                {
                    "project": log_project,
                    "params": {
                        "database": database,
                        "ranges": [item.get("folder") for item in ranges],
                        "source": "postclean-auto",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
            final_message = (
                f"本地缓存刷新完成，共处理 {completed_ranges} 个批次，累计同步 {refreshed_rows} 条记录。"
                if overall_success
                else f"本地缓存刷新部分失败，已完成 {completed_ranges} / {total_ranges} 个批次。"
            )
            update_fetch_refresh_job(
                topic_identifier,
                database,
                status="completed" if overall_success else "error",
                message=final_message,
                progress={
                    "total_ranges": total_ranges,
                    "completed_ranges": completed_ranges,
                    "refreshed_rows": refreshed_rows,
                    "current_range": "",
                    "percentage": 100,
                },
                result=result_payload,
                log_message=final_message,
                log_event="task.completed" if overall_success else "task.failed",
                log_level="info" if overall_success else "error",
            )
        except Exception as exc:  # pragma: no cover - background diagnostics
            LOGGER.exception("Fetch refresh job failed for %s@%s", topic_identifier, database)
            detail = str(exc)
            _log_with_context(
                "fetch-refresh",
                False,
                {
                    "project": log_project,
                    "params": {
                        "database": database,
                        "ranges": [item.get("folder") for item in ranges],
                        "source": "postclean-auto",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
            update_fetch_refresh_job(
                topic_identifier,
                database,
                status="error",
                message=detail,
                progress={"current_range": "", "percentage": 0},
                log_message=detail,
                log_event="task.failed",
                log_level="error",
            )
        finally:
            stop_event.set()
            heartbeat_fetch_refresh_job(topic_identifier, database)
            update_fetch_refresh_worker(
                status="idle",
                running=False,
                current_task_id="",
                heartbeat=True,
            )

    return FETCH_REFRESH_EXECUTOR.submit(_job)


def _submit_rebuild_fetch_job(
    *,
    topic_identifier: str,
    database: str,
    fetch_date: str,
    date: str,
    log_project: str,
    display_name: str,
) -> concurrent.futures.Future:
    """提交 fetch 重建后台任务"""
    def _job():
        stop_event = threading.Event()

        def _heartbeat_loop():
            while not stop_event.wait(2.0):
                heartbeat_rebuild_fetch_job(topic_identifier, database, fetch_date)

        def _on_progress(event: str, message: str, payload: Dict[str, Any]) -> None:
            progress_payload = {
                "total_tables": int(payload.get("total_tables") or 0),
                "completed_tables": int(payload.get("completed_tables") or 0),
                "uploaded_rows": int(payload.get("uploaded_rows") or 0),
                "current_table": str(payload.get("table") or "").strip(),
                "percentage": int(payload.get("percentage") or 0),
            }
            update_rebuild_fetch_job(
                topic_identifier,
                database,
                fetch_date,
                message=message,
                progress=progress_payload,
                log_message=message,
                log_event=event,
                log_level="error" if event == "task.failed" else "info",
            )

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"rebuild-fetch-heartbeat-{topic_identifier}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            # 更新状态为运行中
            update_rebuild_fetch_job(
                topic_identifier,
                database,
                fetch_date,
                status="running",
                message="开始从本地缓存重建数据库...",
            )

            from src.update import run_update

            result = run_update(
                topic_identifier,
                date,
                dataset_name=database,
                rebuild_from_fetch=True,
                fetch_date=fetch_date,
            )
            success = evaluate_success(result)
            _log_with_context(
                "rebuild-fetch",
                success,
                {
                    "project": log_project,
                    "params": {
                        "database": database,
                        "fetch_date": fetch_date,
                        "date": date,
                        "source": "api",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
            serialised = serialise_result(result)
            update_rebuild_fetch_job(
                topic_identifier,
                database,
                fetch_date,
                status="completed" if success else "error",
                message=serialised.get("message", "") if isinstance(serialised, dict) else str(result),
                progress={"percentage": 100 if success else 0},
                result=serialised,
                log_message=serialised.get("message", "") if isinstance(serialised, dict) else str(result),
                log_event="task.completed" if success else "task.failed",
                log_level="info" if success else "error",
            )
        except Exception as exc:
            LOGGER.exception("Rebuild fetch job failed for %s@%s", topic_identifier, database)
            update_rebuild_fetch_job(
                topic_identifier,
                database,
                fetch_date,
                status="error",
                message=str(exc),
                log_message=str(exc),
                log_event="task.failed",
                log_level="error",
            )
        finally:
            stop_event.set()
            heartbeat_rebuild_fetch_job(topic_identifier, database, fetch_date)

    return REBUILD_FETCH_EXECUTOR.submit(_job)


def _enqueue_fetch_refresh_job(
    *,
    topic_identifier: str,
    database: str,
    log_project: str,
    display_name: str,
) -> Dict[str, Any]:
    ranges = _build_fetch_refresh_ranges(topic_identifier)
    if not ranges:
        return {
            "status": "skipped",
            "message": "当前项目暂无可刷新的本地缓存批次。",
            "ranges": [],
        }

    existing = get_fetch_refresh_job(topic_identifier, database)
    if existing and str(existing.get("status") or "").strip() in {"queued", "running"}:
        return {
            "status": "queued",
            "reused": True,
            "message": existing.get("message") or "本地缓存刷新任务已在后台运行。",
            "ranges": existing.get("ranges") or ranges,
            "task": existing,
        }

    payload = create_fetch_refresh_job(topic_identifier, database, ranges)
    _submit_fetch_refresh_job(
        topic_identifier=topic_identifier,
        database=database,
        ranges=ranges,
        log_project=log_project,
        display_name=display_name,
    )
    return {
        "status": "queued",
        "reused": False,
        "message": f"已自动提交本地缓存刷新任务，共 {len(ranges)} 个批次待处理。",
        "ranges": ranges,
        "task": payload,
    }


from src.fluid.api import fluid_bp
from src.analyze.api import analyze_bp
from src.topic.api import topic_bp
from src.report.api import report_bp
import threading as _threading

from src.netinsight import cancel_task as cancel_netinsight_task
from src.netinsight import create_task as create_netinsight_task
from src.netinsight import delete_task as delete_netinsight_task
from src.netinsight import ensure_worker_running as ensure_netinsight_worker
from src.netinsight import get_task as get_netinsight_task
from src.netinsight import list_tasks as list_netinsight_tasks
from src.netinsight import load_worker_status as load_netinsight_worker_status
from src.netinsight import plan_task_from_brief
from src.netinsight import read_login_state as read_netinsight_login_state
from src.netinsight import write_session_state as write_netinsight_session_state
from src.netinsight import resolve_task_output_file as resolve_netinsight_task_output_file
from src.netinsight import retry_task as retry_netinsight_task
from src.netinsight import write_login_state as write_netinsight_login_state

app = Flask(__name__)
app.register_blueprint(fluid_bp, url_prefix='/api/fluid')
app.register_blueprint(analyze_bp, url_prefix='/api/analyze')
app.register_blueprint(topic_bp, url_prefix='/api/topic')
app.register_blueprint(report_bp, url_prefix='/api/report')
CORS(app)

CONFIG = load_config()

DATABASES_CONFIG_NAME = "databases"
LLM_CONFIG_NAME = "llm"
FILTER_STATUS_STREAM_INTERVAL = 1.0
FILTER_STATUS_STREAM_TIMEOUT = 300.0
FILTER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2)
POSTCLEAN_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
DEDUPLICATE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
FETCH_REFRESH_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
REBUILD_FETCH_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)


def _resolve_runtime_binding() -> Tuple[str, int]:
    """Determine which host/port the Flask app should bind to."""

    host = "0.0.0.0"

    port_value = os.environ.get("OPINION_BACKEND_PORT")
    if port_value:
        try:
            port = int(port_value)
        except ValueError:
            LOGGER.warning(
                "Invalid OPINION_BACKEND_PORT=%s provided. Falling back to 8000.",
                port_value,
            )
            port = 8000
    else:
        port = 8000

    return host, port


def _load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            fh.seek(0)
            return fh.read()


def _run_data_pipeline(topic: str, date: str, *, project: Optional[str] = None, topic_label: Optional[str] = None) -> Dict[str, Any]:
    """
    Run Merge → Clean sequentially.

    Args:
        topic: Project/topic identifier.
        date: Date string in YYYY-MM-DD format.
        project: Canonical project name used for logging.
        topic_label: Optional display name recorded in logs.

    Returns:
        Dict[str, Any]: Structured status report with per-step results.
    """
    from src.merge import run_merge  # type: ignore
    from src.clean import run_clean  # type: ignore

    pipeline_steps = [
        ("merge", run_merge),
        ("clean", run_clean),
    ]

    log_project = project or topic
    params: Dict[str, Any] = {
        "date": date,
        "source": "api.pipeline",
        "bucket": topic,
    }
    if topic_label:
        params["topic"] = topic_label

    step_context = {
        "project": log_project,
        "params": {
            **params,
        },
    }
    steps: List[Dict[str, Any]] = []

    for name, func in pipeline_steps:
        result = func(topic, date)
        success = evaluate_success(result)
        steps.append({
            "operation": name,
            "success": success,
            "result": serialise_result(result),
        })
        _log_with_context(name, success, step_context)

        if not success:
            return {
                "status": "error",
                "message": f"{name} 步骤执行失败",
                "steps": steps,
            }

    return {
        "status": "ok",
        "steps": steps,
    }


@app.get("/api/status")
def status():
    return jsonify({
        "status": "ok",
        "message": "OpinionSystem backend is running",
        "config": {
            "backend": CONFIG.get("backend", {}),
        },
    })


@app.get("/api/system/background-tasks")
def system_background_tasks():
    active_only_raw = str(request.args.get("active_only") or "1").strip().lower()
    active_only = active_only_raw not in {"0", "false", "no", "off"}
    try:
        limit = max(1, min(int(request.args.get("limit") or 20), 50))
    except ValueError:
        return error("Field 'limit' must be an integer", 400)

    try:
        from server_support.background_tasks import collect_background_task_payload

        payload = collect_background_task_payload(active_only=active_only, limit=limit)
    except Exception as exc:
        LOGGER.exception("Failed to collect background tasks")
        return error(f"读取后台任务状态失败: {str(exc)}", 500)
    return success({"data": payload})


@app.post("/api/system/background-tasks/<string:task_id>/cancel")
def system_cancel_background_task(task_id: str):
    """统一取消后台任务 API

    task_id 格式: <source>:<id>
    例如:
    - netinsight:ni-20250101-120000-abc123
    - report:report-20250101-120000-abc123
    - stopword:sw-20250101-120000-abc123
    - publisher-detection:pd-20250101-120000-abc123
    - deduplicate:<topic>:<database>
    - postclean:<topic>:<database>
    - fetch-refresh:<topic>:<database>
    """
    if not task_id or ":" not in task_id:
        return error("无效的任务ID格式", 400)

    parts = task_id.split(":", 1)
    source = parts[0]
    actual_id = parts[1]

    try:
        if source == "netinsight":
            from src.netinsight import cancel_task as cancel_netinsight_task
            task = cancel_netinsight_task(actual_id)
            return success({"data": task})

        elif source == "report":
            from src.report.task_queue import cancel_task as cancel_report_task
            task = cancel_report_task(actual_id)
            return success({"data": task})

        elif source == "stopword":
            task = cancel_stopword_task(actual_id)
            return success({"data": task})

        elif source == "publisher-detection":
            task = cancel_publisher_detection_task(actual_id)
            return success({"data": task})

        elif source == "deduplicate":
            # deduplicate id format: <topic>:<database>
            sub_parts = actual_id.split(":", 1)
            if len(sub_parts) != 2:
                return error("无效的去重任务ID格式", 400)
            topic, database = sub_parts
            result = cancel_deduplicate_job(topic, database)
            if result is None:
                return error("未找到去重任务", 404)
            return success({"data": result})

        elif source == "postclean":
            # postclean id format: <topic>:<database>
            sub_parts = actual_id.split(":", 1)
            if len(sub_parts) != 2:
                return error("无效的后清洗任务ID格式", 400)
            topic, database = sub_parts
            result = cancel_postclean_job(topic, database)
            if result is None:
                return error("未找到后清洗任务", 404)
            return success({"data": result})

        else:
            return error(f"不支持的任务类型: {source}", 400)

    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 409)
    except Exception as exc:
        LOGGER.exception("Failed to cancel background task: %s", task_id)
        return error(f"取消任务失败: {str(exc)}", 500)


@app.delete("/api/system/background-tasks/<string:task_id>")
def system_delete_background_task(task_id: str):
    """统一删除后台任务 API（只能删除已结束的任务）

    task_id 格式与取消API相同
    """
    if not task_id or ":" not in task_id:
        return error("无效的任务ID格式", 400)

    parts = task_id.split(":", 1)
    source = parts[0]
    actual_id = parts[1]

    try:
        if source == "netinsight":
            from src.netinsight import delete_task as delete_netinsight_task
            delete_netinsight_task(actual_id)
            return success({"data": {"deleted": task_id}})

        elif source == "report":
            # report 任务暂不支持删除
            return error("报告任务暂不支持删除", 400)

        elif source == "stopword":
            delete_stopword_task(actual_id)
            return success({"data": {"deleted": task_id}})

        elif source == "publisher-detection":
            delete_publisher_detection_task(actual_id)
            return success({"data": {"deleted": task_id}})

        elif source == "deduplicate":
            sub_parts = actual_id.split(":", 1)
            if len(sub_parts) != 2:
                return error("无效的去重任务ID格式", 400)
            topic, database = sub_parts
            deleted = delete_deduplicate_job(topic, database)
            return success({"data": {"deleted": task_id, "found": deleted}})

        elif source == "postclean":
            sub_parts = actual_id.split(":", 1)
            if len(sub_parts) != 2:
                return error("无效的后清洗任务ID格式", 400)
            topic, database = sub_parts
            deleted = delete_postclean_job(topic, database)
            return success({"data": {"deleted": task_id, "found": deleted}})

        else:
            return error(f"不支持的任务类型: {source}", 400)

    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 409)
    except Exception as exc:
        LOGGER.exception("Failed to delete background任务: %s", task_id)
        return error(f"删除任务失败: {str(exc)}", 500)


@app.get("/api/config")
def get_config():
    return jsonify(CONFIG)


@app.get("/api/home/today-hot-overview")
def home_today_hot_overview():
    limit_raw = str(request.args.get("limit", "") or "").strip()
    refresh_raw = str(request.args.get("refresh", "") or "").strip().lower()
    mode_raw = str(request.args.get("mode", "") or "").strip().lower()
    research_raw = str(request.args.get("research", "") or "").strip().lower()
    force_refresh = refresh_raw in {"1", "true", "yes", "on"}
    mode = mode_raw if mode_raw in {"fast", "research"} else "fast"
    if not mode_raw and research_raw in {"1", "true", "yes", "on"}:
        mode = "research"
    limit = 12
    if limit_raw:
        try:
            limit = int(limit_raw)
        except ValueError:
            return error("Invalid 'limit' parameter, expected integer")

    LOGGER.info(
        "API /api/home/today-hot-overview called | limit=%s force_refresh=%s mode=%s ip=%s",
        limit,
        force_refresh,
        mode,
        request.remote_addr,
    )

    try:
        payload = get_today_hot_overview(
            limit=limit,
            force_refresh=force_refresh,
            mode=mode,
        )
        LOGGER.info(
            "API /api/home/today-hot-overview success | total_items=%s summary_source=%s revision_id=%s",
            int(payload.get("total_items") or 0),
            payload.get("summary_source"),
            payload.get("revision_id"),
        )
        return success({"data": payload})
    except Exception as exc:
        LOGGER.exception("Failed to build today's hot overview")
        return error(f"Failed to build today's hot overview: {str(exc)}", 500)


@app.get("/api/home/today-hot-overview/history")
def home_today_hot_overview_history():
    mode_raw = str(request.args.get("mode", "") or "").strip().lower()
    research_raw = str(request.args.get("research", "") or "").strip().lower()
    limit_raw = str(request.args.get("limit", "") or "").strip()
    mode = mode_raw if mode_raw in {"fast", "research"} else "fast"
    if not mode_raw and research_raw in {"1", "true", "yes", "on"}:
        mode = "research"
    limit = 10
    if limit_raw:
        try:
            limit = int(limit_raw)
        except ValueError:
            return error("Invalid 'limit' parameter, expected integer")

    records = list_hot_overview_history(mode=mode, limit=limit)
    LOGGER.info(
        "API /api/home/today-hot-overview/history success | mode=%s records=%s",
        mode,
        len(records),
    )
    return success({"data": {"records": records, "total": len(records)}})


@app.post("/api/home/today-hot-overview/rollback")
def home_today_hot_overview_rollback():
    payload = request.get_json(silent=True) or {}
    revision_id = str(payload.get("revision_id") or "").strip()
    mode_raw = str(payload.get("mode") or "").strip().lower()
    mode = mode_raw if mode_raw in {"fast", "research"} else "fast"
    if not mode_raw and str(payload.get("research") or "").strip().lower() in {"1", "true", "yes", "on"}:
        mode = "research"
    if not revision_id:
        return error("Missing required field(s): revision_id")

    rolled = rollback_hot_overview_revision(
        revision_id=revision_id,
        mode=mode,
    )
    if not isinstance(rolled, dict):
        return error("Revision not found", 404)
    LOGGER.info(
        "API /api/home/today-hot-overview/rollback success | revision_id=%s mode=%s",
        revision_id,
        mode,
    )
    return success({"data": rolled})


@app.post("/api/home/today-hot-overview/reclassify")
def home_today_hot_overview_reclassify():
    payload = request.get_json(silent=True) or {}
    target_title = str(payload.get("target_title") or "").strip()
    hint = str(payload.get("hint") or "").strip()
    mode_raw = str(payload.get("mode") or "").strip().lower()
    mode = mode_raw if mode_raw in {"fast", "research"} else "fast"
    if not mode_raw and str(payload.get("research") or "").strip().lower() in {"1", "true", "yes", "on"}:
        mode = "research"
    
    if not target_title:
        return error("Missing required field(s): target_title")

    LOGGER.info(
        "API /api/home/today-hot-overview/reclassify called | target_title=%s hint=%s mode=%s",
        target_title[:20],
        hint[:20],
        mode
    )
    
    try:
        new_payload = reclassify_hot_overview(
            target_title=target_title,
            hint=hint,
            mode=mode,
        )
        if not new_payload:
            return error("No cached overview data available to reclassify.", 404)
        
        LOGGER.info(
            "API /api/home/today-hot-overview/reclassify success | revision_id=%s",
            new_payload.get("revision_id"),
        )
        return success({"data": new_payload})
    except Exception as exc:
        LOGGER.exception("Failed to reclassify overview target")
        return error(f"Failed to reclassify: {str(exc)}", 500)

@app.route("/api/ai/chat", methods=["POST"])
def chat_ai():
    """
    Stream chat completion using system LLM settings (Assistant profile).
    Expected JSON payload: { "messages": [ { "role": "user", "content": "..." } ] }
    """
    data = request.json
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "No messages provided"}), 400

    config = load_llm_config()
    assistant = config.get("assistant", {})
    credentials = config.get("credentials", {})

    # Load Knowledge Base
    kb_content = []
    kb_dir = BACKEND_DIR / "knowledge_base" / "assistant"
    if kb_dir.exists():
        for md_file in sorted(kb_dir.rglob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                if content.strip():
                    relative_name = md_file.relative_to(kb_dir).as_posix()
                    kb_content.append(f"--- {relative_name} ---\n{content}")
            except Exception as e:
                LOGGER.error(f"Failed to read KB file {md_file}: {e}")

    # Build System Prompt
    system_prompt_parts = []
    
    # 1. Custom System Prompt from Config
    custom_system_prompt = assistant.get("system_prompt", "").strip()
    if custom_system_prompt:
        system_prompt_parts.append(custom_system_prompt)
    else:
        system_prompt_parts.append("You are a helpful assistant provided by OpinionSystem.")

    # 2. Add Knowledge Base Context if available
    if kb_content:
        system_prompt_parts.append("\n[Context Information from Knowledge Base]")
        system_prompt_parts.append("\n".join(kb_content))
        system_prompt_parts.append("[End of Context Information]")

    combined_system_message = "\n\n".join(system_prompt_parts)
    
    # Prepend system message to messages list
    # Ensure we don't duplicate system message if client sent one, but usually client sends user/assistant
    final_messages = [{"role": "system", "content": combined_system_message}] + messages

    # Determine provider details
    provider = assistant.get("provider", "openai").lower()
    model = assistant.get("model", "llama3")
    
    # Default defaults (Ollama-like)
    api_key = "ollama"
    base_url = "http://localhost:11434/v1"

    if provider == "qwen":
        api_key = credentials.get("qwen_api_key") or credentials.get("dashscope_api_key") or "EMPTY"
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    elif provider == "openai":
         # Use configured OpenAI settings, which might point to a local server or real OpenAI
         configured_base = credentials.get("openai_base_url")
         if configured_base:
             base_url = configured_base
         
         configured_key = credentials.get("openai_api_key") or credentials.get("opinion_openai_api_key")
         if configured_key:
             api_key = configured_key

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    def generate():
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=final_messages,
                stream=True,
                max_tokens=assistant.get("max_tokens"),
                temperature=assistant.get("temperature"),
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            LOGGER.error(f"AI Chat Error: {e}")
            yield f"Error: {str(e)}"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.get("/api/filter/template")
def get_filter_template():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()

    if not topic_param and not project_param:
        return error("Missing required field(s): topic or project")

    resolution_payload: Dict[str, Any] = {}
    if topic_param:
        resolution_payload["topic"] = topic_param
    if project_param:
        resolution_payload["project"] = project_param

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    try:
        data = load_filter_template_config(topic_identifier)
    except ValueError as exc:
        return error(str(exc))

    return success({"data": data})


@app.post("/api/filter/template")
def upsert_filter_template():
    payload = request.get_json(silent=True) or {}
    topic_param = str(payload.get("topic") or payload.get("project") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    theme = str(payload.get("topic_theme") or payload.get("theme") or "").strip()
    categories_value = payload.get("categories", [])

    if not topic_param:
        return error("Missing required field(s): topic")
    if not theme:
        return error("Missing required field(s): topic_theme")
    if not isinstance(categories_value, list):
        return error("Field 'categories' must be a list")

    categories = [str(item).strip() for item in categories_value if str(item or "").strip()]

    resolution_payload: Dict[str, Any] = {"topic": topic_param}
    if project_param:
        resolution_payload["project"] = project_param
    if payload.get("dataset_id"):
        resolution_payload["dataset_id"] = payload.get("dataset_id")

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    template_override = payload.get("template")
    try:
        data = persist_filter_template_config(topic_identifier, theme, categories, template_override)
    except ValueError as exc:
        return error(str(exc))

    return success({"data": data})


@app.get("/api/filter/stopwords/suggestions")
def get_filter_stopword_suggestions():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()
    dataset_id_param = str(request.args.get("dataset_id", "") or "").strip()
    date_param = str(request.args.get("date", "") or "").strip()
    stage_param = str(request.args.get("stage", "") or "").strip().lower()

    try:
        topic_identifier, resolved_date, stage = _resolve_stopword_suggestion_inputs(
            topic_param,
            project_param,
            dataset_id_param,
            date_param,
            stage_param,
        )
    except ValueError as exc:
        return error(str(exc))

    payload = build_stopword_suggestion_status_payload(
        topic_identifier,
        resolved_date,
        stage=stage,
    )
    return success({"data": payload})


@app.post("/api/filter/stopwords/suggestions")
def create_filter_stopword_suggestion_task():
    payload = request.get_json(silent=True) or {}
    topic_param = str(payload.get("topic") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    dataset_id_param = str(payload.get("dataset_id") or "").strip()
    date_param = str(payload.get("date") or "").strip()
    stage_param = str(payload.get("stage") or "").strip().lower()
    force_value = payload.get("force")
    top_k_value = payload.get("top_k", payload.get("limit", 100))

    try:
        topic_identifier, resolved_date, stage = _resolve_stopword_suggestion_inputs(
            topic_param,
            project_param,
            dataset_id_param,
            date_param,
            stage_param,
        )
    except ValueError as exc:
        return error(str(exc))

    force = bool(force_value) if isinstance(force_value, bool) else str(force_value or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        task = create_stopword_suggestion_task(
            topic_identifier,
            resolved_date,
            top_k=int(top_k_value or 100),
            stage=stage,
            force=force,
        )
    except Exception as exc:
        LOGGER.exception("Failed to create stopword suggestion task")
        return error(str(exc), 500)

    response_payload = {
        "topic_identifier": topic_identifier,
        "date": resolved_date,
        "stage": stage,
        "task": task,
    }
    return success({"data": response_payload}, status_code=202)


@app.get("/api/content/prompt")
def get_content_prompt():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()

    if not topic_param and not project_param:
        return error("Missing required field(s): topic or project")

    resolution_payload: Dict[str, Any] = {}
    if topic_param:
        resolution_payload["topic"] = topic_param
    if project_param:
        resolution_payload["project"] = project_param

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    try:
        data = load_content_prompt_config(topic_identifier)
    except ValueError as exc:
        return error(str(exc))

    return success({"data": data})


@app.post("/api/content/prompt")
def upsert_content_prompt():
    payload = request.get_json(silent=True) or {}
    topic_param = str(payload.get("topic") or payload.get("project") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    system_prompt = str(payload.get("system_prompt") or "").strip()
    analysis_prompt = str(payload.get("analysis_prompt") or "").strip()

    if not topic_param:
        return error("Missing required field(s): topic")
    if not system_prompt and not analysis_prompt:
        return error("Missing required field(s): system_prompt or analysis_prompt")

    resolution_payload: Dict[str, Any] = {"topic": topic_param}
    if project_param:
        resolution_payload["project"] = project_param
    if payload.get("dataset_id"):
        resolution_payload["dataset_id"] = payload.get("dataset_id")

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    try:
        data = persist_content_prompt_config(topic_identifier, system_prompt, analysis_prompt)
    except ValueError as exc:
        return error(str(exc))

    return success({"data": data})


@app.get("/api/filter/status")
def filter_status():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()
    dataset_id_param = str(request.args.get("dataset_id", "") or "").strip()
    date_param = str(request.args.get("date", "") or "").strip()

    try:
        topic_identifier, resolved_date, fallback_from = _resolve_filter_status_inputs(
            topic_param, project_param, dataset_id_param, date_param
        )
    except ValueError as exc:
        return error(str(exc))

    status_payload = _build_filter_status_payload(topic_identifier, resolved_date, fallback_from)
    return success({"data": status_payload})


@app.get("/api/filter/status/stream")
def filter_status_stream():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()
    dataset_id_param = str(request.args.get("dataset_id", "") or "").strip()
    date_param = str(request.args.get("date", "") or "").strip()
    interval_param = str(request.args.get("interval", "") or "").strip()

    try:
        topic_identifier, resolved_date, fallback_from = _resolve_filter_status_inputs(
            topic_param, project_param, dataset_id_param, date_param
        )
    except ValueError as exc:
        return error(str(exc))

    try:
        interval = float(interval_param) if interval_param else FILTER_STATUS_STREAM_INTERVAL
    except ValueError:
        interval = FILTER_STATUS_STREAM_INTERVAL
    interval = max(0.5, min(5.0, interval))

    def _stream():
        start_time = time.time()
        last_snapshot = ""
        yield f"retry: {int(interval * 1500)}\n\n"
        while True:
            try:
                status_payload = _build_filter_status_payload(topic_identifier, resolved_date, fallback_from)
            except Exception as exc:  # pragma: no cover - defensive
                error_payload = {"message": str(exc)}
                yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
                break

            message = json.dumps({"data": status_payload}, ensure_ascii=False)
            if message != last_snapshot:
                yield f"data: {message}\n\n"
                last_snapshot = message

            if not status_payload.get("running"):
                break
            if (time.time() - start_time) >= FILTER_STATUS_STREAM_TIMEOUT:
                break
            time.sleep(interval)

        yield "event: done\ndata: {}\n\n"

    response = Response(stream_with_context(_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.post("/api/merge")
def merge_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.merge import run_merge  # type: ignore

    response, code = _execute_operation(
        "merge",
        run_merge,
        topic_identifier,
        date,
        log_context={
            "project": log_project,
            "params": {
                "date": date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.post("/api/clean")
def clean_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(
            payload,
            PROJECT_MANAGER,
            allow_missing_date=True,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.clean import run_clean  # type: ignore

    try:
        resolved_date, fallback_from = resolve_stage_processing_date(topic_identifier, "clean", date or None)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    response, code = _execute_operation(
        "clean",
        run_clean,
        topic_identifier,
        resolved_date,
        log_context={
            "project": log_project,
            "params": {
                "date": resolved_date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    if fallback_from and response.get("status") == "ok":
        metadata = response.setdefault("context", {})
        metadata["resolved_date"] = resolved_date
        metadata["requested_date"] = fallback_from
    return jsonify(response), code


@app.post("/api/filter")
def filter_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(
            payload,
            PROJECT_MANAGER,
            allow_missing_date=True,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.filter import run_filter  # type: ignore

    try:
        resolved_date, fallback_from = resolve_stage_processing_date(topic_identifier, "filter", date or None)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    mark_filter_job_running(topic_identifier, resolved_date)
    try:
        _submit_filter_job(
            run_filter,
            topic_identifier=topic_identifier,
            resolved_date=resolved_date,
            log_project=log_project,
            display_name=display_name,
        )
    except Exception as exc:  # pragma: no cover - executor failure
        mark_filter_job_finished(topic_identifier, resolved_date)
        LOGGER.exception("Failed to enqueue filter job")
        return jsonify({"status": "error", "message": str(exc)}), 500

    context: Dict[str, Any] = {}
    if fallback_from:
        context["resolved_date"] = resolved_date
        context["requested_date"] = fallback_from

    response_payload: Dict[str, Any] = {
        "status": "ok",
        "operation": "filter",
        "message": "筛选任务已提交，稍后可在进度面板查看实时状态。",
        "data": {
            "topic": topic_identifier,
            "date": resolved_date,
            "queued": True,
        },
    }
    if context:
        response_payload["context"] = context
    return jsonify(response_payload), 202


@app.post("/api/filter/preclean")
def filter_preclean_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(
            payload,
            PROJECT_MANAGER,
            allow_missing_date=True,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.filter import run_keyword_preclean  # type: ignore

    try:
        resolved_date, fallback_from = resolve_stage_processing_date(topic_identifier, "filter", date or None)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    response, code = _execute_operation(
        "filter-preclean",
        run_keyword_preclean,
        topic_identifier,
        resolved_date,
        log_context={
            "project": log_project,
            "params": {
                "date": resolved_date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    if fallback_from and response.get("status") == "ok":
        metadata = response.setdefault("context", {})
        metadata["resolved_date"] = resolved_date
        metadata["requested_date"] = fallback_from
    return jsonify(response), code


@app.post("/api/upload")
def upload_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    prepare_intermediate_value = payload.get("prepare_intermediate_from_clean")
    if prepare_intermediate_value is None:
        prepare_intermediate_value = payload.get("prepare_intermediate")
    if prepare_intermediate_value is None:
        prepare_intermediate_value = payload.get("skip_filter")

    prepare_intermediate_from_clean = False
    if isinstance(prepare_intermediate_value, bool):
        prepare_intermediate_from_clean = prepare_intermediate_value
    elif isinstance(prepare_intermediate_value, str):
        prepare_intermediate_from_clean = (
            prepare_intermediate_value.strip().lower() in {"1", "true", "yes", "on"}
        )

    # 处理从 fetch 重建参数
    rebuild_from_fetch_value = payload.get("rebuild_from_fetch")
    rebuild_from_fetch = False
    fetch_date = str(payload.get("fetch_date") or "").strip()
    if isinstance(rebuild_from_fetch_value, bool):
        rebuild_from_fetch = rebuild_from_fetch_value
    elif isinstance(rebuild_from_fetch_value, str):
        rebuild_from_fetch = (
            rebuild_from_fetch_value.strip().lower() in {"1", "true", "yes", "on"}
        )

    # 如果是 fetch 重建，使用后台任务模式
    if rebuild_from_fetch:
        database = display_name or topic_identifier
        existing = get_rebuild_fetch_job(topic_identifier, database, fetch_date)
        if existing and str(existing.get("status") or "").strip() in {"queued", "running"}:
            return jsonify({
                "status": "accepted",
                "operation": "rebuild-fetch",
                "reused": True,
                "data": existing,
            }), 202

        create_rebuild_fetch_job(
            topic_identifier,
            database,
            fetch_date,
            message="任务已创建，等待执行...",
            progress={"percentage": 0},
        )
        _submit_rebuild_fetch_job(
            topic_identifier=topic_identifier,
            database=database,
            fetch_date=fetch_date,
            date=date,
            log_project=log_project,
            display_name=display_name,
        )
        return jsonify({
            "status": "accepted",
            "operation": "rebuild-fetch",
            "reused": False,
            "data": {
                "topic": topic_identifier,
                "database": database,
                "fetch_date": fetch_date,
                "status": "queued",
                "message": "已从本地缓存重建数据库任务提交",
            },
        }), 202

    from src.update import run_update  # type: ignore

    response, code = _execute_operation(
        "upload",
        run_update,
        topic_identifier,
        date,
        dataset_name=display_name,
        prepare_intermediate_from_clean=prepare_intermediate_from_clean,
        log_context={
            "project": log_project,
            "params": {
                "date": date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
                "prepare_intermediate_from_clean": prepare_intermediate_from_clean,
            },
        },
    )
    return jsonify(response), code


@app.get("/api/upload/rebuild-fetch/status")
def upload_rebuild_fetch_status_endpoint():
    """获取 fetch 重建任务状态"""
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    database = str(request.args.get("database") or "").strip()
    fetch_date = str(request.args.get("fetch_date") or "").strip()

    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400
    if not database:
        return jsonify({"status": "error", "message": "Missing required field(s): database"}), 400

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(
            {
                "topic": topic,
                "project": project,
                "dataset_id": dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    job = get_rebuild_fetch_job(topic_identifier, database, fetch_date)
    if not job:
        return jsonify({
            "status": "ok",
            "operation": "rebuild-fetch-status",
            "data": {
                "topic": topic_identifier,
                "database": database,
                "fetch_date": fetch_date,
                "status": "idle",
                "message": "无运行中的任务",
            },
        }), 200

    return jsonify({
        "status": "ok",
        "operation": "rebuild-fetch-status",
        "data": job,
    }), 200


@app.post("/api/pipeline")
def pipeline_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    response, code = _execute_operation(
        "pipeline",
        _run_data_pipeline,
        topic_identifier,
        date,
        project=log_project,
        topic_label=display_name,
        log_context={
            "project": log_project,
            "params": {
                "date": date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.post("/api/query")
def query_endpoint():
    from src.query import run_query  # type: ignore

    payload = request.get_json(silent=True) or {}
    include_counts_value = payload.get("include_counts", True)
    include_counts = True
    if isinstance(include_counts_value, bool):
        include_counts = include_counts_value
    elif isinstance(include_counts_value, str):
        include_counts = include_counts_value.strip().lower() not in ("false", "0", "no", "off", "")

    response, code = _execute_operation(
        "query",
        run_query,
        include_counts=include_counts,
        log_context={"params": {"source": "api"}},
    )
    return jsonify(response), code


@app.get("/api/fetch/availability")
def fetch_availability_endpoint():
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    if not any([topic, project, dataset_id]):
        return error("Missing required field(s): topic/project/dataset_id")

    payload = {
        "topic": topic,
        "project": project,
        "dataset_id": dataset_id,
    }
    try:
        topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    # 对于远程数据源，可用日期区间查询需要使用真实数据库名，
    # 即请求中提供的 topic；若缺失则退回到展示名/内部标识。
    db_topic = topic or display_name or topic_identifier

    from src.fetch import get_topic_available_date_range  # type: ignore

    availability = get_topic_available_date_range(db_topic)
    return success(
        {
            "data": {
                "topic": display_name or db_topic,
                "bucket": topic_identifier,
                "range": availability,
            }
        }
    )


@app.delete("/api/database/<database_name>")
def delete_database_endpoint(database_name: str):
    """
    删除指定的远程数据库
    """
    db_name = str(database_name or "").strip()
    if not db_name:
        return error("Database name is required")

    # Safety check: prevent deleting system databases (basic list)
    system_dbs = {'information_schema', 'mysql', 'performance_schema', 'sys', 'postgres', 'test', 'phpmyadmin'}
    if db_name.lower() in system_dbs:
        return error(f"Cannot delete system database '{db_name}'", status_code=403)

    from src.utils.io.db import db_manager
    
    # Optional: Check if database exists first? drop_database handles IF EXISTS
    
    success_flag = db_manager.drop_database(db_name)
    if success_flag:
        return success({"message": f"Database '{db_name}' deleted successfully"})
    else:
        return error(f"Failed to delete database '{db_name}'", status_code=500)


@app.post("/api/database/postclean")
def database_postclean_endpoint():
    payload = request.get_json(silent=True) or {}
    topic = str(payload.get("topic") or "").strip()
    project = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    database = str(payload.get("database") or "").strip()
    raw_tables = payload.get("tables")

    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400
    if not database:
        return jsonify({"status": "error", "message": "Missing required field(s): database"}), 400

    try:
        topic_identifier, display_name, log_project, _ = resolve_topic_identifier(
            {
                "topic": topic,
                "project": project,
                "dataset_id": dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    tables: Optional[List[str]] = None
    if isinstance(raw_tables, list):
        tables = [str(item).strip() for item in raw_tables if str(item or "").strip()]

    existing = get_postclean_job(topic_identifier, database, tables)
    if existing and existing.get("status") == "running":
        return jsonify({
            "status": "accepted",
            "operation": "database-postclean",
            "reused": True,
            "data": existing,
        }), 202

    payload = create_postclean_job(topic_identifier, database, tables)
    _submit_postclean_job(
        topic_identifier=topic_identifier,
        database=database,
        tables=tables,
        log_project=log_project,
        display_name=display_name,
    )
    return jsonify({
        "status": "accepted",
        "operation": "database-postclean",
        "reused": False,
        "data": payload,
    }), 202


@app.post("/api/database/postclean/publishers/task")
def database_postclean_publishers_task_endpoint():
    payload = request.get_json(silent=True) or {}
    topic = str(payload.get("topic") or "").strip()
    project = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    database = str(payload.get("database") or "").strip()
    raw_tables = payload.get("tables")
    force = bool(payload.get("force"))
    limit = int(payload.get("limit") or 50)
    sample_limit = int(payload.get("sample_limit") or 3)

    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400
    if not database:
        return jsonify({"status": "error", "message": "Missing required field(s): database"}), 400

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(
            {
                "topic": topic,
                "project": project,
                "dataset_id": dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    tables: Optional[List[str]] = None
    if isinstance(raw_tables, list):
        tables = [str(item).strip() for item in raw_tables if str(item or "").strip()]

    try:
        task = create_publisher_detection_task(
            topic_identifier,
            database,
            tables=tables,
            limit=max(1, min(limit or 50, 200)),
            sample_limit=max(1, min(sample_limit or 3, 10)),
            force=force,
        )
    except Exception as exc:  # pragma: no cover
        LOGGER.exception("Failed to create publisher detection task")
        return jsonify({"status": "error", "message": str(exc)}), 500

    payload = build_publisher_detection_status_payload(
        topic_identifier,
        database,
        tables=tables,
    )
    return jsonify({
        "status": "accepted",
        "operation": "database-postclean-publishers-task",
        "data": serialise_result(payload),
        "task_id": str(task.get("id") or ""),
    }), 202


@app.get("/api/database/postclean/publishers")
def database_postclean_publishers_endpoint():
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    database = str(request.args.get("database") or "").strip()
    raw_tables = request.args.getlist("tables")
    limit = request.args.get("limit", default=50, type=int)
    sample_limit = request.args.get("sample_limit", default=3, type=int)

    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400
    if not database:
        return jsonify({"status": "error", "message": "Missing required field(s): database"}), 400

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(
            {
                "topic": topic,
                "project": project,
                "dataset_id": dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    tables = [str(item).strip() for item in raw_tables if str(item or "").strip()]
    try:
        from src.filter import list_postclean_publishers  # type: ignore

        result = list_postclean_publishers(
            topic_identifier,
            database,
            tables=tables or None,
            limit=max(1, min(limit or 50, 200)),
            sample_limit=max(1, min(sample_limit or 3, 10)),
        )
    except Exception as exc:  # pragma: no cover
        LOGGER.exception("Failed to load postclean publishers for %s@%s", topic_identifier, database)
        return jsonify({"status": "error", "message": str(exc)}), 500

    code = 200 if evaluate_success(result) else 400
    return jsonify(serialise_result(result)), code


@app.get("/api/database/postclean/publishers/status")
def database_postclean_publishers_status_endpoint():
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    database = str(request.args.get("database") or "").strip()
    raw_tables = request.args.getlist("tables")

    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400
    if not database:
        return jsonify({"status": "error", "message": "Missing required field(s): database"}), 400

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(
            {
                "topic": topic,
                "project": project,
                "dataset_id": dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    tables = [str(item).strip() for item in raw_tables if str(item or "").strip()]
    payload = build_publisher_detection_status_payload(
        topic_identifier,
        database,
        tables=tables,
    )
    return jsonify({
        "status": "ok",
        "operation": "database-postclean-publishers-status",
        "data": serialise_result(payload),
    }), 200


@app.get("/api/database/postclean/status")
def database_postclean_status_endpoint():
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    database = str(request.args.get("database") or "").strip()
    raw_tables = request.args.getlist("tables")

    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400
    if not database:
        return jsonify({"status": "error", "message": "Missing required field(s): database"}), 400

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(
            {
                "topic": topic,
                "project": project,
                "dataset_id": dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    tables = [str(item).strip() for item in raw_tables if str(item or "").strip()]
    payload = get_postclean_job(topic_identifier, database, tables) or {
        "topic": topic_identifier,
        "database": database,
        "tables": tables,
        "status": "idle",
        "message": "",
        "started_at": "",
        "updated_at": "",
        "last_heartbeat": "",
        "progress": {
            "total_tables": 0,
            "completed_tables": 0,
            "deleted_rows": 0,
            "current_table": "",
            "percentage": 0,
        },
        "logs": [],
        "result": None,
    }
    return jsonify({"status": "ok", "operation": "database-postclean-status", "data": payload}), 200


@app.post("/api/database/deduplicate")
def database_deduplicate_endpoint():
    payload = request.get_json(silent=True) or {}
    topic = str(payload.get("topic") or "").strip()
    project = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    database = str(payload.get("database") or "").strip()
    raw_tables = payload.get("tables")

    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400
    if not database:
        return jsonify({"status": "error", "message": "Missing required field(s): database"}), 400

    try:
        topic_identifier, display_name, log_project, _ = resolve_topic_identifier(
            {
                "topic": topic,
                "project": project,
                "dataset_id": dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    tables: Optional[List[str]] = None
    if isinstance(raw_tables, list):
        tables = [str(item).strip() for item in raw_tables if str(item or "").strip()]

    existing = get_deduplicate_job(topic_identifier, database, tables)
    if existing and existing.get("status") == "running":
        return jsonify({
            "status": "accepted",
            "operation": "database-deduplicate",
            "reused": True,
            "data": existing,
        }), 202

    payload = create_deduplicate_job(topic_identifier, database, tables)
    _submit_deduplicate_job(
        topic_identifier=topic_identifier,
        database=database,
        tables=tables,
        log_project=log_project,
        display_name=display_name,
    )
    return jsonify({
        "status": "accepted",
        "operation": "database-deduplicate",
        "reused": False,
        "data": payload,
    }), 202


@app.get("/api/database/deduplicate/status")
def database_deduplicate_status_endpoint():
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    database = str(request.args.get("database") or "").strip()
    raw_tables = request.args.getlist("tables")

    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400
    if not database:
        return jsonify({"status": "error", "message": "Missing required field(s): database"}), 400

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(
            {
                "topic": topic,
                "project": project,
                "dataset_id": dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    tables = [str(item).strip() for item in raw_tables if str(item or "").strip()]
    payload = get_deduplicate_job(topic_identifier, database, tables) or {
        "topic": topic_identifier,
        "database": database,
        "tables": tables,
        "status": "idle",
        "message": "",
        "started_at": "",
        "updated_at": "",
        "last_heartbeat": "",
        "progress": {
            "total_tables": 0,
            "completed_tables": 0,
            "deleted_rows": 0,
            "current_table": "",
            "percentage": 0,
        },
        "logs": [],
        "result": None,
    }
    return jsonify({"status": "ok", "operation": "database-deduplicate-status", "data": payload}), 200


@app.post("/api/fetch")
def fetch_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = require_fields(payload, "start", "end")
    if not valid:
        return jsonify(error), 400

    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip()
    if not start or not end:
        return jsonify({"status": "error", "message": "Missing required field(s): start, end"}), 400

    topic = str(payload.get("topic") or "").strip()
    project = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400

    try:
        topic_identifier, display_name, log_project, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    # 远程 Fetch 从数据库读取数据，需使用真实库名；
    # 优先使用请求中的 topic，其次展示名，最后回退内部标识。
    db_topic = (topic or "").strip() or display_name or topic_identifier

    from src.fetch import run_fetch  # type: ignore

    response, code = _execute_operation(
        "fetch",
        run_fetch,
        topic_identifier,
        start,
        end,
        db_topic=db_topic,
        log_context={
            "project": log_project,
            "params": {
                "start": start,
                "end": end,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code





















@app.get("/api/projects")
def list_projects():
    return jsonify({"status": "ok", "projects": PROJECT_MANAGER.list_projects()})


@app.get("/api/projects/<string:name>")
def project_detail(name: str):
    project = PROJECT_MANAGER.get_project(name)
    if not project:
        return jsonify({"status": "error", "message": "Project not found"}), 404
    return jsonify({"status": "ok", "project": project})


@app.post("/api/projects")
def create_project():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    if not name:
        return jsonify({"status": "error", "message": "Missing required field: name"}), 400

    description = payload.get("description")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    project = PROJECT_MANAGER.create_or_update_project(
        name,
        description=description,
        metadata=metadata,
    )
    return jsonify({"status": "ok", "project": project})


@app.delete("/api/projects/<string:name>")
def delete_project(name: str):
    if not PROJECT_MANAGER.delete_project(name):
        return jsonify({"status": "error", "message": "Project not found"}), 404
    return jsonify({"status": "ok", "message": "Project deleted"})


@app.get("/api/projects/<string:name>/datasets")
def project_datasets(name: str):
    try:
        datasets = list_project_datasets(name)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to read dataset manifest for project %s", name)
        return jsonify({"status": "error", "message": "无法读取项目数据清单"}), 500
    return jsonify({"status": "ok", "datasets": datasets})


@app.get("/api/projects/<string:name>/datasets/<string:dataset_id>/preview")
def project_dataset_preview(name: str, dataset_id: str):
    page = request.args.get("page", default=1, type=int)
    page_size = request.args.get("page_size", default=20, type=int)
    try:
        preview = get_dataset_preview(name, dataset_id, page=page, page_size=page_size)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except FileNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to preview dataset %s for project %s", dataset_id, name)
        return jsonify({"status": "error", "message": "无法加载数据集预览"}), 500
    return jsonify({"status": "ok", "preview": preview})


@app.get("/api/projects/<string:name>/date-range")
def project_date_range(name: str):
    dataset_id = request.args.get("dataset_id")
    try:
        summary = get_dataset_date_summary(name, dataset_id=dataset_id)
    except (LookupError, FileNotFoundError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to derive date range for project %s", name)
        return jsonify({"status": "error", "message": "无法解析数据集日期范围"}), 500

    dataset_info = summary.get("dataset")
    if isinstance(dataset_info, dict):
        dataset_info.setdefault("column_mapping", summary.get("column_mapping"))

    payload: Dict[str, Any] = {"status": "ok", "topic": name}
    payload.update(summary)
    return jsonify(payload)


@app.get("/api/projects/<string:name>/archives")
def project_archives(name: str):
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    layers_param = str(request.args.get("layers") or "").strip()

    resolution_payload: Dict[str, Any] = {"project": name}
    if dataset_id:
        resolution_payload["dataset_id"] = dataset_id

    try:
        topic_identifier, display_name, log_project, dataset_meta = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    requested_layers = [layer.strip() for layer in layers_param.split(",") if layer.strip()] or None

    archives = collect_project_archives(
        topic_identifier,
        layers=requested_layers,
        dataset_id=str(dataset_meta.get("id") or dataset_id or "").strip() or None,
    )
    latest = {
        layer: (entries[0]["date"] if entries else None)
        for layer, entries in archives.items()
    }

    return jsonify({
        "status": "ok",
        "project": log_project,
        "topic": topic_identifier,
        "display_name": display_name,
        "archives": archives,
        "latest": latest,
    })


@app.delete("/api/projects/<string:name>/archives/<string:layer>/<string:date>")
def delete_project_archive(name: str, layer: str, date: str):
    """
    删除指定项目的存档

    Args:
        name: 项目名称
        layer: 存档层级 (raw, merge, clean)
        date: 存档日期

    Returns:
        JSON响应
    """
    dataset_id = str(request.args.get("dataset_id") or "").strip()

    # 验证层级参数
    valid_layers = ["raw", "merge", "clean"]
    if layer not in valid_layers:
        return jsonify({
            "status": "error",
            "message": f"无效的存档层级: {layer}，支持的层级: {', '.join(valid_layers)}"
        }), 400

    # 验证日期格式
    if not re.match(r'^\d{8}$', date):
        return jsonify({
            "status": "error",
            "message": "无效的日期格式，请使用YYYYMMDD格式，例如: 20241202"
        }), 400

    resolution_payload: Dict[str, Any] = {"project": name}
    if dataset_id:
        resolution_payload["dataset_id"] = dataset_id

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    try:
        # 检查依赖关系 - 不能删除被后续阶段依赖的存档
        dependency_check = check_archive_dependencies(topic_identifier, layer, date)
        if not dependency_check["can_delete"]:
            return jsonify({
                "status": "error",
                "message": dependency_check["message"],
                "dependent_layers": dependency_check.get("dependent_layers", [])
            }), 409

        # 执行删除操作
        result = delete_archive_directory(topic_identifier, layer, date)

        if result["success"]:
            return jsonify({
                "status": "ok",
                "message": f"成功删除 {layer.upper()} 存档 ({date})",
                "deleted_files": result["deleted_files"],
                "deleted_size": result.get("deleted_size", 0)
            })
        else:
            return jsonify({
                "status": "error",
                "message": result["message"] or f"删除 {layer.upper()} 存档失败"
            }), 500

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return jsonify({
            "status": "error",
            "message": f"删除存档时发生错误: {str(e)}",
            "error_details": error_details if app.debug else None
        }), 500


def check_archive_dependencies(topic_identifier: str, layer: str, date: str) -> Dict[str, Any]:
    """
    检查存档的依赖关系，确认是否可以安全删除

    Args:
        topic_identifier: 专题标识符
        layer: 存档层级
        date: 存档日期

    Returns:
        检查结果字典
    """
    from server_support.archives import collect_project_archives

    # 定义依赖关系：clean依赖merge，merge依赖raw
    dependencies = {
        "raw": ["merge", "clean"],
        "merge": ["clean"]
    }

    # 如果删除clean存档，没有后续依赖，可以直接删除
    if layer == "clean":
        return {"can_delete": True, "message": "Clean存档无后续依赖，可以删除"}

    # 检查是否有后续阶段依赖此存档
    dependent_layers = dependencies.get(layer, [])
    blocking_archives = []

    for dependent_layer in dependent_layers:
        # 获取后续层级的存档
        archives = collect_project_archives(topic_identifier, layers=[dependent_layer])
        dependent_archives = archives.get(dependent_layer, [])

        # 检查是否有基于当前存档日期创建的后续存档
        for archive in dependent_archives:
            # 这里简化检查：如果后续存档日期等于或晚于当前存档日期，可能存在依赖
            # 实际业务中可能需要更精确的依赖关系追踪
            if archive["date"] >= date:
                blocking_archives.append({
                    "layer": dependent_layer,
                    "date": archive["date"],
                    "updated_at": archive.get("updated_at", "")
                })

    if blocking_archives:
        archive_list = ", ".join([
            f"{arch['layer'].upper()}({arch['date']})"
            for arch in blocking_archives
        ])
        return {
            "can_delete": False,
            "message": f"无法删除 {layer.upper()} 存档，存在依赖关系：{archive_list}",
            "dependent_layers": blocking_archives
        }

    return {"can_delete": True, "message": f"{layer.upper()}存档无依赖，可以删除"}


def delete_archive_directory(topic_identifier: str, layer: str, date: str) -> Dict[str, Any]:
    """
    删除指定存档目录

    Args:
        topic_identifier: 专题标识符
        layer: 存档层级 (raw, merge, clean)
        date: 存档日期

    Returns:
        删除结果字典
    """
    import shutil
    import os
    from src.utils.setting.paths import bucket

    try:
        archive_dir = bucket(layer, topic_identifier, date)

        if not os.path.exists(archive_dir):
            return {
                "success": False,
                "message": f"存档目录不存在: {archive_dir}",
                "deleted_files": [],
                "deleted_size": 0
            }

        # 统计要删除的文件
        deleted_files = []
        deleted_size = 0

        for root, _, files in os.walk(archive_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(file_path)
                    deleted_size += file_size
                    relative_path = os.path.relpath(file_path, archive_dir)
                    deleted_files.append(relative_path)
                except OSError:
                    # 忽略无法获取大小的文件
                    pass

        # 执行删除
        shutil.rmtree(archive_dir)

        return {
            "success": True,
            "message": f"成功删除存档目录: {layer}/{date}",
            "deleted_files": deleted_files,
            "deleted_size": deleted_size,
            "deleted_count": len(deleted_files)
        }

    except PermissionError:
        return {
            "success": False,
            "message": "权限不足，无法删除存档目录",
            "deleted_files": [],
            "deleted_size": 0
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"删除存档目录时发生错误: {str(e)}",
            "deleted_files": [],
            "deleted_size": 0
        }


def _build_fetch_cache_response(resolution_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not resolution_payload:
        return {"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}, 400
    try:
        topic_identifier, display_name, log_project, dataset_meta = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400

    dataset_reference = str(
        dataset_meta.get("id") or resolution_payload.get("dataset_id") or ""
    ).strip() or None

    caches = collect_layer_archives(
        topic_identifier,
        "fetch",
        dataset_id=dataset_reference,
    )
    totals = {
        "files": sum(int(entry.get("file_count") or 0) for entry in caches),
        "size": sum(int(entry.get("total_size") or 0) for entry in caches),
    }
    payload = {
        "status": "ok",
        "project": log_project,
        "topic": topic_identifier,
        "display_name": display_name,
        "cache_root": str(DATA_PROJECTS_ROOT / topic_identifier / "fetch"),
        "caches": caches,
        "latest_cache": caches[0] if caches else None,
        "totals": totals,
        "count": len(caches),
    }
    return payload, 200


@app.get("/api/projects/<string:name>/fetch-cache")
def project_fetch_cache(name: str):
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    resolution_payload: Dict[str, Any] = {"project": name}
    if dataset_id:
        resolution_payload["dataset_id"] = dataset_id
    response_payload, status_code = _build_fetch_cache_response(resolution_payload)
    return jsonify(response_payload), status_code


@app.get("/api/projects/<string:name>/fetch-dates")
def project_fetch_dates(name: str):
    """获取项目的 fetch 层缓存日期列表"""
    fetch_base = DATA_PROJECTS_ROOT / name / "fetch"
    dates = []
    if fetch_base.exists():
        for item in fetch_base.iterdir():
            if item.is_dir():
                dates.append(item.name)
    dates.sort(reverse=True)
    return jsonify({"status": "ok", "dates": dates})


@app.get("/api/fetch/cache")
def fetch_cache_overview():
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()

    resolution_payload: Dict[str, Any] = {}
    if topic:
        resolution_payload["topic"] = topic
    if project:
        resolution_payload["project"] = project
    if dataset_id:
        resolution_payload["dataset_id"] = dataset_id

    response_payload, status_code = _build_fetch_cache_response(resolution_payload)
    return jsonify(response_payload), status_code


@app.get("/api/netinsight/tasks")
def netinsight_tasks():
    project = str(request.args.get("project") or "").strip()
    status = str(request.args.get("status") or "").strip()
    limit_raw = str(request.args.get("limit") or "").strip()
    limit = 100
    if limit_raw:
        try:
            limit = int(limit_raw)
        except ValueError:
            return error("Invalid 'limit' parameter, expected integer")
    return success({"data": list_netinsight_tasks(project=project, status=status, limit=limit)})


@app.get("/api/netinsight/tasks/<string:task_id>")
def netinsight_task_detail(task_id: str):
    try:
        task = get_netinsight_task(task_id)
    except LookupError as exc:
        return error(str(exc), 404)
    return success({"data": task})


@app.get("/api/netinsight/tasks/<string:task_id>/files/<string:file_kind>")
def netinsight_task_file(task_id: str, file_kind: str):
    try:
        file_path = resolve_netinsight_task_output_file(task_id, file_kind)
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc))
    download_name = f"{task_id}-{file_path.name}"
    return send_file(file_path, as_attachment=True, download_name=download_name)


@app.post("/api/netinsight/tasks/plan")
def netinsight_task_plan():
    payload = request.get_json(silent=True) or {}
    brief = str(payload.get("brief") or payload.get("query") or "").strip()
    if not brief:
        return error("Missing required field(s): brief")
    plan = plan_task_from_brief(brief)
    return success({"data": plan})


@app.post("/api/netinsight/tasks")
def netinsight_create_task():
    payload = request.get_json(silent=True) or {}
    try:
        task = create_netinsight_task(payload)
        worker = ensure_netinsight_worker()
    except ValueError as exc:
        return error(str(exc))
    except Exception as exc:
        LOGGER.exception("Failed to create NetInsight task")
        return error(f"创建 NetInsight 任务失败: {str(exc)}", 500)
    return success({"data": {"task": task, "worker": worker}}, status_code=201)


@app.post("/api/netinsight/tasks/<string:task_id>/cancel")
def netinsight_cancel_task(task_id: str):
    try:
        task = cancel_netinsight_task(task_id)
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 409)
    return success({"data": task})


@app.post("/api/netinsight/tasks/<string:task_id>/retry")
def netinsight_retry_task(task_id: str):
    try:
        task = retry_netinsight_task(task_id)
        worker = ensure_netinsight_worker()
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 409)
    return success({"data": {"task": task, "worker": worker}}, status_code=201)


@app.delete("/api/netinsight/tasks/<string:task_id>")
def netinsight_delete_task(task_id: str):
    try:
        delete_netinsight_task(task_id)
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 409)
    return success({"data": {"deleted": task_id}})


@app.get("/api/netinsight/worker")
def netinsight_worker_status():
    return success({"data": load_netinsight_worker_status()})


@app.get("/api/netinsight/login")
def netinsight_login_status():
    return success({"data": read_netinsight_login_state()})


_netinsight_login_thread: _threading.Thread | None = None


@app.post("/api/netinsight/login")
def netinsight_trigger_login():
    global _netinsight_login_thread
    state = read_netinsight_login_state()
    if state.get("status") == "logging_in":
        return success({"data": state, "message": "登录正在进行中，请稍候"})

    from src.netinsight.client import NetInsightError, login_and_capture
    from src.netinsight.config import load_netinsight_config, resolve_netinsight_credentials

    config = load_netinsight_config()
    creds = resolve_netinsight_credentials()
    username = creds.get("user", "")
    password = creds.get("pass", "")
    if not username or not password:
        return jsonify({"status": "error", "message": "未配置账号密码，请先在设置里填写"}), 400

    runtime = config.get("runtime", {})
    LOGGER.info(
        "NetInsight login requested | headless=%s browser_channel=%s",
        bool(runtime.get("headless", False)),
        str(runtime.get("browser_channel") or "") or "default",
    )
    write_netinsight_login_state({
        "status": "logging_in",
        "step": "准备启动…",
        "logged_in_at": None,
        "error": None,
        "username": username,
    })

    def _do_login():
        from datetime import datetime, timezone

        def _on_step(msg: str) -> None:
            LOGGER.info("NetInsight login | %s", msg)
            write_netinsight_login_state({
                "status": "logging_in",
                "step": msg,
                "logged_in_at": None,
                "error": None,
                "username": username,
            })

        try:
            context = login_and_capture(
                username,
                password,
                headless=bool(runtime.get("headless", False)),
                no_proxy=bool(runtime.get("no_proxy", False)),
                login_timeout_ms=int(runtime.get("login_timeout_ms") or 120000),
                browser_channel=str(runtime.get("browser_channel") or ""),
                progress_callback=_on_step,
            )
            saved_at = datetime.now(timezone.utc).isoformat()
            write_netinsight_session_state({
                "username": username,
                "saved_at": saved_at,
                "headers": context.headers,
                "cookies": context.cookies,
            })
            write_netinsight_login_state({
                "status": "ok",
                "step": "登录成功",
                "logged_in_at": saved_at,
                "error": None,
                "username": username,
            })
            LOGGER.info("NetInsight login completed successfully")
        except Exception as exc:
            LOGGER.exception("NetInsight login failed")
            write_netinsight_login_state({
                "status": "failed",
                "step": "登录失败",
                "logged_in_at": None,
                "error": str(exc),
                "username": username,
            })

    t = _threading.Thread(target=_do_login, daemon=True)
    t.start()
    _netinsight_login_thread = t
    return success({"data": read_netinsight_login_state(), "message": "已开始登录，请稍候…"})


@app.put("/api/projects/<string:name>/datasets/<string:dataset_id>/mapping")
def update_project_dataset_mapping(name: str, dataset_id: str):
    payload = request.get_json(silent=True) or {}
    raw_mapping = payload.get("column_mapping", payload)
    mapping = parse_column_mapping_payload(raw_mapping)
    if not mapping:
        for key in ("date", "title", "content", "author"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                mapping[key] = value.strip()

    topic_label = None
    if "topic_label" in payload:
        topic_label = normalise_topic_label(payload.get("topic_label"))

    try:
        updated = update_dataset_column_mapping(
            name,
            dataset_id,
            mapping,
            topic_label=topic_label,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to update column mapping for dataset %s of project %s", dataset_id, name)
        return jsonify({"status": "error", "message": "无法更新字段映射"}), 500

    return jsonify(
        {
            "status": "ok",
            "column_mapping": updated.get("column_mapping", {}),
            "topic_label": updated.get("topic_label", ""),
        }
    )


@app.post("/api/projects/<string:name>/datasets")
def upload_project_dataset(name: str):
    uploads = request.files.getlist("file") or request.files.getlist("files")
    if not uploads:
        single = request.files.get("file")
        if single and getattr(single, "filename", ""):
            uploads = [single]
    uploads = [upload for upload in uploads if getattr(upload, "filename", "")]
    if not uploads:
        return jsonify({"status": "error", "message": "请选择需要上传的表格文件"}), 400

    mapping_hints = parse_column_mapping_from_form(request.form)
    topic_label_hint = normalise_topic_label(request.form.get("topic_label"))

    datasets: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    last_exception = None

    for upload in uploads:
        try:
            dataset = store_uploaded_dataset(
                name,
                upload,
                column_mapping=mapping_hints,
                topic_label=topic_label_hint,
            )
            datasets.append(dataset)
            try:
                PROJECT_MANAGER.log_operation(
                    name,
                    "import_dataset",
                    params={
                        "dataset_id": dataset.get("id"),
                        "filename": dataset.get("display_name"),
                        "rows": dataset.get("rows"),
                        "columns": dataset.get("column_count"),
                        "column_mapping": dataset.get("column_mapping"),
                        "topic_label": dataset.get("topic_label"),
                        "source": "api",
                    },
                    success=True,
                )
            except Exception:  # pragma: no cover - logging should not break API
                LOGGER.debug("Failed to persist dataset upload log for project %s", name, exc_info=True)
        except ValueError as exc:
            failures.append({"filename": upload.filename or "", "message": str(exc)})
            last_exception = exc
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to store dataset for project %s", name)
            failures.append({"filename": upload.filename or "", "message": "数据集保存失败"})
            last_exception = exc
            try:
                PROJECT_MANAGER.log_operation(
                    name,
                    "import_dataset",
                    params={"source": "api", "filename": upload.filename},
                    success=False,
                )
            except Exception:  # pragma: no cover - avoid cascading failures
                LOGGER.debug("Unable to persist failed dataset log for project %s", name, exc_info=True)

    if not datasets and failures:
        message = failures[0].get("message") or "数据集保存失败"
        status_code = 400 if isinstance(last_exception, ValueError) else 500
        return jsonify({"status": "error", "message": message, "errors": failures}), status_code

    payload: Dict[str, Any] = {
        "status": "ok",
        "datasets": datasets,
        "count": len(datasets),
    }
    if datasets:
        payload["dataset"] = datasets[-1]
    if failures:
        payload["errors"] = failures

    status_code = 201 if len(failures) == 0 else 207
    return jsonify(payload), status_code


# RAG Configuration endpoints
@app.route("/api/rag/config", methods=["GET"])
def get_rag_config():
    """Get RAG configuration."""
    try:
        config = load_rag_config()
    except Exception as e:
        LOGGER.exception("Failed to load RAG config; returning defaults")
        try:
            config = get_default_rag_config()
        except Exception:
            config = {}

    try:
        # Mask API keys for security
        masked_config = mask_api_keys(config)
    except Exception as mask_exc:  # pragma: no cover - defensive masking
        LOGGER.exception("Failed to mask RAG config: %s", mask_exc)
        masked_config = config if isinstance(config, dict) else {}

    return success({"data": masked_config})


@app.route("/api/rag/config", methods=["POST"])
def save_rag_config():
    """Save RAG configuration."""
    try:
        payload = request.get_json(silent=True) or {}
        config = payload.get("config") if isinstance(payload, dict) and "config" in payload else payload

        if not isinstance(config, dict):
            return error("Invalid RAG configuration payload", 400)

        # Validate configuration
        is_valid, errors = validate_rag_config(config)
        if not is_valid:
            return jsonify({"status": "error", "message": "Invalid RAG configuration", "errors": errors}), 400

        persist_rag_config(config)
        return success({"message": "RAG configuration saved successfully"})
    except Exception as e:
        LOGGER.error(f"Failed to save RAG config: {e}")
        return error("Failed to save RAG configuration", 500)


@app.route("/api/rag/test", methods=["POST"])
def test_rag_config():
    """Test RAG configuration."""
    try:
        payload = request.get_json(silent=True) or {}
        valid, error_response = require_fields(payload, "query")
        if not valid:
            return jsonify(error_response), 400

        query = payload.get("query")

        # TODO: Implement actual RAG test
        # For now, just return a mock response
        results = [
            {
                "id": "test_1",
                "text": f"This is a test result for query: {query}",
                "score": 0.95,
                "metadata": {"source": "test"}
            }
        ]

        return jsonify({"status": "ok", "data": {"results": results, "total": len(results)}})
    except Exception as e:
        LOGGER.error(f"Failed to test RAG: {e}")
        return error(message="Failed to test RAG configuration")


@app.route("/api/rag/embedding/models", methods=["GET"])
def list_embedding_models():
    """List available embedding models."""
    try:
        models = {
            "huggingface": [
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "sentence-transformers/all-MiniLM-L6-v2",
                "sentence-transformers/all-mpnet-base-v2",
                "shibing624/text2vec-base-chinese",
            ],
            "openai": [
                "text-embedding-ada-002",
                "text-embedding-3-small",
                "text-embedding-3-large",
            ]
        }
        return success({"data": models})
    except Exception as e:
        LOGGER.error(f"Failed to list embedding models: {e}")
        return error(message="Failed to list embedding models")


@app.route("/api/settings/rag/prompts", methods=["GET"])
def get_router_prompts():
    """Get RouterRAG prompt configuration for a specific topic."""
    try:
        topic = request.args.get("topic", "")
        reset = request.args.get("reset", "false").lower() == "true"
        
        if not topic:
            return error(message="Missing 'topic' parameter")
        
        if reset:
            from server_support.router_prompts.utils import DEFAULT_ROUTER_PROMPT_CONFIG
            return success({"data": DEFAULT_ROUTER_PROMPT_CONFIG})
        
        # Load the prompt configuration for the topic
        prompts = load_router_prompt_config(topic)
        
        return success({"data": prompts})
    except Exception as e:
        LOGGER.error(f"Failed to load router prompts for topic '{topic}': {e}")
        return error(message=f"Failed to load prompts: {str(e)}")


@app.route("/api/settings/rag/prompts", methods=["POST"])
def save_router_prompts():
    """Save RouterRAG prompt configuration for a specific topic."""
    try:
        payload = request.get_json(silent=True) or {}
        topic = payload.get("topic", "")
        prompts = payload.get("prompts", {})
        
        if not topic:
            return error(message="Missing 'topic' in request body")
        
        if not prompts:
            return error(message="Missing 'prompts' in request body")
        
        # Persist the prompt configuration
        persist_router_prompt_config(topic, prompts)
        
        return success({"message": f"Prompts saved successfully for topic '{topic}'"})
    except Exception as e:
        LOGGER.error(f"Failed to save router prompts: {e}")
        return error(message=f"Failed to save prompts: {str(e)}")


@app.route("/")
def root():
    return jsonify({"message": "OpinionSystem API", "endpoints": [
        "/api/status",
        "/api/config",
        "/api/merge",
        "/api/clean",
        "/api/filter",
        "/api/upload",
        "/api/query",
        "/api/fetch",
        "/api/analyze",
        "/api/analyze/ai-summary/rebuild",
        "/api/report",
        "/api/report/history",
        "/api/report/regenerate",
        "/api/netinsight/tasks",
        "/api/netinsight/tasks/<task_id>/files/<kind>",
        "/api/netinsight/worker",
        "/api/projects",
        "/api/projects/<name>",
        "/api/projects/<name>/datasets",
        "/api/projects/<name>/fetch-cache",
        "/api/fetch/cache",
        "/api/settings/netinsight",
        "/api/rag/config",
        "/api/rag/test",
        "/api/rag/embedding/models",
        "/api/settings/rag/prompts",
    ]})


register_settings_endpoints(app, PROJECT_MANAGER)


def main() -> None:
    host, port = _resolve_runtime_binding()
    LOGGER.info("Starting OpinionSystem backend on %s:%s (set OPINION_BACKEND_PORT to override)", host, port)
    try:
        app.run(host=host, port=port)
    except OSError as exc:  # pragma: no cover - defensive handling for production issues
        # Windows reports WinError 10013 when a port is blocked by permissions/firewall rules.
        # On Unix the equivalent errno is typically 13 (EACCES) or 98 (EADDRINUSE).
        winerror = getattr(exc, "winerror", None)
        if winerror == 10013 or exc.errno in {13, 98, 10013}:  # type: ignore[arg-type]
            LOGGER.error(
                "Unable to bind OpinionSystem backend to %s:%s. "
                "The port is either already in use or blocked by your operating system. "
                "Please choose a different port via OPINION_BACKEND_PORT or free the existing one.",
                host,
                port,
            )
            raise SystemExit(1) from exc
        raise





# ====== RAG (Retrieval-Augmented Generation) API Endpoints ======

@app.get("/api/rag/topics")
def get_rag_topics():
    """获取可用的RAG专题列表"""
    try:
        project = str(request.args.get("project") or "").strip()
        project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
        project_bucket = project_bucket or project
        tagrag_topics: List[str] = []
        router_topics: List[str] = []

        if project_bucket:
            tagrag_topics = list_project_tagrag_topics(project_bucket)
            router_topics = list_project_routerrag_topics(project_bucket)
            return success({
                "data": {
                    "tagrag_topics": sorted({t.strip() for t in tagrag_topics if str(t).strip()}),
                    "router_topics": sorted({t.strip() for t in router_topics if str(t).strip()}),
                }
            })

        # No fallback to src/utils/rag when project is not provided.

        return success({
            "data": {
                "tagrag_topics": sorted({t.strip() for t in tagrag_topics if str(t).strip()}),
                "router_topics": sorted({t.strip() for t in router_topics if str(t).strip()})
            }
        })
    except Exception as exc:
        LOGGER.exception("Failed to get RAG topics")
        return error(f"获取RAG专题列表失败: {str(exc)}")


@app.get("/api/rag/cache/status")
def get_rag_cache_status():
    project = str(request.args.get("project") or "").strip()
    topic = str(request.args.get("topic") or "").strip()
    rag_type = str(request.args.get("type") or "").strip() or "tagrag"

    if not project or not topic:
        return error("Missing required field(s): project, topic")

    project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
    project_bucket = project_bucket or project

    status = get_rag_build_status(project_bucket, rag_type, topic)
    return success({"data": status})


@app.post("/api/rag/build")
def rag_build():
    payload = request.get_json(silent=True) or {}
    topic = str(payload.get("topic") or "").strip()
    project = str(payload.get("project") or "").strip()
    rag_type = str(payload.get("type") or "").strip() or "tagrag"
    start = str(payload.get("start") or "").strip() or None
    end = str(payload.get("end") or "").strip() or None

    if not topic or not project:
        return error("Missing required field(s): project, topic")

    project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
    project_bucket = project_bucket or project

    status = start_rag_build(
        project_bucket,
        rag_type,
        topic,
        db_topic=topic,
        start=start,
        end=end,
    )
    return success({"data": status})


@app.post("/api/rag/tagrag/retrieve")
def tagrag_retrieve():
    """TagRAG检索接口"""
    try:
        payload = request.get_json(silent=True) or {}

        # Validate required fields
        query = payload.get("query", "").strip()
        topic = payload.get("topic", "").strip()
        project = str(payload.get("project") or "").strip()
        project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
        project_bucket = project_bucket or project
        top_k = payload.get("top_k", 10)

        if not query:
            return error("Missing required field: query")
        if not topic:
            return error("Missing required field: topic")

        if project_bucket and not ensure_rag_ready(project_bucket, "tagrag", topic):
            status = start_rag_build(project_bucket, "tagrag", topic, db_topic=topic)
            return jsonify({
                "status": "building",
                "message": "正在准备检索资料，请稍后再试",
                "data": status,
            }), 202

        # Import TagRAG retrieval
        from src.utils.rag.tagrag.tag_retrieve_data import retrieve_documents

        db_path = None
        if project_bucket:
            db_path = ensure_tagrag_db(topic, project_bucket)

        # Retrieve documents
        results = retrieve_documents(
            query=query,
            topic=topic,
            top_k=top_k,
            threshold=payload.get("threshold", 0.0),
            db_path=str(db_path) if db_path else None,
        )

        return success({"data": {"results": results, "total": len(results)}})
    except Exception as exc:
        LOGGER.exception("Failed to retrieve TagRAG documents")
        return error(f"TagRAG检索失败: {str(exc)}")


@app.post("/api/rag/routerrag/retrieve")
def routerrag_retrieve():
    """RouterRAG检索接口"""
    try:
        payload = request.get_json(silent=True) or {}

        # Validate required fields
        query = payload.get("query", "").strip()
        topic = payload.get("topic", "").strip()
        project = str(payload.get("project") or "").strip()
        project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
        project_bucket = project_bucket or project
        top_k = payload.get("top_k", 10)

        if not query:
            return error("Missing required field: query")
        if not topic:
            return error("Missing required field: topic")

        if project_bucket and not ensure_rag_ready(project_bucket, "routerrag", topic):
            status = start_rag_build(project_bucket, "routerrag", topic, db_topic=topic)
            return jsonify({
                "status": "building",
                "message": "正在准备检索资料，请稍后再试",
                "data": status,
            }), 202

        # Import RouterRAG retrieval
        from src.utils.rag.ragrouter.router_retrieve_data import retrieve_documents

        base_path = None
        if project_bucket:
            base_path = ensure_routerrag_db(topic, project_bucket)

        # Retrieve documents
        mode = payload.get("mode", "normalrag")
        results = retrieve_documents(
            query=query,
            topic=topic,
            top_k=top_k,
            threshold=payload.get("threshold", 0.0),
            mode=mode,
            db_base_path=base_path,
        )

        if isinstance(results, dict):
            return success({"data": results})
        return success({"data": {"results": results, "total": len(results)}})
    except Exception as exc:
        LOGGER.exception("Failed to retrieve RouterRAG documents")
        return error(f"RouterRAG检索失败: {str(exc)}")


@app.post("/api/rag/universal/retrieve")
def universal_rag_retrieve():
    """通用RAG检索接口（支持多种检索策略）"""
    try:
        payload = request.get_json(silent=True) or {}

        # Validate required fields
        query = payload.get("query", "").strip()
        topic = payload.get("topic", "").strip()
        rag_type = payload.get("rag_type", "tagrag")  # tagrag, routerrag, hybrid
        project = str(payload.get("project") or "").strip()
        project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
        project_bucket = project_bucket or project
        top_k = payload.get("top_k", 10)

        if not query:
            return error("Missing required field: query")
        if not topic:
            return error("Missing required field: topic")

        results = []

        if rag_type == "tagrag":
            from src.utils.rag.tagrag.tag_retrieve_data import retrieve_documents
            if project_bucket and not ensure_rag_ready(project_bucket, "tagrag", topic):
                status = start_rag_build(project_bucket, "tagrag", topic, db_topic=topic)
                return jsonify({
                    "status": "building",
                    "message": "正在准备检索资料，请稍后再试",
                    "data": status,
                }), 202
            db_path = ensure_tagrag_db(topic, project_bucket) if project_bucket else None
            results = retrieve_documents(query=query, topic=topic, top_k=top_k, db_path=str(db_path) if db_path else None)

        elif rag_type == "routerrag":
            from src.utils.rag.ragrouter.router_retrieve_data import retrieve_documents
            if project_bucket and not ensure_rag_ready(project_bucket, "routerrag", topic):
                status = start_rag_build(project_bucket, "routerrag", topic, db_topic=topic)
                return jsonify({
                    "status": "building",
                    "message": "正在准备检索资料，请稍后再试",
                    "data": status,
                }), 202
            base_path = ensure_routerrag_db(topic, project_bucket) if project_bucket else None
            results = retrieve_documents(query=query, topic=topic, top_k=top_k, db_base_path=base_path)

        elif rag_type == "hybrid":
            # Combine results from both systems
            try:
                from src.utils.rag.tagrag.tag_retrieve_data import retrieve_documents as tagrag_retrieve
                from src.utils.rag.ragrouter.router_retrieve_data import retrieve_documents as router_retrieve

                if project_bucket:
                    if not ensure_rag_ready(project_bucket, "tagrag", topic):
                        status = start_rag_build(project_bucket, "tagrag", topic, db_topic=topic)
                        return jsonify({
                            "status": "building",
                            "message": "正在准备检索资料，请稍后再试",
                            "data": status,
                        }), 202
                    if not ensure_rag_ready(project_bucket, "routerrag", topic):
                        status = start_rag_build(project_bucket, "routerrag", topic, db_topic=topic)
                        return jsonify({
                            "status": "building",
                            "message": "正在准备检索资料，请稍后再试",
                            "data": status,
                        }), 202

                tag_db_path = ensure_tagrag_db(topic, project_bucket) if project_bucket else None
                router_base_path = ensure_routerrag_db(topic, project_bucket) if project_bucket else None
                tagrag_results = tagrag_retrieve(query=query, topic=topic, top_k=top_k // 2, db_path=str(tag_db_path) if tag_db_path else None)
                router_payload = router_retrieve(query=query, topic=topic, top_k=top_k // 2, db_base_path=router_base_path)
                
                router_results = router_payload.get("results", []) if isinstance(router_payload, dict) else router_payload
                summary = router_payload.get("summary", "") if isinstance(router_payload, dict) else ""

                # Combine and deduplicate
                results = tagrag_results + router_results
                results = results[:top_k]  # Limit to top_k
                
                if summary:
                    # If we have a summary, return the dict format
                    results = {"results": results, "total": len(results), "summary": summary}
            except Exception as e:
                LOGGER.warning(f"Hybrid retrieval failed, falling back to TagRAG: {e}")
                from src.utils.rag.tagrag.tag_retrieve_data import retrieve_documents
                results = retrieve_documents(query=query, topic=topic, top_k=top_k)

        if isinstance(results, dict):
            if "rag_type" not in results:
                results["rag_type"] = rag_type
            return success({"data": results})
        return success({"data": {"results": results, "total": len(results), "rag_type": rag_type}})
    except Exception as exc:
        LOGGER.exception("Failed to retrieve documents")
        return error(f"检索失败: {str(exc)}")


@app.post("/api/rag/export")
def export_rag_data():
    """导出RAG数据格式"""
    try:
        payload = request.get_json(silent=True) or {}

        # Validate required fields
        input_path = payload.get("input_path", "").strip()
        output_path = payload.get("output_path", "").strip()
        topic = payload.get("topic", "").strip()

        if not input_path or not output_path:
            return error("Missing required fields: input_path, output_path")

        # Import converter
        from src.rag.cli.export_tagrag import export_tagrag_texts
        from pathlib import Path

        # Run export
        export_tagrag_texts(
            input_path=Path(input_path),
            output_path=Path(output_path),
            topic=topic or "export",
            chunk_size=payload.get("chunk_size", 3),
            chunk_strategy=payload.get("chunk_strategy", "count")
        )

        return success({"message": "导出成功", "output_path": output_path})
    except Exception as exc:
        LOGGER.exception("Failed to export RAG data")
        return error(f"导出失败: {str(exc)}")


if __name__ == "__main__":
    main()
