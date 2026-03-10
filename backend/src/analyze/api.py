from flask import Blueprint, request, jsonify
from server_support.ops import _execute_operation
from server_support.responses import error, success
from server_support import require_fields, resolve_topic_identifier
from server_support.topic_context import resolve_context, TopicContext
from server_support.archive_locator import ArchiveLocator, split_folder_range, compose_folder_name
from src.project import get_project_manager

PROJECT_MANAGER = get_project_manager()
from src.utils.setting.paths import bucket
from pathlib import Path
import json
import logging
from typing import Optional, List, Dict, Any

LOGGER = logging.getLogger(__name__)

analyze_bp = Blueprint('analyze', __name__)

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

def _load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            fh.seek(0)
            return fh.read()


def _resolve_analyze_root_via_locator(ctx: TopicContext, start: str, end: Optional[str]) -> Optional[Path]:
    """Locate analyze result directory via unified ArchiveLocator."""
    locator = ArchiveLocator(ctx)
    return locator.resolve_result_dir("analyze", start, end)


@analyze_bp.route('', methods=['POST'])
def analyze_endpoint():
    payload = request.get_json(silent=True) or {}
    valid, err = require_fields(payload, "start", "end")
    if not valid:
        return jsonify(err), 400

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


@analyze_bp.route('/ai-summary/rebuild', methods=['POST'])
def rebuild_ai_summary_endpoint():
    payload = request.get_json(silent=True) or {}
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip() or None
    only_function = str(payload.get("function") or "").strip() or None

    if not start:
        return error("Missing required field(s): start", status_code=400)

    try:
        topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    except ValueError as exc:
        return error(str(exc), status_code=400)

    ctx = resolve_context(payload, PROJECT_MANAGER)
    analyze_root = _resolve_analyze_root_via_locator(ctx, start, end)
    if not analyze_root:
        return error("未找到对应的分析结果目录", status_code=404)

    from src.analyze import rebuild_ai_summary_from_analyze_folder  # type: ignore

    ok = rebuild_ai_summary_from_analyze_folder(
        topic_identifier,
        analyze_root.name,
        only_function=only_function,
    )
    if not ok:
        return error("未找到可用于生成 AI 摘要的分析产物", status_code=404)

    resolved_start, resolved_end = split_folder_range(analyze_root.name)
    ai_summary_path = analyze_root / "ai_summary.json"
    return success(
        {
            "data": {
                "topic": display_name or topic_identifier,
                "topic_identifier": topic_identifier,
                "folder": analyze_root.name,
                "range": {
                    "start": resolved_start,
                    "end": resolved_end,
                },
                "function": only_function or "all",
                "ai_summary_path": str(ai_summary_path),
                "ai_summary_exists": ai_summary_path.exists(),
            }
        }
    )


@analyze_bp.route('/history', methods=['GET'])
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
        ctx = resolve_context(payload, PROJECT_MANAGER)
    except ValueError:
        topic_identifier = (raw_topic or "").strip()
        if not topic_identifier:
            return error("Missing required query parameters: topic or project")
        display_name = raw_topic or raw_project or topic_identifier
        ctx = TopicContext(
            identifier=topic_identifier,
            display_name=display_name,
            aliases=[a for a in (raw_topic, raw_project) if a],
        )

    locator = ArchiveLocator(ctx)
    records = locator.list_history("analyze")
    return success(
        {
            "records": records,
            "topic": ctx.display_name,
            "topic_identifier": ctx.identifier,
        }
    )


@analyze_bp.route('/results', methods=['GET'])
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
        ctx = resolve_context(payload, PROJECT_MANAGER)
    except ValueError:
        topic_identifier = (raw_topic or "").strip()
        if not topic_identifier:
            return error("Missing required query parameters: topic or project")
        ctx = TopicContext(
            identifier=topic_identifier,
            display_name=raw_topic or raw_project or topic_identifier,
            aliases=[a for a in (raw_topic, raw_project) if a],
        )

    topic_display = ctx.display_name or raw_topic or raw_project or ctx.identifier

    start = (request.args.get("start") or "").strip()
    if not start:
        return error("Missing required query parameters: start")

    end = (request.args.get("end") or "").strip() or None
    function_alias = (request.args.get("function") or "").strip().lower() or None
    target_alias = (request.args.get("target") or "").strip()

    locator = ArchiveLocator(ctx)
    analyze_root = locator.resolve_result_dir("analyze", start, end)
    if not analyze_root:
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
