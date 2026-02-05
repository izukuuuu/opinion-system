from flask import Blueprint, request, jsonify
from server_support.ops import _execute_operation
from server_support.responses import error, success
from server_support import require_fields, resolve_topic_identifier
from src.project import get_project_manager

PROJECT_MANAGER = get_project_manager()
from src.utils.setting.paths import bucket, _normalise_topic, get_data_root
from pathlib import Path
import time
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

def _compose_analyze_folder(start: str, end: Optional[str]) -> str:
    start = start.strip()
    end = (end or "").strip()
    if not start:
        return ""
    if end:
        return f"{start}_{end}"
    return start

def _split_analyze_folder(folder: str) -> tuple[str, str]:
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

def _normalise_name(value: Optional[str]) -> str:
    return _normalise_topic(value or "")

def _load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            fh.seek(0)
            return fh.read()

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
