from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from flask import Flask, Response, jsonify, request, send_file, stream_with_context

from server_support import (
    build_settings_backup,
    restore_settings_backup,
    load_databases_config,
    persist_databases_config,
    load_llm_config,
    persist_llm_config,
    error,
    success,
    resolve_topic_identifier,
)
from src.netinsight import load_netinsight_config  # type: ignore
from src.netinsight import persist_netinsight_config  # type: ignore
from src.netinsight import summarise_netinsight_credentials  # type: ignore

LOGGER = logging.getLogger(__name__)

def _summarise_api_key(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {"configured": False, "last_four": ""}
    last_four = value[-4:] if len(value) >= 4 else value
    return {"configured": True, "last_four": last_four}

def register_settings_endpoints(app: Flask, project_manager: Any):
    
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

    @app.get("/api/settings/llm/report-runtime")
    def get_report_runtime_settings():
        config = load_llm_config()
        langchain = config.get("langchain") if isinstance(config.get("langchain"), dict) else {}
        report_runtime = langchain.get("report_runtime") if isinstance(langchain.get("report_runtime"), dict) else {}
        credentials = config.get("credentials") if isinstance(config.get("credentials"), dict) else {}
        report_key = credentials.get("report_api_key")
        payload = {
            "provider": str(report_runtime.get("provider") or langchain.get("provider") or "qwen").strip() or "qwen",
            "model": str(report_runtime.get("model") or langchain.get("report_model") or langchain.get("model") or "").strip(),
            "base_url": str(report_runtime.get("base_url") or langchain.get("base_url") or "").strip(),
            "temperature": report_runtime.get("temperature", langchain.get("temperature", 0.3)),
            "max_tokens": report_runtime.get("max_tokens", langchain.get("report_max_tokens", langchain.get("max_tokens", 3000))),
            "timeout": report_runtime.get("timeout", langchain.get("report_timeout", langchain.get("timeout", 120.0))),
            "max_retries": report_runtime.get("max_retries", langchain.get("max_retries", 2)),
            "api_key": _summarise_api_key(report_key if isinstance(report_key, str) else None),
        }
        return success({"data": payload})

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
        _update_text_field("report_api_key")

        config["credentials"] = credentials
        persist_llm_config(config)

        return success({
            "data": {
                "qwen": _summarise_api_key(credentials.get("qwen_api_key") or credentials.get("dashscope_api_key")),
                "openai": _summarise_api_key(credentials.get("openai_api_key") or credentials.get("opinion_openai_api_key")),
                "openai_base_url": str(credentials.get("openai_base_url") or ""),
            }
        })

    @app.put("/api/settings/llm/report-runtime")
    def update_report_runtime_settings():
        payload = request.get_json(silent=True) or {}
        config = load_llm_config()
        langchain = config.get("langchain", {})
        if not isinstance(langchain, dict):
            langchain = {}
        report_runtime = langchain.get("report_runtime", {})
        if not isinstance(report_runtime, dict):
            report_runtime = {}

        for field in ["provider", "model", "base_url"]:
            if field in payload:
                report_runtime[field] = str(payload.get(field) or "").strip()

        if "temperature" in payload:
            try:
                report_runtime["temperature"] = float(payload["temperature"])
            except (TypeError, ValueError):
                return error("Field 'temperature' must be a number")

        for field in ["max_tokens", "max_retries"]:
            if field in payload:
                try:
                    report_runtime[field] = int(payload[field])
                except (TypeError, ValueError):
                    return error(f"Field '{field}' must be an integer")

        if "timeout" in payload:
            try:
                report_runtime["timeout"] = float(payload["timeout"])
            except (TypeError, ValueError):
                return error("Field 'timeout' must be a number")

        langchain["report_runtime"] = report_runtime
        config["langchain"] = langchain

        credentials = config.get("credentials", {})
        if not isinstance(credentials, dict):
            credentials = {}
        if payload.get("clear_api_key"):
            credentials.pop("report_api_key", None)
        elif "api_key" in payload:
            api_key = str(payload.get("api_key") or "").strip()
            if api_key:
                credentials["report_api_key"] = api_key
            else:
                credentials.pop("report_api_key", None)
        config["credentials"] = credentials

        persist_llm_config(config)
        saved = load_llm_config()
        saved_langchain = saved.get("langchain") if isinstance(saved.get("langchain"), dict) else {}
        saved_runtime = saved_langchain.get("report_runtime") if isinstance(saved_langchain.get("report_runtime"), dict) else {}
        saved_credentials = saved.get("credentials") if isinstance(saved.get("credentials"), dict) else {}
        return success(
            {
                "data": {
                    "provider": str(saved_runtime.get("provider") or saved_langchain.get("provider") or "qwen").strip() or "qwen",
                    "model": str(saved_runtime.get("model") or saved_langchain.get("report_model") or saved_langchain.get("model") or "").strip(),
                    "base_url": str(saved_runtime.get("base_url") or saved_langchain.get("base_url") or "").strip(),
                    "temperature": saved_runtime.get("temperature", saved_langchain.get("temperature", 0.3)),
                    "max_tokens": saved_runtime.get("max_tokens", saved_langchain.get("report_max_tokens", saved_langchain.get("max_tokens", 3000))),
                    "timeout": saved_runtime.get("timeout", saved_langchain.get("report_timeout", saved_langchain.get("timeout", 120.0))),
                    "max_retries": saved_runtime.get("max_retries", saved_langchain.get("max_retries", 2)),
                    "api_key": _summarise_api_key(saved_credentials.get("report_api_key") if isinstance(saved_credentials.get("report_api_key"), str) else None),
                }
            }
        )

    @app.put("/api/settings/llm/filter")
    def update_llm_filter():
        payload = request.get_json(silent=True) or {}
        config = load_llm_config()
        filter_llm = config.get("filter_llm", {})

        for field in ["provider", "model", "base_url"]:
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

    @app.put("/api/settings/llm/langchain")
    def update_llm_langchain():
        payload = request.get_json(silent=True) or {}
        config = load_llm_config()
        langchain = config.get("langchain", {})
        if not isinstance(langchain, dict):
            langchain = {}

        for field in ["provider", "model", "base_url", "report_model", "analyze_summary_model"]:
            if field in payload:
                langchain[field] = str(payload[field]).strip()

        if "temperature" in payload:
            try:
                langchain["temperature"] = float(payload["temperature"])
            except (TypeError, ValueError):
                return error("Field 'temperature' must be a number")

        for field in ["max_tokens", "max_retries"]:
            if field in payload:
                try:
                    langchain[field] = int(payload[field])
                except (TypeError, ValueError):
                    return error(f"Field '{field}' must be an integer")

        if "timeout" in payload:
            try:
                langchain["timeout"] = float(payload["timeout"])
            except (TypeError, ValueError):
                return error("Field 'timeout' must be a number")

        langchain.pop("enabled", None)
        config["langchain"] = langchain
        persist_llm_config(config)
        return success({"data": langchain})

    @app.get("/api/settings/netinsight")
    def get_netinsight_settings():
        config = load_netinsight_config()
        runtime = dict(config.get("runtime", {}))
        planner = dict(config.get("planner", {}))
        return success(
            {
                "data": {
                    "credentials": summarise_netinsight_credentials(),
                    "runtime": runtime,
                    "planner": planner,
                }
            }
        )

    @app.put("/api/settings/netinsight")
    def update_netinsight_settings():
        payload = request.get_json(silent=True) or {}
        config = load_netinsight_config()

        credentials = dict(config.get("credentials", {}))
        runtime = dict(config.get("runtime", {}))
        planner = dict(config.get("planner", {}))

        if "user" in payload:
            credentials["user"] = str(payload.get("user") or "").strip()
        if payload.get("clear_password"):
            credentials["pass"] = ""
        elif "password" in payload:
            password = str(payload.get("password") or "").strip()
            if password:
                credentials["pass"] = password

        for field in ("headless", "no_proxy"):
            if field in payload:
                value = payload.get(field)
                if isinstance(value, bool):
                    runtime[field] = value
                elif isinstance(value, str):
                    runtime[field] = value.strip().lower() in {"1", "true", "yes", "on"}
                else:
                    runtime[field] = bool(value)

        for field in ("login_timeout_ms", "worker_idle_seconds", "page_size"):
            if field in payload:
                try:
                    runtime[field] = int(payload.get(field))
                except (TypeError, ValueError):
                    return error(f"Field '{field}' must be an integer")

        for field in ("sort", "info_type", "browser_channel"):
            if field in payload:
                runtime[field] = str(payload.get(field) or "").strip()

        for field in ("default_days", "default_total_limit"):
            if field in payload:
                try:
                    planner[field] = int(payload.get(field))
                except (TypeError, ValueError):
                    return error(f"Field '{field}' must be an integer")

        if "default_platforms" in payload:
            value = payload.get("default_platforms")
            if not isinstance(value, list):
                return error("Field 'default_platforms' must be a list")
            planner["default_platforms"] = [str(item).strip() for item in value if str(item).strip()]

        config["credentials"] = credentials
        config["runtime"] = runtime
        config["planner"] = planner
        persist_netinsight_config(config)

        saved = load_netinsight_config()
        return success(
            {
                "data": {
                    "credentials": summarise_netinsight_credentials(),
                    "runtime": dict(saved.get("runtime", {})),
                    "planner": dict(saved.get("planner", {})),
                }
            }
        )

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
