"""Background worker subprocess for fluid analysis queue execution."""
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

from server_support.fluid_analysis import (  # type: ignore
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
    window_hours = int(task.get("window_hours") or 3)
    target_file = str(task.get("target_file") or "").strip() or None

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
            message="正在检查数据目录和加载源文件。",
            progress={"current_phase": "prepare"},
        )

        from src.fluid.fluid_analysis import run_fluid_analysis_with_progress  # type: ignore
        from src.utils.setting.paths import bucket  # type: ignore

        date_range = f"{start_date}_{end_date}" if end_date else start_date
        data_root = bucket("fetch", topic_identifier, date_range)
        out_dir = bucket("fluid", topic_identifier, date_range)

        if not data_root.exists():
            raise FileNotFoundError(f"数据目录不存在: {data_root}")

        def _progress_callback(payload: Dict[str, Any]) -> None:
            _raise_if_cancelled(task_id)
            phase = str(payload.get("phase") or "analyze").strip()
            percentage = int(payload.get("percentage") or 0)
            message = str(payload.get("message") or "").strip()
            progress_update = {
                "total_files": int(payload.get("total_files") or 0),
                "processed_files": int(payload.get("processed_files") or 0),
                "total_windows": int(payload.get("total_windows") or 0),
                "processed_windows": int(payload.get("processed_windows") or 0),
                "current_file": str(payload.get("current_file") or "").strip(),
                "current_phase": phase,
            }
            mark_task_progress(
                task_id,
                status="running",
                phase=phase,
                percentage=percentage,
                message=message,
                progress=progress_update,
            )

        success = run_fluid_analysis_with_progress(
            topic_identifier,
            start_date,
            end_date=end_date,
            window_hours=window_hours,
            target_file=target_file,
            progress_callback=_progress_callback,
        )

        _raise_if_cancelled(task_id)

        if not success:
            raise RuntimeError("流体指标分析未生成有效结果")

        unified_json = out_dir / "fluid_indicators_unified.json"
        file_outputs = []
        for f in data_root.iterdir():
            if f.is_file() and f.suffix.lower() in {".csv", ".xlsx", ".xls"}:
                file_json = out_dir / f"fluid_{f.stem}_indicators.json"
                if file_json.exists():
                    file_outputs.append(str(file_json.name))

        mark_task_completed(
            task_id,
            message=f"流体指标分析完成，输出目录: {out_dir.name}",
            result={
                "unified_json": str(unified_json.name) if unified_json.exists() else "",
                "file_outputs": file_outputs,
                "output_dir": str(out_dir),
            },
        )
        LOGGER.info(
            "fluid indicator worker | task completed | task=%s topic=%s",
            task_id,
            topic_identifier,
        )

    except TaskCancelled as exc:
        mark_task_cancelled(task_id, str(exc))
        LOGGER.warning(
            "fluid indicator worker | task cancelled | task=%s reason=%s",
            task_id,
            str(exc),
        )
    except Exception as exc:
        LOGGER.exception(
            "fluid indicator worker | task failed | task=%s topic=%s",
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

    LOGGER.info("fluid indicator worker started | pid=%s", os.getpid())

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
                        "fluid indicator worker stopped after idle timeout | pid=%s",
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
                "fluid indicator worker | task reserved | task=%s topic=%s",
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
                    "fluid indicator worker | unhandled exception | task=%s",
                    task_id,
                )
                try:
                    mark_task_failed(task_id, str(exc))
                except Exception:
                    pass

    except KeyboardInterrupt:
        LOGGER.info("fluid indicator worker interrupted by user")
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
        LOGGER.info("fluid indicator worker stopped | pid=%s", os.getpid())


if __name__ == "__main__":
    main()