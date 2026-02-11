from flask import Blueprint, request, jsonify
from server_support.ops import _execute_operation
from server_support.responses import error, success
from server_support import require_fields, resolve_topic_identifier
from src.project import get_project_manager
from src.topic.prompt_config import (
    load_topic_bertopic_prompt_config,
    persist_topic_bertopic_prompt_config,
)
from src.topic.config import (
    load_bertopic_config,
    save_bertopic_config,
)

PROJECT_MANAGER = get_project_manager()
from src.utils.setting.paths import bucket, get_data_root
from pathlib import Path
import logging
from typing import Dict, Any, List

LOGGER = logging.getLogger(__name__)

topic_bp = Blueprint('topic', __name__)

def _load_json_file(path: Path) -> Any:
    # Local helper for this module
    import json
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            fh.seek(0)
            return fh.read()

def _compose_analyze_folder(start: str, end: str = None) -> str:
    # Duplicated local helper to avoid cross-module import if analyze api changes
    start = start.strip()
    end = (end or "").strip()
    if not start:
        return ""
    if end:
        return f"{start}_{end}"
    return start


def _parse_topic_folder_range(folder_name: str) -> tuple[str, str]:
    token = str(folder_name or "").strip()
    if not token:
        return "", ""
    if "_" in token:
        start, end = token.split("_", 1)
    else:
        start, end = token, token
    return start.strip(), end.strip()

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
    supports_run_params = False
    try:
        # 导入新的BERTopic模块
        from src.topic.data_bertopic_qwen_v2 import run_topic_bertopic
        supports_run_params = True

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
    run_params = payload.get("run_params")
    if not isinstance(run_params, dict):
        run_params = {}

    # 运行BERTopic分析
    run_kwargs = {
        "fetch_dir": fetch_dir,
        "userdict": userdict,
        "stopwords": stopwords,
        "bucket_topic": bucket_topic,
        "display_topic": topic_label,
    }
    if supports_run_params:
        run_kwargs["db_topic"] = db_topic
        run_kwargs["run_params"] = run_params

    result = run_topic_bertopic(
        bucket_topic,
        start_date,
        end_date,
        **run_kwargs,
    )

    if result:
        # 如果请求同步到 Neo4j
        if payload.get("sync_neo4j"):
            try:
                from src.graph.sync_bertopic import sync_bertopic_results
                sync_bertopic_results(bucket_topic, start_date, end_date)
            except Exception as e:
                LOGGER.error(f"Failed to sync to Neo4j: {e}", exc_info=True)

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


@topic_bp.route('/bertopic/run', methods=['POST'])
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


@topic_bp.route('/bertopic/availability', methods=['GET'])
def check_topic_availability():
    """检查专题的数据可用性范围"""
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

    # 获取数据可用日期范围（兼容 dict / tuple 返回）
    availability = get_topic_available_date_range(db_topic)
    if isinstance(availability, dict):
        avail_start = availability.get("start")
        avail_end = availability.get("end")
    else:
        avail_start, avail_end = availability

    # 检查本地缓存情况
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


@topic_bp.route('/bertopic/prompt', methods=['GET'])
def get_topic_bertopic_prompt():
    """获取 BERTopic 提示词配置。"""
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
    except ValueError:
        topic_identifier = (topic or project or dataset_id).strip()
        if not topic_identifier:
            return error("Missing required field(s): topic/project/dataset_id")
        display_name = topic or project or topic_identifier

    try:
        data = load_topic_bertopic_prompt_config(topic_identifier)
    except Exception as exc:
        LOGGER.exception("Failed to load BERTopic prompt config")
        return error(f"加载 BERTopic 提示词配置失败: {str(exc)}")

    data["topic_identifier"] = topic_identifier
    data["topic"] = display_name or topic_identifier
    return success({"data": data})


@topic_bp.route('/bertopic/prompt', methods=['POST'])
def save_topic_bertopic_prompt():
    """保存 BERTopic 提示词配置。"""
    payload = request.get_json(silent=True) or {}
    topic = str(payload.get("topic") or "").strip()
    project = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()

    if not any([topic, project, dataset_id]):
        return error("Missing required field(s): topic/project/dataset_id")

    resolution_payload = {
        "topic": topic,
        "project": project,
        "dataset_id": dataset_id,
    }
    try:
        topic_identifier, display_name, _, _ = resolve_topic_identifier(
            resolution_payload,
            PROJECT_MANAGER,
        )
    except ValueError:
        topic_identifier = (topic or project or dataset_id).strip()
        if not topic_identifier:
            return error("Missing required field(s): topic/project/dataset_id")
        display_name = topic or project or topic_identifier

    try:
        data = persist_topic_bertopic_prompt_config(
            topic_identifier,
            payload.get("target_topics", payload.get("targetTopics")),
            str(payload.get("recluster_system_prompt") or ""),
            str(payload.get("recluster_user_prompt") or ""),
            str(payload.get("keyword_system_prompt") or ""),
            str(payload.get("keyword_user_prompt") or ""),
        )
    except Exception as exc:
        LOGGER.exception("Failed to save BERTopic prompt config")
        return error(f"保存 BERTopic 提示词配置失败: {str(exc)}")

    data["topic_identifier"] = topic_identifier
    data["topic"] = display_name or topic_identifier
    return success({"data": data})


@topic_bp.route('/bertopic/results', methods=['GET'])
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


