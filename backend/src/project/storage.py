"""Utilities for storing per-project tabular datasets."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pandas as pd
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..utils.io.excel import read_jsonl, write_jsonl

__all__ = [
    "normalise_project_name",
    "get_dataset_metadata",
    "find_dataset_by_id",
    "store_uploaded_dataset",
    "list_project_datasets",
    "get_dataset_preview",
    "get_dataset_date_summary",
    "update_dataset_column_mapping",
]

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent
_DATA_ROOT = _BACKEND_ROOT / "data" / "projects"
_MANIFEST_FILENAME = "manifest.json"
_ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".jsonl"}


def _normalise_project_name(name: str) -> str:
    """Convert the project name into a filesystem friendly slug."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("- ")
    return cleaned.lower() or "project"


def normalise_project_name(name: str) -> str:
    """Public helper to normalise project identifiers."""
    return _normalise_project_name(str(name or ""))


def _ensure_directories(project: str) -> Dict[str, Path]:
    slug = _normalise_project_name(project)
    project_dir = _DATA_ROOT / slug
    uploads_dir = project_dir / "uploads"
    original_dir = uploads_dir / "original"
    jsonl_dir = uploads_dir / "jsonl"
    cache_dir = uploads_dir / "cache"
    meta_dir = uploads_dir / "meta"

    for path in (original_dir, jsonl_dir, cache_dir, meta_dir):
        path.mkdir(parents=True, exist_ok=True)

    return {
        "slug": slug,
        "project_dir": project_dir,
        "uploads_dir": uploads_dir,
        "original_dir": original_dir,
        "jsonl_dir": jsonl_dir,
        "cache_dir": cache_dir,
        "meta_dir": meta_dir,
    }


def _dataset_timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _load_dataframe(path: Path, extension: str) -> pd.DataFrame:
    if extension == ".csv":
        return pd.read_csv(path)
    if extension in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if extension == ".jsonl":
        return read_jsonl(path)
    raise ValueError(f"不支持的文件类型：{extension}")


def _manifest_path(project_slug: str) -> Path:
    return _DATA_ROOT / project_slug / "uploads" / _MANIFEST_FILENAME


def _write_manifest(project_slug: str, metadata: Dict) -> None:
    manifest_path = _manifest_path(project_slug)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"project": metadata.get("project", ""), "datasets": []}
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict) and isinstance(loaded.get("datasets"), list):
                manifest = loaded
        except Exception:
            manifest = {"project": metadata.get("project", ""), "datasets": []}
    datasets = [item for item in manifest.get("datasets", []) if item.get("id") != metadata.get("id")]
    datasets.append(metadata)
    datasets.sort(key=lambda item: item.get("stored_at", ""), reverse=True)
    manifest["datasets"] = datasets
    manifest["project"] = metadata.get("project", manifest.get("project", ""))
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)


def list_project_datasets(project: str) -> List[Dict]:
    """Return all datasets recorded for the given project."""

    if not project or not project.strip():
        raise ValueError("项目名称不能为空")
    slug = _normalise_project_name(project)
    manifest_path = _manifest_path(slug)
    if not manifest_path.exists():
        return []
    try:
        with manifest_path.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        datasets = manifest.get("datasets", []) if isinstance(manifest, dict) else []
        if isinstance(datasets, list):
            datasets = [item for item in datasets if isinstance(item, dict)]
            for item in datasets:
                dataset_id = str(item.get("id", ""))
                meta_path = _meta_path(slug, dataset_id) if dataset_id else None
                if meta_path and meta_path.exists():
                    try:
                        with meta_path.open("r", encoding="utf-8") as meta_fh:
                            meta_data = json.load(meta_fh)
                        if isinstance(meta_data, dict):
                            item.setdefault("columns", meta_data.get("columns", []))
                            if isinstance(meta_data.get("column_mapping"), dict):
                                item["column_mapping"] = _sanitize_column_mapping(
                                    meta_data.get("column_mapping"),
                                    [str(column) for column in item.get("columns", [])],
                                )
                            else:
                                item.setdefault("column_mapping", {})
                            topic_label_value = meta_data.get("topic_label", "")
                            if isinstance(topic_label_value, str):
                                item["topic_label"] = topic_label_value.strip()
                            else:
                                item.setdefault("topic_label", "")
                    except Exception:
                        item.setdefault("column_mapping", {})
                else:
                    if isinstance(item.get("column_mapping"), dict):
                        item["column_mapping"] = _sanitize_column_mapping(
                            item["column_mapping"],
                            [str(column) for column in item.get("columns", [])],
                        )
                    else:
                        item.setdefault("column_mapping", {})
                    topic_label_value = item.get("topic_label", "")
                    if isinstance(topic_label_value, str):
                        item["topic_label"] = topic_label_value.strip()
                    else:
                        item["topic_label"] = ""
            datasets.sort(key=lambda item: item.get("stored_at", ""), reverse=True)
            return datasets
    except Exception:
        return []
    return []


