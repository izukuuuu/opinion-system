"""
报告生成 API。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

from server_support import error, resolve_topic_identifier, success
from src.project import get_project_manager
from src.utils.setting.paths import _normalise_topic, get_data_root

from .structured_service import generate_report_payload


PROJECT_MANAGER = get_project_manager()
report_bp = Blueprint("report", __name__)


def _resolve_topic(topic_param: str, project_param: str, dataset_id: str) -> Tuple[str, str]:
    if not topic_param and not project_param:
        raise ValueError("Missing required field(s): topic or project")

    payload = {}
    if topic_param:
        payload["topic"] = topic_param
    if project_param:
        payload["project"] = project_param
    if dataset_id:
        payload["dataset_id"] = dataset_id

    topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    return topic_identifier, display_name


def _split_report_folder(folder: str) -> Tuple[str, str]:
    folder_text = str(folder or "").strip()
    if not folder_text:
        return "", ""
    if "_" in folder_text:
        start, end = folder_text.split("_", 1)
        start_text = start.strip()
        end_text = end.strip() or start_text
        return start_text, end_text
    return folder_text, folder_text


def _normalise_report_record(record: Dict[str, Any], defaults: Dict[str, str]) -> Optional[Dict[str, Any]]:
    folder = str(record.get("folder") or "").strip()
    start, end = _split_report_folder(folder)
    if not start:
        return None
    topic = str(record.get("topic") or defaults.get("topic") or "").strip()
    topic_identifier = str(record.get("topic_identifier") or defaults.get("topic_identifier") or "").strip()
    if not topic:
        return None
    return {
        "id": str(record.get("id") or f"{topic_identifier}:{folder}"),
        "topic": topic,
        "topic_identifier": topic_identifier or topic,
        "start": start,
        "end": end,
        "folder": folder or (f"{start}_{end}" if end and end != start else start),
        "updated_at": str(record.get("updated_at") or ""),
    }


def _collect_report_history(
    topic_identifier: str,
    topic_label: str,
    aliases: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    data_root = get_data_root() / "projects"
    data_root.mkdir(parents=True, exist_ok=True)

    candidate_names: List[str] = [topic_identifier]
    if aliases:
        candidate_names.extend([str(alias or "").strip() for alias in aliases if str(alias or "").strip()])
    candidate_names.extend([_normalise_topic(name) for name in candidate_names if name])

    seen_dirs: set[str] = set()
    records: List[Dict[str, Any]] = []

    for candidate in candidate_names:
        cleaned = str(candidate or "").strip()
        if not cleaned or cleaned in seen_dirs:
            continue
        seen_dirs.add(cleaned)

        report_root = data_root / cleaned / "reports"
        if not report_root.exists():
            continue

        for entry in report_root.iterdir():
            if not entry.is_dir():
                continue
            start, end = _split_report_folder(entry.name)
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
    normalized: List[Dict[str, Any]] = []
    defaults = {"topic": topic_label, "topic_identifier": topic_identifier}
    for item in records:
        item.pop("_updated_ts", None)
        normalized_item = _normalise_report_record(item, defaults)
        if normalized_item:
            normalized.append(normalized_item)
    return normalized


@report_bp.get("")
def get_report_payload():
    topic_param = str(request.args.get("topic") or "").strip()
    project_param = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    start = str(request.args.get("start") or "").strip()
    end = str(request.args.get("end") or "").strip() or None

    if not start:
        return error("Missing required field(s): start")

    try:
        topic_identifier, display_name = _resolve_topic(topic_param, project_param, dataset_id)
    except ValueError as exc:
        return error(str(exc))

    try:
        payload = generate_report_payload(
            topic_identifier,
            start,
            end,
            topic_label=display_name,
            regenerate=False,
        )
    except ValueError as exc:
        return error(str(exc), status_code=404)
    except Exception as exc:
        return error(f"报告生成失败: {str(exc)}", status_code=500)

    return success({"data": payload})


@report_bp.get("/history")
def get_report_history():
    raw_topic = str(request.args.get("topic") or "").strip()
    raw_project = str(request.args.get("project") or "").strip()
    raw_dataset_id = str(request.args.get("dataset_id") or "").strip()

    try:
        topic_identifier, display_name = _resolve_topic(raw_topic, raw_project, raw_dataset_id)
    except ValueError:
        if not raw_topic:
            return error("Missing required field(s): topic or project")
        topic_identifier = raw_topic
        display_name = raw_topic

    aliases = [alias for alias in (raw_topic, raw_project) if alias]
    records = _collect_report_history(topic_identifier, display_name, aliases=aliases)
    return success(
        {
            "records": records,
            "topic": display_name,
            "topic_identifier": topic_identifier,
        }
    )


@report_bp.post("/regenerate")
def regenerate_report_payload():
    payload = request.get_json(silent=True) or {}
    topic_param = str(payload.get("topic") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip() or None

    if not start:
        return jsonify({"status": "error", "message": "Missing required field(s): start"}), 400

    try:
        topic_identifier, display_name = _resolve_topic(topic_param, project_param, dataset_id)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    try:
        report_payload = generate_report_payload(
            topic_identifier,
            start,
            end,
            topic_label=display_name,
            regenerate=True,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except Exception as exc:
        return jsonify({"status": "error", "message": f"报告重生成失败: {str(exc)}"}), 500

    return jsonify({"status": "ok", "data": report_payload})
