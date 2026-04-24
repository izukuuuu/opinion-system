"""Homepage hot-overview helper based on public hot-list feeds."""

from __future__ import annotations

import asyncio
import copy
import html
import json
import logging
import re
import threading
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
_HOT_OVERVIEW_FILTER_CONFIG = Path(__file__).resolve().with_name("hot_overview_filters.yaml")
_DEFAULT_BLOCK_PAGE_PATTERNS: Tuple[str, ...] = (
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
_DEFAULT_GENERIC_SUMMARY_PATTERNS: Tuple[str, ...] = (
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
_ADMISSIBLE_EVIDENCE_STATUSES = {"relevant", "single_source", "corroborated"}
_UNCERTAIN_EVIDENCE_STATUSES = {"retrieved", "weak_match", "unresolved", "contradicted"}
_DEFAULT_NAV_MENU_TOKENS: Tuple[str, ...] = (
    "关于我们",
    "网站声明",
    "联系方式",
    "用户反馈",
    "网站地图",
    "帮助",
    "注册",
    "登录",
    "首页",
    "电报",
    "话题",
    "盯盘",
    "VIP",
    "下载",
    "头条",
    "A股",
    "港股",
    "基金",
    "地产",
    "金融",
    "汽车",
    "科创",
    "品见",
)
_DEFAULT_FACT_MARKER_PATTERN = (
    r"(来源：|记者|当地时间|发布|表示|指出|回应|通报|报告|称|宣布|"
    r"20\d{2}年\d{1,2}月\d{1,2}日|。|：)"
)
_DEFAULT_NAV_NOISE_MARKERS: Tuple[str, ...] = (
    "关于我们",
    "网站声明",
    "联系方式",
    "用户反馈",
    "网站地图",
    "注册|登录",
    "节目官网",
    "节目单",
    "栏目片库",
    "首页电报话题",
)
_DEFAULT_SHARE_NOISE_MARKERS: Tuple[str, ...] = (
    "微信扫描二维码",
    "分享到好友和朋友圈",
    "分享至好友和朋友圈",
    "打开微信",
    "微信扫一扫",
    "复制链接",
)
_DEFAULT_OFFICIAL_DOMAIN_SUFFIXES: Tuple[str, ...] = (
    ".gov.cn",
    ".gov",
    ".edu.cn",
    ".edu",
)
_DEFAULT_LOW_TRUST_DOMAIN_TOKENS: Tuple[str, ...] = (
    "weibo.com",
    "toutiao.com",
    "tieba.baidu.com",
    "zhihu.com",
    "search.bilibili.com",
    "m.bilibili.com",
)
_DEFAULT_AUTHORITY_DOMAIN_SCORES: Dict[str, float] = {}
_DEFAULT_QUALITY_GATE: Dict[str, float] = {
    "min_chars": 220.0,
    "min_sentences": 3.0,
    "min_readerable_score": 0.48,
    "max_nav_hits": 12.0,
}


def _coerce_string_list(value: Any, defaults: Tuple[str, ...]) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return defaults
    items: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return tuple(items) if items else defaults


def _coerce_float_map(value: Any, defaults: Dict[str, float]) -> Dict[str, float]:
    if not isinstance(value, dict):
        return dict(defaults)
    result: Dict[str, float] = {}
    for key, raw in value.items():
        domain = str(key or "").strip().lower()
        if not domain:
            continue
        try:
            score = float(raw)
        except Exception:
            continue
        result[domain] = max(0.0, min(1.0, score))
    return result if result else dict(defaults)


def _coerce_quality_gate(value: Any, defaults: Dict[str, float]) -> Dict[str, float]:
    result = dict(defaults)
    if not isinstance(value, dict):
        return result
    for key in ("min_chars", "min_sentences", "min_readerable_score", "max_nav_hits"):
        if key not in value:
            continue
        try:
            result[key] = float(value.get(key))
        except Exception:
            continue
    result["min_chars"] = max(80.0, result["min_chars"])
    result["min_sentences"] = max(1.0, result["min_sentences"])
    result["min_readerable_score"] = max(0.1, min(0.95, result["min_readerable_score"]))
    result["max_nav_hits"] = max(2.0, result["max_nav_hits"])
    return result


def _load_hot_overview_filter_config() -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "block_page_patterns": list(_DEFAULT_BLOCK_PAGE_PATTERNS),
        "generic_summary_patterns": list(_DEFAULT_GENERIC_SUMMARY_PATTERNS),
        "nav_menu_tokens": list(_DEFAULT_NAV_MENU_TOKENS),
        "nav_noise_markers": list(_DEFAULT_NAV_NOISE_MARKERS),
        "share_noise_markers": list(_DEFAULT_SHARE_NOISE_MARKERS),
        "fact_marker_pattern": _DEFAULT_FACT_MARKER_PATTERN,
        "official_domain_suffixes": list(_DEFAULT_OFFICIAL_DOMAIN_SUFFIXES),
        "low_trust_domain_tokens": list(_DEFAULT_LOW_TRUST_DOMAIN_TOKENS),
        "authority_domain_scores": dict(_DEFAULT_AUTHORITY_DOMAIN_SCORES),
        "quality_gate": dict(_DEFAULT_QUALITY_GATE),
    }
    if not _HOT_OVERVIEW_FILTER_CONFIG.exists():
        return config
    try:
        import yaml  # type: ignore

        with _HOT_OVERVIEW_FILTER_CONFIG.open("r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
    except Exception as exc:
        warn_key = f"hot_overview_filters:{_HOT_OVERVIEW_FILTER_CONFIG}"
        if warn_key not in _WARNED_FETCH_KEYS:
            _WARNED_FETCH_KEYS.add(warn_key)
            logging.getLogger(__name__).warning("Failed to load hot_overview filter config: %s", exc)
        return config
    if isinstance(payload, dict):
        config["block_page_patterns"] = list(
            _coerce_string_list(payload.get("block_page_patterns"), _DEFAULT_BLOCK_PAGE_PATTERNS)
        )
        config["generic_summary_patterns"] = list(
            _coerce_string_list(payload.get("generic_summary_patterns"), _DEFAULT_GENERIC_SUMMARY_PATTERNS)
        )
        config["nav_menu_tokens"] = list(
            _coerce_string_list(payload.get("nav_menu_tokens"), _DEFAULT_NAV_MENU_TOKENS)
        )
        config["nav_noise_markers"] = list(
            _coerce_string_list(payload.get("nav_noise_markers"), _DEFAULT_NAV_NOISE_MARKERS)
        )
        config["share_noise_markers"] = list(
            _coerce_string_list(payload.get("share_noise_markers"), _DEFAULT_SHARE_NOISE_MARKERS)
        )
        fact_pattern = str(payload.get("fact_marker_pattern") or "").strip()
        if fact_pattern:
            config["fact_marker_pattern"] = fact_pattern
        config["official_domain_suffixes"] = list(
            _coerce_string_list(payload.get("official_domain_suffixes"), _DEFAULT_OFFICIAL_DOMAIN_SUFFIXES)
        )
        config["low_trust_domain_tokens"] = list(
            _coerce_string_list(payload.get("low_trust_domain_tokens"), _DEFAULT_LOW_TRUST_DOMAIN_TOKENS)
        )
        config["authority_domain_scores"] = _coerce_float_map(
            payload.get("authority_domain_scores"),
            _DEFAULT_AUTHORITY_DOMAIN_SCORES,
        )
        config["quality_gate"] = _coerce_quality_gate(payload.get("quality_gate"), _DEFAULT_QUALITY_GATE)
    return config


_LOADED_FILTER_CONFIG: Dict[str, Any] = {}
_BLOCK_PAGE_PATTERNS: Tuple[str, ...] = _DEFAULT_BLOCK_PAGE_PATTERNS
_GENERIC_SUMMARY_PATTERNS: Tuple[str, ...] = _DEFAULT_GENERIC_SUMMARY_PATTERNS
_NAV_MENU_TOKENS: Tuple[str, ...] = _DEFAULT_NAV_MENU_TOKENS
_NAV_NOISE_MARKERS: Tuple[str, ...] = _DEFAULT_NAV_NOISE_MARKERS
_SHARE_NOISE_MARKERS: Tuple[str, ...] = _DEFAULT_SHARE_NOISE_MARKERS
_OFFICIAL_DOMAIN_SUFFIXES: Tuple[str, ...] = _DEFAULT_OFFICIAL_DOMAIN_SUFFIXES
_LOW_TRUST_DOMAIN_TOKENS: Tuple[str, ...] = _DEFAULT_LOW_TRUST_DOMAIN_TOKENS
_AUTHORITY_DOMAIN_SCORES: Dict[str, float] = dict(_DEFAULT_AUTHORITY_DOMAIN_SCORES)
_QUALITY_GATE_CONFIG: Dict[str, float] = dict(_DEFAULT_QUALITY_GATE)
_FACT_MARKER_PATTERN = re.compile(_DEFAULT_FACT_MARKER_PATTERN)
_FILTER_CONFIG_MTIME: Optional[float] = None
_FILTER_CONFIG_LAST_CHECK_TS: float = 0.0
_FILTER_CONFIG_CHECK_INTERVAL_SECONDS = 2.0
_FILTER_CONFIG_LOCK = threading.Lock()


def _compile_fact_marker_pattern(pattern: str) -> Any:
    candidate = str(pattern or "").strip()
    if not candidate:
        candidate = _DEFAULT_FACT_MARKER_PATTERN
    try:
        return re.compile(candidate)
    except re.error as exc:
        warn_key = f"hot_overview_filters:regex:{candidate}"
        if warn_key not in _WARNED_FETCH_KEYS:
            _WARNED_FETCH_KEYS.add(warn_key)
            logging.getLogger(__name__).warning("Invalid fact_marker_pattern in filter config: %s", exc)
        return re.compile(_DEFAULT_FACT_MARKER_PATTERN)


def _apply_hot_overview_filter_config(config: Dict[str, Any]) -> None:
    global _LOADED_FILTER_CONFIG
    global _BLOCK_PAGE_PATTERNS
    global _GENERIC_SUMMARY_PATTERNS
    global _NAV_MENU_TOKENS
    global _NAV_NOISE_MARKERS
    global _SHARE_NOISE_MARKERS
    global _OFFICIAL_DOMAIN_SUFFIXES
    global _LOW_TRUST_DOMAIN_TOKENS
    global _AUTHORITY_DOMAIN_SCORES
    global _QUALITY_GATE_CONFIG
    global _FACT_MARKER_PATTERN
    _LOADED_FILTER_CONFIG = dict(config or {})
    _BLOCK_PAGE_PATTERNS = tuple(_LOADED_FILTER_CONFIG.get("block_page_patterns") or _DEFAULT_BLOCK_PAGE_PATTERNS)
    _GENERIC_SUMMARY_PATTERNS = tuple(
        _LOADED_FILTER_CONFIG.get("generic_summary_patterns") or _DEFAULT_GENERIC_SUMMARY_PATTERNS
    )
    _NAV_MENU_TOKENS = tuple(_LOADED_FILTER_CONFIG.get("nav_menu_tokens") or _DEFAULT_NAV_MENU_TOKENS)
    _NAV_NOISE_MARKERS = tuple(_LOADED_FILTER_CONFIG.get("nav_noise_markers") or _DEFAULT_NAV_NOISE_MARKERS)
    _SHARE_NOISE_MARKERS = tuple(
        _LOADED_FILTER_CONFIG.get("share_noise_markers") or _DEFAULT_SHARE_NOISE_MARKERS
    )
    _OFFICIAL_DOMAIN_SUFFIXES = tuple(
        _LOADED_FILTER_CONFIG.get("official_domain_suffixes") or _DEFAULT_OFFICIAL_DOMAIN_SUFFIXES
    )
    _LOW_TRUST_DOMAIN_TOKENS = tuple(
        _LOADED_FILTER_CONFIG.get("low_trust_domain_tokens") or _DEFAULT_LOW_TRUST_DOMAIN_TOKENS
    )
    _AUTHORITY_DOMAIN_SCORES = _coerce_float_map(
        _LOADED_FILTER_CONFIG.get("authority_domain_scores"),
        _DEFAULT_AUTHORITY_DOMAIN_SCORES,
    )
    _QUALITY_GATE_CONFIG = _coerce_quality_gate(
        _LOADED_FILTER_CONFIG.get("quality_gate"),
        _DEFAULT_QUALITY_GATE,
    )
    _FACT_MARKER_PATTERN = _compile_fact_marker_pattern(
        str(_LOADED_FILTER_CONFIG.get("fact_marker_pattern") or _DEFAULT_FACT_MARKER_PATTERN)
    )


def _refresh_hot_overview_filter_config_if_needed(*, force: bool = False) -> bool:
    global _FILTER_CONFIG_MTIME
    global _FILTER_CONFIG_LAST_CHECK_TS
    now = time.time()
    if not force and (now - _FILTER_CONFIG_LAST_CHECK_TS) < _FILTER_CONFIG_CHECK_INTERVAL_SECONDS:
        return False
    _FILTER_CONFIG_LAST_CHECK_TS = now
    try:
        mtime = _HOT_OVERVIEW_FILTER_CONFIG.stat().st_mtime if _HOT_OVERVIEW_FILTER_CONFIG.exists() else None
    except OSError:
        mtime = None
    if not force and mtime == _FILTER_CONFIG_MTIME:
        return False
    with _FILTER_CONFIG_LOCK:
        try:
            current_mtime = _HOT_OVERVIEW_FILTER_CONFIG.stat().st_mtime if _HOT_OVERVIEW_FILTER_CONFIG.exists() else None
        except OSError:
            current_mtime = None
        if not force and current_mtime == _FILTER_CONFIG_MTIME:
            return False
        config = _load_hot_overview_filter_config()
        _apply_hot_overview_filter_config(config)
        _FILTER_CONFIG_MTIME = current_mtime
        _URL_TEXT_CACHE.clear()
        logging.getLogger(__name__).info(
            "hot_overview filters reloaded | file=%s mtime=%s block=%s generic=%s nav_tokens=%s authority_overrides=%s",
            _HOT_OVERVIEW_FILTER_CONFIG,
            current_mtime,
            len(_BLOCK_PAGE_PATTERNS),
            len(_GENERIC_SUMMARY_PATTERNS),
            len(_NAV_MENU_TOKENS),
            len(_AUTHORITY_DOMAIN_SCORES),
        )
        return True


_refresh_hot_overview_filter_config_if_needed(force=True)


def _trim_navigation_prefix(line: str) -> str:
    text = str(line or "").strip()
    if not text:
        return ""
    source_idx = text.find("来源：")
    if source_idx > 80 and len(text) > 220:
        start_idx = max(0, source_idx - 56)
        candidate = text[start_idx:].strip(" |-·")
        candidate = re.sub(r"^.*?(白名单|栏目片库|节目单)", "", candidate).strip(" |-·")
        if len(candidate) >= 24:
            return candidate
    m_date = re.search(r"20\d{2}年\d{1,2}月\d{1,2}日", text)
    if m_date and int(m_date.start()) > 80 and len(text) > 220:
        start_idx = max(0, int(m_date.start()) - 56)
        candidate = text[start_idx:].strip(" |-·")
        if len(candidate) >= 24:
            return candidate
    hits = [token for token in _NAV_MENU_TOKENS if token in text]
    if len(hits) < 4:
        return text
    cut_idx = 0
    for token in hits:
        pos = text.rfind(token)
        if pos >= 0:
            cut_idx = max(cut_idx, pos + len(token))
    tail = text[cut_idx:].strip(" |-·")
    return tail if len(tail) >= 12 else ""


def _strip_share_noise(text: str) -> str:
    line = str(text or "").strip()
    if not line:
        return ""
    cleaned = line
    for token in _SHARE_NOISE_MARKERS:
        marker = str(token or "").strip()
        if not marker:
            continue
        pos = cleaned.find(marker)
        if pos < 0:
            continue
        # If share/social marker appears near prefix, trim it away.
        if pos <= 42 and len(cleaned) > (pos + len(marker) + 12):
            cleaned = cleaned[pos + len(marker) :].strip(" |:-·,，。")
    cleaned = re.sub(
        r"^(?:用微信扫描二维码|微信扫描二维码|分享至好友和朋友圈|分享到好友和朋友圈|打开微信)[^。]{0,28}",
        "",
        cleaned,
    ).strip(" |:-·,，。")
    return cleaned


def _clean_extracted_text(text: str, limit: int = 2000) -> str:
    raw = html.unescape(str(text or ""))
    if not raw:
        return ""
    lines = re.split(r"[\r\n]+", raw)
    kept: List[str] = []
    for line in lines:
        compact = re.sub(r"\s+", " ", line).strip()
        if not compact:
            continue
        compact = _trim_navigation_prefix(compact)
        compact = _strip_share_noise(compact)
        if not compact:
            continue
        noise_hits = sum(1 for token in _NAV_MENU_TOKENS if token in compact)
        if noise_hits >= 8 and "来源：" not in compact and not re.search(r"20\d{2}年\d{1,2}月\d{1,2}日", compact):
            continue
        if noise_hits >= 5 and len(compact) < 120:
            continue
        if not _FACT_MARKER_PATTERN.search(compact) and len(compact) < 140:
            continue
        if len(compact) < 16:
            continue
        if re.fullmatch(r"[A-Za-z0-9\-\| /]+", compact) and len(compact) < 48:
            continue
        kept.append(compact)
    if not kept:
        merged = re.sub(r"\s+", " ", raw).strip()
    else:
        merged = re.sub(r"\s+", " ", " ".join(kept)).strip()
    return merged[:limit] if merged else ""


def _is_navigation_noise_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return True
    marker_hits = sum(1 for marker in _NAV_NOISE_MARKERS if marker in compact)
    source_idx = compact.find("来源：")
    if marker_hits >= 2 and (source_idx < 0 or source_idx > 220):
        return True
    return False


def _extract_html_paragraphs(html_text: str, limit: int = 2000) -> str:
    raw_html = str(html_text or "")
    if not raw_html:
        return ""
    scoped = raw_html
    m_scope = re.search(r"(?is)<article[^>]*>(.*?)</article>", raw_html)
    if not m_scope:
        m_scope = re.search(r"(?is)<main[^>]*>(.*?)</main>", raw_html)
    if isinstance(m_scope, re.Match):
        scoped = m_scope.group(1)

    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", scoped)
    if not paragraphs:
        paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", raw_html)
    if not paragraphs:
        return ""

    kept: List[str] = []
    for chunk in paragraphs[:18]:
        line = _strip_html_tags(chunk)
        line = _clean_extracted_text(line, limit=320)
        if not line:
            continue
        if len(line) < 18:
            continue
        if _is_navigation_noise_text(line):
            continue
        kept.append(line)
        if len(kept) >= 6:
            break
        if len(" ".join(kept)) >= limit:
            break
    merged = re.sub(r"\s+", " ", " ".join(kept)).strip()
    return merged[:limit] if merged else ""


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
    metrics = _compute_readerability_metrics(content)
    if not bool(metrics.get("passes")) and len(content) < 320:
        return True
    return False


def _sanitize_context_text(text: str, limit: int = 2000) -> str:
    content = _clean_extracted_text(text, limit=limit)
    if _is_navigation_noise_text(content):
        return ""
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


def _compose_fact_summary(
    text: str,
    *,
    primary_fact: str = "",
    claims: Optional[List[Dict[str, str]]] = None,
    limit: int = 180,
) -> str:
    parts: List[str] = []
    lead = _truncate_compact_text(str(primary_fact or "").strip(), limit=120)
    if lead:
        parts.append(lead)
    for claim in claims or []:
        if not isinstance(claim, dict):
            continue
        subject = str(claim.get("subject") or "").strip()
        action = str(claim.get("action") or "").strip()
        obj = str(claim.get("object") or "").strip()
        if not subject or not action:
            continue
        fragment = f"{subject}{action}{obj}".strip()
        fragment = _truncate_compact_text(fragment, limit=90)
        if not fragment:
            continue
        if any(fragment in existing or existing in fragment for existing in parts):
            continue
        parts.append(fragment)
        if len(parts) >= 3:
            break
    if len(parts) < 2:
        for sentence in _split_sentences(text):
            line = _truncate_compact_text(sentence, limit=110)
            if len(line) < 20:
                continue
            if any(line in existing or existing in line for existing in parts):
                continue
            parts.append(line)
            if len(parts) >= 3:
                break
    summary = "；".join(part for part in parts if part).strip("；")
    if not summary:
        summary = _truncate_compact_text(str(text or "").strip(), limit=limit)
    return summary[:limit]


def _normalize_compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _extract_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
        host = (parsed.netloc or "").strip().lower()
        if ":" in host:
            host = host.split(":", 1)[0].strip().lower()
        return host
    except Exception:
        return ""


def _normalise_domain(domain_or_url: str) -> str:
    value = str(domain_or_url or "").strip().lower()
    if not value:
        return ""
    if "://" in value:
        value = _extract_domain(value)
    if value.startswith("www."):
        value = value[4:]
    if ":" in value:
        value = value.split(":", 1)[0].strip().lower()
    return value


def _domain_root(domain_or_url: str) -> str:
    host = _normalise_domain(domain_or_url)
    if not host:
        return ""
    parts = [part for part in host.split(".") if part]
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


def _is_official_domain(domain_or_url: str) -> bool:
    host = _normalise_domain(domain_or_url)
    if not host:
        return False
    for suffix in _OFFICIAL_DOMAIN_SUFFIXES:
        norm_suffix = str(suffix or "").strip().lower()
        if not norm_suffix:
            continue
        suffix_clean = norm_suffix.lstrip(".")
        if host == suffix_clean or host.endswith("." + suffix_clean):
            return True
    return False


def _authority_score_for_domain(domain_or_url: str) -> float:
    host = _normalise_domain(domain_or_url)
    if not host:
        return 0.25
    if host in _AUTHORITY_DOMAIN_SCORES:
        return max(0.0, min(1.0, float(_AUTHORITY_DOMAIN_SCORES.get(host) or 0.0)))
    root = _domain_root(host)
    if root in _AUTHORITY_DOMAIN_SCORES:
        return max(0.0, min(1.0, float(_AUTHORITY_DOMAIN_SCORES.get(root) or 0.0)))
    if _is_official_domain(host):
        return 0.94
    if any(token and token in host for token in _LOW_TRUST_DOMAIN_TOKENS):
        return 0.36
    # Default neutral authority score for generic news domains.
    return 0.58


def _is_low_value_source_domain(domain_or_url: str) -> bool:
    host = _normalise_domain(domain_or_url)
    if not host:
        return True
    if host.startswith("search.") or ".search." in host:
        return True
    if any(token and token in host for token in _LOW_TRUST_DOMAIN_TOKENS):
        return True
    return False


def _extract_datetime_candidates(text: str) -> List[datetime]:
    content = str(text or "")
    if not content:
        return []
    candidates: List[datetime] = []
    for pattern in (
        r"(20\d{2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
        r"(20\d{2})(\d{2})(\d{2})",
    ):
        for match in re.finditer(pattern, content):
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                candidates.append(datetime(year, month, day, tzinfo=timezone.utc))
            except Exception:
                continue
    return candidates


def _extract_published_at(text: str, *, url: str = "") -> str:
    candidates = _extract_datetime_candidates(text)
    if url:
        candidates.extend(_extract_datetime_candidates(urllib.parse.unquote(str(url))))
    if not candidates:
        return ""
    now_utc = datetime.now(timezone.utc)
    valid: List[datetime] = []
    for candidate in candidates:
        if candidate > now_utc:
            # Ignore obvious future dates.
            continue
        if candidate.year < 2000:
            continue
        valid.append(candidate)
    if not valid:
        return ""
    valid.sort(reverse=True)
    return valid[0].date().isoformat()


def _freshness_score(published_at: str) -> float:
    text = str(published_at or "").strip()
    if not text:
        return 0.42
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return 0.35
    age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    if age_hours <= 24:
        return 0.98
    if age_hours <= 72:
        return 0.86
    if age_hours <= 168:
        return 0.68
    if age_hours <= 720:
        return 0.42
    return 0.2


def _compute_readerability_metrics(text: str) -> Dict[str, Any]:
    content = re.sub(r"\s+", " ", str(text or "")).strip()
    if not content:
        return {
            "char_count": 0,
            "sentence_count": 0,
            "avg_sentence_len": 0.0,
            "punctuation_count": 0,
            "nav_hits": 0,
            "readerable_score": 0.0,
            "passes": False,
        }
    sentences = [s for s in _split_sentences(content) if len(s) >= 10]
    sentence_count = len(sentences)
    char_count = len(content)
    punctuation_count = len(re.findall(r"[，,。.!！？；;：:]", content))
    nav_hits = sum(1 for token in _NAV_MENU_TOKENS if token and token in content)
    avg_sentence_len = (sum(len(s) for s in sentences) / sentence_count) if sentence_count else 0.0

    len_score = min(1.0, char_count / 900.0)
    sentence_score = min(1.0, sentence_count / 8.0)
    punct_score = min(1.0, punctuation_count / 16.0)
    length_balance = 1.0 if 12 <= avg_sentence_len <= 90 else 0.55
    nav_penalty = min(0.45, nav_hits * 0.045)
    readerable_score = max(
        0.0,
        len_score * 0.34 + sentence_score * 0.30 + punct_score * 0.22 + length_balance * 0.14 - nav_penalty,
    )

    min_chars = float(_QUALITY_GATE_CONFIG.get("min_chars") or 220.0)
    min_sentences = float(_QUALITY_GATE_CONFIG.get("min_sentences") or 3.0)
    min_readerable_score = float(_QUALITY_GATE_CONFIG.get("min_readerable_score") or 0.48)
    max_nav_hits = float(_QUALITY_GATE_CONFIG.get("max_nav_hits") or 12.0)
    passes = (
        char_count >= min_chars
        and sentence_count >= min_sentences
        and readerable_score >= min_readerable_score
        and nav_hits <= max_nav_hits
    )
    return {
        "char_count": char_count,
        "sentence_count": sentence_count,
        "avg_sentence_len": round(avg_sentence_len, 2),
        "punctuation_count": punctuation_count,
        "nav_hits": nav_hits,
        "readerable_score": round(readerable_score, 3),
        "passes": bool(passes),
    }


def _extract_claim_units(text: str, *, limit: int = 3) -> List[Dict[str, str]]:
    verbs = (
        "发布",
        "宣布",
        "表示",
        "指出",
        "回应",
        "通报",
        "报告",
        "称",
        "启动",
        "签署",
        "警告",
        "证实",
        "调查",
        "上调",
        "下调",
        "量产",
        "上线",
        "开通",
    )
    claims: List[Dict[str, str]] = []
    for sentence in _split_sentences(text):
        line = re.sub(r"\s+", " ", str(sentence or "")).strip()
        if len(line) < 18:
            continue
        action = ""
        action_pos = -1
        for verb in verbs:
            pos = line.find(verb)
            if pos > 0:
                action = verb
                action_pos = pos
                break
        if not action:
            continue
        subject = line[:action_pos].strip(" ，,：:;；。")
        object_text = line[action_pos + len(action) :].strip(" ，,：:;；。")
        if not subject:
            subject = line[:14]
        if not object_text:
            object_text = line[action_pos : action_pos + 48]
        time_match = re.search(r"(20\d{2}[年/\-.]\d{1,2}[月/\-.]\d{1,2}日?)", line)
        location_match = re.search(r"(?:在|于)([\u4e00-\u9fff]{2,12}(?:省|市|县|州|海峡|地区|国|湾|岛)?)", line)
        claim = {
            "subject": subject[:28],
            "action": action[:10],
            "object": object_text[:68],
            "time": (time_match.group(1) if time_match else "")[:20],
            "location": (location_match.group(1) if location_match else "")[:20],
            "raw_sentence": line[:140],
        }
        signature = f"{claim['subject']}|{claim['action']}|{claim['object']}"
        if any(f"{c.get('subject')}|{c.get('action')}|{c.get('object')}" == signature for c in claims):
            continue
        claims.append(claim)
        if len(claims) >= limit:
            break
    return claims


def _refine_evidence_with_subagent(
    title: str,
    text: str,
    *,
    source_domain: str = "",
    published_at: str = "",
) -> Dict[str, Any]:
    raw_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw_text:
        return {"fact": "", "claims": [], "quality": "empty"}

    fallback_fact = _best_fact_sentence(raw_text) or _truncate_compact_text(raw_text, limit=120)
    fallback_claims = _extract_claim_units(raw_text, limit=3)

    prompt = (
        "你是网页证据精炼子代理。请仅依据给定网页正文抽取事实，不要外推。\n"
        "输出严格 JSON：\n"
        "{\n"
        '  "fact":"120-180字事实摘要，必须含主体+动作，尽量含时间/地点，不写推测",\n'
        '  "claims":[\n'
        "    {\n"
        '      "subject":"",\n'
        '      "action":"",\n'
        '      "object":"",\n'
        '      "time":"",\n'
        '      "location":"",\n'
        '      "raw_sentence":""\n'
        "    }\n"
        "  ],\n"
        '  "quality":"high|medium|low"\n'
        "}\n"
        "规则：\n"
        "1) 只输出 JSON；2) 无法确认则 quality=low 且 claims 为空；\n"
        "3) 禁止出现“可能/或许/据推测”等推断词；\n"
        "4) 不得补充输入中不存在的数字、日期、主体。\n\n"
        f"标题: {title}\n"
        f"来源域名: {source_domain or '-'}\n"
        f"发布日期: {published_at or '-'}\n"
        f"网页正文:\n{raw_text[:1400]}"
    )
    try:
        response_text = _safe_run_async(
            call_langchain_chat(
                [
                    {"role": "system", "content": "你是严谨的中文事实抽取助手。"},
                    {"role": "user", "content": prompt},
                ],
                task="report",
                temperature=0.0,
                max_tokens=260,
            )
        )
        payload = _extract_json_payload(str(response_text or "")) or {}
        fact = _truncate_compact_text(str(payload.get("fact") or "").strip(), limit=180)
        raw_claims = payload.get("claims")
        claims: List[Dict[str, str]] = []
        if isinstance(raw_claims, list):
            for item in raw_claims:
                if not isinstance(item, dict):
                    continue
                claim = {
                    "subject": str(item.get("subject") or "").strip()[:28],
                    "action": str(item.get("action") or "").strip()[:12],
                    "object": str(item.get("object") or "").strip()[:68],
                    "time": str(item.get("time") or "").strip()[:20],
                    "location": str(item.get("location") or "").strip()[:20],
                    "raw_sentence": str(item.get("raw_sentence") or "").strip()[:140],
                }
                if not claim["subject"] or not claim["action"]:
                    continue
                claims.append(claim)
                if len(claims) >= 3:
                    break
        quality = str(payload.get("quality") or "").strip().lower()
        if quality not in {"high", "medium", "low"}:
            quality = "medium"
        if not fact:
            fact = fallback_fact
        if not claims:
            claims = fallback_claims
        return {"fact": fact, "claims": claims[:3], "quality": quality}
    except Exception:
        return {"fact": fallback_fact, "claims": fallback_claims[:3], "quality": "fallback"}


_KEYWORD_STOPWORDS: Tuple[str, ...] = (
    "首页",
    "早报",
    "热点",
    "热搜",
    "话题",
    "视频",
    "直播",
    "详情",
    "全文",
    "快讯",
    "今日",
    "hot",
)
_KEYWORD_POOL_AI_ONLY = True
_EXPOSE_EVIDENCE_STATUS_TO_CLIENT = False


def _is_valid_keyword_text(text: str, *, min_len: int = 2, max_len: int = 18) -> bool:
    token = re.sub(r"\s+", "", str(text or "").strip())
    if not token:
        return False
    if len(token) < min_len or len(token) > max_len:
        return False
    if re.fullmatch(r"\d+(?:[./-]\d+)?", token):
        return False
    if token.lower() in _KEYWORD_STOPWORDS:
        return False
    return True


def _is_cjk_only(text: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", str(text or "")))


def _drop_fragment_keywords(tokens: List[str], *, limit: Optional[int] = None) -> List[str]:
    unique: List[str] = []
    for raw in tokens:
        text = str(raw or "").strip()
        if not text or text in unique:
            continue
        unique.append(text)
    long_cjk_terms = [item for item in unique if _is_cjk_only(item) and len(item) >= 8]
    filtered: List[str] = []
    for text in unique:
        if _is_cjk_only(text) and 3 <= len(text) <= 5 and any(text in long_term for long_term in long_cjk_terms):
            continue
        filtered.append(text)
        if limit is not None and len(filtered) >= limit:
            break
    return filtered


def _extract_semantic_terms(
    text: str,
    *,
    max_terms: int = 14,
    emit_cjk_ngrams: bool = True,
) -> List[str]:
    raw = _normalize_compact(text)
    if not raw:
        return []
    pieces = re.findall(r"[a-z0-9\-\+]+|[\u4e00-\u9fff]+", raw)
    terms: List[str] = []
    seen: set[str] = set()
    for piece in pieces:
        if not piece:
            continue
        if re.fullmatch(r"[a-z0-9\-\+]+", piece):
            if len(piece) >= 2 and piece not in seen:
                seen.add(piece)
                terms.append(piece[:18])
            if len(terms) >= max_terms:
                break
            continue
        if len(piece) <= 8:
            if piece not in seen:
                seen.add(piece)
                terms.append(piece)
            if emit_cjk_ngrams and len(piece) >= 5:
                for n in (4, 3):
                    if len(piece) < n:
                        continue
                    for i in range(0, len(piece) - n + 1):
                        sample = piece[i : i + n]
                        if sample in seen:
                            continue
                        seen.add(sample)
                        terms.append(sample)
                        if len(terms) >= max_terms:
                            break
                    if len(terms) >= max_terms:
                        break
        else:
            if not emit_cjk_ngrams:
                if len(piece) <= 16 and piece not in seen:
                    seen.add(piece)
                    terms.append(piece)
            else:
                # Keep a few informative slices from long Chinese spans.
                samples = [piece[:6], piece[-6:], piece[:4], piece[-4:]]
                for sample in samples:
                    if len(sample) < 3:
                        continue
                    if sample in seen:
                        continue
                    seen.add(sample)
                    terms.append(sample)
                    if len(terms) >= max_terms:
                        break
        if len(terms) >= max_terms:
            break
    return terms[:max_terms]


def _title_match_score(left: str, right: str) -> float:
    a = _normalize_compact(left)
    b = _normalize_compact(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq_ratio = SequenceMatcher(None, a, b).ratio()
    left_terms = _extract_semantic_terms(a, max_terms=12)
    if not left_terms:
        return seq_ratio
    overlap_hits = sum(1 for term in left_terms if term and term in b)
    overlap_ratio = overlap_hits / max(1, len(left_terms))
    contains_bonus = 0.12 if min(len(a), len(b)) >= 10 and (a in b or b in a) else 0.0
    return min(1.0, seq_ratio * 0.55 + overlap_ratio * 0.45 + contains_bonus)


def _context_relevance_score(title: str, text: str) -> float:
    norm_title = _normalize_compact(title)
    norm_text = _normalize_compact(text)
    if not norm_title or not norm_text:
        return 0.0
    if len(norm_title) < 8:
        if norm_title in norm_text:
            return 1.0
        short_terms = _extract_semantic_terms(norm_title, max_terms=10)
        if not short_terms:
            return 0.0
        hits = [term for term in short_terms if term and term in norm_text]
        overlap = len(hits) / max(1, len(short_terms))
        return min(1.0, overlap + (0.1 if any(len(term) >= 4 for term in hits) else 0.0))
    title_terms = _extract_semantic_terms(norm_title, max_terms=12)
    if not title_terms:
        return 1.0 if norm_title in norm_text else 0.0
    matched_terms = [term for term in title_terms if term and term in norm_text]
    overlap_ratio = len(matched_terms) / max(1, len(title_terms))
    strong_anchor = any(len(term) >= 4 for term in matched_terms)
    seq_bonus = SequenceMatcher(None, norm_title[:32], norm_text[:300]).ratio() * 0.2
    score = overlap_ratio * 0.8 + (0.15 if strong_anchor else 0.0) + seq_bonus
    if norm_title in norm_text:
        score = max(score, 0.95)
    return min(1.0, score)


def _normalise_verification_status(raw_status: Any) -> str:
    status = str(raw_status or "").strip().lower()
    if status in {
        "retrieved",
        "relevant",
        "single_source",
        "corroborated",
        "weak_match",
        "unresolved",
        "contradicted",
    }:
        return status
    if status in {"matched", "confirmed"}:
        return "single_source"
    if status == "missing":
        return "unresolved"
    return "unresolved"


def _is_context_relevant_to_title(title: str, text: str) -> bool:
    return _context_relevance_score(title, text) >= 0.52


def _headline_fallback_summary(headline: str) -> str:
    clean = re.sub(r"\s+", " ", str(headline or "")).strip("。;；,， ")
    if not clean:
        return ""
    if len(clean) > 70:
        clean = clean[:70] + "..."
    return clean


def _sanitize_source_title(value: str, *, fallback: str = "") -> str:
    text = _resolve_alias_in_text(str(value or "").strip())
    if not text:
        text = _resolve_alias_in_text(str(fallback or "").strip())
    text = re.sub(r"^\[[^\]]{1,24}\]\s*#\d+\s*", "", text).strip()
    text = re.sub(r"（热度[^）]*）", "", text).strip()
    text = re.sub(r"\(热度[^)]*\)", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80]


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


def _search_bing_news_rss_candidates(title: str, timeout: int = 8) -> Tuple[List[str], List[str]]:
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
        warn_key = f"search:bing:{query}"
        if warn_key not in _WARNED_FETCH_KEYS:
            _WARNED_FETCH_KEYS.add(warn_key)
            LOGGER.warning("Bing RSS search failed for title=%s: %s", query[:32], exc)
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


def _decode_duckduckgo_redirect(url: str) -> str:
    target = str(url or "").strip()
    if not target:
        return ""
    if target.startswith("//"):
        target = "https:" + target
    if target.startswith("/"):
        target = "https://duckduckgo.com" + target
    try:
        parsed = urllib.parse.urlparse(target)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            params = urllib.parse.parse_qs(parsed.query)
            uddg = params.get("uddg")
            if isinstance(uddg, list) and uddg:
                return urllib.parse.unquote(str(uddg[0]))
    except Exception:
        return target
    return target


def _search_duckduckgo_candidates(title: str, timeout: int = 8) -> Tuple[List[str], List[str]]:
    query = str(title or "").strip()
    if not query:
        return [], []
    url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(query + " 新闻")
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
            page = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        warn_key = f"search:ddg:{query}"
        if warn_key not in _WARNED_FETCH_KEYS:
            _WARNED_FETCH_KEYS.add(warn_key)
            LOGGER.warning("DuckDuckGo search failed for title=%s: %s", query[:32], exc)
        return [], []

    snippets: List[str] = []
    links: List[str] = []
    pattern = r'(?is)<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
    for match in re.finditer(pattern, page):
        raw_href = html.unescape(match.group(1) if match else "").strip()
        href = _decode_duckduckgo_redirect(raw_href)
        if href.startswith("http") and href not in links:
            links.append(href)
        title_text = _strip_html_tags(match.group(2) if match else "")
        tail = page[match.end() : min(len(page), match.end() + 1400)]
        m_snippet = re.search(r'(?is)class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</', tail)
        desc_text = _strip_html_tags(m_snippet.group(1) if m_snippet else "")
        snippet = f"{title_text}。{desc_text}".strip("。")
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet[:220])
        if len(links) >= 6 and len(snippets) >= 4:
            break
    return snippets[:4], links[:6]


def _search_news_rss_candidates(title: str, timeout: int = 8) -> Tuple[List[str], List[str]]:
    query = str(title or "").strip()
    if not query:
        return [], []
    ddg_snippets, ddg_links = _search_duckduckgo_candidates(query, timeout=timeout)
    bing_snippets, bing_links = _search_bing_news_rss_candidates(query, timeout=timeout)

    snippets: List[str] = []
    for candidate in ddg_snippets + bing_snippets:
        text = _truncate_compact_text(candidate, limit=220)
        if text and text not in snippets:
            snippets.append(text)
        if len(snippets) >= 5:
            break

    links: List[str] = []
    for candidate in ddg_links + bing_links:
        url = str(candidate or "").strip()
        if url.startswith("http") and url not in links:
            links.append(url)
        if len(links) >= 8:
            break
    return snippets[:5], links[:8]


def _score_candidate_link(title: str, url: str, *, snippet: str = "") -> float:
    target_title = _resolve_alias_in_text(str(title or "").strip())
    target_url = str(url or "").strip()
    if not target_title or not target_url:
        return 0.0
    domain = _extract_domain(target_url)
    authority = _authority_score_for_domain(domain)
    decoded_url = urllib.parse.unquote(target_url)
    alignment = max(
        _title_match_score(target_title, decoded_url),
        _context_relevance_score(target_title, snippet),
    )
    published_at = _extract_published_at(decoded_url + " " + str(snippet or ""), url=target_url)
    freshness = _freshness_score(published_at)
    official_bonus = 0.08 if _is_official_domain(domain) else 0.0
    score = alignment * 0.46 + authority * 0.24 + freshness * 0.22 + official_bonus
    return round(max(0.0, min(1.0, score)), 3)


def _is_probably_article_url(url: str) -> bool:
    target = str(url or "").strip()
    if not target.startswith("http"):
        return False
    try:
        parsed = urllib.parse.urlparse(target)
    except Exception:
        return False
    host = _normalise_domain(parsed.netloc)
    path = str(parsed.path or "").strip().lower()
    query = str(parsed.query or "").strip().lower()
    lowered = (host + path + "?" + query).lower()
    deny_tokens = (
        "/search",
        "search.",
        "keyword=",
        "wd=",
        "/tag/",
        "/tags/",
        "/video/",
        "/playlist",
        "/topic/",
        "share_source=",
    )
    if any(token in lowered for token in deny_tokens):
        return False
    if path in {"", "/"}:
        return False
    if path.endswith(".html") or path.endswith(".shtml"):
        return True
    if re.search(r"/20\d{2}[/-]\d{1,2}[/-]\d{1,2}", path):
        return True
    allow_tokens = ("/news/", "/article/", "/a/", "/detail/", "/content/")
    if any(token in path for token in allow_tokens):
        return True
    # Fallback: sufficiently deep path often indicates concrete content page.
    segments = [seg for seg in path.split("/") if seg]
    return len(segments) >= 3


def _discover_candidate_links(item: Dict[str, Any], timeout: int = 8) -> Tuple[str, List[str], str]:
    title = _resolve_alias_in_text(str(item.get("title") or "").strip())
    if not title:
        return "", [], ""
    base_url = str(item.get("url") or item.get("mobileUrl") or "").strip()
    snippets, searched_links = _search_news_rss_candidates(title, timeout=timeout)
    links: List[str] = []
    if _is_probably_article_url(base_url):
        links.append(base_url)
    for link in searched_links:
        if _is_probably_article_url(link) and link not in links:
            links.append(link)
    if not links and base_url.startswith("http"):
        # Keep source URL as last-resort candidate even if it looks non-article.
        links.append(base_url)
    merged_snippet = _truncate_compact_text("；".join(snippets), limit=260) if snippets else ""
    scored_links: List[Tuple[float, int, str]] = []
    for idx, link in enumerate(links):
        scored_links.append((_score_candidate_link(title, link, snippet=merged_snippet), idx, link))
    scored_links.sort(key=lambda item: (item[0], -item[1]), reverse=True)

    ranked: List[str] = []
    domain_counts: Dict[str, int] = {}
    for _, _, link in scored_links:
        root = _domain_root(link)
        if root and domain_counts.get(root, 0) >= 2:
            continue
        ranked.append(link)
        if root:
            domain_counts[root] = domain_counts.get(root, 0) + 1
        if len(ranked) >= 8:
            break
    if not ranked:
        ranked = links[:8]
    return title, ranked[:8], merged_snippet


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
        score = _title_match_score(target, norm_title)
        if score > best_score:
            best_score = score
            best_title = str(title or "").strip()
            best_text = str(text or "").strip()
    # Avoid matching by a shared short token (e.g., only "龙虾").
    if best_score >= 0.58:
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
    pending_cards: List[Dict[str, Any]] = []
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
            meta = evidence_meta.get(matched_title) if isinstance(evidence_meta, dict) else None
            status = _normalise_verification_status((meta or {}).get("verification_status"))
            if matched_title:
                updated["source_title"] = _sanitize_source_title(matched_title, fallback=headline)
            else:
                updated["source_title"] = _sanitize_source_title(source_title, fallback=headline)
            confidence = (meta or {}).get("confidence")
            try:
                confidence = round(max(0.0, min(1.0, float(confidence))), 2)
            except Exception:
                confidence = 0.0
            if bg:
                fact_sentence = _best_fact_sentence(bg)
                claims = list((meta or {}).get("claims") or [])
                composed_summary = _compose_fact_summary(
                    bg,
                    primary_fact=fact_sentence,
                    claims=claims if isinstance(claims, list) else [],
                    limit=180,
                )
                current_summary = str(updated.get("summary") or "").strip()
                # Keep richer summary when available; only fallback when summary is too short/generic.
                if composed_summary and (_looks_generic_summary(current_summary) or len(current_summary) < 56):
                    updated["summary"] = composed_summary
                updated["evidence"] = {
                    "status": status if status != "unresolved" else "single_source",
                    "matched_title": matched_title[:72],
                    "excerpt": fact_sentence[:160] if fact_sentence else "",
                    "source_url": str((meta or {}).get("source_url") or ""),
                    "source_domain": str((meta or {}).get("source_domain") or ""),
                    "source_domains": list((meta or {}).get("source_domains") or []),
                    "method": str((meta or {}).get("method") or ""),
                    "confidence": confidence,
                    "agreement_count": int((meta or {}).get("agreement_count") or 1),
                    "published_at": str((meta or {}).get("published_at") or ""),
                    "official_source_present": bool((meta or {}).get("official_source_present")),
                    "is_official": bool((meta or {}).get("is_official")),
                    "signals": {
                        "authority_score": round(_safe_float((meta or {}).get("authority_score"), 0.0), 2),
                        "freshness_score": round(_safe_float((meta or {}).get("freshness_score"), 0.0), 2),
                        "entity_alignment_score": round(_safe_float((meta or {}).get("entity_alignment_score"), 0.0), 2),
                        "overall_score": round(_safe_float((meta or {}).get("overall_score"), 0.0), 2),
                    },
                    "quality_metrics": dict((meta or {}).get("quality_metrics") or {}),
                    "claims": claims[:3],
                    "verification": dict((meta or {}).get("verification") or {}),
                }
            else:
                fallback = _headline_fallback_summary(headline)
                if status in _UNCERTAIN_EVIDENCE_STATUSES:
                    # Product rule: uncertain cards should stay lightweight without pseudo-facts.
                    if _looks_generic_summary(summary) and fallback:
                        updated["summary"] = fallback
                elif _looks_generic_summary(summary) and fallback:
                    updated["summary"] = fallback
                updated["evidence"] = {
                    "status": status if status != "unresolved" else "unresolved",
                    "matched_title": "",
                    "excerpt": "",
                    "source_url": "",
                    "source_domain": "",
                    "source_domains": [],
                    "method": "",
                    "confidence": confidence,
                    "agreement_count": int((meta or {}).get("agreement_count") or 0),
                    "published_at": "",
                    "official_source_present": False,
                    "is_official": False,
                    "signals": {
                        "authority_score": 0.0,
                        "freshness_score": 0.0,
                        "entity_alignment_score": 0.0,
                        "overall_score": 0.0,
                    },
                    "quality_metrics": {},
                    "claims": [],
                    "verification": dict((meta or {}).get("verification") or {}),
                }
            card_status = _normalise_verification_status((updated.get("evidence") or {}).get("status"))
            if not _EXPOSE_EVIDENCE_STATUS_TO_CLIENT:
                updated.pop("evidence", None)
            if card_status in _ADMISSIBLE_EVIDENCE_STATUSES:
                next_cards.append(updated)
            else:
                pending_cards.append(updated)
        if next_cards:
            grounded.append({**section, "cards": next_cards[:3]})
    if pending_cards:
        grounded.append(
            {
                "title": "热点速览",
                "badge": "关注" if not _EXPOSE_EVIDENCE_STATUS_TO_CLIENT else "线索",
                "cards": pending_cards[:6],
            }
        )
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
        p_text = _extract_html_paragraphs(html, limit=2000)
        if p_text and not _is_block_or_low_quality_text(p_text):
            _URL_TEXT_CACHE[url] = {"text": p_text, "expires_at": now + TEXT_CACHE_TTL_SECONDS}
            return p_text
        html = re.sub(r"(?is)<br\s*/?>", "\n", html)
        html = re.sub(r"(?is)</(p|div|li|h1|h2|h3|h4|h5|article|section|tr)>", "\n", html)
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
    other_review = cloned.get("other_hotspot_review")
    has_clusters = isinstance(other_review, dict) and isinstance(other_review.get("clusters"), list)
    if not has_clusters:
        diagnostics = cloned.get("diagnostics") if isinstance(cloned.get("diagnostics"), dict) else {}
        evidence_meta = {}
        if isinstance(diagnostics, dict):
            evidence_meta = diagnostics.get("evidence_meta") if isinstance(diagnostics.get("evidence_meta"), dict) else {}
        if not evidence_meta and isinstance(cloned.get("_evidence_meta"), dict):
            evidence_meta = cloned.get("_evidence_meta") or {}
        source_items = merged_items if isinstance(merged_items, list) and merged_items else cloned.get("items")
        if isinstance(source_items, list):
            cloned["other_hotspot_review"] = _build_other_hotspot_review(
                source_items,
                evidence_meta=evidence_meta if isinstance(evidence_meta, dict) else {},
                link_candidates=cloned.get("_link_candidates") if isinstance(cloned.get("_link_candidates"), dict) else {},
                max_clusters=4,
                max_items_per_cluster=6,
            )
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
    evidence_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    max_items: int = 25,
) -> str:
    lines: List[str] = []
    backgrounds = backgrounds or {}
    evidence_meta = evidence_meta or {}
    for idx, item in enumerate(news_items[:max_items], start=1):
        source = str(item.get("source") or "未知来源")
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        hot = _coerce_hot_value(item.get("hot_value"))
        rank = int(item.get("rank") or idx)
        hot_text = f"热度{hot}" if hot > 0 else "热度未知"
        
        bg = backgrounds.get(title)
        meta = evidence_meta.get(title) if isinstance(evidence_meta, dict) else {}
        status = _normalise_verification_status((meta or {}).get("verification_status"))
        source_domain = str((meta or {}).get("source_domain") or "").strip()
        confidence = (meta or {}).get("confidence")
        try:
            confidence_text = f"{float(confidence):.2f}"
        except Exception:
            confidence_text = "0.00"
        if bg:
            lines.append(
                f"{idx}. [{source}] #{rank} {title}（{hot_text}）\n"
                f"   [证据状态: {status}, confidence={confidence_text}, domain={source_domain or '-'}]\n"
                f"   [背景补充: {bg}]"
            )
        else:
            lines.append(
                f"{idx}. [{source}] #{rank} {title}（{hot_text}）\n"
                f"   [证据状态: {status}, confidence={confidence_text}, domain={source_domain or '-'}]"
            )

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
        candidate = str(chunk or "").strip()
        if len(candidate) > 16:
            prefix = re.split(
                r"(引发|导致|回应|表示|宣布|发布|升级|约谈|收盘|上涨|下跌|波动|冲突|战争)",
                candidate,
                maxsplit=1,
            )[0].strip()
            candidate = prefix if 2 <= len(prefix) <= 16 else ""
        if not _is_valid_keyword_text(candidate, min_len=2, max_len=16):
            continue
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) >= 4:
            break
    if selected:
        return selected[:4]
    for token in _extract_semantic_terms(title, max_terms=4, emit_cjk_ngrams=False):
        if _is_valid_keyword_text(token, min_len=2, max_len=16) and token not in selected:
            selected.append(token)
        if len(selected) >= 2:
            break
    return selected[:4]


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


def _derive_keywords_from_backgrounds(backgrounds: Dict[str, str], limit: int = 14) -> List[str]:
    if not isinstance(backgrounds, dict):
        return []
    keywords: List[str] = []
    for title, bg in backgrounds.items():
        for candidate in _extract_tags_from_title(str(title or "")):
            token = str(candidate or "").strip()
            if _is_valid_keyword_text(token, min_len=2, max_len=16) and token not in keywords:
                keywords.append(token)
            if len(keywords) >= limit * 2:
                return _drop_fragment_keywords(keywords, limit=limit)
        for candidate in _extract_semantic_terms(str(bg or ""), max_terms=10, emit_cjk_ngrams=False):
            token = str(candidate or "").strip()
            if _is_valid_keyword_text(token, min_len=2, max_len=16) and token not in keywords:
                keywords.append(token)
            if len(keywords) >= limit * 2:
                return _drop_fragment_keywords(keywords, limit=limit)
    return _drop_fragment_keywords(keywords, limit=limit)


class _KeywordState(TypedDict):
    lines: List[str]
    extracted: List[str]
    keywords: List[str]


def _run_keyword_langgraph(
    news_items: List[Dict[str, Any]],
    limit: int = 14,
    *,
    backgrounds: Optional[Dict[str, str]] = None,
    evidence_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[str]:
    backgrounds = backgrounds or {}
    evidence_meta = evidence_meta or {}
    lines: List[str] = []
    verified_backgrounds: Dict[str, str] = {}
    for item in news_items[:25]:
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        if not title:
            continue
        meta = evidence_meta.get(title) if isinstance(evidence_meta, dict) else {}
        status = _normalise_verification_status((meta or {}).get("verification_status"))
        bg = str(backgrounds.get(title) or "").strip()
        if status in _ADMISSIBLE_EVIDENCE_STATUSES and bg:
            lines.append(f"标题: {title}\n证据({status}): {bg[:180]}")
            verified_backgrounds[title] = bg
    if not lines:
        return []

    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return []

    def _extract_keywords_node(state: _KeywordState) -> _KeywordState:
        prompt = (
            "你是舆情关键词提取助手。请基于标题与证据摘要提取 10-14 个关键词，"
            "优先使用有证据支撑的实体、议题与动作词。仅返回 JSON："
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
                        if _is_valid_keyword_text(text, min_len=2, max_len=16) and text not in extracted:
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
            if _is_valid_keyword_text(text, min_len=2, max_len=16) and text not in merged:
                merged.append(text)
        return {
            "lines": state.get("lines", []),
            "extracted": extracted,
            "keywords": _drop_fragment_keywords(merged, limit=limit),
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
                if _is_valid_keyword_text(text, min_len=2, max_len=16) and text not in cleaned:
                    cleaned.append(text)
            return _drop_fragment_keywords(cleaned, limit=limit)
    except Exception as exc:
        LOGGER.warning("Keyword LangGraph agent failed: %s", exc)
    return []


def _build_dynamic_keyword_pool(
    news_items: List[Dict[str, Any]],
    limit: int = 14,
    *,
    backgrounds: Optional[Dict[str, str]] = None,
    evidence_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[str]:
    keywords = _run_keyword_langgraph(
        news_items,
        limit=limit,
        backgrounds=backgrounds,
        evidence_meta=evidence_meta,
    )
    return keywords[:limit] if keywords else []


def _build_research_prompt(
    news_items: List[Dict[str, Any]],
    *,
    backgrounds: Optional[Dict[str, str]] = None,
    evidence_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    backgrounds = backgrounds or {}
    evidence_meta = evidence_meta or {}
    lines = []
    for idx, item in enumerate(news_items[:18], start=1):
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        meta = evidence_meta.get(title) if isinstance(evidence_meta, dict) else {}
        status = _normalise_verification_status((meta or {}).get("verification_status"))
        confidence = (meta or {}).get("confidence")
        try:
            confidence_text = f"{float(confidence):.2f}"
        except Exception:
            confidence_text = "0.00"
        source_domain = str((meta or {}).get("source_domain") or "").strip() or "-"
        authority_score = round(_safe_float((meta or {}).get("authority_score"), 0.0), 2)
        freshness_score = round(_safe_float((meta or {}).get("freshness_score"), 0.0), 2)
        alignment_score = round(_safe_float((meta or {}).get("entity_alignment_score"), 0.0), 2)
        overall_score = round(_safe_float((meta or {}).get("overall_score"), 0.0), 2)
        claims = list((meta or {}).get("claims") or [])
        claim_count = len(claims)
        published_at = str((meta or {}).get("published_at") or "").strip() or "-"
        evidence = str(backgrounds.get(title) or "").strip()
        evidence_line = evidence[:180] if evidence else "无可用正文证据"
        lines.append(
            f"{idx}. [{item.get('source','未知来源')}] "
            f"{title} "
            f"(rank={item.get('rank','-')},heat={item.get('heat_score','-')},"
            f"status={status},confidence={confidence_text},domain={source_domain},"
            f"authority={authority_score},freshness={freshness_score},"
            f"alignment={alignment_score},overall={overall_score},claims={claim_count},published_at={published_at})\n"
            f"   evidence: {evidence_line}"
        )
    return (
        "你是调研分析 agent。请基于热榜标题+证据摘要进行结构化调研，输出 JSON：\n"
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
        "4) 若证据不足，要在 open_questions 中明确写出缺口；\n"
        "5) 不得把 unresolved/weak_match 状态写成确定性事实；\n"
        "6) 优先使用 corroborated/single_source 且 overall 分更高的条目形成主线结论。\n\n"
        "标题数据：\n"
        + "\n".join(lines)
    )


def _resolve_alias_in_text(text: str) -> str:
    # Keep original text; semantic disambiguation should be handled by LLM with evidence.
    return str(text or "")


def _run_research_langgraph(
    news_items: List[Dict[str, Any]],
    *,
    backgrounds: Optional[Dict[str, str]] = None,
    evidence_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    backgrounds = backgrounds or {}
    evidence_meta = evidence_meta or {}
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
        prompt = _build_research_prompt(
            news_items,
            backgrounds=backgrounds,
            evidence_meta=evidence_meta,
        )
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
        method_note = str(raw.get("method_note") or "").strip() or "基于热榜标题与网页证据摘要聚类生成。"
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


def _build_other_hotspot_review(
    news_items: List[Dict[str, Any]],
    *,
    evidence_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    link_candidates: Optional[Dict[str, List[str]]] = None,
    max_clusters: int = 4,
    max_items_per_cluster: int = 5,
) -> Dict[str, Any]:
    evidence_meta = evidence_meta or {}
    link_candidates = link_candidates or {}
    clusters_map: Dict[str, Dict[str, Any]] = {}

    def _collect_urls(item: Dict[str, Any], title: str) -> List[Dict[str, str]]:
        urls: List[str] = []
        base_url = str(item.get("url") or item.get("mobileUrl") or "").strip()
        if base_url.startswith("http") and base_url not in urls:
            urls.append(base_url)
        for candidate in list(link_candidates.get(title) or []):
            text = str(candidate or "").strip()
            if text.startswith("http") and text not in urls:
                urls.append(text)
            if len(urls) >= 6:
                break
        records: List[Dict[str, str]] = []
        for url in urls:
            records.append(
                {
                    "url": url,
                    "domain": _normalise_domain(_extract_domain(url)),
                }
            )
            if len(records) >= 4:
                break
        return records

    for item in news_items[:30]:
        title = _resolve_alias_in_text(str(item.get("title") or "").strip())
        if not title:
            continue
        status = _normalise_verification_status(
            ((evidence_meta.get(title) or {}) if isinstance(evidence_meta, dict) else {}).get("verification_status")
        )
        if status in _ADMISSIBLE_EVIDENCE_STATUSES:
            continue
        cluster_title, _ = _infer_section(title)
        cluster = clusters_map.setdefault(
            cluster_title,
            {
                "title": cluster_title,
                "badge": "热点速览（分类）",
                "items": [],
            },
        )
        rows = cluster.get("items")
        if not isinstance(rows, list):
            continue
        urls = _collect_urls(item, title)
        heat = int(item.get("heat_score") or 0)
        rows.append(
            {
                "title": title[:80],
                "source": str(item.get("source") or "未知来源")[:30],
                "rank": int(item.get("rank") or 0),
                "heat": max(1, min(100, heat)) if heat else 60,
                "urls": urls,
            }
        )
        if _EXPOSE_EVIDENCE_STATUS_TO_CLIENT:
            rows[-1]["status"] = status

    clusters: List[Dict[str, Any]] = []
    for cluster in clusters_map.values():
        rows = cluster.get("items") if isinstance(cluster, dict) else None
        if not isinstance(rows, list) or not rows:
            continue
        rows.sort(key=lambda row: int(row.get("heat") or 0), reverse=True)
        clusters.append({**cluster, "items": rows[:max_items_per_cluster]})
    clusters.sort(
        key=lambda row: sum(int(item.get("heat") or 0) for item in (row.get("items") or [])),
        reverse=True,
    )
    clusters = clusters[:max_clusters]
    total_items = sum(len(cluster.get("items") or []) for cluster in clusters)
    return {
        "cluster_count": len(clusters),
        "item_count": total_items,
        "clusters": clusters,
    }


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
        "keyword_pool": [] if _KEYWORD_POOL_AI_ONLY else keyword_pool[:14],
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
        if not _EXPOSE_EVIDENCE_STATUS_TO_CLIENT:
            title = re.sub(r"(已验证|未验证|待核实|未核实|核验)", "", title).strip(" ·|-")
        if not title:
            continue
        badge = str(raw.get("badge") or "关注").strip()[:10]
        if not _EXPOSE_EVIDENCE_STATUS_TO_CLIENT and badge in {"线索", "已验证", "未验证", "待核实"}:
            badge = "关注"
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
                source_title = _sanitize_source_title(source_title, fallback=headline)
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

    fallback_keywords = [] if _KEYWORD_POOL_AI_ONLY else list(fallback.get("keyword_pool") or [])
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
        if not _is_valid_keyword_text(text, min_len=2, max_len=18):
            continue
        if any(existing.get("text") == text for existing in keywords):
            continue
        keywords.append({"text": text[:18], "cluster": cluster})
    if keywords:
        allowed_texts = set(_drop_fragment_keywords([str(entry.get("text") or "") for entry in keywords], limit=14))
        filtered = [entry for entry in keywords if str(entry.get("text") or "") in allowed_texts]
        if filtered:
            return filtered[:14]
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

    def _build_verified_snapshot(
        items: List[Dict[str, Any]],
        backgrounds: Dict[str, str],
        evidence_meta: Dict[str, Dict[str, Any]],
        *,
        max_entries: int = 4,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for item in items[:25]:
            title = _resolve_alias_in_text(str(item.get("title") or "").strip())
            if not title:
                continue
            meta = evidence_meta.get(title) if isinstance(evidence_meta, dict) else {}
            status = _normalise_verification_status((meta or {}).get("verification_status"))
            if status not in _ADMISSIBLE_EVIDENCE_STATUSES:
                continue
            bg = str(backgrounds.get(title) or "").strip()
            if not bg:
                continue
            fact = _best_fact_sentence(bg) or _truncate_compact_text(bg, limit=120)
            if not fact:
                continue
            candidates.append(
                {
                    "title": title[:80],
                    "fact": fact[:120],
                    "status": status,
                    "domain": _normalise_domain(str((meta or {}).get("source_domain") or "")),
                    "published_at": str((meta or {}).get("published_at") or "").strip(),
                    "confidence": round(_safe_float((meta or {}).get("confidence"), 0.0), 2),
                    "overall_score": round(_safe_float((meta or {}).get("overall_score"), 0.0), 2),
                }
            )
        candidates.sort(
            key=lambda row: (
                float(row.get("overall_score") or 0.0),
                float(row.get("confidence") or 0.0),
            ),
            reverse=True,
        )
        dedup: List[Dict[str, Any]] = []
        seen_titles: set[str] = set()
        for row in candidates:
            title = str(row.get("title") or "")
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            dedup.append(row)
            if len(dedup) >= max_entries:
                break
        return dedup

    def _planner_node(state: _OverviewState) -> _OverviewState:
        run_mode = "research" if str(state.get("mode") or "").lower() == "research" else "fast"
        max_prompt_items = 18 if run_mode == "fast" else 25
        plan = {
            "mode": run_mode,
            "max_prompt_items": max_prompt_items,
            # Ensure all candidate inputs for generation are covered by evidence pass.
            "evidence_fetch_count": max_prompt_items,
            "link_scout_count": max_prompt_items,
            "link_scout_timeout_seconds": 5 if run_mode == "fast" else 8,
            "per_doc_input_chars": 1100 if run_mode == "fast" else 1800,
            "fetch_timeout_seconds": 6 if run_mode == "fast" else 10,
            "candidate_url_limit": 3 if run_mode == "fast" else 6,
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
        backgrounds = state.get("backgrounds", {}) or {}
        evidence_meta = state.get("evidence_meta", {}) or {}
        verified_backgrounds: Dict[str, str] = {}
        for title, bg in backgrounds.items():
            if not str(bg or "").strip():
                continue
            status = _normalise_verification_status((evidence_meta.get(title) or {}).get("verification_status"))
            if status in _ADMISSIBLE_EVIDENCE_STATUSES:
                verified_backgrounds[title] = str(bg).strip()
        if not verified_backgrounds:
            verified_backgrounds = {
                str(k): str(v).strip()
                for k, v in backgrounds.items()
                if str(v or "").strip()
            }
        prompt = _build_prompt(
            items,
            backgrounds=verified_backgrounds,
            evidence_meta=evidence_meta,
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
        search_contexts = state.get("search_contexts") or {}
        
        # Determine what to fetch.
        # If target, fetch that specific target. Otherwise fetch all candidate items used for generation.
        fetch_targets: List[Dict[str, Any]] = []
        if target:
            fetch_targets = [item for item in items if _resolve_alias_in_text(str(item.get("title") or "").strip()) == target]
        else:
            fetch_targets = items[: int(planner.get("evidence_fetch_count") or planner.get("max_prompt_items") or 18)]
                
        import concurrent.futures
        
        def fetch_and_summarize(item: Dict[str, Any], allow_playwright: bool) -> Tuple[str, str, Dict[str, Any]]:
            title = _resolve_alias_in_text(str(item.get("title") or "").strip())
            url = item.get("url") or item.get("mobileUrl") or ""
            if not title:
                return title, "", {}
            
            if title in backgrounds and title != target:
                cached_meta = dict(evidence_meta.get(title) or {})
                if not cached_meta:
                    cached_meta = {
                        "source_url": "",
                        "source_domain": "",
                        "method": "cache",
                        "verification_status": "single_source",
                        "confidence": 0.65,
                        "agreement_count": 1,
                        "relevance_score": 0.65,
                        "authority_score": 0.58,
                        "freshness_score": 0.42,
                        "entity_alignment_score": 0.65,
                        "overall_score": 0.63,
                        "is_official": False,
                        "official_source_present": False,
                        "published_at": "",
                        "quality_metrics": {},
                        "claims": [],
                        "verification": {
                            "status": "single_source",
                            "confidence": 0.65,
                            "agreement_count": 1,
                            "official_source_present": False,
                        },
                    }
                cached_meta.setdefault("authority_score", 0.58)
                cached_meta.setdefault("freshness_score", 0.42)
                cached_meta.setdefault("entity_alignment_score", float(cached_meta.get("relevance_score") or 0.0))
                cached_meta.setdefault("overall_score", float(cached_meta.get("confidence") or 0.0))
                cached_meta.setdefault("is_official", False)
                cached_meta.setdefault("official_source_present", bool(cached_meta.get("is_official")))
                cached_meta.setdefault("published_at", "")
                cached_meta.setdefault("quality_metrics", {})
                cached_meta.setdefault("claims", [])
                cached_meta.setdefault(
                    "verification",
                    {
                        "status": "single_source",
                        "confidence": float(cached_meta.get("confidence") or 0.0),
                        "agreement_count": int(cached_meta.get("agreement_count") or 1),
                        "official_source_present": bool(cached_meta.get("official_source_present")),
                    },
                )
                cached_meta["verification_status"] = _normalise_verification_status(
                    cached_meta.get("verification_status")
                )
                return title, backgrounds[title], cached_meta
                
            candidate_urls = list(link_candidates.get(title) or [])
            if isinstance(url, str) and url.startswith("http") and url not in candidate_urls:
                candidate_urls.insert(0, url)
            if not candidate_urls and isinstance(url, str) and url.startswith("http"):
                candidate_urls = [url]
            if not candidate_urls:
                return title, "", {
                    "source_url": "",
                    "source_domain": "",
                    "method": "none",
                    "verification_status": "unresolved",
                    "confidence": 0.0,
                    "agreement_count": 0,
                    "relevance_score": 0.0,
                    "authority_score": 0.0,
                    "freshness_score": 0.0,
                    "entity_alignment_score": 0.0,
                    "overall_score": 0.0,
                    "is_official": False,
                    "official_source_present": False,
                    "published_at": "",
                    "quality_metrics": {},
                    "claims": [],
                    "verification": {
                        "status": "unresolved",
                        "confidence": 0.0,
                        "agreement_count": 0,
                        "official_source_present": False,
                    },
                }

            relevant_candidates: List[Tuple[float, str, Dict[str, Any]]] = []
            weak_candidate: Optional[Tuple[float, str, Dict[str, Any]]] = None
            retrieved_any = False
            fetch_timeout = int(planner.get("fetch_timeout_seconds") or 10)
            candidate_limit = int(planner.get("candidate_url_limit") or 6)
            non_article_attempted = False
            for candidate in candidate_urls[: max(1, candidate_limit)]:
                if not _is_probably_article_url(candidate):
                    if non_article_attempted:
                        continue
                    non_article_attempted = True
                text = _fetch_url_text(candidate, timeout=fetch_timeout)
                selected_method = "direct"
                need_playwright = (not text) or _is_block_or_low_quality_text(text)
                if need_playwright and allow_playwright and bool(planner.get("use_playwright_fallback")):
                    text = _fetch_url_text_playwright(
                        str(candidate),
                        timeout_ms=max(6000, fetch_timeout * 1000 + 2000),
                    )
                    if text:
                        selected_method = "playwright"
                if not text or _is_block_or_low_quality_text(text):
                    continue
                retrieved_any = True
                relevance_score = _context_relevance_score(title, text)
                domain = _extract_domain(str(candidate))
                authority_score = _authority_score_for_domain(domain)
                is_official = _is_official_domain(domain)
                low_value_source = _is_low_value_source_domain(domain)
                published_at = _extract_published_at(text, url=str(candidate))
                freshness_score = _freshness_score(published_at)
                quality_metrics = _compute_readerability_metrics(text)
                readerable_score = float(quality_metrics.get("readerable_score") or 0.0)
                overall_score = (
                    relevance_score * 0.46
                    + readerable_score * 0.22
                    + freshness_score * 0.20
                    + authority_score * 0.12
                    + (0.04 if is_official else 0.0)
                    - (0.16 if low_value_source else 0.0)
                )
                claims = _extract_claim_units(text, limit=3)
                meta = {
                    "source_url": str(candidate),
                    "source_domain": _normalise_domain(domain),
                    "method": selected_method or "direct",
                    "relevance_score": round(relevance_score, 2),
                    "authority_score": round(authority_score, 2),
                    "freshness_score": round(freshness_score, 2),
                    "entity_alignment_score": round(relevance_score, 2),
                    "overall_score": round(min(1.0, max(0.0, overall_score)), 3),
                    "is_official": bool(is_official),
                    "low_value_source": bool(low_value_source),
                    "published_at": published_at,
                    "quality_metrics": quality_metrics,
                    "claims": claims,
                }
                if relevance_score >= 0.52 and bool(quality_metrics.get("passes")):
                    relevant_candidates.append((float(meta["overall_score"]), text, meta))
                    if len(relevant_candidates) >= 3 and float(meta["overall_score"]) >= 0.66:
                        break
                elif relevance_score >= 0.30:
                    if weak_candidate is None or float(meta["overall_score"]) > float(weak_candidate[0]):
                        weak_candidate = (float(meta["overall_score"]), text, meta)

            if relevant_candidates:
                relevant_candidates.sort(
                    key=lambda entry: entry[0],
                    reverse=True,
                )
                best_score, best_text, best_meta = relevant_candidates[0]
                domains = [str((meta or {}).get("source_domain") or "") for _, _, meta in relevant_candidates]
                unique_domains = [d for d in dict.fromkeys(domains) if d]
                agreement_count = len(
                    [
                        1
                        for score, _, _ in relevant_candidates
                        if float(score) >= 0.58
                    ]
                )
                official_source_present = any(bool((meta or {}).get("is_official")) for _, _, meta in relevant_candidates)
                status = "relevant"
                if (agreement_count >= 2 and len(unique_domains) >= 2) or (
                    official_source_present and best_score >= 0.62
                ):
                    status = "corroborated"
                elif best_score >= 0.66:
                    status = "single_source"
                if _is_low_value_source_domain(str(best_meta.get("source_domain") or "")) and status != "corroborated":
                    status = "weak_match"
                confidence = min(
                    0.98,
                    0.28
                    + best_score * 0.52
                    + (0.12 if status == "corroborated" else 0.0)
                    + (0.06 if official_source_present else 0.0),
                )
                text = best_text[: int(planner.get("per_doc_input_chars") or 900)]
                if status not in _ADMISSIBLE_EVIDENCE_STATUSES:
                    return title, "", {
                        **best_meta,
                        "verification_status": status,
                        "confidence": round(min(0.55, confidence), 2),
                        "agreement_count": agreement_count,
                        "official_source_present": bool(official_source_present),
                        "verification": {
                            "status": status,
                            "confidence": round(min(0.55, confidence), 2),
                            "agreement_count": agreement_count,
                            "official_source_present": bool(official_source_present),
                        },
                        "relevance": "weak_match",
                    }
                refined = _refine_evidence_with_subagent(
                    title,
                    text,
                    source_domain=str(best_meta.get("source_domain") or ""),
                    published_at=str(best_meta.get("published_at") or ""),
                )
                refined_fact = _truncate_compact_text(str(refined.get("fact") or "").strip(), limit=220)
                refined_claims = list(refined.get("claims") or [])
                best_claims = refined_claims or _extract_claim_units(text, limit=3) or list(best_meta.get("claims") or [])
                summary = _compose_fact_summary(
                    text,
                    primary_fact=refined_fact,
                    claims=best_claims if isinstance(best_claims, list) else [],
                    limit=180,
                )
                if len(summary) < 48:
                    fact_sentence = _best_fact_sentence(text)
                    summary = _compose_fact_summary(
                        text,
                        primary_fact=fact_sentence,
                        claims=best_claims if isinstance(best_claims, list) else [],
                        limit=180,
                    )

                source_urls: List[str] = []
                source_domains: List[str] = []
                for _, _, candidate_meta in relevant_candidates[:3]:
                    url_text = str(candidate_meta.get("source_url") or "").strip()
                    if url_text and url_text not in source_urls:
                        source_urls.append(url_text)
                    domain_text = _normalise_domain(str(candidate_meta.get("source_domain") or ""))
                    if domain_text and domain_text not in source_domains:
                        source_domains.append(domain_text)
                return title, summary, {
                    **best_meta,
                    "source_urls": source_urls,
                    "source_domains": source_domains,
                    "verification_status": status,
                    "confidence": round(confidence, 2),
                    "agreement_count": agreement_count,
                    "official_source_present": bool(official_source_present),
                    "claims": best_claims[:3],
                    "verification": {
                        "status": status,
                        "confidence": round(confidence, 2),
                        "agreement_count": agreement_count,
                        "official_source_present": bool(official_source_present),
                    },
                    "relevance": "matched",
                }

            if weak_candidate is not None:
                weak_score, weak_text, weak_meta = weak_candidate
                weak_claims = _extract_claim_units(weak_text, limit=2) or list(weak_meta.get("claims") or [])
                return title, "", {
                    **weak_meta,
                    "verification_status": "weak_match",
                    "confidence": round(min(0.55, 0.2 + weak_score * 0.35), 2),
                    "agreement_count": 1,
                    "official_source_present": bool(weak_meta.get("is_official")),
                    "claims": weak_claims[:2],
                    "verification": {
                        "status": "weak_match",
                        "confidence": round(min(0.55, 0.2 + weak_score * 0.35), 2),
                        "agreement_count": 1,
                        "official_source_present": bool(weak_meta.get("is_official")),
                    },
                    "relevance": "weak_match",
                }

            if retrieved_any:
                fallback_url = str(candidate_urls[0]) if candidate_urls else ""
                return title, "", {
                    "source_url": fallback_url,
                    "source_domain": _normalise_domain(_extract_domain(fallback_url)),
                    "method": "direct",
                    "verification_status": "retrieved",
                    "confidence": 0.1,
                    "agreement_count": 0,
                    "relevance_score": 0.0,
                    "authority_score": round(_authority_score_for_domain(fallback_url), 2),
                    "freshness_score": 0.0,
                    "entity_alignment_score": 0.0,
                    "overall_score": 0.0,
                    "is_official": _is_official_domain(fallback_url),
                    "official_source_present": _is_official_domain(fallback_url),
                    "published_at": "",
                    "quality_metrics": {},
                    "claims": [],
                    "verification": {
                        "status": "retrieved",
                        "confidence": 0.1,
                        "agreement_count": 0,
                        "official_source_present": _is_official_domain(fallback_url),
                    },
                    "relevance": "retrieved",
                }

            return title, "", {
                "source_url": "",
                "source_domain": "",
                "method": "none",
                "verification_status": "unresolved",
                "confidence": 0.0,
                "agreement_count": 0,
                "relevance_score": 0.0,
                "authority_score": 0.0,
                "freshness_score": 0.0,
                "entity_alignment_score": 0.0,
                "overall_score": 0.0,
                "is_official": False,
                "official_source_present": False,
                "published_at": "",
                "quality_metrics": {},
                "claims": [],
                "verification": {
                    "status": "unresolved",
                    "confidence": 0.0,
                    "agreement_count": 0,
                    "official_source_present": False,
                },
                "relevance": "unresolved",
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
                    if not title:
                        continue
                    if bg:
                        backgrounds[title] = bg
                    if isinstance(meta, dict):
                        meta["verification_status"] = _normalise_verification_status(meta.get("verification_status"))
                        evidence_meta[title] = meta
                except Exception as e:
                    LOGGER.warning("Research node fetch error: %s", e)

        for item in fetch_targets:
            title = _resolve_alias_in_text(str(item.get("title") or "").strip())
            if not title or title in evidence_meta:
                continue
            snippet = str(search_contexts.get(title) or "").strip()
            if snippet:
                snippet_published_at = _extract_published_at(snippet)
                evidence_meta[title] = {
                    "source_url": "",
                    "source_domain": "",
                    "method": "rss_snippet",
                    "verification_status": "retrieved",
                    "confidence": 0.08,
                    "agreement_count": 0,
                    "relevance_score": 0.0,
                    "authority_score": 0.0,
                    "freshness_score": round(_freshness_score(snippet_published_at), 2),
                    "entity_alignment_score": 0.0,
                    "overall_score": 0.0,
                    "is_official": False,
                    "official_source_present": False,
                    "published_at": snippet_published_at,
                    "quality_metrics": _compute_readerability_metrics(snippet),
                    "claims": _extract_claim_units(snippet, limit=2),
                    "verification": {
                        "status": "retrieved",
                        "confidence": 0.08,
                        "agreement_count": 0,
                        "official_source_present": False,
                    },
                    "relevance": "retrieved",
                }
            else:
                evidence_meta[title] = {
                    "source_url": "",
                    "source_domain": "",
                    "method": "none",
                    "verification_status": "unresolved",
                    "confidence": 0.0,
                    "agreement_count": 0,
                    "relevance_score": 0.0,
                    "authority_score": 0.0,
                    "freshness_score": 0.0,
                    "entity_alignment_score": 0.0,
                    "overall_score": 0.0,
                    "is_official": False,
                    "official_source_present": False,
                    "published_at": "",
                    "quality_metrics": {},
                    "claims": [],
                    "verification": {
                        "status": "unresolved",
                        "confidence": 0.0,
                        "agreement_count": 0,
                        "official_source_present": False,
                    },
                    "relevance": "unresolved",
                }

        if target and hint and target in backgrounds:
            backgrounds[target] = backgrounds[target].replace(f" [用户提示: {hint}]", "") + f" [用户提示: {hint}]"
        elif target and hint:
            backgrounds[target] = f"[用户提示: {hint}]"
            evidence_meta[target] = {
                "source_url": "",
                "source_domain": "",
                "method": "user_hint",
                "verification_status": "retrieved",
                "confidence": 0.06,
                "agreement_count": 0,
                "relevance_score": 0.0,
                "authority_score": 0.0,
                "freshness_score": 0.0,
                "entity_alignment_score": 0.0,
                "overall_score": 0.0,
                "is_official": False,
                "official_source_present": False,
                "published_at": "",
                "quality_metrics": {},
                "claims": [],
                "verification": {
                    "status": "retrieved",
                    "confidence": 0.06,
                    "agreement_count": 0,
                    "official_source_present": False,
                },
                "relevance": "retrieved",
            }
            
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
            scout_timeout = int(planner.get("link_scout_timeout_seconds") or 8)
            futures = [executor.submit(_discover_candidate_links, item, scout_timeout) for item in scout_targets]
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
        dynamic_keywords = _build_dynamic_keyword_pool(
            items,
            limit=14,
            backgrounds=backgrounds,
            evidence_meta=evidence_meta,
        )
        if dynamic_keywords:
            fallback_structured["keyword_pool"] = [
                {"text": kw[:18], "cluster": "general"} for kw in dynamic_keywords[:14]
            ]
        
        prompt = _build_prompt(
            items,
            backgrounds=backgrounds,
            evidence_meta=evidence_meta,
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
        evidence_meta = state.get("evidence_meta") or {}
        items = state.get("items") or []
        planner = state.get("planner") or {}
        max_items = int(planner.get("max_prompt_items") or 18)
        target_titles = [
            _resolve_alias_in_text(str(item.get("title") or "").strip())
            for item in items[:max_items]
            if str(item.get("title") or "").strip()
        ]
        status_list: List[str] = []
        for title in target_titles:
            raw_status = (evidence_meta.get(title) or {}).get("verification_status")
            status_list.append(_normalise_verification_status(raw_status))

        evidence_ready_count = sum(1 for status in status_list if status in _ADMISSIBLE_EVIDENCE_STATUSES)
        corroborated_count = sum(1 for status in status_list if status == "corroborated")
        official_source_count = 0
        overall_signal_scores: List[float] = []
        for title in target_titles:
            meta = evidence_meta.get(title) if isinstance(evidence_meta, dict) else {}
            if bool((meta or {}).get("official_source_present")):
                official_source_count += 1
            overall_signal_scores.append(_safe_float((meta or {}).get("overall_score"), 0.0))
        uncertain_count = sum(
            1
            for status in status_list
            if status in _UNCERTAIN_EVIDENCE_STATUSES
        )
        evidence_coverage = round(evidence_ready_count / max(1, len(target_titles)), 2)
        corroborated_coverage = round(corroborated_count / max(1, len(target_titles)), 2)
        official_source_coverage = round(official_source_count / max(1, len(target_titles)), 2)
        avg_overall_signal = round(sum(overall_signal_scores) / max(1, len(overall_signal_scores)), 2)
        uncertain_card_ratio = round(uncertain_count / max(1, len(target_titles)), 2)

        sections = final_payload.get("sections") if isinstance(final_payload, dict) else []
        card_count = 0
        section_count = 0
        grounded_section_count = 0
        for section in sections if isinstance(sections, list) else []:
            if isinstance(section, dict) and isinstance(section.get("cards"), list):
                card_count += len(section.get("cards") or [])
                title = str(section.get("title") or "").strip()
                if title not in {"待核实热点", "热点速览"}:
                    section_count += 1
                    cards = section.get("cards") or []
                    has_grounded = False
                    for card in cards if isinstance(cards, list) else []:
                        status = _normalise_verification_status(((card or {}).get("evidence") or {}).get("status"))
                        if status in _ADMISSIBLE_EVIDENCE_STATUSES:
                            has_grounded = True
                            break
                    if has_grounded:
                        grounded_section_count += 1
        overview_grounded_ratio = round(grounded_section_count / max(1, section_count), 2) if section_count else 0.0

        if not backgrounds:
            issues.append("low_evidence")
        if evidence_coverage < 0.7:
            issues.append("low_evidence_coverage")
        if corroborated_coverage < 0.5:
            issues.append("low_corroborated_coverage")
        if overview_grounded_ratio < 1.0:
            issues.append("ungrounded_overview")
        if uncertain_card_ratio > 0.3:
            issues.append("high_uncertainty")

        # Hard gate for evidence quality; keep format checks as baseline.
        ok = ok and evidence_coverage >= 0.7 and overview_grounded_ratio >= 1.0 and uncertain_card_ratio <= 0.3
        dedup_issues = list(dict.fromkeys(str(item) for item in issues if str(item).strip()))
        critic = {
            "ok": ok,
            "issues": dedup_issues,
            "evidence_count": len(backgrounds),
            "card_count": card_count,
            "evidence_coverage": evidence_coverage,
            "corroborated_coverage": corroborated_coverage,
            "official_source_coverage": official_source_coverage,
            "avg_overall_signal": avg_overall_signal,
            "overview_grounded_ratio": overview_grounded_ratio,
            "uncertain_card_ratio": uncertain_card_ratio,
            "evidence_ready_count": evidence_ready_count,
            "target_count": len(target_titles),
            "sense_resolved_count": len(sense_map) if isinstance(sense_map, dict) else 0,
        }
        return {**state, "critic": critic}

    def _resolver_node(state: _OverviewState) -> _OverviewState:
        final_payload = dict(state.get("final_payload") or {})
        draft = dict(state.get("draft_payload") or {})
        critic = state.get("critic") or {}
        backgrounds = state.get("backgrounds") or {}
        evidence_meta = state.get("evidence_meta") or {}
        issue_set = {str(item) for item in (critic.get("issues") or [])}

        if not final_payload:
            if draft and not {"low_evidence_coverage", "ungrounded_overview"} & issue_set:
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
        if {"low_evidence_coverage", "ungrounded_overview"} & issue_set:
            verified_snapshot = _build_verified_snapshot(
                state.get("items", []),
                backgrounds if isinstance(backgrounds, dict) else {},
                evidence_meta if isinstance(evidence_meta, dict) else {},
                max_entries=4,
            )
            if verified_snapshot:
                lead_titles = [str(item.get("title") or "") for item in verified_snapshot[:2] if str(item.get("title") or "")]
                lead_text = "；".join(lead_titles)
                final_payload["overview"] = f"{lead_text}。" if lead_text else str(final_payload.get("overview") or "")
                detail_lines: List[str] = []
                bullet_points: List[str] = []
                keyword_pool: List[Dict[str, str]] = [] if not _KEYWORD_POOL_AI_ONLY else []
                seen_keywords: set[str] = set() if not _KEYWORD_POOL_AI_ONLY else set()
                for entry in verified_snapshot:
                    title_text = str(entry.get("title") or "").strip()
                    fact_text = str(entry.get("fact") or "").strip()
                    domain = str(entry.get("domain") or "").strip()
                    published_at = str(entry.get("published_at") or "").strip()
                    suffix_parts = []
                    if domain:
                        suffix_parts.append(domain)
                    if published_at:
                        suffix_parts.append(published_at)
                    suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
                    line = f"{title_text}：{fact_text}{suffix}"
                    detail_lines.append(line[:160])
                    bullet_points.append(f"{title_text}：{fact_text}"[:48])
                    if not _KEYWORD_POOL_AI_ONLY:
                        for token in _extract_semantic_terms(
                            title_text + " " + fact_text,
                            max_terms=6,
                            emit_cjk_ngrams=False,
                        ):
                            text = str(token or "").strip()
                            if not _is_valid_keyword_text(text, min_len=2, max_len=16):
                                continue
                            if text in seen_keywords:
                                continue
                            seen_keywords.add(text)
                            keyword_pool.append({"text": text, "cluster": "general"})
                            if len(keyword_pool) >= 12:
                                break
                        if len(keyword_pool) >= 12:
                            continue
                final_payload["detailed_overview"] = "；".join(detail_lines)
                final_payload["bullet_points"] = bullet_points[:8]
                if (not _KEYWORD_POOL_AI_ONLY) and keyword_pool:
                    final_payload["keyword_pool"] = keyword_pool[:14]

                unresolved_titles: List[str] = []
                for item in state.get("items", [])[:18]:
                    title = _resolve_alias_in_text(str(item.get("title") or "").strip())
                    if not title:
                        continue
                    status = _normalise_verification_status(((evidence_meta.get(title) or {}) if isinstance(evidence_meta, dict) else {}).get("verification_status"))
                    if status in _UNCERTAIN_EVIDENCE_STATUSES and title not in unresolved_titles:
                        unresolved_titles.append(title)
                watch_points = [f"跟进：{text}"[:32] for text in unresolved_titles[:4]]
                final_payload["watch_points"] = watch_points[:6]
                final_payload["summary_source"] = "verified_snapshot_guarded"
            else:
                fallback_text = _fallback_overview(state.get("items", []))
                final_payload["overview"] = str(fallback_text.get("overview") or final_payload.get("overview") or "")
                final_payload["detailed_overview"] = str(
                    fallback_text.get("detailed_overview") or final_payload.get("detailed_overview") or ""
                )
                bullets = final_payload.get("bullet_points")
                if not isinstance(bullets, list) or not bullets:
                    final_payload["bullet_points"] = ["热点结构可见，建议持续关注后续进展。"]
                final_payload["watch_points"] = list(fallback_text.get("watch_points") or [])
                final_payload["summary_source"] = "langchain_reflective_guarded"
        final_payload["_critic"] = critic
        return {**state, "final_payload": final_payload}

    try:
        workflow = StateGraph(_OverviewState)
        workflow.add_node("planner", _planner_node)
        workflow.add_node("link_scout", _link_scout_node)
        workflow.add_node("research", _research_node)
        workflow.add_node("disambiguation", _disambiguation_node)
        workflow.add_node("draft", _draft_node)
        workflow.add_node("refine", _refine_node)
        workflow.add_node("critic", _critic_node)
        workflow.add_node("resolver", _resolver_node)
        
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "link_scout")
        workflow.add_edge("link_scout", "research")
        workflow.add_edge("research", "disambiguation")
        workflow.add_edge("disambiguation", "draft")
        workflow.add_edge("draft", "refine")
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
            other_hotspot_review = _build_other_hotspot_review(
                news_items,
                evidence_meta=result.get("evidence_meta", {}) or {},
                link_candidates=link_candidates,
                max_clusters=4,
                max_items_per_cluster=6,
            )
            final_payload["_backgrounds"] = backgrounds
            final_payload["_planner"] = result.get("planner", {})
            final_payload["_link_scout"] = link_scout_diag
            final_payload["_sense_map"] = result.get("sense_map", {})
            final_payload["_evidence_meta"] = result.get("evidence_meta", {})
            final_payload["_link_candidates"] = link_candidates
            final_payload["_other_hotspot_review"] = other_hotspot_review
            LOGGER.info(
                "hot_overview diagnostics | scout_titles=%s candidates=%s snippets=%s evidence_hits=%s sense_resolved=%s evidence_meta=%s review_clusters=%s review_items=%s",
                int(link_scout_diag.get("title_count") or 0),
                int(link_scout_diag.get("candidate_link_count") or 0),
                int(link_scout_diag.get("snippet_count") or 0),
                int(link_scout_diag.get("evidence_hit_count") or 0),
                len(result.get("sense_map", {}) or {}),
                len(result.get("evidence_meta", {}) or {}),
                int(other_hotspot_review.get("cluster_count") or 0),
                int(other_hotspot_review.get("item_count") or 0),
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
    filters_changed = _refresh_hot_overview_filter_config_if_needed()
    now = time.time()
    today = _today_snapshot_date()
    cache_key = _resolve_mode(mode=mode, include_research=include_research)
    run_research = cache_key == "research"
    cache_slot = _CACHE.setdefault(cache_key, {"data": None, "expires_at": 0.0})
    if filters_changed:
        force_refresh = True
        cache_slot["data"] = None
        cache_slot["expires_at"] = 0.0
    LOGGER.info(
        "hot_overview start | force_refresh=%s limit=%s mode=%s today=%s filters_changed=%s",
        force_refresh,
        limit,
        cache_key,
        today,
        filters_changed,
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
        "other_hotspot_review": summary.get("_other_hotspot_review", {}),
        "items": selected_items,
        "total_items": len(merged_items),
        "sources": source_stats,
        "research": None,
        "evidence": (
            {
                "enabled": True,
                "mode": cache_key,
                "doc_count": len(summary.get("_backgrounds", {}) or {}),
                "titles": list((summary.get("_backgrounds", {}) or {}).keys())[:6],
            }
            if _EXPOSE_EVIDENCE_STATUS_TO_CLIENT
            else {}
        ),
        "diagnostics": {
            "planner": summary.get("_planner", {}),
            "critic": summary.get("_critic", {}),
            "link_scout": summary.get("_link_scout", {}),
            "sense_map": summary.get("_sense_map", {}),
            "evidence_meta": summary.get("_evidence_meta", {}),
            "other_hotspot_review": summary.get("_other_hotspot_review", {}),
        },
        "_backgrounds": summary.get("_backgrounds", {}),
        "_merged_items": merged_items,
    }

    if run_research:
        payload["research"] = _run_research_langgraph(
            merged_items,
            backgrounds=summary.get("_backgrounds", {}) or {},
            evidence_meta=summary.get("_evidence_meta", {}) or {},
        )

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


def build_hot_overview_timeout_fallback(
    *,
    limit: int = DEFAULT_LIMIT,
    mode: str = "fast",
    include_research: Optional[bool] = None,
    reason: str = "",
) -> Dict[str, Any]:
    """Return a safe payload when realtime refresh/build times out."""
    cache_key = _resolve_mode(mode=mode, include_research=include_research)
    today = _today_snapshot_date()
    now_iso = datetime.now(timezone.utc).isoformat()
    cache_slot = _CACHE.setdefault(cache_key, {"data": None, "expires_at": 0.0})

    # Prefer in-memory/archive payload even if stale; UX beats hard failure on timeout.
    candidate = cache_slot.get("data")
    if not isinstance(candidate, dict):
        candidate = _load_archive_payload(cache_key)

    if isinstance(candidate, dict):
        payload = _apply_limit_to_payload(candidate, limit)
        payload["generated_at"] = now_iso
        payload["summary_source"] = "timeout_fallback_cache"
        payload["fallback_notice"] = "热点实时刷新超时，已回退到可用缓存。"
        payload.setdefault("diagnostics", {})
        if isinstance(payload.get("diagnostics"), dict):
            payload["diagnostics"]["fallback"] = {
                "kind": "timeout_cache",
                "reason": reason or "build_timeout",
            }
        return payload

    # First open and no cache: return a render-safe empty payload with a friendly notice.
    return {
        "revision_id": _new_revision_id(),
        "generated_at": now_iso,
        "snapshot_date": today,
        "mode": cache_key,
        "summary_source": "timeout_fallback_empty",
        "overview": "热点服务暂时繁忙，已为你保留页面结构，请稍后重试刷新。",
        "detailed_overview": "",
        "bullet_points": [],
        "watch_points": [],
        "keyword_pool": [],
        "sections": [],
        "other_hotspot_review": {"cluster_count": 0, "clusters": [], "item_count": 0},
        "items": [],
        "total_items": 0,
        "sources": [],
        "research": None,
        "evidence": {},
        "diagnostics": {
            "fallback": {
                "kind": "timeout_empty",
                "reason": reason or "build_timeout",
            }
        },
        "fallback_notice": "热点实时刷新超时，当前暂无可用缓存，请稍后再试。",
        "_backgrounds": {},
        "_merged_items": [],
    }


def reclassify_hot_overview(
    *,
    target_title: str,
    hint: str,
    mode: str = "fast",
    include_research: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    _refresh_hot_overview_filter_config_if_needed()
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
        "other_hotspot_review": summary.get("_other_hotspot_review", {}),
        "items": selected_items,
        "total_items": len(merged_items),
        "sources": old_payload.get("sources", []),
        "research": old_payload.get("research"),
        "evidence": (
            {
                "enabled": True,
                "mode": cache_key,
                "doc_count": len(summary.get("_backgrounds", {}) or {}),
                "titles": list((summary.get("_backgrounds", {}) or {}).keys())[:6],
            }
            if _EXPOSE_EVIDENCE_STATUS_TO_CLIENT
            else {}
        ),
        "diagnostics": {
            "planner": summary.get("_planner", {}),
            "critic": summary.get("_critic", {}),
            "link_scout": summary.get("_link_scout", {}),
            "sense_map": summary.get("_sense_map", {}),
            "evidence_meta": summary.get("_evidence_meta", {}),
            "other_hotspot_review": summary.get("_other_hotspot_review", {}),
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
