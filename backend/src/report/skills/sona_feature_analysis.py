from __future__ import annotations

from typing import Any, Dict

from .loader import resolve_report_skill


def load_sona_feature_analysis_skill(topic: str = "") -> Dict[str, Any]:
    return resolve_report_skill("sona_feature_analysis", topic=topic)


__all__ = ["load_sona_feature_analysis_skill"]
