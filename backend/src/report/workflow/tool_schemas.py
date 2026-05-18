from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class SchemaError(Exception):
    message: str
    path: str = ""

    def __str__(self) -> str:
        suffix = f" @ {self.path}" if self.path else ""
        return f"{self.message}{suffix}"


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _require_dict(value: Any, *, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError("expected object", path=path)
    return value


def _require_list(value: Any, *, path: str) -> List[Any]:
    if not isinstance(value, list):
        raise SchemaError("expected array", path=path)
    return value


def _require_str(value: Any, *, path: str, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise SchemaError("expected string", path=path)
    if not allow_empty and not value.strip():
        raise SchemaError("expected non-empty string", path=path)
    return value


def _optional_str(value: Any) -> str:
    return str(value or "").strip()


def validate_fetch_availability_output(payload: Dict[str, Any]) -> None:
    """Contract guard for fetch availability output.

    Target: backend/src/fetch/data_fetch.py::get_topic_available_date_range
    """
    root = _require_dict(payload, path="$")
    # start/end can be None or str
    if "start" not in root or "end" not in root:
        raise SchemaError("missing start/end", path="$")
    start = root.get("start")
    end = root.get("end")
    if start is not None and not isinstance(start, str):
        raise SchemaError("start must be string|null", path="$.start")
    if end is not None and not isinstance(end, str):
        raise SchemaError("end must be string|null", path="$.end")

    channels = root.get("channels", {})
    channels = _require_dict(channels, path="$.channels")
    for key, value in channels.items():
        _require_str(str(key), path="$.channels.<key>", allow_empty=False)
        entry = _require_dict(value, path=f"$.channels.{key}")
        if "start" not in entry or "end" not in entry:
            raise SchemaError("channel range missing start/end", path=f"$.channels.{key}")
        if entry.get("start") is not None and not isinstance(entry.get("start"), str):
            raise SchemaError("channel.start must be string|null", path=f"$.channels.{key}.start")
        if entry.get("end") is not None and not isinstance(entry.get("end"), str):
            raise SchemaError("channel.end must be string|null", path=f"$.channels.{key}.end")


def validate_basic_analysis_snapshot(snapshot: Dict[str, Any]) -> None:
    """Contract guard for basic analysis snapshot shape.

    Target: backend/src/report/capability_adapters.py::collect_basic_analysis_snapshot
    """
    root = _require_dict(snapshot, path="$")
    _require_str(root.get("snapshot_id"), path="$.snapshot_id", allow_empty=False)
    _require_str(root.get("topic_identifier"), path="$.topic_identifier", allow_empty=False)
    _require_str(root.get("topic_label"), path="$.topic_label", allow_empty=True)

    time_range = _require_dict(root.get("time_range"), path="$.time_range")
    _require_str(time_range.get("start"), path="$.time_range.start", allow_empty=False)
    _require_str(time_range.get("end"), path="$.time_range.end", allow_empty=False)

    if not isinstance(root.get("available"), bool):
        raise SchemaError("available must be boolean", path="$.available")
    if not isinstance(root.get("available_functions"), list):
        raise SchemaError("available_functions must be array", path="$.available_functions")
    if not isinstance(root.get("missing_functions"), list):
        raise SchemaError("missing_functions must be array", path="$.missing_functions")

    overview = _require_dict(root.get("overview"), path="$.overview")
    # Keep loose: only require keys exist to prevent silent removals
    required_overview_keys = [
        "total_volume",
        "peak",
        "sentiment",
        "top_topics",
        "top_keywords",
        "top_publishers",
        "top_geography",
    ]
    for key in required_overview_keys:
        if key not in overview:
            raise SchemaError("missing overview key", path=f"$.overview.{key}")

    _require_list(root.get("functions"), path="$.functions")
    trace = root.get("trace")
    if trace is not None and not isinstance(trace, dict):
        raise SchemaError("trace must be object", path="$.trace")


__all__ = [
    "SchemaError",
    "validate_basic_analysis_snapshot",
    "validate_fetch_availability_output",
]

