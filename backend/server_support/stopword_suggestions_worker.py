from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BACKEND_DIR / "src"
for path in (BACKEND_DIR, SRC_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from server_support.stopword_suggestions import (  # type: ignore
    analyse_archive_terms,
    get_task,
    mark_task_progress,
    reserve_next_task,
    write_worker_status,
)

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def _utc_sleep(seconds: float) -> None:
    time.sleep(seconds)


def _run_task(task_id: str) -> None:
    task = get_task(task_id)
    topic_identifier = str(task.get("topic_identifier") or "").strip()
    date = str(task.get("date") or "").strip()
    stage = str(task.get("stage") or "pre").strip().lower() or "pre"
    top_k = int(task.get("top_k") or 120)

    def _progress_callback(phase: str, percentage: int, message: str, summary: dict) -> None:
        mark_task_progress(
            task_id,
            status="running",
            phase=phase,
            percentage=percentage,
            message=message,
            summary=summary,
        )

    result = analyse_archive_terms(
        topic_identifier,
        date,
        top_k=top_k,
        stage=stage,
        progress_callback=_progress_callback,
    )

    summary = dict(result.get("summary") or {})
    source_layer = str(summary.get("source_layer") or "")
    mark_task_progress(
        task_id,
        status="completed",
        phase="completed",
        percentage=100,
        message=f"高频词统计完成，数据源：{source_layer or '未知'}。",
        summary=summary,
        result=dict(result.get("result") or {}),
    )


def main() -> None:
    write_worker_status(
        {
            "pid": os.getpid(),
            "status": "idle",
            "running": True,
            "current_task_id": "",
            "last_heartbeat": "",
            "started_at": "",
        }
    )

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
                        "last_heartbeat": "",
                        "started_at": "",
                    }
                )
                _utc_sleep(1.0)
                continue

            task_id = str(task.get("id") or "")
            write_worker_status(
                {
                    "pid": os.getpid(),
                    "status": "running",
                    "running": True,
                    "current_task_id": task_id,
                    "last_heartbeat": "",
                    "started_at": task.get("started_at") or "",
                }
            )

            _run_task(task_id)
        except Exception as exc:  # pragma: no cover - runtime guard
            LOGGER.exception("Stopword suggestion worker failed")
            task_id = ""
            try:
                if "task" in locals() and isinstance(task, dict):
                    task_id = str(task.get("id") or "")
            except Exception:
                task_id = ""
            if task_id:
                try:
                    mark_task_progress(
                        task_id,
                        status="failed",
                        phase="failed",
                        percentage=100,
                        message=str(exc),
                        error=str(exc),
                    )
                except Exception:
                    LOGGER.exception("Failed to mark stopword suggestion task as failed")
            _utc_sleep(1.0)


if __name__ == "__main__":
    main()