@topic_bp.route('/bertopic/history', methods=['GET'])
def get_topic_bertopic_history():
    """列出专题可用的 BERTopic 结果存档（按时间倒序）"""
    raw_topic = str(request.args.get("topic") or "").strip()
    raw_project = str(request.args.get("project") or "").strip()
    raw_dataset_id = str(request.args.get("dataset_id") or "").strip()

    if not any([raw_topic, raw_project, raw_dataset_id]):
        return error("Missing required query parameters: topic/project/dataset_id")

    payload = {
        "topic": raw_topic,
        "project": raw_project,
        "dataset_id": raw_dataset_id,
    }

    try:
        topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    except ValueError:
        topic_identifier = (raw_topic or raw_project or raw_dataset_id).strip()
        if not topic_identifier:
            return error("Missing required query parameters: topic/project/dataset_id")
        display_name = raw_topic or raw_project or topic_identifier

    topic_root = get_data_root() / "projects" / topic_identifier / "topic"
    if not topic_root.exists() or not topic_root.is_dir():
        return success(
            {
                "data": {
                    "topic": display_name or topic_identifier,
                    "topic_identifier": topic_identifier,
                    "records": [],
                }
            }
        )

    file_map = {
        "summary": "1主题统计结果.json",
        "keywords": "2主题关键词.json",
        "coords": "3文档2D坐标.json",
        "llm_clusters": "4大模型再聚类结果.json",
        "llm_keywords": "5大模型主题关键词.json",
    }

    records: List[Dict[str, Any]] = []
    for entry in topic_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        start, end = _parse_topic_folder_range(entry.name)
        if not start:
            continue

        available_keys: List[str] = []
        latest_mtime = entry.stat().st_mtime

        for key, filename in file_map.items():
            path = entry / filename
            if not path.exists():
                continue
            available_keys.append(key)
            try:
                latest_mtime = max(latest_mtime, path.stat().st_mtime)
            except OSError:
                pass

        if not available_keys:
            continue

        records.append(
            {
                "id": f"{topic_identifier}:{entry.name}",
                "topic": topic_identifier,
                "display_topic": display_name or topic_identifier,
                "start": start,
                "end": end or start,
                "folder": entry.name,
                "available_files": available_keys,
                "updated_at": latest_mtime,
            }
        )

    records.sort(
        key=lambda item: (
            str(item.get("start") or ""),
            str(item.get("end") or ""),
            float(item.get("updated_at") or 0),
        ),
        reverse=True,
    )

    return success(
        {
            "data": {
                "topic": display_name or topic_identifier,
                "topic_identifier": topic_identifier,
                "records": records,
            }
        }
    )


@topic_bp.route('/bertopic/topics', methods=['GET'])
def list_topic_buckets():
    """获取所有可用的专题 Bucket 列表"""
    try:
        from src.utils.setting.paths import get_data_root
        from src.query import run_query
        data_root = get_data_root()
        projects_dir = data_root / "projects"

        only_with_results = request.args.get("only_with_results", "false").lower() == "true"
        only_with_data = request.args.get("only_with_data", "false").lower() == "true"

        topics = []

        if only_with_data:
            try:
                response, _ = _execute_operation(
                    "query",
                    run_query,
                    include_counts=True,
                    log_context={"params": {"source": "api"}}
                )

                if response.get("status") == "ok":
                    databases = response.get("data", {}).get("databases", [])
                    for db in databases:
                        db_name = db.get("name", "").strip()
                        if db_name:
                            project_dir = projects_dir / db_name if projects_dir.exists() else None
                            has_topic = False

                            if project_dir and project_dir.exists():
                                topic_dir = project_dir / "topic"
                                has_topic = topic_dir.exists() and topic_dir.is_dir()

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

        if not topics or not only_with_data:
            if projects_dir.exists():
                all_items = list(projects_dir.iterdir())
                for item in sorted(all_items):
                    if item.is_dir() and not item.name.startswith('.'):
                        topic_dir = item / "topic"
                        has_topic = topic_dir.exists() and topic_dir.is_dir()

                        has_data = False
                        fetch_dir = item / "fetch"
                        if fetch_dir.exists():
                            has_data = any(fetch_dir.iterdir())

                        if not only_with_data or has_data:
                            if not only_with_results or has_topic:
                                topics.append({
                                    "bucket": item.name,
                                    "name": item.name,
                                    "display_name": item.name,
                                    "has_bertopic_results": has_topic,
                                    "source": "local"
                                })

        seen = set()
        unique_topics = []
        for topic in topics:
            key = topic["bucket"]
            if key not in seen:
                seen.add(key)
                unique_topics.append(topic)
            elif topic.get("source") == "database":
                for i, existing in enumerate(unique_topics):
                    if existing["bucket"] == key:
                        unique_topics[i] = topic
                        break

        return success({
            "topics": unique_topics,
            "data_root": str(data_root),
            "projects_dir": str(projects_dir),
            "source": "database" if any(t.get("source") == "database" for t in unique_topics) else "local"
        })
    except Exception as exc:
        LOGGER.exception("Failed to list topic buckets")
        return error(f"获取专题列表失败: {str(exc)}")


@topic_bp.route('/config', methods=['GET'])
def get_bertopic_config():
    """获取 BERTopic 全局配置"""
    try:
        config = load_bertopic_config()
        return success({"data": config})
    except Exception as exc:
        return error(f"加载配置失败: {str(exc)}")


@topic_bp.route('/config', methods=['POST'])
def update_bertopic_config():
    """更新 BERTopic 全局配置"""
    try:
        payload = request.get_json(silent=True) or {}
        config = save_bertopic_config(payload)
        return success({"data": config})
    except Exception as exc:
        return error(f"保存配置失败: {str(exc)}")
