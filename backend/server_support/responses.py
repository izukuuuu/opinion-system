"""Response helpers for the backend server endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from flask import jsonify


def serialise_result(value: Any) -> Any:
    """Make sure the result can be JSON serialised."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [serialise_result(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialise_result(val) for key, val in value.items()}

    try:
        import pandas as pd  # type: ignore

        if isinstance(value, pd.DataFrame):
            return value.to_dict(orient="records")
        if isinstance(value, pd.Series):
            return value.to_dict()
    except Exception:  # pragma: no cover - optional dependency
        pass

    try:
        return json.loads(json.dumps(value, default=str))
    except TypeError:
        return str(value)


def evaluate_success(result: Any) -> bool:
    """Infer whether the underlying operation succeeded."""

    if isinstance(result, bool):
        return result
    if result is None:
        return False
    if isinstance(result, dict):
        status = result.get("status")
        if status is not None:
            return status != "error"
        return True
    return True


def require_fields(payload: Dict[str, Any], *fields: str) -> Tuple[bool, Dict[str, Any]]:
    """Validate presence of required request payload fields."""

    missing = [field for field in fields if not payload.get(field)]
    if missing:
        return False, {
            "status": "error",
            "message": f"Missing required field(s): {', '.join(missing)}",
        }
    return True, {}


def success(payload: Dict[str, Any], status_code: int = 200):
    """Return a success JSON response."""

    response = {"status": "ok"}
    response.update(payload)
    return jsonify(response), status_code


def error(message: str, status_code: int = 400):
    """Return an error JSON response."""

    return jsonify({"status": "error", "message": message}), status_code


__all__ = [
    "error",
    "evaluate_success",
    "require_fields",
    "serialise_result",
    "success",
]
