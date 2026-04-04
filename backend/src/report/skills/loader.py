from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypedDict

import yaml

from ...utils.setting import settings


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent
PROJECT_AGENTS_SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
KNOWN_BUNDLE_DIR_NAMES = ("skills", "commands")
MARKDOWN_SUFFIXES = {".md", ".markdown"}
TEXT_RESOURCE_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".jinja",
    ".j2",
    ".js",
    ".json",
    ".md",
    ".markdown",
    ".py",
    ".rst",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
SECTION_ALIASES = {
    "goal": "goal",
    "目标": "goal",
    "reasoning style": "reasoning_style",
    "推理风格": "reasoning_style",
    "language requirements": "language_requirements",
    "语言要求": "language_requirements",
    "language contract": "language_contract",
    "语言契约": "language_contract",
    "style language requirements": "style_language_requirements",
    "文书类型语言要求": "style_language_requirements",
    "section guidance": "section_guidance",
    "章节指引": "section_guidance",
    "tool hints": "tool_hints",
    "工具提示": "tool_hints",
    "constraints": "constraints",
    "约束": "constraints",
}
FALLBACK_SKILL_CONTEXT: Dict[str, Any] = {
    "skill_key": "report_default_skill",
    "name": "report_default_skill",
    "agentSkillName": "report-default-skill",
    "displayName": "Report Default Skill",
    "topic": "",
    "description": "默认报告写作规范。",
    "goal": "基于已验证事实生成结构清晰、边界明确的舆情报告。",
    "documentType": "analysis_report",
    "reasoningStyle": [
        "先归纳事实，再解释结构和机制，最后输出边界清晰的结论。",
    ],
    "languageRequirements": [
        "正文不暴露内部字段名、模块名、工具名或技术审计口吻。",
        "证据不足时明确保留不确定性，不把线索写成事实。",
    ],
    "languageContract": {},
    "styleLanguageRequirements": {},
    "sectionGuidance": {},
    "toolNames": [],
    "constraints": [],
    "metadata": {},
    "instructionsMarkdown": "",
    "instructions_markdown": "",
    "sections": {},
    "resourceIndex": [],
    "resource_index": [],
    "sourcePath": "",
    "sourceKind": "fallback",
    "sourceScope": "fallback",
    "skillKey": "report_default_skill",
    "aliases": ["report_default_skill", "report-default-skill"],
}


class SkillCatalogEntry(TypedDict, total=False):
    skill_key: str
    name: str
    skillKey: str
    agentSkillName: str
    displayName: str
    description: str
    documentType: str
    sourceScope: str
    sourceKind: str
    sourcePath: str
    source_scope: str
    source_kind: str
    source_path: str
    aliases: List[str]
    metadata: Dict[str, Any]


class ResolvedSkill(TypedDict, total=False):
    skill_key: str
    name: str
    skillKey: str
    agentSkillName: str
    displayName: str
    topic: str
    description: str
    goal: str
    documentType: str
    reasoningStyle: List[str]
    languageRequirements: List[str]
    languageContract: Dict[str, Any]
    styleLanguageRequirements: Dict[str, Any]
    sectionGuidance: Dict[str, Any]
    toolNames: List[str]
    constraints: List[str]
    metadata: Dict[str, Any]
    instructionsMarkdown: str
    instructions_markdown: str
    sections: Dict[str, str]
    resourceIndex: List[Dict[str, Any]]
    resource_index: List[Dict[str, Any]]
    sourcePath: str
    sourceKind: str
    sourceScope: str
    aliases: List[str]


@dataclass(frozen=True)
class SkillRootSpec:
    scope_key: str
    path: Path
    priority: int


