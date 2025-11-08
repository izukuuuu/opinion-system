"""In-memory registry that tracks running filter tasks for progress reporting."""

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
