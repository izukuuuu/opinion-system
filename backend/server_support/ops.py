"""Shared execution operations for backend server."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple

from src.project import get_project_manager
from .responses import evaluate_success, serialise_result

LOGGER = logging.getLogger(__name__)


def _log_with_context(
    operation: str,
    success: bool,
    context: Optional[Dict[str, Any]]
) -> None:
    """Log an operation to the project's persistent record."""
    if not context:
        return
    project = context.get("project")
    if not project:
        return
    params = context.get("params") or {}
    try:
        manager = get_project_manager()
        manager.log_operation(project, operation, params=params, success=success)
    except Exception:  # pragma: no cover
        LOGGER.warning(
            "Failed to persist project log for operation %s",
            operation,
            exc_info=True,
        )


def _execute_operation(
    operation: str,
    caller: Callable[..., Any],
    *args: Any,
    log_context: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Tuple[Dict[str, Any], int]:
    """Execute a callable, log the result, and return a standardized response."""
    try:
        result = caller(*args, **kwargs)
        success = evaluate_success(result)
        _log_with_context(operation, success, log_context)
        serialised = serialise_result(result)
        if success:
            return {
                "status": "ok",
                "operation": operation,
                "data": serialised,
            }, 200

        message = "操作执行失败"
        if isinstance(serialised, dict):
            message = serialised.get("message") or serialised.get("error") or message
        elif isinstance(serialised, str):
            message = serialised

        return {
            "status": "error",
            "operation": operation,
            "message": message,
            "data": serialised,
        }, 500
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Error while executing operation %s", operation)
        _log_with_context(operation, False, log_context)
        return {
            "status": "error",
            "operation": operation,
            "message": str(exc),
        }, 500
