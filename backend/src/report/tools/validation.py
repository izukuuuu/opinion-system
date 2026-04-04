from __future__ import annotations

from typing import Any, Dict, List

from langchain.tools import BaseTool


def validate_langchain_toolset(tools: List[Any]) -> Dict[str, Any]:
    issues: List[str] = []
    names: List[str] = []
    schema_overview: List[Dict[str, Any]] = []

    for index, item in enumerate(tools):
        if not isinstance(item, BaseTool):
            issues.append(f"工具索引 {index} 不是 BaseTool 实例。")
            continue

        name = str(getattr(item, "name", "") or "").strip()
        description = str(getattr(item, "description", "") or "").strip()
        if not name:
            issues.append(f"工具索引 {index} 缺少 name。")
            continue
        if name in names:
            issues.append(f"工具 {name} 重名。")
        names.append(name)
        if not description:
            issues.append(f"工具 {name} 缺少 description/docstring。")

        schema = None
        schema_dict: Dict[str, Any] = {}
        try:
            schema = getattr(item, "tool_call_schema", None) or getattr(item, "args_schema", None)
            if schema is not None and hasattr(schema, "model_json_schema"):
                schema_dict = schema.model_json_schema() or {}
        except Exception:
            schema_dict = {}
        properties = schema_dict.get("properties") if isinstance(schema_dict, dict) else None
        if schema is None:
            issues.append(f"工具 {name} 缺少 args schema。")
        elif properties is None:
            issues.append(f"工具 {name} 的 schema 不是 object properties 结构。")

        schema_overview.append(
            {
                "name": name,
                "has_description": bool(description),
                "schema_properties": sorted(list(properties.keys())) if isinstance(properties, dict) else [],
            }
        )

    return {
        "pass": not issues,
        "issues": issues,
        "tool_count": len(tools),
        "schema_overview": schema_overview,
    }


def ensure_langchain_toolset_valid(tools: List[Any]) -> None:
    report = validate_langchain_toolset(tools)
    if report.get("pass"):
        return
    issues = "; ".join(str(item).strip() for item in (report.get("issues") or []) if str(item or "").strip())
    raise ValueError(f"Report tools failed LangChain validation: {issues}")
