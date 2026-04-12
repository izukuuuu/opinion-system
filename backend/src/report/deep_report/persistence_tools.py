from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from langchain.tools import tool


def build_persistence_tools(
    *,
    draft_writer: Callable[[str], Dict[str, Any]],
    cache_writer: Callable[[Dict[str, Any]], Dict[str, Any]],
    publish_writer: Callable[[Dict[str, Any]], Dict[str, Any]],
    production_writer: Callable[[Dict[str, Any]], Dict[str, Any]],
    delete_writer: Callable[[str], Dict[str, Any]],
) -> List[Any]:
    @tool("write_final_report")
    def write_final_report(markdown: str) -> str:
        """将最终文稿写入运行时产物目录。"""
        return json.dumps(draft_writer(str(markdown or "")), ensure_ascii=False, indent=2)

    @tool("overwrite_report_cache")
    def overwrite_report_cache(payload_json: str) -> str:
        """覆盖写入正式报告缓存。"""
        try:
            payload = json.loads(str(payload_json or "{}"))
        except Exception:
            payload = {}
        return json.dumps(cache_writer(payload if isinstance(payload, dict) else {}), ensure_ascii=False, indent=2)

    @tool("publish_report")
    def publish_report(payload_json: str) -> str:
        """预留的外发动作。"""
        try:
            payload = json.loads(str(payload_json or "{}"))
        except Exception:
            payload = {}
        return json.dumps(publish_writer(payload if isinstance(payload, dict) else {}), ensure_ascii=False, indent=2)

    @tool("persist_production_record")
    def persist_production_record(payload_json: str) -> str:
        """预留的生产侧写入动作。"""
        try:
            payload = json.loads(str(payload_json or "{}"))
        except Exception:
            payload = {}
        return json.dumps(production_writer(payload if isinstance(payload, dict) else {}), ensure_ascii=False, indent=2)

    @tool("delete_workspace_artifact")
    def delete_workspace_artifact(path: str) -> str:
        """删除运行时产物。"""
        return json.dumps(delete_writer(str(path or "")), ensure_ascii=False, indent=2)

    return [
        write_final_report,
        overwrite_report_cache,
        publish_report,
        persist_production_record,
        delete_workspace_artifact,
    ]
