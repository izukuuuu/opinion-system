"""
Multi-Agent BERTopic Re-clustering Module

Uses LangGraph StateGraph to orchestrate 5 specialised agents:

1. Scope Analyst        – recommends max_topics from raw stats
2. Cluster Strategist   – merges BERTopic topics into clusters
3. Relevance Judge      – marks irrelevant clusters for dropping
4. Custom Filter Judge  – applies user-defined exclusion rules
                          (one LLM call per filter rule)
5. Naming & Keywords    – produces final names and keywords

Graph topology::

    scope_analyst → cluster_strategist → relevance_judge
         ↑                                    │
         │ (retry)                             ├─ apply_filters → custom_filter_judge ─┐
         │                                    │                                       ├→ naming_keywords → END
         └─── increment_iteration ◄───────────┘                                       │
                                              └─ skip_filters ────────────────────────┘

A lightweight Supervisor router (_post_judge_router) coordinates the
Strategist→Judge refinement loop and the conditional activation of
user-defined custom filters.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, TypedDict

from ..utils.ai import call_langchain_chat, ensure_langchain_uuid_compat

# ---------------------------------------------------------------------------
# Shared state schema
# ---------------------------------------------------------------------------

class ReclusterState(TypedDict, total=False):
    """Shared state passed through the StateGraph."""

    # Inputs (set once)
    topic_stats: List[Dict[str, Any]]          # BERTopic raw topic stats
    focus_topic: str                            # 专题名
    max_topics_hint: int                        # user-supplied upper bound
    min_topics_floor: int                       # hard lower bound for retained topics
    drop_rule_prompt: str                       # user-defined drop template
    recluster_system_prompt: str
    recluster_user_prompt: str
    keyword_system_prompt: str
    keyword_user_prompt: str
    recluster_dimension: str                    # business rule: clustering perspective
    must_separate_rules: List[str]              # business rule: custom topic seed hints (legacy key)
    custom_topic_seed_rules: List[str]          # business rule: custom topic seed hints
    must_merge_rules: List[str]                 # business rule: force-merge hints
    core_drop_rules: List[str]                  # business rule: contextual relevance hints
    judge_sample_per_topic: int                  # evidence size shown to judge
    large_cluster_doc_share: float               # safeguard: keep large-share cluster
    large_cluster_doc_count: int                 # safeguard: keep large-count cluster
    max_drop_ratio: float                        # safeguard: do not drop too many clusters
    global_filters: List[str]                    # system-level exclusion category names
    project_filters: List[Dict[str, str]]        # user-defined exclusion filters
    custom_filters: List[Dict[str, str]]         # legacy alias of project_filters
    logger: Any                                 # logging.Logger (not serialised)

    # Intermediate / outputs
    recommended_max_topics: int
    scope_reasoning: str
    clusters: List[Dict[str, Any]]
    judged_clusters: List[Dict[str, Any]]
    retained_clusters: List[Dict[str, Any]]
    dropped_count: int
    iteration: int
    final_clusters: List[Dict[str, Any]]       # after naming/keywords
    error: str


MAX_ITERATIONS = 3
_EMPTY: List[Dict[str, Any]] = []
DEFAULT_JUDGE_SAMPLE_PER_TOPIC = 3
DEFAULT_LARGE_CLUSTER_DOC_SHARE = 0.08
DEFAULT_MAX_DROP_RATIO = 0.45

DIMENSION_RULE_GUIDES: Dict[str, List[str]] = {
    "业务场景": [
        "优先按业务链路阶段、用户诉求场景、问题处理环节进行一级分组。",
        "同一组需要能解释为同一业务情境下的同类问题或动作。",
        "若语义接近但业务动作不同，应拆分为不同类别。",
    ],
    "情感倾向": [
        "优先按情绪极性与立场方向分组（正向/负向/中性/争议）。",
        "同组内情绪基调应一致，不要把对立情绪合并。",
        "事实陈述类内容需先判断语气倾向再归类。",
    ],
    "对象实体": [
        "优先按被讨论对象分组（品牌/机构/人物/产品/渠道）。",
        "不同对象即使议题接近，也优先分开。",
        "对象指代不明时，先根据上下文补全主实体再聚类。",
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_async_call(coro):
    """Run an async coroutine from sync context (reuse existing event loop if any)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _call_llm(
    messages: List[Dict[str, str]],
    *,
    task: str = "topic_bertopic",
    temperature: float = 0.2,
    max_tokens: int = 2400,
) -> Optional[str]:
    raw = _safe_async_call(
        call_langchain_chat(
            messages,
            task=task,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    return cleaned or None


def _extract_json(text: str) -> Optional[Dict]:
    """Attempt to parse JSON from LLM text (with fence stripping)."""
    import re
    if not text:
        return None
    # strip ```json ... ``` fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # try to find first { ... }
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


def _log(state: ReclusterState, msg: str, level: str = "info"):
    logger = state.get("logger")
    if logger:
        getattr(logger, level, logger.info)(f"[MultiAgent] {msg}")


def _coerce_int(value: Any, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = int(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _coerce_float(value: Any, default: float, minimum: Optional[float] = None, maximum: Optional[float] = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _trim_text(text: Any, max_chars: int = 220) -> str:
    import re

    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars - 1]}…"


def _normalise_label_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    seen: set = set()
    result: List[str] = []
    for item in raw:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalise_filter_items(raw: Any) -> List[Dict[str, str]]:
    if not isinstance(raw, list):
        return []
    seen: set = set()
    result: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        description = str(item.get("description") or "").strip()
        if not category and not description:
            continue
        key = (category, description)
        if key in seen:
            continue
        seen.add(key)
        result.append({"category": category, "description": description})
    return result


def _resolve_custom_filters(state: ReclusterState) -> List[Dict[str, str]]:
    """Merge global/project filters with backward-compatible legacy filters."""
    seen: set = set()
    resolved: List[Dict[str, str]] = []

    for label in _normalise_label_list(state.get("global_filters")):
        key = (label, "系统预设全局排除类目")
        if key in seen:
            continue
        seen.add(key)
        resolved.append({"category": label, "description": "系统预设全局排除类目"})

    project_filters = _normalise_filter_items(state.get("project_filters"))
    legacy_filters = _normalise_filter_items(state.get("custom_filters"))
    for item in [*project_filters, *legacy_filters]:
        key = (item["category"], item["description"])
        if key in seen:
            continue
        seen.add(key)
        resolved.append(item)

    return resolved


def _yaml_quote(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _append_yaml_list(lines: List[str], indent: int, items: List[str]) -> None:
    prefix = " " * indent
    for item in items:
        value = str(item or "").strip()
        if not value:
            continue
        lines.append(f"{prefix}- {_yaml_quote(value)}")


def _build_business_rules_hint(
    recluster_dimension: str,
    custom_topic_seeds: List[str],
    must_merge: List[str],
) -> str:
    dimension = str(recluster_dimension or "").strip()
    if not (dimension or custom_topic_seeds or must_merge):
        return ""

    lines: List[str] = ["business_rules:"]

    if dimension:
        guide_items = DIMENSION_RULE_GUIDES.get(
            dimension,
            [
                "请先按该视角完成一级分组，再在组内做语义细分。",
                "同组需具备一致且可解释的共同特征，不可仅按表层关键词合并。",
                "类别命名需体现该视角，避免泛化命名。",
            ],
        )
        lines.extend(
            [
                "  recluster_strategy:",
                f"    perspective: {_yaml_quote(dimension)}",
                '    objective: "先按主导视角完成一级聚类，再在组内做语义细分与命名。"',
                "    guide:",
            ]
        )
        _append_yaml_list(lines, 6, guide_items)

    if custom_topic_seeds:
        lines.extend(
            [
                "  custom_topic_recognition:",
                "    seed_topics:",
            ]
        )
        _append_yaml_list(lines, 6, custom_topic_seeds)
        lines.extend(
            [
                "    assignment_rule:",
                '      - "与 seed_topics 语义高度相近的原始主题，优先归入同一类别。"',
                '      - "该类别与其他聚类流程一致，需进入后续命名与关键词生成阶段。"',
                '      - "若同时命中多个 seed_topics，按语义最贴近者归类并在描述中体现边界。"',
            ]
        )

    if must_merge:
        lines.append("  should_merge:")
        _append_yaml_list(lines, 4, must_merge)

    lines.extend(
        [
            "  execution_requirements:",
            '    - "优先保证组内语义一致性，再控制组间边界清晰。"',
            '    - "custom_topic_recognition.seed_topics 仅定义归类锚点，不直接作为最终类别名。"',
            '    - "与 should_merge 冲突时，优先满足 seed_topics 的归类锚定。"',
            '    - "输出类别命名需可解释，并与主导视角保持一致。"',
        ]
    )
    return "\n".join(lines)


def _build_topic_lookup(topic_stats: List[Dict[str, Any]]) -> tuple[Dict[str, Dict[str, Any]], int]:
    lookup: Dict[str, Dict[str, Any]] = {}
    total_docs = 0
    for topic in topic_stats:
        topic_name = str(topic.get("topic_name") or "").strip()
        if not topic_name:
            continue
        count = _coerce_int(topic.get("count"), 0, minimum=0)
        total_docs += count
        keywords = topic.get("keywords") if isinstance(topic.get("keywords"), list) else []
        samples_raw = topic.get("samples") if isinstance(topic.get("samples"), list) else []
        samples: List[str] = []
        for item in samples_raw:
            trimmed = _trim_text(item)
            if trimmed:
                samples.append(trimmed)
        lookup[topic_name] = {
            "count": count,
            "keywords": [str(k).strip() for k in keywords if str(k or "").strip()],
            "samples": samples,
        }
    return lookup, total_docs


def _cluster_doc_stats(
    cluster: Dict[str, Any],
    topic_lookup: Dict[str, Dict[str, Any]],
    total_docs: int,
    sample_per_topic: int,
) -> Dict[str, Any]:
    topics = cluster.get("topics")
    if not isinstance(topics, list):
        topics = []

    details = []
    doc_count = 0
    seen_topics: set = set()
    for topic_name in topics:
        name = str(topic_name or "").strip()
        if not name or name in seen_topics:
            continue
        seen_topics.add(name)
        detail = topic_lookup.get(name, {})
        count = _coerce_int(detail.get("count"), 0, minimum=0)
        doc_count += count
        keywords = detail.get("keywords") if isinstance(detail.get("keywords"), list) else []
        samples = detail.get("samples") if isinstance(detail.get("samples"), list) else []
        details.append(
            {
                "topic_name": name,
                "count": count,
                "keywords": keywords[:8],
                "samples": samples[:sample_per_topic],
            }
        )

    share = (doc_count / max(1, total_docs)) if total_docs > 0 else 0.0
    return {
        "doc_count": int(doc_count),
        "doc_share": float(share),
        "topic_evidence": details,
    }


def _cluster_relevance_text(cluster: Dict[str, Any], stats: Dict[str, Any]) -> str:
    parts: List[str] = []
    parts.append(str(cluster.get("cluster_name", "") or ""))
    parts.append(str(cluster.get("description", "") or ""))
    topics = cluster.get("topics")
    if isinstance(topics, list):
        parts.extend(str(t or "") for t in topics)
    evidence = stats.get("topic_evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                continue
            kws = item.get("keywords")
            if isinstance(kws, list):
                parts.extend(str(k or "") for k in kws)
            samples = item.get("samples")
            if isinstance(samples, list):
                parts.extend(str(s or "") for s in samples)
    return " ".join(parts)


HARD_RELEVANCE_AUDIT_SYSTEM = (
    "你是一个专题相关性审计器。任务是严格判定一个聚类是否与专题直接相关。"
    "只输出 JSON。"
)

HARD_RELEVANCE_AUDIT_USER = """
专题：{focus_topic}

候选聚类：
{cluster_json}

判定规则：
1. 必须基于主题样本文本、关键词和描述进行语义判定；
2. 仅当聚类与专题存在直接语义关联时才 relevant=true；
3. 泛生活/泛广告/跨域营销内容应判为 relevant=false；
4. 若证据不足，也应偏向 relevant=false。

输出 JSON：
{{
  "relevant": true/false,
  "confidence": 0.0-1.0,
  "reason": "一句话理由"
}}
"""

_SEMANTIC_EMBEDDER: Any = None


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "1", "yes", "y", "是"}:
            return True
        if token in {"false", "0", "no", "n", "否"}:
            return False
    return None


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2.0)


def _get_semantic_embedder():
    global _SEMANTIC_EMBEDDER
    if _SEMANTIC_EMBEDDER is not None:
        return _SEMANTIC_EMBEDDER
    from sentence_transformers import SentenceTransformer

    _SEMANTIC_EMBEDDER = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    return _SEMANTIC_EMBEDDER


def _build_semantic_gate(
    focus_topic: str,
    clusters: List[Dict[str, Any]],
    cluster_stats_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    focus = str(focus_topic or "").strip()
    if not focus:
        return {
            "enabled": False,
            "scores": {},
            "threshold": 0.0,
            "max_score": 0.0,
            "median_score": 0.0,
            "candidate_names": [],
        }

    names: List[str] = []
    texts: List[str] = []
    for c in clusters:
        name = str(c.get("cluster_name", "")).strip()
        if not name:
            continue
        stats = cluster_stats_map.get(name, {"topic_evidence": []})
        payload_text = _trim_text(_cluster_relevance_text(c, stats), max_chars=1200)
        if not payload_text:
            payload_text = name
        names.append(name)
        texts.append(payload_text)

    if len(names) < 3:
        return {
            "enabled": False,
            "scores": {},
            "threshold": 0.0,
            "max_score": 0.0,
            "median_score": 0.0,
            "candidate_names": [],
        }

    try:
        model = _get_semantic_embedder()
        vectors = model.encode(
            [focus] + texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception:
        return {
            "enabled": False,
            "scores": {},
            "threshold": 0.0,
            "max_score": 0.0,
            "median_score": 0.0,
            "candidate_names": [],
        }

    focus_vec = vectors[0]
    scores: Dict[str, float] = {}
    for idx, name in enumerate(names):
        vec = vectors[idx + 1]
        # Vectors are already normalized, so dot product is cosine similarity.
        score = sum(float(a) * float(b) for a, b in zip(focus_vec, vec))
        scores[name] = float(score)

    vals = list(scores.values())
    max_score = max(vals) if vals else 0.0
    median_score = _median(vals)
    # Conservative adaptive threshold: only catch low-similarity outliers.
    threshold = max(0.16, min(median_score - 0.08, max_score * 0.58))
    if threshold >= max_score:
        threshold = max(0.16, max_score * 0.8)

    ranked = sorted(scores.items(), key=lambda kv: float(kv[1]))
    low_count = max(1, int(len(ranked) * 0.34))
    candidate_names = {name for name, _ in ranked[:low_count]}
    candidate_names.update(name for name, score in ranked if float(score) <= float(threshold))

    return {
        "enabled": True,
        "scores": scores,
        "threshold": float(threshold),
        "max_score": float(max_score),
        "median_score": float(median_score),
        "candidate_names": sorted(candidate_names),
    }


def _detect_hard_offtopic_drop(
    focus_topic: str,
    cluster: Dict[str, Any],
    stats: Dict[str, Any],
    semantic_gate: Dict[str, Any],
) -> tuple[bool, str]:
    if not str(focus_topic or "").strip():
        return False, ""
    if not semantic_gate.get("enabled"):
        return False, ""

    name = str(cluster.get("cluster_name", "")).strip()
    score_map = semantic_gate.get("scores") if isinstance(semantic_gate.get("scores"), dict) else {}
    score = score_map.get(name)
    if score is None:
        return False, ""
    candidate_names = set(semantic_gate.get("candidate_names") or [])
    if candidate_names and name not in candidate_names:
        return False, ""

    threshold = _coerce_float(semantic_gate.get("threshold"), 0.0, minimum=0.0, maximum=1.0)
    max_score = _coerce_float(semantic_gate.get("max_score"), 0.0, minimum=0.0, maximum=1.0)
    # First gate: low-similarity outlier OR low-ranking candidate.
    if (float(score) > threshold) and ((max_score - float(score)) < 0.16):
        return False, ""

    payload = {
        "cluster_name": name,
        "description": str(cluster.get("description", "")).strip(),
        "topics": [str(t).strip() for t in (cluster.get("topics") or []) if str(t or "").strip()],
        "cluster_doc_count": _coerce_int(stats.get("doc_count"), 0, minimum=0),
        "cluster_doc_share": round(_coerce_float(stats.get("doc_share"), 0.0, minimum=0.0, maximum=1.0), 4),
        "topic_evidence": stats.get("topic_evidence") if isinstance(stats.get("topic_evidence"), list) else [],
    }
    prompt = HARD_RELEVANCE_AUDIT_USER.format(
        focus_topic=str(focus_topic).strip(),
        cluster_json=json.dumps(payload, ensure_ascii=False, indent=2),
    )
    audit_text = _call_llm(
        [
            {"role": "system", "content": HARD_RELEVANCE_AUDIT_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=600,
    )
    if not audit_text:
        return False, ""

    parsed = _extract_json(audit_text)
    if not isinstance(parsed, dict):
        return False, ""

    relevant = _coerce_optional_bool(parsed.get("relevant"))
    if relevant is not False:
        return False, ""

    confidence = _coerce_float(parsed.get("confidence"), 0.0, minimum=0.0, maximum=1.0)
    if confidence < 0.7:
        return False, ""

    reason = str(parsed.get("reason") or "").strip()
    if not reason:
        reason = f"硬规则丢弃：语义审计判定为无关(conf={confidence:.2f})"
    reason = f"{reason} (semantic_score={float(score):.3f}, threshold={threshold:.3f})"
    return True, reason


# ---------------------------------------------------------------------------
# Agent node: Scope Analyst
# ---------------------------------------------------------------------------

SCOPE_ANALYST_SYSTEM = (
    "你是一个主题建模专家。你的任务是根据 BERTopic 输出的主题统计信息，"
    "推荐一个合理的最大主题数上限。考虑主题的语义离散度、文档分布和关键词重叠度。"
)

SCOPE_ANALYST_USER = """
以下是 BERTopic 生成的原始主题统计（共 {n_topics} 个主题）：

{topic_summary}

用户设定的最大主题数上限为 {max_hint}。

请分析这些主题的语义分布，推荐一个合理的最终主题数范围。
仅输出 JSON，不要输出解释文字：
{{
  "recommended_max_topics": <数字>,
  "reasoning": "简要解释推荐理由"
}}
"""


def scope_analyst_node(state: ReclusterState) -> Dict[str, Any]:
    """Analyse topic stats and recommend a max_topics value."""
    topic_stats = state.get("topic_stats", [])
    max_hint = state.get("max_topics_hint", 8)
    min_floor = max(3, int(state.get("min_topics_floor", 3)))

    topic_lines = []
    for i, t in enumerate(topic_stats):
        kws = t.get("keywords", [])
        kw_text = "、".join(str(k) for k in kws[:8]) if kws else ""
        topic_lines.append(
            f"{i+1}. {t.get('topic_name', '?')} ({t.get('count', 0)} docs) 关键词: {kw_text}"
        )

    prompt = SCOPE_ANALYST_USER.format(
        n_topics=len(topic_stats),
        topic_summary="\n".join(topic_lines),
        max_hint=max_hint,
    )
    _log(state, f"Scope Analyst: 分析 {len(topic_stats)} 个原始主题...")

    result_text = _call_llm(
        [
            {"role": "system", "content": SCOPE_ANALYST_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        max_tokens=600,
    )
    if not result_text:
        _log(state, "Scope Analyst: LLM 返回为空，使用用户提示值", "warning")
        return {
            "recommended_max_topics": max_hint,
            "scope_reasoning": "LLM 未返回有效结果，使用用户设定值",
        }

    parsed = _extract_json(result_text)
    if parsed and "recommended_max_topics" in parsed:
        rec = int(parsed["recommended_max_topics"])
        rec = max(min_floor, min(rec, max_hint))  # clamp to configured bounds
        reasoning = str(parsed.get("reasoning", ""))
        _log(state, f"Scope Analyst: 推荐 max_topics={rec}  理由: {reasoning}")
        return {
            "recommended_max_topics": rec,
            "scope_reasoning": reasoning,
        }

    _log(state, "Scope Analyst: 解析失败，使用用户提示值", "warning")
    return {
        "recommended_max_topics": max_hint,
        "scope_reasoning": "解析失败，使用用户设定值",
    }


# ---------------------------------------------------------------------------
# Agent node: Cluster Strategist
# ---------------------------------------------------------------------------

CLUSTER_STRATEGIST_SYSTEM = (
    "你是一个专业的文本分析专家，擅长对主题进行归纳和聚类。"
    "你的输出必须是纯 JSON，不要输出任何解释文字。"
)

CLUSTER_STRATEGIST_USER = """
请将以下 BERTopic 主题结果合并为不超过 {max_topics} 个高层级类别。

{business_rules_hint}
{iteration_hint}

输入数据：
{input_data}

要求：
1. 优先合并语义相近、关键词重叠高的主题；
2. 每个原始主题都必须被分配到某个类别；
3. 类别名称应清晰、简洁，避免空泛词；
4. 必须结合每个主题提供的样本文本进行判断，不能只看关键词；
5. 保持一定语义发散性，避免把差异明显的主题强行合并；
6. 为每个类别写一句简短描述；
7. 仅输出 JSON。

输出 JSON 格式：
{{
  "clusters": [
    {{
      "cluster_name": "类别名称",
      "topics": ["原始主题1", "原始主题2"],
      "description": "该类别的简要描述"
    }}
  ]
}}
"""


def cluster_strategist_node(state: ReclusterState) -> Dict[str, Any]:
    """Merge raw topics into high-level clusters."""
    topic_stats = state.get("topic_stats", [])
    max_topics = state.get("recommended_max_topics", 8)
    iteration = state.get("iteration", 0)

    # Provide iteration context if retrying
    iteration_hint = ""
    if iteration > 0:
        dropped = state.get("dropped_count", 0)
        remaining = len(state.get("retained_clusters", []))
        iteration_hint = (
            f"注意：这是第 {iteration + 1} 轮迭代。上一轮聚类后有 {dropped} 个类别被判定为无关并丢弃，"
            f"剩余 {remaining} 个类别。请重新组织聚类，确保保留的类别覆盖所有相关主题。"
        )

    topic_descriptions = []
    for i, t in enumerate(topic_stats):
        kws = t.get("keywords", [])
        kw_text = "、".join(str(k) for k in kws[:10]) if kws else ""
        sample_items = t.get("samples") if isinstance(t.get("samples"), list) else []
        sample_lines: List[str] = []
        for idx, item in enumerate(sample_items[:3]):
            trimmed = _trim_text(item, 120)
            if trimmed:
                sample_lines.append(f"例{idx + 1}:{trimmed}")
        sample_text = " | ".join(sample_lines)
        if kw_text:
            line = f"{i+1}. {t.get('topic_name', '?')} ({t.get('count', 0)}篇) 关键词: {kw_text}"
        else:
            line = f"{i+1}. {t.get('topic_name', '?')} ({t.get('count', 0)}篇)"
        if sample_text:
            line = f"{line} 样本: {sample_text}"
        topic_descriptions.append(line)

    input_data = json.dumps(
        {"topics": topic_stats, "topic_list": topic_descriptions},
        ensure_ascii=False,
        indent=2,
    )

    # Construct structured business rules hint (YAML-like block)
    recluster_dimension = str(state.get("recluster_dimension") or "").strip()
    custom_topic_seeds = _normalise_label_list(
        state.get("custom_topic_seed_rules", state.get("must_separate_rules"))
    )
    must_merge = _normalise_label_list(state.get("must_merge_rules"))
    business_rules_hint = _build_business_rules_hint(
        recluster_dimension=recluster_dimension,
        custom_topic_seeds=custom_topic_seeds,
        must_merge=must_merge,
    )

    prompt_template = str(state.get("recluster_user_prompt") or CLUSTER_STRATEGIST_USER)
    prompt_values = {
        "max_topics": max_topics,
        "target_topics": max_topics,
        "TARGET_TOPICS": max_topics,
        "business_rules_hint": business_rules_hint,
        "iteration_hint": iteration_hint,
        "input_data": input_data,
        "topic_list": "\n".join(topic_descriptions),
        "topic_stats_json": json.dumps(topic_stats, ensure_ascii=False, indent=2),
        "FOCUS_TOPIC": str(state.get("focus_topic", "")).strip(),
        "focus_topic": str(state.get("focus_topic", "")).strip(),
    }
    prompt = prompt_template
    for key, val in prompt_values.items():
        prompt = prompt.replace(f"{{{key}}}", str(val))
    if business_rules_hint and "{business_rules_hint}" not in prompt_template:
        prompt = f"{prompt.rstrip()}\n\n补充业务规则（YAML）：\n{business_rules_hint}"
    if iteration_hint and "{iteration_hint}" not in prompt_template:
        prompt = f"{prompt.rstrip()}\n\n{iteration_hint}"

    system_prompt = state.get("recluster_system_prompt") or CLUSTER_STRATEGIST_SYSTEM

    _log(state, f"Cluster Strategist: 合并为 ≤{max_topics} 个类别 (iter={iteration})...")

    result_text = _call_llm(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=3600,
    )
    if not result_text:
        _log(state, "Cluster Strategist: LLM 返回为空", "error")
        return {"clusters": [], "error": "Cluster Strategist LLM 返回为空"}

    parsed = _extract_json(result_text)
    if not parsed:
        _log(state, "Cluster Strategist: 无法解析 JSON", "error")
        return {"clusters": [], "error": "Cluster Strategist JSON 解析失败"}

    clusters = parsed.get("clusters", [])
    if not isinstance(clusters, list):
        clusters = []

    normalised = []
    for c in clusters:
        if not isinstance(c, dict):
            continue
        normalised.append({
            "cluster_name": str(c.get("cluster_name", "")).strip(),
            "topics": [str(t).strip() for t in (c.get("topics") or []) if str(t or "").strip()],
            "description": str(c.get("description", "")).strip(),
        })

    _log(state, f"Cluster Strategist: 生成 {len(normalised)} 个聚类")
    return {"clusters": normalised}


# ---------------------------------------------------------------------------
# Agent node: Relevance Judge
# ---------------------------------------------------------------------------

RELEVANCE_JUDGE_SYSTEM = (
    "你是一个信息相关性判定专家。你需要严格评估每个主题类别是否与指定专题相关。"
    "仅输出 JSON，不要输出任何解释文字。"
)

RELEVANCE_JUDGE_USER = """
专题名称：{focus_topic}

{drop_rule}

判定注意事项：
1. 必须优先阅读 topic_evidence 中每个原始主题的多条样本文本后再判定；
2. 只有在“样本文本 + 关键词 + 描述”都显示明显无关时才可 drop=true；
3. 对文档量大的聚类要谨慎：当 cluster_doc_count 很高或 cluster_doc_share 较高时，默认不应丢弃；
4. 输出必须覆盖每个 cluster_name，不得遗漏。

以下是待评审的主题聚类列表：
{clusters_json}

请为每个聚类判定是否应该丢弃（drop）。仅输出 JSON：
{{
  "clusters": [
    {{
      "cluster_name": "类别名称",
      "drop": true/false,
      "drop_reason": "丢弃理由（仅 drop=true 时需要）"
    }}
  ]
}}
"""


def relevance_judge_node(state: ReclusterState) -> Dict[str, Any]:
    """Judge each cluster for relevance, marking irrelevant ones for drop."""
    clusters = state.get("clusters", [])
    focus_topic = state.get("focus_topic", "")
    
    core_drop = _normalise_label_list(state.get("core_drop_rules"))
    base_drop_rule = str(state.get("drop_rule_prompt", "") or "")
    if core_drop:
        drop_rule = "【核心降噪指令】\n" + "\n".join(f"- {r}" for r in core_drop) + "\n\n【辅助参数说明】\n" + base_drop_rule
    else:
        drop_rule = base_drop_rule

    min_floor = max(3, int(state.get("min_topics_floor", 3)))
    topic_lookup, total_topic_docs = _build_topic_lookup(state.get("topic_stats", []))
    sample_per_topic = _coerce_int(
        state.get("judge_sample_per_topic"),
        DEFAULT_JUDGE_SAMPLE_PER_TOPIC,
        minimum=2,
        maximum=6,
    )
    large_share_threshold = _coerce_float(
        state.get("large_cluster_doc_share"),
        DEFAULT_LARGE_CLUSTER_DOC_SHARE,
        minimum=0.01,
        maximum=0.9,
    )
    configured_large_count = _coerce_int(
        state.get("large_cluster_doc_count"),
        0,
        minimum=0,
    )
    inferred_large_count = int(total_topic_docs * large_share_threshold) if total_topic_docs > 0 else 0
    large_count_threshold = configured_large_count if configured_large_count > 0 else inferred_large_count
    max_drop_ratio = _coerce_float(
        state.get("max_drop_ratio"),
        DEFAULT_MAX_DROP_RATIO,
        minimum=0.0,
        maximum=0.9,
    )

    if not clusters:
        return {"judged_clusters": [], "retained_clusters": [], "dropped_count": 0}

    clusters_for_judge = []
    cluster_stats_map: Dict[str, Dict[str, Any]] = {}
    for c in clusters:
        name = str(c.get("cluster_name", "")).strip()
        stats = _cluster_doc_stats(c, topic_lookup, total_topic_docs, sample_per_topic)
        if name:
            cluster_stats_map[name] = stats
        clusters_for_judge.append(
            {
                "cluster_name": name,
                "topics": c.get("topics", []),
                "description": c.get("description", ""),
                "cluster_doc_count": stats["doc_count"],
                "cluster_doc_share": round(stats["doc_share"], 4),
                "topic_evidence": stats["topic_evidence"],
            }
        )

    # Apply variable substitution to drop rule
    rendered_drop_rule = drop_rule.replace("{FOCUS_TOPIC}", focus_topic).replace(
        "{focus_topic}", focus_topic
    )

    prompt = RELEVANCE_JUDGE_USER.format(
        focus_topic=focus_topic,
        drop_rule=rendered_drop_rule,
        clusters_json=json.dumps(clusters_for_judge, ensure_ascii=False, indent=2),
    )

    _log(state, f"Relevance Judge: 评审 {len(clusters)} 个聚类...")
    _log(
        state,
        (
            "Relevance Judge: 判定阈值 "
            f"large_share>={large_share_threshold:.2%}, "
            f"large_count>={large_count_threshold}, "
            f"max_drop_ratio<={max_drop_ratio:.0%}"
        ),
    )

    result_text = _call_llm(
        [
            {"role": "system", "content": RELEVANCE_JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2600,
    )

    if not result_text:
        _log(state, "Relevance Judge: LLM 返回为空，保留全部聚类", "warning")
        judged = []
        for c in clusters:
            name = str(c.get("cluster_name", "")).strip()
            stats = cluster_stats_map.get(name, {"doc_count": 0, "doc_share": 0.0})
            judged.append(
                {
                    **c,
                    "drop": False,
                    "drop_reason": "",
                    "doc_count": int(stats.get("doc_count", 0)),
                    "doc_share": float(stats.get("doc_share", 0.0)),
                }
            )
        return {"judged_clusters": judged, "retained_clusters": judged, "dropped_count": 0}

    parsed = _extract_json(result_text)
    if not parsed:
        _log(state, "Relevance Judge: JSON 解析失败，保留全部聚类", "warning")
        judged = []
        for c in clusters:
            name = str(c.get("cluster_name", "")).strip()
            stats = cluster_stats_map.get(name, {"doc_count": 0, "doc_share": 0.0})
            judged.append(
                {
                    **c,
                    "drop": False,
                    "drop_reason": "",
                    "doc_count": int(stats.get("doc_count", 0)),
                    "doc_share": float(stats.get("doc_share", 0.0)),
                }
            )
        return {"judged_clusters": judged, "retained_clusters": judged, "dropped_count": 0}

    judge_results = parsed.get("clusters", [])
    if not isinstance(judge_results, list):
        judge_results = []

    # Build a lookup from judge results
    drop_map: Dict[str, Dict] = {}
    for jr in judge_results:
        if isinstance(jr, dict):
            name = str(jr.get("cluster_name", "")).strip()
            if name:
                drop_map[name] = jr

    semantic_gate = _build_semantic_gate(focus_topic, clusters, cluster_stats_map)
    if semantic_gate.get("enabled"):
        score_map = semantic_gate.get("scores") if isinstance(semantic_gate.get("scores"), dict) else {}
        low_preview = ", ".join(
            f"{k}:{float(v):.3f}"
            for k, v in sorted(score_map.items(), key=lambda kv: float(kv[1]))[:3]
        )
        _log(
            state,
            (
                "Relevance Judge: 语义门限 "
                f"score<={float(semantic_gate.get('threshold', 0.0)):.3f} "
                f"(median={float(semantic_gate.get('median_score', 0.0)):.3f}, "
                f"max={float(semantic_gate.get('max_score', 0.0)):.3f}); "
                f"lowest={low_preview}"
            ),
        )

    retained = []
    dropped = 0
    judged = []
    for c in clusters:
        name = str(c.get("cluster_name", "")).strip()
        judge_info = drop_map.get(name, {})
        is_drop = False
        drop_reason = ""
        hard_drop = False
        stats = cluster_stats_map.get(name, {"doc_count": 0, "doc_share": 0.0})
        doc_count = _coerce_int(stats.get("doc_count"), 0, minimum=0)
        doc_share = _coerce_float(stats.get("doc_share"), 0.0, minimum=0.0, maximum=1.0)

        # Parse drop flag
        drop_val = judge_info.get("drop")
        if isinstance(drop_val, bool):
            is_drop = drop_val
        elif isinstance(drop_val, str):
            is_drop = drop_val.lower().strip() in ("true", "yes", "是")

        # Deterministic off-topic guard for obvious cross-domain noise.
        force_drop, force_reason = _detect_hard_offtopic_drop(
            focus_topic,
            c,
            stats,
            semantic_gate,
        )
        if force_drop:
            is_drop = True
            hard_drop = True
            drop_reason = force_reason

        # High-volume safeguard: large clusters should not be dropped lightly.
        if is_drop and (not hard_drop) and (
            doc_share >= large_share_threshold
            or (large_count_threshold > 0 and doc_count >= large_count_threshold)
        ):
            is_drop = False
            drop_reason = (
                "保留：触发大主题保护"
                f"(doc_count={doc_count}, share={doc_share:.2%})"
            )

        if is_drop and not drop_reason:
            drop_reason = str(judge_info.get("drop_reason", "模型判定为无关")).strip()
        if is_drop:
            dropped += 1

        entry = {
            **c,
            "drop": is_drop,
            "hard_drop": hard_drop,
            "drop_reason": drop_reason,
            "doc_count": doc_count,
            "doc_share": doc_share,
        }
        judged.append(entry)
        if not is_drop:
            retained.append(entry)

    # Guardrail: prevent dropping too many clusters in a single run.
    allowed_drop = int(len(judged) * max_drop_ratio)
    drop_indices = [idx for idx, item in enumerate(judged) if item.get("drop")]
    if len(drop_indices) > allowed_drop:
        restore_needed = len(drop_indices) - allowed_drop
        soft_drop_indices = [idx for idx in drop_indices if not judged[idx].get("hard_drop")]
        for idx in sorted(soft_drop_indices, key=lambda i: judged[i].get("doc_count", 0), reverse=True)[:restore_needed]:
            judged[idx]["drop"] = False
            judged[idx]["drop_reason"] = "保留：触发最大丢弃比例约束"
        retained = [item for item in judged if not item.get("drop")]
        dropped = sum(1 for item in judged if item.get("drop"))
        _log(state, f"Relevance Judge: 触发最大丢弃比例约束，max_drop_ratio={max_drop_ratio:.0%}")

    # Enforce a hard floor so downstream report never collapses to too few topics.
    if len(retained) < min_floor:
        needed = min_floor - len(retained)
        non_hard_drop_indices = [idx for idx, item in enumerate(judged) if item.get("drop") and not item.get("hard_drop")]
        for idx in sorted(non_hard_drop_indices, key=lambda i: judged[i].get("doc_count", 0), reverse=True):
            if needed <= 0:
                break
            restored = {
                **judged[idx],
                "drop": False,
                "drop_reason": "保底保留：触发最小主题数约束",
            }
            judged[idx] = restored
            retained.append(restored)
            needed -= 1
        if needed > 0:
            hard_drop_indices = [idx for idx, item in enumerate(judged) if item.get("drop") and item.get("hard_drop")]
            for idx in sorted(hard_drop_indices, key=lambda i: judged[i].get("doc_count", 0), reverse=True):
                if needed <= 0:
                    break
                restored = {
                    **judged[idx],
                    "drop": False,
                    "hard_drop": False,
                    "drop_reason": "保底保留：触发最小主题数约束（硬丢弃回补）",
                }
                judged[idx] = restored
                retained.append(restored)
                needed -= 1
        dropped = sum(1 for item in judged if item.get("drop"))
        _log(state, f"Relevance Judge: 触发保底保留，最小主题数={min_floor}")

    _log(state, f"Relevance Judge: 保留 {len(retained)}, 丢弃 {dropped}")
    return {
        "judged_clusters": judged,
        "retained_clusters": retained,
        "dropped_count": dropped,
    }


# ---------------------------------------------------------------------------
# Agent node: Naming & Keywords
# ---------------------------------------------------------------------------

NAMING_KEYWORDS_SYSTEM = "你是一个专业的文本分析专家，擅长为主题类别生成精炼的名称和关键词。"

NAMING_KEYWORDS_USER = """
为以下主题类别生成 5-8 个核心关键词：

类别名称：{cluster_name}
包含主题：{topics}
描述：{description}

请直接输出关键词列表，使用逗号分隔，不要输出额外说明。
"""


def naming_keywords_node(state: ReclusterState) -> Dict[str, Any]:
    """Generate final names and keywords for retained clusters."""
    retained = state.get("retained_clusters", [])
    keyword_system = state.get("keyword_system_prompt") or NAMING_KEYWORDS_SYSTEM
    keyword_user_tpl = state.get("keyword_user_prompt") or NAMING_KEYWORDS_USER

    if not retained:
        return {"final_clusters": []}

    _log(state, f"Naming & Keywords: 为 {len(retained)} 个聚类生成关键词...")

    import re

    final = []
    for c in retained:
        topics_list = c.get("topics", [])
        topics_text = "、".join(str(t) for t in topics_list if str(t or "").strip())
        description = str(c.get("description", "")).strip()

        # Render keyword prompt template
        prompt = keyword_user_tpl
        for key, val in {
            "cluster_name": c.get("cluster_name", ""),
            "topics": topics_text,
            "topics_csv": ", ".join(str(t) for t in topics_list),
            "topics_json": json.dumps(topics_list, ensure_ascii=False),
            "description": description,
        }.items():
            prompt = prompt.replace(f"{{{key}}}", str(val))

        try:
            kw_text = _call_llm(
                [
                    {"role": "system", "content": keyword_system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
            )
            if kw_text:
                keywords = [
                    w.strip() for w in re.split(r"[,\n，、;；]+", kw_text) if w.strip()
                ][:8]
            else:
                keywords = []
        except Exception as exc:
            _log(state, f"Naming & Keywords: 关键词生成失败 ({c.get('cluster_name')}): {exc}", "error")
            keywords = []

        final.append({
            **c,
            "keywords": keywords,
        })

    _log(state, f"Naming & Keywords: 完成 {len(final)} 个聚类的关键词生成")
    return {"final_clusters": final}


# ---------------------------------------------------------------------------
# Agent node: Custom Filter Judge
# ---------------------------------------------------------------------------

CUSTOM_FILTER_JUDGE_SYSTEM = (
    "你是一个内容筛选专家。你需要严格评估每个主题聚类是否匹配用户指定的排除规则。"
    "仅输出 JSON，不要输出任何解释文字。"
)

CUSTOM_FILTER_JUDGE_USER = """
用户定义了一条排除规则：
类别：{filter_category}
描述/关键词：{filter_description}

请逐一审查以下主题聚类，判断每个聚类的内容（包括名称、描述、子主题名称和关键词）
是否属于上述排除类别。

判定要点：
1. 仔细阅读每个聚类的 cluster_name、description、topics 列表和 topic_evidence 中的关键词与样本；
2. 如果聚类的核心内容属于排除类别所描述的范畴，则 match=true；
3. 仅当聚类与排除规则有明确语义关联时才 match=true，不要过度扩大范围；
4. 覆盖所有聚类，不得遗漏。

待审查聚类：
{clusters_json}

输出 JSON：
{{
  "results": [
    {{
      "cluster_name": "聚类名称",
      "match": true/false,
      "reason": "判定理由"
    }}
  ]
}}
"""


def custom_filter_judge_node(state: ReclusterState) -> Dict[str, Any]:
    """Apply user-defined custom filters, one LLM call per filter rule."""
    custom_filters = _resolve_custom_filters(state)

    retained = list(state.get("retained_clusters") or [])
    judged = list(state.get("judged_clusters") or [])

    if not custom_filters or not retained:
        return {}  # Nothing to do

    topic_lookup, total_topic_docs = _build_topic_lookup(state.get("topic_stats", []))
    sample_per_topic = _coerce_int(
        state.get("judge_sample_per_topic"),
        DEFAULT_JUDGE_SAMPLE_PER_TOPIC,
        minimum=2,
        maximum=6,
    )
    large_share_threshold = _coerce_float(
        state.get("large_cluster_doc_share"),
        DEFAULT_LARGE_CLUSTER_DOC_SHARE,
        minimum=0.01,
        maximum=0.9,
    )

    total_filtered = 0

    for f_idx, filter_rule in enumerate(custom_filters):
        cat = str(filter_rule.get("category") or "").strip()
        desc = str(filter_rule.get("description") or "").strip()
        if not cat and not desc:
            continue

        filter_label = cat or desc
        _log(state, f"Custom Filter [{f_idx + 1}/{len(custom_filters)}]: 评估规则「{filter_label}」对 {len(retained)} 个聚类...")

        # Build cluster info for this filter evaluation
        clusters_for_filter = []
        for c in retained:
            name = str(c.get("cluster_name", "")).strip()
            stats = _cluster_doc_stats(c, topic_lookup, total_topic_docs, sample_per_topic)
            clusters_for_filter.append({
                "cluster_name": name,
                "topics": c.get("topics", []),
                "description": c.get("description", ""),
                "cluster_doc_count": stats["doc_count"],
                "cluster_doc_share": round(stats["doc_share"], 4),
                "topic_evidence": stats["topic_evidence"],
            })

        prompt = CUSTOM_FILTER_JUDGE_USER.format(
            filter_category=cat or "(未指定)",
            filter_description=desc or "(未指定)",
            clusters_json=json.dumps(clusters_for_filter, ensure_ascii=False, indent=2),
        )

        result_text = _call_llm(
            [
                {"role": "system", "content": CUSTOM_FILTER_JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2600,
        )

        if not result_text:
            _log(state, f"Custom Filter [{f_idx + 1}]: LLM 返回为空，跳过此规则", "warning")
            continue

        parsed = _extract_json(result_text)
        if not parsed:
            _log(state, f"Custom Filter [{f_idx + 1}]: JSON 解析失败，跳过此规则", "warning")
            continue

        results = parsed.get("results", [])
        if not isinstance(results, list):
            continue

        # Build match lookup
        match_map: Dict[str, Dict] = {}
        for item in results:
            if isinstance(item, dict):
                name = str(item.get("cluster_name", "")).strip()
                if name:
                    match_map[name] = item

        # Apply filter results
        filter_dropped = 0
        new_retained = []
        for c in retained:
            name = str(c.get("cluster_name", "")).strip()
            match_info = match_map.get(name, {})
            is_match = False
            match_val = match_info.get("match")
            if isinstance(match_val, bool):
                is_match = match_val
            elif isinstance(match_val, str):
                is_match = match_val.lower().strip() in ("true", "yes", "是")

            if is_match:
                # Large-cluster safeguard: don't drop high-volume clusters
                doc_share = _coerce_float(c.get("doc_share"), 0.0, minimum=0.0, maximum=1.0)
                if doc_share >= large_share_threshold:
                    _log(
                        state,
                        f"Custom Filter [{f_idx + 1}]: 保留「{name}」（大主题保护, share={doc_share:.2%}）",
                    )
                    new_retained.append(c)
                    continue

                reason = str(match_info.get("reason") or "").strip()
                drop_reason = f"自定义筛选「{filter_label}」: {reason}" if reason else f"自定义筛选「{filter_label}」命中"
                # Update in judged_clusters
                for j_idx, jc in enumerate(judged):
                    if str(jc.get("cluster_name", "")).strip() == name:
                        judged[j_idx] = {
                            **jc,
                            "drop": True,
                            "drop_reason": drop_reason,
                            "custom_filter_matched": filter_label,
                        }
                        break
                filter_dropped += 1
                total_filtered += 1
            else:
                new_retained.append(c)

        retained = new_retained
        _log(state, f"Custom Filter [{f_idx + 1}]: 规则「{filter_label}」过滤掉 {filter_dropped} 个聚类，剩余 {len(retained)}")

        if not retained:
            _log(state, "Custom Filter: 所有聚类已被过滤，终止后续规则", "warning")
            break

    if total_filtered > 0:
        _log(state, f"Custom Filter: 共过滤 {total_filtered} 个聚类，最终保留 {len(retained)}")

    return {
        "retained_clusters": retained,
        "judged_clusters": judged,
        "dropped_count": sum(1 for c in judged if c.get("drop")),
    }


# ---------------------------------------------------------------------------
# Supervisor routing
# ---------------------------------------------------------------------------

def _post_judge_router(state: ReclusterState) -> str:
    """Three-way router after relevance_judge.

    Returns:
        'retry'          – too few clusters, loop back to strategist
        'apply_filters'  – proceed with user-defined custom filters
        'skip_filters'   – no custom filters, go straight to naming
    """
    # 1. Check whether we should retry the strategist→judge loop
    iteration = state.get("iteration", 0)
    retained = state.get("retained_clusters", [])
    recommended = state.get("recommended_max_topics", 8)
    min_floor = max(3, int(state.get("min_topics_floor", 3)))
    threshold = max(min_floor, recommended // 2)

    if (iteration + 1) < MAX_ITERATIONS and len(retained) < threshold:
        _log(state, f"Supervisor: retained={len(retained)} < threshold={threshold}, retrying (iter={iteration})")
        return "retry"

    # 2. Check whether custom filters are defined
    valid = _resolve_custom_filters(state)
    if valid:
        _log(state, f"Supervisor: {len(valid)} 条自定义筛选规则待执行，进入 Custom Filter Judge")
        return "apply_filters"

    return "skip_filters"


def _increment_iteration(state: ReclusterState) -> Dict[str, Any]:
    return {"iteration": state.get("iteration", 0) + 1}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_recluster_graph():
    """Build and compile the multi-agent StateGraph for BERTopic re-clustering.

    Graph topology:
        Phase 1 – Analysis:     scope_analyst
        Phase 2 – Clustering:   cluster_strategist ⇄ relevance_judge (iterative)
        Phase 3 – Filtering:    custom_filter_judge (conditional, skipped if no rules)
        Phase 4 – Finalisation: naming_keywords → END
    """
    ensure_langchain_uuid_compat()
    try:
        from langgraph.graph import StateGraph, END
    except ImportError as exc:
        raise ImportError(
            "langgraph is required for multi-agent re-clustering. "
            "Install it with: pip install langgraph>=0.2.0"
        ) from exc

    graph = StateGraph(ReclusterState)

    # ── Register all agent nodes ──────────────────────────────────────────
    graph.add_node("scope_analyst", scope_analyst_node)
    graph.add_node("cluster_strategist", cluster_strategist_node)
    graph.add_node("relevance_judge", relevance_judge_node)
    graph.add_node("custom_filter_judge", custom_filter_judge_node)
    graph.add_node("naming_keywords", naming_keywords_node)
    graph.add_node("increment_iteration", _increment_iteration)

    # ── Phase 1: scope analysis ───────────────────────────────────────────
    graph.set_entry_point("scope_analyst")
    graph.add_edge("scope_analyst", "cluster_strategist")

    # ── Phase 2: iterative clustering + relevance judging ─────────────────
    graph.add_edge("cluster_strategist", "relevance_judge")
    graph.add_conditional_edges(
        "relevance_judge",
        _post_judge_router,
        {
            "retry":         "increment_iteration",
            "apply_filters": "custom_filter_judge",
            "skip_filters":  "naming_keywords",
        },
    )
    graph.add_edge("increment_iteration", "cluster_strategist")

    # ── Phase 3: custom filters → naming ──────────────────────────────────
    graph.add_edge("custom_filter_judge", "naming_keywords")

    # ── Phase 4: final naming ─────────────────────────────────────────────
    graph.add_edge("naming_keywords", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_multi_agent_recluster(
    topic_stats: List[Dict[str, Any]],
    focus_topic: str,
    prompt_config: Optional[Dict[str, Any]] = None,
    logger: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Run the multi-agent BERTopic re-clustering pipeline.

    Returns a dict with:
      - "clusters": final cluster list with keywords
      - "dropped": list of dropped clusters
      - "scope_reasoning": why the max_topics was chosen
      - "iterations": how many rounds were needed
    """
    config = prompt_config or {}

    # Resolve max_topics from config
    try:
        max_topics = int(config.get("max_topics") or config.get("target_topics", 8))
    except (TypeError, ValueError):
        max_topics = 8
    max_topics = max(3, min(50, max_topics))
    try:
        min_topics = int(config.get("min_topics", 3))
    except (TypeError, ValueError):
        min_topics = 3
    min_topics = max(3, min(max_topics, min_topics))
    judge_sample_per_topic = _coerce_int(
        config.get("judge_sample_per_topic", config.get("topic_sample_size", DEFAULT_JUDGE_SAMPLE_PER_TOPIC)),
        DEFAULT_JUDGE_SAMPLE_PER_TOPIC,
        minimum=2,
        maximum=6,
    )
    large_cluster_doc_share = _coerce_float(
        config.get("large_cluster_doc_share", DEFAULT_LARGE_CLUSTER_DOC_SHARE),
        DEFAULT_LARGE_CLUSTER_DOC_SHARE,
        minimum=0.01,
        maximum=0.9,
    )
    large_cluster_doc_count = _coerce_int(
        config.get("large_cluster_doc_count", 0),
        0,
        minimum=0,
    )
    max_drop_ratio = _coerce_float(
        config.get("max_drop_ratio", DEFAULT_MAX_DROP_RATIO),
        DEFAULT_MAX_DROP_RATIO,
        minimum=0.0,
        maximum=0.9,
    )

    from .prompt_config import (
        DEFAULT_DROP_RULE_PROMPT,
        DEFAULT_GLOBAL_FILTERS,
        DEFAULT_RECLUSTER_SYSTEM_PROMPT,
        DEFAULT_RECLUSTER_USER_PROMPT,
        DEFAULT_KEYWORDS_SYSTEM_PROMPT,
        DEFAULT_KEYWORDS_USER_PROMPT,
    )

    raw_global_filters = config.get("global_filters") if "global_filters" in config else DEFAULT_GLOBAL_FILTERS
    global_filters = _normalise_label_list(raw_global_filters)
    raw_project_filters = config.get("project_filters")
    if raw_project_filters is None:
        raw_project_filters = config.get("custom_filters")
    project_filters = _normalise_filter_items(raw_project_filters)
    legacy_filters = _normalise_filter_items(config.get("custom_filters"))
    core_drop_rules = _normalise_label_list(
        config.get("core_drop_rules", config.get("relevance_rules", []))
    )
    custom_topic_seed_rules = _normalise_label_list(
        config.get("custom_topic_seed_rules", config.get("must_separate_rules"))
    )
    must_merge_rules = _normalise_label_list(config.get("must_merge_rules"))

    initial_state: ReclusterState = {
        "topic_stats": topic_stats,
        "focus_topic": focus_topic,
        "max_topics_hint": max_topics,
        "min_topics_floor": min_topics,
        "drop_rule_prompt": str(config.get("drop_rule_prompt") or DEFAULT_DROP_RULE_PROMPT),
        "recluster_system_prompt": str(config.get("recluster_system_prompt") or DEFAULT_RECLUSTER_SYSTEM_PROMPT),
        "recluster_user_prompt": str(config.get("recluster_user_prompt") or DEFAULT_RECLUSTER_USER_PROMPT),
        "keyword_system_prompt": str(config.get("keyword_system_prompt") or DEFAULT_KEYWORDS_SYSTEM_PROMPT),
        "keyword_user_prompt": str(config.get("keyword_user_prompt") or DEFAULT_KEYWORDS_USER_PROMPT),
        "recluster_dimension": str(config.get("recluster_dimension") or ""),
        "must_separate_rules": custom_topic_seed_rules,
        "custom_topic_seed_rules": custom_topic_seed_rules,
        "must_merge_rules": must_merge_rules,
        "core_drop_rules": core_drop_rules,
        "judge_sample_per_topic": judge_sample_per_topic,
        "large_cluster_doc_share": large_cluster_doc_share,
        "large_cluster_doc_count": large_cluster_doc_count,
        "max_drop_ratio": max_drop_ratio,
        "global_filters": global_filters,
        "project_filters": project_filters,
        "custom_filters": legacy_filters,
        "logger": logger,
        "iteration": 0,
        "recommended_max_topics": max_topics,
        "scope_reasoning": "",
        "clusters": [],
        "judged_clusters": [],
        "retained_clusters": [],
        "dropped_count": 0,
        "final_clusters": [],
        "error": "",
    }

    app = build_recluster_graph()
    final_state = app.invoke(initial_state)

    # Collect results
    final_clusters = final_state.get("final_clusters", [])
    judged = final_state.get("judged_clusters", [])
    dropped_clusters = [c for c in judged if c.get("drop")]

    return {
        "clusters": final_clusters,
        "dropped": dropped_clusters,
        "scope_reasoning": final_state.get("scope_reasoning", ""),
        "recommended_max_topics": final_state.get("recommended_max_topics", max_topics),
        "iterations": final_state.get("iteration", 0) + 1,
    }
