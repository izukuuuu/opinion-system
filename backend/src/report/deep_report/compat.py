from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def extract_legacy_interrupts(payload: Any) -> List[Any]:
    legacy_interrupts = payload.get("__interrupt__") if isinstance(payload, dict) else None
    if isinstance(legacy_interrupts, (list, tuple)):
        return list(legacy_interrupts)
    return []


def parse_structured_report_tool_input(
    payload: Any,
    payload_json: Any = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if isinstance(payload, dict):
        return payload, {"compat_mode": False, "source": "payload"}
    parsed_payload = _parse_json_object(payload)
    if parsed_payload:
        return parsed_payload, {"compat_mode": True, "source": "payload_string"}
    parsed_legacy = _parse_json_object(payload_json)
    if parsed_legacy:
        return parsed_legacy, {"compat_mode": True, "source": "payload_json"}
    return {}, {"compat_mode": False, "source": "invalid"}


def _parse_json_object(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    text = str(raw_value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(text[start : end + 1])
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}


__all__ = [
    "extract_legacy_interrupts",
    "parse_structured_report_tool_input",
]
