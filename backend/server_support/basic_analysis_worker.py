"""Background worker subprocess for basic analysis queue execution."""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

BACKEND_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BACKEND_DIR / "src"
for path in (BACKEND_DIR, SRC_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from server_support.basic_analysis import (  # type: ignore
    get_task,
    load_worker_status,
    mark_task_cancelled,
    mark_task_completed,
    mark_task_failed,
    mark_task_progress,
    reserve_next_task,
    should_cancel,
    write_worker_status,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)

_IDLE_TIMEOUT_SECONDS = 90
_HEARTBEAT_INTERVAL_SECONDS = 12


class TaskCancelled(RuntimeError):
    """任务已取消异常。"""
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raise_if_cancelled(task_id: str) -> None:
    if should_cancel(task_id):
        raise TaskCancelled("任务已按请求取消")


def _heartbeat_loop(
    task_id: str,
    stop_event: threading.Event,
    started_at: str,
) -> None:
    """心跳线程。"""
    while not stop_event.wait(_HEARTBEAT_INTERVAL_SECONDS):
        try:
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
        except Exception:
            continue


def _run_task(task_id: str) -> None:
    """执行单个任务。"""
    task = get_task(task_id)
    topic_identifier = str(task.get("topic_identifier") or "").strip()
    start_date = str(task.get("start_date") or "").strip()
    end_date = str(task.get("end_date") or "").strip() or None
    only_function = str(task.get("only_function") or "").strip() or None

    stop_event = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(task_id, stop_event, task.get("started_at") or _utc_now()),
        daemon=True,
    )
    heartbeat_thread.start()

    try:
        _raise_if_cancelled(task_id)
        mark_task_progress(
            task_id,
            status="running",
            phase="prepare",
            percentage=5,
            message="正在检查数据目录和加载配置。",
            progress={"current_phase": "prepare"},
        )

        from src.analyze.runner import run_Analyze_with_progress  # type: ignore
        from src.utils.setting.paths import bucket  # type: ignore

        date_range = f"{start_date}_{end_date}" if end_date else start_date

        def _progress_callback(payload: Dict[str, Any]) -> None:
            _raise_if_cancelled(task_id)
            phase = str(payload.get("phase") or "analyze").strip()
            percentage = int(payload.get("percentage") or 0)
            message = str(payload.get("message") or "").strip()
            progress_update = {
                "total_functions": int(payload.get("total_functions") or 0),
                "completed_functions": int(payload.get("completed_functions") or 0),
                "current_function": str(payload.get("current_function") or "").strip(),
                "current_target": str(payload.get("current_target") or "").strip(),
                # 情感分析进度
                "sentiment_phase": str(payload.get("sentiment_phase") or "").strip(),
                "sentiment_total": int(payload.get("sentiment_total") or 0),
                "sentiment_processed": int(payload.get("sentiment_processed") or 0),
                "sentiment_classified": int(payload.get("sentiment_classified") or 0),
                "sentiment_remaining": int(payload.get("sentiment_remaining") or 0),
            }
            mark_task_progress(
                task_id,
                status="running",
                phase=phase,
                percentage=percentage,
                message=message,
                progress=progress_update,
            )

        success = run_Analyze_with_progress(
            topic_identifier,
            start_date,
            end_date=end_date,
            only_function=only_function,
            progress_callback=_progress_callback,
        )

        _raise_if_cancelled(task_id)

        if not success:
            raise RuntimeError("基础分析未生成有效结果")

        analyze_root = bucket("analyze", topic_identifier, date_range)
        mark_task_completed(
            task_id,
            message=f"基础分析完成，输出目录: {analyze_root.name}",
            result={
                "analyze_root": str(analyze_root),
                "success_count": 1,
            },
        )
        LOGGER.info(
            "analyze indicator worker | task completed | task=%s topic=%s",
            task_id,
            topic_identifier,
        )

    except TaskCancelled as exc:
        mark_task_cancelled(task_id, str(exc))
        LOGGER.warning(
            "analyze indicator worker | task cancelled | task=%s reason=%s",
            task_id,
            str(exc),
        )
    except Exception as exc:
        LOGGER.exception(
            "analyze indicator worker | task failed | task=%s topic=%s",
            task_id,
            topic_identifier,
        )
        mark_task_failed(task_id, str(exc))
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=1.0)


def main() -> None:
    """Worker 主循环。"""
    started_at = _utc_now()
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

    LOGGER.info("analyze indicator worker started | pid=%s", os.getpid())

    try:
        while True:
            task = reserve_next_task()
            if not task:
                worker_status = load_worker_status()
                if time.monotonic() - last_active_at >= _IDLE_TIMEOUT_SECONDS:
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
                    LOGGER.info(
                        "analyze indicator worker stopped after idle timeout | pid=%s",
                        os.getpid(),
                    )
                    return

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
                time.sleep(2.0)
                continue

            last_active_at = time.monotonic()
            task_id = str(task.get("id") or "")
            LOGGER.info(
                "analyze indicator worker | task reserved | task=%s topic=%s",
                task_id,
                str(task.get("topic_identifier") or ""),
            )

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
            except Exception as exc:
                LOGGER.exception(
                    "analyze indicator worker | unhandled exception | task=%s",
                    task_id,
                )
                try:
                    mark_task_failed(task_id, str(exc))
                except Exception:
                    pass

    except KeyboardInterrupt:
        LOGGER.info("analyze indicator worker interrupted by user")
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
        LOGGER.info("analyze indicator worker stopped | pid=%s", os.getpid())


if __name__ == "__main__":
    main()