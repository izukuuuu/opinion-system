from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from ..capability_manifest import RUNTIME_COORDINATOR, RUNTIME_SUBAGENT
from ..configs import (
    get_all_subagent_configs,
    get_all_subagents_by_tier,
    get_coordinator_skill_keys,
    get_subagent_output_files,
    get_subagent_output_globs,
    get_subagent_skill_keys,
)
from ..skills import select_report_skill_sources
from ..tools import select_report_tools

SUPPORTED_SUBAGENT_NAMES: Tuple[str, ...] = (
    "retrieval_router",
    "archive_evidence_organizer",
    "bertopic_evolution_analyst",
    "timeline_analyst",
    "stance_conflict",
    "event_analyst",
    "claim_actor_conflict",
    "agenda_frame_builder",
    "propagation_analyst",
    "decision_utility_judge",
    "writer",
)

_SUBAGENT_NODE_NAMES: Dict[str, str] = {
    "retrieval_router": "retrieval_router_node",
    "archive_evidence_organizer": "archive_evidence_node",
    "bertopic_evolution_analyst": "bertopic_node",
    "timeline_analyst": "timeline_node",
    "stance_conflict": "stance_node",
    "event_analyst": "event_analyst_node",
    "claim_actor_conflict": "conflict_node",
    "agenda_frame_builder": "agenda_node",
    "propagation_analyst": "propagation_node",
    "decision_utility_judge": "utility_node",
    "writer": "writer_node",
}

_TIER_PRESENTATION: Dict[int, Dict[str, str]] = {
    0: {"label": "范围确认与检索冻结", "detail": "等待开始。"},
    1: {"label": "证据与主题演化", "detail": "等待并行证据整理与主题演化。"},
    2: {"label": "时间线与立场", "detail": "等待时间线与主体立场分析。"},
    3: {"label": "事件分析与冲突图", "detail": "等待事件分析与冲突图整理。"},
    4: {"label": "议题框架与传播机制", "detail": "等待议题框架与传播机制分析。"},
    5: {"label": "效用裁决", "detail": "等待效用裁决结果。"},
    6: {"label": "文稿生成与结构化交付", "detail": "等待文稿草拟与结构化交付。"},
}

_RESEARCH_ONLY_AGENTS = {"bertopic_evolution_analyst"}
_COORDINATOR_OUTPUT_FILES: Dict[str, str] = {
    "section_packets/overview.json": "report_coordinator",
    "section_packets/timeline.json": "report_coordinator",
    "section_packets/risk.json": "report_coordinator",
}


def _require_supported_agents() -> Dict[str, Dict[str, Any]]:
    configs = get_all_subagent_configs()
    config_names = set(configs.keys())
    supported = set(SUPPORTED_SUBAGENT_NAMES)
    missing = sorted(config_names - supported)
    if missing:
        raise ValueError(f"subagents.yaml contains unsupported subagents without providers: {', '.join(missing)}")
    unresolved = sorted(supported - config_names)
    if unresolved:
        raise ValueError(f"subagents.yaml is missing required subagents: {', '.join(unresolved)}")
    return configs


def get_subagent_metadata() -> Dict[str, Dict[str, Any]]:
    return _require_supported_agents()


def get_subagent_metadata_by_name(agent_name: str) -> Dict[str, Any]:
    metadata = get_subagent_metadata().get(str(agent_name or "").strip()) or {}
    if not metadata:
        raise ValueError(f"Unknown report subagent metadata: {agent_name}")
    return dict(metadata)


def get_tier_groups() -> Dict[int, List[str]]:
    grouped = get_all_subagents_by_tier()
    metadata = get_subagent_metadata()
    return {
        tier: [name for name in names if name in metadata]
        for tier, names in grouped.items()
    }


def build_tier_todo_specs() -> Dict[int, Dict[str, Any]]:
    grouped = get_tier_groups()
    specs: Dict[int, Dict[str, Any]] = {}
    for tier, agents in grouped.items():
        presentation = _TIER_PRESENTATION.get(tier, {})
        specs[tier] = {
            "id": f"tier-{tier}",
            "label": str(presentation.get("label") or f"Tier {tier}").strip(),
            "detail": str(presentation.get("detail") or "等待开始。").strip(),
            "agents": list(agents),
        }
    return specs


def build_tier_prompt_lines() -> List[str]:
    lines: List[str] = []
    for tier, agents in get_tier_groups().items():
        if tier > 5:
            continue
        rendered = "、".join(agents)
        if len(agents) > 1:
            rendered = f"{rendered}（并行）"
        lines.append(f"   Tier {tier}: {rendered}")
    return lines


def get_subagent_node_name(agent_name: str) -> str:
    name = str(agent_name or "").strip()
    return _SUBAGENT_NODE_NAMES.get(name, f"{name}_node")


