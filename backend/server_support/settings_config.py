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
