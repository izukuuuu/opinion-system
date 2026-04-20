from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Literal, Sequence

from langchain.tools import tool


PROJECT_ROOT = Path(__file__).resolve().parents[4]
RAG_CACHE_ROOT = PROJECT_ROOT / "backend" / "data" / "_report" / "rag"
RAG_KNOWLEDGE_ROOT = PROJECT_ROOT / "backend" / "knowledge_base" / "report" / "rag"
RAG_MANIFEST_PATH = RAG_KNOWLEDGE_ROOT / "manifest.json"

TEXT_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".csv"}
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 160
_INDEX_LOCK = Lock()
_RETRIEVER_CACHE: Dict[str, "_BackgroundRetriever"] = {}

KnowledgeType = Literal["methodology", "cases", "expert_notes", "youth_insight", "policy", "auto"]


class _DeterministicHashEmbeddings:
    """Local deterministic embeddings for Chroma when remote embeddings are unavailable."""

    def __init__(self, *, dimensions: int = 256) -> None:
        self.dimensions = max(64, int(dimensions or 256))

    def _vectorize(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in _tokenize(text, max_items=96):
            digest = sha256(token.encode("utf-8", errors="ignore")).digest()
            for index in range(0, len(digest), 2):
                bucket = int.from_bytes(digest[index : index + 2], "big") % self.dimensions
                vector[bucket] += 1.0
        norm = sum(value * value for value in vector) ** 0.5
        if norm <= 0:
            return vector
        return [round(value / norm, 8) for value in vector]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._vectorize(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._vectorize(text)


def _safe_read_text(path: Path, *, max_chars: int = 200_000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return text[:max_chars] if len(text) > max_chars else text


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _chunk_text(text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[Dict[str, Any]]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [{"text": normalized, "start": 0, "end": len(normalized)}]

    chunks: List[Dict[str, Any]] = []
    start = 0
    step = max(1, chunk_size - max(0, chunk_overlap))
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        window = normalized[start:end]
        if end < len(normalized):
            split_at = max(window.rfind("。"), window.rfind("；"), window.rfind("！"), window.rfind("？"))
            if split_at >= int(chunk_size * 0.45):
                end = start + split_at + 1
                window = normalized[start:end]
        compact = window.strip()
        if compact:
            chunks.append({"text": compact, "start": start, "end": end})
        if end >= len(normalized):
            break
        start += step
    return chunks


def _tokenize(text: str, *, max_items: int = 40) -> List[str]:
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
    output: List[str] = []
    seen = set()
    for token in sorted(tokens, key=len, reverse=True):
        lowered = token.lower()
        if len(token) < 2 or lowered in seen:
            continue
        seen.add(lowered)
        output.append(token)
        if len(output) >= max_items:
            break
    return output


def _score_text(query_tokens: Sequence[str], text: str) -> float:
    haystack = str(text or "").lower()
    if not query_tokens or not haystack:
        return 0.0
    score = 0.0
    for token in query_tokens:
        lowered = token.lower()
        if lowered in haystack:
            score += 1.0 + min(len(token), 12) * 0.08
    return round(score, 4)


def _relative_source_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def _iter_files(paths: Iterable[Path]) -> List[Path]:
    results: List[Path] = []
    seen = set()
    for root in paths:
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = sorted(root.rglob("*"))
        for path in candidates:
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if path.name.startswith(".") or path.name.lower().startswith("readme"):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            results.append(path)
    return results


def _load_manifest() -> Dict[str, Any]:
    try:
        payload = json.loads(RAG_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _manifest_knowledge_types() -> Dict[str, Dict[str, Any]]:
    manifest = _load_manifest()
    entries = manifest.get("knowledge_types")
    if not isinstance(entries, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for key, value in entries.items():
        kind = str(key or "").strip().lower()
        if not kind or not isinstance(value, dict):
            continue
        normalized[kind] = dict(value)
    return normalized


def _supported_knowledge_types() -> List[str]:
    return list(_manifest_knowledge_types().keys())


def _knowledge_spec(knowledge_type: str) -> Dict[str, Any]:
    kind = str(knowledge_type or "").strip().lower()
    return dict(_manifest_knowledge_types().get(kind) or {})


def _knowledge_directory(knowledge_type: str) -> Path:
    spec = _knowledge_spec(knowledge_type)
    directory = str(spec.get("directory") or str(knowledge_type or "").strip().lower()).strip()
    return RAG_KNOWLEDGE_ROOT / directory


def _knowledge_sources(knowledge_type: str) -> List[Path]:
    return _iter_files([_knowledge_directory(knowledge_type)])


def _resolve_knowledge_types(knowledge_type: str) -> List[str]:
    kind = str(knowledge_type or "auto").strip().lower() or "auto"
    if kind != "auto":
        return [kind]
    return _supported_knowledge_types()


@dataclass
class _BackgroundRetriever:
    knowledge_type: str
    backend: str
    documents: List[Dict[str, Any]]
    vectorstore: Any | None = None

    def invoke(self, query: str, *, top_k: int) -> List[Dict[str, Any]]:
        query_text = _normalize_text(query)
        if not query_text:
            return []
        limit = max(1, min(int(top_k or 4), 8))
        if self.backend == "chroma" and self.vectorstore is not None:
            try:
                results = self.vectorstore.similarity_search_with_relevance_scores(query_text, k=limit)
            except Exception:
                results = []
            payload: List[Dict[str, Any]] = []
            for doc, score in results:
                metadata = dict(getattr(doc, "metadata", {}) or {})
                payload.append(
                    {
                        "knowledge_type": self.knowledge_type,
                        "title": str(metadata.get("title") or "").strip(),
                        "snippet": _normalize_text(getattr(doc, "page_content", ""))[:520],
                        "score": round(float(score or 0.0), 4),
                        "source_path": str(metadata.get("source_path") or "").strip(),
                        "metadata": metadata,
                    }
                )
            payload.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
            return payload[:limit]

        query_tokens = _tokenize(query_text)
        ranked: List[Dict[str, Any]] = []
        for item in self.documents:
            score = _score_text(query_tokens, str(item.get("page_content") or ""))
            if score <= 0:
                continue
            ranked.append(
                {
                    "knowledge_type": self.knowledge_type,
                    "title": str((item.get("metadata") or {}).get("title") or "").strip(),
                    "snippet": _normalize_text(item.get("page_content"))[:520],
                    "score": score,
                    "source_path": str((item.get("metadata") or {}).get("source_path") or "").strip(),
                    "metadata": dict(item.get("metadata") or {}),
                }
            )
        ranked.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
        return ranked[:limit]


def _build_documents(knowledge_type: str) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for path in _knowledge_sources(knowledge_type):
        text = _safe_read_text(path)
        if not text:
            continue
        chunks = _chunk_text(text)
        for idx, chunk in enumerate(chunks, start=1):
            docs.append(
                {
                    "page_content": str(chunk.get("text") or "").strip(),
                    "metadata": {
                        "knowledge_type": knowledge_type,
                        "title": path.name,
                        "source_path": _relative_source_path(path),
                        "chunk_index": idx,
                        "chunk_start": int(chunk.get("start") or 0),
                        "chunk_end": int(chunk.get("end") or 0),
                    },
                }
            )
    return docs


def _build_chroma_retriever(knowledge_type: str, documents: List[Dict[str, Any]]) -> _BackgroundRetriever:
    if not documents:
        return _BackgroundRetriever(knowledge_type=knowledge_type, backend="chroma", documents=[])
    try:
        from langchain_chroma import Chroma
        from langchain_core.documents import Document
    except Exception as exc:
        raise RuntimeError("langchain-chroma is required for report RAG retrieval.") from exc

    embedding_provider = "hash"
    embedding: Any
    if str(os.environ.get("OPENAI_API_KEY") or "").strip():
        try:
            from langchain_openai import OpenAIEmbeddings
        except Exception as exc:
            raise RuntimeError("langchain-openai is required when OPENAI_API_KEY is configured for report RAG.") from exc
        embedding = OpenAIEmbeddings(model="text-embedding-3-small")
        embedding_provider = "openai-text-embedding-3-small"
    else:
        embedding = _DeterministicHashEmbeddings()

    persist_directory = RAG_CACHE_ROOT / knowledge_type / embedding_provider
    persist_directory.mkdir(parents=True, exist_ok=True)
    collection_name = f"report-background-{knowledge_type}-{embedding_provider}".replace("_", "-")
    try:
        vectorstore = Chroma(
            collection_name=collection_name,
            persist_directory=str(persist_directory),
            embedding_function=embedding,
        )
        existing = int(vectorstore._collection.count())  # type: ignore[attr-defined]
    except Exception as exc:
        raise RuntimeError(f"Failed to initialize Chroma retriever for knowledge_type={knowledge_type}.") from exc

    if existing == 0:
        vectorstore.add_documents(
            [
                Document(page_content=str(item.get("page_content") or ""), metadata=dict(item.get("metadata") or {}))
                for item in documents
                if str(item.get("page_content") or "").strip()
            ]
        )
    return _BackgroundRetriever(knowledge_type=knowledge_type, backend="chroma", documents=documents, vectorstore=vectorstore)


def _get_retriever_for_type(knowledge_type: str) -> _BackgroundRetriever:
    kind = str(knowledge_type or "methodology").strip().lower() or "methodology"
    if kind == "auto":
        raise ValueError("auto is not a concrete retriever type")
    if kind not in set(_supported_knowledge_types()):
        raise ValueError(f"Unsupported knowledge_type: {knowledge_type}")
    with _INDEX_LOCK:
        cached = _RETRIEVER_CACHE.get(kind)
        if cached is not None:
            return cached
        documents = _build_documents(kind)
        retriever = _build_chroma_retriever(kind, documents)
        _RETRIEVER_CACHE[kind] = retriever
        return retriever


def build_rag_background_payload(topic: str, *, knowledge_types: Sequence[str] | None = None, top_k: int = 4) -> Dict[str, Any]:
    query = _normalize_text(topic)
    types = [
        str(item).strip().lower()
        for item in (knowledge_types or ["methodology", "cases", "youth_insight"])
        if str(item or "").strip()
    ]
    groups: List[Dict[str, Any]] = []
    for knowledge_type in types:
        if knowledge_type not in set(_supported_knowledge_types()):
            continue
        retriever = _get_retriever_for_type(knowledge_type)
        spec = _knowledge_spec(knowledge_type)
        groups.append(
            {
                "knowledge_type": knowledge_type,
                "label": str(spec.get("label") or "").strip(),
                "description": str(spec.get("description") or "").strip(),
                "writer_auto_allowed": bool(spec.get("writer_auto_allowed")),
                "knowledge_root": _relative_source_path(_knowledge_directory(knowledge_type)),
                "backend": retriever.backend,
                "source_paths": [_relative_source_path(path) for path in _knowledge_sources(knowledge_type)],
                "results": retriever.invoke(query, top_k=top_k),
            }
        )
    return {
        "tool_name": "rag_knowledge_search",
        "query": query,
        "knowledge_type": "auto" if not knowledge_types else ",".join(types),
        "context_kind": "background_context",
        "results": groups,
    }


@tool
def rag_knowledge_search(query: str, knowledge_type: str = "methodology", top_k: int = 4) -> str:
    """
    检索报告背景知识库，只返回背景参考，不作为事实证据。

    knowledge_type: methodology | cases | expert_notes | youth_insight | policy | auto
    """
    query_text = _normalize_text(query)
    safe_top_k = max(1, min(int(top_k or 4), 8))
    if not query_text:
        return json.dumps(
            {
                "query": "",
                "knowledge_type": str(knowledge_type or "methodology").strip() or "methodology",
                "context_kind": "background_context",
                "result_count": 0,
                "results": [],
                "usage_boundary": [
                    "仅可作为理论解释、历史类比、背景补充。",
                    "禁止将结果写成当前事件已证实事实。",
                    "禁止将结果混入 evidence_cards 或 claim verification。",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    result_rows: List[Dict[str, Any]] = []
    selected_types = _resolve_knowledge_types(knowledge_type)
    for selected in selected_types:
        retriever = _get_retriever_for_type(selected)
        result_rows.extend(retriever.invoke(query_text, top_k=safe_top_k))

    result_rows.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    result_rows = result_rows[:safe_top_k]
    payload = {
        "query": query_text,
        "knowledge_type": str(knowledge_type or "methodology").strip() or "methodology",
        "context_kind": "background_context",
        "result_count": len(result_rows),
        "manifest_version": str(_load_manifest().get("version") or "").strip(),
        "knowledge_types": {
            kind: {
                "label": str(_knowledge_spec(kind).get("label") or "").strip(),
                "description": str(_knowledge_spec(kind).get("description") or "").strip(),
                "writer_auto_allowed": bool(_knowledge_spec(kind).get("writer_auto_allowed")),
                "knowledge_root": _relative_source_path(_knowledge_directory(kind)),
            }
            for kind in selected_types
        },
        "source_paths": list(dict.fromkeys([item.get("source_path") for item in result_rows if str(item.get("source_path") or "").strip()])),
        "results": result_rows,
        "usage_boundary": [
            "仅可作为理论解释、历史类比、背景补充。",
            "禁止将结果写成当前事件已证实事实。",
            "禁止将结果混入 evidence_cards 或 claim verification。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = [
    "build_rag_background_payload",
    "rag_knowledge_search",
    "_get_retriever_for_type",
]
