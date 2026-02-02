from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import sys
import time
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import Flask, Response, jsonify, request, send_file, stream_with_context
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
from src.utils.setting.paths import bucket, get_data_root, _normalise_topic  # type: ignore

from src.topic.data_bertopic_qwen import run_topic_bertopic
from openai import OpenAI

from server_support import (  # type: ignore
    collect_layer_archives,
    collect_project_archives,
    collect_filter_status,
    error,
    evaluate_success,
    filter_ai_overview,
    build_settings_backup,
    restore_settings_backup,
    load_config,
    load_content_prompt_config,
    load_databases_config,
    load_filter_template_config,
    load_llm_config,
    load_rag_config,
    ensure_rag_ready,
    get_rag_build_status,
    ensure_routerrag_db,
    ensure_tagrag_db,
    list_project_routerrag_topics,
    list_project_tagrag_topics,
    start_rag_build,
    mask_api_keys,
    normalise_topic_label,
    parse_column_mapping_from_form,
    parse_column_mapping_payload,
    persist_databases_config,
    persist_content_prompt_config,
    persist_filter_template_config,
    persist_llm_config,
    persist_rag_config,
    prepare_pipeline_args,
    resolve_topic_identifier,
    resolve_stage_processing_date,
    require_fields,
    serialise_result,
    success,
    validate_rag_config,
    DATA_PROJECTS_ROOT,
    mark_filter_job_running,
    mark_filter_job_finished,
    get_default_rag_config,
)
from server_support.router_prompts.utils import (
    load_router_prompt_config,
    persist_router_prompt_config,
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
    start = start.strip()
    end = (end or "").strip()
    if not start:
        return ""
    if end:
        return f"{start}_{end}"
    return start

def _run_topic_bertopic_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    valid, error_response = require_fields(payload, "topic", "start_date")
    if not valid:
        return error_response

    raw_topic = str(payload.get("topic") or "").strip()
    raw_project = str(payload.get("project") or "").strip()
    raw_dataset_id = str(payload.get("dataset_id") or "").strip()

    start_date = str(payload.get("start_date") or "").strip()
    end_value = payload.get("end_date")
    end_date = str(end_value).strip() if end_value else None

    if not raw_topic and not raw_project and not raw_dataset_id:
        return {
            "status": "error",
            "message": "Missing required field(s): topic, project, or dataset_id",
        }

    if not start_date:
        return {
            "status": "error",
            "message": "Missing required field(s): start_date",
        }

    # 将云端/项目标识解析为本地 bucket 名称（与基础分析一致）
    try:
        topic_identifier, display_name, log_project, _ = resolve_topic_identifier(
            {
                "topic": raw_topic,
                "project": raw_project,
                "dataset_id": raw_dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError:
        topic_identifier = (raw_topic or raw_project or "").strip()
        display_name = raw_topic or raw_project or topic_identifier
        log_project = topic_identifier

    bucket_topic = topic_identifier or raw_topic
    db_topic = raw_topic or display_name or bucket_topic
    topic_label = display_name or db_topic

    # 确保存储目录存在，避免回落到旧路径
    try:
        PROJECT_MANAGER.ensure_project_storage(log_project or bucket_topic, create_if_missing=True)
    except Exception:
        LOGGER.warning("Failed to ensure project storage for BERTopic", exc_info=True)

    # 使用新的BERTopic实现，集成fetch流程
    try:
        # 导入新的BERTopic模块
        from src.topic.data_bertopic_qwen_v2 import run_topic_bertopic

        # 确保fetch数据可用性检查
        from src.fetch.data_fetch import get_topic_available_date_range

        # 检查数据可用范围（使用数据库实际专题名）
        availability = get_topic_available_date_range(db_topic)
        if isinstance(availability, dict):
            avail_start = availability.get("start")
            avail_end = availability.get("end")
        else:
            avail_start, avail_end = availability

        if avail_start and avail_end:
            import pandas as pd
            req_start = pd.to_datetime(start_date).date()
            req_end = pd.to_datetime(end_date or start_date).date()
            avail_start_date = pd.to_datetime(avail_start).date()
            avail_end_date = pd.to_datetime(avail_end).date()

            if req_start < avail_start_date or req_end > avail_end_date:
                return {
                    "status": "error",
                    "message": f"请求的日期范围 {start_date}~{end_date or start_date} 超出可用范围 {avail_start}~{avail_end}",
                }
    except ImportError:
        # 如果新模块不存在，回退到旧实现
        from src.topic.data_bertopic_qwen import run_topic_bertopic

    fetch_dir = payload.get("fetch_dir")
    fetch_dir = str(fetch_dir).strip() if fetch_dir else None

    userdict = payload.get("userdict")
    userdict = str(userdict).strip() if userdict else None

    stopwords = payload.get("stopwords")
    stopwords = str(stopwords).strip() if stopwords else None

    # 运行BERTopic分析
    result = run_topic_bertopic(
        bucket_topic,
        start_date,
        end_date,
        fetch_dir=fetch_dir,
        userdict=userdict,
        stopwords=stopwords,
        bucket_topic=bucket_topic,
        db_topic=db_topic,
        display_topic=topic_label,
    )

    if result:
        # 返回成功响应，包含更多信息
        folder_name = f"{start_date}_{end_date}" if end_date else start_date
        return {
            "status": "ok",
            "operation": "topic-bertopic",
            "data": {
                "topic": topic_label,
                "bucket": bucket_topic,
                "start_date": start_date,
                "end_date": end_date,
                "folder": folder_name,
                "message": "BERTopic分析完成，结果已保存"
            }
        }

    return {
        "status": "error",
        "message": "BERTopic 主题分析执行失败，请检查后端日志",
    }


def _split_analyze_folder(folder: str) -> Tuple[str, str]:
    folder = (folder or "").strip()
    if not folder:
        return "", ""
    if "_" in folder:
        start, end = folder.split("_", 1)
        start = start.strip()
        end = end.strip() or start
    else:
        start = folder
        end = folder
    return start, end


def _summarise_api_key(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {"configured": False, "last_four": ""}
    last_four = value[-4:] if len(value) >= 4 else value
    return {"configured": True, "last_four": last_four}


def _resolve_filter_status_inputs(
    topic_param: str, project_param: str, date_param: str
) -> Tuple[str, str, Optional[str]]:
    if not topic_param and not project_param:
        raise ValueError("Missing required field(s): topic or project")

    resolution_payload: Dict[str, Any] = {}
    if topic_param:
        resolution_payload["topic"] = topic_param
    if project_param:
        resolution_payload["project"] = project_param

    topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    resolved_date, fallback_from = resolve_stage_processing_date(topic_identifier, "filter", date_param or None)
    return topic_identifier, resolved_date, fallback_from


def _build_filter_status_payload(
    topic_identifier: str,
    resolved_date: str,
    fallback_from: Optional[str],
) -> Dict[str, Any]:
    status_payload = collect_filter_status(topic_identifier, resolved_date)
    status_payload["ai_config"] = filter_ai_overview()
    if fallback_from:
        context = status_payload.setdefault("context", {})
        if isinstance(context, dict):
            context["resolved_date"] = resolved_date
            context["requested_date"] = fallback_from
    return status_payload


def _collect_analyze_history(
    topic_identifier: str,
    topic_label: str,
    aliases: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    data_root = get_data_root() / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    candidate_names: List[str] = [topic_identifier]
    if aliases:
        candidate_names.extend(aliases)
    candidate_names.extend([_normalise_name(name) for name in candidate_names if name])

    seen_dirs: set[str] = set()
    records: List[Dict[str, Any]] = []

    for name in candidate_names:
        cleaned = (name or "").strip()
        if not cleaned or cleaned in seen_dirs:
            continue
        seen_dirs.add(cleaned)
        analyze_dir = data_root / cleaned / "analyze"
        if not analyze_dir.exists():
            continue
        for entry in analyze_dir.iterdir():
            if not entry.is_dir():
                continue
            start, end = _split_analyze_folder(entry.name)
            if not start:
                continue
            stats = entry.stat()
            records.append(
                {
                    "id": f"{cleaned}:{entry.name}",
                    "topic": topic_label,
                    "topic_identifier": cleaned,
                    "start": start,
                    "end": end,
                    "folder": entry.name,
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stats.st_mtime)),
                    "_updated_ts": stats.st_mtime,
                }
            )

    records.sort(key=lambda item: item.get("_updated_ts", 0), reverse=True)
    for record in records:
        record.pop("_updated_ts", None)
    return records


def _normalise_name(value: Optional[str]) -> str:
    return _normalise_topic(value or "")


def _submit_filter_job(
    run_callable: Callable[[str, str, Optional[Any]], Any],
    *,
    topic_identifier: str,
    resolved_date: str,
    log_project: str,
    display_name: str,
) -> concurrent.futures.Future:
    """
    Execute the filter pipeline in a worker thread so that the API request
    can return immediately while streaming endpoints keep receiving updates.
    """

    def _job():
        try:
            _execute_operation(
                "filter",
                run_callable,
                topic_identifier,
                resolved_date,
                log_context={
                    "project": log_project,
                    "params": {
                        "date": resolved_date,
                        "source": "api",
                        "topic": display_name,
                        "bucket": topic_identifier,
                    },
                },
            )
        except Exception:  # pragma: no cover - background diagnostics
            LOGGER.exception("Filter job failed for %s@%s", topic_identifier, resolved_date)
        finally:
            mark_filter_job_finished(topic_identifier, resolved_date)

    return FILTER_EXECUTOR.submit(_job)


app = Flask(__name__)
CORS(app)

CONFIG = load_config()

DATABASES_CONFIG_NAME = "databases"
LLM_CONFIG_NAME = "llm"
FILTER_STATUS_STREAM_INTERVAL = 1.0
FILTER_STATUS_STREAM_TIMEOUT = 300.0
FILTER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _resolve_runtime_binding() -> Tuple[str, int]:
    """Determine which host/port the Flask app should bind to."""

    host = "0.0.0.0"

    port_value = os.environ.get("OPINION_BACKEND_PORT")
    if port_value:
        try:
            port = int(port_value)
        except ValueError:
            LOGGER.warning(
                "Invalid OPINION_BACKEND_PORT=%s provided. Falling back to 8000.",
                port_value,
            )
            port = 8000
    else:
        port = 8000

    return host, port


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


@app.get("/api/settings/archives/export")
def export_settings_archive():
    try:
        buffer, filename, manifest = build_settings_backup()
    except Exception:  # pragma: no cover - runtime export errors surface to client
        LOGGER.exception("Failed to build settings backup")
        return error("导出存档失败，请检查后端日志", status_code=500)

    response = send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )
    included = manifest.get("included_roots") or []
    missing = manifest.get("missing_roots") or []
    generated_at = manifest.get("generated_at")

    if included:
        response.headers["X-Backup-Roots"] = ",".join(included)
    if missing:
        response.headers["X-Backup-Missing"] = ",".join(missing)
    if generated_at:
        response.headers["X-Backup-Generated-At"] = str(generated_at)
    response.headers["X-Backup-File-Count"] = str(manifest.get("file_count", 0))
    return response


@app.post("/api/settings/archives/import")
def import_settings_archive():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return error("请上传 ZIP 存档文件")

    try:
        result = restore_settings_backup(upload.stream)
    except ValueError as exc:
        return error(str(exc))
    except Exception:  # pragma: no cover - runtime import errors surface to client
        LOGGER.exception("Failed to restore settings backup")
        return error("导入存档失败，请检查后端日志", status_code=500)

    return success({"data": result})


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
    response_payload = dict(config)
    response_payload.pop("credentials", None)
    return success({"data": response_payload})


@app.get("/api/settings/llm/credentials")
def get_llm_credentials():
    config = load_llm_config()
    credentials = config.get("credentials", {})
    qwen_key = credentials.get("qwen_api_key") or credentials.get("dashscope_api_key")
    openai_key = credentials.get("openai_api_key") or credentials.get("opinion_openai_api_key")
    return success({
        "data": {
            "qwen": _summarise_api_key(qwen_key if isinstance(qwen_key, str) else None),
            "openai": _summarise_api_key(openai_key if isinstance(openai_key, str) else None),
            "openai_base_url": str(credentials.get("openai_base_url") or ""),
        }
    })


@app.put("/api/settings/llm/credentials")
def update_llm_credentials():
    payload = request.get_json(silent=True) or {}
    config = load_llm_config()
    credentials = dict(config.get("credentials", {}))

    def _update_text_field(field: str) -> None:
        if field not in payload:
            return
        value = payload.get(field)
        text = ""
        if isinstance(value, str):
            text = value.strip()
        elif value is None:
            text = ""
        else:
            text = str(value).strip()

        if text:
            credentials[field] = text
        else:
            credentials.pop(field, None)

    _update_text_field("qwen_api_key")
    _update_text_field("dashscope_api_key")
    _update_text_field("openai_api_key")
    _update_text_field("opinion_openai_api_key")
    _update_text_field("openai_base_url")

    config["credentials"] = credentials
    persist_llm_config(config)

    return success({
        "data": {
            "qwen": _summarise_api_key(credentials.get("qwen_api_key") or credentials.get("dashscope_api_key")),
            "openai": _summarise_api_key(credentials.get("openai_api_key") or credentials.get("opinion_openai_api_key")),
            "openai_base_url": str(credentials.get("openai_base_url") or ""),
        }
    })


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

@app.route("/api/ai/chat", methods=["POST"])
def chat_ai():
    """
    Stream chat completion using system LLM settings (Assistant profile).
    Expected JSON payload: { "messages": [ { "role": "user", "content": "..." } ] }
    """
    data = request.json
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "No messages provided"}), 400

    config = load_llm_config()
    assistant = config.get("assistant", {})
    credentials = config.get("credentials", {})

    # Load Knowledge Base
    kb_content = []
    kb_dir = BACKEND_DIR / "knowledge_base"
    if kb_dir.exists():
        for md_file in kb_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                if content.strip():
                    kb_content.append(f"--- {md_file.name} ---\n{content}")
            except Exception as e:
                LOGGER.error(f"Failed to read KB file {md_file}: {e}")

    # Build System Prompt
    system_prompt_parts = []
    
    # 1. Custom System Prompt from Config
    custom_system_prompt = assistant.get("system_prompt", "").strip()
    if custom_system_prompt:
        system_prompt_parts.append(custom_system_prompt)
    else:
        system_prompt_parts.append("You are a helpful assistant provided by OpinionSystem.")

    # 2. Add Knowledge Base Context if available
    if kb_content:
        system_prompt_parts.append("\n[Context Information from Knowledge Base]")
        system_prompt_parts.append("\n".join(kb_content))
        system_prompt_parts.append("[End of Context Information]")

    combined_system_message = "\n\n".join(system_prompt_parts)
    
    # Prepend system message to messages list
    # Ensure we don't duplicate system message if client sent one, but usually client sends user/assistant
    final_messages = [{"role": "system", "content": combined_system_message}] + messages

    # Determine provider details
    provider = assistant.get("provider", "openai").lower()
    model = assistant.get("model", "llama3")
    
    # Default defaults (Ollama-like)
    api_key = "ollama"
    base_url = "http://localhost:11434/v1"

    if provider == "qwen":
        api_key = credentials.get("qwen_api_key") or credentials.get("dashscope_api_key") or "EMPTY"
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    elif provider == "openai":
         # Use configured OpenAI settings, which might point to a local server or real OpenAI
         configured_base = credentials.get("openai_base_url")
         if configured_base:
             base_url = configured_base
         
         configured_key = credentials.get("openai_api_key") or credentials.get("opinion_openai_api_key")
         if configured_key:
             api_key = configured_key

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    def generate():
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=final_messages,
                stream=True,
                max_tokens=assistant.get("max_tokens"),
                temperature=assistant.get("temperature"),
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            LOGGER.error(f"AI Chat Error: {e}")
            yield f"Error: {str(e)}"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")





