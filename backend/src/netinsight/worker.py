"""Background worker subprocess for NetInsight queue execution."""
from __future__ import annotations

import csv
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BACKEND_DIR / "src"
for path in (BACKEND_DIR, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.netinsight.client import NetInsightError  # type: ignore
from src.netinsight.client import RequestContext  # type: ignore
from src.netinsight.client import collect_platform_records  # type: ignore
from src.netinsight.client import deduplicate_records  # type: ignore
from src.netinsight.client import login_and_capture  # type: ignore
from src.netinsight.client import query_platform_counts  # type: ignore
from src.netinsight.config import load_netinsight_config  # type: ignore
from src.netinsight.config import resolve_netinsight_credentials  # type: ignore
from src.netinsight.task_queue import (  # type: ignore
    get_task,
    load_worker_status,
    mark_task_cancelled,
    mark_task_completed,
    mark_task_failed,
    mark_task_progress,
    output_dir_for_task,
    read_session_state,
    reserve_next_task,
    should_cancel,
    store_search_plan,
    write_session_state,
    write_worker_status,
)

LOGGER = logging.getLogger(__name__)


class TaskCancelled(RuntimeError):
    """Raised when the queue item was cancelled by the user."""


def main() -> None:
    config = load_netinsight_config()
    runtime = config.get("runtime", {})
    idle_seconds = max(15, int(runtime.get("worker_idle_seconds") or 90))
    started_at = utc_now()
    last_active_at = time.monotonic()

    write_worker_status(
        {
            "pid": os_getpid(),
            "status": "idle",
            "running": True,
            "current_task_id": "",
            "last_heartbeat": utc_now(),
            "started_at": started_at,
        }
    )

    try:
        while True:
            task = reserve_next_task()
            if not task:
                write_worker_status(
                    {
                        "pid": os_getpid(),
                        "status": "idle",
                        "running": True,
                        "current_task_id": "",
                        "last_heartbeat": utc_now(),
                        "started_at": started_at,
                    }
                )
                if time.monotonic() - last_active_at >= idle_seconds:
                    write_worker_status(
                        {
                            "pid": os_getpid(),
                            "status": "stopped",
                            "running": False,
                            "current_task_id": "",
                            "last_heartbeat": utc_now(),
                            "started_at": started_at,
                        }
                    )
                    return
                time.sleep(2.0)
                continue

            last_active_at = time.monotonic()
            task_id = str(task.get("id") or "")
            write_worker_status(
                {
                    "pid": os_getpid(),
                    "status": "running",
                    "running": True,
                    "current_task_id": task_id,
                    "last_heartbeat": utc_now(),
                    "started_at": started_at,
                }
            )
            try:
                _run_task(task_id)
            except TaskCancelled as exc:
                mark_task_cancelled(task_id, str(exc))
            except Exception as exc:
                mark_task_failed(task_id, str(exc))
    except Exception:
        LOGGER.exception("NetInsight worker crashed")
        raise
    finally:
        write_worker_status(
            {
                "pid": os_getpid(),
                "status": "stopped",
                "running": False,
                "current_task_id": "",
                "last_heartbeat": utc_now(),
                "started_at": started_at,
            }
        )


def _run_task(task_id: str) -> None:
    task = get_task(task_id)
    runtime = load_netinsight_config().get("runtime", {})
    credentials = resolve_netinsight_credentials()
    username = credentials.get("user") or ""
    password = credentials.get("pass") or ""
    if not username or not password:
        raise NetInsightError("NetInsight 账号或密码未配置，请先到设置页保存账号信息。")

    if should_cancel(task_id):
        raise TaskCancelled("任务在启动前已被取消")

    keywords = list(task.get("keywords") or [])
    platforms = list(task.get("platforms") or [])
    config = task.get("config", {})
    time_range = str(config.get("time_range") or "")
    total_limit = max(1, int(config.get("total_limit") or 500))
    page_size = max(10, int(config.get("page_size") or 50))
    sort = str(config.get("sort") or "comments_desc")
    info_type = str(config.get("info_type") or "2")
    per_platform_limit = max(1, total_limit // max(len(platforms), 1))

    context_source = "cached"
    context = _load_cached_context(task_id, username)
    if not context:
        context_source = "fresh"
        context = _login_with_progress(
            task_id=task_id,
            username=username,
            password=password,
            runtime=runtime,
            initial_message="正在登录 NetInsight",
        )

    counts_total = max(len(keywords) * len(platforms), 1)
    counts_completed = 0
    aggregated_plan: Dict[str, Any] = {}
    planned_total = 0
    all_warnings: List[str] = []

    for platform in platforms:
        _raise_if_cancelled(task_id)
        try:
            result = query_platform_counts(
                keywords=keywords,
                time_range=time_range,
                platform=platform,
                threshold=per_platform_limit,
                context=context,
                progress_callback=lambda payload, current_platform=platform, done=counts_completed: _handle_count_progress(
                    task_id,
                    payload,
                    current_platform=current_platform,
                    counts_completed_base=done,
                    counts_total=counts_total,
                ),
            )
        except NetInsightError as exc:
            if context_source == "cached" and _is_login_expired(exc):
                context_source = "fresh"
                context = _login_with_progress(
                    task_id=task_id,
                    username=username,
                    password=password,
                    runtime=runtime,
                    initial_message="缓存登录已失效，正在重新登录 NetInsight",
                )
                result = query_platform_counts(
                    keywords=keywords,
                    time_range=time_range,
                    platform=platform,
                    threshold=per_platform_limit,
                    context=context,
                    progress_callback=lambda payload, current_platform=platform, done=counts_completed: _handle_count_progress(
                        task_id,
                        payload,
                        current_platform=current_platform,
                        counts_completed_base=done,
                        counts_total=counts_total,
                    ),
                )
            else:
                raise
        counts_completed += len(keywords)
        aggregated_plan[platform] = result
        planned_total += int(result.get("planned_total") or 0)
        all_warnings.extend(result.get("warnings") or [])
        mark_task_progress(
            task_id,
            phase="count",
            message=f"{platform} 计数完成",
            percentage=5 + int((counts_completed / counts_total) * 15),
            current_platform=platform,
            counts_completed=counts_completed,
            counts_total=counts_total,
            planned_total=planned_total,
        )

    store_search_plan(task_id, aggregated_plan)
    if planned_total <= 0:
        warning_text = "；".join(all_warnings[:5])
        raise NetInsightError(f"未获得可采集的数据量。{warning_text}".strip())

    all_records: List[Dict[str, Any]] = []
    search_summary: Dict[str, Any] = {}
    for platform_index, platform in enumerate(platforms, start=1):
        _raise_if_cancelled(task_id)
        platform_plan = aggregated_plan.get(platform) or {}
        search_matrix = platform_plan.get("search_matrix") or {}
        try:
            result = collect_platform_records(
                search_matrix=search_matrix,
                time_range=time_range,
                platform=platform,
                context=context,
                page_size=page_size,
                sort=sort,
                info_type=info_type,
                task_id=task_id,
                progress_callback=lambda payload, idx=platform_index: _handle_collect_progress(
                    task_id,
                    payload,
                    planned_total=planned_total,
                    platform_index=idx,
                    platform_total=len(platforms),
                ),
            )
        except NetInsightError as exc:
            if context_source == "cached" and _is_login_expired(exc):
                context_source = "fresh"
                context = _login_with_progress(
                    task_id=task_id,
                    username=username,
                    password=password,
                    runtime=runtime,
                    initial_message="缓存登录已失效，正在重新登录 NetInsight",
                )
                result = collect_platform_records(
                    search_matrix=search_matrix,
                    time_range=time_range,
                    platform=platform,
                    context=context,
                    page_size=page_size,
                    sort=sort,
                    info_type=info_type,
                    task_id=task_id,
                    progress_callback=lambda payload, idx=platform_index: _handle_collect_progress(
                        task_id,
                        payload,
                        planned_total=planned_total,
                        platform_index=idx,
                        platform_total=len(platforms),
                    ),
                )
            else:
                raise
        records = result.get("records") or []
        summary = result.get("search_summary") or {}
        all_records.extend(records)
        search_summary[platform] = summary
        mark_task_progress(
            task_id,
            phase="collect",
            message=f"{platform} 采集完成，累计 {len(all_records)} 条",
            percentage=min(90, 20 + int((len(all_records) / max(planned_total, 1)) * 70)),
            current_platform=platform,
            fetched_total=len(all_records),
            planned_total=planned_total,
        )

    _raise_if_cancelled(task_id)
    output_dir = output_dir_for_task(task)
    raw_count = len(all_records)
    dedupe_enabled = bool(config.get("dedupe_by_content", True))
    if dedupe_enabled:
        deduped_records, removed_duplicates = deduplicate_records(all_records)
    else:
        deduped_records, removed_duplicates = list(all_records), 0

    if not deduped_records:
        raise NetInsightError("采集完成，但没有可存储的数据记录。")

    mark_task_progress(
        task_id,
        phase="export",
        message="正在导出 CSV / JSONL 文件",
        percentage=95,
        fetched_total=raw_count,
        deduped_total=len(deduped_records),
    )
    output = _export_outputs(
        output_dir=output_dir,
        task=task,
        records=deduped_records,
        raw_count=raw_count,
        removed_duplicates=removed_duplicates,
        search_plan=aggregated_plan,
        search_summary=search_summary,
        warnings=all_warnings,
    )
    mark_task_completed(
        task_id,
        output,
        f"采集完成，导出 {len(deduped_records)} 条记录",
    )


def _load_cached_context(task_id: str, username: str) -> RequestContext | None:
    session_state = read_session_state()
    saved_user = str(session_state.get("username") or "").strip()
    headers = session_state.get("headers")
    cookies = session_state.get("cookies")
    if saved_user != username or not isinstance(headers, dict) or not isinstance(cookies, dict):
        return None

    LOGGER.info(
        "NetInsight worker | task=%s reusing cached session saved_at=%s",
        task_id,
        str(session_state.get("saved_at") or ""),
    )
    mark_task_progress(
        task_id,
        phase="login",
        message="正在复用已登录的 NetInsight 会话",
        percentage=5,
        event_level="info",
    )
    return RequestContext(
        headers={str(key): str(value) for key, value in headers.items()},
        cookies={str(key): str(value) for key, value in cookies.items()},
    )


def _login_with_progress(
    *,
    task_id: str,
    username: str,
    password: str,
    runtime: Dict[str, Any],
    initial_message: str,
) -> RequestContext:
    mark_task_progress(
        task_id,
        phase="login",
        message=initial_message,
        percentage=5,
        event_level="info",
    )

    def _on_login_step(message: str) -> None:
        LOGGER.info("NetInsight worker login | task=%s step=%s", task_id, message)
        mark_task_progress(
            task_id,
            phase="login",
            message=message,
            percentage=8,
        )

    context = login_and_capture(
        username=username,
        password=password,
        headless=bool(runtime.get("headless", False)),
        no_proxy=bool(runtime.get("no_proxy", False)),
        login_timeout_ms=int(runtime.get("login_timeout_ms") or 120000),
        browser_channel=str(runtime.get("browser_channel") or ""),
        progress_callback=_on_login_step,
    )
    write_session_state(
        {
            "username": username,
            "saved_at": utc_now(),
            "headers": context.headers,
            "cookies": context.cookies,
        }
    )
    return context


def _is_login_expired(exc: Exception) -> bool:
    message = str(exc or "")
    return "登录态已失效" in message or "code=515" in message or "会话 Cookie" in message


def _handle_count_progress(
    task_id: str,
    payload: Dict[str, Any],
    *,
    current_platform: str,
    counts_completed_base: int,
    counts_total: int,
) -> None:
    counts_completed = counts_completed_base + int(payload.get("index") or 0)
    message = (
        f"正在统计 {current_platform} / {payload.get('keyword') or ''}，"
        f"可用量 {int(payload.get('count') or 0)}"
    )
    mark_task_progress(
        task_id,
        phase="count",
        message=message,
        percentage=5 + int((counts_completed / max(counts_total, 1)) * 15),
        current_platform=current_platform,
        current_keyword=str(payload.get("keyword") or ""),
        counts_completed=counts_completed,
        counts_total=counts_total,
    )


def _handle_collect_progress(
    task_id: str,
    payload: Dict[str, Any],
    *,
    planned_total: int,
    platform_index: int,
    platform_total: int,
) -> None:
    fetched_total = int(payload.get("fetched_total") or 0)
    message = (
        f"正在抓取 {payload.get('platform') or ''} / {payload.get('keyword') or ''} "
        f"第 {payload.get('page') or 0}/{payload.get('pages') or 0} 页"
    )
    base_percentage = 20 + int((fetched_total / max(planned_total, 1)) * 70)
    boost = int(((platform_index - 1) / max(platform_total, 1)) * 5)
    mark_task_progress(
        task_id,
        phase="collect",
        message=message,
        percentage=min(90, base_percentage + boost),
        current_platform=str(payload.get("platform") or ""),
        current_keyword=str(payload.get("keyword") or ""),
        planned_total=planned_total,
        fetched_total=fetched_total,
    )
    _raise_if_cancelled(task_id)


def _raise_if_cancelled(task_id: str) -> None:
    if should_cancel(task_id):
        raise TaskCancelled("任务已按请求取消")


def _export_outputs(
    *,
    output_dir: Path,
    task: Dict[str, Any],
    records: List[Dict[str, Any]],
    raw_count: int,
    removed_duplicates: int,
    search_plan: Dict[str, Any],
    search_summary: Dict[str, Any],
    warnings: List[str],
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "records.csv"
    jsonl_path = output_dir / "records.jsonl"
    meta_path = output_dir / "meta.json"

    _write_csv(csv_path, records)
    _write_jsonl(jsonl_path, records)

    meta = {
        "task_id": task.get("id"),
        "title": task.get("title"),
        "project": task.get("project"),
        "keywords": task.get("keywords"),
        "platforms": task.get("platforms"),
        "config": task.get("config"),
        "record_count": len(records),
        "raw_count": raw_count,
        "removed_duplicates": removed_duplicates,
        "search_plan": search_plan,
        "search_summary": search_summary,
        "warnings": warnings,
        "generated_at": utc_now(),
    }
    with meta_path.open("w", encoding="utf-8") as stream:
        json.dump(meta, stream, ensure_ascii=False, indent=2)

    return {
        "dir": str(output_dir),
        "files": [str(csv_path), str(jsonl_path), str(meta_path)],
        "record_count": raw_count,
        "deduplicated_count": len(records),
        "removed_duplicates": removed_duplicates,
    }


def _write_csv(path: Path, records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    fieldnames = list(records[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({key: _stringify(value) for key, value in record.items()})


def _write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False))
            stream.write("\n")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def os_getpid() -> int:
    import os

    return os.getpid()


if __name__ == "__main__":
    main()
