"""Helpers for dataset metadata normalisation and file management."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.project import find_dataset_by_id, get_dataset_metadata  # type: ignore

from .paths import DATA_PROJECTS_ROOT, PROJECT_ROOT

LOGGER = logging.getLogger(__name__)


def parse_column_mapping_payload(raw: Any) -> Dict[str, str]:
    """Normalise column mapping values from JSON or dict payloads."""

    mapping: Dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, str):
                mapping[str(key)] = value.strip()
    elif isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            for key, value in decoded.items():
                if isinstance(value, str):
                    mapping[str(key)] = value.strip()

    normalized: Dict[str, str] = {}
    for key in ("date", "title", "content", "author"):
        value = mapping.get(key)
        if isinstance(value, str):
            normalized[key] = value.strip()
    return normalized


def iter_unique_strings(values: List[Any]) -> List[str]:
    """Return unique, non-empty string representations preserving order."""

    seen = set()
    ordered: List[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def resolve_dataset_payload(project_name: str, dataset_id: Any) -> Dict[str, Any]:
    """Locate dataset metadata either by project scope or globally."""

    dataset_id_str = str(dataset_id or "").strip()
    if not dataset_id_str:
        return {}

    if project_name:
        try:
            return get_dataset_metadata(project_name, dataset_id_str)
        except (LookupError, ValueError):
            pass

    metadata = find_dataset_by_id(dataset_id_str)
    if metadata:
        return metadata
    return {}


def update_dataset_source_references(dataset_meta: Dict[str, Any]) -> None:
    """Update dataset manifests to reflect a new source file path."""

    dataset_id = dataset_meta.get("id")
    source_file = dataset_meta.get("source_file")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        return
    if not isinstance(source_file, str) or not source_file.strip():
        return

    project_slug = (
        dataset_meta.get("project_slug")
        or dataset_meta.get("project_id")
        or dataset_meta.get("project")
        or ""
    )
    project_slug = str(project_slug).strip()
    if not project_slug:
        try:
            parts = Path(source_file).parts
            projects_idx = parts.index("projects")
            project_slug = parts[projects_idx + 1]
        except (ValueError, IndexError):
            return

    uploads_dir = DATA_PROJECTS_ROOT / project_slug / "uploads"
    meta_path = uploads_dir / "meta" / f"{dataset_id}.json"
    try:
        if meta_path.exists():
            with meta_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data["source_file"] = source_file
                with meta_path.open("w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        LOGGER.exception("Failed to update metadata file for dataset %s", dataset_id)

    manifest_path = uploads_dir / "manifest.json"
    try:
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as fh:
                manifest = json.load(fh)
            changed = False
            if isinstance(manifest, dict):
                records = manifest.get("datasets")
                if isinstance(records, list):
                    for record in records:
                        if isinstance(record, dict) and record.get("id") == dataset_id:
                            record["source_file"] = source_file
                            changed = True
                            break
            if changed:
                with manifest_path.open("w", encoding="utf-8") as fh:
                    json.dump(manifest, fh, ensure_ascii=False, indent=2)
    except Exception:
        LOGGER.exception("Failed to update manifest for dataset %s", dataset_id)


def resolve_dataset_source_path(dataset_meta: Dict[str, Any]) -> Optional[Path]:
    """Return the absolute path to the dataset source file if available."""

    source_file = dataset_meta.get("source_file")
    if not isinstance(source_file, str) or not source_file.strip():
        return None

    source_path = Path(source_file.strip())
    if not source_path.is_absolute():
        source_path = (PROJECT_ROOT / source_path).resolve()

    if not source_path.exists():
        LOGGER.warning(
            "Dataset %s source file %s is missing; raw staging skipped",
            dataset_meta.get("id"),
            source_path,
        )
        return None

    if source_path.suffix:
        return source_path

    display_name = dataset_meta.get("display_name")
    suffix_hint = Path(str(display_name)).suffix.lower() if isinstance(display_name, str) else ""
    if not suffix_hint:
        name_lower = source_path.name.lower()
        for token, extension in (
            ("_xlsx", ".xlsx"),
            ("_xls", ".xls"),
            ("_csv", ".csv"),
            ("_jsonl", ".jsonl"),
        ):
            if name_lower.endswith(token):
                suffix_hint = extension
                break

    if not suffix_hint:
        return source_path

    dataset_id = str(dataset_meta.get("id") or source_path.stem or "dataset").strip() or "dataset"
    new_path = source_path.with_name(f"{dataset_id}{suffix_hint}")

    if new_path.exists():
        return source_path

    try:
        source_path.rename(new_path)
        dataset_meta["source_file"] = str(new_path.relative_to(PROJECT_ROOT))
        update_dataset_source_references(dataset_meta)
        LOGGER.info(
            "Renamed dataset %s source file to %s",
            dataset_meta.get("id"),
            new_path,
        )
        return new_path
    except Exception:
        LOGGER.exception(
            "Failed to normalise source file name for dataset %s",
            dataset_meta.get("id"),
        )
        return source_path


def ensure_raw_dataset_availability(topic_identifier: str, date: str, dataset_meta: Dict[str, Any]) -> None:
    """Ensure the merge stage can locate the original spreadsheet input."""

    if not dataset_meta:
        return

    source_path = resolve_dataset_source_path(dataset_meta)
    if source_path is None:
        return

    raw_dir = DATA_PROJECTS_ROOT / topic_identifier / "raw" / date
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        LOGGER.exception(
            "Failed to create raw directory %s for dataset %s",
            raw_dir,
            dataset_meta.get("id"),
        )
        return

    display_name = dataset_meta.get("display_name")
    candidate_extension = source_path.suffix.lower()
    if not candidate_extension and isinstance(display_name, str):
        candidate_extension = Path(display_name).suffix.lower()
    destination_name = source_path.name
    if candidate_extension and not destination_name.lower().endswith(candidate_extension):
        base_name = str(dataset_meta.get("id") or source_path.stem or "dataset").strip() or "dataset"
        destination_name = f"{base_name}{candidate_extension}"

    destination_path = raw_dir / destination_name
    try:
        if destination_path.exists():
            try:
                if destination_path.samefile(source_path):
                    return
            except (OSError, AttributeError):
                try:
                    if destination_path.stat().st_size == source_path.stat().st_size:
                        return
                except OSError:
                    pass
        shutil.copy2(source_path, destination_path)
        LOGGER.info(
            "Prepared raw input for dataset %s at %s",
            dataset_meta.get("id"),
            destination_path,
        )
    except Exception:
        LOGGER.exception(
            "Failed to copy dataset %s (%s) to raw directory %s",
            dataset_meta.get("id"),
            source_path,
            raw_dir,
        )


def parse_column_mapping_from_form(form: Dict[str, Any]) -> Dict[str, str]:
    """Extract mapping hints from multipart form submissions."""

    initial = parse_column_mapping_payload(form.get("column_mapping"))
    for key in ("date", "title", "content", "author"):
        field_name = f"{key}_column"
        value = form.get(field_name)
        if isinstance(value, str) and value.strip():
            initial[key] = value.strip()
    return initial


__all__ = [
    "ensure_raw_dataset_availability",
    "iter_unique_strings",
    "parse_column_mapping_from_form",
    "parse_column_mapping_payload",
    "resolve_dataset_payload",
    "resolve_dataset_source_path",
    "update_dataset_source_references",
]