def _stringify_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _resolve_dataset_metadata(project: str, dataset_id: str) -> Dict[str, Any]:
    datasets = list_project_datasets(project)
    for item in datasets:
        if item.get("id") == dataset_id:
            return item
    raise LookupError("指定的数据集不存在或已被移除")


def get_dataset_metadata(project: str, dataset_id: str) -> Dict[str, Any]:
    """Public helper to load metadata for a dataset within a project."""
    if not project or not str(project).strip():
        raise ValueError("项目名称不能为空")
    if not dataset_id:
        raise ValueError("数据集编号不能为空")
    return _resolve_dataset_metadata(project, dataset_id)


def find_dataset_by_id(dataset_id: str) -> Optional[Dict[str, Any]]:
    """Locate dataset metadata by id across all projects."""
    dataset_id = str(dataset_id or "").strip()
    if not dataset_id:
        return None

    for project_dir in _DATA_ROOT.iterdir():
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name
        try:
            datasets = list_project_datasets(project_name)
        except ValueError:
            continue
        except Exception:
            continue
        for record in datasets:
            if record.get("id") == dataset_id:
                if "project_slug" not in record:
                    record["project_slug"] = normalise_project_name(record.get("project", project_name))
                return record
    return None


_DATE_KEYWORDS = (
    "date",
    "time",
    "publish",
    "发布时间",
    "发布日期",
    "时间",
    "日期",
)
_DATE_OPTION_LIMIT = 365

_TITLE_KEYWORDS = (
    "title",
    "headline",
    "subject",
    "题目",
    "标题",
    "主题",
)
_CONTENT_KEYWORDS = (
    "content",
    "text",
    "body",
    "article",
    "全文",
    "正文",
    "内容",
    "摘要",
)
_AUTHOR_KEYWORDS = (
    "author",
    "writer",
    "reporter",
    "editor",
    "作者",
    "记者",
    "博主",
)
_COLUMN_MAPPING_KEYS = ("date", "title", "content", "author")


def _normalise_column_name(column: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(column)).lower()


def _coerce_datetime_series(series: pd.Series) -> pd.Series:
    coerced = pd.to_datetime(series, errors="coerce", utc=False)

    valid_count = coerced.notna().sum()
    if valid_count == 0 and pd.api.types.is_numeric_dtype(series):
        # Attempt to interpret as Excel serial numbers
        excel_series = pd.to_datetime(series, errors="coerce", unit="d", origin="1899-12-30")
        if excel_series.notna().sum() > valid_count:
            coerced = excel_series

    if hasattr(coerced.dt, "tz") and coerced.dt.tz is not None:
        try:
            coerced = coerced.dt.tz_localize(None)
        except TypeError:
            pass
    return coerced.dropna()


def _candidate_datetime_columns(dataframe: pd.DataFrame) -> List[Tuple[str, pd.Series]]:
    candidates: List[Tuple[str, pd.Series]] = []
    for column in dataframe.columns:
        normalised = _normalise_column_name(column)
        if not any(keyword in normalised for keyword in _DATE_KEYWORDS):
            continue
        series = _coerce_datetime_series(dataframe[column])
        if not series.empty:
            candidates.append((str(column), series))
    if candidates:
        return candidates

    # Fallback: attempt to coerce any column
    for column in dataframe.columns:
        series = _coerce_datetime_series(dataframe[column])
        if not series.empty:
            candidates.append((str(column), series))
    return candidates


