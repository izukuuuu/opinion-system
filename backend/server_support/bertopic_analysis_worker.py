"""Background worker subprocess for BERTopic queue execution."""
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

from server_support.bertopic_analysis import (  # type: ignore
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
from src.topic.api import run_topic_bertopic_job  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)

_IDLE_TIMEOUT_SECONDS = 90
_HEARTBEAT_INTERVAL_SECONDS = 12


class TaskCancelled(RuntimeError):
    """Task cancelled."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raise_if_cancelled(task_id: str) -> None:
    if should_cancel(task_id):
        raise TaskCancelled("任务已按请求取消")


class BertopicWorker:
    def __init__(self) -> None:
        self.current_task_id = ""
        self.started_at = _utc_now()
        self.stop_event = threading.Event()
        self.heartbeat_thread: threading.Thread | None = None

    def _heartbeat_loop(self) -> None:
        while not self.stop_event.wait(_HEARTBEAT_INTERVAL_SECONDS):
            try:
                write_worker_status(
                    {
                        "pid": os.getpid(),
                        "status": "running" if self.current_task_id else "idle",
                        "running": True,
                        "current_task_id": self.current_task_id,
                        "active_count": 1 if self.current_task_id else 0,
                        "last_heartbeat": _utc_now(),
                        "started_at": self.started_at,
                    }
                )
            except Exception:
                continue

    def _run_single_task(self, task_id: str) -> None:
        self.current_task_id = task_id
        try:
            task = get_task(task_id)
            payload = task.get("request_payload") if isinstance(task.get("request_payload"), dict) else {}
            if not isinstance(payload, dict):
                raise RuntimeError("BERTopic 任务缺少有效请求参数")

            _raise_if_cancelled(task_id)
            mark_task_progress(
                task_id,
                status="running",
                phase="prepare",
                percentage=5,
                message="正在检查 BERTopic 任务参数。",
                progress={"current_step": "prepare"},
            )

            def _progress_callback(progress: Dict[str, Any]) -> None:
                _raise_if_cancelled(task_id)
                if not isinstance(progress, dict):
                    return
                mark_task_progress(
                    task_id,
                    status=str(progress.get("status") or "running").strip() or "running",
                    phase=str(progress.get("phase") or "analyze").strip() or "analyze",
                    percentage=int(progress.get("percentage") or 0),
                    message=str(progress.get("message") or "").strip() or "BERTopic 分析进行中。",
                    progress={
                        "current_step": str(progress.get("current_step") or "").strip(),
                        "text_count": int(progress.get("text_count") or 0),
                        "topic_count": int(progress.get("topic_count") or 0),
                    },
                )

            response = run_topic_bertopic_job(payload, progress_callback=_progress_callback)
            _raise_if_cancelled(task_id)

            if str(response.get("status") or "") != "ok":
                raise RuntimeError(str(response.get("message") or "BERTopic 分析失败"))

            data = response.get("data") if isinstance(response.get("data"), dict) else {}
            mark_task_completed(
                task_id,
                message=str(data.get("message") or "BERTopic 分析完成"),
                result={
                    "folder": str(data.get("folder") or ""),
                    "output_dir": str(data.get("output_dir") or ""),
                },
            )
            LOGGER.info("bertopic worker | task completed | task=%s", task_id)
        except TaskCancelled as exc:
            mark_task_cancelled(task_id, str(exc))
            LOGGER.warning("bertopic worker | task cancelled | task=%s reason=%s", task_id, str(exc))
        except Exception as exc:
            LOGGER.exception("bertopic worker | task failed | task=%s", task_id)
            mark_task_failed(task_id, str(exc))
        finally:
            self.current_task_id = ""

    def run(self) -> None:
        write_worker_status(
            {
                "pid": os.getpid(),
                "status": "idle",
                "running": True,
                "current_task_id": "",
                "active_count": 0,
                "last_heartbeat": _utc_now(),
                "started_at": self.started_at,
            }
        )

        LOGGER.info("bertopic worker started | pid=%s", os.getpid())
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

        last_active_at = time.monotonic()
        try:
            while True:
                task = reserve_next_task()
                if task:
                    task_id = str(task.get("id") or "")
                    if task_id:
                        last_active_at = time.monotonic()
                        LOGGER.info("bertopic worker | task reserved | task=%s", task_id)
                        self._run_single_task(task_id)
                        continue

                worker_status = load_worker_status()
                if not worker_status.get("running"):
                    break

                if time.monotonic() - last_active_at >= _IDLE_TIMEOUT_SECONDS:
                    LOGGER.info("bertopic worker stopping after idle timeout | pid=%s", os.getpid())
                    break
                write_worker_status(
                    {
                        "pid": os.getpid(),
                        "status": "idle",
                        "running": True,
                        "current_task_id": "",
                        "active_count": 0,
                        "last_heartbeat": _utc_now(),
                        "started_at": self.started_at,
                    }
                )
                time.sleep(1.5)
        except KeyboardInterrupt:
            LOGGER.info("bertopic worker interrupted by user")
        finally:
            self.stop_event.set()
            write_worker_status(
                {
                    "pid": 0,
                    "status": "stopped",
                    "running": False,
                    "current_task_id": "",
                    "active_count": 0,
                    "last_heartbeat": _utc_now(),
                    "started_at": self.started_at,
                }
            )
            LOGGER.info("bertopic worker stopped | pid=%s", os.getpid())


def main() -> None:
    worker = BertopicWorker()
    worker.run()


if __name__ == "__main__":
    main()
