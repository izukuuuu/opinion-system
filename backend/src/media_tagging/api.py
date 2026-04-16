from __future__ import annotations

from typing import Any, Dict, List

from flask import Blueprint, request

from server_support import error, success
from server_support.archive_locator import ArchiveLocator
from server_support.responses import require_fields
from server_support.topic_context import TopicContext, resolve_context
from src.project import get_project_manager

PROJECT_MANAGER = get_project_manager()

media_tagging_bp = Blueprint("media_tagging", __name__)


def _resolve_context_from_request() -> TopicContext:
    payload_json = request.get_json(silent=True) if request.is_json else {}
    payload = {
        "topic": request.args.get("topic") or (payload_json.get("topic") if isinstance(payload_json, dict) else ""),
        "project": request.args.get("project") or (payload_json.get("project") if isinstance(payload_json, dict) else ""),
        "dataset_id": request.args.get("dataset_id") or (payload_json.get("dataset_id") if isinstance(payload_json, dict) else ""),
    }
    try:
        return resolve_context(payload, PROJECT_MANAGER)
    except ValueError:
        raw_topic = str(payload.get("topic") or payload.get("project") or "").strip()
        if not raw_topic:
            raise
        return TopicContext(identifier=raw_topic, display_name=raw_topic, aliases=[raw_topic])


@media_tagging_bp.route("/run-async", methods=["POST"])
def run_media_tagging_async():
    from server_support.media_tagging import create_or_reuse_task, ensure_worker_running

    payload = request.get_json(silent=True) or {}
    valid, err = require_fields(payload, "start")
    if not valid:
        return error(err.get("message") or "Missing required field(s): start", status_code=400)
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip() or None
    force = bool(payload.get("force", False))

    try:
        ctx = resolve_context(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc), status_code=400)

    try:
        task = create_or_reuse_task(ctx.identifier, start, end_date=end, force=force)
        ensure_worker_running()
        return success({"task": task, "message": "任务已创建"})
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/tasks", methods=["GET"])
def list_media_tagging_tasks():
    from server_support.media_tagging import list_tasks

    start = str(request.args.get("start") or "").strip()
    end = str(request.args.get("end") or "").strip() or None
    if not start:
        return error("Missing required query parameter: start", status_code=400)

    try:
        ctx = _resolve_context_from_request()
    except ValueError:
        return error("Missing required query parameters: topic or project")

    try:
        listing = list_tasks(limit=max(1, min(200, int(request.args.get("limit") or 50))))
        tasks = listing.get("tasks") if isinstance(listing, dict) else []
        worker = listing.get("worker") if isinstance(listing, dict) else {}
        filtered = []
        for task in tasks or []:
            if not isinstance(task, dict):
                continue
            if str(task.get("topic_identifier") or "").strip() != ctx.identifier:
                continue
            if str(task.get("start_date") or "").strip() != start:
                continue
            task_end = str(task.get("end_date") or "").strip() or None
            if (task_end or None) != end:
                continue
            filtered.append(task)
        filtered.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return success({"data": {"topic_identifier": ctx.identifier, "start": start, "end": end or start, "tasks": filtered, "worker": worker}})
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/worker", methods=["GET"])
def get_media_tagging_worker():
    from server_support.media_tagging import load_worker_status

    return success({"worker": load_worker_status()})


@media_tagging_bp.route("/task/<string:task_id>", methods=["GET"])
def get_media_tagging_task(task_id: str):
    from server_support.media_tagging import get_task

    try:
        return success({"task": get_task(task_id)})
    except LookupError:
        return error("Task not found", status_code=404)
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/task/<string:task_id>/cancel", methods=["POST"])
def cancel_media_tagging_task(task_id: str):
    from server_support.media_tagging import cancel_task

    try:
        return success({"task": cancel_task(task_id)})
    except LookupError:
        return error("Task not found", status_code=404)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/task/<string:task_id>", methods=["DELETE"])
def delete_media_tagging_task(task_id: str):
    from server_support.media_tagging import delete_task

    try:
        delete_task(task_id)
        return success({"message": "Task deleted"})
    except LookupError:
        return error("Task not found", status_code=404)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/history", methods=["GET"])
def media_tagging_history():
    try:
        ctx = _resolve_context_from_request()
    except ValueError:
        return error("Missing required query parameters: topic or project")
    locator = ArchiveLocator(ctx)
    records = locator.list_history("media_tags")
    return success({"records": records, "topic": ctx.display_name, "topic_identifier": ctx.identifier})


@media_tagging_bp.route("/results", methods=["GET"])
def media_tagging_results():
    from src.media_tagging import read_media_tagging_result

    start = str(request.args.get("start") or "").strip()
    end = str(request.args.get("end") or "").strip() or None
    if not start:
        return error("Missing required query parameter: start", status_code=400)
    try:
        ctx = _resolve_context_from_request()
    except ValueError:
        return error("Missing required query parameters: topic or project")
    try:
        payload = read_media_tagging_result(ctx.identifier, start, end)
        payload["topic"] = ctx.display_name
        return success(payload)
    except FileNotFoundError as exc:
        return error(str(exc), status_code=404)
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/results/labels", methods=["POST"])
def media_tagging_update_labels():
    from src.media_tagging import update_media_tagging_labels

    payload = request.get_json(silent=True) or {}
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip() or None
    updates = payload.get("updates") if isinstance(payload.get("updates"), list) else []
    if not start:
        return error("Missing required field(s): start", status_code=400)
    try:
        ctx = resolve_context(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc), status_code=400)
    try:
        refreshed = update_media_tagging_labels(ctx.identifier, start, end_date=end, updates=updates)
        refreshed["topic"] = ctx.display_name
        return success(refreshed)
    except FileNotFoundError as exc:
        return error(str(exc), status_code=404)
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/registry", methods=["GET"])
def media_tagging_registry():
    from src.media_tagging import list_registry_items

    label = str(request.args.get("label") or "").strip()
    search = str(request.args.get("search") or "").strip()
    try:
        return success({"data": {"items": list_registry_items(label=label, search=search)}})
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/registry/<string:item_id>", methods=["PUT"])
def media_tagging_registry_update(item_id: str):
    from src.media_tagging import upsert_registry_item

    payload = request.get_json(silent=True) or {}
    try:
        item = upsert_registry_item({**payload, "id": item_id})
        return success({"data": item})
    except Exception as exc:
        return error(str(exc), status_code=500)


@media_tagging_bp.route("/labeled", methods=["GET"])
def media_tagging_labeled():
    from src.media_tagging import build_labeled_media_payload

    start = str(request.args.get("start") or "").strip()
    end = str(request.args.get("end") or "").strip() or None
    label = str(request.args.get("label") or "").strip()
    if not start:
        return error("Missing required query parameter: start", status_code=400)
    try:
        ctx = _resolve_context_from_request()
    except ValueError:
        return error("Missing required query parameters: topic or project")
    try:
        return success({"data": build_labeled_media_payload(ctx.identifier, start, end_date=end, label=label)})
    except FileNotFoundError as exc:
        return error(str(exc), status_code=404)
    except Exception as exc:
        return error(str(exc), status_code=500)