def _select_best_datetime_column(candidates: List[Tuple[str, pd.Series]]) -> Tuple[str, pd.Series]:
    if not candidates:
        raise ValueError("数据集中未找到可识别的日期列")
    # Prefer column with most valid entries; tie-breaker by earliest column index
    ranked = sorted(candidates, key=lambda item: (-len(item[1]), item[0]))
    column, series = ranked[0]
    return column, series


def _summarise_dates(series: pd.Series) -> Tuple[str, str, List[str]]:
    if series.empty:
        raise ValueError("日期列不包含有效数据")
    normalised = series.dt.normalize()
    unique_dates = sorted({value.date() for value in normalised.dropna()})
    if not unique_dates:
        raise ValueError("日期列不包含有效数据")
    formatted = [date.isoformat() for date in unique_dates]
    return formatted[0], formatted[-1], formatted


def _meta_path(project_slug: str, dataset_id: str) -> Path:
    return _DATA_ROOT / project_slug / "uploads" / "meta" / f"{dataset_id}.json"


def _infer_column_by_keywords(columns: List[str], keywords: Tuple[str, ...]) -> Optional[str]:
    for column in columns:
        normalised = _normalise_column_name(column)
        if any(keyword in normalised for keyword in keywords):
            return column
    return None


def _infer_textual_column(dataframe: pd.DataFrame, keywords: Tuple[str, ...]) -> Optional[str]:
    candidates: List[str] = []
    columns = [str(column) for column in dataframe.columns]
    for column in columns:
        normalised = _normalise_column_name(column)
        if any(keyword in normalised for keyword in keywords):
            candidates.append(column)
    if not candidates:
        return None

    # Prefer columns that contain longer text on average.
    best_column = candidates[0]
    best_length = -1
    for column in candidates:
        series = dataframe[column].dropna()
        if series.empty:
            continue
        sample = series.astype(str).str.len()
        avg_length = float(sample.mean()) if not sample.empty else 0.0
        if avg_length > best_length:
            best_length = avg_length
            best_column = column
    return best_column


def _sanitize_column_mapping(mapping: Optional[Dict[str, Any]], columns: List[str]) -> Dict[str, str]:
    available = {str(column) for column in columns}
    sanitized: Dict[str, str] = {}
    mapping = mapping or {}
    for key in _COLUMN_MAPPING_KEYS:
        value = mapping.get(key)
        if isinstance(value, str):
            value = value.strip()
            sanitized[key] = value if value in available else ""
        else:
            sanitized[key] = ""
    return sanitized


