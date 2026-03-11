"""Homepage hot-overview helper based on public hot-list feeds."""

from __future__ import annotations

import asyncio
import copy
import html
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from src.utils.ai import call_langchain_chat

TEXT_CACHE_TTL_SECONDS = 20 * 60
_URL_TEXT_CACHE: Dict[str, Dict[str, Any]] = {}
_JINA_DISABLED_DOMAINS: Dict[str, float] = {
    "toutiao.com": float("inf"),
    "www.toutiao.com": float("inf"),
}
_WARNED_FETCH_KEYS: set[str] = set()
_BLOCK_PAGE_PATTERNS: Tuple[str, ...] = (
    "您需要允许该网站执行 javascript",
    "enable javascript",
    "please enable javascript",
    "access denied",
    "forbidden",
    "verify you are human",
    "验证码",
    "人机验证",
    "cloudflare",
    "unavailable for legal reasons",
)
_GENERIC_SUMMARY_PATTERNS: Tuple[str, ...] = (
    "引发公众",
    "引发关注",
    "持续升温",
    "值得关注",
    "体现",
    "释放信号",
    "风险提示",
    "保持审慎",
    "未说明具体",
    "相关讨论热度",
)


def _is_block_or_low_quality_text(text: str) -> bool:
    content = re.sub(r"\s+", " ", str(text or "")).strip()
    if not content:
        return True
    lowered = content.lower()
    if any(pattern in lowered for pattern in _BLOCK_PAGE_PATTERNS):
        return True
    # Too short text is usually nav/cookie/anti-bot snippets.
    if len(content) < 80:
        return True
    return False


def _sanitize_context_text(text: str, limit: int = 2000) -> str:
    content = re.sub(r"\s+", " ", str(text or "")).strip()
    if _is_block_or_low_quality_text(content):
        return ""
    return content[:limit]


def _looks_generic_summary(text: str) -> bool:
    content = re.sub(r"\s+", "", str(text or ""))
    if not content:
        return True
    if len(content) < 24:
        return True
    return any(pattern in content for pattern in _GENERIC_SUMMARY_PATTERNS)


def _split_sentences(text: str) -> List[str]:
    raw = re.split(r"[。！？!?；;]\s*", str(text or ""))
    return [re.sub(r"\s+", " ", s).strip() for s in raw if s and s.strip()]


def _best_fact_sentence(background: str) -> str:
    sentences = _split_sentences(background)
    if not sentences:
        return ""
    strong_verbs = ("发布", "表示", "宣布", "取消", "开行", "恢复", "发行", "出台", "补贴", "访问", "回应", "上线")
    for sentence in sentences:
        if len(sentence) < 16:
            continue
        if any(ch.isdigit() for ch in sentence) or any(verb in sentence for verb in strong_verbs):
            return sentence[:120]
    for sentence in sentences:
        if len(sentence) >= 18:
            return sentence[:120]
    return sentences[0][:120]


def _normalize_compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def _is_context_relevant_to_title(title: str, text: str) -> bool:
    norm_title = _normalize_compact(title)
    norm_text = _normalize_compact(text)
    if not norm_title or not norm_text:
        return False
    if len(norm_title) < 8:
        return norm_title in norm_text
    for i in range(0, max(1, len(norm_title) - 3)):
        anchor = norm_title[i : i + 4]
        if anchor and anchor in norm_text:
            return True
    return False


def _headline_fallback_summary(headline: str) -> str:
    clean = re.sub(r"\s+", " ", str(headline or "")).strip("。;；,， ")
    if not clean:
        return ""
    if len(clean) > 70:
        clean = clean[:70] + "..."
    return clean


def _strip_html_tags(text: str) -> str:
    plain = re.sub(r"(?is)<[^>]+>", " ", str(text or ""))
    plain = html.unescape(plain)
    return re.sub(r"\s+", " ", plain).strip()


def _truncate_compact_text(text: str, limit: int = 260) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 3)] + "..."


def _fetch_search_context_by_title(title: str, timeout: int = 8) -> str:
    query = str(title or "").strip()
    if not query:
        return ""
    snippets, candidate_links = _search_news_rss_candidates(query, timeout=timeout)

    for link in candidate_links[:2]:
        text = _fetch_url_text(link, timeout=timeout)
        if text and not _is_block_or_low_quality_text(text):
            return _truncate_compact_text(text, limit=260)

    merged = "；".join(snippets)
    return _truncate_compact_text(merged, limit=260) if merged else ""


