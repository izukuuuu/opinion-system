"""Background worker subprocess for basic analysis queue execution with parallel task support."""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Set

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
_MAX_CONCURRENT_TASKS = 4  # 最大并行任务数


class TaskCancelled(RuntimeError):
    """任务已取消异常。"""
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raise_if_cancelled(task_id: str) -> None:
    if should_cancel(task_id):
        raise TaskCancelled("任务已按请求取消")


class ParallelWorker:
    """支持并行执行多个任务的 Worker。"""

    def __init__(self, max_concurrent: int = _MAX_CONCURRENT_TASKS):
        self.max_concurrent = max_concurrent
        self.running_task_ids: Set[str] = set()
        self.running_tasks_lock = threading.Lock()
        self.active_task_id = ""  # 用于心跳显示的当前任务
        self.started_at = _utc_now()
        self.stop_event = threading.Event()
        self.heartbeat_thread: threading.Thread = None

    def _heartbeat_loop(self) -> None:
        """心跳线程。"""
        while not self.stop_event.wait(_HEARTBEAT_INTERVAL_SECONDS):
            try:
                with self.running_tasks_lock:
                    task_count = len(self.running_task_ids)
                    current_task = next(iter(self.running_task_ids), "") if self.running_task_ids else ""

                write_worker_status(
                    {
                        "pid": os.getpid(),
                        "status": "running" if task_count > 0 else "idle",
                        "running": True,
                        "current_task_id": current_task,
                        "active_count": task_count,
                        "last_heartbeat": _utc_now(),
                        "started_at": self.started_at,
                    }
                )
            except Exception:
                continue

    def _run_single_task(self, task_id: str) -> None:
        """执行单个任务。"""
        try:
            with self.running_tasks_lock:
                self.running_task_ids.add(task_id)

            task = get_task(task_id)
            topic_identifier = str(task.get("topic_identifier") or "").strip()
            start_date = str(task.get("start_date") or "").strip()
            end_date = str(task.get("end_date") or "").strip() or None
            only_function = str(task.get("only_function") or "").strip() or None

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
                "analyze indicator worker | task failed | task=%s",
                task_id,
            )
            mark_task_failed(task_id, str(exc))
        finally:
            with self.running_tasks_lock:
                self.running_task_ids.discard(task_id)

    def run(self) -> None:
        """Worker 主循环。"""
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

        LOGGER.info(
            "analyze indicator worker started | pid=%s max_concurrent=%d",
            os.getpid(),
            self.max_concurrent,
        )

        # 启动心跳线程
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
        )
        self.heartbeat_thread.start()

        last_active_at = time.monotonic()

        try:
            with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
                futures: Dict[Future, str] = {}

                while True:
                    # 清理已完成的任务
                    completed_futures = [f for f in futures if f.done()]
                    for future in completed_futures:
                        task_id = futures.pop(future, "")
                        if future.exception() and task_id:
                            LOGGER.warning(
                                "analyze indicator worker | task exception | task=%s exc=%s",
                                task_id,
                                future.exception(),
                            )

                    # 检查是否可以接受新任务
                    running_count = len(futures)
                    if running_count < self.max_concurrent:
                        task = reserve_next_task()
                        if task:
                            task_id = str(task.get("id") or "")
                            if task_id:
                                last_active_at = time.monotonic()
                                LOGGER.info(
                                    "analyze indicator worker | task reserved | task=%s topic=%s",
                                    task_id,
                                    str(task.get("topic_identifier") or ""),
                                )
                                future = executor.submit(self._run_single_task, task_id)
                                futures[future] = task_id
                                continue

                    # 没有新任务，检查空闲超时
                    with self.running_tasks_lock:
                        task_count = len(self.running_task_ids)

                    if task_count == 0:
                        if time.monotonic() - last_active_at >= _IDLE_TIMEOUT_SECONDS:
                            LOGGER.info(
                                "analyze indicator worker stopping after idle timeout | pid=%s",
                                os.getpid(),
                            )
                            break

                    time.sleep(1.0)

        except KeyboardInterrupt:
            LOGGER.info("analyze indicator worker interrupted by user")
        finally:
            self.stop_event.set()
            write_worker_status(
                {
                    "pid": os.getpid(),
                    "status": "stopped",
                    "running": False,
                    "current_task_id": "",
                    "active_count": 0,
                    "last_heartbeat": _utc_now(),
                    "started_at": self.started_at,
                }
            )
            LOGGER.info("analyze indicator worker stopped | pid=%s", os.getpid())


def main() -> None:
    """Worker 入口。"""
    worker = ParallelWorker(max_concurrent=_MAX_CONCURRENT_TASKS)
    worker.run()


if __name__ == "__main__":
    main()