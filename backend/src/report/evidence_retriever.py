from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
import pickle
import re
from threading import RLock
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from ..utils.setting.paths import bucket, get_data_root


_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,16}")
_NEGATION_HINTS = ("辟谣", "不实", "并非", "未发布", "网传", "谣言", "假的", "误读", "未经证实")
_POLICY_HINTS = ("控烟", "禁烟", "无烟", "二手烟", "吸烟", "戒烟", "烟草", "公共场所", "卫健委", "条例", "执法")
_POLICY_CONTEXT_HINTS = ("政策", "通知", "条例", "卫健委", "公共场所", "控烟", "禁烟", "执法", "宣传", "健康", "二手烟")
_KITCHEN_NOISE_HINTS = ("厨房", "油烟", "油烟机", "抽油烟", "灶台", "做饭", "烟灶", "神器")
_RETRIEVAL_CACHE_VERSION = 1
_CORPUS_CACHE_FILENAME = "retrieval_corpus.pkl"
_EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_CORPUS_CACHE_LOCK = RLock()
_CORPUS_CACHE_MEMO: Dict[str, Dict[str, Any]] = {}
_EMBEDDING_MODEL: Any = None


def _extract_date_text(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    matched = re.search(r"(20\d{2}-\d{2}-\d{2})", raw)
    return matched.group(1) if matched else ""


def _extract_date_obj(value: Any) -> Optional[datetime]:
    date_text = _extract_date_text(value)
    if not date_text:
        return None
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except Exception:
        return None


def _tokenize(text: Any, *, max_items: int = 18) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    tokens: List[str] = []
    seen = set()
    for token in _TOKEN_RE.findall(raw):
        cleaned = str(token or "").strip()
        if len(cleaned) < 2:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(cleaned)
        if len(tokens) >= max_items:
            break
    return tokens


def _normalise_platforms(platforms: Any) -> List[str]:
    if not isinstance(platforms, list):
        return []
    return [str(item).strip() for item in platforms if str(item or "").strip()]


def _normalise_terms(values: Any, *, max_items: int = 18) -> List[str]:
    if not isinstance(values, list):
        return []
    result: List[str] = []
    seen = set()
    for item in values:
        token = str(item or "").strip()
        if len(token) < 2:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
        if len(result) >= max_items:
            break
    return result


def _build_query_terms(query: str, entities: Optional[List[str]] = None, *, max_items: int = 18) -> List[str]:
    entity_terms = _normalise_terms(entities, max_items=max_items)
    seen = {item.lower() for item in entity_terms}
    output = list(entity_terms)
    for token in _tokenize(query, max_items=max_items):
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(token)
        if len(output) >= max_items:
            break
    return output[:max_items]


def _within_range(date_text: str, start: str = "", end: str = "") -> bool:
    if start and date_text and date_text < start:
        return False
    if end and date_text and date_text > end:
        return False
    return True


def _parse_fetch_range(folder_name: str) -> Tuple[str, str]:
    text = str(folder_name or "").strip()
    if "_" in text:
        start, end = text.split("_", 1)
        return _extract_date_text(start), _extract_date_text(end)
    single = _extract_date_text(text)
    return single, single


def _compose_range_folder(start: str, end: str) -> str:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip()
    return f"{start_text}_{end_text}" if end_text and end_text != start_text else start_text


def _fetch_root(topic_identifier: str) -> Path:
    return get_data_root() / "projects" / topic_identifier / "fetch"


def _date_distance_days(left: Optional[datetime], right: Optional[datetime]) -> int:
    if left is None or right is None:
        return 10**9
    return abs((left - right).days)


def _resolve_source_bundle(topic_identifier: str, start: str, end: str) -> Dict[str, Any]:
    request_start_text = _extract_date_text(start)
    request_end_text = _extract_date_text(end or start)
    folder = f"{start}_{end}" if end and end != start else start
    exact = bucket("fetch", topic_identifier, folder) / "总体.jsonl"
    if exact.exists():
        return {
            "files": [exact],
            "source_resolution": "exact_fetch_range",
            "resolved_fetch_range": {"start": request_start_text, "end": request_end_text or request_start_text},
            "partial_range_coverage": False,
        }

    request_start = _extract_date_obj(start)
    request_end = _extract_date_obj(end or start)
    covering: List[Tuple[int, str, str, Path]] = []
    overlap: List[Tuple[int, int, int, str, str, Path]] = []
    root = _fetch_root(topic_identifier)
    if root.exists() and root.is_dir() and request_start and request_end:
        for item in root.iterdir():
            if not item.is_dir():
                continue
            range_start, range_end = _parse_fetch_range(item.name)
            start_dt = _extract_date_obj(range_start)
            end_dt = _extract_date_obj(range_end)
            overall = item / "总体.jsonl"
            if not overall.exists() or start_dt is None or end_dt is None:
                continue
            if start_dt <= request_start and end_dt >= request_end:
                covering.append((max(0, (end_dt - start_dt).days), range_start, range_end, overall))
                continue
            overlap_start = max(start_dt, request_start)
            overlap_end = min(end_dt, request_end)
            if overlap_start <= overlap_end:
                overlap_days = max(0, (overlap_end - overlap_start).days) + 1
                boundary_distance = _date_distance_days(start_dt, request_start) + _date_distance_days(end_dt, request_end)
                coverage_span = max(0, (end_dt - start_dt).days)
                overlap.append((overlap_days, boundary_distance, coverage_span, range_start, range_end, overall))
    if covering:
        covering.sort(key=lambda item: (item[0], item[1], item[2], str(item[3])))
        best = covering[0]
        return {
            "files": [best[3]],
            "source_resolution": "covering_fetch_range",
            "resolved_fetch_range": {"start": best[1], "end": best[2]},
            "partial_range_coverage": False,
        }
    if overlap:
        overlap.sort(key=lambda item: (-item[0], item[1], item[2], item[3], item[4], str(item[5])))
        best = overlap[0]
        return {
            "files": [best[5]],
            "source_resolution": "overlap_fetch_range",
            "resolved_fetch_range": {"start": best[3], "end": best[4]},
            "partial_range_coverage": True,
        }

    uploads_dir = get_data_root() / "projects" / topic_identifier / "uploads" / "jsonl"
    uploads = sorted([path for path in uploads_dir.glob("*.jsonl") if path.is_file()]) if uploads_dir.exists() else []
    if uploads:
        return {
            "files": uploads,
            "source_resolution": "uploads_jsonl",
            "resolved_fetch_range": {"start": "", "end": ""},
            "partial_range_coverage": False,
        }
    return {
        "files": [],
        "source_resolution": "unavailable",
        "resolved_fetch_range": {"start": "", "end": ""},
        "partial_range_coverage": False,
    }


def resolve_source_scope(topic_identifier: str, start: str, end: str) -> Dict[str, Any]:
    bundle = _resolve_source_bundle(topic_identifier, start, end)
    return {
        "source_files": [str(path) for path in bundle.get("files") or []],
        "source_resolution": str(bundle.get("source_resolution") or "").strip(),
        "resolved_fetch_range": dict(bundle.get("resolved_fetch_range") or {}),
        "partial_range_coverage": bool(bundle.get("partial_range_coverage")),
    }


def _resolve_source_files(topic_identifier: str, start: str, end: str) -> Tuple[List[Path], str]:
    bundle = _resolve_source_bundle(topic_identifier, start, end)
    return list(bundle.get("files") or []), str(bundle.get("source_resolution") or "").strip()


def _build_source_fingerprint(source_files: Sequence[Path], source_resolution: str) -> str:
    payload: List[Dict[str, Any]] = []
    for file_path in source_files:
        try:
            stat = file_path.stat()
            payload.append(
                {
                    "path": str(file_path.resolve()),
                    "mtime_ns": int(stat.st_mtime_ns),
                    "size": int(stat.st_size),
                }
            )
        except Exception:
            payload.append({"path": str(file_path), "mtime_ns": 0, "size": 0})
    raw = json.dumps(
        {
            "version": _RETRIEVAL_CACHE_VERSION,
            "source_resolution": str(source_resolution or "").strip(),
            "files": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _retrieval_cache_root(topic_identifier: str, start: str, end: str) -> Path:
    cache_root = bucket("reports", topic_identifier, _compose_range_folder(start, end)) / "retrieval_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def _corpus_cache_key(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    platforms: Sequence[str],
    time_start: str,
    time_end: str,
    source_files: Sequence[Path],
    source_resolution: str,
) -> str:
    payload = {
        "version": _RETRIEVAL_CACHE_VERSION,
        "topic_identifier": str(topic_identifier or "").strip(),
        "start": str(start or "").strip(),
        "end": str(end or "").strip(),
        "platforms": sorted(str(item or "").strip() for item in platforms if str(item or "").strip()),
        "time_start": str(time_start or "").strip(),
        "time_end": str(time_end or "").strip(),
        "source_fingerprint": _build_source_fingerprint(source_files, source_resolution),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _corpus_cache_path(topic_identifier: str, start: str, end: str, cache_key: str) -> Path:
    return _retrieval_cache_root(topic_identifier, start, end) / cache_key / _CORPUS_CACHE_FILENAME


def _build_tfidf_index(docs: Sequence[str]) -> Tuple[Optional[TfidfVectorizer], Any]:
    if not docs:
        return None, None
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), lowercase=True, min_df=1, max_features=30000)
    matrix = vectorizer.fit_transform(docs)
    return vectorizer, matrix


def _score_tfidf_query(vectorizer: Optional[TfidfVectorizer], matrix: Any, query_text: str, docs_count: int) -> List[float]:
    if vectorizer is None or matrix is None or not str(query_text or "").strip():
        return [0.0 for _ in range(docs_count)]
    try:
        query_vec = vectorizer.transform([str(query_text or "").strip()])
        scores = (matrix @ query_vec.T).toarray().reshape(-1)
        return [float(value) for value in scores.tolist()]
    except Exception:
        return [0.0 for _ in range(docs_count)]


def _get_embedding_model() -> Any:
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL
    from sentence_transformers import SentenceTransformer

    _EMBEDDING_MODEL = SentenceTransformer(_EMBEDDING_MODEL_NAME)
    return _EMBEDDING_MODEL


def _build_embedding_doc_vectors(docs: Sequence[str], mode: str) -> Optional[np.ndarray]:
    safe_mode = str(mode or "fast").strip().lower()
    if safe_mode != "research" or not docs:
        return None
    try:
        model = _get_embedding_model()
        vectors = model.encode(list(docs), normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)
    except Exception:
        return None


def _score_embedding_query(doc_vectors: Optional[np.ndarray], query_text: str, mode: str) -> List[float]:
    docs_count = int(doc_vectors.shape[0]) if isinstance(doc_vectors, np.ndarray) and doc_vectors.ndim >= 1 else 0
    safe_mode = str(mode or "fast").strip().lower()
    if safe_mode != "research" or docs_count <= 0 or not str(query_text or "").strip():
        return [0.0 for _ in range(docs_count)]
    try:
        model = _get_embedding_model()
        query_vec = np.asarray(model.encode([str(query_text or "").strip()], normalize_embeddings=True)[0], dtype=np.float32)
        scores = np.matmul(doc_vectors, query_vec)
        return [float(value) for value in scores.tolist()]
    except Exception:
        return [0.0 for _ in range(docs_count)]


def _build_corpus_entries(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
) -> Dict[str, Any]:
    rows = list(
        _iter_filtered_entries(
            topic_identifier=topic_identifier,
            start=start,
            end=end,
            platforms=platforms,
            time_start=time_start,
            time_end=time_end,
        )
    )
    entries: List[Dict[str, Any]] = []
    docs: List[str] = []
    for row, source_file, row_index in rows:
        doc = "\n".join(
            [
                str(row.get("title") or "").strip(),
                str(row.get("title") or "").strip(),
                _record_text(row),
                str(row.get("platform") or "").strip(),
                str(row.get("author") or "").strip(),
            ]
        )
        entries.append({"row": row, "source_file": source_file, "row_index": row_index, "doc": doc})
        docs.append(doc)
    vectorizer, matrix = _build_tfidf_index(docs)
    return {
        "entries": entries,
        "vectorizer": vectorizer,
        "matrix": matrix,
        "embedding_doc_vectors": None,
        "doc_count": len(docs),
    }


def _load_cached_corpus(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict):
            return None
        if int(payload.get("version") or 0) != _RETRIEVAL_CACHE_VERSION:
            return None
        corpus = payload.get("corpus")
        return corpus if isinstance(corpus, dict) else None
    except Exception:
        return None


def _store_cached_corpus(path: Path, corpus: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump({"version": _RETRIEVAL_CACHE_VERSION, "corpus": corpus}, handle, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        return


def _get_retrieval_corpus(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
    mode: str = "fast",
) -> Dict[str, Any]:
    normalized_platforms = _normalise_platforms(platforms)
    lower_bound = str(time_start or "").strip() or str(start or "").strip()
    upper_bound = str(time_end or "").strip() or str(end or "").strip()
    source_files, source_resolution = _resolve_source_files(topic_identifier, start, end)
    cache_key = _corpus_cache_key(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        platforms=normalized_platforms,
        time_start=lower_bound,
        time_end=upper_bound,
        source_files=source_files,
        source_resolution=source_resolution,
    )
    cache_path = _corpus_cache_path(topic_identifier, start, end, cache_key)
    with _CORPUS_CACHE_LOCK:
        corpus = _CORPUS_CACHE_MEMO.get(cache_key)
        if corpus is None:
            corpus = _load_cached_corpus(cache_path)
        if corpus is None:
            corpus = _build_corpus_entries(
                topic_identifier=topic_identifier,
                start=start,
                end=end,
                platforms=normalized_platforms,
                time_start=lower_bound,
                time_end=upper_bound,
            )
            _store_cached_corpus(cache_path, corpus)
        if str(mode or "fast").strip().lower() == "research" and corpus.get("embedding_doc_vectors") is None:
            docs = [str(entry.get("doc") or "") for entry in corpus.get("entries") or [] if isinstance(entry, dict)]
            corpus["embedding_doc_vectors"] = _build_embedding_doc_vectors(docs[: max(12, len(docs))], mode)
            _store_cached_corpus(cache_path, corpus)
        _CORPUS_CACHE_MEMO[cache_key] = corpus
    return {
        "cache_key": cache_key,
        "cache_path": cache_path,
        "source_files": source_files,
        "source_resolution": source_resolution,
        "time_start": lower_bound,
        "time_end": upper_bound,
        "entries": list(corpus.get("entries") or []),
        "vectorizer": corpus.get("vectorizer"),
        "matrix": corpus.get("matrix"),
        "embedding_doc_vectors": corpus.get("embedding_doc_vectors"),
    }


def _record_text(row: Dict[str, Any]) -> str:
    parts = [
        str(row.get("title") or "").strip(),
        str(row.get("contents") or row.get("content") or "").strip(),
        str(row.get("author") or "").strip(),
        str(row.get("hit_words") or "").strip(),
        str(row.get("classification") or "").strip(),
        str(row.get("organization") or row.get("org") or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def _normalise_title(title: str) -> str:
    text = re.sub(r"\s+", "", str(title or "").strip()).lower()
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", text)


def _iter_source_entries(topic_identifier: str, start: str, end: str) -> Iterable[Tuple[Dict[str, Any], str, int]]:
    source_files, _ = _resolve_source_files(topic_identifier, start, end)
    for file_path in source_files:
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                for row_index, line in enumerate(handle, start=1):
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        yield payload, str(file_path), row_index
        except Exception:
            continue


def _iter_filtered_entries(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
) -> Iterable[Tuple[Dict[str, Any], str, int]]:
    allowed_platforms = set(_normalise_platforms(platforms))
    lower_bound = str(time_start or "").strip() or str(start or "").strip()
    upper_bound = str(time_end or "").strip() or str(end or "").strip()
    for row, source_file, row_index in _iter_source_entries(topic_identifier, start, end):
        date_text = _extract_date_text(row.get("published_at") or row.get("publish_time") or row.get("date"))
        if not _within_range(date_text, lower_bound, upper_bound):
            continue
        platform = str(row.get("platform") or "").strip()
        if allowed_platforms and platform and platform not in allowed_platforms:
            continue
        yield row, source_file, row_index


def _iter_source_rows(topic_identifier: str, start: str, end: str) -> Iterable[Dict[str, Any]]:
    for row, _, _ in _iter_source_entries(topic_identifier, start, end):
        yield row


def _iter_filtered_rows(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
) -> Iterable[Dict[str, Any]]:
    for row, _, _ in _iter_filtered_entries(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        platforms=platforms,
        time_start=time_start,
        time_end=time_end,
    ):
        yield row


def iter_filtered_records(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
) -> Iterable[Dict[str, Any]]:
    for row, source_file, row_index in _iter_filtered_entries(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        platforms=platforms,
        time_start=time_start,
        time_end=time_end,
    ):
        payload = dict(row)
        payload["_source_file"] = source_file
        payload["_source_row_index"] = row_index
        yield payload


def _make_snippet(text: str, tokens: List[str], max_chars: int = 120) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw:
        return ""
    for token in tokens:
        pos = raw.find(token)
        if pos >= 0:
            start = max(0, pos - 24)
            end = min(len(raw), pos + max_chars - 24)
            snippet = raw[start:end].strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(raw):
                snippet = snippet + "..."
            return snippet
    return raw[:max_chars]


def _score_row(text: str, title: str, tokens: List[str]) -> Tuple[float, List[str], Dict[str, float]]:
    matched: List[str] = []
    title_score = 0.0
    body_score = 0.0
    lowered_text = text.lower()
    lowered_title = title.lower()
    for token in tokens:
        lowered = token.lower()
        if lowered in lowered_title:
            matched.append(token)
            title_score += 2.2
        elif lowered in lowered_text:
            matched.append(token)
            body_score += 1.0
    return title_score + body_score, matched, {"title": round(title_score, 4), "body": round(body_score, 4)}


def _query_has_policy_intent(query_text: str, query_terms: Sequence[str]) -> bool:
    haystack = f"{str(query_text or '').strip()} {' '.join(query_terms)}"
    return any(hint in haystack for hint in _POLICY_HINTS)


def _source_quality_bonus(row: Dict[str, Any]) -> float:
    score = 0.0
    platform = str(row.get("platform") or "").strip()
    source_type = str(row.get("source_type") or "").strip()
    author_type = str(row.get("author_type") or row.get("account_type") or row.get("publisher_type") or "").strip()
    is_official = row.get("is_official")
    if platform == "新闻":
        score += 0.2
    if "官方" in author_type or "官方" in source_type:
        score += 0.25
    if is_official not in (None, "", False, 0, "0", "false", "False"):
        score += 0.35
    return round(score, 4)


def _policy_context_adjustment(row: Dict[str, Any], query_text: str, query_terms: Sequence[str]) -> float:
    if not _query_has_policy_intent(query_text, query_terms):
        return 0.0
    text = _record_text(row)
    score = sum(0.18 for hint in _POLICY_CONTEXT_HINTS if hint in text)
    if any(hint in text for hint in _KITCHEN_NOISE_HINTS):
        score -= 1.8
    return round(score, 4)


def _compute_tfidf_scores(docs: Sequence[str], query_text: str) -> List[float]:
    if not docs or not str(query_text or "").strip():
        return [0.0 for _ in docs]
    try:
        vectorizer, matrix = _build_tfidf_index(docs)
        return _score_tfidf_query(vectorizer, matrix, query_text, len(docs))
    except Exception:
        return [0.0 for _ in docs]


def _maybe_embedding_scores(docs: Sequence[str], query_text: str, mode: str) -> List[float]:
    safe_mode = str(mode or "fast").strip().lower()
    if safe_mode != "research" or not docs or not str(query_text or "").strip():
        return [0.0 for _ in docs]
    try:
        doc_vecs = _build_embedding_doc_vectors(docs[: max(12, len(docs))], mode)
        return _score_embedding_query(doc_vecs, query_text, mode)
    except Exception:
        return [0.0 for _ in docs]


def _select_diverse_candidates(candidates: List[Dict[str, Any]], *, top_k: int) -> List[Dict[str, Any]]:
    remaining = list(candidates)
    selected: List[Dict[str, Any]] = []
    platform_counts: Counter[str] = Counter()
    date_counts: Counter[str] = Counter()
    while remaining and len(selected) < max(1, int(top_k or 1)):
        best_index = 0
        best_score = -10**9
        for index, candidate in enumerate(remaining[:120]):
            adjusted = float(candidate["score"])
            adjusted -= 0.35 * platform_counts.get(candidate["platform"] or "未知", 0)
            adjusted -= 0.18 * date_counts.get(candidate["date_text"] or "未知", 0)
            if adjusted > best_score:
                best_score = adjusted
                best_index = index
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        platform_counts[chosen["platform"] or "未知"] += 1
        date_counts[chosen["date_text"] or "未知"] += 1
    return selected


def _retrieve_candidates(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    query_text: str,
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
    top_k: int = 20,
    mode: str = "fast",
) -> Dict[str, Any]:
    corpus = _get_retrieval_corpus(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        platforms=platforms,
        time_start=time_start,
        time_end=time_end,
        mode=mode,
    )
    entries = [entry for entry in corpus.get("entries") or [] if isinstance(entry, dict)]
    query_terms = _build_query_terms(query_text, entities)
    lexical_scores = _score_tfidf_query(
        corpus.get("vectorizer"),
        corpus.get("matrix"),
        query_text,
        len(entries),
    )
    embedding_scores = _score_embedding_query(corpus.get("embedding_doc_vectors"), query_text, mode)
    candidates: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries):
        row = entry.get("row") if isinstance(entry.get("row"), dict) else {}
        source_file = str(entry.get("source_file") or "").strip()
        row_index = int(entry.get("row_index") or 0)
        title = str(row.get("title") or "").strip()
        text = _record_text(row)
        token_score, matched_terms, token_breakdown = _score_row(text, title, query_terms)
        lexical_score = lexical_scores[index] if index < len(lexical_scores) else 0.0
        embedding_score = embedding_scores[index] if index < len(embedding_scores) else 0.0
        if query_terms and token_score <= 0.0 and lexical_score <= 0.0 and embedding_score <= 0.0:
            continue
        source_bonus = _source_quality_bonus(row)
        context_adjustment = _policy_context_adjustment(row, query_text, query_terms)
        total_score = token_score + lexical_score * 6.0 + embedding_score * 2.5 + source_bonus + context_adjustment
        if total_score <= 0.0:
            continue
        platform = str(row.get("platform") or "").strip()
        date_text = _extract_date_text(row.get("published_at") or row.get("publish_time") or row.get("date")) or "未知"
        url = str(row.get("url") or "").strip()
        dedupe_key = url.lower() if url else _normalise_title(title)
        # Extract engagement and sentiment data from raw row (for downstream evidence cards)
        engagement_likes = row.get("点赞数") or row.get("like_count") or row.get("likes")
        engagement_comments = row.get("评论数") or row.get("comment_count") or row.get("comments")
        engagement_shares = row.get("转发数") or row.get("share_count") or row.get("shares") or row.get("转发")
        engagement_views = row.get("播放量") or row.get("view_count") or row.get("views") or row.get("阅读量")
        sentiment_raw = row.get("情感") or row.get("sentiment") or row.get("sentiment_label") or row.get("polarity")
        hotness_raw = row.get("热度") or row.get("hotness_score") or row.get("hotness")

        candidates.append(
            {
                "title": title,
                "snippet": _make_snippet(text, matched_terms or _tokenize(title or text)),
                "url": url,
                "published_at": str(row.get("published_at") or row.get("publish_time") or row.get("date") or "").strip(),
                "platform": platform,
                "author": str(row.get("author") or "").strip(),
                "matched_terms": matched_terms[:6],
                "score": round(total_score, 4),
                "source_file": source_file,
                "source_row_index": row_index,
                "score_breakdown": {
                    **token_breakdown,
                    "lexical": round(lexical_score * 6.0, 4),
                    "embedding": round(embedding_score * 2.5, 4),
                    "source_quality": source_bonus,
                    "policy_context": context_adjustment,
                },
                "date_text": date_text,
                "dedupe_key": dedupe_key or f"{source_file}:{row_index}",
                "row_text": text,
                # Engagement data for evidence cards (NetInsight sources have these)
                "engagement_likes": engagement_likes,
                "engagement_comments": engagement_comments,
                "engagement_shares": engagement_shares,
                "engagement_views": engagement_views,
                "sentiment_raw": sentiment_raw,
                "hotness_raw": hotness_raw,
            }
        )

    by_key: Dict[str, Dict[str, Any]] = {}
    for candidate in sorted(candidates, key=lambda item: float(item["score"]), reverse=True):
        key = str(candidate["dedupe_key"] or "").strip()
        if key not in by_key:
            by_key[key] = candidate
    deduped = list(by_key.values())
    selected = _select_diverse_candidates(deduped, top_k=max(3, min(int(top_k or 20), 50)))
    source_distribution: Dict[str, int] = {}
    time_distribution: Dict[str, int] = {}
    matched_terms_counter: Counter[str] = Counter()
    for candidate in deduped:
        source_distribution[candidate["platform"] or "未知"] = source_distribution.get(candidate["platform"] or "未知", 0) + 1
        time_distribution[candidate["date_text"]] = time_distribution.get(candidate["date_text"], 0) + 1
        matched_terms_counter.update(candidate["matched_terms"])
    source_files = list(corpus.get("source_files") or [])
    source_resolution = str(corpus.get("source_resolution") or "").strip()
    retrieval_strategy = "tfidf_lexical"
    if str(mode or "fast").strip().lower() == "research":
        retrieval_strategy = "tfidf_lexical+embedding" if any(score > 0 for score in embedding_scores) else "tfidf_lexical"
    return {
        "query": str(query_text or "").strip(),
        "query_terms": query_terms[:10],
        "time_start": str(corpus.get("time_start") or "").strip(),
        "time_end": str(corpus.get("time_end") or "").strip(),
        "items": [{key: value for key, value in item.items() if key not in {"dedupe_key", "date_text", "row_text"}} for item in selected],
        "source_distribution": source_distribution,
        "time_distribution": dict(sorted(time_distribution.items(), key=lambda item: item[0])),
        "high_signal_terms": [term for term, _ in matched_terms_counter.most_common(8)],
        "scanned_records": len(entries),
        "matched_records": len(candidates),
        "candidate_count": len(candidates),
        "deduped_count": len(deduped),
        "source_files": [str(path) for path in source_files],
        "source_resolution": source_resolution,
        "retrieval_strategy": retrieval_strategy,
        "mode": "research" if str(mode or "").strip().lower() == "research" else "fast",
        "cache_scope": "window_corpus",
    }


def verify_claim_with_records(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    claim: str,
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    retrieve_mode: str = "claim_verification",
    top_k: int = 20,
    mode: str = "fast",
) -> Dict[str, Any]:
    claim_text = str(claim or "").strip()
    retrieval = _retrieve_candidates(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        query_text=claim_text,
        entities=entities,
        platforms=platforms,
        top_k=max(12, int(top_k or 20) * 2),
        mode=mode,
    )
    claim_negated = any(hint in claim_text for hint in _NEGATION_HINTS)
    supporting_items: List[Dict[str, Any]] = []
    contradicting_items: List[Dict[str, Any]] = []
    for item in retrieval["items"]:
        row_negated = any(hint in str(item.get("snippet") or "") for hint in _NEGATION_HINTS) or any(
            hint in str(item.get("title") or "") for hint in _NEGATION_HINTS
        )
        payload = dict(item)
        payload["evidence_alignment"] = "support" if row_negated == claim_negated else "contradict"
        if payload["evidence_alignment"] == "support":
            supporting_items.append(payload)
        else:
            contradicting_items.append(payload)

    if supporting_items and contradicting_items:
        verification_status = "conflicting"
    elif len(supporting_items) >= 3:
        verification_status = "supported"
    elif supporting_items:
        verification_status = "partially_supported"
    else:
        verification_status = "unverified"

    return {
        "claim": claim_text,
        "retrieve_mode": str(retrieve_mode or "claim_verification").strip(),
        "query_terms": retrieval["query_terms"],
        "supporting_items": supporting_items[: max(3, min(int(top_k or 20), 50))],
        "contradicting_items": contradicting_items[: max(3, min(8, max(1, int(top_k or 20)) // 2))],
        "insufficient_evidence": verification_status in {"unverified", "partially_supported"},
        "representative_quotes": [
            {
                "quote": str(item.get("snippet") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "platform": str(item.get("platform") or "").strip(),
            }
            for item in supporting_items[:3]
            if str(item.get("snippet") or "").strip()
        ],
        "source_distribution": retrieval["source_distribution"],
        "verification_status": verification_status,
        "scanned_records": retrieval["scanned_records"],
        "matched_records": retrieval["matched_records"],
        "candidate_count": retrieval["candidate_count"],
        "deduped_count": retrieval["deduped_count"],
        "source_files": retrieval["source_files"],
        "source_resolution": retrieval["source_resolution"],
        "retrieval_strategy": retrieval["retrieval_strategy"],
        "mode": retrieval["mode"],
    }


def search_raw_records(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    query: str,
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
    top_k: int = 20,
    mode: str = "fast",
) -> Dict[str, Any]:
    return _retrieve_candidates(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        query_text=str(query or "").strip(),
        entities=entities,
        platforms=platforms,
        time_start=time_start,
        time_end=time_end,
        top_k=top_k,
        mode=mode,
    )


def summarize_source_scope(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    top_platforms: int = 6,
    top_authors: int = 8,
) -> Dict[str, Any]:
    platform_counter: Counter[str] = Counter()
    author_counter: Counter[str] = Counter()
    scanned = 0
    platform_present = 0
    author_present = 0
    org_present = 0
    official_present = 0

    for row in _iter_filtered_rows(topic_identifier=topic_identifier, start=start, end=end):
        scanned += 1
        platform = str(row.get("platform") or "").strip()
        author = str(row.get("author") or "").strip()
        organization = str(row.get("organization") or row.get("org") or "").strip()
        author_type = str(row.get("author_type") or row.get("account_type") or row.get("publisher_type") or "").strip()
        source_type = str(row.get("source_type") or "").strip()
        is_official = row.get("is_official")
        if platform:
            platform_present += 1
            platform_counter[platform] += 1
        if author:
            author_present += 1
            author_counter[author] += 1
        if organization:
            org_present += 1
        if author_type or source_type or is_official not in (None, "", False, 0, "0", "false", "False"):
            official_present += 1

    available_dimensions = ["platform"]
    if author_present:
        available_dimensions.append("author")
    if org_present:
        available_dimensions.append("organization")
    if official_present:
        available_dimensions.extend(item for item in ("author_type", "official_source_flag") if item not in available_dimensions)

    missing_dimensions = []
    if not official_present:
        missing_dimensions.extend(["author_type", "official_source_flag", "official_posting_record"])
    if not org_present:
        missing_dimensions.append("organization")

    source_files, source_resolution = _resolve_source_files(topic_identifier, start, end)
    return {
        "scanned_records": scanned,
        "platforms": [{"name": name, "count": count} for name, count in platform_counter.most_common(max(1, top_platforms))],
        "authors": [{"name": name, "count": count} for name, count in author_counter.most_common(max(1, top_authors))],
        "coverage": {
            "platform_ratio": round(platform_present / scanned, 4) if scanned else 0.0,
            "author_ratio": round(author_present / scanned, 4) if scanned else 0.0,
            "organization_ratio": round(org_present / scanned, 4) if scanned else 0.0,
            "official_signal_ratio": round(official_present / scanned, 4) if scanned else 0.0,
        },
        "available_dimensions": available_dimensions,
        "missing_dimensions": missing_dimensions,
        "writable_subjects": ["平台分布", *([] if not author_present else ["作者署名或头部发布者"]), *([] if not org_present else ["组织名称"])],
        "prohibited_inference": [
            *([] if official_present else ["不能从当前数据直接推导政务、官方或机构账号是否缺位、是否同步发布、是否响应迟缓。"]),
            *([] if org_present else ["不能从当前数据直接推导具体机构之间的分工或责任链。"]),
        ],
        "boundary_summary": "当前主体范围直接来自原始条目字段统计，只能支撑平台、作者和已显式存在的组织/主体字段判断；缺失维度不得被扩写成机构行为结论。",
        "source_files": [str(path) for path in source_files],
        "source_resolution": source_resolution,
    }


def analyze_temporal_event_window(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    anchor_date: str,
    query: str = "",
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    window_days: int = 7,
    top_k: int = 6,
) -> Dict[str, Any]:
    anchor_dt = _extract_date_obj(anchor_date)
    if anchor_dt is None:
        return {
            "anchor_date": str(anchor_date or "").strip(),
            "verification_status": "invalid_anchor_date",
            "windows": {},
            "shift_summary": "时间锚点格式无效，无法进行时窗比较。",
        }

    query_terms = _build_query_terms(str(query or "").strip(), entities)
    safe_window_days = max(1, min(int(window_days or 7), 30))
    safe_top_k = max(2, min(int(top_k or 6), 12))
    windows: Dict[str, Dict[str, Any]] = {
        "pre_window": {"count": 0, "items": [], "terms": Counter()},
        "anchor_window": {"count": 0, "items": [], "terms": Counter()},
        "post_window": {"count": 0, "items": [], "terms": Counter()},
    }

    for row in iter_filtered_records(topic_identifier=topic_identifier, start=start, end=end, platforms=platforms):
        row_dt = _extract_date_obj(row.get("published_at") or row.get("publish_time") or row.get("date"))
        if row_dt is None:
            continue
        delta_days = (row_dt.date() - anchor_dt.date()).days
        if delta_days < -safe_window_days or delta_days > safe_window_days:
            continue
        if delta_days < 0:
            bucket_key = "pre_window"
        elif delta_days == 0:
            bucket_key = "anchor_window"
        else:
            bucket_key = "post_window"

        title = str(row.get("title") or "").strip()
        text = _record_text(row)
        if query_terms:
            score, matched_terms, _ = _score_row(text, title, query_terms)
            if score <= 0:
                continue
        else:
            score = 1.0
            matched_terms = _tokenize(title or text, max_items=6)
        payload = {
            "title": title,
            "snippet": _make_snippet(text, matched_terms or _tokenize(title or text)),
            "url": str(row.get("url") or "").strip(),
            "published_at": str(row.get("published_at") or row.get("publish_time") or row.get("date") or "").strip(),
            "platform": str(row.get("platform") or "").strip(),
            "author": str(row.get("author") or "").strip(),
            "matched_terms": matched_terms[:6],
            "score": round(score, 4),
            "source_file": str(row.get("_source_file") or "").strip(),
        }
        windows[bucket_key]["count"] += 1
        windows[bucket_key]["terms"].update(matched_terms)
        windows[bucket_key]["items"].append(payload)
        windows[bucket_key]["items"].sort(key=lambda item: float(item["score"]), reverse=True)
        del windows[bucket_key]["items"][safe_top_k:]

    normalized: Dict[str, Any] = {}
    for key, bucket in windows.items():
        normalized[key] = {
            "count": int(bucket["count"]),
            "top_terms": [term for term, _ in bucket["terms"].most_common(6)],
            "sample_items": list(bucket["items"]),
        }

    pre_count = normalized["pre_window"]["count"]
    anchor_count = normalized["anchor_window"]["count"]
    post_count = normalized["post_window"]["count"]
    if anchor_count > max(pre_count, post_count):
        shift_summary = "锚点日期附近讨论最集中，说明该时间点与传播放大存在明显同步关系。"
    elif post_count > pre_count:
        shift_summary = "锚点后窗口的相关讨论继续扩散，说明事件效应并未止于单日峰值。"
    elif pre_count > 0:
        shift_summary = "锚点前已存在较强铺垫，当前节点更像累积放量而非单点凭空触发。"
    else:
        shift_summary = "当前时间窗内的有效样本有限，只能做弱趋势判断。"

    source_files, source_resolution = _resolve_source_files(topic_identifier, start, end)
    return {
        "anchor_date": anchor_dt.strftime("%Y-%m-%d"),
        "query_terms": query_terms[:10],
        "window_days": safe_window_days,
        "verification_status": "ok",
        "windows": normalized,
        "shift_summary": shift_summary,
        "source_files": [str(path) for path in source_files],
        "source_resolution": source_resolution,
    }


def compare_content_focus(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    bucket_a_terms: List[str],
    bucket_b_terms: List[str],
    query: str = "",
    entities: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    time_start: str = "",
    time_end: str = "",
    top_k: int = 8,
) -> Dict[str, Any]:
    query_terms = _build_query_terms(str(query or "").strip(), entities)
    bucket_a = _normalise_terms(bucket_a_terms, max_items=16)
    bucket_b = _normalise_terms(bucket_b_terms, max_items=16)
    safe_top_k = max(2, min(int(top_k or 8), 12))
    stats: Dict[str, Dict[str, Any]] = {
        "bucket_a": {"count": 0, "items": [], "terms": Counter(), "total_score": 0.0},
        "bucket_b": {"count": 0, "items": [], "terms": Counter(), "total_score": 0.0},
    }

    for row in iter_filtered_records(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        platforms=platforms,
        time_start=time_start,
        time_end=time_end,
    ):
        title = str(row.get("title") or "").strip()
        text = _record_text(row)
        if query_terms:
            base_score, _, _ = _score_row(text, title, query_terms)
            if base_score <= 0:
                continue
        else:
            base_score = 1.0
        a_score, a_terms, _ = _score_row(text, title, bucket_a)
        b_score, b_terms, _ = _score_row(text, title, bucket_b)
        if a_score <= 0 and b_score <= 0:
            continue
        bucket_key = "bucket_a" if a_score >= b_score else "bucket_b"
        matched_terms = a_terms if bucket_key == "bucket_a" else b_terms
        score = base_score + max(a_score, b_score)
        bucket = stats[bucket_key]
        bucket["count"] += 1
        bucket["total_score"] = round(float(bucket["total_score"]) + score, 4)
        bucket["terms"].update(matched_terms)
        bucket["items"].append(
            {
                "title": title,
                "snippet": _make_snippet(text, matched_terms or _tokenize(title or text)),
                "url": str(row.get("url") or "").strip(),
                "published_at": str(row.get("published_at") or row.get("publish_time") or row.get("date") or "").strip(),
                "platform": str(row.get("platform") or "").strip(),
                "author": str(row.get("author") or "").strip(),
                "matched_terms": matched_terms[:6],
                "score": round(score, 4),
                "source_file": str(row.get("_source_file") or "").strip(),
            }
        )
        bucket["items"].sort(key=lambda item: float(item["score"]), reverse=True)
        del bucket["items"][safe_top_k:]

    normalized = {
        key: {
            "label": key,
            "count": int(value["count"]),
            "top_terms": [term for term, _ in value["terms"].most_common(6)],
            "sample_items": list(value["items"]),
            "total_score": round(float(value["total_score"]), 4),
        }
        for key, value in stats.items()
    }
    if normalized["bucket_a"]["count"] > normalized["bucket_b"]["count"]:
        dominant_focus = "bucket_a"
        comparison = "相关讨论更偏向第一组语义桶。"
    elif normalized["bucket_b"]["count"] > normalized["bucket_a"]["count"]:
        dominant_focus = "bucket_b"
        comparison = "相关讨论更偏向第二组语义桶。"
    else:
        dominant_focus = "balanced"
        comparison = "两组语义桶在当前样本中的讨论强度接近。"

    source_files, source_resolution = _resolve_source_files(topic_identifier, start, end)
    return {
        "query_terms": query_terms[:10],
        "time_start": str(time_start or start or "").strip(),
        "time_end": str(time_end or end or "").strip(),
        "bucket_a_terms": bucket_a[:10],
        "bucket_b_terms": bucket_b[:10],
        "bucket_a": normalized["bucket_a"],
        "bucket_b": normalized["bucket_b"],
        "dominant_focus": dominant_focus,
        "comparison": comparison,
        "source_files": [str(path) for path in source_files],
        "source_resolution": source_resolution,
    }
