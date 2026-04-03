from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from filelock import FileLock

from src.topic.config import load_bertopic_stopwords  # type: ignore
from src.topic.prompt_config import load_topic_bertopic_prompt_config  # type: ignore
from src.utils.setting.paths import get_data_root  # type: ignore

LOGGER = logging.getLogger(__name__)

STATE_ROOT = get_data_root() / "_stopword_suggestions"
TASK_STATE_DIR = STATE_ROOT / "tasks"
WORKER_STATUS_PATH = STATE_ROOT / "worker.json"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
DEFAULT_TOP_K = 100
MIN_TOKEN_LENGTH = 2
EN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,31}")
ZH_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+")
URL_TOKEN_RE = re.compile(r"^(https?://|www\.)", re.I)
_SAFE_TERM_RE = re.compile(r"^[\W_]+$", re.UNICODE)
STAGE_SOURCE_PRIORITY = {
    "pre": ("clean", "fetch"),
    "post": ("filter", "clean", "fetch"),
}

DEFAULT_EN_STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "been", "before", "being", "below",
    "between", "both", "but", "can", "could", "did", "does", "doing", "down", "during",
    "each", "few", "for", "from", "further", "had", "has", "have", "having", "her", "here",
    "hers", "him", "his", "how", "into", "its", "itself", "just", "more", "most", "not",
    "off", "once", "only", "other", "our", "ours", "out", "over", "same", "should", "some",
    "such", "than", "that", "the", "their", "theirs", "them", "then", "there", "these",
    "they", "this", "those", "through", "under", "until", "very", "was", "were", "what",
    "when", "where", "which", "while", "who", "will", "with", "would", "you", "your",
}

try:
    import jieba  # type: ignore

    JIEBA_AVAILABLE = True
    jieba.setLogLevel(60)
except Exception:  # pragma: no cover - optional dependency
    jieba = None
    JIEBA_AVAILABLE = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _ensure_state_dirs() -> None:
    TASK_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return default


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Optional[Exception] = None
    for attempt in range(6):
        tmp_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            os.replace(str(tmp_path), str(path))
            return
        except Exception as exc:
            last_error = exc
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


def task_state_path(task_id: str) -> Path:
    _ensure_state_dirs()
    return TASK_STATE_DIR / f"{task_id}.json"


def _load_all_tasks() -> List[Dict[str, Any]]:
    _ensure_state_dirs()
    tasks: List[Dict[str, Any]] = []
    for path in TASK_STATE_DIR.glob("*.json"):
        payload = _load_json(path, {})
        if isinstance(payload, dict) and payload.get("id"):
            tasks.append(payload)
    return tasks


def _load_task(task_id: str) -> Optional[Dict[str, Any]]:
    payload = _load_json(task_state_path(task_id), {})
    return payload if isinstance(payload, dict) and payload.get("id") else None


def _save_task(task: Dict[str, Any]) -> None:
    path = task_state_path(str(task.get("id") or ""))
    lock = FileLock(str(path) + ".lock")
    with lock:
        task["updated_at"] = _utc_now()
        _atomic_write_json(path, task)


def _update_task(task_id: str, mutate) -> Dict[str, Any]:
    path = task_state_path(task_id)
    lock = FileLock(str(path) + ".lock")
    with lock:
        task = _load_json(path, {})
        if not isinstance(task, dict) or not task.get("id"):
            raise LookupError("未找到排除词建议任务")
        mutate(task)
        task["updated_at"] = _utc_now()
        _atomic_write_json(path, task)
        return task


def _new_task_id() -> str:
    return f"sw-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _normalise_term(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def _split_terms(text: str) -> List[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _load_excluded_terms(topic_identifier: str) -> set[str]:
    prompt_payload = load_topic_bertopic_prompt_config(topic_identifier)
    prompt_terms = prompt_payload.get("project_stopwords") or []
    global_payload = load_bertopic_stopwords()
    global_terms = _split_terms(str(global_payload.get("content") or ""))
    excluded = {_normalise_term(term) for term in prompt_terms}
    excluded.update(_normalise_term(term) for term in global_terms)
    excluded.update(DEFAULT_EN_STOPWORDS)
    return {item for item in excluded if item}


