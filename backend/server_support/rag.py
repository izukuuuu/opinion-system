"""RAG helpers for resolving per-project storage paths and auto-building indices."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import json
import threading
import time

import lancedb

from src.utils.setting.paths import get_data_root, bucket
from src.utils.io.excel import read_jsonl
from src.utils.logging.logging import setup_logger, log_success, log_error
from src.utils.rag.tagrag.tag_vec_data import vectorize_and_store
from src.utils.rag.ragrouter.router_vec_data import run_ragrouter
from src.fetch.data_fetch import fetch_range, get_topic_available_date_range

_RAG_BUILD_STATUS: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
_RAG_BUILD_LOCK = threading.Lock()


def _project_rag_root(project: str) -> Optional[Path]:
    project = str(project or "").strip()
    if not project:
        return None
    data_root = get_data_root()
    project_dir = data_root / "projects" / project
    if not project_dir.exists():
        return None
    rag_root = project_dir / "rag"
    rag_root.mkdir(parents=True, exist_ok=True)
    return rag_root


def _status_key(project: str, rag_type: str, topic: str) -> Tuple[str, str, str]:
    return (project, rag_type, topic)


def get_rag_build_status(project: str, rag_type: str, topic: str) -> Dict[str, Any]:
    with _RAG_BUILD_LOCK:
        status = _RAG_BUILD_STATUS.get(_status_key(project, rag_type, topic))
        return dict(status) if isinstance(status, dict) else {
            "status": "idle",
            "percent": 0,
            "message": "",
            "updated_at": None,
        }


def _update_status(project: str, rag_type: str, topic: str, status: str, percent: int, message: str) -> None:
    with _RAG_BUILD_LOCK:
        _RAG_BUILD_STATUS[_status_key(project, rag_type, topic)] = {
            "status": status,
            "percent": max(0, min(100, int(percent))),
            "message": message,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }


def _tagrag_db_ready(topic: str, project: str) -> bool:
    rag_root = _project_rag_root(project)
    if not rag_root:
        return False
    vector_dir = rag_root / "tagrag" / "vector_db"
    if not vector_dir.exists():
        return False
    try:
        db = lancedb.connect(str(vector_dir))
        return bool(db.table_names())
    except Exception:
        return False


def _routerrag_db_ready(topic: str, project: str) -> bool:
    rag_root = _project_rag_root(project)
    if not rag_root:
        return False
    base_path = rag_root / "routerrag" / f"{topic}数据库"
    vector_dir = base_path / "vector_db"
    if not vector_dir.exists():
        return False
    try:
        db = lancedb.connect(str(vector_dir))
        return bool(db.table_names())
    except Exception:
        return False


def list_project_tagrag_topics(project: str) -> List[str]:
    rag_root = _project_rag_root(project)
    if not rag_root:
        return []
    format_dir = rag_root / "tagrag" / "format_db"
    if not format_dir.exists():
        return []
    return [p.stem for p in format_dir.glob("*.json") if p.stem]


def list_project_routerrag_topics(project: str) -> List[str]:
    rag_root = _project_rag_root(project)
    if not rag_root:
        return []
    router_root = rag_root / "routerrag"
    if not router_root.exists():
        return []
    topics = []
    for child in router_root.iterdir():
        if not child.is_dir():
            continue
        if (child / "normal_db").exists() or (child / "vector_db").exists():
            topics.append(child.name.replace("数据库", ""))
    return topics


def _fetch_dir_for_range(project: str, start: str, end: str) -> Path:
    folder = f"{start}_{end}" if end and end != start else start
    return bucket("fetch", project, folder)


def _extract_texts_from_fetch(fetch_dir: Path) -> List[str]:
    text_cols = ["contents", "content", "text", "正文"]
    files: List[Path] = []
    overall = fetch_dir / "总体.jsonl"
    if overall.exists():
        files.append(overall)
    for candidate in sorted(fetch_dir.glob("*.jsonl")):
        if candidate not in files:
            files.append(candidate)

    if not files:
        return []

    texts: List[str] = []
    seen = set()

    def _add_text(value: object) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        if text in seen:
            return
        seen.add(text)
        texts.append(text)

    for path in files:
        df = None
        try:
            df = read_jsonl(path)
        except Exception:
            df = None
        if df is not None and not df.empty:
            text_col = next((c for c in text_cols if c in df.columns), None)
            if text_col:
                for value in df[text_col].fillna(""):
                    _add_text(value)
                if texts:
                    continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except Exception:
                        continue
                    for col in text_cols:
                        if col in payload:
                            _add_text(payload.get(col))
                            break
        except Exception:
            continue

    return texts


def ensure_tagrag_db(topic: str, project: str, fetch_dir: Optional[Path] = None) -> Optional[Path]:
    rag_root = _project_rag_root(project)
    if not rag_root:
        return None

    tagrag_root = rag_root / "tagrag"
    format_dir = tagrag_root / "format_db"
    vector_dir = tagrag_root / "vector_db"
    format_dir.mkdir(parents=True, exist_ok=True)
    vector_dir.mkdir(parents=True, exist_ok=True)

    try:
        db = lancedb.connect(str(vector_dir))
        if db.table_names() and any(name for name in db.table_names()):
            return vector_dir
    except Exception:
        pass

    logger = setup_logger(f"TagRAG_{project}", "default")

    if fetch_dir is None:
        log_error(logger, f"未提供fetch缓存，无法构建TagRAG: {project}", "TagRAG")
        return None

    _update_status(project, "tagrag", topic, "running", 10, "正在准备资料")

    texts = _extract_texts_from_fetch(fetch_dir)
    if not texts:
        log_error(logger, f"fetch缓存无可用文本，无法构建TagRAG: {project}", "TagRAG")
        _update_status(project, "tagrag", topic, "error", 100, "可用内容为空，稍后重试")
        return None

    _update_status(project, "tagrag", topic, "running", 35, "正在整理内容")

    data = {"data": []}
    for idx, text in enumerate(texts):
        data["data"].append({
            "id": idx,
            "text": text,
            "tag": text,
        })

    format_path = format_dir / f"{topic}.json"
    format_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log_success(logger, f"已生成TagRAG格式数据: {format_path}", "TagRAG")

    try:
        _update_status(project, "tagrag", topic, "running", 60, "正在建立索引")
        vectorize_and_store(
            topic_name=topic,
            format_json_path=str(format_path),
            vector_db_path=str(vector_dir),
        )
        _update_status(project, "tagrag", topic, "done", 100, "准备完成")
        return vector_dir
    except Exception as exc:
        log_error(logger, f"TagRAG向量化失败: {exc}", "TagRAG")
        _update_status(project, "tagrag", topic, "error", 100, "准备失败，请稍后重试")
        return None


def ensure_routerrag_db(topic: str, project: str, fetch_dir: Optional[Path] = None) -> Optional[Path]:
    rag_root = _project_rag_root(project)
    if not rag_root:
        return None

    base_path = rag_root / "routerrag" / f"{topic}数据库"
    vector_dir = base_path / "vector_db"
    if vector_dir.exists():
        return base_path

    logger = setup_logger(f"RouterRAG_{project}", "default")

    if fetch_dir is None:
        log_error(logger, f"未提供fetch缓存，无法构建RouterRAG: {project}", "RouterRAG")
        return None

    _update_status(project, "routerrag", topic, "running", 10, "正在准备资料")

    texts = _extract_texts_from_fetch(fetch_dir)
    if not texts:
        log_error(logger, f"fetch缓存无可用文本，无法构建RouterRAG: {project}", "RouterRAG")
        _update_status(project, "routerrag", topic, "error", 100, "可用内容为空，稍后重试")
        return None

    _update_status(project, "routerrag", topic, "running", 30, "正在整理内容")

    text_db = base_path / "normal_db" / "text_db"
    text_db.mkdir(parents=True, exist_ok=True)

    chunk_size = 3
    doc_id = 1
    for i in range(0, len(texts), chunk_size):
        chunk = texts[i : i + chunk_size]
        file_name = f"doc{doc_id}_{topic}_text1.txt"
        (text_db / file_name).write_text("\n\n---\n\n".join(chunk), encoding="utf-8")
        doc_id += 1

    try:
        _update_status(project, "routerrag", topic, "running", 70, "正在建立索引")
        ok = run_ragrouter(topic_name=topic, base_path=base_path)
        if ok:
            _update_status(project, "routerrag", topic, "done", 100, "准备完成")
            return base_path
        _update_status(project, "routerrag", topic, "error", 100, "准备失败，请稍后重试")
        return None
    except Exception as exc:
        log_error(logger, f"RouterRAG向量化失败: {exc}", "RouterRAG")
        _update_status(project, "routerrag", topic, "error", 100, "准备失败，请稍后重试")
        return None


def start_rag_build(
    project: str,
    rag_type: str,
    topic: str,
    *,
    db_topic: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    status = get_rag_build_status(project, rag_type, topic)
    if status.get("status") == "running":
        return status

    def _run():
        try:
            source_topic = db_topic or topic
            range_start = start
            range_end = end
            if not range_start or not range_end:
                avail = get_topic_available_date_range(source_topic)
                if isinstance(avail, dict):
                    range_start = avail.get("start")
                    range_end = avail.get("end")
                else:
                    range_start, range_end = avail
            if not range_start or not range_end:
                _update_status(project, rag_type, topic, "error", 100, "未找到可用数据范围")
                return

            output_date = f"{range_start}_{range_end}" if range_end and range_end != range_start else range_start
            logger = setup_logger(f"RAGBuild_{project}", output_date)
            ok = fetch_range(project, range_start, range_end, output_date, logger, db_topic=source_topic)
            if not ok:
                _update_status(project, rag_type, topic, "error", 100, "资料准备失败")
                return

            fetch_dir = _fetch_dir_for_range(project, range_start, range_end)
            if rag_type == "tagrag":
                ensure_tagrag_db(topic, project, fetch_dir=fetch_dir)
            else:
                ensure_routerrag_db(topic, project, fetch_dir=fetch_dir)
        except Exception:
            _update_status(project, rag_type, topic, "error", 100, "准备失败，请稍后重试")

    _update_status(project, rag_type, topic, "running", 5, "开始准备")
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return get_rag_build_status(project, rag_type, topic)


def ensure_rag_ready(project: str, rag_type: str, topic: str) -> bool:
    if rag_type == "tagrag":
        return _tagrag_db_ready(topic, project)
    return _routerrag_db_ready(topic, project)
