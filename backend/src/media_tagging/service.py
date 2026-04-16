from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from uuid import uuid4

import pandas as pd

from server_support.archive_locator import compose_folder_name
from src.utils.setting.paths import bucket, ensure_bucket, get_data_root

ALLOWED_MEDIA_LEVELS = {"official_media", "local_media"}
REGISTRY_ROOT = get_data_root() / "_media_registry"
REGISTRY_PATH = REGISTRY_ROOT / "registry.json"
DEFAULT_SAMPLE_LIMIT = 3
READ_CHUNK_SIZE = 2000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def normalize_publisher_name(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    text = re.sub(r"[\u3000\s]+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("【", "[").replace("】", "]")
    text = text.replace("“", '"').replace("”", '"')
    return text.casefold()


def _ensure_registry_root() -> None:
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def _sanitize_aliases(values: Any) -> List[str]:
    aliases: List[str] = []
    seen: set[str] = set()
    if isinstance(values, str):
        source = re.split(r"[\n,，;；]", values)
    elif isinstance(values, list):
        source = values
    else:
        source = []
    for item in source:
        text = _safe_text(item)
        if not text:
            continue
        key = normalize_publisher_name(text)
        if not key or key in seen:
            continue
        seen.add(key)
        aliases.append(text)
    return aliases


def _sanitize_registry_item(item: Dict[str, Any]) -> Dict[str, Any]:
    name = _safe_text(item.get("name"))
    normalized_name = normalize_publisher_name(item.get("normalized_name") or name)
    aliases = _sanitize_aliases(item.get("aliases"))
    media_level = _safe_text(item.get("media_level"))
    if media_level not in ALLOWED_MEDIA_LEVELS:
        media_level = ""
    status = _safe_text(item.get("status")) or ("active" if media_level else "draft")
    return {
        "id": _safe_text(item.get("id")) or f"mr-{uuid4().hex[:10]}",
        "name": name,
        "normalized_name": normalized_name,
        "aliases": aliases,
        "media_level": media_level,
        "status": status,
        "notes": _safe_text(item.get("notes")),
        "updated_at": _safe_text(item.get("updated_at")) or _utc_now(),
    }


def load_media_registry() -> Dict[str, Any]:
    _ensure_registry_root()
    payload = _load_json(REGISTRY_PATH, {})
    raw_items = payload.get("items") if isinstance(payload, dict) else []
    items = [_sanitize_registry_item(item) for item in raw_items if isinstance(item, dict)]
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return {
        "items": items,
        "updated_at": _safe_text(payload.get("updated_at")) if isinstance(payload, dict) else "",
    }


def save_media_registry(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    sanitized = [_sanitize_registry_item(item) for item in items if isinstance(item, dict)]
    payload = {
        "items": sanitized,
        "updated_at": _utc_now(),
    }
    _write_json(REGISTRY_PATH, payload)
    return payload


def list_registry_items(*, label: str = "", search: str = "") -> List[Dict[str, Any]]:
    payload = load_media_registry()
    items = payload.get("items") if isinstance(payload, dict) else []
    result: List[Dict[str, Any]] = []
    query = normalize_publisher_name(search)
    for item in items:
        if not isinstance(item, dict):
            continue
        if label and _safe_text(item.get("media_level")) != label:
            continue
        if query:
            haystacks = [
                normalize_publisher_name(item.get("name")),
                normalize_publisher_name(item.get("normalized_name")),
            ]
            haystacks.extend(normalize_publisher_name(alias) for alias in item.get("aliases") or [])
            if not any(query in hay for hay in haystacks if hay):
                continue
        result.append(dict(item))
    return result


def upsert_registry_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = load_media_registry()
    items = current.get("items") if isinstance(current, dict) else []
    requested_id = _safe_text(payload.get("id"))
    requested_name = _safe_text(payload.get("name"))
    requested_normalized = normalize_publisher_name(payload.get("normalized_name") or requested_name)
    updated_item = _sanitize_registry_item(
        {
            **payload,
            "normalized_name": requested_normalized,
            "updated_at": _utc_now(),
        }
    )

    replaced = False
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if requested_id and _safe_text(item.get("id")) == requested_id:
            items[index] = {**item, **updated_item}
            replaced = True
            break
        if requested_normalized and normalize_publisher_name(item.get("name")) == requested_normalized:
            items[index] = {**item, **updated_item, "id": _safe_text(item.get("id")) or updated_item["id"]}
            replaced = True
            break
    if not replaced:
        items.append(updated_item)
    save_media_registry(items)
    return updated_item


def _build_registry_index(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        keys = [
            normalize_publisher_name(item.get("name")),
            normalize_publisher_name(item.get("normalized_name")),
        ]
        keys.extend(normalize_publisher_name(alias) for alias in item.get("aliases") or [])
        for key in keys:
            if key and key not in index:
                index[key] = item
    return index


def _resolve_media_tags_dir(topic_identifier: str, start: str, end: Optional[str]) -> Path:
    folder = compose_folder_name(start, end or None)
    if folder:
        return bucket("media_tags", topic_identifier, folder)
    return bucket("media_tags", topic_identifier, start)


def _resolve_fetch_dir(topic_identifier: str, start: str, end: Optional[str]) -> Optional[Path]:
    folder_candidates = []
    composed = compose_folder_name(start, end or None)
    if composed:
        folder_candidates.append(composed)
    same_day = f"{start}_{start}"
    if start not in folder_candidates:
        folder_candidates.append(start)
    if same_day not in folder_candidates:
        folder_candidates.append(same_day)
    for folder in folder_candidates:
        target = bucket("fetch", topic_identifier, folder)
        if target.exists() and target.is_dir():
            return target
    return None


def _iter_input_files(fetch_dir: Path) -> List[Path]:
    overall = fetch_dir / "总体.jsonl"
    if overall.exists():
        return [overall]
    return sorted(path for path in fetch_dir.glob("*.jsonl") if path.is_file())


def _iter_jsonl_records(file_path: Path) -> Iterable[Dict[str, Any]]:
    try:
        reader = pd.read_json(file_path, lines=True, chunksize=READ_CHUNK_SIZE)
    except ValueError:
        reader = []
    for chunk in reader:
        if chunk is None or chunk.empty:
            continue
        for record in chunk.to_dict(orient="records"):
            if isinstance(record, dict):
                yield record


def _parse_timestamp(value: str) -> datetime:
    text = _safe_text(value)
    if not text:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _append_sample(samples: List[Dict[str, Any]], sample: Dict[str, Any], limit: int) -> None:
    if len(samples) >= limit:
        return
    key = (_safe_text(sample.get("url")), _safe_text(sample.get("title")), _safe_text(sample.get("published_at")))
    for existing in samples:
        existing_key = (
            _safe_text(existing.get("url")),
            _safe_text(existing.get("title")),
            _safe_text(existing.get("published_at")),
        )
        if key == existing_key:
            return
    samples.append(sample)


def _build_summary(topic_identifier: str, start: str, end: str, fetch_dir: Path, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    official_count = sum(1 for item in candidates if item.get("current_label") == "official_media")
    local_count = sum(1 for item in candidates if item.get("current_label") == "local_media")
    return {
        "topic_identifier": topic_identifier,
        "range": {
            "start": start,
            "end": end,
            "folder": compose_folder_name(start, end),
        },
        "fetch_dir": str(fetch_dir),
        "generated_at": _utc_now(),
        "total_candidates": len(candidates),
        "labeled_count": official_count + local_count,
        "official_media_count": official_count,
        "local_media_count": local_count,
    }


def run_media_tagging(
    topic_identifier: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    topic_identifier = _safe_text(topic_identifier)
    start_date = _safe_text(start_date)
    end_text = _safe_text(end_date) or start_date
    fetch_dir = _resolve_fetch_dir(topic_identifier, start_date, end_date)
    if fetch_dir is None:
        raise FileNotFoundError("未找到对应时间范围的本地缓存，请先同步远程数据到本地。")

    registry_payload = load_media_registry()
    registry_items = registry_payload.get("items") if isinstance(registry_payload, dict) else []
    registry_index = _build_registry_index(registry_items)

    files = _iter_input_files(fetch_dir)
    if not files:
        raise FileNotFoundError("当前时间范围下没有可识别的本地数据文件。")

    aggregates: Dict[str, Dict[str, Any]] = {}
    total_files = len(files)
    processed_files = 0

    for file_path in files:
        for record in _iter_jsonl_records(file_path):
            publisher_name = _safe_text(record.get("publisher"))
            if not publisher_name:
                publisher_name = _safe_text(record.get("author"))
            normalized_name = normalize_publisher_name(publisher_name)
            if not publisher_name or not normalized_name:
                continue
            item = aggregates.setdefault(
                normalized_name,
                {
                    "publisher_name": publisher_name,
                    "normalized_name": normalized_name,
                    "publish_count": 0,
                    "platforms": set(),
                    "samples": [],
                    "latest_published_at": "",
                },
            )
            item["publish_count"] += 1
            platform = _safe_text(record.get("platform"))
            if platform:
                item["platforms"].add(platform)
            published_at = _safe_text(record.get("published_at"))
            if _parse_timestamp(published_at) > _parse_timestamp(item.get("latest_published_at", "")):
                item["latest_published_at"] = published_at
            sample = {
                "title": _safe_text(record.get("title")),
                "url": _safe_text(record.get("url")),
                "published_at": published_at,
                "platform": platform,
            }
            _append_sample(item["samples"], sample, max(int(sample_limit or DEFAULT_SAMPLE_LIMIT), 1))

        processed_files += 1
        if progress_callback:
            progress_callback(
                {
                    "phase": "collect",
                    "percentage": int(processed_files / max(total_files, 1) * 85),
                    "message": f"正在整理媒体候选（{processed_files}/{total_files}）",
                    "total_files": total_files,
                    "processed_files": processed_files,
                    "current_file": file_path.name,
                    "candidate_count": len(aggregates),
                }
            )

    candidates: List[Dict[str, Any]] = []
    for normalized_name, item in aggregates.items():
        matched = registry_index.get(normalized_name)
        current_label = _safe_text(matched.get("media_level")) if matched else ""
        if current_label not in ALLOWED_MEDIA_LEVELS:
            current_label = ""
        candidate = {
            "publisher_name": item["publisher_name"],
            "normalized_name": normalized_name,
            "publish_count": int(item["publish_count"]),
            "matched_registry_id": _safe_text(matched.get("id")) if matched else "",
            "matched_registry_name": _safe_text(matched.get("name")) if matched else "",
            "current_label": current_label,
            "sample_count": len(item["samples"]),
            "latest_published_at": _safe_text(item.get("latest_published_at")),
            "platforms": sorted(item["platforms"]),
            "samples": item["samples"],
        }
        candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            -int(item.get("publish_count") or 0),
            -_parse_timestamp(item.get("latest_published_at")).timestamp(),
            _safe_text(item.get("publisher_name")),
        )
    )

    result_dir = ensure_bucket("media_tags", topic_identifier, compose_folder_name(start_date, end_text))
    summary = _build_summary(topic_identifier, start_date, end_text, fetch_dir, candidates)
    summary_path = result_dir / "summary.json"
    candidates_path = result_dir / "candidates.json"
    _write_json(summary_path, summary)
    _write_json(candidates_path, {"generated_at": _utc_now(), "candidates": candidates})

    if progress_callback:
        progress_callback(
            {
                "phase": "persist",
                "percentage": 100,
                "message": f"媒体候选整理完成，共识别 {len(candidates)} 个候选媒体。",
                "total_files": total_files,
                "processed_files": total_files,
                "current_file": "",
                "candidate_count": len(candidates),
            }
        )

    return {
        "status": "ok",
        "summary": summary,
        "candidates": candidates,
        "summary_path": str(summary_path),
        "candidates_path": str(candidates_path),
    }


def read_media_tagging_result(topic_identifier: str, start_date: str, end_date: Optional[str] = None) -> Dict[str, Any]:
    end_text = _safe_text(end_date) or _safe_text(start_date)
    result_dir = _resolve_media_tags_dir(topic_identifier, start_date, end_date)
    summary_path = result_dir / "summary.json"
    candidates_path = result_dir / "candidates.json"
    summary = _load_json(summary_path, {})
    candidates_payload = _load_json(candidates_path, {})
    candidates = candidates_payload.get("candidates") if isinstance(candidates_payload, dict) else []
    if not isinstance(summary, dict) or not isinstance(candidates, list):
        raise FileNotFoundError("未找到对应的媒体打标结果。")
    registry_items = list_registry_items()
    return {
        "topic_identifier": topic_identifier,
        "range": {
            "start": start_date,
            "end": end_text,
            "folder": compose_folder_name(start_date, end_text),
        },
        "summary": summary,
        "candidates": candidates,
        "registry": registry_items,
    }


def _rebuild_summary_from_candidates(summary: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    updated = dict(summary or {})
    official_count = sum(1 for item in candidates if _safe_text(item.get("current_label")) == "official_media")
    local_count = sum(1 for item in candidates if _safe_text(item.get("current_label")) == "local_media")
    updated["generated_at"] = _utc_now()
    updated["total_candidates"] = len(candidates)
    updated["official_media_count"] = official_count
    updated["local_media_count"] = local_count
    updated["labeled_count"] = official_count + local_count
    return updated


def update_media_tagging_labels(
    topic_identifier: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
    updates: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    payload = read_media_tagging_result(topic_identifier, start_date, end_date)
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    registry_payload = load_media_registry()
    registry_items = registry_payload.get("items") if isinstance(registry_payload, dict) else []
    registry_index = _build_registry_index(registry_items)
    update_list = updates or []

    candidate_map = {
        normalize_publisher_name(item.get("publisher_name")): item
        for item in candidates
        if isinstance(item, dict)
    }

    for update in update_list:
        if not isinstance(update, dict):
            continue
        key = normalize_publisher_name(update.get("publisher_name"))
        candidate = candidate_map.get(key)
        if not candidate:
            continue
        requested_label = _safe_text(update.get("current_label"))
        if requested_label not in ALLOWED_MEDIA_LEVELS:
            requested_label = ""
        registry_name = _safe_text(update.get("registry_name")) or _safe_text(candidate.get("matched_registry_name")) or _safe_text(candidate.get("publisher_name"))
        aliases = _sanitize_aliases(update.get("aliases"))
        notes = _safe_text(update.get("notes"))

        existing_registry = registry_index.get(normalize_publisher_name(registry_name)) or registry_index.get(candidate.get("normalized_name"))
        registry_payload_item = {
            "id": _safe_text(existing_registry.get("id")) if existing_registry else _safe_text(candidate.get("matched_registry_id")),
            "name": registry_name,
            "normalized_name": normalize_publisher_name(registry_name),
            "aliases": aliases or (existing_registry.get("aliases") if isinstance(existing_registry, dict) else []),
            "media_level": requested_label,
            "status": "active" if requested_label else "draft",
            "notes": notes or (existing_registry.get("notes") if isinstance(existing_registry, dict) else ""),
        }
        if candidate.get("publisher_name") and normalize_publisher_name(candidate.get("publisher_name")) != normalize_publisher_name(registry_name):
            combined_aliases = _sanitize_aliases([candidate.get("publisher_name"), *(registry_payload_item.get("aliases") or [])])
            registry_payload_item["aliases"] = combined_aliases
        registry_item = upsert_registry_item(registry_payload_item)
        registry_index = _build_registry_index(list_registry_items())

        candidate["matched_registry_id"] = _safe_text(registry_item.get("id"))
        candidate["matched_registry_name"] = _safe_text(registry_item.get("name"))
        candidate["current_label"] = requested_label

    updated_summary = _rebuild_summary_from_candidates(summary, candidates)
    result_dir = _resolve_media_tags_dir(topic_identifier, start_date, end_date)
    _write_json(result_dir / "summary.json", updated_summary)
    _write_json(result_dir / "candidates.json", {"generated_at": _utc_now(), "candidates": candidates})
    return read_media_tagging_result(topic_identifier, start_date, end_date)


def build_labeled_media_payload(
    topic_identifier: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
    label: str = "",
) -> Dict[str, Any]:
    payload = read_media_tagging_result(topic_identifier, start_date, end_date)
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    registry_index = _build_registry_index(list_registry_items())
    labeled: List[Dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        current_label = _safe_text(item.get("current_label"))
        if current_label not in ALLOWED_MEDIA_LEVELS:
            continue
        if label and current_label != label:
            continue
        registry = registry_index.get(normalize_publisher_name(item.get("matched_registry_name"))) or registry_index.get(item.get("normalized_name"))
        labeled.append(
            {
                "name": _safe_text(item.get("matched_registry_name")) or _safe_text(item.get("publisher_name")),
                "aliases": _sanitize_aliases((registry or {}).get("aliases") if isinstance(registry, dict) else []),
                "media_level": current_label,
                "publish_count": int(item.get("publish_count") or 0),
                "topic_hit_count": int(item.get("publish_count") or 0),
                "sample_titles": [_safe_text(sample.get("title")) for sample in item.get("samples") or [] if _safe_text(sample.get("title"))],
            }
        )
    official = [item for item in labeled if item.get("media_level") == "official_media"]
    local = [item for item in labeled if item.get("media_level") == "local_media"]
    return {
        "topic_identifier": topic_identifier,
        "range": payload.get("range") or {},
        "official_media": official,
        "local_media": local,
        "all_labeled_media": labeled,
    }


__all__ = [
    "ALLOWED_MEDIA_LEVELS",
    "build_labeled_media_payload",
    "list_registry_items",
    "load_media_registry",
    "normalize_publisher_name",
    "read_media_tagging_result",
    "run_media_tagging",
    "upsert_registry_item",
    "update_media_tagging_labels",
]