def build_runtime_subagent_specs(
    *,
    system_prompts: Dict[str, str],
    skill_assets: Dict[str, Any],
    middleware_factory: Callable[[str], List[Any]],
) -> List[Dict[str, Any]]:
    metadata = get_subagent_metadata()
    missing_prompts = sorted(set(metadata.keys()) - set(system_prompts.keys()))
    if missing_prompts:
        raise ValueError(f"Missing system prompts for report subagents: {', '.join(missing_prompts)}")

    specs: List[Dict[str, Any]] = []
    for tier, agent_names in get_tier_groups().items():
        for agent_name in agent_names:
            toolset = select_report_tools(runtime_target=RUNTIME_SUBAGENT, agent_name=agent_name)
            skill_keys = get_subagent_skill_keys(agent_name)
            skills = select_report_skill_sources(
                skill_assets,
                available_tool_ids=[t.name for t in toolset if str(getattr(t, "name", "") or "").strip()],
                preferred_skill_keys=skill_keys,
                runtime_target=RUNTIME_SUBAGENT,
                agent_name=agent_name,
            )
            entry = metadata[agent_name]
            specs.append(
                {
                    "name": agent_name,
                    "tier": tier,
                    "description": str(entry.get("description") or "").strip(),
                    "skill_keys": list(skill_keys),
                    "output_files": get_subagent_output_files(agent_name),
                    "output_globs": get_subagent_output_globs(agent_name),
                    "system_prompt": str(system_prompts[agent_name] or "").strip(),
                    "tools": toolset,
                    "middleware": middleware_factory(agent_name),
                    "skills": skills,
                }
            )
    return specs


def build_subagent_spec_map(
    *,
    system_prompts: Dict[str, str],
    skill_assets: Dict[str, Any],
    middleware_factory: Callable[[str], List[Any]],
) -> Dict[str, Dict[str, Any]]:
    return {
        str(spec.get("name") or "").strip(): spec
        for spec in build_runtime_subagent_specs(
            system_prompts=system_prompts,
            skill_assets=skill_assets,
            middleware_factory=middleware_factory,
        )
    }


def build_coordinator_skills(*, skill_assets: Dict[str, Any], core_tools: List[Any] | None = None) -> List[str]:
    toolset = list(core_tools or select_report_tools(runtime_target=RUNTIME_COORDINATOR))
    coordinator_skill_keys = get_coordinator_skill_keys()
    if not coordinator_skill_keys:
        raise ValueError("subagents.yaml must declare coordinator.skill_keys")
    return select_report_skill_sources(
        skill_assets,
        available_tool_ids=[t.name for t in toolset if str(getattr(t, "name", "") or "").strip()],
        preferred_skill_keys=coordinator_skill_keys,
        runtime_target=RUNTIME_COORDINATOR,
    )


def get_repair_agent_tiers() -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for tier, agent_names in get_tier_groups().items():
        for agent_name in agent_names:
            if agent_name == "writer":
                continue
            mapping[agent_name] = tier
    return mapping


def get_exploration_artifact_owners() -> Dict[str, str]:
    owners: Dict[str, str] = {}
    for agent_name, config in get_subagent_metadata().items():
        for path in config.get("output_files", []) or []:
            relative = str(path or "").strip().split("/state/", 1)[-1]
            if relative:
                owners[relative] = agent_name
    owners.update(_COORDINATOR_OUTPUT_FILES)
    return owners


def get_required_exploration_artifacts(mode: str) -> List[str]:
    selected_mode = str(mode or "").strip().lower() or "fast"
    output: List[str] = []
    for tier, agent_names in get_tier_groups().items():
        for agent_name in agent_names:
            if agent_name == "writer":
                continue
            if selected_mode != "research" and agent_name in _RESEARCH_ONLY_AGENTS:
                continue
            config = get_subagent_metadata_by_name(agent_name)
            for path in config.get("output_files", []) or []:
                relative = str(path or "").strip().split("/state/", 1)[-1]
                if relative and relative not in output:
                    output.append(relative)
    for relative in _COORDINATOR_OUTPUT_FILES.keys():
        if relative not in output:
            output.append(relative)
    return output


__all__ = [
    "SUPPORTED_SUBAGENT_NAMES",
    "build_coordinator_skills",
    "build_runtime_subagent_specs",
    "build_subagent_spec_map",
    "build_tier_prompt_lines",
    "build_tier_todo_specs",
    "get_exploration_artifact_owners",
    "get_repair_agent_tiers",
    "get_required_exploration_artifacts",
    "get_subagent_metadata",
    "get_subagent_metadata_by_name",
    "get_subagent_node_name",
    "get_tier_groups",
]
