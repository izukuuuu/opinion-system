"""Background worker subprocess for report queue execution."""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

BACKEND_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BACKEND_DIR / "src"
for path in (BACKEND_DIR, SRC_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from server_support.archive_locator import compose_folder_name  # type: ignore
from server_support.topic_context import TopicContext  # type: ignore
from src.report.full_report_service import (  # type: ignore
    AI_FULL_REPORT_CACHE_FILENAME,
    generate_full_report_payload,
)
from src.report.runtime import ensure_analyze_results, ensure_explain_results  # type: ignore
from src.report.structured_service import REPORT_CACHE_FILENAME, generate_report_payload  # type: ignore
from src.report.task_queue import (  # type: ignore
    append_agent_memo,
    append_event,
    get_task,
    mark_agent_started,
    mark_artifact_ready,
    mark_task_cancelled,
    mark_task_completed,
    mark_task_failed,
    mark_task_progress,
    reserve_next_task,
    set_worker_pid,
    should_cancel,
    write_worker_status,
)
from src.utils.setting.paths import bucket  # type: ignore

LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
)
PHASE_PERCENTAGE = {
    "prepare": 5,
    "analyze": 18,
    "explain": 32,
    "interpret": 58,
    "write": 82,
    "review": 93,
    "persist": 98,
}


class TaskCancelled(RuntimeError):
    """Raised when the queue item was cancelled by the user."""


def main() -> None:
    started_at = _utc_now()
    idle_seconds = 90
    last_active_at = time.monotonic()
    write_worker_status(
        {
            "pid": os.getpid(),
            "status": "idle",
            "running": True,
            "current_task_id": "",
            "last_heartbeat": _utc_now(),
            "started_at": started_at,
        }
    )
    try:
        while True:
            task = reserve_next_task()
            if not task:
                write_worker_status(
                    {
                        "pid": os.getpid(),
                        "status": "idle",
                        "running": True,
                        "current_task_id": "",
                        "last_heartbeat": _utc_now(),
                        "started_at": started_at,
                    }
                )
                if time.monotonic() - last_active_at >= idle_seconds:
                    write_worker_status(
                        {
                            "pid": os.getpid(),
                            "status": "stopped",
                            "running": False,
                            "current_task_id": "",
                            "last_heartbeat": _utc_now(),
                            "started_at": started_at,
                        }
                    )
                    return
                time.sleep(2.0)
                continue

            last_active_at = time.monotonic()
            task_id = str(task.get("id") or "")
            set_worker_pid(task_id, os.getpid())
            write_worker_status(
                {
                    "pid": os.getpid(),
                    "status": "running",
                    "running": True,
                    "current_task_id": task_id,
                    "last_heartbeat": _utc_now(),
                    "started_at": started_at,
                }
            )
            try:
                _run_task(task_id)
            except TaskCancelled as exc:
                mark_task_cancelled(task_id, str(exc))
            except Exception as exc:
                LOGGER.exception("Report worker failed | task=%s", task_id)
                mark_task_failed(task_id, str(exc))
    finally:
        write_worker_status(
            {
                "pid": os.getpid(),
                "status": "stopped",
                "running": False,
                "current_task_id": "",
                "last_heartbeat": _utc_now(),
                "started_at": started_at,
            }
        )