@app.put("/api/settings/llm/assistant")
def update_llm_assistant():
    payload = request.get_json(silent=True) or {}
    config = load_llm_config()
    assistant = config.get("assistant", {})

    for field in ["provider", "model", "base_url", "system_prompt"]:
        if field in payload:
            assistant[field] = str(payload[field]).strip()

    if "max_tokens" in payload:
        try:
            assistant["max_tokens"] = int(payload["max_tokens"])
        except (TypeError, ValueError):
            return error("Field 'max_tokens' must be an integer")

    if "temperature" in payload:
        try:
            assistant["temperature"] = float(payload["temperature"])
        except (TypeError, ValueError):
            return error("Field 'temperature' must be a number")

    config["assistant"] = assistant
    persist_llm_config(config)
    return success({"data": assistant})


@app.put("/api/settings/llm/embedding")
def update_llm_embedding():
    payload = request.get_json(silent=True) or {}
    config = load_llm_config()
    embedding_llm = config.get("embedding_llm", {})
    if not isinstance(embedding_llm, dict):
        embedding_llm = {}

    for field in ["provider", "model", "base_url"]:
        if field in payload:
            embedding_llm[field] = str(payload[field]).strip()

    if "dimension" in payload:
        try:
            embedding_llm["dimension"] = int(payload["dimension"])
        except (TypeError, ValueError):
            return error("Field 'dimension' must be an integer")

    config["embedding_llm"] = embedding_llm
    persist_llm_config(config)
    return success({"data": embedding_llm})


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