@dataclass
class ParsedSkill:
    skill_key: str
    agent_skill_name: str
    display_name: str
    description: str
    goal: str
    document_type: str
    reasoning_style: List[str]
    language_requirements: List[str]
    language_contract: Dict[str, Any]
    style_language_requirements: Dict[str, Any]
    section_guidance: Dict[str, Any]
    tool_names: List[str]
    constraints: List[str]
    metadata: Dict[str, Any]
    compatibility: str
    body: str
    sections: Dict[str, str]
    aliases: List[str]
    source_path: Path
    source_kind: str
    source_scope: str
    source_root: Path
    skill_dir: Optional[Path]

    def catalog(self) -> SkillCatalogEntry:
        return {
            "skill_key": self.skill_key,
            "name": self.skill_key,
            "skillKey": self.skill_key,
            "agentSkillName": self.agent_skill_name,
            "displayName": self.display_name,
            "description": self.description,
            "documentType": self.document_type,
            "sourceScope": self.source_scope,
            "sourceKind": self.source_kind,
            "sourcePath": str(self.source_path.resolve()),
            "source_scope": self.source_scope,
            "source_kind": self.source_kind,
            "source_path": str(self.source_path.resolve()),
            "aliases": list(self.aliases),
            "metadata": dict(self.metadata),
        }

    def resolved(self, topic: str = "") -> ResolvedSkill:
        resource_index = _build_resource_index(self)
        return {
            "skill_key": self.skill_key,
            "name": self.skill_key,
            "skillKey": self.skill_key,
            "agentSkillName": self.agent_skill_name,
            "displayName": self.display_name,
            "topic": str(topic or "").strip(),
            "description": self.description,
            "goal": self.goal,
            "documentType": self.document_type,
            "reasoningStyle": list(self.reasoning_style),
            "languageRequirements": list(self.language_requirements),
            "languageContract": dict(self.language_contract),
            "styleLanguageRequirements": dict(self.style_language_requirements),
            "sectionGuidance": dict(self.section_guidance),
            "toolNames": list(self.tool_names),
            "constraints": list(self.constraints),
            "metadata": dict(self.metadata),
            "instructionsMarkdown": self.body,
            "instructions_markdown": self.body,
            "sections": dict(self.sections),
            "resourceIndex": resource_index,
            "resource_index": list(resource_index),
            "sourcePath": str(self.source_path.resolve()),
            "sourceKind": self.source_kind,
            "sourceScope": self.source_scope,
            "aliases": list(self.aliases),
        }


