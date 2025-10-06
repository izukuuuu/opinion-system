"""Utilities for storing per-project tabular datasets."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

import pandas as pd
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

__all__ = ["store_uploaded_dataset", "list_project_datasets"]

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent
_DATA_ROOT = _BACKEND_ROOT / "data"
_STORE_ROOT = _BACKEND_ROOT / "store"
_MANIFEST_FILENAME = "manifest.json"
_ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def _normalise_project_name(name: str) -> str:
    """Convert the project name into a filesystem friendly slug."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("- ")
    return cleaned.lower() or "project"


def _ensure_directories(project: str) -> str:
    slug = _normalise_project_name(project)
    data_dir = _DATA_ROOT / slug
    store_dir = _STORE_ROOT / slug
    data_dir.mkdir(parents=True, exist_ok=True)
    store_dir.mkdir(parents=True, exist_ok=True)
    return slug


def _dataset_timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _load_dataframe(path: Path, extension: str) -> pd.DataFrame:
    if extension == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _manifest_path(project_slug: str) -> Path:
    return _DATA_ROOT / project_slug / _MANIFEST_FILENAME


def _write_manifest(project_slug: str, metadata: Dict) -> None:
    manifest_path = _manifest_path(project_slug)
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
            datasets.sort(key=lambda item: item.get("stored_at", ""), reverse=True)
            return datasets
    except Exception:
        return []
    return []


def store_uploaded_dataset(project: str, file_storage: FileStorage) -> Dict:
    """Persist an uploaded spreadsheet for a project and generate metadata."""

    if not project or not project.strip():
        raise ValueError("项目名称不能为空")
    if not file_storage or not getattr(file_storage, "filename", ""):
        raise ValueError("未检测到上传文件")

    project_slug = _ensure_directories(project)
    original_name = file_storage.filename or "dataset.xlsx"
    extension = Path(original_name).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
        raise ValueError(f"暂不支持的文件类型：{extension or '未知'}，仅支持 {allowed}")

    timestamp = _dataset_timestamp()
    dataset_id = f"{timestamp.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
    stored_name = secure_filename(original_name) or f"dataset{extension}"
    stored_filename = f"{dataset_id}_{stored_name}"
    store_path = _STORE_ROOT / project_slug / stored_filename
    file_storage.save(store_path)

    dataframe = _load_dataframe(store_path, extension)
    rows = int(dataframe.shape[0])
    columns = [str(column) for column in dataframe.columns]
    data_dir = _DATA_ROOT / project_slug
    pkl_path = data_dir / f"{dataset_id}.pkl"
    dataframe.to_pickle(pkl_path)

    metadata = {
        "id": dataset_id,
        "project": project,
        "project_slug": project_slug,
        "display_name": original_name,
        "stored_at": timestamp.isoformat(),
        "rows": rows,
        "column_count": len(columns),
        "columns": columns,
        "file_size": store_path.stat().st_size,
        "source_file": str(store_path.relative_to(_REPO_ROOT)),
        "pkl_file": str(pkl_path.relative_to(_REPO_ROOT)),
    }

    json_path = data_dir / f"{dataset_id}.json"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
    metadata["json_file"] = str(json_path.relative_to(_REPO_ROOT))

    _write_manifest(project_slug, metadata)
    return metadata
