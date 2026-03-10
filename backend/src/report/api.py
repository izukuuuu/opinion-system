"""
报告生成 API。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

from server_support import error, resolve_topic_identifier, success
from server_support.topic_context import resolve_context, TopicContext
from server_support.archive_locator import ArchiveLocator
from src.project import get_project_manager

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

    payload = {}
    if raw_topic:
        payload["topic"] = raw_topic
    if raw_project:
        payload["project"] = raw_project
    if raw_dataset_id:
        payload["dataset_id"] = raw_dataset_id

    try:
        ctx = resolve_context(payload, PROJECT_MANAGER)
    except ValueError:
        if not raw_topic:
            return error("Missing required field(s): topic or project")
        ctx = TopicContext(
            identifier=raw_topic,
            display_name=raw_topic,
            aliases=[a for a in (raw_topic, raw_project) if a],
        )

    locator = ArchiveLocator(ctx)
    records = locator.list_history("reports")
    return success(
        {
            "records": records,
            "topic": ctx.display_name,
            "topic_identifier": ctx.identifier,
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
