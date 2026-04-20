
"""Report configs module."""
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

_CONFIGS_DIR = Path(__file__).parent
_SUBAGENTS_CONFIG: Optional[Dict[str, Any]] = None


def _load_subagents_config() -> Dict[str, Any]:
    """Load subagents configuration from YAML file."""
    global _SUBAGENTS_CONFIG
    if _SUBAGENTS_CONFIG is None:
        config_path = _CONFIGS_DIR / "subagents.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                _SUBAGENTS_CONFIG = yaml.safe_load(f) or {}
        else:
            _SUBAGENTS_CONFIG = {}
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
    return [name for name, cfg in subagents.items() if cfg.get("tier") == tier]


__all__ = [
    "get_subagent_config",
    "get_all_subagent_configs",
    "get_coordinator_skill_keys",
    "get_subagent_skill_keys",
    "get_subagent_output_files",
    "get_subagent_output_globs",
    "get_subagents_by_tier",
]