def _iter_text_fields(record: Dict[str, Any]) -> Iterable[str]:
    for key in ("title", "contents", "hit_words", "summary", "content"):
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            joined = " ".join(str(item or "") for item in value)
            if joined.strip():
                yield joined
            continue
        text = str(value).strip()
        if text:
            yield text


def _looks_like_noise_token(token: str) -> bool:
    if not token:
        return True
    if len(token) < MIN_TOKEN_LENGTH:
        return True
    if URL_TOKEN_RE.match(token):
        return True
    if token.isdigit():
        return True
    if _SAFE_TERM_RE.match(token):
        return True
    return False


def _iter_tokens(text: str, excluded_terms: set[str]) -> Iterable[str]:
    source = str(text or "").strip()
    if not source:
        return

    if JIEBA_AVAILABLE:
        for raw in jieba.lcut(source, cut_all=False):
            token = str(raw or "").strip()
            if _looks_like_noise_token(token):
                continue
            if not ZH_TOKEN_RE.search(token):
                continue
            normalised = _normalise_term(token)
            if normalised in excluded_terms or len(normalised) < MIN_TOKEN_LENGTH:
                continue
            yield token
    else:  # pragma: no cover - fallback path
        for token in ZH_TOKEN_RE.findall(source):
            token = token.strip()
            if _looks_like_noise_token(token):
                continue
            normalised = _normalise_term(token)
            if normalised in excluded_terms or len(normalised) < MIN_TOKEN_LENGTH:
                continue
            yield token

    for raw in EN_TOKEN_RE.findall(source):
        token = str(raw or "").strip().lower()
        if _looks_like_noise_token(token):
            continue
        if token in excluded_terms:
            continue
        yield token


def _build_top_terms(
    doc_counter: Counter[str],
    total_counter: Counter[str],
    *,
    total_docs: int,
    top_k: int,
) -> List[Dict[str, Any]]:
    ranked = sorted(
        doc_counter.items(),
        key=lambda item: (-item[1], -int(total_counter.get(item[0], 0)), item[0]),
    )
    results: List[Dict[str, Any]] = []
    for term, doc_count in ranked[: max(top_k, 1)]:
        total_count = int(total_counter.get(term, 0))
        results.append(
            {
                "term": term,
                "doc_count": int(doc_count),
                "total_count": total_count,
                "doc_ratio": round(doc_count / max(total_docs, 1), 4),
            }
        )
    return results


def create_task(
    topic_identifier: str,
    date: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    stage: str = "pre",
) -> Dict[str, Any]:
    now = _utc_now()
    task = {
        "id": _new_task_id(),
        "topic_identifier": str(topic_identifier or "").strip(),
        "date": str(date or "").strip(),
        "stage": str(stage or "pre").strip().lower() or "pre",
        "source_layer": "",
        "status": "queued",
        "phase": "queued",
        "percentage": 0,
        "message": "等待高频词 worker 接单。",
        "top_k": max(_safe_int(top_k, DEFAULT_TOP_K), 20),
        "worker_pid": 0,
        "error": "",
        "summary": {
            "total_files": 0,
            "processed_files": 0,
            "total_docs": 0,
            "processed_docs": 0,
            "distinct_terms": 0,
        },
        "result": {
            "terms": [],
        },
        "created_at": now,
        "updated_at": now,
        "started_at": "",
        "finished_at": "",
    }
    _save_task(task)
    return task


def get_task(task_id: str) -> Dict[str, Any]:
    task = _load_task(task_id)
    if not task:
        raise LookupError("未找到排除词建议任务")
    return task