def _infer_column_mapping(dataframe: pd.DataFrame, hints: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    columns = [str(column) for column in dataframe.columns]
    hints = hints or {}

    mapping = {key: "" for key in _COLUMN_MAPPING_KEYS}
    sanitized_hints = _sanitize_column_mapping(hints, columns)

    # Date column: prefer hint, otherwise inference.
    date_hint = sanitized_hints.get("date")
    if date_hint:
        mapping["date"] = date_hint
    else:
        candidates = _candidate_datetime_columns(dataframe)
        if candidates:
            mapping["date"] = _select_best_datetime_column(candidates)[0]

    # Title column.
    title_hint = sanitized_hints.get("title")
    if title_hint:
        mapping["title"] = title_hint
    else:
        inferred_title = _infer_textual_column(dataframe, _TITLE_KEYWORDS)
        if inferred_title:
            mapping["title"] = inferred_title

    # Content column.
    content_hint = sanitized_hints.get("content")
    if content_hint:
        mapping["content"] = content_hint
    else:
        inferred_content = _infer_textual_column(dataframe, _CONTENT_KEYWORDS)
        if inferred_content:
            mapping["content"] = inferred_content

    # Author column.
    author_hint = sanitized_hints.get("author")
    if author_hint:
        mapping["author"] = author_hint
    else:
        inferred_author = _infer_column_by_keywords(columns, _AUTHOR_KEYWORDS)
        if inferred_author:
            mapping["author"] = inferred_author

    return _sanitize_column_mapping(mapping, columns)


def _latest_dataset_metadata(project: str) -> Dict[str, Any]:
    datasets = list_project_datasets(project)
    if not datasets:
        raise LookupError("未找到该专题的任何数据集")
    return datasets[0]


def get_dataset_date_summary(project: str, dataset_id: Optional[str] = None) -> Dict[str, Any]:
    """Analyse a stored dataset and return recognised date options."""

    if not project or not project.strip():
        raise ValueError("项目名称不能为空")

    metadata = _resolve_dataset_metadata(project, dataset_id) if dataset_id else _latest_dataset_metadata(project)

    pkl_path_str = metadata.get("pkl_file")
    if not pkl_path_str:
        raise LookupError("数据集缺少缓存文件")
    pkl_path = (_REPO_ROOT / pkl_path_str).resolve()
    if not pkl_path.exists():
        raise FileNotFoundError(f"未找到数据集缓存文件：{pkl_path}")

    dataframe = pd.read_pickle(pkl_path)
    if dataframe is None or dataframe.empty:
        raise ValueError("数据集为空，无法提取日期范围")

    column_mapping = metadata.get("column_mapping") if isinstance(metadata.get("column_mapping"), dict) else {}
    sanitized_mapping = _sanitize_column_mapping(column_mapping, [str(column) for column in dataframe.columns])

    preferred_column = sanitized_mapping.get("date")
    if preferred_column:
        preferred_series = _coerce_datetime_series(dataframe[preferred_column])
        if not preferred_series.empty:
            column = preferred_column
            series = preferred_series
        else:
            candidates = _candidate_datetime_columns(dataframe)
            column, series = _select_best_datetime_column(candidates)
    else:
        candidates = _candidate_datetime_columns(dataframe)
        column, series = _select_best_datetime_column(candidates)

    sanitized_mapping["date"] = column
    min_date, max_date, formatted = _summarise_dates(series)

    limited_values = formatted[-_DATE_OPTION_LIMIT:] if _DATE_OPTION_LIMIT else formatted
    return {
        "dataset": {
            "id": metadata.get("id"),
            "display_name": metadata.get("display_name"),
            "stored_at": metadata.get("stored_at"),
            "rows": metadata.get("rows"),
            "column_count": metadata.get("column_count"),
            "topic_label": metadata.get("topic_label", ""),
        },
        "date_column": column,
        "unique_date_count": len(formatted),
        "min_date": min_date,
        "max_date": max_date,
        "date_values": limited_values,
        "truncated": len(formatted) > len(limited_values),
        "column_mapping": sanitized_mapping,
    }


def update_dataset_column_mapping(
    project: str,
    dataset_id: str,
    mapping: Dict[str, Any],
    topic_label: Optional[str] = None,
) -> Dict[str, Any]:
    if not project or not project.strip():
        raise ValueError("项目名称不能为空")
    if not dataset_id:
        raise ValueError("数据集编号不能为空")

    metadata = _resolve_dataset_metadata(project, dataset_id)
    columns = [str(column) for column in metadata.get("columns", [])]
    sanitized_mapping = _sanitize_column_mapping(mapping, columns)
    topic_value = topic_label if isinstance(topic_label, str) else None
    if topic_value is not None:
        topic_value = topic_value.strip()

    project_slug = _normalise_project_name(project)
    meta_path = _meta_path(project_slug, dataset_id)
    meta_payload: Dict[str, Any] = {}

    if meta_path.exists():
        try:
            with meta_path.open("r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                meta_payload.update(loaded)
        except Exception:
            meta_payload = {}

    if not meta_payload:
        meta_payload = metadata.copy()

    meta_payload.update(
        {
            "id": dataset_id,
            "project": project,
            "project_slug": project_slug,
            "columns": columns or meta_payload.get("columns", []),
            "column_mapping": sanitized_mapping,
        }
    )
    current_topic = meta_payload.get("topic_label", "")
    if not isinstance(current_topic, str):
        current_topic = ""
    if topic_value is not None:
        meta_payload["topic_label"] = topic_value
    else:
        meta_payload["topic_label"] = current_topic.strip()

    with meta_path.open("w", encoding="utf-8") as fh:
        json.dump(meta_payload, fh, ensure_ascii=False, indent=2)

    manifest_record = metadata.copy()
    manifest_record["column_mapping"] = sanitized_mapping
    manifest_record["topic_label"] = meta_payload.get("topic_label", "")
    _write_manifest(project_slug, manifest_record)

    return {
        "column_mapping": sanitized_mapping,
        "topic_label": meta_payload.get("topic_label", ""),
    }


def get_dataset_preview(project: str, dataset_id: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    """Return a paginated preview for a stored dataset."""

    if not project or not project.strip():
        raise ValueError("项目名称不能为空")
    if not dataset_id:
        raise ValueError("数据集编号不能为空")

    page = max(int(page or 1), 1)
    page_size = max(min(int(page_size or 20), 200), 1)
    offset = (page - 1) * page_size

    metadata = _resolve_dataset_metadata(project, dataset_id)
    jsonl_path = metadata.get("jsonl_file")
    if not jsonl_path:
        raise LookupError("数据集缺少 JSONL 存储路径")

    file_path = (_REPO_ROOT / jsonl_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError("未找到数据集 JSONL 文件")

    declared_columns = [str(column) for column in metadata.get("columns", [])]
    columns = list(dict.fromkeys(declared_columns))
    rows: List[Dict[str, str]] = []
    extra_columns: List[str] = []

    with file_path.open("r", encoding="utf-8") as handle:
        for raw_line in islice(handle, offset, offset + page_size):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue

            for key in record.keys():
                key_str = str(key)
                if key_str not in columns and key_str not in extra_columns:
                    extra_columns.append(key_str)

            row = {str(key): _stringify_cell(value) for key, value in record.items()}
            row["__row_index"] = offset + len(rows) + 1
            rows.append(row)
            if len(rows) >= page_size:
                break

    columns.extend(extra_columns)
    total_rows = int(metadata.get("rows") or 0)
    total_pages = (
        (total_rows - 1) // page_size + 1 if total_rows else (1 if rows else 0)
    )

    return {
        "dataset": metadata,
        "columns": columns,
        "rows": rows,
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "total_pages": total_pages,
    }


def store_uploaded_dataset(
    project: str,
    file_storage: FileStorage,
    column_mapping: Optional[Dict[str, Any]] = None,
    topic_label: Optional[str] = None,
) -> Dict:
    """Persist an uploaded spreadsheet for a project and generate metadata."""

    if not project or not project.strip():
        raise ValueError("项目名称不能为空")
    if not file_storage or not getattr(file_storage, "filename", ""):
        raise ValueError("未检测到上传文件")

    dirs = _ensure_directories(project)
    project_slug = dirs["slug"]
    original_dir = dirs["original_dir"]
    jsonl_dir = dirs["jsonl_dir"]
    cache_dir = dirs["cache_dir"]
    meta_dir = dirs["meta_dir"]

    original_name = file_storage.filename or "dataset.xlsx"
    extension = Path(original_name).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
        raise ValueError(f"暂不支持的文件类型：{extension or '未知'}，仅支持 {allowed}")

    timestamp = _dataset_timestamp()
    dataset_id = f"{timestamp.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
    stored_name = secure_filename(original_name) or f"dataset{extension or 'jsonl'}"
    stored_filename = f"{dataset_id}_{stored_name}"
    store_path = original_dir / stored_filename
    file_storage.save(store_path)

    dataframe = _load_dataframe(store_path, extension)
    rows = int(dataframe.shape[0])
    columns = [str(column) for column in dataframe.columns]
    inferred_mapping = _infer_column_mapping(dataframe, hints=column_mapping)
    topic_value = (topic_label or "").strip()

    # 缓存为 pickle，供后端快速载入
    pkl_path = cache_dir / f"{dataset_id}.pkl"
    dataframe.to_pickle(pkl_path)

    # 统一产出 JSONL 版本
    jsonl_path = jsonl_dir / f"{dataset_id}.jsonl"
    write_jsonl(dataframe, jsonl_path)

    metadata = {
        "id": dataset_id,
        "project": project,
        "project_slug": project_slug,
        "display_name": original_name,
        "stored_at": timestamp.isoformat(),
        "rows": rows,
        "column_count": len(columns),
        "columns": columns,
        "column_mapping": inferred_mapping,
        "topic_label": topic_value,
        "file_size": store_path.stat().st_size,
        "source_file": str(store_path.relative_to(_REPO_ROOT)),
        "pkl_file": str(pkl_path.relative_to(_REPO_ROOT)),
        "jsonl_file": str(jsonl_path.relative_to(_REPO_ROOT)),
    }

    meta_path = meta_dir / f"{dataset_id}.json"
    with meta_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
    metadata["json_file"] = str(meta_path.relative_to(_REPO_ROOT))

    _write_manifest(project_slug, metadata)
    return metadata
