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

from server_support.publisher_detection import (  # type: ignore
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
    database = str(task.get("database") or "").strip()
    tables = task.get("tables") if isinstance(task.get("tables"), list) else []
    limit = int(task.get("limit") or 50)
    sample_limit = int(task.get("sample_limit") or 3)

    def _progress_callback(payload: dict) -> None:
        progress = {
            "total_tables": int(payload.get("total_tables") or 0),
            "completed_tables": int(payload.get("completed_tables") or 0),
            "percentage": int(payload.get("percentage") or 0),
            "current_table": str(payload.get("current_table") or "").strip(),
            "scanned_tables": payload.get("scanned_tables") if isinstance(payload.get("scanned_tables"), list) else [],
            "skipped_tables": payload.get("skipped_tables") if isinstance(payload.get("skipped_tables"), list) else [],
            "missing_tables": payload.get("missing_tables") if isinstance(payload.get("missing_tables"), list) else [],
        }
        percentage = progress["percentage"]
        phase = str(payload.get("phase") or "analyze").strip() or "analyze"
        message = str(payload.get("message") or "").strip() or "正在统计发布者分布。"
        mark_task_progress(
            task_id,
            status="running",
            phase=phase,
            percentage=percentage,
            message=message,
            progress=progress,
        )
        write_worker_status(
            {
                "pid": os.getpid(),
                "status": "running",
                "running": True,
                "current_task_id": task_id,
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "started_at": task.get("started_at") or "",
            }
        )

    from src.filter import list_postclean_publishers  # type: ignore

    result = list_postclean_publishers(
        topic_identifier,
        database,
        tables=tables or None,
        limit=limit,
        sample_limit=sample_limit,
        progress_callback=_progress_callback,
    )
    if str(result.get("status") or "") != "ok":
        raise RuntimeError(str(result.get("message") or "异常发布者识别失败"))

    total_tables = len(result.get("scanned_tables") or []) + len(result.get("skipped_tables") or []) + len(result.get("missing_tables") or [])
    completed_progress = {
        "total_tables": total_tables,
        "completed_tables": total_tables,
        "percentage": 100,
        "current_table": "",
        "scanned_tables": result.get("scanned_tables") if isinstance(result.get("scanned_tables"), list) else [],
        "skipped_tables": result.get("skipped_tables") if isinstance(result.get("skipped_tables"), list) else [],
        "missing_tables": result.get("missing_tables") if isinstance(result.get("missing_tables"), list) else [],
    }
    mark_task_progress(
        task_id,
        status="completed",
        phase="completed",
        percentage=100,
        message=f"发布者识别完成，共返回 {len(result.get('publishers') or [])} 个候选发布者。",
        progress=completed_progress,
        result=result,
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
            LOGGER.exception("Publisher detection worker failed")
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
                    LOGGER.exception("Failed to mark publisher detection task as failed")
            _utc_sleep(1.0)


if __name__ == "__main__":
    main()
