from __future__ import annotations

from typing import Any, Dict, List


def render_markdown(payload: Dict[str, Any]) -> str:
    conclusion = payload.get("conclusion") if isinstance(payload.get("conclusion"), dict) else {}
    timeline = payload.get("timeline") if isinstance(payload.get("timeline"), list) else []
    stance = payload.get("stance_matrix") if isinstance(payload.get("stance_matrix"), list) else []
    risks = payload.get("risk_judgement") if isinstance(payload.get("risk_judgement"), list) else []
    actions = payload.get("suggested_actions") if isinstance(payload.get("suggested_actions"), list) else []
    propagation = payload.get("propagation_features") if isinstance(payload.get("propagation_features"), list) else []
    unverified = payload.get("unverified_points") if isinstance(payload.get("unverified_points"), list) else []
    citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    lines: List[str] = [
        f"# {str(task.get('topic_label') or task.get('topic_identifier') or '专题报告').strip()}",
        "",
        f"> 区间：{str(task.get('start') or '').strip()} -> {str(task.get('end') or '').strip()} | 模式：{str(task.get('mode') or '').strip()}",
        "",
        "## 结论摘要",
        str(conclusion.get("executive_summary") or "暂无摘要。").strip(),
        "",
    ]
    findings = [str(item).strip() for item in (conclusion.get("key_findings") or []) if str(item or "").strip()]
    if findings:
        lines.append("### 核心发现")
        lines.extend([f"- {item}" for item in findings[:8]])
        lines.append("")
    if timeline:
        lines.append("## 时间线")
        for item in timeline[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(f"### {str(item.get('date') or '').strip()} {str(item.get('title') or '').strip()}".strip())
            description = str(item.get("description") or "").strip()
            if description:
                lines.append(description)
            impact = str(item.get("impact") or "").strip()
            if impact:
                lines.append(f"- 影响：{impact}")
            lines.append("")
    if stance:
        lines.append("## 立场矩阵")
        for item in stance[:12]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- **{str(item.get('subject') or '').strip()}**：{str(item.get('stance') or '').strip()}。{str(item.get('summary') or '').strip()}"
            )
        lines.append("")
    if propagation:
        lines.append("## 传播结构")
        for item in propagation[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- **{str(item.get('dimension') or '').strip()}**：{str(item.get('finding') or '').strip()}")
        lines.append("")
    if risks:
        lines.append("## 风险判断")
        for item in risks[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- **{str(item.get('label') or '').strip()}**（{str(item.get('level') or '').strip()}）：{str(item.get('summary') or '').strip()}"
            )
        lines.append("")
    if actions:
        lines.append("## 建议动作")
        for item in actions[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- **{str(item.get('action') or '').strip()}**：{str(item.get('rationale') or '').strip()}")
        lines.append("")
    if unverified:
        lines.append("## 待核验点")
        for item in unverified[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {str(item.get('statement') or '').strip()}：{str(item.get('reason') or '').strip()}")
        lines.append("")
    if citations:
        lines.append("## 引用索引")
        for item in citations[:20]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            prefix = f"- [{str(item.get('citation_id') or '').strip()}] {title}".strip()
            if url:
                prefix += f" ({url})"
            lines.append(prefix)
            if snippet:
                lines.append(f"  {snippet}")
        lines.append("")
    return "\n".join(lines).strip()


def build_structured_digest(payload: Dict[str, Any]) -> Dict[str, Any]:
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    conclusion = payload.get("conclusion") if isinstance(payload.get("conclusion"), dict) else {}
    return {
        "topic": str(task.get("topic_label") or task.get("topic_identifier") or "").strip(),
        "range": {
            "start": str(task.get("start") or "").strip(),
            "end": str(task.get("end") or "").strip(),
        },
        "summary": str(conclusion.get("executive_summary") or "").strip(),
        "key_findings": [str(item).strip() for item in (conclusion.get("key_findings") or []) if str(item or "").strip()][:6],
        "key_risks": [str(item).strip() for item in (conclusion.get("key_risks") or []) if str(item or "").strip()][:6],
        "counts": {
            "timeline": len(payload.get("timeline") or []),
            "subjects": len(payload.get("subjects") or []),
            "evidence": len(payload.get("key_evidence") or []),
            "conflicts": len(payload.get("conflict_points") or []),
            "propagation": len(payload.get("propagation_features") or []),
            "risks": len(payload.get("risk_judgement") or []),
            "actions": len(payload.get("suggested_actions") or []),
            "citations": len(payload.get("citations") or []),
        },
    }


def build_full_payload(structured_payload: Dict[str, Any], markdown: str, *, cache_version: int) -> Dict[str, Any]:
    task = structured_payload.get("task") if isinstance(structured_payload.get("task"), dict) else {}
    title = str(task.get("topic_label") or task.get("topic_identifier") or "AI 完整报告").strip() or "AI 完整报告"
    return {
        "title": title,
        "subtitle": "结构化研判生成的正式文稿",
        "rangeText": f"{str(task.get('start') or '').strip()} -> {str(task.get('end') or '').strip()}",
        "markdown": str(markdown or "").strip(),
        "assets": [],
        "meta": {
            "cache_version": int(cache_version),
            "thread_id": str(task.get("thread_id") or "").strip(),
            "structured_digest": build_structured_digest(structured_payload),
        },
    }
