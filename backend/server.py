from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import Flask, jsonify, request
from flask_cors import CORS

# 注意：所有新的辅助函数请存放在 ``backend/server_support`` 包中，
# 并通过 ``from server_support import ...`` 或具体模块导入，保持 server.py 专注于路由逻辑。

from server_support.paths import BACKEND_DIR, SRC_DIR  # type: ignore


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

for path in (BACKEND_DIR, SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.project import (  # type: ignore
    get_dataset_date_summary,
    get_dataset_preview,
    get_project_manager,
    list_project_datasets,
    update_dataset_column_mapping,
    store_uploaded_dataset,
)
from src.utils.setting.paths import bucket  # type: ignore

from server_support import (  # type: ignore
    collect_filter_status,
    error,
    evaluate_success,
    filter_ai_overview,
    load_config,
    load_databases_config,
    load_filter_template_config,
    load_llm_config,
    normalise_topic_label,
    parse_column_mapping_from_form,
    parse_column_mapping_payload,
    persist_databases_config,
    persist_filter_template_config,
    persist_llm_config,
    prepare_pipeline_args,
    resolve_topic_identifier,
    require_fields,
    serialise_result,
    success,
)

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
    except Exception as exc:  # pragma: no cover - defensive: surface backend errors
        LOGGER.exception("Error while executing operation %s", operation)
        _log_with_context(operation, False, log_context)
        return {
            "status": "error",
            "operation": operation,
            "message": str(exc),
        }, 500


def _compose_analyze_folder(start: str, end: Optional[str]) -> str:
    end = end or ""
    start = start.strip()
    end = end.strip()
    if not start:
        return ""
    if end and end != start:
        return f"{start}_{end}"
    return start


app = Flask(__name__)
CORS(app)

CONFIG = load_config()

DATABASES_CONFIG_NAME = "databases"
LLM_CONFIG_NAME = "llm"


def _load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            fh.seek(0)
            return fh.read()


def _run_data_pipeline(topic: str, date: str, *, project: Optional[str] = None, topic_label: Optional[str] = None) -> Dict[str, Any]:
    """
    Run Merge → Clean sequentially.

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

    pipeline_steps = [
        ("merge", run_merge),
        ("clean", run_clean),
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
        success = evaluate_success(result)
        steps.append({
            "operation": name,
            "success": success,
            "result": serialise_result(result),
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
    config = load_databases_config()
    return success(
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
        return error(f"Missing required field(s): {', '.join(missing)}")

    connection_id = str(payload["id"]).strip()
    config = load_databases_config()
    connections = config.get("connections", [])

    if any(conn.get("id") == connection_id for conn in connections):
        return error(f"Connection '{connection_id}' already exists", status_code=409)

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

    persist_databases_config(config)

    return success({"data": new_connection}, status_code=201)


@app.put("/api/settings/databases/<connection_id>")
def update_database_connection(connection_id: str):
    payload = request.get_json(silent=True) or {}
    config = load_databases_config()
    connections = config.get("connections", [])

    for connection in connections:
        if connection.get("id") == connection_id:
            if "id" in payload and str(payload["id"]).strip() != connection_id:
                return error("Connection id cannot be changed")

            for field in ["name", "engine", "url", "description"]:
                if field in payload:
                    connection[field] = str(payload[field]).strip()

            if payload.get("set_active"):
                config["active"] = connection_id

            persist_databases_config(config)
            return success({"data": connection})

    return error(f"Connection '{connection_id}' was not found", status_code=404)


@app.delete("/api/settings/databases/<connection_id>")
def delete_database_connection(connection_id: str):
    config = load_databases_config()
    connections = config.get("connections", [])
    remaining = [conn for conn in connections if conn.get("id") != connection_id]

    if len(remaining) == len(connections):
        return error(f"Connection '{connection_id}' was not found", status_code=404)

    if config.get("active") == connection_id:
        return error("Cannot delete the active database connection", status_code=409)

    config["connections"] = remaining
    persist_databases_config(config)
    return success({"data": {"deleted": connection_id}})


@app.post("/api/settings/databases/<connection_id>/activate")
def activate_database_connection(connection_id: str):
    config = load_databases_config()
    connections = config.get("connections", [])

    if not any(conn.get("id") == connection_id for conn in connections):
        return error(f"Connection '{connection_id}' was not found", status_code=404)

    config["active"] = connection_id
    persist_databases_config(config)
    return success({"data": {"active": connection_id}})


@app.get("/api/settings/llm")
def get_llm_settings():
    config = load_llm_config()
    return success({"data": config})


@app.put("/api/settings/llm/filter")
def update_llm_filter():
    payload = request.get_json(silent=True) or {}
    config = load_llm_config()
    filter_llm = config.get("filter_llm", {})

    for field in ["provider", "model"]:
        if field in payload:
            filter_llm[field] = str(payload[field]).strip()

    for field in ["qps", "batch_size", "truncation"]:
        if field in payload:
            try:
                filter_llm[field] = int(payload[field])
            except (TypeError, ValueError):
                return error(f"Field '{field}' must be an integer")

    config["filter_llm"] = filter_llm
    persist_llm_config(config)
    return success({"data": filter_llm})


@app.get("/api/filter/template")
def get_filter_template():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()

    if not topic_param and not project_param:
        return error("Missing required field(s): topic or project")

    resolution_payload: Dict[str, Any] = {}
    if topic_param:
        resolution_payload["topic"] = topic_param
    if project_param:
        resolution_payload["project"] = project_param

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    try:
        data = load_filter_template_config(topic_identifier)
    except ValueError as exc:
        return error(str(exc))

    return success({"data": data})


@app.post("/api/filter/template")
def upsert_filter_template():
    payload = request.get_json(silent=True) or {}
    topic_param = str(payload.get("topic") or payload.get("project") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    theme = str(payload.get("topic_theme") or payload.get("theme") or "").strip()
    categories_value = payload.get("categories", [])

    if not topic_param:
        return error("Missing required field(s): topic")
    if not theme:
        return error("Missing required field(s): topic_theme")
    if not isinstance(categories_value, list):
        return error("Field 'categories' must be a list")

    categories = [str(item).strip() for item in categories_value if str(item or "").strip()]

    resolution_payload: Dict[str, Any] = {"topic": topic_param}
    if project_param:
        resolution_payload["project"] = project_param
    if payload.get("dataset_id"):
        resolution_payload["dataset_id"] = payload.get("dataset_id")

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    template_override = payload.get("template")
    try:
        data = persist_filter_template_config(topic_identifier, theme, categories, template_override)
    except ValueError as exc:
        return error(str(exc))

    return success({"data": data})


@app.get("/api/filter/status")
def filter_status():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()
    date_param = str(request.args.get("date", "") or "").strip()

    if not topic_param and not project_param:
        return error("Missing required field(s): topic or project")
    if not date_param:
        return error("Missing required field(s): date")

    resolution_payload: Dict[str, Any] = {}
    if topic_param:
        resolution_payload["topic"] = topic_param
    if project_param:
        resolution_payload["project"] = project_param

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    status_payload = collect_filter_status(topic_identifier, date_param)
    status_payload["ai_config"] = _filter_ai_overview()
    return success({"data": status_payload})


@app.post("/api/settings/llm/presets")
def create_llm_preset():
    payload = request.get_json(silent=True) or {}
    required = ["id", "name", "provider", "model"]
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return error(f"Missing required field(s): {', '.join(missing)}")

    preset_id = str(payload["id"]).strip()
    config = load_llm_config()
    presets = config.get("presets", [])

    if any(preset.get("id") == preset_id for preset in presets):
        return error(f"Preset '{preset_id}' already exists", status_code=409)

    new_preset = {
        "id": preset_id,
        "name": str(payload["name"]).strip(),
        "provider": str(payload["provider"]).strip(),
        "model": str(payload["model"]).strip(),
        "description": str(payload.get("description", "")).strip(),
    }

    presets.append(new_preset)
    config["presets"] = presets
    persist_llm_config(config)
    return success({"data": new_preset}, status_code=201)


@app.put("/api/settings/llm/presets/<preset_id>")
def update_llm_preset(preset_id: str):
    payload = request.get_json(silent=True) or {}
    config = load_llm_config()
    presets = config.get("presets", [])

    for preset in presets:
        if preset.get("id") == preset_id:
            if "id" in payload and str(payload["id"]).strip() != preset_id:
                return error("Preset id cannot be changed")

            for field in ["name", "provider", "model", "description"]:
                if field in payload:
                    preset[field] = str(payload[field]).strip()

            persist_llm_config(config)
            return success({"data": preset})

    return error(f"Preset '{preset_id}' was not found", status_code=404)


@app.delete("/api/settings/llm/presets/<preset_id>")
def delete_llm_preset(preset_id: str):
    config = load_llm_config()
    presets = config.get("presets", [])
    remaining = [preset for preset in presets if preset.get("id") != preset_id]

    if len(remaining) == len(presets):
        return error(f"Preset '{preset_id}' was not found", status_code=404)

    config["presets"] = remaining
    persist_llm_config(config)
    return success({"data": {"deleted": preset_id}})


@app.post("/api/merge")
def merge_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(payload, PROJECT_MANAGER)
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
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(payload, PROJECT_MANAGER)
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
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(payload, PROJECT_MANAGER)
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
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(payload, PROJECT_MANAGER)
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
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(payload, PROJECT_MANAGER)
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
    valid, error = require_fields(payload, "start", "end")
    if not valid:
        return jsonify(error), 400

    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip()
    if not start or not end:
        return jsonify({"status": "error", "message": "Missing required field(s): start, end"}), 400

    try:
        topic_identifier, display_name, log_project, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
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
    valid, error = require_fields(payload, "start", "end")
    if not valid:
        return jsonify(error), 400

    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip()
    if not start or not end:
        return jsonify({"status": "error", "message": "Missing required field(s): start, end"}), 400

    try:
        topic_identifier, display_name, log_project, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
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
        topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    except ValueError:
        topic_identifier = (raw_topic or "").strip()
        if not topic_identifier:
            return error("Missing required query parameters: topic or project")
        display_name = raw_topic or raw_project or topic_identifier

    topic_display = display_name or raw_topic or raw_project or topic_identifier

    start = (request.args.get("start") or "").strip()
    if not start:
        return error("Missing required query parameters: start")

    end = (request.args.get("end") or "").strip() or None
    function_alias = (request.args.get("function") or "").strip().lower() or None
    target_alias = (request.args.get("target") or "").strip()

    folder_name = _compose_analyze_folder(start, end)
    if not folder_name:
        return error("Invalid start date supplied")

    analyze_root = bucket("analyze", topic_identifier, folder_name)
    if not analyze_root.exists():
        return error("未找到对应的分析结果目录", status_code=404)

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
        return error("未找到匹配的分析结果文件", status_code=404)

    response_payload = {
        "topic": topic_display,
        "range": {
            "start": start,
            "end": end or start,
        },
        "functions": results,
    }
    return success(response_payload)


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
    mapping = parse_column_mapping_payload(raw_mapping)
    if not mapping:
        for key in ("date", "title", "content", "author"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                mapping[key] = value.strip()

    topic_label = None
    if "topic_label" in payload:
        topic_label = normalise_topic_label(payload.get("topic_label"))

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

    mapping_hints = parse_column_mapping_from_form(request.form)
    topic_label_hint = normalise_topic_label(request.form.get("topic_label"))

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
