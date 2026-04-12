from __future__ import annotations

from typing import Any, Dict

from .loader import resolve_report_skill


def load_sentiment_analysis_methodology_skill(topic: str = "") -> Dict[str, Any]:
    return resolve_report_skill("sentiment_analysis_methodology", topic=topic)


__all__ = ["load_sentiment_analysis_methodology_skill"]