def _run_task(task_id: str) -> None:
    task = get_task(task_id)
    request = dict(task.get("request") or {})
    topic_identifier = str(request.get("topic_identifier") or task.get("topic_identifier") or "").strip()
    topic_label = str(request.get("topic") or task.get("topic") or topic_identifier).strip() or topic_identifier
    start = str(request.get("start") or task.get("start") or "").strip()
    end = str(request.get("end") or task.get("end") or start).strip() or start
    mode = str(request.get("mode") or task.get("mode") or "fast").strip().lower() or "fast"
    aliases = [
        str(item).strip()
        for item in (request.get("aliases") or [])
        if str(item or "").strip()
    ]
    ctx = TopicContext(identifier=topic_identifier, display_name=topic_label, aliases=aliases)
    LOGGER.warning(
        "report worker | task start | task=%s topic=%s start=%s end=%s mode=%s",
        task_id,
        topic_identifier,
        start,
        end,
        mode,
    )

    stop_event = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_loop,
        args=(task_id, stop_event, task.get("started_at") or _utc_now()),
        daemon=True,
    )
    heartbeat.start()
    try:
        _raise_if_cancelled(task_id)
        mark_agent_started(
            task_id,
            agent="researcher",
            phase="prepare",
            message="Researcher 正在检查专题数据和历史产物。",
        )
        mark_task_progress(task_id, phase="prepare", percentage=PHASE_PERCENTAGE["prepare"], message="正在检查基础数据是否完备。")
        mark_task_progress(task_id, phase="analyze", percentage=PHASE_PERCENTAGE["analyze"], message="Researcher 正在确认基础分析结果。")

        analyze_prepare = ensure_analyze_results(
            topic_identifier,
            start=start,
            end=end,
            ctx=ctx,
        )
        LOGGER.warning(
            "report worker | analyze ready | task=%s prepared=%s root=%s",
            task_id,
            bool(analyze_prepare.get("prepared")),
            analyze_prepare.get("analyze_root"),
        )
        append_agent_memo(
            task_id,
            agent="researcher",
            phase="analyze",
            message=analyze_prepare.get("message") or "基础分析结果已就绪。",
            delta=str(analyze_prepare.get("message") or "基础分析结果已就绪。"),
            payload=analyze_prepare,
        )
        _raise_if_cancelled(task_id)

        mark_task_progress(task_id, phase="explain", percentage=PHASE_PERCENTAGE["explain"], message="Researcher 正在补齐总体文字解读。")
        explain_prepare = ensure_explain_results(
            topic_identifier,
            start=start,
            end=end,
            ctx=ctx,
        )
        if not bool(explain_prepare.get("ready")):
            LOGGER.warning(
                "report worker | explain still incomplete | task=%s source=%s smart_fill=%s available=%s/%s",
                task_id,
                explain_prepare.get("source"),
                explain_prepare.get("smart_fill"),
                explain_prepare.get("available_count"),
                explain_prepare.get("expected_count"),
            )
        else:
            LOGGER.warning(
                "report worker | explain ready | task=%s source=%s generated=%s",
                task_id,
                explain_prepare.get("source"),
                (explain_prepare.get("smart_fill") or {}).get("generated_functions"),
            )
        append_agent_memo(
            task_id,
            agent="researcher",
            phase="explain",
            message=explain_prepare.get("message") or "总体文字解读检查完成。",
            delta=str(explain_prepare.get("message") or "总体文字解读检查完成。"),
            payload=explain_prepare,
        )
        if mode == "research":
            append_agent_memo(
                task_id,
                agent="researcher",
                phase="explain",
                message="当前任务使用 research 模式，会保留更完整的调研轨迹。",
                delta="当前任务使用 research 模式，会保留更完整的调研轨迹。",
            )
        _raise_if_cancelled(task_id)

        report_payload = generate_report_payload(
            topic_identifier,
            start,
            end,
            topic_label=topic_label,
            regenerate=True,
            event_callback=lambda event: _handle_report_event(task_id, event),
        )
        LOGGER.warning(
            "report worker | report payload generated | task=%s title=%s",
            task_id,
            str(report_payload.get("title") or "").strip(),
        )
        _raise_if_cancelled(task_id)

        full_report_payload = generate_full_report_payload(
            topic_identifier,
            start,
            end,
            topic_label=topic_label,
            regenerate=True,
            structured_payload=report_payload,
            event_callback=lambda event: _handle_report_event(task_id, event),
        )
        LOGGER.warning(
            "report worker | full report payload generated | task=%s title=%s",
            task_id,
            str(full_report_payload.get("title") or "").strip(),
        )
        _raise_if_cancelled(task_id)

        folder = compose_folder_name(start, end)
        cache_path = bucket("reports", topic_identifier, folder) / REPORT_CACHE_FILENAME
        full_cache_path = bucket("reports", topic_identifier, folder) / AI_FULL_REPORT_CACHE_FILENAME
        mark_task_progress(task_id, phase="persist", percentage=PHASE_PERCENTAGE["persist"], message="正在写入最终报告缓存。")
        mark_artifact_ready(
            task_id,
            message="结构化报告与 AI 完整报告缓存已写入。",
            payload={
                "report_ready": True,
                "report_cache_path": str(cache_path),
                "report_title": str(report_payload.get("title") or "").strip(),
                "full_report_ready": True,
                "full_report_cache_path": str(full_cache_path),
                "full_report_title": str(full_report_payload.get("title") or "").strip(),
                "view": {
                    "topic": topic_label,
                    "topic_identifier": topic_identifier,
                    "start": start,
                    "end": end,
                },
            },
        )
        mark_task_completed(
            task_id,
            message="报告已生成。",
            payload={
                "report_ready": True,
                "report_cache_path": str(cache_path),
                "report_title": str(report_payload.get("title") or "").strip(),
                "full_report_ready": True,
                "full_report_cache_path": str(full_cache_path),
                "full_report_title": str(full_report_payload.get("title") or "").strip(),
            },
        )
        LOGGER.warning(
            "report worker | task completed | task=%s cache=%s full_cache=%s",
            task_id,
            cache_path,
            full_cache_path,
        )
    finally:
        stop_event.set()
        heartbeat.join(timeout=1.0)


