"""
过滤任务运行状态模块

本模块用于在内存中跟踪舆情分析系统的过滤（filter）任务运行状态，便于进度上报与并发控制，主要功能包括：

1. 记录正在运行的过滤任务（按专题和日期唯一标识）。
2. 支持任务开始、结束的状态变更，线程安全。
3. 提供查询接口，判断某个过滤任务是否正在运行。
4. 适用于后端接口、任务调度与前端进度轮询等场景。

主要导出函数：
- mark_filter_job_running：标记过滤任务为运行中
- mark_filter_job_finished：标记过滤任务已结束
- is_filter_job_running：判断过滤任务是否运行中

适用场景：
- 过滤任务进度上报
- 并发任务控制
- 后端接口与前端轮询
"""

from __future__ import annotations

import threading
from typing import Set, Tuple

_lock = threading.Lock()
_running_jobs: Set[Tuple[str, str]] = set()


def _normalise(topic: str, date: str) -> Tuple[str, str]:
    return (topic.strip(), date.strip())


def mark_filter_job_running(topic: str, date: str) -> None:
    """Record a filter task as running."""

    key = _normalise(topic, date)
    with _lock:
        _running_jobs.add(key)


def mark_filter_job_finished(topic: str, date: str) -> None:
    """Remove a filter task from the running set."""

    key = _normalise(topic, date)
    with _lock:
        _running_jobs.discard(key)


def is_filter_job_running(topic: str, date: str) -> bool:
    """Return True if a filter task is currently running."""

    key = _normalise(topic, date)
    with _lock:
        return key in _running_jobs


__all__ = [
    "is_filter_job_running",
    "mark_filter_job_finished",
    "mark_filter_job_running",
]
