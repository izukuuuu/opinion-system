"""
舆情智库工具：为舆情分析提供方法论支持与参考资料检索。

正式迁入 backend/src/report/tools，避免继续从 knowledge_base 下动态导入工具脚本。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from langchain.tools import tool


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SONA_ROOT = PROJECT_ROOT / "backend" / "knowledge_base" / "report" / "sentiment_analysis_methodology"
LOCAL_REFERENCES_DIR = SONA_ROOT / "舆情深度分析" / "references"
LOCAL_METHOD_DIR = SONA_ROOT / "舆情深度分析"
PROJECT_REFERENCES_DIR = SONA_ROOT / "references"
EXPERT_NOTES_DIR = LOCAL_REFERENCES_DIR / "expert_notes"

TEXT_SUFFIX = {".md", ".txt", ".json", ".jsonl", ".csv"}


def _reference_dirs() -> List[Path]:
    dirs = [LOCAL_REFERENCES_DIR, LOCAL_METHOD_DIR, PROJECT_REFERENCES_DIR]
    uniq: List[Path] = []
    seen = set()
    for directory in dirs:
        key = str(directory.resolve()) if directory.exists() else str(directory)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(directory)
    return uniq


def _find_reference_file(candidates: List[str]) -> Optional[Path]:
    for name in candidates:
        for directory in _reference_dirs():
            path = directory / name
            if path.exists() and path.is_file():
                return path
    return None


def _safe_read_text(path: Path, max_chars: int = 120_000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars]
        return text
    except Exception:
        return ""


def _tokenize(text: str, max_tokens: int = 32) -> List[str]:
    value = (text or "").strip()
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

    dedup: List[str] = []
    seen = set()
    for token in sorted(tokens, key=len, reverse=True):
        key = token.lower()
        if len(token) < 2 or key in seen:
            continue
        seen.add(key)
        dedup.append(token)
        if len(dedup) >= max_tokens:
            break
    return dedup


def _iter_reference_files(max_files: int = 200) -> List[Path]:
    files: List[Path] = []
    for directory in _reference_dirs():
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIX:
                continue
            if path.name.startswith(".") or path.name.lower().startswith("readme"):
                continue
            files.append(path)
            if len(files) >= max_files:
                return files
    return files


def _split_paragraphs(text: str) -> List[str]:
    blocks = re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n"))
    result: List[str] = []
    for block in blocks:
        compact = re.sub(r"\s+", " ", block).strip()
        if len(compact) >= 16:
            result.append(compact)
    return result


def _score_text(block: str, tokens: List[str]) -> float:
    if not block or not tokens:
        return 0.0
    lowered = block.lower()
    score = 0.0
    for token in tokens:
        if token.lower() in lowered:
            score += 1.0 + min(len(token), 10) * 0.08
    return score


def _rank_reference_snippets(query: str, max_items: int = 8) -> List[Dict[str, Any]]:
    tokens = _tokenize(query, max_tokens=36)
    if not tokens:
        return []

    ranked: List[Dict[str, Any]] = []
    for file_path in _iter_reference_files(max_files=260):
        text = _safe_read_text(file_path, max_chars=120_000)
        if not text:
            continue
        paragraphs = _split_paragraphs(text)
        if not paragraphs:
            continue

        local_hits: List[Tuple[float, str]] = []
        for paragraph in paragraphs:
            score = _score_text(paragraph, tokens)
            if score <= 0:
                continue
            local_hits.append((score, paragraph))

        local_hits.sort(key=lambda item: item[0], reverse=True)
        for score, paragraph in local_hits[:3]:
            ranked.append(
                {
                    "source": str(file_path),
                    "title": file_path.name,
                    "score": round(score, 4),
                    "snippet": paragraph[:360] + ("..." if len(paragraph) > 360 else ""),
                }
            )

    ranked.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return ranked[: max(1, max_items)]


def _search_links_for_topic(topic: str) -> List[Dict[str, str]]:
    query = (topic or "").strip() or "舆情事件"
    encoded = quote(query)
    return [
        {
            "name": "微博智搜",
            "url": f"https://s.weibo.com/aisearch?q={encoded}&Refer=weibo_aisearch",
            "usage": "查看微博智搜聚合观点与相关讨论",
        },
        {
            "name": "微博搜索",
            "url": f"https://s.weibo.com/weibo?q={encoded}",
            "usage": "查看微博原始帖子与热度讨论",
        },
        {
            "name": "百度资讯",
            "url": f"https://www.baidu.com/s?wd={encoded}%20舆情%20评论",
            "usage": "查看媒体评论与报道",
        },
    ]


@tool
def get_sentiment_analysis_framework(topic: Optional[str] = None) -> str:
    """
    获取舆情分析框架和核心维度。
    """
    framework = """