def _search_news_rss_candidates(title: str, timeout: int = 8) -> Tuple[List[str], List[str]]:
    query = str(title or "").strip()
    if not query:
        return [], []
    search_url = (
        "https://www.bing.com/news/search?q="
        + urllib.parse.quote(query + " 新闻")
        + "&format=rss&mkt=zh-CN"
    )
    try:
        req = urllib.request.Request(
            url=search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rss_xml = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        warn_key = f"search:{query}"
        if warn_key not in _WARNED_FETCH_KEYS:
            _WARNED_FETCH_KEYS.add(warn_key)
            LOGGER.warning("Search context fetch failed for title=%s: %s", query[:32], exc)
        return [], []

    items = re.findall(r"(?is)<item>(.*?)</item>", rss_xml)
    if not items:
        return [], []

    snippets: List[str] = []
    candidate_links: List[str] = []
    for block in items[:5]:
        m_title = re.search(r"(?is)<title>(.*?)</title>", block)
        m_desc = re.search(r"(?is)<description>(.*?)</description>", block)
        m_link = re.search(r"(?is)<link>(.*?)</link>", block)
        title_text = _strip_html_tags(m_title.group(1) if m_title else "")
        desc_text = _strip_html_tags(m_desc.group(1) if m_desc else "")
        link_text = (m_link.group(1).strip() if m_link else "")
        if title_text or desc_text:
            snippet = f"{title_text}。{desc_text}".strip("。")
            snippet = re.sub(r"\s+", " ", snippet).strip()
            if snippet:
                snippets.append(snippet[:220])
        if link_text.startswith("http"):
            candidate_links.append(link_text)
    return snippets[:3], candidate_links[:5]


def _discover_candidate_links(item: Dict[str, Any], timeout: int = 8) -> Tuple[str, List[str], str]:
    title = _resolve_alias_in_text(str(item.get("title") or "").strip())
    if not title:
        return "", [], ""
    base_url = str(item.get("url") or item.get("mobileUrl") or "").strip()
    snippets, searched_links = _search_news_rss_candidates(title, timeout=timeout)
    links: List[str] = []
    if base_url.startswith("http"):
        links.append(base_url)
    for link in searched_links:
        if link not in links:
            links.append(link)
    merged_snippet = _truncate_compact_text("；".join(snippets), limit=260) if snippets else ""
    return title, links[:6], merged_snippet


def _match_background_title(headline: str, backgrounds: Dict[str, str]) -> str:
    target = re.sub(r"\s+", "", _resolve_alias_in_text(str(headline or "")).lower())
    if not target:
        return ""
    exact = backgrounds.get(_resolve_alias_in_text(str(headline or "")).strip())
    if isinstance(exact, str) and exact.strip():
        return _resolve_alias_in_text(str(headline or "")).strip()
    best_score = 0.0
    best_title = ""
    best_text = ""
    for title, text in backgrounds.items():
        norm_title = re.sub(r"\s+", "", _resolve_alias_in_text(str(title or "")).lower())
        if not norm_title:
            continue
        score = SequenceMatcher(None, target, norm_title).ratio()
        has_anchor = False
        if len(target) >= 4:
            for i in range(0, len(target) - 3):
                if target[i : i + 4] in norm_title:
                    has_anchor = True
                    break
        if not has_anchor and len(norm_title) >= 4:
            for i in range(0, len(norm_title) - 3):
                if norm_title[i : i + 4] in target:
                    has_anchor = True
                    break
        if not has_anchor:
            continue
        # Only reward containment when both strings are sufficiently informative.
        min_len = min(len(target), len(norm_title))
        if min_len >= 10 and (target in norm_title or norm_title in target):
            score = max(score, 0.88)
        if score > best_score:
            best_score = score
            best_title = str(title or "").strip()
            best_text = str(text or "").strip()
    # Avoid matching by a shared short token (e.g., only "龙虾").
    if best_score >= 0.35:
        return best_title if best_text else ""
    return ""


def _match_background(headline: str, backgrounds: Dict[str, str]) -> str:
    matched_title = _match_background_title(headline, backgrounds)
    if not matched_title:
        return ""
    return str(backgrounds.get(matched_title) or "").strip()


def _ground_sections_with_evidence(
    sections: Any,
    backgrounds: Dict[str, str],
    evidence_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(sections, list):
        return []
    evidence_meta = evidence_meta or {}
    grounded: List[Dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        cards = section.get("cards")
        if not isinstance(cards, list):
            grounded.append(section)
            continue
        next_cards: List[Dict[str, Any]] = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            updated = dict(card)
            headline = str(updated.get("headline") or "").strip()
            source_title = _resolve_alias_in_text(str(updated.get("source_title") or "").strip())
            summary = str(updated.get("summary") or "").strip()
            matched_title = ""
            if source_title and source_title in backgrounds:
                matched_title = source_title
            if not matched_title:
                matched_title = _match_background_title(source_title or headline, backgrounds)
            bg = str(backgrounds.get(matched_title) or "").strip() if matched_title else ""
            if bg:
                fact_sentence = _best_fact_sentence(bg)
                # 强制抽取式摘要：有证据则统一回落到证据句，禁止模型补细节。
                if fact_sentence:
                    updated["summary"] = fact_sentence
                meta = evidence_meta.get(matched_title) if isinstance(evidence_meta, dict) else None
                updated["evidence"] = {
                    "status": "confirmed",
                    "matched_title": matched_title[:72],
                    "excerpt": fact_sentence[:160] if fact_sentence else "",
                    "source_url": str((meta or {}).get("source_url") or ""),
                    "method": str((meta or {}).get("method") or ""),
                }
            else:
                if _looks_generic_summary(summary):
                    fallback = _headline_fallback_summary(headline)
                    if fallback:
                        updated["summary"] = fallback
                updated["evidence"] = {
                    "status": "missing",
                    "matched_title": "",
                    "excerpt": "",
                    "source_url": "",
                    "method": "",
                }
            next_cards.append(updated)
        grounded.append({**section, "cards": next_cards})
    return grounded


def _fetch_url_text(url: str, timeout: int = 10) -> str:
    url = str(url or "").strip()
    if not url or not url.startswith("http"):
        return ""
    now = time.time()
    cached = _URL_TEXT_CACHE.get(url)
    if isinstance(cached, dict) and now < float(cached.get("expires_at") or 0.0):
        return str(cached.get("text") or "")

    domain = (urllib.parse.urlparse(url).netloc or "").lower()
    use_jina = now >= float(_JINA_DISABLED_DOMAINS.get(domain) or 0.0)
    try:
        if use_jina:
            jina_url = "https://r.jina.ai/" + url
            req = urllib.request.Request(
                url=jina_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                    ),
                    "X-Return-Format": "text"
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
            text = _sanitize_context_text(text, limit=2000)
            if not text:
                return ""
            _URL_TEXT_CACHE[url] = {"text": text, "expires_at": now + TEXT_CACHE_TTL_SECONDS}
            return text
    except urllib.error.HTTPError as exc:
        if exc.code == 451:
            _JINA_DISABLED_DOMAINS[domain] = float("inf")
        warn_key = f"jina:{url}:{exc.code}"
        if warn_key not in _WARNED_FETCH_KEYS:
            _WARNED_FETCH_KEYS.add(warn_key)
            LOGGER.warning("Context fetch failed via Jina for %s: %s", url, exc)
    except Exception as exc:
        warn_key = f"jina:{url}:generic"
        if warn_key not in _WARNED_FETCH_KEYS:
            _WARNED_FETCH_KEYS.add(warn_key)
            LOGGER.warning("Context fetch failed via Jina for %s: %s", url, exc)

    # Fallback: direct page fetch + lightweight HTML cleanup
    try:
        req = urllib.request.Request(
            url=url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = str(resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
        if "text/html" not in content_type:
            return ""
        html = raw.decode("utf-8", errors="ignore")
        html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
        text = re.sub(r"(?is)<[^>]+>", " ", html)
        text = _sanitize_context_text(text, limit=2000)
        if not text:
            return ""
        _URL_TEXT_CACHE[url] = {"text": text, "expires_at": now + TEXT_CACHE_TTL_SECONDS}
        return text
    except Exception as fallback_exc:
        warn_key = f"direct:{url}"
        if warn_key not in _WARNED_FETCH_KEYS:
            _WARNED_FETCH_KEYS.add(warn_key)
            LOGGER.warning("Context direct-fetch failed for %s: %s", url, fallback_exc)
        return ""


def _fetch_url_text_playwright(url: str, timeout_ms: int = 12000) -> str:
    """Optional playwright fallback for JS-heavy pages."""
    target = str(url or "").strip()
    if not target or not target.startswith("http"):
        return ""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(600)
            text = page.inner_text("body")
            browser.close()
            if not isinstance(text, str):
                return ""
            return _sanitize_context_text(text, limit=2000)
    except Exception as exc:
        LOGGER.warning("Context fetch failed via Playwright for %s: %s", target, exc)
        return ""

LOGGER = logging.getLogger(__name__)

HOT_SOURCE_CONFIG: List[Tuple[str, str]] = [
    ("toutiao", "今日头条"),
    ("bilibili-hot-search", "B站热搜"),
    ("cls-hot", "财联社热门"),
    ("wallstreetcn-hot", "华尔街见闻"),
]
HOT_SOURCE_WEIGHT: Dict[str, float] = {
    "toutiao": 1.0,
    "bilibili-hot-search": 0.95,
    "cls-hot": 0.9,
    "wallstreetcn-hot": 0.85,
}
ALLOWED_TAG_CLUSTERS = {
    "geopolitics",
    "policy",
    "economy",
    "technology",
    "industry",
    "society",
    "general",
}
NEWSNOW_API = "https://newsnow.busiyi.world/api/s?id={platform_id}&latest"
CACHE_TTL_SECONDS = 15 * 60
DEFAULT_LIMIT = 12
MAX_HISTORY_ITEMS = 20
HOT_ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "home_hot_overview"

_CACHE: Dict[str, Dict[str, Any]] = {
    "fast": {"data": None, "expires_at": 0.0},
    "research": {"data": None, "expires_at": 0.0},
}
_HISTORY: Dict[str, List[Dict[str, Any]]] = {
    "fast": [],
    "research": [],
}


def _today_snapshot_date() -> str:
    # Use local server date for daily archive boundary.
    return datetime.now().strftime("%Y-%m-%d")


def _archive_file_path(cache_key: str) -> Path:
    safe_key = "research" if cache_key == "research" else "fast"
    return HOT_ARCHIVE_DIR / f"{safe_key}.json"


def _load_archive_payload(cache_key: str) -> Optional[Dict[str, Any]]:
    path = _archive_file_path(cache_key)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        LOGGER.warning("hot_overview archive load failed | key=%s path=%s err=%s", cache_key, path, exc)
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _save_archive_payload(cache_key: str, payload: Dict[str, Any]) -> None:
    path = _archive_file_path(cache_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        LOGGER.warning("hot_overview archive save failed | key=%s path=%s err=%s", cache_key, path, exc)


def _is_payload_fresh_for_today(payload: Any, today: str) -> bool:
    if not isinstance(payload, dict):
        return False
    return str(payload.get("snapshot_date") or "") == today


def _apply_limit_to_payload(payload: Dict[str, Any], limit: int) -> Dict[str, Any]:
    clamped_limit = max(5, min(40, int(limit or DEFAULT_LIMIT)))
    cloned = _clone_payload(payload)
    merged_items = cloned.get("_merged_items")
    if isinstance(merged_items, list) and merged_items:
        cloned["items"] = merged_items[:clamped_limit]
    else:
        items = cloned.get("items")
        if isinstance(items, list):
            cloned["items"] = items[:clamped_limit]
    return cloned


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _coerce_hot_value(raw_value: Any) -> int:
    if isinstance(raw_value, (int, float)):
        return int(raw_value)
    if isinstance(raw_value, str):
        stripped = "".join(ch for ch in raw_value if ch.isdigit())
        if stripped:
            try:
                return int(stripped)
            except ValueError:
                return 0
    return 0


def _fetch_platform_hot_items(platform_id: str, platform_name: str, top_n: int = 15) -> List[Dict[str, Any]]:
    url = NEWSNOW_API.format(platform_id=urllib.parse.quote(platform_id))
    req = urllib.request.Request(
        url=url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://newsnow.busiyi.world/",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
        data = _safe_json_loads(payload) or {}
    except Exception as exc:
        LOGGER.warning("Hot source fetch failed for %s: %s", platform_id, exc)
        return []

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return []

    items: List[Dict[str, Any]] = []
    for rank, item in enumerate(raw_items[:top_n], start=1):
        if not isinstance(item, dict):
            continue
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        if not title:
            continue
        hot_value = _coerce_hot_value(item.get("hotValue"))
        items.append(
            {
                "title": title,
                "url": str(item.get("url") or item.get("mobileUrl") or "").strip(),
                "source_id": platform_id,
                "source": platform_name,
                "rank": rank,
                "hot_value": hot_value,
                "has_hot_value": hot_value > 0,
            }
        )
    return items


def _entry_score(entry: Dict[str, Any]) -> float:
    source_id = str(entry.get("source_id") or "")
    source_weight = HOT_SOURCE_WEIGHT.get(source_id, 0.8)
    rank = int(entry.get("rank") or 9999)
    hot_value = _coerce_hot_value(entry.get("hot_value"))
    hot_component = min(1.0, hot_value / 1_000_000.0)
    rank_component = max(0.0, (50 - min(rank, 50)) / 50.0)
    return source_weight * 0.55 + rank_component * 0.35 + hot_component * 0.10


def _merge_and_sort_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dedup: Dict[str, Dict[str, Any]] = {}
    for item in items:
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        if not title:
            continue
        key = title.lower()
        existing = dedup.get(key)
        if existing is None:
            dedup[key] = dict(item)
            continue
        if _coerce_hot_value(item.get("hot_value")) > _coerce_hot_value(existing.get("hot_value")):
            existing["hot_value"] = _coerce_hot_value(item.get("hot_value"))
            existing["has_hot_value"] = bool(existing["hot_value"] > 0)
        existing_sources = str(existing.get("source") or "")
        incoming_source = str(item.get("source") or "")
        if incoming_source and incoming_source not in existing_sources:
            existing["source"] = f"{existing_sources} / {incoming_source}".strip(" /")
        existing["rank"] = min(int(existing.get("rank") or 9999), int(item.get("rank") or 9999))

    merged = list(dedup.values())

    for entry in merged:
        score = _entry_score(entry)
        # 当来源不提供真实热度时，给前端一个统一可比较的综合热度指数。
        entry["heat_score"] = max(1, min(100, int(round(score * 100))))

    merged.sort(key=_entry_score, reverse=True)
    return merged


def _build_prompt(
    news_items: List[Dict[str, Any]],
    backgrounds: Dict[str, str] = None,
    *,
    max_items: int = 25,
) -> str:
    lines: List[str] = []
    backgrounds = backgrounds or {}
    for idx, item in enumerate(news_items[:max_items], start=1):
        source = str(item.get("source") or "未知来源")
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        hot = _coerce_hot_value(item.get("hot_value"))
        rank = int(item.get("rank") or idx)
        hot_text = f"热度{hot}" if hot > 0 else "热度未知"
        
        bg = backgrounds.get(title)
        if bg:
            lines.append(f"{idx}. [{source}] #{rank} {title}（{hot_text}）\n   [背景补充: {bg}]")
        else:
            lines.append(f"{idx}. [{source}] #{rank} {title}（{hot_text}）")

    joined = "\n".join(lines)
    return (
        "你是中文舆情编辑。基于以下今日热榜条目，输出一个 JSON 对象，格式严格如下：\n"
        '{\n'
        '  "overview": "120-180字总览",\n'
        '  "detailed_overview": "220-320字扩展解读",\n'
        '  "bullet_points": ["要点1","要点2","..."],\n'
        '  "watch_points": ["后续观察点1","后续观察点2","..."],\n'
        '  "keyword_pool": [\n'
        '    {"text": "关键词1", "cluster": "policy"}\n'
        "  ],\n"
        '  "sections": [\n'
        "    {\n"
        '      "title": "国际关系·地缘",\n'
        '      "badge": "热度聚焦",\n'
        '      "cards": [\n'
        "        {\n"
        '          "source_title": "必须是输入热榜中的原始标题",\n'
        '          "headline": "事件标题",\n'
        '          "stance": "正向|负向|中性",\n'
        '          "heat": 86,\n'
        '          "summary": "40-90字简述",\n'
        '          "tags": [\n'
        '            {"name": "标签1", "cluster": "geopolitics"}\n'
        "          ]\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "要求：\n"
        "1) 只返回 JSON，不要 markdown。\n"
        "2) bullet_points 返回 6-8 条，每条不超过32字。\n"
        "3) watch_points 返回 4-6 条，每条不超过32字。\n"
        "4) keyword_pool 返回 10-14 个对象，每个对象包含 text 和 cluster。\n"
        "5) sections 返回 2-3 个分组，每组 2-3 张卡片。\n"
        "6) cards.tags 必须是对象数组，每个对象包含 name 和 cluster。\n"
        "6.1) cards.source_title 必须填写对应的原始热榜标题（不可改写）。\n"
        "7) cluster 仅可使用：geopolitics, policy, economy, technology, industry, society, general。\n"
        "8) 每张卡片 summary 必须优先使用[背景补充]中的具体事实，写清主体+动作，不写空泛结论。\n"
        "9) 若出现歧义术语（例如同一词在不同语境含义不同），必须在 overview 或 detailed_overview 里明确解释该术语在本批数据中的具体所指。\n"
        "10) 禁止空话套话（如“引发关注”“释放信号”“体现立场”等无事实承载表述）。\n"
        "11) 用客观描述，不要编造未给出的细节。\n\n"
        f"热榜数据：\n{joined}"
    )


def _extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    direct = _safe_json_loads(raw)
    if direct is not None:
        return direct

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return _safe_json_loads(raw[start : end + 1])
    return None


def _safe_run_async(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _clone_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return copy.deepcopy(payload)
    except Exception:
        return dict(payload)


def _new_revision_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _push_history(cache_key: str, payload: Dict[str, Any]) -> None:
    history = _HISTORY.setdefault(cache_key, [])
    history.append(_clone_payload(payload))
    if len(history) > MAX_HISTORY_ITEMS:
        del history[:-MAX_HISTORY_ITEMS]


def _resolve_mode(*, mode: Optional[str] = None, include_research: Optional[bool] = None) -> str:
    if isinstance(mode, str) and mode.strip():
        return "research" if mode.strip().lower() == "research" else "fast"
    if include_research is True:
        return "research"
    return "fast"


def _extract_tags_from_title(title: str) -> List[str]:
    clean = re.sub(r"[，。！？、：；,.!?;:()（）【】\[\]\"'“”‘’]", " ", title)
    chunks = [part.strip() for part in re.split(r"[·|｜/\-\s]+", clean) if part.strip()]
    selected: List[str] = []
    for chunk in chunks:
        candidate = chunk[:10]
        if 2 <= len(candidate) <= 10 and candidate not in selected:
            selected.append(candidate)
        if len(selected) >= 4:
            break
    if selected:
        return selected[:4]
    fallback = title.strip()[:8]
    return [fallback] if fallback else []


def _derive_title_keywords(news_items: List[Dict[str, Any]], limit: int = 14) -> List[str]:
    keywords: List[str] = []
    for item in news_items[:16]:
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        if not title:
            continue
        tags = _extract_tags_from_title(title)
        for tag in tags:
            if tag not in keywords:
                keywords.append(tag)
            if len(keywords) >= limit:
                return keywords
    return keywords


class _KeywordState(TypedDict):
    lines: List[str]
    extracted: List[str]
    keywords: List[str]


def _run_keyword_langgraph(news_items: List[Dict[str, Any]], limit: int = 14) -> List[str]:
    lines = [
        _resolve_alias_in_text(str(item.get("title") or "").strip())
        for item in news_items[:25]
        if str(item.get("title") or "").strip()
    ]
    if not lines:
        return []

    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return []

    def _extract_keywords_node(state: _KeywordState) -> _KeywordState:
        prompt = (
            "你是舆情关键词提取助手。请基于这些新闻标题提取 10-14 个关键词，"
            "覆盖事件主体、议题、行业与宏观变量。仅返回 JSON："
            '{"keywords":["关键词1","关键词2"]}\n\n'
            + "\n".join(f"- {line}" for line in state.get("lines", []))
        )
        response_text = _safe_run_async(
            call_langchain_chat(
                [
                    {"role": "system", "content": "你是严谨的中文分析助手。"},
                    {"role": "user", "content": prompt},
                ],
                task="report",
                temperature=0.1,
                max_tokens=400,
            )
        )
        extracted: List[str] = []
        if isinstance(response_text, str) and response_text.strip():
            payload = _extract_json_payload(response_text)
            if isinstance(payload, dict):
                raw_keywords = payload.get("keywords")
                if isinstance(raw_keywords, list):
                    for item in raw_keywords:
                        text = str(item or "").strip()
                        if 2 <= len(text) <= 12 and text not in extracted:
                            extracted.append(text)
        return {
            "lines": state.get("lines", []),
            "extracted": extracted[:limit],
            "keywords": state.get("keywords", []),
        }

    def _normalize_keywords_node(state: _KeywordState) -> _KeywordState:
        merged: List[str] = []
        extracted = state.get("extracted", [])
        for item in extracted:
            text = str(item or "").strip()
            if 2 <= len(text) <= 12 and text not in merged:
                merged.append(text)
        for item in _derive_title_keywords(news_items, limit=limit):
            if item not in merged:
                merged.append(item)
            if len(merged) >= limit:
                break
        return {
            "lines": state.get("lines", []),
            "extracted": extracted,
            "keywords": merged[:limit],
        }

    try:
        workflow = StateGraph(_KeywordState)
        workflow.add_node("extract", _extract_keywords_node)
        workflow.add_node("normalize", _normalize_keywords_node)
        workflow.set_entry_point("extract")
        workflow.add_edge("extract", "normalize")
        workflow.add_edge("normalize", END)
        app = workflow.compile()
        result = app.invoke({"lines": lines, "extracted": [], "keywords": []})
        keywords = result.get("keywords", []) if isinstance(result, dict) else []
        if isinstance(keywords, list):
            cleaned: List[str] = []
            for item in keywords:
                text = str(item or "").strip()
                if 2 <= len(text) <= 12 and text not in cleaned:
                    cleaned.append(text)
            return cleaned[:limit]
    except Exception as exc:
        LOGGER.warning("Keyword LangGraph agent failed: %s", exc)
    return []


def _build_dynamic_keyword_pool(news_items: List[Dict[str, Any]], limit: int = 14) -> List[str]:
    keywords = _run_keyword_langgraph(news_items, limit=limit)
    return keywords[:limit] if keywords else []


def _build_research_prompt(news_items: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, item in enumerate(news_items[:18], start=1):
        lines.append(
            f"{idx}. [{item.get('source','未知来源')}] "
            f"{item.get('title','')} "
            f"(rank={item.get('rank','-')},heat={item.get('heat_score','-')})"
        )
    return (
        "你是调研分析 agent。请基于热榜标题进行结构化调研，输出 JSON：\n"
        '{\n'
        '  "clusters":[\n'
        "    {\n"
        '      "theme":"主题名",\n'
        '      "insight":"80-150字分析",\n'
        '      "risk_level":"low|medium|high",\n'
        '      "confidence":0.0,\n'
        '      "evidence_titles":["标题1","标题2"],\n'
        '      "open_questions":["待验证问题1","待验证问题2"]\n'
        "    }\n"
        "  ],\n"
        '  "method_note":"一句话说明本次归纳依据"\n'
        "}\n"
        "规则：\n"
        "1) 只输出 JSON；2) clusters 输出 3-5 个；3) confidence 取值 0~1；\n"
        "4) 若证据不足，要在 open_questions 中明确写出缺口。\n\n"
        "标题数据：\n"
        + "\n".join(lines)
    )


def _resolve_alias_in_text(text: str) -> str:
    # Keep original text; semantic disambiguation should be handled by LLM with evidence.
    return str(text or "")


def _run_research_langgraph(news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not news_items:
        return {"clusters": [], "method_note": "无可用标题数据，未执行调研。"}
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return {"clusters": [], "method_note": "LangGraph 不可用，跳过调研节点。"}

    class _ResearchState(TypedDict):
        input_lines: List[str]
        raw_payload: Dict[str, Any]
        output: Dict[str, Any]

    input_lines = [
        _resolve_alias_in_text(str(item.get("title") or "").strip())
        for item in news_items[:18]
        if str(item.get("title") or "").strip()
    ]

    def _synthesis_node(state: _ResearchState) -> _ResearchState:
        prompt = _build_research_prompt(news_items)
        response_text = _safe_run_async(
            call_langchain_chat(
                [
                    {"role": "system", "content": "你是严谨的中文调研分析助手。"},
                    {"role": "user", "content": prompt},
                ],
                task="report",
                temperature=0.15,
                max_tokens=1200,
            )
        )
        payload = _extract_json_payload(response_text) if isinstance(response_text, str) else None
        return {
            "input_lines": state.get("input_lines", []),
            "raw_payload": payload if isinstance(payload, dict) else {},
            "output": state.get("output", {}),
        }

    def _normalise_node(state: _ResearchState) -> _ResearchState:
        raw = state.get("raw_payload", {})
        raw_clusters = raw.get("clusters")
        clusters: List[Dict[str, Any]] = []
        if isinstance(raw_clusters, list):
            for item in raw_clusters:
                if not isinstance(item, dict):
                    continue
                theme = str(item.get("theme") or "").strip()
                insight = str(item.get("insight") or "").strip()
                risk = str(item.get("risk_level") or "medium").strip().lower()
                if risk not in {"low", "medium", "high"}:
                    risk = "medium"
                try:
                    confidence = float(item.get("confidence") or 0.0)
                except (TypeError, ValueError):
                    confidence = 0.0
                confidence = max(0.0, min(1.0, confidence))
                evidence_titles: List[str] = []
                raw_evidence = item.get("evidence_titles")
                if isinstance(raw_evidence, list):
                    for title in raw_evidence:
                        text = str(title or "").strip()
                        if text and text not in evidence_titles:
                            evidence_titles.append(text[:52])
                open_questions: List[str] = []
                raw_questions = item.get("open_questions")
                if isinstance(raw_questions, list):
                    for question in raw_questions:
                        text = str(question or "").strip()
                        if text and text not in open_questions:
                            open_questions.append(text[:66])
                if theme and insight:
                    clusters.append(
                        {
                            "theme": theme[:20],
                            "insight": insight[:220],
                            "risk_level": risk,
                            "confidence": round(confidence, 2),
                            "evidence_titles": evidence_titles[:4],
                            "open_questions": open_questions[:4],
                        }
                    )
        if not clusters:
            fallback_titles = [
                _resolve_alias_in_text(str(item.get("title") or "").strip())
                for item in news_items[:3]
                if str(item.get("title") or "").strip()
            ]
            clusters = [
                {
                    "theme": "热点综合",
                    "insight": "当前数据主要来自热榜标题，建议补充正文证据后再形成结论。",
                    "risk_level": "medium",
                    "confidence": 0.42,
                    "evidence_titles": fallback_titles,
                    "open_questions": ["是否存在跨平台同源信息放大？", "事件是否已有官方后续披露？"],
                }
            ]
        method_note = str(raw.get("method_note") or "").strip() or "基于多平台热榜标题聚类，未引入正文全文证据。"
        return {
            "input_lines": state.get("input_lines", []),
            "raw_payload": raw,
            "output": {"clusters": clusters[:5], "method_note": method_note[:120]},
        }

    try:
        workflow = StateGraph(_ResearchState)
        workflow.add_node("synthesis", _synthesis_node)
        workflow.add_node("normalize", _normalise_node)
        workflow.set_entry_point("synthesis")
        workflow.add_edge("synthesis", "normalize")
        workflow.add_edge("normalize", END)
        app = workflow.compile()
        result = app.invoke({"input_lines": input_lines, "raw_payload": {}, "output": {}})
        if isinstance(result, dict) and isinstance(result.get("output"), dict):
            return dict(result["output"])
    except Exception as exc:
        LOGGER.warning("Research LangGraph agent failed: %s", exc)
    return {"clusters": [], "method_note": "调研流程执行失败，已回退。"}


def _infer_section(title: str) -> Tuple[str, str]:
    if any(word in title for word in ["美", "伊", "中东", "战争", "外交", "冲突", "制裁"]):
        return "国际关系·地缘", "热度聚焦"
    if any(word in title for word in ["AI", "科技", "芯片", "制造", "工厂", "产业", "监管"]):
        return "科技·经济·制造", "动态"
    if any(word in title for word in ["股市", "油价", "消费", "金融", "经济", "信心", "贸易"]):
        return "经济·市场", "观察"
    return "社会议题·政策", "关注"


def _fallback_structured_payload(news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    sections_map: Dict[str, Dict[str, Any]] = {}
    keyword_pool: List[Dict[str, str]] = []
    for item in news_items[:9]:
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        if not title:
            continue
        section_title, badge = _infer_section(title)
        section_entry = sections_map.setdefault(section_title, {"title": section_title, "badge": badge, "cards": []})

        tags = _extract_tags_from_title(title)
        for tag in tags:
            if not any(item.get("text") == tag for item in keyword_pool):
                keyword_pool.append({"text": tag, "cluster": "general"})
        summary = f"{title[:70]}{'...' if len(title) > 70 else ''}，相关讨论热度持续上升。"
        card = {
            "source_title": title[:80],
            "headline": title[:34],
            "stance": "中性",
            "heat": int(item.get("heat_score") or 60),
            "summary": summary,
            "tags": [{"name": tag, "cluster": "general"} for tag in tags[:4]],
            "source": str(item.get("source") or ""),
        }
        cards = section_entry.get("cards")
        if isinstance(cards, list) and len(cards) < 3:
            cards.append(card)

    sections = [value for value in sections_map.values() if isinstance(value.get("cards"), list) and value["cards"]]
    if not sections and news_items:
        top = news_items[0]
        sections = [
            {
                "title": "今日热点",
                "badge": "聚焦",
                "cards": [
                    {
                        "source_title": _resolve_alias_in_text(str(top.get("title") or "热点事件"))[:80],
                        "headline": _resolve_alias_in_text(str(top.get("title") or "热点事件"))[:34],
                        "stance": "中性",
                        "heat": int(top.get("heat_score") or 60),
                        "summary": "当前热点讨论集中在高频议题，建议持续观察传播路径变化。",
                        "tags": [
                            {"name": tag, "cluster": "general"}
                            for tag in _extract_tags_from_title(_resolve_alias_in_text(str(top.get("title") or "")))
                        ],
                        "source": str(top.get("source") or ""),
                    }
                ],
            }
        ]

    return {
        "keyword_pool": keyword_pool[:14],
        "sections": sections[:3],
    }


def _fallback_overview(news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    top_titles = [
        _resolve_alias_in_text(str(item.get("title") or "").strip())
        for item in news_items[:6]
        if str(item.get("title") or "").strip()
    ]
    headline = "；".join(top_titles) if top_titles else "今日热点集中在综合社会与财经话题。"
    if len(headline) > 180:
        headline = headline[:177] + "..."

    bullets = []
    for item in news_items[:8]:
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        source = str(item.get("source") or "").strip()
        if not title:
            continue
        bullets.append(f"{source}：{title[:28]}{'...' if len(title) > 28 else ''}")
    if not bullets:
        bullets = ["当前未获取到有效热点条目。"]

    watch_points = [
        "持续关注政策类议题是否进入执行层面。",
        "观察科技话题是否从概念讨论转向量产进展。",
        "跟踪财经议题是否引发市场风险偏好变化。",
        "留意跨平台重复话题的传播扩散速度。",
    ]
    detailed_overview = (
        "从多平台热榜结构看，今日讨论重心集中在科技、宏观政策与国际局势三条主线。"
        "科技议题以产业进展和产品化应用为主，政策议题聚焦稳增长与产业支持，"
        "国际与金融议题则呈现事件驱动特征。整体传播节奏上，短标题和强结论内容更易进入前列，"
        "说明用户更偏好高信息密度的即时更新。"
    )

    return {
        "overview": headline,
        "detailed_overview": detailed_overview,
        "bullet_points": bullets[:8],
        "watch_points": watch_points,
        **_fallback_structured_payload(news_items),
        "summary_source": "fallback",
    }


def _normalise_section_payload(
    raw_sections: Any,
    *,
    fallback: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not isinstance(raw_sections, list):
        return list(fallback.get("sections") or [])

    def _normalise_cluster(raw: Any) -> str:
        cluster = str(raw or "").strip().lower()
        return cluster if cluster in ALLOWED_TAG_CLUSTERS else "general"

    sections: List[Dict[str, Any]] = []
    for raw in raw_sections:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        badge = str(raw.get("badge") or "关注").strip()[:10]
        cards_raw = raw.get("cards")
        cards: List[Dict[str, Any]] = []
        if isinstance(cards_raw, list):
            for item in cards_raw:
                if not isinstance(item, dict):
                    continue
                headline = str(item.get("headline") or "").strip()
                source_title = _resolve_alias_in_text(str(item.get("source_title") or "").strip())
                summary = str(item.get("summary") or "").strip()
                if not headline:
                    continue
                if not source_title:
                    source_title = headline
                stance = str(item.get("stance") or "中性").strip()
                if stance not in {"正向", "负向", "中性"}:
                    stance = "中性"
                try:
                    heat = int(item.get("heat") or 0)
                except (TypeError, ValueError):
                    heat = 0
                heat = max(1, min(100, heat))
                tags: List[Dict[str, str]] = []
                raw_tags = item.get("tags")
                if isinstance(raw_tags, list):
                    for tag in raw_tags:
                        if isinstance(tag, dict):
                            name = str(tag.get("name") or tag.get("text") or "").strip()
                            if not name:
                                continue
                            entry = {"name": name[:14], "cluster": _normalise_cluster(tag.get("cluster"))}
                        else:
                            name = str(tag or "").strip()
                            if not name:
                                continue
                            entry = {"name": name[:14], "cluster": "general"}
                        if not any(existing.get("name") == entry["name"] for existing in tags):
                            tags.append(entry)
                cards.append(
                    {
                        "headline": headline[:38],
                        "source_title": source_title[:80],
                        "summary": summary[:140],
                        "stance": stance,
                        "heat": heat,
                        "tags": tags[:5],
                    }
                )
        if cards:
            sections.append({"title": title[:16], "badge": badge, "cards": cards[:3]})

    if sections:
        return sections[:3]
    return list(fallback.get("sections") or [])


def _normalise_keywords(raw_keywords: Any, fallback: Dict[str, Any]) -> List[Dict[str, str]]:
    def _normalise_cluster(raw: Any) -> str:
        cluster = str(raw or "").strip().lower()
        return cluster if cluster in ALLOWED_TAG_CLUSTERS else "general"

    fallback_keywords = list(fallback.get("keyword_pool") or [])
    if not isinstance(raw_keywords, list):
        return fallback_keywords

    keywords: List[Dict[str, str]] = []
    for item in raw_keywords:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("name") or "").strip()
            cluster = _normalise_cluster(item.get("cluster"))
        else:
            text = str(item or "").strip()
            cluster = "general"
        if not text:
            continue
        if any(existing.get("text") == text for existing in keywords):
            continue
        keywords.append({"text": text[:18], "cluster": cluster})
    if keywords:
        return keywords[:14]
    return fallback_keywords


class _OverviewState(TypedDict):
    mode: str
    items: List[Dict[str, Any]]
    backgrounds: Dict[str, str]
    reclassify_target: str
    reclassify_hint: str
    link_candidates: Dict[str, List[str]]
    search_contexts: Dict[str, str]
    sense_map: Dict[str, Dict[str, Any]]
    evidence_meta: Dict[str, Dict[str, Any]]
    planner: Dict[str, Any]
    draft_payload: Dict[str, Any]
    final_payload: Dict[str, Any]
    critic: Dict[str, Any]


def _summarise_news(
    news_items: List[Dict[str, Any]], 
    reclassify_target: str = "", 
    reclassify_hint: str = "",
    existing_backgrounds: Dict[str, str] = None,
    mode: str = "fast",
) -> Dict[str, Any]:
    if not news_items:
        return {
            "overview": "今日暂无可用热点数据。",
            "detailed_overview": "当前热点源返回为空，建议稍后重试或切换数据源。",
            "bullet_points": ["请稍后刷新重试。"],
            "watch_points": ["检查数据源可用性与网络连通性。"],
            "keyword_pool": [],
            "sections": [],
            "summary_source": "fallback",
        }

    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return _fallback_overview(news_items)

    def _validate_payload(payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if not str(payload.get("overview") or "").strip():
            issues.append("missing_overview")
        points = payload.get("bullet_points")
        if not isinstance(points, list) or not points:
            issues.append("missing_bullet_points")
        sections = payload.get("sections")
        if not isinstance(sections, list) or not sections:
            issues.append("missing_sections")
        return len(issues) == 0, issues

    def _compress_background_text(text: str, limit: int = 280) -> str:
        compact = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3] + "..."

    def _planner_node(state: _OverviewState) -> _OverviewState:
        run_mode = "research" if str(state.get("mode") or "").lower() == "research" else "fast"
        plan = {
            "mode": run_mode,
            "max_prompt_items": 18 if run_mode == "fast" else 25,
            "evidence_fetch_count": 12 if run_mode == "fast" else 12,
            "link_scout_count": 12 if run_mode == "fast" else 12,
            "per_doc_input_chars": 1100 if run_mode == "fast" else 1800,
            "use_playwright_fallback": True,
            "playwright_max_docs": 2 if run_mode == "fast" else 4,
            "doc_summary_with_llm": run_mode == "research",
            "draft_max_tokens": 650 if run_mode == "fast" else 900,
            "refine_max_tokens": 700 if run_mode == "fast" else 950,
        }
        return {**state, "planner": plan}

    def _disambiguation_node(state: _OverviewState) -> _OverviewState:
        items = state.get("items", [])
        backgrounds = state.get("backgrounds", {}) or {}
        search_contexts = state.get("search_contexts", {}) or {}
        planner = state.get("planner", {}) or {}
        max_items = int(planner.get("evidence_fetch_count") or 12)

        lines: List[str] = []
        for idx, item in enumerate(items[:max_items], start=1):
            title = _resolve_alias_in_text(str(item.get("title") or "").strip())
            if not title:
                continue
            bg = str(backgrounds.get(title) or search_contexts.get(title) or "").strip()
            if bg:
                lines.append(f"{idx}. 标题: {title}\n   证据: {bg[:260]}")
            else:
                lines.append(f"{idx}. 标题: {title}\n   证据: 无")
        if not lines:
            return {**state, "sense_map": {}}

        prompt = (
            "你是语义消歧 agent。请仅根据给定证据判断每条标题中的歧义术语具体所指。"
            "输出 JSON：\n"
            "{\n"
            '  "title_senses":[\n'
            "    {\n"
            '      "title":"原始标题",\n'
            '      "canonical_topic":"该标题真实主题（12字内）",\n'
            '      "term_notes":[{"term":"歧义词","meaning":"具体所指","confidence":0.0}],\n'
            '      "evidence_level":"high|medium|low"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "规则：\n"
            "1) 只输出 JSON；2) 无证据时 evidence_level=low，meaning 写“未确认”；"
            "3) 不得凭常识编造未给出事实。\n\n"
            "输入：\n" + "\n".join(lines)
        )

        response_text = _safe_run_async(
            call_langchain_chat(
                [
                    {"role": "system", "content": "你是严谨的中文语义消歧助手。"},
                    {"role": "user", "content": prompt},
                ],
                task="report",
                temperature=0.0,
                max_tokens=700,
            )
        )
        payload = _extract_json_payload(str(response_text or "")) or {}
        raw_list = payload.get("title_senses")
        sense_map: Dict[str, Dict[str, Any]] = {}
        if isinstance(raw_list, list):
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                title = _resolve_alias_in_text(str(item.get("title") or "").strip())
                if not title:
                    continue
                canonical = str(item.get("canonical_topic") or "").strip()[:24]
                evidence_level = str(item.get("evidence_level") or "low").strip().lower()
                if evidence_level not in {"high", "medium", "low"}:
                    evidence_level = "low"
                term_notes = item.get("term_notes")
                normal_notes: List[Dict[str, Any]] = []
                if isinstance(term_notes, list):
                    for note in term_notes:
                        if not isinstance(note, dict):
                            continue
                        term = str(note.get("term") or "").strip()[:16]
                        meaning = str(note.get("meaning") or "").strip()[:64]
                        try:
                            confidence = float(note.get("confidence") or 0.0)
                        except Exception:
                            confidence = 0.0
                        confidence = max(0.0, min(1.0, confidence))
                        if term or meaning:
                            normal_notes.append(
                                {"term": term, "meaning": meaning, "confidence": confidence}
                            )
                sense_map[title] = {
                    "canonical_topic": canonical,
                    "evidence_level": evidence_level,
                    "term_notes": normal_notes[:4],
                }
        LOGGER.info(
            "hot_overview disambiguation | titles=%s resolved=%s",
            len(lines),
            len(sense_map),
        )
        return {**state, "sense_map": sense_map}

    def _draft_node(state: _OverviewState) -> _OverviewState:
        items = state.get("items", [])
        planner = state.get("planner", {})
        prompt = _build_prompt(
            items,
            backgrounds={},
            max_items=int(planner.get("max_prompt_items") or 18),
        )
        
        response_text = _safe_run_async(
            call_langchain_chat(
                [
                    {"role": "system", "content": "你是严谨的中文舆情分析助手。请根据新闻标题进行分类归纳。输出合法的JSON格式。"},
                    {"role": "user", "content": prompt},
                ],
                task="report",
                temperature=0.2,
                max_tokens=int(planner.get("draft_max_tokens") or 700),
            )
        )
        
        draft = {}
        if isinstance(response_text, str) and response_text.strip():
            payload = _extract_json_payload(response_text)
            if isinstance(payload, dict):
                draft = payload
        
        return {**state, "draft_payload": draft}

    def _research_node(state: _OverviewState) -> _OverviewState:
        backgrounds = dict(state.get("backgrounds") or {})
        evidence_meta = dict(state.get("evidence_meta") or {})
        items = state.get("items", [])
        target = state.get("reclassify_target")
        hint = state.get("reclassify_hint")
        planner = state.get("planner", {})
        link_candidates = state.get("link_candidates") or {}
        
        # Determine what to fetch.
        # If target, fetch that specific target. If no target, fetch top 3 items to ground the main overview.
        fetch_targets: List[Dict[str, Any]] = []
        if target:
            fetch_targets = [item for item in items if _resolve_alias_in_text(str(item.get("title") or "").strip()) == target]
        else:
            fetch_targets = items[: int(planner.get("evidence_fetch_count") or 3)]
                
        import concurrent.futures
        
        def fetch_and_summarize(item: Dict[str, Any], allow_playwright: bool) -> Tuple[str, str, Dict[str, Any]]:
            title = _resolve_alias_in_text(str(item.get("title") or "").strip())
            url = item.get("url") or item.get("mobileUrl") or ""
            if not title:
                return title, "", {}
            
            if title in backgrounds and title != target:
                return title, backgrounds[title], dict(evidence_meta.get(title) or {})
                
            candidate_urls = list(link_candidates.get(title) or [])
            if isinstance(url, str) and url.startswith("http") and url not in candidate_urls:
                candidate_urls.insert(0, url)
            if not candidate_urls and isinstance(url, str) and url.startswith("http"):
                candidate_urls = [url]

            text = ""
            selected_url = ""
            selected_method = ""
            for candidate in candidate_urls[:5]:
                text = _fetch_url_text(candidate)
                need_playwright = (not text) or _is_block_or_low_quality_text(text)
                if need_playwright and allow_playwright and bool(planner.get("use_playwright_fallback")):
                    text = _fetch_url_text_playwright(str(candidate), timeout_ms=12000)
                    if text:
                        selected_method = "playwright"
                else:
                    if text:
                        selected_method = "direct"
                if text and not _is_block_or_low_quality_text(text) and _is_context_relevant_to_title(title, text):
                    selected_url = str(candidate)
                    break
                text = ""

            if not text or _is_block_or_low_quality_text(text):
                return title, "", {"source_url": "", "method": "none", "relevance": "unmatched"}

            text = text[: int(planner.get("per_doc_input_chars") or 900)]

            # fast 模式尽量省 token：不用逐条 LLM 总结，直接截取压缩正文。
            if not bool(planner.get("doc_summary_with_llm")):
                return title, _compress_background_text(text, limit=200), {
                    "source_url": selected_url,
                    "method": selected_method or "direct",
                    "relevance": "matched",
                }

            prompt = (
                f"请简要总结这篇报道核心事实（120字内），用于辅助归类标题：“{title}”。"
                "过滤广告和无关导航。\n网页文本："
                + text
            )
            resp = _safe_run_async(
                call_langchain_chat(
                    [{"role": "user", "content": prompt}],
                    task="report",
                    temperature=0.1,
                    max_tokens=160,
                )
            )
            return title, _compress_background_text(str(resp or "").strip(), limit=220), {
                "source_url": selected_url,
                "method": selected_method or "direct",
                "relevance": "matched",
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            playwright_quota = int(planner.get("playwright_max_docs") or 0)
            futures = [
                executor.submit(fetch_and_summarize, item, idx < playwright_quota)
                for idx, item in enumerate(fetch_targets)
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    title, bg, meta = future.result()
                    if bg:
                        backgrounds[title] = bg
                        evidence_meta[title] = meta or {}
                except Exception as e:
                    LOGGER.warning("Research node fetch error: %s", e)

        if target and hint and target in backgrounds:
            backgrounds[target] = backgrounds[target].replace(f" [用户提示: {hint}]", "") + f" [用户提示: {hint}]"
        elif target and hint:
            backgrounds[target] = f"[用户提示: {hint}]"
            
        return {**state, "backgrounds": backgrounds, "evidence_meta": evidence_meta}

    def _link_scout_node(state: _OverviewState) -> _OverviewState:
        items = state.get("items", [])
        target = state.get("reclassify_target")
        planner = state.get("planner", {})
        scout_targets: List[Dict[str, Any]] = []
        if target:
            scout_targets = [item for item in items if _resolve_alias_in_text(str(item.get("title") or "").strip()) == target]
        else:
            scout_targets = items[: int(planner.get("link_scout_count") or planner.get("evidence_fetch_count") or 6)]

        if not scout_targets:
            return {**state, "link_candidates": {}, "search_contexts": {}}

        import concurrent.futures

        link_candidates: Dict[str, List[str]] = {}
        search_contexts: Dict[str, str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_discover_candidate_links, item, 8) for item in scout_targets]
            for future in concurrent.futures.as_completed(futures):
                try:
                    title, links, snippet = future.result()
                except Exception as exc:
                    LOGGER.warning("Link scout error: %s", exc)
                    continue
                if not title:
                    continue
                if links:
                    link_candidates[title] = links
                if snippet:
                    search_contexts[title] = snippet
        LOGGER.info(
            "hot_overview link_scout | targets=%s links=%s snippets=%s",
            len(scout_targets),
            sum(len(v) for v in link_candidates.values()),
            len(search_contexts),
        )
        return {**state, "link_candidates": link_candidates, "search_contexts": search_contexts}

    def _refine_node(state: _OverviewState) -> _OverviewState:
        items = state.get("items", [])
        backgrounds = state.get("backgrounds", {})
        evidence_meta = state.get("evidence_meta", {}) or {}
        sense_map = state.get("sense_map", {}) or {}
        draft = state.get("draft_payload", {})
        planner = state.get("planner", {})
        fallback_structured = _fallback_structured_payload(items)
        
        prompt = _build_prompt(
            items,
            backgrounds=backgrounds,
            max_items=int(planner.get("max_prompt_items") or 18),
        )
        draft_str = json.dumps(draft, ensure_ascii=False) if draft else "{}"
        sense_str = json.dumps(sense_map, ensure_ascii=False) if sense_map else "{}"
        
        instruction = f"""你是专业严谨的舆情主编。
这是我们之前基于标题生成的【初稿】：
{draft_str}

这是带有部分新闻背景调查的新输入：
{prompt}

这是语义消歧 agent 给出的“标题真实所指”：
{sense_str}

请根据最新的背景调查信息，反思并修正初稿。
1. 检查初稿中是否存在望文生义的分类（比如将科技项目错认为农业生态等）。若有，必须将其移动到正确的分类，并更新概要和关键词。
2. 尊重[背景补充]的内容以及用户的提示。
3. 请严格返回和以前完全一样的 JSON 结构（overview, detailed_overview, bullet_points, watch_points, keyword_pool, sections）。
4. keyword_pool 每个对象都必须包含 text 和 cluster；cards.tags 每个对象都必须包含 name 和 cluster；cards.source_title 必须保留原始热榜标题。
5. 对每张卡片 summary：如果输入存在[背景补充]，必须写背景中的具体事实；没有背景时只写标题可证事实，不要联想推测。
6. 若出现歧义术语（如“龙虾”），必须在 overview 或 detailed_overview 中明确说明其在本批数据中的具体所指。
7. 禁止空话套话（如“引发关注”“释放信号”“体现立场”等无事实承载表述）。
8. 对含歧义词的卡片，分类与标签必须服从“标题真实所指”，不能按字面归类。
9. 卡片 summary 只能复述输入证据里的事实，不得新增未出现的漏洞编号、版本号、时间或主体。
"""
        response_text = _safe_run_async(
            call_langchain_chat(
                [{"role": "user", "content": instruction}],
                task="report",
                temperature=0.2,
                max_tokens=int(planner.get("refine_max_tokens") or 750),
            )
        )

        final_payload = {}
        if isinstance(response_text, str) and response_text.strip():
            payload = _extract_json_payload(response_text)
            if isinstance(payload, dict):
                overview = str(payload.get("overview") or draft.get("overview") or "").strip()
                detailed_overview = str(payload.get("detailed_overview") or draft.get("detailed_overview") or "").strip()
                raw_points = payload.get("bullet_points") or draft.get("bullet_points")
                raw_watch_points = payload.get("watch_points") or draft.get("watch_points")
                raw_keywords = payload.get("keyword_pool") or draft.get("keyword_pool")
                raw_sections = payload.get("sections") or draft.get("sections")
                
                points: List[str] = []
                watch_points: List[str] = []
                if isinstance(raw_points, list):
                    points = [str(p).strip() for p in raw_points if str(p).strip()]
                if isinstance(raw_watch_points, list):
                    watch_points = [str(p).strip() for p in raw_watch_points if str(p).strip()]
                
                if overview and points:
                    normalised_sections = _normalise_section_payload(raw_sections, fallback=fallback_structured)
                    grounded_sections = _ground_sections_with_evidence(
                        normalised_sections,
                        backgrounds,
                        evidence_meta=evidence_meta,
                    )
                    final_payload = {
                        "overview": overview[:220],
                        "detailed_overview": detailed_overview[:420],
                        "bullet_points": points[:8],
                        "watch_points": watch_points[:6],
                        "keyword_pool": _normalise_keywords(raw_keywords, fallback_structured),
                        "sections": grounded_sections,
                        "summary_source": "langchain_reflective",
                    }
        
        # Fallback to draft if refinement fails or yields nothing
        if not final_payload and draft:
            draft["summary_source"] = "langchain_draft"
            final_payload = draft
            
        return {**state, "final_payload": final_payload}

    def _critic_node(state: _OverviewState) -> _OverviewState:
        final_payload = state.get("final_payload") or {}
        ok, issues = _validate_payload(final_payload)
        backgrounds = state.get("backgrounds") or {}
        sense_map = state.get("sense_map") or {}
        sections = final_payload.get("sections") if isinstance(final_payload, dict) else []
        card_count = 0
        for section in sections if isinstance(sections, list) else []:
            if isinstance(section, dict) and isinstance(section.get("cards"), list):
                card_count += len(section.get("cards") or [])
        critic = {
            "ok": ok,
            "issues": issues,
            "evidence_count": len(backgrounds),
            "card_count": card_count,
            "evidence_coverage": round((len(backgrounds) / max(1, card_count)), 2),
            "sense_resolved_count": len(sense_map) if isinstance(sense_map, dict) else 0,
        }
        if not backgrounds:
            critic["issues"] = list(critic["issues"]) + ["low_evidence"]
        return {**state, "critic": critic}

    def _resolver_node(state: _OverviewState) -> _OverviewState:
        final_payload = dict(state.get("final_payload") or {})
        draft = dict(state.get("draft_payload") or {})
        critic = state.get("critic") or {}
        backgrounds = state.get("backgrounds") or {}
        evidence_meta = state.get("evidence_meta") or {}
        if not bool(critic.get("ok")):
            if draft:
                draft["summary_source"] = "langchain_draft_resolved"
                final_payload = draft
            else:
                final_payload = _fallback_overview(state.get("items", []))
                final_payload["summary_source"] = "fallback_resolved"
        sections = final_payload.get("sections")
        if isinstance(sections, list):
            final_payload["sections"] = _ground_sections_with_evidence(
                sections,
                backgrounds,
                evidence_meta=evidence_meta if isinstance(evidence_meta, dict) else {},
            )
        final_payload["_critic"] = critic
        return {**state, "final_payload": final_payload}

    try:
        workflow = StateGraph(_OverviewState)
        workflow.add_node("planner", _planner_node)
        workflow.add_node("draft", _draft_node)
        workflow.add_node("link_scout", _link_scout_node)
        workflow.add_node("research", _research_node)
        workflow.add_node("disambiguation", _disambiguation_node)
        workflow.add_node("refine", _refine_node)
        workflow.add_node("critic", _critic_node)
        workflow.add_node("resolver", _resolver_node)
        
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "draft")
        workflow.add_edge("draft", "link_scout")
        workflow.add_edge("link_scout", "research")
        workflow.add_edge("research", "disambiguation")
        workflow.add_edge("disambiguation", "refine")
        workflow.add_edge("refine", "critic")
        workflow.add_edge("critic", "resolver")
        workflow.add_edge("resolver", END)
        app = workflow.compile()
        
        result = app.invoke({
            "mode": mode,
            "items": news_items,
            "backgrounds": existing_backgrounds or {},
            "reclassify_target": reclassify_target,
            "reclassify_hint": reclassify_hint,
            "link_candidates": {},
            "search_contexts": {},
            "sense_map": {},
            "evidence_meta": {},
            "planner": {},
            "draft_payload": {},
            "final_payload": {},
            "critic": {},
        })
        
        final_payload = result.get("final_payload")
        if final_payload:
            backgrounds = result.get("backgrounds", {}) or {}
            link_candidates = result.get("link_candidates", {}) or {}
            search_contexts = result.get("search_contexts", {}) or {}
            touched_titles = set()
            touched_titles.update(str(k) for k in link_candidates.keys())
            touched_titles.update(str(k) for k in search_contexts.keys())
            evidence_hit_count = 0
            samples: List[Dict[str, Any]] = []
            for title in list(touched_titles)[:6]:
                candidates = link_candidates.get(title) if isinstance(link_candidates, dict) else []
                if isinstance(backgrounds, dict) and str(backgrounds.get(title) or "").strip():
                    evidence_hit_count += 1
                samples.append(
                    {
                        "title": title[:52],
                        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
                        "has_search_snippet": bool(str(search_contexts.get(title) or "").strip()) if isinstance(search_contexts, dict) else False,
                        "has_evidence": bool(str(backgrounds.get(title) or "").strip()) if isinstance(backgrounds, dict) else False,
                    }
                )
            link_scout_diag = {
                "title_count": len(touched_titles),
                "candidate_link_count": sum(
                    len(v) for v in link_candidates.values() if isinstance(v, list)
                ) if isinstance(link_candidates, dict) else 0,
                "snippet_count": len(search_contexts) if isinstance(search_contexts, dict) else 0,
                "evidence_hit_count": evidence_hit_count,
                "samples": samples,
            }
            final_payload["_backgrounds"] = backgrounds
            final_payload["_planner"] = result.get("planner", {})
            final_payload["_link_scout"] = link_scout_diag
            final_payload["_sense_map"] = result.get("sense_map", {})
            final_payload["_evidence_meta"] = result.get("evidence_meta", {})
            LOGGER.info(
                "hot_overview diagnostics | scout_titles=%s candidates=%s snippets=%s evidence_hits=%s sense_resolved=%s evidence_meta=%s",
                int(link_scout_diag.get("title_count") or 0),
                int(link_scout_diag.get("candidate_link_count") or 0),
                int(link_scout_diag.get("snippet_count") or 0),
                int(link_scout_diag.get("evidence_hit_count") or 0),
                len(result.get("sense_map", {}) or {}),
                len(result.get("evidence_meta", {}) or {}),
            )
            return final_payload
            
    except Exception as exc:
        LOGGER.warning("Overview multi-agent failed: %s", exc)

    return _fallback_overview(news_items)

def list_hot_overview_history(
    *,
    mode: str = "fast",
    include_research: Optional[bool] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    cache_key = _resolve_mode(mode=mode, include_research=include_research)
    history = _HISTORY.get(cache_key, [])
    clamped_limit = max(1, min(50, int(limit or 10)))
    selected = history[-clamped_limit:]
    selected = list(reversed(selected))
    records: List[Dict[str, Any]] = []
    for item in selected:
        if not isinstance(item, dict):
            continue
        records.append(
            {
                "revision_id": str(item.get("revision_id") or ""),
                "generated_at": str(item.get("generated_at") or ""),
                "snapshot_date": str(item.get("snapshot_date") or ""),
                "summary_source": str(item.get("summary_source") or ""),
                "total_items": int(item.get("total_items") or 0),
                "mode": str(item.get("mode") or cache_key),
            }
        )
    return records


def rollback_hot_overview_revision(
    *,
    revision_id: str,
    mode: str = "fast",
    include_research: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    rid = str(revision_id or "").strip()
    if not rid:
        return None
    cache_key = _resolve_mode(mode=mode, include_research=include_research)
    history = _HISTORY.get(cache_key, [])
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("revision_id") or "") != rid:
            continue
        payload = _clone_payload(item)
        if not str(payload.get("snapshot_date") or "").strip():
            payload["snapshot_date"] = _today_snapshot_date()
        cache_slot = _CACHE.setdefault(cache_key, {"data": None, "expires_at": 0.0})
        cache_slot["data"] = payload
        cache_slot["expires_at"] = time.time() + CACHE_TTL_SECONDS
        _save_archive_payload(cache_key, payload)
        LOGGER.info(
            "hot_overview rollback | cache_key=%s revision_id=%s total_items=%s",
            cache_key,
            rid,
            int(payload.get("total_items") or 0),
        )
        return payload
    return None


def get_today_hot_overview(
    *,
    limit: int = DEFAULT_LIMIT,
    force_refresh: bool = False,
    mode: str = "fast",
    include_research: Optional[bool] = None,
) -> Dict[str, Any]:
    """Fetch hot topics and produce an AI overview for homepage."""
    now = time.time()
    today = _today_snapshot_date()
    cache_key = _resolve_mode(mode=mode, include_research=include_research)
    run_research = cache_key == "research"
    cache_slot = _CACHE.setdefault(cache_key, {"data": None, "expires_at": 0.0})
    LOGGER.info(
        "hot_overview start | force_refresh=%s limit=%s mode=%s today=%s",
        force_refresh,
        limit,
        cache_key,
        today,
    )
    if not force_refresh:
        cached_data = cache_slot.get("data")
        if _is_payload_fresh_for_today(cached_data, today):
            payload = _apply_limit_to_payload(cached_data, limit)
            LOGGER.info(
                "hot_overview memory_hit | snapshot_date=%s total_items=%s summary_source=%s",
                today,
                int(payload.get("total_items") or 0),
                payload.get("summary_source"),
            )
            return payload

        archived_data = _load_archive_payload(cache_key)
        if _is_payload_fresh_for_today(archived_data, today):
            cache_slot["data"] = _clone_payload(archived_data)
            cache_slot["expires_at"] = now + CACHE_TTL_SECONDS
            payload = _apply_limit_to_payload(archived_data, limit)
            LOGGER.info(
                "hot_overview archive_hit | snapshot_date=%s mode=%s total_items=%s",
                today,
                cache_key,
                int(payload.get("total_items") or 0),
            )
            return payload

    all_items: List[Dict[str, Any]] = []
    source_stats: List[Dict[str, Any]] = []
    for source_id, source_name in HOT_SOURCE_CONFIG:
        items = _fetch_platform_hot_items(source_id, source_name, top_n=20)
        source_stats.append(
            {
                "source_id": source_id,
                "source": source_name,
                "count": len(items),
            }
        )
        all_items.extend(items)
        LOGGER.info("hot_overview source_fetched | source=%s count=%s", source_id, len(items))

    existing_bg = {}
    if cache_slot["data"] is not None:
        existing_bg = cache_slot["data"].get("_backgrounds", {})

    merged_items = _merge_and_sort_items(all_items)
    summary = _summarise_news(merged_items, existing_backgrounds=existing_bg, mode=cache_key)
    clamped_limit = max(5, min(40, int(limit or DEFAULT_LIMIT)))
    selected_items = merged_items[:clamped_limit]

    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "revision_id": _new_revision_id(),
        "generated_at": generated_at,
        "snapshot_date": today,
        "mode": cache_key,
        "summary_source": summary.get("summary_source", "fallback"),
        "overview": summary.get("overview", ""),
        "detailed_overview": summary.get("detailed_overview", ""),
        "bullet_points": summary.get("bullet_points", []),
        "watch_points": summary.get("watch_points", []),
        "keyword_pool": summary.get("keyword_pool", []),
        "sections": summary.get("sections", []),
        "items": selected_items,
        "total_items": len(merged_items),
        "sources": source_stats,
        "research": None,
        "evidence": {
            "enabled": True,
            "mode": cache_key,
            "doc_count": len(summary.get("_backgrounds", {}) or {}),
            "titles": list((summary.get("_backgrounds", {}) or {}).keys())[:6],
        },
        "diagnostics": {
            "planner": summary.get("_planner", {}),
            "critic": summary.get("_critic", {}),
            "link_scout": summary.get("_link_scout", {}),
            "sense_map": summary.get("_sense_map", {}),
            "evidence_meta": summary.get("_evidence_meta", {}),
        },
        "_backgrounds": summary.get("_backgrounds", {}),
        "_merged_items": merged_items,
    }

    if run_research:
        payload["research"] = _run_research_langgraph(merged_items)

    cache_slot["data"] = _clone_payload(payload)
    cache_slot["expires_at"] = now + CACHE_TTL_SECONDS
    _save_archive_payload(cache_key, payload)
    _push_history(cache_key, payload)
    link_scout_diag = payload.get("diagnostics", {}).get("link_scout", {})
    sense_map = payload.get("diagnostics", {}).get("sense_map", {})
    evidence_meta = payload.get("diagnostics", {}).get("evidence_meta", {})
    LOGGER.info(
        "hot_overview built | snapshot_date=%s total_items=%s selected=%s summary_source=%s keywords=%s sections=%s mode=%s scout_titles=%s scout_candidates=%s scout_hits=%s sense_resolved=%s evidence_meta=%s",
        today,
        len(merged_items),
        len(selected_items),
        payload.get("summary_source"),
        len(payload.get("keyword_pool") or []),
        len(payload.get("sections") or []),
        cache_key,
        int(link_scout_diag.get("title_count") or 0),
        int(link_scout_diag.get("candidate_link_count") or 0),
        int(link_scout_diag.get("evidence_hit_count") or 0),
        len(sense_map) if isinstance(sense_map, dict) else 0,
        len(evidence_meta) if isinstance(evidence_meta, dict) else 0,
    )
    return payload


def reclassify_hot_overview(
    *,
    target_title: str,
    hint: str,
    mode: str = "fast",
    include_research: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    cache_key = _resolve_mode(mode=mode, include_research=include_research)
    cache_slot = _CACHE.setdefault(cache_key, {"data": None, "expires_at": 0.0})
    
    if not cache_slot["data"]:
        return None
        
    old_payload = cache_slot["data"]
    merged_items = old_payload.get("_merged_items", [])
    if not merged_items:
        return None
        
    existing_bg = old_payload.get("_backgrounds", {})
    summary = _summarise_news(
        merged_items, 
        reclassify_target=target_title, 
        reclassify_hint=hint,
        existing_backgrounds=existing_bg,
        mode=cache_key,
    )
    
    now = time.time()
    generated_at = datetime.now(timezone.utc).isoformat()
    selected_items = old_payload.get("items", [])
    
    payload = {
        "revision_id": _new_revision_id(),
        "generated_at": generated_at,
        "snapshot_date": _today_snapshot_date(),
        "mode": cache_key,
        "summary_source": summary.get("summary_source", "fallback"),
        "overview": summary.get("overview", ""),
        "detailed_overview": summary.get("detailed_overview", ""),
        "bullet_points": summary.get("bullet_points", []),
        "watch_points": summary.get("watch_points", []),
        "keyword_pool": summary.get("keyword_pool", []),
        "sections": summary.get("sections", []),
        "items": selected_items,
        "total_items": len(merged_items),
        "sources": old_payload.get("sources", []),
        "research": old_payload.get("research"),
        "evidence": {
            "enabled": True,
            "mode": cache_key,
            "doc_count": len(summary.get("_backgrounds", {}) or {}),
            "titles": list((summary.get("_backgrounds", {}) or {}).keys())[:6],
        },
        "diagnostics": {
            "planner": summary.get("_planner", {}),
            "critic": summary.get("_critic", {}),
            "link_scout": summary.get("_link_scout", {}),
            "sense_map": summary.get("_sense_map", {}),
            "evidence_meta": summary.get("_evidence_meta", {}),
        },
        "_backgrounds": summary.get("_backgrounds", {}),
        "_merged_items": merged_items,
    }
    
    cache_slot["data"] = _clone_payload(payload)
    cache_slot["expires_at"] = now + CACHE_TTL_SECONDS
    _save_archive_payload(cache_key, payload)
    _push_history(cache_key, payload)
    
    link_scout_diag = payload.get("diagnostics", {}).get("link_scout", {})
    evidence_meta = payload.get("diagnostics", {}).get("evidence_meta", {})
    LOGGER.info(
        "hot_overview reclassified | target=%s hint=%s summary_source=%s sections=%s scout_titles=%s scout_candidates=%s scout_hits=%s evidence_meta=%s",
        target_title,
        hint,
        payload.get("summary_source"),
        len(payload.get("sections") or []),
        int(link_scout_diag.get("title_count") or 0),
        int(link_scout_diag.get("candidate_link_count") or 0),
        int(link_scout_diag.get("evidence_hit_count") or 0),
        len(evidence_meta) if isinstance(evidence_meta, dict) else 0,
    )
    return payload
