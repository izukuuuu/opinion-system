from __future__ import annotations

import json
from typing import Any, Dict, List


def safe_json_loads(raw: str) -> Dict[str, Any]:
    try:
        value = json.loads(str(raw or ""))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def safe_json_loads_list(raw: str) -> List[Any]:
    try:
        value = json.loads(str(raw or ""))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def to_clean_list(raw: str, *, max_items: int = 12) -> List[str]:
    items = safe_json_loads_list(raw)
    cleaned: List[str] = []
    seen = set()
    for item in items:
        token = str(item or "").strip()
        if len(token) < 2:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(token)
        if len(cleaned) >= max_items:
            break
    return cleaned
