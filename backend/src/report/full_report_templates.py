from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple


TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates" / "full_report"
DEFAULT_TEMPLATE_ID = "public_hotspot"
TEMPLATE_FILE_MAP = {
    "public_hotspot": "public_hotspot.md",
    "policy_dynamics": "policy_dynamics.md",
    "crisis_response": "crisis_response.md",
}

_TEMPLATE_EXTRA_HINTS: Dict[str, List[str]] = {
    "public_hotspot": ["热点", "公共", "社会", "争议", "讨论", "话题", "舆论", "扩散"],
    "policy_dynamics": ["政策", "新规", "条例", "通知", "监管", "行业", "治理", "控烟", "禁烟", "专项整治"],
    "crisis_response": ["危机", "突发", "事故", "风波", "应急", "公关", "投诉", "爆雷", "伤亡"],
}


def _normalize_template_id(value: str) -> str:
    text = str(value or "").strip()
    return text if text in TEMPLATE_FILE_MAP else DEFAULT_TEMPLATE_ID


def _template_file_map() -> Dict[str, str]:
    discovered = {
        path.stem: path.name
        for path in sorted(TEMPLATE_ROOT.glob("*.md"))
        if path.is_file()
    }
    return discovered or dict(TEMPLATE_FILE_MAP)


