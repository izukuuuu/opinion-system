from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BACKEND_DIR / "src"
for path in (BACKEND_DIR, SRC_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from server_support.media_tagging import (  # type: ignore
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

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

_IDLE_TIMEOUT_SECONDS = 90
_HEARTBEAT_INTERVAL_SECONDS = 10


class TaskCancelled(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raise_if_cancelled(task_id: str) -> None:
    if should_cancel(task_id):
        raise TaskCancelled("任务已按请求取消")


def _run_task(task_id: str) -> None:
    task = get_task(task_id)
    topic_identifier = str(task.get("topic_identifier") or "").strip()
    start_date = str(task.get("start_date") or "").strip()
    end_date = str(task.get("end_date") or "").strip() or None

    def _progress_callback(payload: dict) -> None:
        _raise_if_cancelled(task_id)
        mark_task_progress(
            task_id,
            status="running",
            phase=str(payload.get("phase") or "collect").strip() or "collect",
            percentage=int(payload.get("percentage") or 0),
            message=str(payload.get("message") or "").strip() or "正在整理媒体候选。",
            progress={
                "total_files": int(payload.get("total_files") or 0),
                "processed_files": int(payload.get("processed_files") or 0),
                "current_file": str(payload.get("current_file") or "").strip(),
                "candidate_count": int(payload.get("candidate_count") or 0),
            },
        )
        write_worker_status(
            {
                "pid": os.getpid(),
                "status": "running",
                "running": True,
                "current_task_id": task_id,
                "active_count": 1,
                "last_heartbeat": _utc_now(),
                "started_at": task.get("started_at") or "",
            }
        )

    from src.media_tagging import run_media_tagging  # type: ignore

    _raise_if_cancelled(task_id)
    result = run_media_tagging(
        topic_identifier,
        start_date,
        end_date=end_date,
        progress_callback=_progress_callback,
    )
    _raise_if_cancelled(task_id)
    mark_task_completed(
        task_id,
        message=f"媒体识别完成，共整理 {len(result.get('candidates') or [])} 个候选媒体。",
        result={
            "summary_path": str(result.get("summary_path") or ""),
            "candidates_path": str(result.get("candidates_path") or ""),
            "total_candidates": len(result.get("candidates") or []),
        },
    )


def main() -> None:
    write_worker_status(
        {
            "pid": os.getpid(),
            "status": "idle",
            "running": True,
            "current_task_id": "",
            "active_count": 0,
            "last_heartbeat": _utc_now(),
            "started_at": _utc_now(),
        }
    )

    last_active_at = time.monotonic()
    while True:
        try:
            task = reserve_next_task()
            if not task:
                write_worker_status(
                    {
                        "pid": os.getpid(),
                        "status": "idle",
                        "running": True,
                        "current_task_id": "",
                        "active_count": 0,
                        "last_heartbeat": _utc_now(),
                        "started_at": _utc_now(),
                    }
                )
                if time.monotonic() - last_active_at >= _IDLE_TIMEOUT_SECONDS:
                    break
                time.sleep(1.0)
                continue

            task_id = str(task.get("id") or "")
            last_active_at = time.monotonic()
            write_worker_status(
                {
                    "pid": os.getpid(),
                    "status": "running",
                    "running": True,
                    "current_task_id": task_id,
                    "active_count": 1,
                    "last_heartbeat": _utc_now(),
                    "started_at": task.get("started_at") or "",
                }
            )
            _run_task(task_id)
        except TaskCancelled as exc:
            if "task" in locals() and isinstance(task, dict) and task.get("id"):
                mark_task_cancelled(str(task.get("id")), str(exc))
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("media tagging worker failed")
            task_id = ""
            try:
                if "task" in locals() and isinstance(task, dict):
                    task_id = str(task.get("id") or "")
            except Exception:
                task_id = ""
            if task_id:
                try:
                    mark_task_failed(task_id, str(exc))
                except Exception:
                    LOGGER.exception("failed to mark media tagging task as failed")
            time.sleep(1.0)

    write_worker_status(
        {
            "pid": os.getpid(),
            "status": "stopped",
            "running": False,
            "current_task_id": "",
            "active_count": 0,
            "last_heartbeat": _utc_now(),
            "started_at": "",
        }
    )


if __name__ == "__main__":
    main()
