from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from deepagents.backends.utils import create_file_data
from langgraph.store.memory import InMemoryStore

from ..knowledge_loader import load_report_knowledge
from ..skills import build_report_skill_runtime_assets, load_report_skill_context


RUNTIME_STORE = InMemoryStore()


def build_memory_markdown(topic_label: str) -> str:
    knowledge = load_report_knowledge(topic_label)
    skill = load_report_skill_context(topic_label)
    banned = [
        "不要暴露内部字段名、模块名、工具名、缓存文件名、目录结构。",
        "前端文案使用用户语言，不使用 backend narration。",
        "证据不足时必须保留边界，不把线索写成事实。",
        "所有正式结论、风险和建议都要尽量回链到 citation_ids。",
    ]
    theory_hints = []
    for item in knowledge.get("dynamic_theories") or knowledge.get("theory_hints") or []:
        text = str(item or "").strip()
        if text:
            theory_hints.append(text)
        if len(theory_hints) >= 6:
            break
    constraints = []
    for item in skill.get("constraints") or []:
        text = str(item or "").strip()
        if text:
            constraints.append(text)
        if len(constraints) >= 8:
            break
    payload = {
        "topic": topic_label,
        "document_type": str(skill.get("documentType") or "").strip(),
        "theory_hints": theory_hints,
        "constraints": constraints,
        "banned": banned,
    }
    return (
        "# Report Runtime Memory\n\n"
        "## Always Relevant Rules\n"
        f"- 专题：{topic_label}\n"
        "- 这个系统的职责是给出可回溯、可审计的舆情研判结构。\n"
        "- 任何建议动作都必须说明依据与边界。\n"
        "- 优先输出结构化结果，再输出文稿。\n\n"
        "## Runtime Profile\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n"
    )


def build_runtime_assets(topic_label: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any], list[str]]:
    skill_assets = build_report_skill_runtime_assets(topic_label)
    files: Dict[str, Dict[str, Any]] = {}
    staged = skill_assets.get("files") if isinstance(skill_assets.get("files"), dict) else {}
    for path, payload in staged.items():
        if isinstance(payload, dict):
            files[str(path)] = payload
    files["/workspace/.keep"] = create_file_data("")
    files["/memories/README.md"] = create_file_data("Report runtime memory lives in AGENTS.md.")
    files["/memories/AGENTS.md"] = create_file_data(build_memory_markdown(topic_label))
    memory_paths = ["/memories/AGENTS.md"]
    return files, skill_assets, memory_paths


def ensure_memory_seed(namespace: tuple[str, ...], topic_label: str) -> None:
    RUNTIME_STORE.put(namespace, "/AGENTS.md", create_file_data(build_memory_markdown(topic_label)))


def build_artifacts_root(task_id: str, data_root: Path) -> Path:
    root = data_root / "_report" / "runtime" / task_id
    root.mkdir(parents=True, exist_ok=True)
    return root