def _normalize_section_payload(title: str, summary: str) -> Dict[str, str]:
    safe_title = str(title or "").strip()
    safe_summary = str(summary or "").strip()
    section_id = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", safe_title.lower()).strip("_") or "section"
    first_sentence = re.split(r"[。！？.!?]", safe_summary)[0].strip() if safe_summary else ""
    writing_instruction = first_sentence[:120] if first_sentence else ""
    return {
        "section_id": section_id,
        "title": safe_title,
        "summary": safe_summary,
        "writing_instruction": writing_instruction,
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
    return [_normalize_section_payload(item.get("title", ""), item.get("summary", "")) for item in sections]


def _scene_metadata(template_id: str) -> Dict[str, Any]:
    from .scene_profile import load_full_report_scene_profile

    profile = load_full_report_scene_profile(template_id)
    return profile if isinstance(profile, dict) else {}


def list_full_report_templates() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for template_id, filename in _template_file_map().items():
        template = load_full_report_template(template_id)
        entries.append(template)
    return entries


def _report_ir_signals(report_ir: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = report_ir if isinstance(report_ir, dict) else {}
    risk_register = payload.get("risk_register") if isinstance(payload.get("risk_register"), dict) else {}
    unresolved_points = payload.get("unresolved_points") if isinstance(payload.get("unresolved_points"), dict) else {}
    agenda_frame_map = payload.get("agenda_frame_map") if isinstance(payload.get("agenda_frame_map"), dict) else {}
    mechanism_summary = payload.get("mechanism_summary") if isinstance(payload.get("mechanism_summary"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    topic_scope = payload.get("topic_scope") if isinstance(payload.get("topic_scope"), dict) else {}
    keywords = [str(item).strip() for item in (topic_scope.get("keywords") or []) if str(item or "").strip()]
    return {
        "risk_count": len(risk_register.get("risks") or []),
        "unresolved_count": len(unresolved_points.get("items") or []),
        "agenda_issue_count": len(agenda_frame_map.get("issues") or []),
        "agenda_frame_count": len(agenda_frame_map.get("frames") or []),
        "mechanism_path_count": len(mechanism_summary.get("amplification_paths") or []),
        "keywords": keywords,
        "topic_label": str(meta.get("topic_label") or meta.get("topic_identifier") or "").strip(),
    }


def _score_template_match(
    template_id: str,
    *,
    topic_label: str = "",
    title: str = "",
    subtitle: str = "",
    mode: str = "",
    report_ir: Dict[str, Any] | None = None,
) -> Tuple[float, List[str]]:
    profile = _scene_metadata(template_id)
    selection_hints = [
        str(item).strip()
        for item in (
            profile.get("selection_hints")
            or profile.get("keyword_hints")
            or []
        )
        if str(item or "").strip()
    ]
    hints = list(dict.fromkeys(selection_hints + _TEMPLATE_EXTRA_HINTS.get(template_id, [])))
    signals = _report_ir_signals(report_ir)
    text_haystack = " ".join(
        [
            str(topic_label or "").strip(),
            str(title or "").strip(),
            str(subtitle or "").strip(),
            str(mode or "").strip(),
            str(signals.get("topic_label") or "").strip(),
            " ".join(signals.get("keywords") or []),
        ]
    ).lower()
    score = 0.0
    reasons: List[str] = []
    matched_hints = [hint for hint in hints if hint and hint.lower() in text_haystack]
    if matched_hints:
        score += min(8.0, 2.0 * len(matched_hints))
        reasons.append(f"文本命中模板特征词: {', '.join(matched_hints[:4])}")

    risk_count = int(signals.get("risk_count") or 0)
    unresolved_count = int(signals.get("unresolved_count") or 0)
    agenda_issue_count = int(signals.get("agenda_issue_count") or 0)
    mechanism_path_count = int(signals.get("mechanism_path_count") or 0)

    if template_id == "policy_dynamics":
        policy_hits = [hint for hint in _TEMPLATE_EXTRA_HINTS["policy_dynamics"] if hint.lower() in text_haystack]
        if policy_hits:
            score += 6.0
            reasons.append(f"存在政策/治理信号: {', '.join(policy_hits[:3])}")
        if agenda_issue_count or mechanism_path_count:
            score += 1.5
            reasons.append("已具备议题/传播结构，可支撑政策行业模板写作")
    elif template_id == "crisis_response":
        crisis_hits = [hint for hint in _TEMPLATE_EXTRA_HINTS["crisis_response"] if hint.lower() in text_haystack]
        if crisis_hits:
            score += 6.0
            reasons.append(f"存在危机/突发信号: {', '.join(crisis_hits[:3])}")
        if risk_count >= 4:
            score += 4.0
            reasons.append(f"风险项较多（{risk_count}），偏向危机模板")
        elif unresolved_count >= 3:
            score += 1.5
            reasons.append(f"待核验点较多（{unresolved_count}），需要危机化边界表达")
    elif template_id == "public_hotspot":
        hotspot_hits = [hint for hint in _TEMPLATE_EXTRA_HINTS["public_hotspot"] if hint.lower() in text_haystack]
        if hotspot_hits:
            score += 4.0
            reasons.append(f"存在公共热点讨论信号: {', '.join(hotspot_hits[:3])}")
        if not reasons:
            score += 1.0
            reasons.append("作为默认公共议题模板保底")

    if template_id != "crisis_response" and risk_count <= 2:
        score += 0.5
    if template_id == "public_hotspot" and risk_count and not matched_hints:
        score -= 0.5
    return score, reasons


def choose_best_template(
    *,
    topic_label: str = "",
    title: str = "",
    subtitle: str = "",
    mode: str = "",
    report_ir: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    candidates = list_full_report_templates()
    scored: List[Tuple[float, Dict[str, Any], List[str]]] = []
    for candidate in candidates:
        template_id = str(candidate.get("template_id") or "").strip() or DEFAULT_TEMPLATE_ID
        score, reasons = _score_template_match(
            template_id,
            topic_label=topic_label,
            title=title,
            subtitle=subtitle,
            mode=mode,
            report_ir=report_ir,
        )
        scored.append((score, candidate, reasons))
    if not scored:
        return load_full_report_template(DEFAULT_TEMPLATE_ID)
    scored.sort(
        key=lambda item: (
            float(item[0]),
            1 if str((item[1] or {}).get("template_id") or "") == DEFAULT_TEMPLATE_ID else 0,
        ),
        reverse=True,
    )
    score, selected, reasons = scored[0]
    scene_profile = _scene_metadata(str(selected.get("template_id") or DEFAULT_TEMPLATE_ID))
    return {
        **selected,
        "scene_id": str(scene_profile.get("scene_id") or selected.get("template_id") or DEFAULT_TEMPLATE_ID).strip(),
        "scene_label": str(scene_profile.get("scene_label") or "").strip(),
        "score": round(float(score or 0.0), 4),
        "matched_reasons": reasons,
        "selection_context": {
            "topic_label": str(topic_label or "").strip(),
            "title": str(title or "").strip(),
            "subtitle": str(subtitle or "").strip(),
            "mode": str(mode or "").strip(),
            "report_ir_signals": _report_ir_signals(report_ir),
        },
    }


def load_full_report_template(scene_id: str | None = None) -> Dict[str, Any]:
    file_map = _template_file_map()
    template_id = _normalize_template_id(str(scene_id or "").strip() or DEFAULT_TEMPLATE_ID)
    filename = file_map.get(template_id) or TEMPLATE_FILE_MAP.get(template_id) or TEMPLATE_FILE_MAP[DEFAULT_TEMPLATE_ID]
    path = TEMPLATE_ROOT / filename
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
    template_key = (
        profile.get("template_id")
        or profile.get("scene_id")
        or DEFAULT_TEMPLATE_ID
    )
    profile.update(load_full_report_template(str(template_key or "").strip()))
    return profile
