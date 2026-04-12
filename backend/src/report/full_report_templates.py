from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List


TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates" / "full_report"
DEFAULT_TEMPLATE_ID = "public_hotspot"
TEMPLATE_FILE_MAP = {
    "public_hotspot": "public_hotspot.md",
    "policy_dynamics": "policy_dynamics.md",
    "crisis_response": "crisis_response.md",
}


def _parse_template_sections(markdown: str) -> List[Dict[str, str]]:
    sections: List[Dict[str, str]] = []
    current: Dict[str, str] | None = None
    for raw_line in str(markdown or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        if line.startswith("## "):
            if current:
                sections.append(current)
            title = line[3:].strip()
            current = {"title": title, "summary": ""}
            continue
        if current and not current.get("summary"):
            plain = re.sub(r"^[*-]\s*", "", line).strip()
            if plain:
                current["summary"] = plain
    if current:
        sections.append(current)
    return sections


def load_full_report_template(scene_id: str | None = None) -> Dict[str, Any]:
    key = str(scene_id or "").strip() or DEFAULT_TEMPLATE_ID
    template_id = key if key in TEMPLATE_FILE_MAP else DEFAULT_TEMPLATE_ID
    path = TEMPLATE_ROOT / TEMPLATE_FILE_MAP[template_id]
    markdown = path.read_text(encoding="utf-8") if path.exists() else ""
    title_match = re.search(r"^\s*#\s+(.+?)\s*$", markdown, flags=re.M)
    return {
        "template_id": template_id,
        "template_name": path.stem,
        "template_path": str(path),
        "template_markdown": markdown,
        "template_title": str(title_match.group(1)).strip() if title_match else "",
        "template_sections": _parse_template_sections(markdown),
    }


def attach_full_report_template(scene_profile: Dict[str, Any]) -> Dict[str, Any]:
    profile = deepcopy(scene_profile) if isinstance(scene_profile, dict) else {}
    profile.update(load_full_report_template(profile.get("scene_id")))
    return profile
