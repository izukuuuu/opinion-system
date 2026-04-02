from __future__ import annotations

from typing import Any, Dict

from .sona_feature_analysis import load_sona_feature_analysis_skill


def load_report_skill_context(topic: str = "") -> Dict[str, Any]:
    return load_sona_feature_analysis_skill(topic)


__all__ = ["load_report_skill_context"]