【舆情分析核心框架】

一、舆情基本要素
- 主体：网民、KOL、媒体、机构
- 客体：事件/议题/品牌/政策
- 渠道：微博、短视频平台、论坛、私域社群等
- 情绪：积极/中性/消极 + 细分（愤怒、焦虑、讽刺等）
- 主体行为：转发、评论、跟帖、二创、线下行动

二、核心分析维度
- 量：声量、增速、峰值、平台分布
- 质：情感极性、话题焦点、信息真实性
- 人：关键意见领袖、关键节点用户、受众画像
- 场：主要平台、话语场风格（理性、撕裂、娱乐化）
- 效：对品牌/政策/行为的实际影响（搜索量、销量、投诉量等）

三、舆情生命周期阶段
- 潜伏期：信息量少但敏感度高
- 萌芽期：意见领袖介入、帖文量开始增长
- 爆发期：媒体跟进、热度达到峰值
- 衰退期：事件解决或新热点出现、舆情衰减

四、分析框架建议
1. 事件脉络：潜伏期→萌芽期→爆发期→衰退期
2. 回应观察：回应处置梳理、趋势变化、传播平台变化、情绪变化、话题变化
3. 总结复盘：话语分析、议题泛化趋势、舆论推手分析、叙事手段分析
"""
    if topic:
        framework += f"\n\n【本次主题】{topic}\n建议优先选择与该主题高度相关的维度与证据，不做模板化套用。"
    return framework


@tool
def get_sentiment_theories(topic: Optional[str] = None) -> str:
    """
    获取舆情规律理论基础。
    """
    theory_file = _find_reference_file(["舆情分析方法论.md"])

    if theory_file and theory_file.exists():
        content = _safe_read_text(theory_file, max_chars=90_000)
        if topic:
            snippets = _rank_reference_snippets(topic, max_items=6)
            topic_hits = [
                f"- {item['snippet']}\n  来源: {item['title']}"
                for item in snippets
                if item.get("title") == theory_file.name
            ]
            if topic_hits:
                return "【舆情理论（主题相关）】\n" + "\n".join(topic_hits[:4])

        lines = content.splitlines()
        picked: List[str] = []
        bucket: List[str] = []
        in_section = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#") and ("理论" in stripped or "规律" in stripped or "框架" in stripped):
                if bucket:
                    picked.append("\n".join(bucket[:20]))
                    bucket = []
                in_section = True
                bucket.append(stripped)
                continue
            if in_section:
                bucket.append(stripped)
                if len(bucket) >= 20:
                    picked.append("\n".join(bucket))
                    bucket = []
                    in_section = False
        if bucket:
            picked.append("\n".join(bucket[:20]))

        if picked:
            return "【舆情理论基础】\n\n" + "\n\n".join(picked[:6])
        return content[:6000]

    return """
【舆情规律理论基础】

1. 沉默螺旋规律：群体压力下的意见趋同
2. 议程设置规律：媒体与公众的互动塑造议题
3. 框架理论：同一事实在不同叙事框架下会引发不同舆论走向
4. 生命周期规律：舆情通常经历萌芽-扩散-消退
5. 风险传播理论：不确定性与恐惧感会显著加速扩散
6. 社会燃烧规律：矛盾累积到阈值后会突发集中爆发
"""


@tool
def get_sentiment_case_template(case_type: str = "社会事件") -> str:
    """
    获取舆情分析报告模板。
    """
    if "商业" in case_type:
        return """
【商业事件舆情分析模板】

一、行业背景
二、事件梳理
   - 萌芽期：宏观背景与触发点
   - 发酵期：多方参与与议题竞逐
   - 爆发期：导火索、峰值节点与关键叙事
   - 延续期：影响外溢与走势研判
三、品牌观察
   - 宣发策略与渠道结构
   - 平台热度分布（小红书/微博/抖音/新闻/问答/论坛）
   - 核心争议与用户情绪迁移
   - SWOT与风险处置建议
"""
    return """
【社会事件舆情分析模板】

一、事件脉络
   - 潜伏期
   - 萌芽期
   - 爆发期
   - 衰退期

二、回应观察
   - 回应处置梳理与时点效果
   - 趋势变化与平台迁移
   - 情绪变化与话题转向