def find_latest_task(
    topic_identifier: str,
    date: str,
    *,
    stage: str = "pre",
    statuses: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    desired_statuses = set(statuses or [])
    matches = []
    for task in _load_all_tasks():
        if str(task.get("topic_identifier") or "") != topic_identifier:
            continue
        if str(task.get("date") or "") != date:
            continue
        if str(task.get("stage") or "pre") != str(stage or "pre"):
            continue
        if desired_statuses and str(task.get("status") or "") not in desired_statuses:
            continue
        matches.append(task)
    if not matches:
        return None
    matches.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return matches[0]


def create_or_reuse_task(
    topic_identifier: str,
    date: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    stage: str = "pre",
    force: bool = False,
) -> Dict[str, Any]:
    running_task = find_latest_task(topic_identifier, date, stage=stage, statuses=["queued", "running"])
    if running_task:
        return running_task
    if not force:
        completed_task = find_latest_task(topic_identifier, date, stage=stage, statuses=["completed"])
        if completed_task:
            return completed_task
    task = create_task(topic_identifier, date, top_k=top_k, stage=stage)
    ensure_worker_running()
    return task


def get_latest_task(topic_identifier: str, date: str, *, stage: str = "pre") -> Optional[Dict[str, Any]]:
    return find_latest_task(topic_identifier, date, stage=stage)


def reserve_next_task() -> Optional[Dict[str, Any]]:
    queued = sorted(
        (item for item in _load_all_tasks() if str(item.get("status") or "") == "queued"),
        key=lambda item: item.get("created_at") or "",
    )
    if not queued:
        return None
    task_id = str(queued[0].get("id") or "")
    if not task_id:
        return None
    return mark_task_progress(
        task_id,
        status="running",
        phase="prepare",
        percentage=1,
        message="worker 已接单，正在统计文档规模。",
    )


def load_worker_status() -> Dict[str, Any]:
    _ensure_state_dirs()
    status = _load_json(WORKER_STATUS_PATH, {})
    if not isinstance(status, dict):
        status = {}
    pid = _safe_int(status.get("pid"), 0)
    running = pid > 0 and _is_process_alive(pid)
    status["running"] = running
    if not running and status.get("status") in {"starting", "idle", "running"}:
        status["status"] = "stopped"
    return status


def write_worker_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_state_dirs()
    status = dict(payload or {})
    status["updated_at"] = _utc_now()
    _atomic_write_json(WORKER_STATUS_PATH, status)
    return status


def ensure_worker_running() -> Dict[str, Any]:
    _ensure_state_dirs()
    worker_lock = FileLock(str(WORKER_STATUS_PATH) + ".lock")
    with worker_lock:
        current = _load_json(WORKER_STATUS_PATH, {})
        pid = _safe_int((current or {}).get("pid"), 0)
        if pid > 0 and _is_process_alive(pid):
            current["running"] = True
            return current

        _reconcile_orphaned_running_tasks({"running": False})
        worker_script = Path(__file__).resolve().parent / "stopword_suggestions_worker.py"
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [sys.executable, str(worker_script)],
            cwd=str(Path(__file__).resolve().parents[1]),
            creationflags=creation_flags,
        )
        status = {
            "pid": process.pid,
            "status": "starting",
            "running": True,
            "current_task_id": "",
            "last_heartbeat": _utc_now(),
            "started_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        _atomic_write_json(WORKER_STATUS_PATH, status)
        return status


def mark_task_progress(
    task_id: str,
    *,
    status: str,
    phase: str,
    percentage: int,
    message: str,
    summary: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    def _mutate(task: Dict[str, Any]) -> None:
        current_status = str(task.get("status") or "")
        if status == "running" and current_status == "queued":
            task["started_at"] = task.get("started_at") or _utc_now()
        task["status"] = status
        task["phase"] = phase
        task["percentage"] = max(0, min(100, int(percentage)))
        task["message"] = message
        task["worker_pid"] = _safe_int(task.get("worker_pid"), 0) or os.getpid()
        task["error"] = error
        if isinstance(summary, dict):
            merged = dict(task.get("summary") or {})
            merged.update(summary)
            task["summary"] = merged
        if isinstance(result, dict):
            merged_result = dict(task.get("result") or {})
            merged_result.update(result)
            task["result"] = merged_result
        if status in TERMINAL_STATUSES:
            task["finished_at"] = _utc_now()

    return _update_task(task_id, _mutate)


def _reconcile_orphaned_running_tasks(worker_status: Dict[str, Any]) -> None:
    if worker_status.get("running"):
        return
    for task in _load_all_tasks():
        if str(task.get("status") or "") != "running":
            continue
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        mark_task_progress(
            task_id,
            status="failed",
            phase="failed",
            percentage=max(_safe_int(task.get("percentage"), 0), 1),
            message="worker 已停止，任务被标记为失败。",
            error="worker 已停止，任务被标记为失败。",
        )


def build_status_payload(topic_identifier: str, date: str, *, stage: str = "pre") -> Dict[str, Any]:
    task = get_latest_task(topic_identifier, date, stage=stage)
    return {
        "topic_identifier": topic_identifier,
        "date": date,
        "stage": stage,
        "task": task,
        "worker": load_worker_status(),
    }


def _source_dir(topic_identifier: str, layer: str, date: str) -> Path:
    return get_data_root() / "projects" / topic_identifier / layer / date


def _pick_source_layer(topic_identifier: str, date: str, stage: str) -> tuple[str, List[Path]]:
    priorities = STAGE_SOURCE_PRIORITY.get(str(stage or "pre"), STAGE_SOURCE_PRIORITY["pre"])
    for layer in priorities:
        layer_dir = _source_dir(topic_identifier, layer, date)
        files = sorted(path for path in layer_dir.glob("*.jsonl") if path.is_file())
        if files:
            return layer, files
    checked = ", ".join(priorities)
    raise FileNotFoundError(f"未找到可用的数据源，已检查: {checked}")


def analyse_archive_terms(
    topic_identifier: str,
    date: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    stage: str = "pre",
    progress_callback=None,
) -> Dict[str, Any]:
    source_layer, files = _pick_source_layer(topic_identifier, date, stage)
    if not files:
        raise FileNotFoundError("未找到可用的数据源文件")

    excluded_terms = _load_excluded_terms(topic_identifier)
    total_docs = 0
    for file_path in files:
        with file_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                if raw_line.strip():
                    total_docs += 1

    processed_docs = 0
    doc_counter: Counter[str] = Counter()
    total_counter: Counter[str] = Counter()
    total_files = len(files)

    if progress_callback:
        progress_callback(
            "analyze",
            8,
            f"已完成规模统计，共 {total_files} 个文件、{total_docs} 条文档。",
            {
                "total_files": total_files,
                "processed_files": 0,
                "total_docs": total_docs,
                "processed_docs": 0,
                "source_layer": source_layer,
            },
        )

    for index, file_path in enumerate(files, start=1):
        with file_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                document_tokens: List[str] = []
                for text in _iter_text_fields(payload):
                    document_tokens.extend(_iter_tokens(text, excluded_terms))
                if document_tokens:
                    total_counter.update(document_tokens)
                    doc_counter.update(set(document_tokens))
                processed_docs += 1

        if progress_callback:
            percentage = 8 + int(index / max(total_files, 1) * 87)
            progress_callback(
                "analyze",
                percentage,
                f"已处理 {index}/{total_files} 个文件。",
                {
                    "total_files": total_files,
                    "processed_files": index,
                    "total_docs": total_docs,
                    "processed_docs": processed_docs,
                    "source_layer": source_layer,
                },
            )

    return {
        "summary": {
            "total_files": total_files,
            "processed_files": total_files,
            "total_docs": total_docs,
            "processed_docs": processed_docs,
            "distinct_terms": len(doc_counter),
            "excluded_terms": len(excluded_terms),
            "source_layer": source_layer,
        },
        "result": {
            "terms": _build_top_terms(doc_counter, total_counter, total_docs=processed_docs, top_k=top_k),
        },
    }


__all__ = [
    "analyse_archive_terms",
    "build_status_payload",
    "create_or_reuse_task",
    "ensure_worker_running",
    "get_task",
    "load_worker_status",
    "mark_task_progress",
    "reserve_next_task",
    "task_state_path",
    "write_worker_status",
]
