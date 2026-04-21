
"""Report configs module."""
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_CONFIGS_DIR = Path(__file__).parent
_SUBAGENTS_CONFIG: Optional[Dict[str, Any]] = None


def _normalize_string_list(value: Any, *, field_name: str, agent_name: str = "") -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        scope = f"subagents.{agent_name}.{field_name}" if agent_name else field_name
        raise ValueError(f"{scope} must be a list")
    output: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            output.append(text)
    return output


def _validate_subagents_config(config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("report subagents config must be a mapping")

    normalized: Dict[str, Any] = {}
    coordinator = config.get("coordinator") if isinstance(config.get("coordinator"), dict) else {}
    normalized["coordinator"] = {
        "skill_keys": _normalize_string_list(coordinator.get("skill_keys"), field_name="coordinator.skill_keys"),
    }

    raw_subagents = config.get("subagents")
    if raw_subagents is None:
        raw_subagents = {}
    if not isinstance(raw_subagents, dict):
        raise ValueError("subagents must be a mapping")

    normalized_subagents: Dict[str, Dict[str, Any]] = {}
    for agent_name, payload in raw_subagents.items():
        name = str(agent_name or "").strip()
        if not name:
            raise ValueError("subagents keys must be non-empty")
        if not isinstance(payload, dict):
            raise ValueError(f"subagents.{name} must be a mapping")
        if "tier" not in payload:
            raise ValueError(f"subagents.{name}.tier is required")
        try:
            tier = int(payload.get("tier"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"subagents.{name}.tier must be an integer") from exc
        normalized_payload = {
            "name": str(payload.get("name") or name).strip() or name,
            "description": str(payload.get("description") or "").strip(),
            "tier": tier,
            "skill_keys": _normalize_string_list(payload.get("skill_keys"), field_name="skill_keys", agent_name=name),
            "output_files": _normalize_string_list(payload.get("output_files"), field_name="output_files", agent_name=name),
            "output_globs": _normalize_string_list(payload.get("output_globs"), field_name="output_globs", agent_name=name),
        }
        if not normalized_payload["output_files"] and not normalized_payload["output_globs"]:
            raise ValueError(f"subagents.{name} must declare output_files or output_globs")
        normalized_subagents[name] = normalized_payload

    normalized["subagents"] = normalized_subagents
    return normalized


def _load_subagents_config() -> Dict[str, Any]:
    """Load subagents configuration from YAML file."""
    global _SUBAGENTS_CONFIG
    if _SUBAGENTS_CONFIG is None:
        config_path = _CONFIGS_DIR / "subagents.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                _SUBAGENTS_CONFIG = _validate_subagents_config(yaml.safe_load(f) or {})
        else:
            _SUBAGENTS_CONFIG = _validate_subagents_config({})
    return _SUBAGENTS_CONFIG


def get_subagent_config(agent_name: str) -> Dict[str, Any]:
    """Get configuration for a specific subagent."""
    config = _load_subagents_config()
    subagents = config.get("subagents", {})
    return subagents.get(agent_name, {})


def get_all_subagent_configs() -> Dict[str, Dict[str, Any]]:
    """Get all subagent configurations."""
    config = _load_subagents_config()
    return config.get("subagents", {})


def get_coordinator_skill_keys() -> list:
    """Get coordinator skill keys."""
    config = _load_subagents_config()
    coordinator = config.get("coordinator", {})
    return coordinator.get("skill_keys", [])


def get_subagent_skill_keys(agent_name: str) -> list:
    """Get skill keys for a specific subagent."""
    agent_config = get_subagent_config(agent_name)
    return agent_config.get("skill_keys", [])


def _format_path_templates(values: list, *, path_tokens: Optional[Dict[str, Any]] = None) -> list:
    tokens = {str(key): str(value) for key, value in (path_tokens or {}).items() if str(key or "").strip()}
    output = []
    for item in values or []:
        template = str(item or "").strip()
        if not template:
            continue
        if tokens:
            try:
                template = template.format(**tokens)
            except Exception:
                pass
        output.append(template)
    return output


def get_subagent_output_files(agent_name: str, *, path_tokens: Optional[Dict[str, Any]] = None) -> list:
    """Get output files for a specific subagent."""
    agent_config = get_subagent_config(agent_name)
    return _format_path_templates(agent_config.get("output_files", []), path_tokens=path_tokens)


def get_subagent_output_globs(agent_name: str, *, path_tokens: Optional[Dict[str, Any]] = None) -> list:
    """Get output globs for a specific subagent."""
    agent_config = get_subagent_config(agent_name)
    return _format_path_templates(agent_config.get("output_globs", []), path_tokens=path_tokens)


def get_subagents_by_tier(tier: int) -> list:
    """Get all subagent names for a specific tier."""
    config = _load_subagents_config()
    subagents = config.get("subagents", {})
    items = [
        (name, cfg)
        for name, cfg in subagents.items()
        if isinstance(cfg, dict) and int(cfg.get("tier") or -1) == int(tier)
    ]
    return [name for name, _cfg in sorted(items, key=lambda item: (int(item[1].get("tier") or 0), item[0]))]


def get_all_subagents_by_tier() -> Dict[int, List[str]]:
    """Get all configured subagents grouped by tier."""
    config = _load_subagents_config()
    grouped: Dict[int, List[str]] = {}
    for name, cfg in (config.get("subagents") or {}).items():
        if not isinstance(cfg, dict):
            continue
        tier = int(cfg.get("tier") or 0)
        grouped.setdefault(tier, []).append(name)
    return {
        tier: sorted(names)
        for tier, names in sorted(grouped.items(), key=lambda item: item[0])
    }


__all__ = [
    "get_subagent_config",
    "get_all_subagent_configs",
    "get_coordinator_skill_keys",
    "get_subagent_skill_keys",
    "get_subagent_output_files",
    "get_subagent_output_globs",
    "get_subagents_by_tier",
    "get_all_subagents_by_tier",
]
