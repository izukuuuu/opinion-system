"""
Report knowledge loader for built-in report methodology assets.

The current structured report pipeline is not an agent workflow, but it can still
reuse the strongest part of Sona's design: methodology-aware context assembly.
This module reads knowledge assets that are maintained inside
``backend/knowledge_base/report/sentiment_analysis_methodology``.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .tools.knowledge_base_tools import (
    append_expert_judgement as append_expert_judgement_tool,
    build_event_reference_links as build_event_reference_links_tool,
    get_sentiment_analysis_framework as get_sentiment_analysis_framework_tool,
    get_sentiment_case_template as get_sentiment_case_template_tool,
    get_sentiment_theories as get_sentiment_theories_tool,
    get_youth_sentiment_insight as get_youth_sentiment_insight_tool,
    search_reference_insights as search_reference_insights_tool,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SONA_ROOT = REPO_ROOT / "backend" / "knowledge_base" / "report" / "sentiment_analysis_methodology"
SONA_METHOD_DIR = SONA_ROOT / "舆情深度分析"
SONA_REFERENCE_DIR = SONA_METHOD_DIR / "references"
SONA_EXPERT_NOTES_DIR = SONA_REFERENCE_DIR / "expert_notes"

THEORY_CANDIDATES = [
    SONA_METHOD_DIR / "舆情分析方法论.md",
]
RESEARCH_CANDIDATES = [
    SONA_METHOD_DIR / "舆情分析深度研究资料.md",
]
OPINION_CANDIDATES = [
    SONA_METHOD_DIR / "舆情分析可参考的一些深度观点.md",
]
YOUTH_CANDIDATES = [
    SONA_METHOD_DIR / "中国青年网民社会心态调查报告（2024）.md",
]

TEXT_SUFFIX = {".md", ".txt", ".json", ".jsonl", ".csv"}
KNOWN_THEORY_NAMES = [
    "生命周期规律",
    "议程设置规律",
    "沉默螺旋规律",
    "框架理论",
    "风险传播理论",
    "社会燃烧规律",
    "博弈均衡规律",
]

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _truncate(text: str, max_chars: int) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "..."


def _first_existing(candidates: List[Path]) -> Optional[Path]:
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _tokenize(text: str, max_tokens: int = 40) -> List[str]:
    value = str(text or "").strip()
    if not value:
        return []

    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_#+.-]{2,}", value)
    tokens: List[str] = []
    for part in parts:
        if re.search(r"[\u4e00-\u9fff]", part):
            tokens.append(part)
            fragment = part[:12]
            for size in (2, 3, 4):
                for index in range(0, max(0, len(fragment) - size + 1)):
                    tokens.append(fragment[index : index + size])
        else:
            tokens.append(part.lower())

    out: List[str] = []
    seen = set()
    for token in sorted(tokens, key=len, reverse=True):
        key = token.lower()
        if len(token) < 2 or key in seen:
            continue
        seen.add(key)
        out.append(token)
        if len(out) >= max_tokens:
            break
    return out


def _split_paragraphs(text: str) -> List[str]:
    blocks = re.split(r"\n\s*\n", str(text or "").replace("\r\n", "\n"))
    out: List[str] = []
    for block in blocks:
        compact = re.sub(r"\s+", " ", block).strip()
        if len(compact) >= 20:
            out.append(compact)
    return out


def _score_block(block: str, tokens: List[str]) -> float:
    if not block or not tokens:
        return 0.0
    lowered = block.lower()
    score = 0.0
    for token in tokens:
        if token.lower() in lowered:
            score += 1.0 + min(len(token), 10) * 0.08
    return score


def _iter_reference_files(max_files: int = 220) -> List[Path]:
    files: List[Path] = []
    for directory in [SONA_REFERENCE_DIR, SONA_EXPERT_NOTES_DIR, SONA_METHOD_DIR]:
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIX:
                continue
            if path.name.startswith("."):
                continue
            if path.name.lower().startswith("readme"):
                continue
            files.append(path)
            if len(files) >= max_files:
                return files
    return files


def _extract_key_sections(content: str) -> str:
    if not content:
        return ""

    section_markers = [
        "舆情分析框架",
        "舆情分析核心维度",
        "舆情基本要素",
        "舆情生命周期",
        "舆情规律",
        "沉默螺旋",
        "议程设置",
        "框架理论",
        "风险传播",
    ]

    key_sections: List[str] = []
    lines = content.splitlines()
    current_title = ""
    current_lines: List[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        if not current_title or not current_lines:
            current_lines = []
            return
        body = "\n".join(current_lines[:24]).strip()
        if body:
            key_sections.append(f"### {current_title}\n{body}")
        current_lines = []

    for line in lines:
        stripped = line.strip()
        is_header = False
        for marker in section_markers:
            if marker in stripped and (stripped.startswith("#") or len(stripped) <= 48):
                is_header = True
                break
        if is_header:
            flush()
            current_title = stripped.replace("#", "").replace("*", "").strip()
            continue
        if current_title:
            current_lines.append(line)

    flush()
    if key_sections:
        return "## 舆情方法论\n\n" + "\n\n".join(key_sections[:8])
    return "## 舆情方法论\n\n" + _truncate(content, 3000)


def _search_local_references(topic: str, max_items: int = 8) -> List[Dict[str, Any]]:
    query = str(topic or "").strip()
    if not query:
        return []

    tokens = _tokenize(query, max_tokens=40)
    if not tokens:
        return []

    scored: List[Dict[str, Any]] = []
    for path in _iter_reference_files(max_files=260):
        text = _read_text(path)
        if not text:
            continue
        for block in _split_paragraphs(text):
            score = _score_block(block, tokens)
            if score <= 0:
                continue
            scored.append(
                {
                    "title": path.name,
                    "source": str(path),
                    "score": round(score, 4),
                    "snippet": _truncate(block, 320),
                }
            )

    scored.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return scored[: max(1, max_items)]


def _format_reference_snippets(items: List[Dict[str, Any]], max_items: int = 6) -> str:
    if not items:
        return ""
    lines = ["## 事件定向参考片段"]
    for item in items[:max_items]:
        snippet = str(item.get("snippet") or "").strip()
        title = str(item.get("title") or "").strip()
        if snippet:
            lines.append(f"- {snippet}\n  来源: {title}")
    return "\n".join(lines)


def _format_reference_links(items: List[Dict[str, Any]], max_items: int = 4) -> str:
    if not items:
        return ""
    lines = ["## 外部检索入口"]
    for item in items[:max_items]:
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        usage = str(item.get("usage") or "").strip()
        if not (name and url):
            continue
        lines.append(f"- {name}: {url}" + (f"（{usage}）" if usage else ""))
    return "\n".join(lines)


def _guess_case_type(topic: str) -> str:
    text = str(topic or "").strip()
    commercial_markers = [
        "品牌",
        "企业",
        "公司",
        "产品",
        "营销",
        "门店",
        "汽车",
        "餐饮",
        "平台",
        "外卖",
        "电商",
        "手机",
    ]
    if any(marker in text for marker in commercial_markers):
        return "商业事件"
    return "社会事件"


def _invoke_tool(tool_obj: Any, payload: Dict[str, Any]) -> str:
    try:
        if hasattr(tool_obj, "invoke"):
            result = tool_obj.invoke(payload)
        elif callable(tool_obj):
            result = tool_obj(**payload)
        else:
            return ""
        return str(result or "").strip()
    except Exception:
        return ""


def _parse_reference_hits(raw: str) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []

    out: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("snippet") or "").strip()
        title = str(item.get("title") or "").strip()
        if not snippet:
            continue
        out.append(
            {
                "title": title,
                "source": str(item.get("source") or "").strip(),
                "score": float(item.get("score") or 0.0),
                "snippet": _truncate(snippet, 320),
            }
        )
    return out


def _parse_links(raw: str) -> List[Dict[str, str]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    links = payload.get("links") if isinstance(payload, dict) else None
    if not isinstance(links, list):
        return []
    out: List[Dict[str, str]] = []
    for item in links:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not (name and url):
            continue
        out.append(
            {
                "name": name,
                "url": url,
                "usage": str(item.get("usage") or "").strip(),
            }
        )
    return out


def _build_fallback_links(topic: str) -> List[Dict[str, str]]:
    query = quote(str(topic or "").strip() or "舆情事件")
    return [
        {
            "name": "微博智搜",
            "url": f"https://s.weibo.com/aisearch?q={query}&Refer=weibo_aisearch",
            "usage": "查看微博智搜聚合观点与相关讨论",
        },
        {
            "name": "微博搜索",
            "url": f"https://s.weibo.com/weibo?q={query}",
            "usage": "查看微博原始帖子与热度讨论",
        },
        {
            "name": "百度资讯",
            "url": f"https://www.baidu.com/s?wd={query}%20舆情%20评论",
            "usage": "查看媒体评论与报道",
        },
    ]


def _pick_theory_hints(summary: str, max_items: int = 4) -> List[str]:
    text = str(summary or "")
    picked: List[str] = []
    for theory_name in KNOWN_THEORY_NAMES:
        if theory_name in text:
            picked.append(theory_name)
        if len(picked) >= max_items:
            break
    return picked


def _load_expert_notes_from_local(topic: str, max_items: int = 4) -> List[Dict[str, Any]]:
    query = str(topic or "").strip()
    if not query or not SONA_EXPERT_NOTES_DIR.exists():
        return []

    tokens = _tokenize(query, max_tokens=40)
    if not tokens:
        return []

    scored: List[Dict[str, Any]] = []
    for path in sorted(SONA_EXPERT_NOTES_DIR.rglob("*.md")):
        text = _read_text(path)
        if not text:
            continue
        for block in _split_paragraphs(text):
            score = _score_block(block, tokens)
            if score <= 0:
                continue
            scored.append(
                {
                    "title": path.name,
                    "source": str(path),
                    "score": round(score, 4),
                    "snippet": _truncate(block, 320),
                }
            )

    scored.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return scored[: max(1, max_items)]


def _extract_dynamic_theories(raw_text: str, max_items: int = 4) -> List[str]:
    if not raw_text:
        return []
    picked: List[str] = []
    for theory_name in KNOWN_THEORY_NAMES:
        if theory_name in raw_text and theory_name not in picked:
            picked.append(theory_name)
        if len(picked) >= max_items:
            break
    if picked:
        return picked

    lines = [line.strip("-• \t") for line in str(raw_text or "").splitlines()]
    for line in lines:
        if len(line) > 30:
            continue
        if any(marker in line for marker in ("理论", "规律", "框架")) and line not in picked:
            picked.append(line)
        if len(picked) >= max_items:
            break
    return picked


def search_report_reference_insights(topic: Optional[str], limit: int = 6) -> List[Dict[str, Any]]:
    topic_text = str(topic or "").strip()
    if not topic_text:
        return []
    safe_limit = max(1, min(int(limit or 6), 12))
    hits = _parse_reference_hits(
        _invoke_tool(search_reference_insights_tool, {"query": topic_text, "limit": safe_limit})
    )
    if hits:
        return hits[:safe_limit]
    return _search_local_references(topic_text, max_items=safe_limit)


def build_report_reference_links(topic: Optional[str]) -> List[Dict[str, str]]:
    topic_text = str(topic or "").strip()
    if not topic_text:
        return []
    links = _parse_links(_invoke_tool(build_event_reference_links_tool, {"topic": topic_text}))
    if links:
        return links[:4]
    return _build_fallback_links(topic_text)


def get_dynamic_theories(topic: Optional[str], limit: int = 4) -> List[str]:
    topic_text = str(topic or "").strip()
    if not topic_text:
        return []
    safe_limit = max(1, min(int(limit or 4), 6))
    raw_text = _invoke_tool(get_sentiment_theories_tool, {"topic": topic_text})
    if not raw_text:
        theory_path = _first_existing(THEORY_CANDIDATES)
        raw_text = _read_text(theory_path) if theory_path else ""
    return _extract_dynamic_theories(raw_text, max_items=safe_limit)


def load_report_expert_notes(topic: Optional[str], limit: int = 4) -> List[Dict[str, Any]]:
    topic_text = str(topic or "").strip()
    if not topic_text:
        return []
    safe_limit = max(1, min(int(limit or 4), 8))
    return _load_expert_notes_from_local(topic_text, max_items=safe_limit)


def append_report_expert_judgement(
    topic: str,
    judgement: str,
    *,
    tags: str = "",
    source: str = "expert",
) -> Dict[str, Any]:
    topic_text = str(topic or "").strip()
    judgement_text = str(judgement or "").strip()
    if not topic_text or not judgement_text:
        return {"ok": False, "error": "topic 与 judgement 不能为空"}

    raw = _invoke_tool(
        append_expert_judgement_tool,
        {
            "topic": topic_text,
            "judgement": judgement_text,
            "tags": tags,
            "source": source,
        },
    )
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"ok": False, "error": raw}

    SONA_EXPERT_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", topic_text)[:60].strip("_") or "expert_note"
    file_path = SONA_EXPERT_NOTES_DIR / f"{datetime.now().strftime('%Y%m%d')}_{slug}.md"
    lines = [
        f"## {topic_text}",
        f"- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 来源: {source}",
    ]
    if str(tags or "").strip():
        lines.append(f"- 标签: {str(tags).strip()}")
    lines.extend(["", "### 研判内容", judgement_text, "", "---", ""])
    try:
        with file_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write("\n".join(lines))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "path": str(file_path),
        "topic": topic_text,
        "message": "专家研判已写入参考库。",
    }


def load_report_knowledge(topic: Optional[str] = None) -> Dict[str, Any]:
    topic_text = str(topic or "").strip() or "舆情事件"
    framework = _invoke_tool(get_sentiment_analysis_framework_tool, {"topic": topic_text})
    theories = _invoke_tool(get_sentiment_theories_tool, {"topic": topic_text})
    case_template = _invoke_tool(
        get_sentiment_case_template_tool,
        {"case_type": _guess_case_type(topic_text)},
    )
    youth_insight = _invoke_tool(get_youth_sentiment_insight_tool, {})
    reference_hits: List[Dict[str, Any]] = []
    reference_links: List[Dict[str, str]] = []
    dynamic_theories: List[str] = []
    expert_notes: List[Dict[str, Any]] = []
    reference_hits = search_report_reference_insights(topic_text, limit=6)
    reference_links = build_report_reference_links(topic_text)
    dynamic_theories = get_dynamic_theories(topic_text, limit=4)
    expert_notes = load_report_expert_notes(topic_text, limit=4)

    content_parts: List[str] = []

    theory_path = _first_existing(THEORY_CANDIDATES)
    if theory_path:
        theory_text = _read_text(theory_path)
        if theory_text:
            content_parts.append(_extract_key_sections(theory_text))

    research_path = _first_existing(RESEARCH_CANDIDATES)
    if research_path:
        research_text = _read_text(research_path)
        if research_text:
            content_parts.append("## 深度研究资料\n\n" + _truncate(research_text, 2200))

    opinion_path = _first_existing(OPINION_CANDIDATES)
    if opinion_path:
        opinion_text = _read_text(opinion_path)
        if opinion_text:
            content_parts.append("## 深度观点摘录\n\n" + _truncate(opinion_text, 1800))

    youth_path = _first_existing(YOUTH_CANDIDATES)
    if youth_path:
        youth_text = _read_text(youth_path)
        if youth_text:
            content_parts.append("## 青年网民心态参考\n\n" + _truncate(youth_text, 1800))

    if framework:
        content_parts.append("## 分析框架\n\n" + _truncate(framework, 2200))
    if theories:
        content_parts.append("## 理论要点\n\n" + _truncate(theories, 2600))
    if case_template:
        content_parts.append("## 报告模板\n\n" + _truncate(case_template, 1600))
    if youth_insight:
        content_parts.append("## 青年洞察\n\n" + _truncate(youth_insight, 1600))

    reference_block = _format_reference_snippets(reference_hits, max_items=6)
    if reference_block:
        content_parts.append(reference_block)

    links_block = _format_reference_links(reference_links, max_items=4)
    if links_block:
        content_parts.append(links_block)

    if dynamic_theories:
        content_parts.append("## 动态理论匹配\n\n" + "\n".join(f"- {item}" for item in dynamic_theories))

    expert_notes_block = _format_reference_snippets(expert_notes, max_items=4)
    if expert_notes_block:
        content_parts.append(expert_notes_block.replace("事件定向参考片段", "专家笔记参考"))

    summary = "\n\n".join(part for part in content_parts if part.strip())
    if not summary:
        summary = (
            "## 舆情方法论\n\n"
            "1. 关注声量、情感、主题、平台和扩散节奏五个核心维度。\n"
            "2. 用生命周期视角拆解潜伏、爆发、扩散和回落阶段。\n"
            "3. 对高争议事件优先关注议程设置、风险传播和框架竞争。"
        )

    theory_hints = _pick_theory_hints(summary, max_items=4)

    return {
        "summary": _truncate(summary, 9000),
        "framework": _truncate(framework, 2200),
        "theories": _truncate(theories, 2600),
        "caseTemplate": _truncate(case_template, 1600),
        "youthInsight": _truncate(youth_insight, 1600),
        "referenceSnippets": reference_hits[:6],
        "referenceLinks": reference_links[:4],
        "dynamicTheories": dynamic_theories[:4],
        "expertNotes": expert_notes[:4],
        "theoryHints": theory_hints,
        "meta": {
            "knowledgeRoot": str(SONA_ROOT),
            "methodDir": str(SONA_METHOD_DIR),
            "toolModule": "backend.src.report.tools.knowledge_base_tools",
            "sonaRoot": str(SONA_ROOT),
            "toolAvailable": True,
            "referenceCount": len(reference_hits),
            "linkCount": len(reference_links),
            "dynamicTheoryCount": len(dynamic_theories),
            "expertNoteCount": len(expert_notes),
            "appendExpertJudgementSupported": True,
            "localMethodologyAvailable": bool(theory_path),
        },
    }
