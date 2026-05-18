from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..task_queue import STATE_ROOT, get_task, load_events_since, task_events_path


def _safe_dt(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _scorecard_path(task_id: str) -> Path:
    return (STATE_ROOT / "tasks") / f"{task_id}.scorecard.json"


def _summarize_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    types = [str(e.get("type") or "").strip() for e in events if isinstance(e, dict)]
    phases = [str(e.get("phase") or "").strip() for e in events if isinstance(e, dict)]
    agents = [str(e.get("agent") or "").strip() for e in events if isinstance(e, dict)]
    errors = [
        e
        for e in events
        if isinstance(e, dict)
        and str(e.get("type") or "").strip() in {"task.failed", "error"}
        or str(e.get("phase") or "").strip() == "failed"
    ]
    first_ts = next((e.get("ts") for e in events if isinstance(e, dict) and str(e.get("ts") or "").strip()), "")
    last_ts = ""
    for e in reversed(events):
        if isinstance(e, dict) and str(e.get("ts") or "").strip():
            last_ts = str(e.get("ts") or "").strip()
            break
    start_dt = _safe_dt(first_ts)
    end_dt = _safe_dt(last_ts)
    runtime_s = (end_dt - start_dt).total_seconds() if start_dt and end_dt else None
    return {
        "counts": {
            "events": len(events),
            "by_type": dict(Counter([t for t in types if t])),
            "by_phase": dict(Counter([p for p in phases if p])),
            "by_agent": dict(Counter([a for a in agents if a])),
            "errors": len(errors),
        },
        "timing": {
            "first_ts": str(first_ts or ""),
            "last_ts": str(last_ts or ""),
            "runtime_seconds": runtime_s,
        },
    }


def write_scorecard_for_task(task_id: str, *, since_event_id: int = 0) -> Dict[str, Any]:
    """Finalize events into scorecard.json (best-effort called by task_queue)."""
    task = get_task(task_id)
    events = load_events_since(task_id, since_event_id)
    summary = _summarize_events(events)

    scorecard: Dict[str, Any] = {
        "schema": "report.scorecard.v1",
        "task_id": str(task_id),
        "status": str(task.get("status") or "").strip(),
        "phase": str(task.get("phase") or "").strip(),
        "topic_identifier": str(task.get("topic_identifier") or "").strip(),
        "start": str(task.get("start") or "").strip(),
        "end": str(task.get("end") or "").strip(),
        "mode": str(task.get("mode") or "fast").strip() or "fast",
        "compile_quality": str(task.get("compile_quality") or "").strip(),
        "degraded_sections": task.get("degraded_sections") if isinstance(task.get("degraded_sections"), list) else [],
        "events": {
            "path": str(task_events_path(task_id)),
            "since_event_id": int(since_event_id),
        },
        **summary,
    }

    out_path = _scorecard_path(task_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")
    return scorecard


__all__ = ["write_scorecard_for_task"]