@app.get("/api/content/prompt")
def get_content_prompt():
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
        data = load_content_prompt_config(topic_identifier)
    except ValueError as exc:
        return error(str(exc))

    return success({"data": data})


@app.post("/api/content/prompt")
def upsert_content_prompt():
    payload = request.get_json(silent=True) or {}
    topic_param = str(payload.get("topic") or payload.get("project") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    system_prompt = str(payload.get("system_prompt") or "").strip()
    analysis_prompt = str(payload.get("analysis_prompt") or "").strip()

    if not topic_param:
        return error("Missing required field(s): topic")
    if not system_prompt and not analysis_prompt:
        return error("Missing required field(s): system_prompt or analysis_prompt")

    resolution_payload: Dict[str, Any] = {"topic": topic_param}
    if project_param:
        resolution_payload["project"] = project_param
    if payload.get("dataset_id"):
        resolution_payload["dataset_id"] = payload.get("dataset_id")

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    try:
        data = persist_content_prompt_config(topic_identifier, system_prompt, analysis_prompt)
    except ValueError as exc:
        return error(str(exc))

    return success({"data": data})


@app.get("/api/filter/status")
def filter_status():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()
    date_param = str(request.args.get("date", "") or "").strip()

    try:
        topic_identifier, resolved_date, fallback_from = _resolve_filter_status_inputs(
            topic_param, project_param, date_param
        )
    except ValueError as exc:
        return error(str(exc))

    status_payload = _build_filter_status_payload(topic_identifier, resolved_date, fallback_from)
    return success({"data": status_payload})


@app.get("/api/filter/status/stream")
def filter_status_stream():
    topic_param = str(request.args.get("topic", "") or "").strip()
    project_param = str(request.args.get("project", "") or "").strip()
    date_param = str(request.args.get("date", "") or "").strip()
    interval_param = str(request.args.get("interval", "") or "").strip()

    try:
        topic_identifier, resolved_date, fallback_from = _resolve_filter_status_inputs(
            topic_param, project_param, date_param
        )
    except ValueError as exc:
        return error(str(exc))

    try:
        interval = float(interval_param) if interval_param else FILTER_STATUS_STREAM_INTERVAL
    except ValueError:
        interval = FILTER_STATUS_STREAM_INTERVAL
    interval = max(0.5, min(5.0, interval))

    def _stream():
        start_time = time.time()
        last_snapshot = ""
        yield f"retry: {int(interval * 1500)}\n\n"
        while True:
            try:
                status_payload = _build_filter_status_payload(topic_identifier, resolved_date, fallback_from)
            except Exception as exc:  # pragma: no cover - defensive
                error_payload = {"message": str(exc)}
                yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
                break

            message = json.dumps({"data": status_payload}, ensure_ascii=False)
            if message != last_snapshot:
                yield f"data: {message}\n\n"
                last_snapshot = message

            if not status_payload.get("running"):
                break
            if (time.time() - start_time) >= FILTER_STATUS_STREAM_TIMEOUT:
                break
            time.sleep(interval)

        yield "event: done\ndata: {}\n\n"

    response = Response(stream_with_context(_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


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
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(
            payload,
            PROJECT_MANAGER,
            allow_missing_date=True,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.clean import run_clean  # type: ignore

    try:
        resolved_date, fallback_from = resolve_stage_processing_date(topic_identifier, "clean", date or None)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    response, code = _execute_operation(
        "clean",
        run_clean,
        topic_identifier,
        resolved_date,
        log_context={
            "project": log_project,
            "params": {
                "date": resolved_date,
                "source": "api",
                "topic": display_name,
                "bucket": topic_identifier,
            },
        },
    )
    if fallback_from and response.get("status") == "ok":
        metadata = response.setdefault("context", {})
        metadata["resolved_date"] = resolved_date
        metadata["requested_date"] = fallback_from
    return jsonify(response), code


@app.post("/api/filter")
def filter_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        topic_identifier, date, display_name, log_project = prepare_pipeline_args(
            payload,
            PROJECT_MANAGER,
            allow_missing_date=True,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    from src.filter import run_filter  # type: ignore

    try:
        resolved_date, fallback_from = resolve_stage_processing_date(topic_identifier, "filter", date or None)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    mark_filter_job_running(topic_identifier, resolved_date)
    try:
        _submit_filter_job(
            run_filter,
            topic_identifier=topic_identifier,
            resolved_date=resolved_date,
            log_project=log_project,
            display_name=display_name,
        )
    except Exception as exc:  # pragma: no cover - executor failure
        mark_filter_job_finished(topic_identifier, resolved_date)
        LOGGER.exception("Failed to enqueue filter job")
        return jsonify({"status": "error", "message": str(exc)}), 500

    context: Dict[str, Any] = {}
    if fallback_from:
        context["resolved_date"] = resolved_date
        context["requested_date"] = fallback_from

    response_payload: Dict[str, Any] = {
        "status": "ok",
        "operation": "filter",
        "message": "筛选任务已提交，稍后可在进度面板查看实时状态。",
        "data": {
            "topic": topic_identifier,
            "date": resolved_date,
            "queued": True,
        },
    }
    if context:
        response_payload["context"] = context
    return jsonify(response_payload), 202


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
        dataset_name=display_name,
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

    payload = request.get_json(silent=True) or {}
    include_counts_value = payload.get("include_counts", True)
    include_counts = True
    if isinstance(include_counts_value, bool):
        include_counts = include_counts_value
    elif isinstance(include_counts_value, str):
        include_counts = include_counts_value.strip().lower() not in ("false", "0", "no", "off", "")

    response, code = _execute_operation(
        "query",
        run_query,
        include_counts=include_counts,
        log_context={"project": "GLOBAL", "params": {"source": "api"}},
    )
    return jsonify(response), code


@app.get("/api/fetch/availability")
def fetch_availability_endpoint():
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    if not any([topic, project, dataset_id]):
        return error("Missing required field(s): topic/project/dataset_id")

    payload = {
        "topic": topic,
        "project": project,
        "dataset_id": dataset_id,
    }
    try:
        topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    # 对于远程数据源，可用日期区间查询需要使用真实数据库名，
    # 即请求中提供的 topic；若缺失则退回到展示名/内部标识。
    db_topic = topic or display_name or topic_identifier

    from src.fetch import get_topic_available_date_range  # type: ignore

    availability = get_topic_available_date_range(db_topic)
    return success(
        {
            "data": {
                "topic": display_name or db_topic,
                "bucket": topic_identifier,
                "range": availability,
            }
        }
    )


@app.delete("/api/database/<database_name>")
def delete_database_endpoint(database_name: str):
    """
    删除指定的远程数据库
    """
    db_name = str(database_name or "").strip()
    if not db_name:
        return error("Database name is required")

    # Safety check: prevent deleting system databases (basic list)
    system_dbs = {'information_schema', 'mysql', 'performance_schema', 'sys', 'postgres', 'test', 'phpmyadmin'}
    if db_name.lower() in system_dbs:
        return error(f"Cannot delete system database '{db_name}'", status_code=403)

    from src.utils.io.db import db_manager
    
    # Optional: Check if database exists first? drop_database handles IF EXISTS
    
    success_flag = db_manager.drop_database(db_name)
    if success_flag:
        return success({"message": f"Database '{db_name}' deleted successfully"})
    else:
        return error(f"Failed to delete database '{db_name}'", status_code=500)


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

    topic = str(payload.get("topic") or "").strip()
    project = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    if not any([topic, project, dataset_id]):
        return jsonify({"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}), 400

    try:
        topic_identifier, display_name, log_project, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    # 远程 Fetch 从数据库读取数据，需使用真实库名；
    # 优先使用请求中的 topic，其次展示名，最后回退内部标识。
    db_topic = (topic or "").strip() or display_name or topic_identifier

    from src.fetch import run_fetch  # type: ignore

    response, code = _execute_operation(
        "fetch",
        run_fetch,
        db_topic,
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


@app.get("/api/analyze/history")
def get_analyze_history():
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

    aliases = [alias for alias in (raw_topic, raw_project) if alias]
    records = _collect_analyze_history(topic_identifier, display_name, aliases)
    return success(
        {
            "records": records,
            "topic": display_name,
            "topic_identifier": topic_identifier,
        }
    )


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
        fallback_root: Optional[Path] = None
        if end:
            single_day_folder = start.strip()
            if single_day_folder and single_day_folder != folder_name:
                fallback_root = bucket("analyze", topic_identifier, single_day_folder)
        if fallback_root and fallback_root.exists():
            analyze_root = fallback_root
        else:
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

    ai_summary_path = analyze_root / "ai_summary.json"
    if ai_summary_path.exists():
        try:
            response_payload["ai_summary"] = _load_json_file(ai_summary_path)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to load AI summary file %s", ai_summary_path, exc_info=True)

    return success(response_payload)

@app.post("/api/analysis/topic/bertopic/run")
def run_topic_bertopic_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, error_response = require_fields(payload, "topic", "start_date")
    if not valid:
        return jsonify(error_response), 400

    raw_topic = str(payload.get("topic") or "").strip()
    raw_project = str(payload.get("project") or "").strip()
    raw_dataset_id = str(payload.get("dataset_id") or "").strip()
    try:
        topic_identifier, display_name, log_project, _ = resolve_topic_identifier(
            {
                "topic": raw_topic,
                "project": raw_project,
                "dataset_id": raw_dataset_id,
            },
            PROJECT_MANAGER,
        )
    except ValueError:
        topic_identifier = raw_topic or raw_project
        display_name = raw_topic or raw_project or topic_identifier
        log_project = topic_identifier

    response, code = _execute_operation(
        "topic-bertopic",
        _run_topic_bertopic_api,
        payload,
        log_context={
            "project": log_project or topic_identifier,
            "params": {
                "start_date": str(payload.get("start_date") or "").strip(),
                "end_date": str(payload.get("end_date") or "").strip(),
                "topic": display_name or raw_topic or raw_project,
                "bucket": topic_identifier,
                "source": "api",
            },
        },
    )
    return jsonify(response), code


@app.get("/api/analysis/topic/bertopic/availability")
def check_topic_availability():
    """检查专题的数据可用性范围

    Query parameters:
        topic: 专题名称
        project: 项目名称（可选）
        dataset_id: 数据集ID（可选）
    """
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()

    if not any([topic, project, dataset_id]):
        return error("Missing required field(s): topic/project/dataset_id")

    payload = {
        "topic": topic,
        "project": project,
        "dataset_id": dataset_id,
    }

    try:
        topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc))

    # 对于远程数据源，使用真实数据库名
    db_topic = topic or display_name or topic_identifier

    from src.fetch.data_fetch import get_topic_available_date_range

    # 获取数据可用日期范围
    avail_start, avail_end = get_topic_available_date_range(db_topic)

    # 检查本地缓存情况
    from src.utils.setting.paths import bucket, get_data_root
    data_root = get_data_root() / "projects"
    project_dir = data_root / topic_identifier

    fetch_caches = []
    if project_dir.exists():
        fetch_dir = project_dir / "fetch"
        if fetch_dir.exists():
            for cache_dir in fetch_dir.iterdir():
                if cache_dir.is_dir():
                    # 解析日期范围
                    dir_name = cache_dir.name
                    if "_" in dir_name:
                        start, end = dir_name.split("_", 1)
                    else:
                        start, end = dir_name, dir_name

                    # 检查是否有总体.jsonl文件
                    has_data = (cache_dir / "总体.jsonl").exists()

                    fetch_caches.append({
                        "folder": dir_name,
                        "start": start,
                        "end": end,
                        "has_data": has_data,
                        "path": str(cache_dir.relative_to(get_data_root()))
                    })

            # 按日期排序
            fetch_caches.sort(key=lambda x: (x["start"], x["end"]), reverse=True)

    response = {
        "topic": display_name or db_topic,
        "topic_identifier": topic_identifier,
        "database_range": {
            "start": avail_start,
            "end": avail_end
        },
        "local_caches": fetch_caches,
        "has_cache": len(fetch_caches) > 0
    }

    return success({"data": response})


@app.get("/api/analysis/topic/bertopic/results")
def get_topic_bertopic_results():
    raw_topic = request.args.get("topic")
    raw_project = request.args.get("project")
    raw_dataset_id = request.args.get("dataset_id")

    start = (request.args.get("start") or "").strip()
    if not start:
        return error("Missing required query parameters: start")
    end = (request.args.get("end") or "").strip() or None

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

    folder_name = _compose_analyze_folder(start, end)
    if not folder_name:
        return error("Invalid start date supplied")

    topic_dir = bucket("topic", topic_identifier, folder_name)
    if not topic_dir.exists():
        fallback_dir = bucket("topic", topic_identifier, start)
        if fallback_dir.exists():
            topic_dir = fallback_dir
        else:
            return error("未找到对应的主题分析结果目录", status_code=404)

    file_map = {
        "summary": "1主题统计结果.json",
        "keywords": "2主题关键词.json",
        "coords": "3文档2D坐标.json",
        "llm_clusters": "4大模型再聚类结果.json",
        "llm_keywords": "5大模型主题关键词.json",
    }

    files_payload: Dict[str, Any] = {}
    for key, filename in file_map.items():
        file_path = topic_dir / filename
        if file_path.exists():
            try:
                files_payload[key] = _load_json_file(file_path)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Failed to load topic result file %s", file_path, exc_info=True)
                files_payload[key] = {"error": str(exc)}

    if not files_payload:
        return error("未找到可用的 BERTopic 结果文件", status_code=404)

    response_payload = {
        "topic": display_name,
        "topic_identifier": topic_identifier,
        "range": {
            "start": start,
            "end": end or start,
        },
        "files": files_payload,
    }

    return success({"data": response_payload})


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


@app.get("/api/projects/<string:name>/archives")
def project_archives(name: str):
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    layers_param = str(request.args.get("layers") or "").strip()

    resolution_payload: Dict[str, Any] = {"project": name}
    if dataset_id:
        resolution_payload["dataset_id"] = dataset_id

    try:
        topic_identifier, display_name, log_project, dataset_meta = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    requested_layers = [layer.strip() for layer in layers_param.split(",") if layer.strip()] or None

    archives = collect_project_archives(
        topic_identifier,
        layers=requested_layers,
        dataset_id=str(dataset_meta.get("id") or dataset_id or "").strip() or None,
    )
    latest = {
        layer: (entries[0]["date"] if entries else None)
        for layer, entries in archives.items()
    }

    return jsonify({
        "status": "ok",
        "project": log_project,
        "topic": topic_identifier,
        "display_name": display_name,
        "archives": archives,
        "latest": latest,
    })


@app.delete("/api/projects/<string:name>/archives/<string:layer>/<string:date>")
def delete_project_archive(name: str, layer: str, date: str):
    """
    删除指定项目的存档

    Args:
        name: 项目名称
        layer: 存档层级 (raw, merge, clean)
        date: 存档日期

    Returns:
        JSON响应
    """
    dataset_id = str(request.args.get("dataset_id") or "").strip()

    # 验证层级参数
    valid_layers = ["raw", "merge", "clean"]
    if layer not in valid_layers:
        return jsonify({
            "status": "error",
            "message": f"无效的存档层级: {layer}，支持的层级: {', '.join(valid_layers)}"
        }), 400

    # 验证日期格式
    if not re.match(r'^\d{8}$', date):
        return jsonify({
            "status": "error",
            "message": "无效的日期格式，请使用YYYYMMDD格式，例如: 20241202"
        }), 400

    resolution_payload: Dict[str, Any] = {"project": name}
    if dataset_id:
        resolution_payload["dataset_id"] = dataset_id

    try:
        topic_identifier, _, _, _ = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    try:
        # 检查依赖关系 - 不能删除被后续阶段依赖的存档
        dependency_check = check_archive_dependencies(topic_identifier, layer, date)
        if not dependency_check["can_delete"]:
            return jsonify({
                "status": "error",
                "message": dependency_check["message"],
                "dependent_layers": dependency_check.get("dependent_layers", [])
            }), 409

        # 执行删除操作
        result = delete_archive_directory(topic_identifier, layer, date)

        if result["success"]:
            return jsonify({
                "status": "ok",
                "message": f"成功删除 {layer.upper()} 存档 ({date})",
                "deleted_files": result["deleted_files"],
                "deleted_size": result.get("deleted_size", 0)
            })
        else:
            return jsonify({
                "status": "error",
                "message": result["message"] or f"删除 {layer.upper()} 存档失败"
            }), 500

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return jsonify({
            "status": "error",
            "message": f"删除存档时发生错误: {str(e)}",
            "error_details": error_details if app.debug else None
        }), 500


def check_archive_dependencies(topic_identifier: str, layer: str, date: str) -> Dict[str, Any]:
    """
    检查存档的依赖关系，确认是否可以安全删除

    Args:
        topic_identifier: 专题标识符
        layer: 存档层级
        date: 存档日期

    Returns:
        检查结果字典
    """
    from server_support.archives import collect_project_archives

    # 定义依赖关系：clean依赖merge，merge依赖raw
    dependencies = {
        "raw": ["merge", "clean"],
        "merge": ["clean"]
    }

    # 如果删除clean存档，没有后续依赖，可以直接删除
    if layer == "clean":
        return {"can_delete": True, "message": "Clean存档无后续依赖，可以删除"}

    # 检查是否有后续阶段依赖此存档
    dependent_layers = dependencies.get(layer, [])
    blocking_archives = []

    for dependent_layer in dependent_layers:
        # 获取后续层级的存档
        archives = collect_project_archives(topic_identifier, layers=[dependent_layer])
        dependent_archives = archives.get(dependent_layer, [])

        # 检查是否有基于当前存档日期创建的后续存档
        for archive in dependent_archives:
            # 这里简化检查：如果后续存档日期等于或晚于当前存档日期，可能存在依赖
            # 实际业务中可能需要更精确的依赖关系追踪
            if archive["date"] >= date:
                blocking_archives.append({
                    "layer": dependent_layer,
                    "date": archive["date"],
                    "updated_at": archive.get("updated_at", "")
                })

    if blocking_archives:
        archive_list = ", ".join([
            f"{arch['layer'].upper()}({arch['date']})"
            for arch in blocking_archives
        ])
        return {
            "can_delete": False,
            "message": f"无法删除 {layer.upper()} 存档，存在依赖关系：{archive_list}",
            "dependent_layers": blocking_archives
        }

    return {"can_delete": True, "message": f"{layer.upper()}存档无依赖，可以删除"}


def delete_archive_directory(topic_identifier: str, layer: str, date: str) -> Dict[str, Any]:
    """
    删除指定存档目录

    Args:
        topic_identifier: 专题标识符
        layer: 存档层级 (raw, merge, clean)
        date: 存档日期

    Returns:
        删除结果字典
    """
    import shutil
    import os
    from src.utils.setting.paths import bucket

    try:
        archive_dir = bucket(layer, topic_identifier, date)

        if not os.path.exists(archive_dir):
            return {
                "success": False,
                "message": f"存档目录不存在: {archive_dir}",
                "deleted_files": [],
                "deleted_size": 0
            }

        # 统计要删除的文件
        deleted_files = []
        deleted_size = 0

        for root, _, files in os.walk(archive_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(file_path)
                    deleted_size += file_size
                    relative_path = os.path.relpath(file_path, archive_dir)
                    deleted_files.append(relative_path)
                except OSError:
                    # 忽略无法获取大小的文件
                    pass

        # 执行删除
        shutil.rmtree(archive_dir)

        return {
            "success": True,
            "message": f"成功删除存档目录: {layer}/{date}",
            "deleted_files": deleted_files,
            "deleted_size": deleted_size,
            "deleted_count": len(deleted_files)
        }

    except PermissionError:
        return {
            "success": False,
            "message": "权限不足，无法删除存档目录",
            "deleted_files": [],
            "deleted_size": 0
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"删除存档目录时发生错误: {str(e)}",
            "deleted_files": [],
            "deleted_size": 0
        }


def _build_fetch_cache_response(resolution_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not resolution_payload:
        return {"status": "error", "message": "Missing required field(s): topic/project/dataset_id"}, 400
    try:
        topic_identifier, display_name, log_project, dataset_meta = resolve_topic_identifier(resolution_payload, PROJECT_MANAGER)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}, 400

    dataset_reference = str(
        dataset_meta.get("id") or resolution_payload.get("dataset_id") or ""
    ).strip() or None

    caches = collect_layer_archives(
        topic_identifier,
        "fetch",
        dataset_id=dataset_reference,
    )
    totals = {
        "files": sum(int(entry.get("file_count") or 0) for entry in caches),
        "size": sum(int(entry.get("total_size") or 0) for entry in caches),
    }
    payload = {
        "status": "ok",
        "project": log_project,
        "topic": topic_identifier,
        "display_name": display_name,
        "cache_root": str(DATA_PROJECTS_ROOT / topic_identifier / "fetch"),
        "caches": caches,
        "latest_cache": caches[0] if caches else None,
        "totals": totals,
        "count": len(caches),
    }
    return payload, 200


@app.get("/api/projects/<string:name>/fetch-cache")
def project_fetch_cache(name: str):
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    resolution_payload: Dict[str, Any] = {"project": name}
    if dataset_id:
        resolution_payload["dataset_id"] = dataset_id
    response_payload, status_code = _build_fetch_cache_response(resolution_payload)
    return jsonify(response_payload), status_code


@app.get("/api/fetch/cache")
def fetch_cache_overview():
    topic = str(request.args.get("topic") or "").strip()
    project = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()

    resolution_payload: Dict[str, Any] = {}
    if topic:
        resolution_payload["topic"] = topic
    if project:
        resolution_payload["project"] = project
    if dataset_id:
        resolution_payload["dataset_id"] = dataset_id

    response_payload, status_code = _build_fetch_cache_response(resolution_payload)
    return jsonify(response_payload), status_code


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
    uploads = request.files.getlist("file") or request.files.getlist("files")
    if not uploads:
        single = request.files.get("file")
        if single and getattr(single, "filename", ""):
            uploads = [single]
    uploads = [upload for upload in uploads if getattr(upload, "filename", "")]
    if not uploads:
        return jsonify({"status": "error", "message": "请选择需要上传的表格文件"}), 400

    mapping_hints = parse_column_mapping_from_form(request.form)
    topic_label_hint = normalise_topic_label(request.form.get("topic_label"))

    datasets: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    last_exception = None

    for upload in uploads:
        try:
            dataset = store_uploaded_dataset(
                name,
                upload,
                column_mapping=mapping_hints,
                topic_label=topic_label_hint,
            )
            datasets.append(dataset)
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
        except ValueError as exc:
            failures.append({"filename": upload.filename or "", "message": str(exc)})
            last_exception = exc
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to store dataset for project %s", name)
            failures.append({"filename": upload.filename or "", "message": "数据集保存失败"})
            last_exception = exc
            try:
                PROJECT_MANAGER.log_operation(
                    name,
                    "import_dataset",
                    params={"source": "api", "filename": upload.filename},
                    success=False,
                )
            except Exception:  # pragma: no cover - avoid cascading failures
                LOGGER.debug("Unable to persist failed dataset log for project %s", name, exc_info=True)

    if not datasets and failures:
        message = failures[0].get("message") or "数据集保存失败"
        status_code = 400 if isinstance(last_exception, ValueError) else 500
        return jsonify({"status": "error", "message": message, "errors": failures}), status_code

    payload: Dict[str, Any] = {
        "status": "ok",
        "datasets": datasets,
        "count": len(datasets),
    }
    if datasets:
        payload["dataset"] = datasets[-1]
    if failures:
        payload["errors"] = failures

    status_code = 201 if len(failures) == 0 else 207
    return jsonify(payload), status_code


# RAG Configuration endpoints
@app.route("/api/rag/config", methods=["GET"])
def get_rag_config():
    """Get RAG configuration."""
    try:
        config = load_rag_config()
    except Exception as e:
        LOGGER.exception("Failed to load RAG config; returning defaults")
        try:
            config = get_default_rag_config()
        except Exception:
            config = {}

    try:
        # Mask API keys for security
        masked_config = mask_api_keys(config)
    except Exception as mask_exc:  # pragma: no cover - defensive masking
        LOGGER.exception("Failed to mask RAG config: %s", mask_exc)
        masked_config = config if isinstance(config, dict) else {}

    return success({"data": masked_config})


@app.route("/api/rag/config", methods=["POST"])
def save_rag_config():
    """Save RAG configuration."""
    try:
        payload = request.get_json(silent=True) or {}
        config = payload.get("config") if isinstance(payload, dict) and "config" in payload else payload

        if not isinstance(config, dict):
            return error("Invalid RAG configuration payload", 400)

        # Validate configuration
        is_valid, errors = validate_rag_config(config)
        if not is_valid:
            return jsonify({"status": "error", "message": "Invalid RAG configuration", "errors": errors}), 400

        persist_rag_config(config)
        return success({"message": "RAG configuration saved successfully"})
    except Exception as e:
        LOGGER.error(f"Failed to save RAG config: {e}")
        return error("Failed to save RAG configuration", 500)


@app.route("/api/rag/test", methods=["POST"])
def test_rag_config():
    """Test RAG configuration."""
    try:
        payload = request.get_json(silent=True) or {}
        valid, error_response = require_fields(payload, "query")
        if not valid:
            return jsonify(error_response), 400

        query = payload.get("query")

        # TODO: Implement actual RAG test
        # For now, just return a mock response
        results = [
            {
                "id": "test_1",
                "text": f"This is a test result for query: {query}",
                "score": 0.95,
                "metadata": {"source": "test"}
            }
        ]

        return jsonify({"status": "ok", "data": {"results": results, "total": len(results)}})
    except Exception as e:
        LOGGER.error(f"Failed to test RAG: {e}")
        return error(message="Failed to test RAG configuration")


@app.route("/api/rag/embedding/models", methods=["GET"])
def list_embedding_models():
    """List available embedding models."""
    try:
        models = {
            "huggingface": [
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "sentence-transformers/all-MiniLM-L6-v2",
                "sentence-transformers/all-mpnet-base-v2",
                "shibing624/text2vec-base-chinese",
            ],
            "openai": [
                "text-embedding-ada-002",
                "text-embedding-3-small",
                "text-embedding-3-large",
            ]
        }
        return success({"data": models})
    except Exception as e:
        LOGGER.error(f"Failed to list embedding models: {e}")
        return error(message="Failed to list embedding models")


@app.route("/api/settings/rag/prompts", methods=["GET"])
def get_router_prompts():
    """Get RouterRAG prompt configuration for a specific topic."""
    try:
        topic = request.args.get("topic", "")
        reset = request.args.get("reset", "false").lower() == "true"
        
        if not topic:
            return error(message="Missing 'topic' parameter")
        
        if reset:
            from server_support.router_prompts.utils import DEFAULT_ROUTER_PROMPT_CONFIG
            return success({"data": DEFAULT_ROUTER_PROMPT_CONFIG})
        
        # Load the prompt configuration for the topic
        prompts = load_router_prompt_config(topic)
        
        return success({"data": prompts})
    except Exception as e:
        LOGGER.error(f"Failed to load router prompts for topic '{topic}': {e}")
        return error(message=f"Failed to load prompts: {str(e)}")


@app.route("/api/settings/rag/prompts", methods=["POST"])
def save_router_prompts():
    """Save RouterRAG prompt configuration for a specific topic."""
    try:
        payload = request.get_json(silent=True) or {}
        topic = payload.get("topic", "")
        prompts = payload.get("prompts", {})
        
        if not topic:
            return error(message="Missing 'topic' in request body")
        
        if not prompts:
            return error(message="Missing 'prompts' in request body")
        
        # Persist the prompt configuration
        persist_router_prompt_config(topic, prompts)
        
        return success({"message": f"Prompts saved successfully for topic '{topic}'"})
    except Exception as e:
        LOGGER.error(f"Failed to save router prompts: {e}")
        return error(message=f"Failed to save prompts: {str(e)}")


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
        "/api/projects/<name>/fetch-cache",
        "/api/fetch/cache",
        "/api/rag/config",
        "/api/rag/test",
        "/api/rag/embedding/models",
        "/api/settings/rag/prompts",
    ]})


def main() -> None:
    host, port = _resolve_runtime_binding()
    LOGGER.info("Starting OpinionSystem backend on %s:%s (set OPINION_BACKEND_PORT to override)", host, port)
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
                "Please choose a different port via OPINION_BACKEND_PORT or free the existing one.",
                host,
                port,
            )
            raise SystemExit(1) from exc
        raise


@app.get("/api/analysis/topic/bertopic/topics")
def list_topic_buckets():
    """获取所有可用的专题 Bucket 列表

    Query parameters:
        only_with_results: 如果为 true，只返回有 BERTopic 分析结果的专题（默认: false）
        only_with_data: 如果为 true，只返回有可用数据的专题（默认: false）
    """
    try:
        from src.utils.setting.paths import get_data_root
        from src.query import run_query  # 使用query模块获取数据库专题列表
        data_root = get_data_root()
        projects_dir = data_root / "projects"

        only_with_results = request.args.get("only_with_results", "false").lower() == "true"
        only_with_data = request.args.get("only_with_data", "false").lower() == "true"

        # 优先从数据库获取专题列表
        topics = []

        if only_with_data:
            # 从远程数据库获取有数据的专题列表
            try:
                response, _ = _execute_operation(
                    "query",
                    run_query,
                    include_counts=True,
                    log_context={"project": "GLOBAL", "params": {"source": "api"}}
                )

                if response.get("status") == "ok":
                    databases = response.get("data", {}).get("databases", [])
                    for db in databases:
                        db_name = db.get("name", "").strip()
                        if db_name:
                            # 检查本地是否有对应的项目目录
                            project_dir = projects_dir / db_name if projects_dir.exists() else None
                            has_topic = False

                            if project_dir and project_dir.exists():
                                topic_dir = project_dir / "topic"
                                has_topic = topic_dir.exists() and topic_dir.is_dir()

                            # 过滤条件
                            if not only_with_results or has_topic:
                                topics.append({
                                    "bucket": db_name,
                                    "name": db_name,
                                    "display_name": db.get("display_name", db_name),
                                    "has_bertopic_results": has_topic,
                                    "source": "database"
                                })

            except Exception as db_exc:
                LOGGER.warning("Failed to get topics from database: %s", db_exc)
                # 降级到本地文件系统扫描

        # 如果没有从数据库获取到数据，或不需要只从数据库获取
        if not topics or not only_with_data:
            # 从本地文件系统扫描
            if projects_dir.exists():
                all_items = list(projects_dir.iterdir())
                LOGGER.info("Found %d items in projects directory", len(all_items))

                for item in sorted(all_items):
                    if item.is_dir() and not item.name.startswith('.'):
                        # 检查是否有 topic 目录
                        topic_dir = item / "topic"
                        has_topic = topic_dir.exists() and topic_dir.is_dir()

                        # 检查是否有fetch数据（表示有可用数据）
                        has_data = False
                        fetch_dir = item / "fetch"
                        if fetch_dir.exists():
                            # 检查是否有任何fetch子目录
                            has_data = any(fetch_dir.iterdir())

                        # 过滤条件
                        if not only_with_data or has_data:
                            if not only_with_results or has_topic:
                                topics.append({
                                    "bucket": item.name,
                                    "name": item.name,
                                    "display_name": item.name,
                                    "has_bertopic_results": has_topic,
                                    "source": "local"
                                })

        # 去重（优先保留数据库来源的记录）
        seen = set()
        unique_topics = []
        for topic in topics:
            key = topic["bucket"]
            if key not in seen:
                seen.add(key)
                unique_topics.append(topic)
            elif topic.get("source") == "database":
                # 如果已经有记录，但当前是数据库来源，更新记录
                for i, existing in enumerate(unique_topics):
                    if existing["bucket"] == key:
                        unique_topics[i] = topic
                        break

        LOGGER.info("Returning %d topics", len(unique_topics))
        return success({
            "topics": unique_topics,
            "data_root": str(data_root),
            "projects_dir": str(projects_dir),
            "source": "database" if any(t.get("source") == "database" for t in unique_topics) else "local"
        })
    except Exception as exc:
        LOGGER.exception("Failed to list topic buckets")
        return error(f"获取专题列表失败: {str(exc)}")


# ====== RAG (Retrieval-Augmented Generation) API Endpoints ======

@app.get("/api/rag/topics")
def get_rag_topics():
    """获取可用的RAG专题列表"""
    try:
        project = str(request.args.get("project") or "").strip()
        project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
        project_bucket = project_bucket or project
        tagrag_topics: List[str] = []
        router_topics: List[str] = []

        if project_bucket:
            tagrag_topics = list_project_tagrag_topics(project_bucket)
            router_topics = list_project_routerrag_topics(project_bucket)
            return success({
                "data": {
                    "tagrag_topics": sorted({t.strip() for t in tagrag_topics if str(t).strip()}),
                    "router_topics": sorted({t.strip() for t in router_topics if str(t).strip()}),
                }
            })

        # No fallback to src/utils/rag when project is not provided.

        return success({
            "data": {
                "tagrag_topics": sorted({t.strip() for t in tagrag_topics if str(t).strip()}),
                "router_topics": sorted({t.strip() for t in router_topics if str(t).strip()})
            }
        })
    except Exception as exc:
        LOGGER.exception("Failed to get RAG topics")
        return error(f"获取RAG专题列表失败: {str(exc)}")


@app.get("/api/rag/cache/status")
def get_rag_cache_status():
    project = str(request.args.get("project") or "").strip()
    topic = str(request.args.get("topic") or "").strip()
    rag_type = str(request.args.get("type") or "").strip() or "tagrag"

    if not project or not topic:
        return error("Missing required field(s): project, topic")

    project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
    project_bucket = project_bucket or project

    status = get_rag_build_status(project_bucket, rag_type, topic)
    return success({"data": status})


@app.post("/api/rag/build")
def rag_build():
    payload = request.get_json(silent=True) or {}
    topic = str(payload.get("topic") or "").strip()
    project = str(payload.get("project") or "").strip()
    rag_type = str(payload.get("type") or "").strip() or "tagrag"
    start = str(payload.get("start") or "").strip() or None
    end = str(payload.get("end") or "").strip() or None

    if not topic or not project:
        return error("Missing required field(s): project, topic")

    project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
    project_bucket = project_bucket or project

    status = start_rag_build(
        project_bucket,
        rag_type,
        topic,
        db_topic=topic,
        start=start,
        end=end,
    )
    return success({"data": status})


@app.post("/api/rag/tagrag/retrieve")
def tagrag_retrieve():
    """TagRAG检索接口"""
    try:
        payload = request.get_json(silent=True) or {}

        # Validate required fields
        query = payload.get("query", "").strip()
        topic = payload.get("topic", "").strip()
        project = str(payload.get("project") or "").strip()
        project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
        project_bucket = project_bucket or project
        top_k = payload.get("top_k", 10)

        if not query:
            return error("Missing required field: query")
        if not topic:
            return error("Missing required field: topic")

        if project_bucket and not ensure_rag_ready(project_bucket, "tagrag", topic):
            status = start_rag_build(project_bucket, "tagrag", topic, db_topic=topic)
            return jsonify({
                "status": "building",
                "message": "正在准备检索资料，请稍后再试",
                "data": status,
            }), 202

        # Import TagRAG retrieval
        from src.utils.rag.tagrag.tag_retrieve_data import retrieve_documents

        db_path = None
        if project_bucket:
            db_path = ensure_tagrag_db(topic, project_bucket)

        # Retrieve documents
        results = retrieve_documents(
            query=query,
            topic=topic,
            top_k=top_k,
            threshold=payload.get("threshold", 0.0),
            db_path=str(db_path) if db_path else None,
        )

        return success({"data": {"results": results, "total": len(results)}})
    except Exception as exc:
        LOGGER.exception("Failed to retrieve TagRAG documents")
        return error(f"TagRAG检索失败: {str(exc)}")


@app.post("/api/rag/routerrag/retrieve")
def routerrag_retrieve():
    """RouterRAG检索接口"""
    try:
        payload = request.get_json(silent=True) or {}

        # Validate required fields
        query = payload.get("query", "").strip()
        topic = payload.get("topic", "").strip()
        project = str(payload.get("project") or "").strip()
        project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
        project_bucket = project_bucket or project
        top_k = payload.get("top_k", 10)

        if not query:
            return error("Missing required field: query")
        if not topic:
            return error("Missing required field: topic")

        if project_bucket and not ensure_rag_ready(project_bucket, "routerrag", topic):
            status = start_rag_build(project_bucket, "routerrag", topic, db_topic=topic)
            return jsonify({
                "status": "building",
                "message": "正在准备检索资料，请稍后再试",
                "data": status,
            }), 202

        # Import RouterRAG retrieval
        from src.utils.rag.ragrouter.router_retrieve_data import retrieve_documents

        base_path = None
        if project_bucket:
            base_path = ensure_routerrag_db(topic, project_bucket)

        # Retrieve documents
        mode = payload.get("mode", "normalrag")
        results = retrieve_documents(
            query=query,
            topic=topic,
            top_k=top_k,
            threshold=payload.get("threshold", 0.0),
            mode=mode,
            db_base_path=base_path,
        )

        if isinstance(results, dict):
            return success({"data": results})
        return success({"data": {"results": results, "total": len(results)}})
    except Exception as exc:
        LOGGER.exception("Failed to retrieve RouterRAG documents")
        return error(f"RouterRAG检索失败: {str(exc)}")


@app.post("/api/rag/universal/retrieve")
def universal_rag_retrieve():
    """通用RAG检索接口（支持多种检索策略）"""
    try:
        payload = request.get_json(silent=True) or {}

        # Validate required fields
        query = payload.get("query", "").strip()
        topic = payload.get("topic", "").strip()
        rag_type = payload.get("rag_type", "tagrag")  # tagrag, routerrag, hybrid
        project = str(payload.get("project") or "").strip()
        project_bucket = PROJECT_MANAGER.resolve_identifier(project) if project else None
        project_bucket = project_bucket or project
        top_k = payload.get("top_k", 10)

        if not query:
            return error("Missing required field: query")
        if not topic:
            return error("Missing required field: topic")

        results = []

        if rag_type == "tagrag":
            from src.utils.rag.tagrag.tag_retrieve_data import retrieve_documents
            if project_bucket and not ensure_rag_ready(project_bucket, "tagrag", topic):
                status = start_rag_build(project_bucket, "tagrag", topic, db_topic=topic)
                return jsonify({
                    "status": "building",
                    "message": "正在准备检索资料，请稍后再试",
                    "data": status,
                }), 202
            db_path = ensure_tagrag_db(topic, project_bucket) if project_bucket else None
            results = retrieve_documents(query=query, topic=topic, top_k=top_k, db_path=str(db_path) if db_path else None)

        elif rag_type == "routerrag":
            from src.utils.rag.ragrouter.router_retrieve_data import retrieve_documents
            if project_bucket and not ensure_rag_ready(project_bucket, "routerrag", topic):
                status = start_rag_build(project_bucket, "routerrag", topic, db_topic=topic)
                return jsonify({
                    "status": "building",
                    "message": "正在准备检索资料，请稍后再试",
                    "data": status,
                }), 202
            base_path = ensure_routerrag_db(topic, project_bucket) if project_bucket else None
            results = retrieve_documents(query=query, topic=topic, top_k=top_k, db_base_path=base_path)

        elif rag_type == "hybrid":
            # Combine results from both systems
            try:
                from src.utils.rag.tagrag.tag_retrieve_data import retrieve_documents as tagrag_retrieve
                from src.utils.rag.ragrouter.router_retrieve_data import retrieve_documents as router_retrieve

                if project_bucket:
                    if not ensure_rag_ready(project_bucket, "tagrag", topic):
                        status = start_rag_build(project_bucket, "tagrag", topic, db_topic=topic)
                        return jsonify({
                            "status": "building",
                            "message": "正在准备检索资料，请稍后再试",
                            "data": status,
                        }), 202
                    if not ensure_rag_ready(project_bucket, "routerrag", topic):
                        status = start_rag_build(project_bucket, "routerrag", topic, db_topic=topic)
                        return jsonify({
                            "status": "building",
                            "message": "正在准备检索资料，请稍后再试",
                            "data": status,
                        }), 202

                tag_db_path = ensure_tagrag_db(topic, project_bucket) if project_bucket else None
                router_base_path = ensure_routerrag_db(topic, project_bucket) if project_bucket else None
                tagrag_results = tagrag_retrieve(query=query, topic=topic, top_k=top_k // 2, db_path=str(tag_db_path) if tag_db_path else None)
                router_payload = router_retrieve(query=query, topic=topic, top_k=top_k // 2, db_base_path=router_base_path)
                
                router_results = router_payload.get("results", []) if isinstance(router_payload, dict) else router_payload
                summary = router_payload.get("summary", "") if isinstance(router_payload, dict) else ""

                # Combine and deduplicate
                results = tagrag_results + router_results
                results = results[:top_k]  # Limit to top_k
                
                if summary:
                    # If we have a summary, return the dict format
                    results = {"results": results, "total": len(results), "summary": summary}
            except Exception as e:
                LOGGER.warning(f"Hybrid retrieval failed, falling back to TagRAG: {e}")
                from src.utils.rag.tagrag.tag_retrieve_data import retrieve_documents
                results = retrieve_documents(query=query, topic=topic, top_k=top_k)

        if isinstance(results, dict):
            if "rag_type" not in results:
                results["rag_type"] = rag_type
            return success({"data": results})
        return success({"data": {"results": results, "total": len(results), "rag_type": rag_type}})
    except Exception as exc:
        LOGGER.exception("Failed to retrieve documents")
        return error(f"检索失败: {str(exc)}")


@app.post("/api/rag/export")
def export_rag_data():
    """导出RAG数据格式"""
    try:
        payload = request.get_json(silent=True) or {}

        # Validate required fields
        input_path = payload.get("input_path", "").strip()
        output_path = payload.get("output_path", "").strip()
        topic = payload.get("topic", "").strip()

        if not input_path or not output_path:
            return error("Missing required fields: input_path, output_path")

        # Import converter
        from src.rag.cli.export_tagrag import export_tagrag_texts
        from pathlib import Path

        # Run export
        export_tagrag_texts(
            input_path=Path(input_path),
            output_path=Path(output_path),
            topic=topic or "export",
            chunk_size=payload.get("chunk_size", 3),
            chunk_strategy=payload.get("chunk_strategy", "count")
        )

        return success({"message": "导出成功", "output_path": output_path})
    except Exception as exc:
        LOGGER.exception("Failed to export RAG data")
        return error(f"导出失败: {str(exc)}")


if __name__ == "__main__":
    main()