def _safe_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _repo_relative_text(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(path.resolve())


def _normalize_token(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return text


def _normalize_agent_skill_name(value: Any) -> str:
    text = re.sub(r"[^0-9a-z\-]+", "-", str(value or "").strip().lower())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return (text or "report-skill")[:64].strip("-") or "report-skill"


def _build_aliases(*values: Any) -> List[str]:
    aliases: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        for candidate in {
            text,
            text.replace("-", "_"),
            text.replace("_", "-"),
            _normalize_token(text),
            _normalize_agent_skill_name(text),
        }:
            token = str(candidate or "").strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(token)
    return aliases


def _coerce_string_list(value: Any, *, max_items: int = 16) -> List[str]:
    if isinstance(value, str):
        rows = [value]
    elif isinstance(value, list):
        rows = value
    else:
        return []
    out: List[str] = []
    seen = set()
    for item in rows:
        token = str(item or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
        if len(out) >= max_items:
            break
    return out


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    source = str(text or "")
    if not source.startswith("---\n") and not source.startswith("---\r\n"):
        return {}, source

    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, source

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}, source

    frontmatter_text = "\n".join(lines[1:end_index]).strip()
    body = "\n".join(lines[end_index + 1 :]).lstrip()
    if not frontmatter_text:
        return {}, body
    try:
        payload = yaml.safe_load(frontmatter_text) or {}
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}, body


def _extract_markdown_sections(body: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", str(body or "")))
    for index, match in enumerate(matches):
        raw_title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = str(body[start:end]).strip()
        if not content:
            continue
        key = SECTION_ALIASES.get(raw_title.lower()) or SECTION_ALIASES.get(raw_title)
        if key:
            sections[key] = content
    return sections


def _extract_json_block(text: str) -> Any:
    match = re.search(r"```(?:json|yaml)?\s*(.*?)```", str(text or ""), flags=re.S | re.I)
    candidate = match.group(1).strip() if match else str(text or "").strip()
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except Exception:
        try:
            return yaml.safe_load(candidate)
        except Exception:
            return None


def _extract_list_block(text: str) -> List[str]:
    lines = str(text or "").splitlines()
    items: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("- ", "* ")):
            items.append(stripped[2:].strip(" `"))
            continue
        numbered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if numbered:
            items.append(numbered.group(1).strip(" `"))
    return _coerce_string_list(items, max_items=24)


def _extract_first_paragraph(text: str) -> str:
    blocks = re.split(r"\n\s*\n", str(text or "").strip())
    for block in blocks:
        paragraph = re.sub(r"\s+", " ", block).strip()
        if paragraph:
            return paragraph
    return ""


def _coerce_metadata(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        try:
            parsed = yaml.safe_load(text)
        except Exception:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _configured_skill_extra_dirs() -> List[Path]:
    try:
        settings.reload()
    except Exception:
        pass
    raw_value = settings.get("llm.langchain.report.skills.load.extra_dirs", [])
    if raw_value in (None, ""):
        raw_value = []
    if isinstance(raw_value, str):
        raw_items = [item.strip() for item in raw_value.split(",")]
    elif isinstance(raw_value, list):
        raw_items = [str(item or "").strip() for item in raw_value]
    else:
        raw_items = []

    paths: List[Path] = []
    seen = set()
    for item in raw_items:
        if not item:
            continue
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _configured_default_skill_key() -> str:
    try:
        settings.reload()
    except Exception:
        pass
    raw = settings.get("llm.langchain.report.skills.default", "sona_feature_analysis")
    return str(raw or "sona_feature_analysis").strip() or "sona_feature_analysis"


def _configured_project_agents_enabled() -> bool:
    try:
        settings.reload()
    except Exception:
        pass
    raw = settings.get("llm.langchain.report.skills.load.enable_project_agents_dir", False)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _iter_markdown_entries(directory: Path) -> Iterable[Tuple[Path, str]]:
    for child in sorted(directory.iterdir()):
        if child.is_dir():
            skill_file = child / "SKILL.md"
            if skill_file.exists():
                yield skill_file, "skill_dir"
        elif child.is_file() and child.suffix.lower() in MARKDOWN_SUFFIXES:
            if child.name.lower().startswith("readme"):
                continue
            yield child, "markdown_file"


def _iter_skill_candidates(base_path: Path) -> Iterable[Tuple[Path, str]]:
    if not base_path.exists():
        return
    if base_path.is_file() and base_path.suffix.lower() in MARKDOWN_SUFFIXES:
        yield base_path, "markdown_file"
        return

    direct_skill = base_path / "SKILL.md"
    if direct_skill.exists():
        yield direct_skill, "skill_dir"

    nested_candidates = [base_path / name for name in KNOWN_BUNDLE_DIR_NAMES]
    nested_candidates.append(base_path / ".cursor" / "commands")

    for nested in nested_candidates:
        if nested.exists() and nested.is_dir():
            yield from _iter_markdown_entries(nested)

    if base_path.name in KNOWN_BUNDLE_DIR_NAMES or (
        base_path.parent.name == ".cursor" and base_path.name == "commands"
    ):
        yield from _iter_markdown_entries(base_path)
        return

    if not direct_skill.exists():
        yield from _iter_markdown_entries(base_path)


def _configured_source_roots() -> List[SkillRootSpec]:
    roots: List[SkillRootSpec] = [
        SkillRootSpec(scope_key="bundled", path=DEFAULT_SKILLS_DIR, priority=0),
    ]
    if _configured_project_agents_enabled():
        roots.append(SkillRootSpec(scope_key="project_agents", path=PROJECT_AGENTS_SKILLS_DIR, priority=1))
    for index, path in enumerate(_configured_skill_extra_dirs()):
        roots.append(SkillRootSpec(scope_key=f"external_{index}", path=path, priority=2 + index))
    return roots


def _build_resource_index(skill: ParsedSkill) -> List[Dict[str, Any]]:
    if skill.skill_dir is None or not skill.skill_dir.exists():
        return []
    resources: List[Dict[str, Any]] = []
    for path in sorted(skill.skill_dir.rglob("*")):
        if not path.is_file() or path.name.upper() == "SKILL.MD":
            continue
        try:
            relative_path = path.relative_to(skill.skill_dir).as_posix()
        except Exception:
            continue
        first_segment = relative_path.split("/", 1)[0] if "/" in relative_path else relative_path
        resource_kind = first_segment if "/" in relative_path else "root"
        resources.append(
            {
                "path": relative_path,
                "kind": resource_kind,
                "size": int(path.stat().st_size) if path.exists() else 0,
                "sourcePath": str(path.resolve()),
                "staged": _should_stage_text_resource(path),
            }
        )
    return resources


def _safe_relative_resource_path(relative_path: str) -> PurePosixPath:
    pure = PurePosixPath(str(relative_path or "").strip())
    if not pure.parts:
        raise ValueError("missing relative resource path")
    if pure.is_absolute():
        raise ValueError("absolute resource paths are not allowed")
    if any(part in {"..", ""} for part in pure.parts):
        raise ValueError("path traversal is not allowed")
    return pure


def _read_skill_resource_text(skill: ParsedSkill, relative_path: str) -> str:
    if skill.skill_dir is None:
        raise FileNotFoundError("skill has no resource directory")
    pure = _safe_relative_resource_path(relative_path)
    target = (skill.skill_dir / Path(str(pure))).resolve()
    try:
        target.relative_to(skill.skill_dir.resolve())
    except Exception as exc:
        raise ValueError("resource path escapes skill directory") from exc
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(str(target))
    return _safe_text(target)


def _should_stage_text_resource(path: Path) -> bool:
    try:
        if path.stat().st_size > 1024 * 1024:
            return False
    except Exception:
        return False
    return path.suffix.lower() in TEXT_RESOURCE_SUFFIXES


def _dump_yaml_frontmatter(payload: Dict[str, Any]) -> str:
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{text}\n---\n\n"


def _serialize_skill_markdown(skill: ParsedSkill) -> str:
    frontmatter: Dict[str, Any] = {
        "name": skill.agent_skill_name,
        "description": skill.description[:1024],
    }
    if skill.display_name and skill.display_name != skill.agent_skill_name:
        frontmatter["title"] = skill.display_name
    if skill.compatibility:
        frontmatter["compatibility"] = skill.compatibility[:500]
    if skill.tool_names:
        frontmatter["allowed_tools"] = " ".join(skill.tool_names)
    if skill.metadata:
        frontmatter["metadata"] = skill.metadata
    body = str(skill.body or "").strip()
    if not body:
        body = f"# {skill.display_name}\n\n{skill.description}".strip()
    return f"{_dump_yaml_frontmatter(frontmatter)}{body}\n"


def _build_state_file_data(content: str) -> Dict[str, Any]:
    lines = str(content or "").split("\n")
    now = datetime.now(UTC).isoformat()
    return {
        "content": lines,
        "created_at": now,
        "modified_at": now,
    }


def _build_virtual_skill_files(skill: ParsedSkill, source_prefix: str) -> Dict[str, Dict[str, Any]]:
    skill_root = PurePosixPath(source_prefix) / skill.agent_skill_name
    files: Dict[str, Dict[str, Any]] = {
        str(skill_root / "SKILL.md"): _build_state_file_data(_serialize_skill_markdown(skill))
    }
    if skill.skill_dir is None:
        return files
    for path in sorted(skill.skill_dir.rglob("*")):
        if not path.is_file() or path.name.upper() == "SKILL.MD":
            continue
        if not _should_stage_text_resource(path):
            continue
        try:
            relative_path = path.relative_to(skill.skill_dir).as_posix()
        except Exception:
            continue
        files[str(skill_root / PurePosixPath(relative_path))] = _build_state_file_data(_safe_text(path))
    return files


def _build_skill_record(path: Path, source_kind: str, root: SkillRootSpec) -> Optional[ParsedSkill]:
    text = _safe_text(path)
    if not text.strip():
        return None

    frontmatter, body = _extract_frontmatter(text)
    metadata = _coerce_metadata(frontmatter.get("metadata"))
    report_meta = _coerce_mapping(metadata.get("report"))
    openclaw_meta = _coerce_mapping(metadata.get("openclaw"))
    sections = _extract_markdown_sections(body)

    path_name_fallback = path.parent.name if path.name.upper() == "SKILL.MD" else path.stem
    declared_name = str(frontmatter.get("name") or "").strip()
    agent_skill_name = _normalize_agent_skill_name(declared_name or path_name_fallback or path.stem)
    display_name = str(frontmatter.get("title") or "").strip() or declared_name or path_name_fallback or agent_skill_name
    description = (
        str(frontmatter.get("description") or "").strip()
        or str(frontmatter.get("summary") or "").strip()
        or _extract_first_paragraph(body)
        or f"{display_name} skill"
    )
    skill_key = (
        str(openclaw_meta.get("skillKey") or "").strip()
        or str(report_meta.get("skillKey") or "").strip()
        or _normalize_token(agent_skill_name)
        or _normalize_token(path_name_fallback)
        or "report_skill"
    )
    aliases = _build_aliases(
        skill_key,
        agent_skill_name,
        path_name_fallback,
        path.parent.name,
        path.stem if path.name.upper() != "SKILL.MD" else "",
        *(_coerce_string_list(report_meta.get("aliases"), max_items=12)),
    )
    goal = str(report_meta.get("goal") or "").strip() or str(sections.get("goal") or "").strip() or description
    reasoning_style = _coerce_string_list(report_meta.get("reasoningStyle"), max_items=12) or _extract_list_block(
        sections.get("reasoning_style", "")
    )
    language_requirements = _coerce_string_list(
        report_meta.get("languageRequirements"),
        max_items=16,
    ) or _extract_list_block(sections.get("language_requirements", ""))
    language_contract = _coerce_mapping(report_meta.get("languageContract"))
    if not language_contract:
        language_contract = _coerce_mapping(_extract_json_block(sections.get("language_contract", "")))
    style_language_requirements = _coerce_mapping(report_meta.get("styleLanguageRequirements"))
    if not style_language_requirements:
        style_language_requirements = _coerce_mapping(
            _extract_json_block(sections.get("style_language_requirements", ""))
        )
    section_guidance = _coerce_mapping(report_meta.get("sectionGuidance"))
    if not section_guidance:
        section_guidance = _coerce_mapping(_extract_json_block(sections.get("section_guidance", "")))
    tool_names = _coerce_string_list(report_meta.get("toolNames"), max_items=24) or _extract_list_block(
        sections.get("tool_hints", "")
    )
    declared_allowed_tools = frontmatter.get("allowed_tools")
    if isinstance(declared_allowed_tools, str):
        tool_names = _coerce_string_list(declared_allowed_tools.split(), max_items=24) or tool_names
    constraints = _coerce_string_list(report_meta.get("constraints"), max_items=16) or _extract_list_block(
        sections.get("constraints", "")
    )
    document_type = (
        str(report_meta.get("documentType") or "").strip()
        or str(frontmatter.get("documentType") or "").strip()
        or "analysis_report"
    )
    compatibility = str(frontmatter.get("compatibility") or "").strip()
    skill_dir = path.parent if path.name.upper() == "SKILL.MD" else None

    return ParsedSkill(
        skill_key=skill_key,
        agent_skill_name=agent_skill_name,
        display_name=display_name,
        description=description,
        goal=goal,
        document_type=document_type,
        reasoning_style=reasoning_style,
        language_requirements=language_requirements,
        language_contract=language_contract,
        style_language_requirements=style_language_requirements,
        section_guidance=section_guidance,
        tool_names=tool_names,
        constraints=constraints,
        metadata=metadata,
        compatibility=compatibility,
        body=body.strip(),
        sections=sections,
        aliases=aliases,
        source_path=path,
        source_kind=source_kind,
        source_scope=root.scope_key,
        source_root=root.path,
        skill_dir=skill_dir,
    )


def _collect_skills() -> List[ParsedSkill]:
    selected_by_key: Dict[str, ParsedSkill] = {}
    seen_paths = set()
    for root in _configured_source_roots():
        if not root.path.exists():
            continue
        for candidate, source_kind in _iter_skill_candidates(root.path):
            try:
                resolved_path = str(candidate.resolve())
            except Exception:
                resolved_path = str(candidate)
            if resolved_path in seen_paths:
                continue
            seen_paths.add(resolved_path)
            record = _build_skill_record(candidate, source_kind, root)
            if not record:
                continue
            selected_by_key[record.skill_key] = record
    skills = list(selected_by_key.values())
    skills.sort(key=lambda item: (item.source_scope, item.agent_skill_name))
    return skills


def discover_report_skills(topic: str = "") -> List[SkillCatalogEntry]:
    return [skill.catalog() for skill in _collect_skills()]


def resolve_report_skill(skill_key: str = "", topic: str = "") -> ResolvedSkill:
    requested = str(skill_key or "").strip()
    if not requested:
        requested = _configured_default_skill_key()
    requested_aliases = {alias.lower() for alias in _build_aliases(requested)}
    fallback_record: Optional[ParsedSkill] = None

    for record in _collect_skills():
        aliases = {str(item or "").strip().lower() for item in record.aliases if str(item or "").strip()}
        if fallback_record is None:
            fallback_record = record
        if aliases.intersection(requested_aliases):
            return record.resolved(topic=topic)

    result = dict(fallback_record.resolved(topic=topic) if fallback_record else FALLBACK_SKILL_CONTEXT)
    if result.get("sourcePath"):
        result.setdefault("metadata", {})
        result["metadata"] = {
            **_coerce_mapping(result.get("metadata")),
            "report": {
                **_coerce_mapping(_coerce_mapping(result.get("metadata")).get("report")),
                "discoveryNote": f"default skill {requested!r} not found; using fallback source {_repo_relative_text(Path(str(result.get('sourcePath'))))}",
            },
        }
    result["topic"] = str(topic or "").strip()
    return result


def load_report_skill_context(topic: str = "") -> ResolvedSkill:
    return resolve_report_skill(_configured_default_skill_key(), topic=topic)


def read_report_skill_resource(skill_key: str, relative_path: str, topic: str = "") -> str:
    requested_aliases = {alias.lower() for alias in _build_aliases(skill_key)}
    for record in _collect_skills():
        aliases = {str(item or "").strip().lower() for item in record.aliases if str(item or "").strip()}
        if aliases.intersection(requested_aliases):
            return _read_skill_resource_text(record, relative_path)
    raise FileNotFoundError(f"skill not found: {skill_key}")


def build_report_skill_runtime_assets(topic: str = "") -> Dict[str, Any]:
    staged_files: Dict[str, Dict[str, Any]] = {}
    sources: List[str] = []
    source_paths = {spec.scope_key: spec.path for spec in _configured_source_roots()}
    discovered = _collect_skills()
    for scope_key in [spec.scope_key for spec in _configured_source_roots()]:
        source_prefix = f"/report-skills/{scope_key}"
        scoped_skills = [skill for skill in discovered if skill.source_scope == scope_key]
        if not scoped_skills:
            continue
        sources.append(source_prefix)
        for skill in scoped_skills:
            staged_files.update(_build_virtual_skill_files(skill, source_prefix))
    return {
        "files": staged_files,
        "sources": sources,
        "catalog": [skill.catalog() for skill in discovered],
        "source_paths": {key: str(path.resolve()) for key, path in source_paths.items() if path.exists()},
        "default_skill_key": _configured_default_skill_key(),
        "topic": str(topic or "").strip(),
    }


__all__ = [
    "SkillCatalogEntry",
    "ResolvedSkill",
    "build_report_skill_runtime_assets",
    "discover_report_skills",
    "load_report_skill_context",
    "read_report_skill_resource",
    "resolve_report_skill",
]