def _heartbeat_loop(task_id: str, stop_event: threading.Event, started_at: str) -> None:
    while not stop_event.wait(12.0):
        try:
            task = get_task(task_id)
            write_worker_status(
                {
                    "pid": os.getpid(),
                    "status": "running",
                    "running": True,
                    "current_task_id": task_id,
                    "last_heartbeat": _utc_now(),
                    "started_at": started_at,
                }
            )
            append_event(
                task_id,
                event_type="heartbeat",
                phase=str(task.get("phase") or ""),
                title="worker heartbeat",
                message=str(task.get("message") or "").strip() or "worker 仍在运行。",
                payload={"worker_pid": os.getpid()},
            )
        except Exception:
            continue


def _handle_report_event(task_id: str, event: Dict[str, Any]) -> None:
    _raise_if_cancelled(task_id)
    if not isinstance(event, dict):
        return
    event_type = str(event.get("type") or "").strip()
    phase = str(event.get("phase") or "").strip() or "interpret"
    title = str(event.get("title") or "").strip()
    message = str(event.get("message") or "").strip()
    agent = str(event.get("agent") or "").strip()
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if event_type == "task.failed":
        LOGGER.warning(
            "report worker | callback event | task=%s type=%s phase=%s message=%s payload=%s",
            task_id,
            event_type,
            phase,
            message,
            payload,
        )
    if event_type == "phase.started":
        mark_task_progress(task_id, phase=phase, percentage=PHASE_PERCENTAGE.get(phase, 60), message=message or title or "阶段已开始。")
        return
    if event_type == "phase.progress":
        mark_task_progress(task_id, phase=phase, percentage=PHASE_PERCENTAGE.get(phase, 60), message=message or title or "阶段执行中。")
        return
    if event_type == "agent.started":
        mark_agent_started(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            message=message or title or "Agent 已启动。",
            title=title,
            payload=payload,
        )
        return
    if event_type == "agent.memo":
        append_agent_memo(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            message=message or title or "Agent 已输出公开备忘录。",
            title=title,
            delta=str(event.get("delta") or "").strip(),
            payload=payload,
        )
        return
    if event_type == "tool.called":
        from src.report.task_queue import record_tool_call  # type: ignore

        record_tool_call(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            title=title or "工具调用",
            message=message or "Agent 正在调用工具。",
            payload=payload,
        )
        return
    if event_type == "tool.result":
        from src.report.task_queue import record_tool_result  # type: ignore

        record_tool_result(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            title=title or "工具回执",
            message=message or "Agent 已拿到工具结果。",
            payload=payload,
        )
        return
    if event_type == "artifact.ready":
        mark_artifact_ready(task_id, message=message or "报告产物已写入。", payload=payload)
        return
    append_event(
        task_id,
        event_type=event_type or "phase.progress",
        phase=phase,
        agent=agent,
        title=title,
        message=message,
        delta=str(event.get("delta") or "").strip(),
        payload=payload,
    )


def _raise_if_cancelled(task_id: str) -> None:
    if should_cancel(task_id):
        raise TaskCancelled("任务已按请求取消。")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
