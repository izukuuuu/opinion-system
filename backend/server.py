from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
from flask import Flask, jsonify, request
from flask_cors import CORS


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
SRC_DIR = BACKEND_DIR / "src"

for path in (BACKEND_DIR, SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.project import (  # type: ignore
    find_dataset_by_id,
    get_dataset_metadata,
    get_dataset_date_summary,
    get_dataset_preview,
    get_project_manager,
    list_project_datasets,
    normalise_project_name,
    update_dataset_column_mapping,
    store_uploaded_dataset,
)
from src.utils.setting.editor import load_config as load_settings_config, save_config as save_settings_config  # type: ignore
from src.utils.setting.paths import bucket  # type: ignore
from src.utils.setting.settings import settings  # type: ignore

CONFIG_PATH = PROJECT_ROOT / "config.yaml"
PROJECT_MANAGER = get_project_manager()

ANALYZE_FILE_MAP = {
    "volume": "volume.json",
    "attitude": "attitude.json",
    "trends": "trends.json",
    "geography": "geography.json",
    "publishers": "publishers.json",
    "keywords": "keywords.json",
    "classification": "classification.json",
}
DEFAULT_ANALYZE_FILENAME = "result.json"
DATA_PROJECTS_ROOT = BACKEND_DIR / "data" / "projects"


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


def _evaluate_success(result: Any) -> bool:
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


def _log_with_context(operation: str, success: bool, context: Optional[Dict[str, Any]]) -> None:
    if not context:
        return
    project = context.get("project")
    if not project:
        return
    params = context.get("params") or {}
    try:
        PROJECT_MANAGER.log_operation(project, operation, params=params, success=success)
    except Exception:  # pragma: no cover - logging失败不影响接口
        LOGGER.warning("Failed to persist project log for operation %s", operation, exc_info=True)


def _execute_operation(
    operation: str,
    caller: Callable[..., Any],
    *args: Any,
    log_context: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Tuple[Dict[str, Any], int]:
    try:
        result = caller(*args, **kwargs)
        success = _evaluate_success(result)
        _log_with_context(operation, success, log_context)
        serialised = _serialise_result(result)
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
    except Exception as exc:  # pragma: no cover - defensive: surface backend errors
        LOGGER.exception("Error while executing operation %s", operation)
        _log_with_context(operation, False, log_context)
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


def _compose_analyze_folder(start: str, end: Optional[str]) -> str:
    end = end or ""
    start = start.strip()
    end = end.strip()
    if not start:
        return ""
    if end and end != start:
        return f"{start}_{end}"
    return start


def _load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            fh.seek(0)
            return fh.read()


def _parse_column_mapping_payload(raw: Any) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, str):
                mapping[str(key)] = value.strip()
    elif isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            for key, value in decoded.items():
                if isinstance(value, str):
                    mapping[str(key)] = value.strip()

    normalized: Dict[str, str] = {}
    for key in ("date", "title", "content", "author"):
        value = mapping.get(key)
        if isinstance(value, str):
            normalized[key] = value.strip()
    return normalized


def _iter_unique_strings(values: List[Any]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _resolve_dataset_payload(project_name: str, dataset_id: Any) -> Dict[str, Any]:
    dataset_id_str = str(dataset_id or "").strip()
    if not dataset_id_str:
        return {}

    if project_name:
        try:
            return get_dataset_metadata(project_name, dataset_id_str)
        except (LookupError, ValueError):
            pass

    metadata = find_dataset_by_id(dataset_id_str)
    if metadata:
        return metadata
    return {}


def _resolve_topic_identifier(payload: Dict[str, Any]) -> Tuple[str, str, str]:
    project_name = str(payload.get("project") or "").strip()
    topic_label = str(payload.get("topic") or "").strip()
    dataset_meta = _resolve_dataset_payload(project_name, payload.get("dataset_id"))

    candidates: List[str] = []
    if dataset_meta:
        slug = dataset_meta.get("project_slug")
        if isinstance(slug, str):
            candidates.append(slug)
        meta_project = dataset_meta.get("project")
        if isinstance(meta_project, str):
            candidates.append(meta_project)
        meta_topic = dataset_meta.get("topic_label")
        if isinstance(meta_topic, str):
            candidates.append(meta_topic)

    if project_name:
        candidates.append(normalise_project_name(project_name))
        candidates.append(project_name)

    if topic_label:
        candidates.append(topic_label)

    ordered_candidates = _iter_unique_strings(candidates)
    if not ordered_candidates:
        raise ValueError("Missing required field(s): topic or project")

    resolved_topic = next(
        (candidate for candidate in ordered_candidates if (DATA_PROJECTS_ROOT / candidate).exists()),
        None,
    )
    if not resolved_topic:
        resolved_topic = ordered_candidates[0]

    display_name = (
        topic_label
        or (dataset_meta.get("topic_label") if isinstance(dataset_meta.get("topic_label"), str) else None)
        or project_name
        or resolved_topic
    )

    log_project = project_name or dataset_meta.get("project") or resolved_topic

    return resolved_topic, display_name, str(log_project)


def _prepare_pipeline_args(payload: Dict[str, Any]) -> Tuple[str, str, str]:
    topic_identifier, display_name, log_project = _resolve_topic_identifier(payload)
    date = str(payload.get("date") or "").strip()
    if not date:
        raise ValueError("Missing required field(s): date")
    return topic_identifier, date, display_name or topic_identifier, log_project or topic_identifier


def _parse_column_mapping_from_form(form: Dict[str, Any]) -> Dict[str, str]:
    initial = _parse_column_mapping_payload(form.get("column_mapping"))
    for key in ("date", "title", "content", "author"):
        field_name = f"{key}_column"
        value = form.get(field_name)
        if isinstance(value, str) and value.strip():
            initial[key] = value.strip()
    return initial


def _normalise_topic_label(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


app = Flask(__name__)
CORS(app)

CONFIG = _load_config()

DATABASES_CONFIG_NAME = "databases"
LLM_CONFIG_NAME = "llm"


def _success(payload: Dict[str, Any], status_code: int = 200):
    response = {"status": "ok"}
    response.update(payload)
    return jsonify(response), status_code


def _error(message: str, status_code: int = 400):
    return jsonify({"status": "error", "message": message}), status_code


def _reload_settings() -> None:
    try:
        settings.reload()
    except Exception:
        LOGGER.warning("Failed to reload runtime settings", exc_info=True)


def _load_databases_config() -> Dict[str, Any]:
    config = load_settings_config(DATABASES_CONFIG_NAME)
    connections = config.get("connections") or []
    if not isinstance(connections, list):
        connections = []
    config["connections"] = connections
    return config


def _persist_databases_config(config: Dict[str, Any]) -> None:
    save_settings_config(DATABASES_CONFIG_NAME, config)
    _reload_settings()


def _load_llm_config() -> Dict[str, Any]:
    config = load_settings_config(LLM_CONFIG_NAME)
    presets = config.get("presets") or []
    if not isinstance(presets, list):
        presets = []
    config["presets"] = presets
    filter_llm = config.get("filter_llm") or {}
    if not isinstance(filter_llm, dict):
        filter_llm = {}
    config["filter_llm"] = filter_llm
    return config


def _persist_llm_config(config: Dict[str, Any]) -> None:
    save_settings_config(LLM_CONFIG_NAME, config)
    _reload_settings()


def _run_data_pipeline(topic: str, date: str, *, project: Optional[str] = None, topic_label: Optional[str] = None) -> Dict[str, Any]:
    """
    Run Merge → Clean → Filter → Upload sequentially.

    Args:
        topic: Project/topic identifier.
        date: Date string in YYYY-MM-DD format.
        project: Canonical project name used for logging.
        topic_label: Optional display name recorded in logs.

    Returns:
        Dict[str, Any]: Structured status report with per-step results.
    """
    from src.merge import run_merge  # type: ignore
    from src.clean import run_clean  # type: ignore
    from src.filter import run_filter  # type: ignore
    from src.update import run_update  # type: ignore

    pipeline_steps = [
        ("merge", run_merge),
        ("clean", run_clean),
        ("filter", run_filter),
        ("upload", run_update),
    ]

    log_project = project or topic
    params: Dict[str, Any] = {
        "date": date,
        "source": "api.pipeline",
        "bucket": topic,
    }
    if topic_label:
        params["topic"] = topic_label

    step_context = {
        "project": log_project,
        "params": {
            **params,
        },
    }
    steps: List[Dict[str, Any]] = []

    for name, func in pipeline_steps:
        result = func(topic, date)
        success = _evaluate_success(result)
        steps.append({
            "operation": name,
            "success": success,
            "result": _serialise_result(result),
        })
        _log_with_context(name, success, step_context)

        if not success:
            return {
                "status": "error",
                "message": f"{name} 步骤执行失败",
                "steps": steps,
            }

    return {
        "status": "ok",
        "steps": steps,
    }


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


@app.get("/api/settings/databases")
def list_database_connections():
    config = _load_databases_config()
    return _success(
        {
            "data": {
                "connections": config.get("connections", []),
                "active": config.get("active"),
            }
        }
    )


@app.post("/api/settings/databases")
def create_database_connection():
    payload = request.get_json(silent=True) or {}
    required = ["id", "name", "engine", "url"]
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return _error(f"Missing required field(s): {', '.join(missing)}")

    connection_id = str(payload["id"]).strip()
    config = _load_databases_config()
    connections = config.get("connections", [])

    if any(conn.get("id") == connection_id for conn in connections):
        return _error(f"Connection '{connection_id}' already exists", status_code=409)

    new_connection = {
        "id": connection_id,
        "name": str(payload["name"]).strip(),
        "engine": str(payload["engine"]).strip(),
        "url": str(payload["url"]).strip(),
        "description": str(payload.get("description", "")).strip(),
    }

    connections.append(new_connection)
    config["connections"] = connections

    if payload.get("set_active") or not config.get("active"):
        config["active"] = connection_id

    _persist_databases_config(config)

    return _success({"data": new_connection}, status_code=201)


@app.put("/api/settings/databases/<connection_id>")
def update_database_connection(connection_id: str):
    payload = request.get_json(silent=True) or {}
    config = _load_databases_config()
    connections = config.get("connections", [])

    for connection in connections:
        if connection.get("id") == connection_id:
            if "id" in payload and str(payload["id"]).strip() != connection_id:
                return _error("Connection id cannot be changed")

            for field in ["name", "engine", "url", "description"]:
                if field in payload:
                    connection[field] = str(payload[field]).strip()

            if payload.get("set_active"):
                config["active"] = connection_id

            _persist_databases_config(config)
            return _success({"data": connection})

    return _error(f"Connection '{connection_id}' was not found", status_code=404)


@app.delete("/api/settings/databases/<connection_id>")
def delete_database_connection(connection_id: str):
    config = _load_databases_config()
    connections = config.get("connections", [])
    remaining = [conn for conn in connections if conn.get("id") != connection_id]

    if len(remaining) == len(connections):
        return _error(f"Connection '{connection_id}' was not found", status_code=404)

    if config.get("active") == connection_id:
        return _error("Cannot delete the active database connection", status_code=409)

    config["connections"] = remaining
    _persist_databases_config(config)
    return _success({"data": {"deleted": connection_id}})


@app.post("/api/settings/databases/<connection_id>/activate")
def activate_database_connection(connection_id: str):
    config = _load_databases_config()
    connections = config.get("connections", [])

    if not any(conn.get("id") == connection_id for conn in connections):
        return _error(f"Connection '{connection_id}' was not found", status_code=404)

    config["active"] = connection_id
    _persist_databases_config(config)
    return _success({"data": {"active": connection_id}})


@app.get("/api/settings/llm")
def get_llm_settings():
    config = _load_llm_config()
    return _success({"data": config})


@app.put("/api/settings/llm/filter")
def update_llm_filter():
    payload = request.get_json(silent=True) or {}
    config = _load_llm_config()
    filter_llm = config.get("filter_llm", {})

    for field in ["provider", "model"]:
        if field in payload:
            filter_llm[field] = str(payload[field]).strip()

    for field in ["qps", "batch_size", "truncation"]:
        if field in payload:
            try:
                filter_llm[field] = int(payload[field])
            except (TypeError, ValueError):
                return _error(f"Field '{field}' must be an integer")

    config["filter_llm"] = filter_llm
    _persist_llm_config(config)
    return _success({"data": filter_llm})


@app.post("/api/settings/llm/presets")
def create_llm_preset():
    payload = request.get_json(silent=True) or {}
    required = ["id", "name", "provider", "model"]
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return _error(f"Missing required field(s): {', '.join(missing)}")

    preset_id = str(payload["id"]).strip()
    config = _load_llm_config()
    presets = config.get("presets", [])

    if any(preset.get("id") == preset_id for preset in presets):
        return _error(f"Preset '{preset_id}' already exists", status_code=409)

    new_preset = {
        "id": preset_id,
        "name": str(payload["name"]).strip(),
        "provider": str(payload["provider"]).strip(),
        "model": str(payload["model"]).strip(),
        "description": str(payload.get("description", "")).strip(),
    }

    presets.append(new_preset)
    config["presets"] = presets
    _persist_llm_config(config)
    return _success({"data": new_preset}, status_code=201)


@app.put("/api/settings/llm/presets/<preset_id>")
def update_llm_preset(preset_id: str):
    payload = request.get_json(silent=True) or {}
    config = _load_llm_config()
    presets = config.get("presets", [])

    for preset in presets:
        if preset.get("id") == preset_id:
            if "id" in payload and str(payload["id"]).strip() != preset_id:
                return _error("Preset id cannot be changed")

            for field in ["name", "provider", "model", "description"]:
                if field in payload:
                    preset[field] = str(payload[field]).strip()

            _persist_llm_config(config)
            return _success({"data": preset})

    return _error(f"Preset '{preset_id}' was not found", status_code=404)


@app.delete("/api/settings/llm/presets/<preset_id>")
def delete_llm_preset(preset_id: str):
    config = _load_llm_config()
    presets = config.get("presets", [])
    remaining = [preset for preset in presets if preset.get("id") != preset_id]

    if len(remaining) == len(presets):
        return _error(f"Preset '{preset_id}' was not found", status_code=404)

    config["presets"] = remaining
    _persist_llm_config(config)
    return _success({"data": {"deleted": preset_id}})


@app.post("/api/merge")
def merge_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = _prepare_pipeline_args(payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.merge import run_merge  # type: ignore

    response, code = _execute_operation(
        "merge",
        run_merge,
        topic_identifier,
        date,
        log_context={
            "project": log_project,
            "params": {
                "date": date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.post("/api/clean")
def clean_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = _prepare_pipeline_args(payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.clean import run_clean  # type: ignore

    response, code = _execute_operation(
        "clean",
        run_clean,
        topic_identifier,
        date,
        log_context={
            "project": log_project,
            "params": {
                "date": date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.post("/api/filter")
def filter_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = _prepare_pipeline_args(payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.filter import run_filter  # type: ignore

    response, code = _execute_operation(
        "filter",
        run_filter,
        topic_identifier,
        date,
        log_context={
            "project": log_project,
            "params": {
                "date": date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.post("/api/upload")
def upload_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = _prepare_pipeline_args(payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.update import run_update  # type: ignore

    response, code = _execute_operation(
        "upload",
        run_update,
        topic_identifier,
        date,
        log_context={
            "project": log_project,
            "params": {
                "date": date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.post("/api/pipeline")
def pipeline_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = _prepare_pipeline_args(payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    response, code = _execute_operation(
        "pipeline",
        _run_data_pipeline,
        topic_identifier,
        date,
        project=log_project,
        topic_label=display_name,
        log_context={
            "project": log_project,
            "params": {
                "date": date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.post("/api/query")
def query_endpoint():
    from src.query import run_query  # type: ignore

    response, code = _execute_operation(
        "query",
        run_query,
        log_context={"project": "GLOBAL", "params": {"source": "api"}},
    )
    return jsonify(response), code


@app.post("/api/fetch")
def fetch_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = _require_fields(payload, "start", "end")
    if not valid:
        return jsonify(error), 400

    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip()
    if not start or not end:
        return jsonify({"status": "error", "message": "Missing required field(s): start, end"}), 400

    try:
        topic_identifier, display_name, log_project = _resolve_topic_identifier(payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.fetch import run_fetch  # type: ignore

    response, code = _execute_operation(
        "fetch",
        run_fetch,
        topic_identifier,
        start,
        end,
        log_context={
            "project": log_project,
            "params": {
                "start": start,
                "end": end,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.post("/api/analyze")
def analyze_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error = _require_fields(payload, "start", "end")
    if not valid:
        return jsonify(error), 400

    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip()
    if not start or not end:
        return jsonify({"status": "error", "message": "Missing required field(s): start, end"}), 400

    try:
        topic_identifier, display_name, log_project = _resolve_topic_identifier(payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    func = payload.get("function")

    from src.analyze import run_Analyze  # type: ignore

    response, code = _execute_operation(
        "analyze",
        run_Analyze,
        topic_identifier,
        start,
        end_date=end,
        only_function=func,
        log_context={
            "project": log_project,
            "params": {
                "start": start,
                "end": end,
                "function": func,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    return jsonify(response), code


@app.get("/api/analyze/results")
def get_analyze_results():
    raw_topic = request.args.get("topic")
    raw_project = request.args.get("project")
    raw_dataset_id = request.args.get("dataset_id")

    payload = {
        "topic": raw_topic,
        "project": raw_project,
        "dataset_id": raw_dataset_id,
    }

    try:
        topic_identifier, display_name, _ = _resolve_topic_identifier(payload)
    except ValueError:
        topic_identifier = (raw_topic or "").strip()
        if not topic_identifier:
            return _error("Missing required query parameters: topic or project")
        display_name = raw_topic or raw_project or topic_identifier

    topic_display = display_name or raw_topic or raw_project or topic_identifier

    start = (request.args.get("start") or "").strip()
    if not start:
        return _error("Missing required query parameters: start")

    end = (request.args.get("end") or "").strip() or None
    function_alias = (request.args.get("function") or "").strip().lower() or None
    target_alias = (request.args.get("target") or "").strip()

    folder_name = _compose_analyze_folder(start, end)
    if not folder_name:
        return _error("Invalid start date supplied")

    analyze_root = bucket("analyze", topic_identifier, folder_name)
    if not analyze_root.exists():
        return _error("未找到对应的分析结果目录", status_code=404)

    def _match_target(name: str) -> bool:
        if not target_alias:
            return True
        return name.strip() == target_alias

    requested_functions = []
    if function_alias:
        for child in analyze_root.iterdir():
            if child.is_dir() and child.name.lower() == function_alias:
                requested_functions = [child.name]
                break
        if not requested_functions:
            requested_functions = [function_alias]
    else:
        requested_functions = [child.name for child in analyze_root.iterdir() if child.is_dir()]

    results = []
    for func_name in requested_functions:
        func_dir = analyze_root / func_name
        if not func_dir.exists() or not func_dir.is_dir():
            continue
        targets = []
        for target_dir in sorted(func_dir.iterdir()):
            if not target_dir.is_dir():
                continue
            target_name = target_dir.name
            if not _match_target(target_name):
                continue
            filename = ANALYZE_FILE_MAP.get(func_name, DEFAULT_ANALYZE_FILENAME)
            file_path = target_dir / filename
            if not file_path.exists():
                json_candidates = sorted(target_dir.glob("*.json"))
                if json_candidates:
                    file_path = json_candidates[0]
                else:
                    continue
            try:
                data = _load_json_file(file_path)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Failed to load analyze result file %s", file_path, exc_info=True)
                data = {"error": str(exc)}
            targets.append(
                {
                    "target": target_name,
                    "file": file_path.name,
                    "data": data,
                }
            )
        if targets:
            results.append({"name": func_name, "targets": targets})

    if not results:
        return _error("未找到匹配的分析结果文件", status_code=404)

    response_payload = {
        "topic": topic_display,
        "range": {
            "start": start,
            "end": end or start,
        },
        "functions": results,
    }
    return _success(response_payload)


@app.get("/api/projects")
def list_projects():
    return jsonify({"status": "ok", "projects": PROJECT_MANAGER.list_projects()})


@app.get("/api/projects/<string:name>")
def project_detail(name: str):
    project = PROJECT_MANAGER.get_project(name)
    if not project:
        return jsonify({"status": "error", "message": "Project not found"}), 404
    return jsonify({"status": "ok", "project": project})


@app.post("/api/projects")
def create_project():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    if not name:
        return jsonify({"status": "error", "message": "Missing required field: name"}), 400

    description = payload.get("description")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    project = PROJECT_MANAGER.create_or_update_project(
        name,
        description=description,
        metadata=metadata,
    )
    return jsonify({"status": "ok", "project": project})


@app.delete("/api/projects/<string:name>")
def delete_project(name: str):
    if not PROJECT_MANAGER.delete_project(name):
        return jsonify({"status": "error", "message": "Project not found"}), 404
    return jsonify({"status": "ok", "message": "Project deleted"})


@app.get("/api/projects/<string:name>/datasets")
def project_datasets(name: str):
    try:
        datasets = list_project_datasets(name)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to read dataset manifest for project %s", name)
        return jsonify({"status": "error", "message": "无法读取项目数据清单"}), 500
    return jsonify({"status": "ok", "datasets": datasets})


@app.get("/api/projects/<string:name>/datasets/<string:dataset_id>/preview")
def project_dataset_preview(name: str, dataset_id: str):
    page = request.args.get("page", default=1, type=int)
    page_size = request.args.get("page_size", default=20, type=int)
    try:
        preview = get_dataset_preview(name, dataset_id, page=page, page_size=page_size)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except FileNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to preview dataset %s for project %s", dataset_id, name)
        return jsonify({"status": "error", "message": "无法加载数据集预览"}), 500
    return jsonify({"status": "ok", "preview": preview})


@app.get("/api/projects/<string:name>/date-range")
def project_date_range(name: str):
    dataset_id = request.args.get("dataset_id")
    try:
        summary = get_dataset_date_summary(name, dataset_id=dataset_id)
    except (LookupError, FileNotFoundError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to derive date range for project %s", name)
        return jsonify({"status": "error", "message": "无法解析数据集日期范围"}), 500

    dataset_info = summary.get("dataset")
    if isinstance(dataset_info, dict):
        dataset_info.setdefault("column_mapping", summary.get("column_mapping"))

    payload: Dict[str, Any] = {"status": "ok", "topic": name}
    payload.update(summary)
    return jsonify(payload)


@app.put("/api/projects/<string:name>/datasets/<string:dataset_id>/mapping")
def update_project_dataset_mapping(name: str, dataset_id: str):
    payload = request.get_json(silent=True) or {}
    raw_mapping = payload.get("column_mapping", payload)
    mapping = _parse_column_mapping_payload(raw_mapping)
    if not mapping:
        for key in ("date", "title", "content", "author"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                mapping[key] = value.strip()

    topic_label = None
    if "topic_label" in payload:
        topic_label = _normalise_topic_label(payload.get("topic_label"))

    try:
        updated = update_dataset_column_mapping(
            name,
            dataset_id,
            mapping,
            topic_label=topic_label,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to update column mapping for dataset %s of project %s", dataset_id, name)
        return jsonify({"status": "error", "message": "无法更新字段映射"}), 500

    return jsonify(
        {
            "status": "ok",
            "column_mapping": updated.get("column_mapping", {}),
            "topic_label": updated.get("topic_label", ""),
        }
    )


@app.post("/api/projects/<string:name>/datasets")
def upload_project_dataset(name: str):
    file = request.files.get("file")
    if not file or not getattr(file, "filename", ""):
        return jsonify({"status": "error", "message": "请选择需要上传的表格文件"}), 400

    mapping_hints = _parse_column_mapping_from_form(request.form)
    topic_label_hint = _normalise_topic_label(request.form.get("topic_label"))

    try:
        dataset = store_uploaded_dataset(
            name,
            file,
            column_mapping=mapping_hints,
            topic_label=topic_label_hint,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to store dataset for project %s", name)
        try:
            PROJECT_MANAGER.log_operation(
                name,
                "import_dataset",
                params={"source": "api"},
                success=False,
            )
        except Exception:  # pragma: no cover - avoid cascading failures
            LOGGER.debug("Unable to persist failed dataset log for project %s", name, exc_info=True)
        return jsonify({"status": "error", "message": "数据集保存失败"}), 500

    try:
        PROJECT_MANAGER.log_operation(
            name,
            "import_dataset",
            params={
                "dataset_id": dataset.get("id"),
                "filename": dataset.get("display_name"),
                "rows": dataset.get("rows"),
                "columns": dataset.get("column_count"),
                "column_mapping": dataset.get("column_mapping"),
                "topic_label": dataset.get("topic_label"),
                "source": "api",
            },
            success=True,
        )
    except Exception:  # pragma: no cover - logging should not break API
        LOGGER.debug("Failed to persist dataset upload log for project %s", name, exc_info=True)

    return jsonify({"status": "ok", "dataset": dataset}), 201


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
        "/api/projects",
        "/api/projects/<name>",
        "/api/projects/<name>/datasets",
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
