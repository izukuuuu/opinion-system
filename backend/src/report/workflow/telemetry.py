from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    try:
        if hasattr(value, "model_dump"):
            return value.model_dump()
    except Exception:
        pass
    if isinstance(value, Path):
        return str(value)
    return str(value)


def append_ndjson_log(path: Path, event: Dict[str, Any], *, envelope: Optional[Dict[str, Any]] = None) -> None:
    """Best-effort append-only NDJSON telemetry log.

    - Never raises (pure observability; does not affect runtime decisions)
    - Writes one JSON object per line
    """
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "ts": _utc_now(),
            **(envelope or {}),
            "event": event if isinstance(event, dict) else {"raw": str(event)},
        }
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=_json_default))
            stream.write("\n")
    except Exception:
        return


def telemetry_enabled() -> bool:
    return str(os.getenv("OPINION_TELEMETRY", "")).strip() in {"1", "true", "TRUE", "yes", "YES"}


def resolve_telemetry_path(*, default_dir: Path, filename: str = "telemetry.ndjson") -> Optional[Path]:
    override = str(os.getenv("OPINION_TELEMETRY_NDJSON", "")).strip()
    if override:
        return Path(override)
    if telemetry_enabled():
        return Path(default_dir) / filename
    return None