三、总结复盘
   - 叙事结构与话语策略
   - 议题泛化与风险外溢
   - 推手网络与传播机制
"""


@tool
def get_youth_sentiment_insight() -> str:
    """
    获取中国青年网民社会心态分析洞察。
    """
    insight_file = _find_reference_file(["青年网民心态.md", "中国青年网民社会心态调查报告（2024）.md"])
    if insight_file and insight_file.exists():
        content = _safe_read_text(insight_file, max_chars=7000)
        return content[:5000] + "\n\n[...详细内容见青年网民心态参考文档...]"
    return "青年网民心态报告文件未找到"


@tool
def search_reference_insights(query: str, limit: int = 6) -> str:
    """
    按事件主题检索本地参考资料（方法论/案例/专家笔记）。
    """
    query_text = (query or "").strip()
    if not query_text:
        return json.dumps({"query": query_text, "count": 0, "results": []}, ensure_ascii=False)

    safe_limit = max(1, min(int(limit or 6), 20))
    hits = _rank_reference_snippets(query_text, max_items=safe_limit)
    return json.dumps({"query": query_text, "count": len(hits), "results": hits}, ensure_ascii=False, indent=2)


@tool
def append_expert_judgement(topic: str, judgement: str, tags: str = "", source: str = "expert") -> str:
    """
    追加专家研判到本地参考库，供后续报告自动引用。
    """
    topic_text = (topic or "").strip()
    judgement_text = (judgement or "").strip()
    if not topic_text or not judgement_text:
        return json.dumps({"ok": False, "error": "topic 与 judgement 不能为空"}, ensure_ascii=False)

    EXPERT_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", topic_text)[:60].strip("_") or "expert_note"
    file_path = EXPERT_NOTES_DIR / f"{datetime.now().strftime('%Y%m%d')}_{slug}.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"## {topic_text}",
        f"- 时间: {now}",
        f"- 来源: {source}",
    ]
    if tags.strip():
        lines.append(f"- 标签: {tags.strip()}")
    lines.extend(["", "### 研判内容", judgement_text, "", "---", ""])

    try:
        with file_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write("\n".join(lines))
        return json.dumps(
            {
                "ok": True,
                "path": str(file_path),
                "topic": topic_text,
                "message": "专家研判已写入参考库，后续报告可自动检索引用。",
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@tool
def build_event_reference_links(topic: str) -> str:
    """
    生成事件外部参考检索链接（如微博智搜），用于人工核验与补充研判。
    """
    links = _search_links_for_topic(topic)
    return json.dumps({"topic": topic, "count": len(links), "links": links}, ensure_ascii=False, indent=2)


@tool
def load_sentiment_knowledge(keyword: str) -> str:
    """
    根据关键词加载舆情知识库。
    """
    value = (keyword or "").strip()
    if not value:
        return str(get_sentiment_analysis_framework.invoke({}))

    if any(token in value for token in ["参考", "评论", "研判", "文章", "案例"]):
        refs = search_reference_insights.invoke({"query": value, "limit": 6})
        try:
            data = json.loads(refs)
            lines = ["【事件参考片段】"]
            for item in data.get("results", [])[:6]:
                lines.append(f"- {item.get('snippet', '')}\n  来源: {item.get('title', '')}")
            return "\n".join(lines)
        except Exception:
            return str(refs)

    if any(token in value for token in ["链接", "检索", "智搜", "微博"]):
        return build_event_reference_links.invoke({"topic": value})

    keyword_map = {
        "框架": str(get_sentiment_analysis_framework.invoke({})),
        "理论": str(get_sentiment_theories.invoke({"topic": value})),
        "社会事件": str(get_sentiment_case_template.invoke({"case_type": "社会事件"})),
        "商业事件": str(get_sentiment_case_template.invoke({"case_type": "商业事件"})),
        "青年": str(get_youth_sentiment_insight.invoke({})),
    }

    for key, mapped in keyword_map.items():
        if key in value:
            return mapped

    return str(get_sentiment_analysis_framework.invoke({"topic": value}))


sentiment_analysis_framework = get_sentiment_analysis_framework
sentiment_theories = get_sentiment_theories
sentiment_case_template = get_sentiment_case_template
youth_sentiment_insight = get_youth_sentiment_insight
reference_search = search_reference_insights
expert_judgement_append = append_expert_judgement
event_reference_links = build_event_reference_links
sentiment_knowledge_loader = load_sentiment_knowledge
