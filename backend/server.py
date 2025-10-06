"""Simple Flask server exposing OpinionSystem operations as REST endpoints."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

import yaml
from flask import Flask, jsonify, request
from flask_cors import CORS


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "backend" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def _load_config() -> Dict[str, Any]:
    if CONFIG_PATH.is_file():
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    LOGGER.warning("Configuration file %s not found, using defaults", CONFIG_PATH)
    return {}


def _serialise_result(value: Any) -> Any:
    """Make sure the result can be JSON serialised."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_serialise_result(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialise_result(val) for key, val in value.items()}

    # Handle common dataframe-like objects lazily to avoid hard dependency.
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


def _execute_operation(operation: str, caller: Callable[..., Any], *args: Any, **kwargs: Any) -> Tuple[Dict[str, Any], int]:
    try:
        result = caller(*args, **kwargs)
        return {
            "status": "ok",
            "operation": operation,
            "data": _serialise_result(result),
        }, 200
    except Exception as exc:  # pragma: no cover - defensive: surface backend errors
        LOGGER.exception("Error while executing operation %s", operation)
        return {
            "status": "error",
            "operation": operation,
            "message": str(exc),
        }, 500


def _require_fields(payload: Dict[str, Any], *fields: str) -> Tuple[bool, Dict[str, Any]]:
    missing = [field for field in fields if not payload.get(field)]
    if missing:
        return False, {
            "status": "error",
            "message": f"Missing required field(s): {', '.join(missing)}",
        }
    return True, {}


app = Flask(__name__)
CORS(app)

CONFIG = _load_config()


@app.get("/api/status")
def status():
    return jsonify({
        "status": "ok",
        "message": "OpinionSystem backend is running",
        "config": {
            "backend": CONFIG.get("backend", {}),
        },
    })


@app.get("/api/config")
def get_config():
    return jsonify(CONFIG)


@app.post("/api/merge")
def merge_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = _require_fields(payload, "topic", "date")
    if not valid:
        return jsonify(error), 400

    from src.merge import run_merge  # type: ignore

    response, code = _execute_operation("merge", run_merge, payload["topic"], payload["date"])
    return jsonify(response), code


@app.post("/api/clean")
def clean_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = _require_fields(payload, "topic", "date")
    if not valid:
        return jsonify(error), 400

    from src.clean import run_clean  # type: ignore

    response, code = _execute_operation("clean", run_clean, payload["topic"], payload["date"])
    return jsonify(response), code


@app.post("/api/filter")
def filter_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = _require_fields(payload, "topic", "date")
    if not valid:
        return jsonify(error), 400

    from src.filter import run_filter  # type: ignore

    response, code = _execute_operation("filter", run_filter, payload["topic"], payload["date"])
    return jsonify(response), code


@app.post("/api/upload")
def upload_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = _require_fields(payload, "topic", "date")
    if not valid:
        return jsonify(error), 400

    from src.update import run_update  # type: ignore

    response, code = _execute_operation("upload", run_update, payload["topic"], payload["date"])
    return jsonify(response), code


@app.post("/api/query")
def query_endpoint():
    from src.query import run_query  # type: ignore

    response, code = _execute_operation("query", run_query)
    return jsonify(response), code


@app.post("/api/fetch")
def fetch_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = _require_fields(payload, "topic", "start", "end")
    if not valid:
        return jsonify(error), 400

    from src.fetch import run_fetch  # type: ignore

    response, code = _execute_operation(
        "fetch", run_fetch, payload["topic"], payload["start"], payload["end"]
    )
    return jsonify(response), code


@app.post("/api/analyze")
def analyze_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = _require_fields(payload, "topic", "start", "end")
    if not valid:
        return jsonify(error), 400

    func = payload.get("function")

    from src.analyze import run_Analyze  # type: ignore

    response, code = _execute_operation(
        "analyze",
        run_Analyze,
        payload["topic"],
        payload["start"],
        end_date=payload["end"],
        only_function=func,
    )
    return jsonify(response), code


@app.route("/")
def root():
    return jsonify({"message": "OpinionSystem API", "endpoints": [
        "/api/status",
        "/api/config",
        "/api/merge",
        "/api/clean",
        "/api/filter",
        "/api/upload",
        "/api/query",
        "/api/fetch",
        "/api/analyze",
    ]})


def main() -> None:
    backend_cfg = CONFIG.get("backend", {})
    host = backend_cfg.get("host", "127.0.0.1")
    port = int(backend_cfg.get("port", 8000))
    LOGGER.info("Starting OpinionSystem backend on %s:%s", host, port)
    try:
        app.run(host=host, port=port)
    except OSError as exc:  # pragma: no cover - defensive handling for production issues
        # Windows reports WinError 10013 when a port is blocked by permissions/firewall rules.
        # On Unix the equivalent errno is typically 13 (EACCES) or 98 (EADDRINUSE).
        winerror = getattr(exc, "winerror", None)
        if winerror == 10013 or exc.errno in {13, 98, 10013}:  # type: ignore[arg-type]
            LOGGER.error(
                "Unable to bind OpinionSystem backend to %s:%s. "
                "The port is either already in use or blocked by your operating system. "
                "Please choose a different port in config.yaml or free the existing one.",
                host,
                port,
            )
            raise SystemExit(1) from exc
        raise


if __name__ == "__main__":
    main()
