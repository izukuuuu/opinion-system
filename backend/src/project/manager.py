"""Project management utilities for OpinionSystem."""
from __future__ import annotations

import json
import pickle
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

__all__ = [
    "OperationRecord",
    "ProjectRecord",
    "ProjectManager",
]

_PROJECT_METADATA_FILENAME = "project.json"
_PROJECT_DATA_SUBDIRS = (
    "raw",
    "merge",
    "clean",
    "filter",
    "fetch",
    "analyze",
    "reports",
    "results",
    "uploads/original",
    "uploads/jsonl",
    "uploads/cache",
    "uploads/meta",
)
_SUFFIX_SANITIZER = re.compile(r"[^\w\u4e00-\u9fff-]+", re.UNICODE)
_LEGACY_SLUG_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


def _now() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _normalise_suffix(text: str) -> str:
    """Generate a filesystem-friendly suffix that preserves common Unicode."""
    normalised = unicodedata.normalize("NFKC", str(text or "").strip())
    cleaned = _SUFFIX_SANITIZER.sub("-", normalised)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-_")


def _project_identifier_hint(name: str) -> str:
    """Compose a suffix hint for project identifiers."""
    suffix = _normalise_suffix(name)
    return suffix.lower() if suffix else ""


def _legacy_project_slug(name: str) -> str:
    """Legacy ASCII-only project slug used by earlier versions."""
    cleaned = _LEGACY_SLUG_SANITIZER.sub("-", str(name or "").strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("- ").lower() or "project"


def _rewrite_relative_project_path(value: str, identifier: str) -> str:
    """Update historical relative paths to point at the new project identifier."""
    if not isinstance(value, str) or not value:
        return value
    normalised = value.replace("\\", "/")
    prefix = "backend/data/projects/"
    idx = normalised.find(prefix)
    if idx == -1:
        return value
    suffix = normalised[idx + len(prefix):]
    if not suffix:
        return value
    parts = suffix.split("/", 1)
    remainder = parts[1] if len(parts) > 1 else ""
    updated = prefix + identifier
    if remainder:
        updated = f"{updated}/{remainder}"
    if "\\" in value:
        updated = updated.replace("/", "\\")
    return updated


def _serialise_mapping(mapping: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ensure the mapping is JSON serialisable."""
    if not mapping:
        return {}
    serialised: Dict[str, Any] = {}
    for key, value in mapping.items():
        safe_key = str(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            serialised[safe_key] = value
        else:
            try:
                serialised[safe_key] = json.loads(json.dumps(value, default=str))
            except TypeError:
                serialised[safe_key] = str(value)
    return serialised


@dataclass
class OperationRecord:
    """A single execution record for a project."""

    operation: str
    params: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "params": _serialise_mapping(self.params),
            "success": bool(self.success),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OperationRecord":
        return cls(
            operation=str(payload.get("operation", "")),
            params=_serialise_mapping(payload.get("params", {})),
            success=bool(payload.get("success", False)),
            timestamp=str(payload.get("timestamp", _now())),
        )


def _ensure_sorted_unique(values: Iterable[str]) -> List[str]:
    return sorted({str(item) for item in values if str(item).strip()})


@dataclass
class ProjectRecord:
    """Persistent metadata describing a project."""

    name: str
    description: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    operations: List[OperationRecord] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    status: str = "pending"
    identifier: str = ""
    storage_path: str = ""

    def touch(self) -> None:
        self.updated_at = _now()

    def add_operation(self, record: OperationRecord) -> None:
        self.operations.append(record)
        self.status = "success" if record.success else "error"
        self.updated_at = record.timestamp
        date_value = record.params.get("date")
        if isinstance(date_value, str):
            all_dates = set(self.dates)
            if date_value not in all_dates:
                all_dates.add(date_value)
                self.dates = sorted(all_dates)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifier,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": _serialise_mapping(self.metadata),
            "operations": [record.to_dict() for record in self.operations],
            "dates": _ensure_sorted_unique(self.dates),
            "status": self.status,
            "last_operation": self.operations[-1].to_dict() if self.operations else None,
            "storage_path": self.storage_path,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ProjectRecord":
        record = cls(
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            created_at=str(payload.get("created_at", _now())),
            updated_at=str(payload.get("updated_at", _now())),
            metadata=_serialise_mapping(payload.get("metadata", {})),
            dates=_ensure_sorted_unique(payload.get("dates", [])),
            status=str(payload.get("status", "pending")),
            identifier=str(payload.get("id") or payload.get("identifier") or ""),
            storage_path=str(payload.get("storage_path", "")),
        )
        operations = payload.get("operations", [])
        if isinstance(operations, list):
            for item in operations:
                if isinstance(item, OperationRecord):
                    record.operations.append(item)
                elif isinstance(item, dict):
                    record.operations.append(OperationRecord.from_dict(item))
        if record.operations:
            record.updated_at = record.operations[-1].timestamp
            record.status = "success" if record.operations[-1].success else "error"
        return record


class ProjectManager:
    """Manage OpinionSystem projects stored on disk."""

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        default_storage = backend_root / "data"
        self.storage_dir = storage_dir or default_storage
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._pickle_path = self.storage_dir / "projects.pkl"
        self._json_path = self.storage_dir / "projects.json"
        self._projects: Dict[str, ProjectRecord] = {}
        self._projects_by_id: Dict[str, ProjectRecord] = {}
        self._load_from_disk()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _load_from_disk(self) -> None:
        loaded = False
        if self._pickle_path.exists():
            try:
                with self._pickle_path.open("rb") as fh:
                    raw = pickle.load(fh)
                if isinstance(raw, dict):
                    for name, payload in raw.items():
                        self._projects[str(name)] = self._coerce_project(payload)
                    loaded = True
            except Exception:
                loaded = False
        if not loaded and self._json_path.exists():
            try:
                with self._json_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, list):
                    for payload in data:
                        if isinstance(payload, dict):
                            project = ProjectRecord.from_dict(payload)
                            if project.name:
                                self._projects[project.name] = project
                    loaded = True
            except Exception:
                loaded = False
        if not loaded:
            self._projects = {}
        self._ensure_all_projects_have_storage()

    def _coerce_project(self, payload: Any) -> ProjectRecord:
        if isinstance(payload, ProjectRecord):
            return payload
        if isinstance(payload, dict):
            return ProjectRecord.from_dict(payload)
        raise TypeError(f"Unsupported project payload: {type(payload)!r}")

    def _reindex(self) -> None:
        self._projects_by_id = {}
        for record in self._projects.values():
            if record.identifier:
                self._projects_by_id[record.identifier] = record

    def _project_base_dir(self, identifier: str) -> Path:
        return self.storage_dir / "projects" / identifier

    def _generate_identifier(self, name: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        suffix = _project_identifier_hint(name)
        candidate = f"{timestamp}-{suffix}" if suffix else timestamp
        existing = set(self._projects_by_id.keys())
        if candidate in existing or not candidate:
            candidate = f"{candidate}-{uuid4().hex[:6]}"
        counter = 1
        while candidate in existing:
            candidate = f"{timestamp}-{suffix}-{counter:02d}" if suffix else f"{timestamp}-{counter:02d}"
            counter += 1
        return candidate

    def _ensure_identifier(self, record: ProjectRecord) -> None:
        if record.identifier:
            return
        record.identifier = self._generate_identifier(record.name)

    def _write_project_metadata(self, record: ProjectRecord, base_dir: Optional[Path] = None) -> None:
        base_path = base_dir or self._project_base_dir(record.identifier)
        base_path.mkdir(parents=True, exist_ok=True)
        metadata = {
            "id": record.identifier,
            "name": record.name,
            "description": record.description,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "status": record.status,
            "dates": _ensure_sorted_unique(record.dates),
            "metadata": _serialise_mapping(record.metadata),
        }
        target = base_path / _PROJECT_METADATA_FILENAME
        with target.open("w", encoding="utf-8") as fh:
            json.dump(metadata, fh, ensure_ascii=False, indent=2)

    def _ensure_project_directories(self, record: ProjectRecord) -> Path:
        data_root = self.storage_dir / "projects"
        data_root.mkdir(parents=True, exist_ok=True)
        legacy_hint = _project_identifier_hint(record.name) or "project"
        legacy_candidates = []
        if legacy_hint:
            legacy_candidates.append(legacy_hint)
        legacy_ascii = _legacy_project_slug(record.name)
        if legacy_ascii and legacy_ascii not in legacy_candidates:
            legacy_candidates.append(legacy_ascii)
        legacy_dirs = [
            data_root / candidate
            for candidate in legacy_candidates
            if candidate and (data_root / candidate).exists() and (data_root / candidate).is_dir()
        ]

        self._ensure_identifier(record)
        base_dir = self._project_base_dir(record.identifier)
        if record.name.upper() != "GLOBAL" and legacy_dirs:
            for candidate_dir in legacy_dirs:
                if candidate_dir == base_dir or not candidate_dir.exists() or not candidate_dir.is_dir():
                    continue
                if not base_dir.exists():
                    try:
                        candidate_dir.rename(base_dir)
                    except OSError:
                        continue
                    else:
                        break
                else:
                    try:
                        moved_any = False
                        for child in candidate_dir.iterdir():
                            target = base_dir / child.name
                            if target.exists() and target.is_dir() and child.is_dir():
                                for nested in child.iterdir():
                                    merged_target = target / nested.name
                                    if not merged_target.exists():
                                        nested.rename(merged_target)
                                        moved_any = True
                            elif not target.exists():
                                child.rename(target)
                                moved_any = True
                        if moved_any:
                            leftovers = sorted(
                                candidate_dir.rglob("*"),
                                key=lambda path: len(path.parts),
                                reverse=True,
                            )
                            for leftover in leftovers:
                                if leftover.is_dir():
                                    try:
                                        leftover.rmdir()
                                    except OSError:
                                        pass
                            try:
                                candidate_dir.rmdir()
                            except OSError:
                                pass
                    except OSError:
                        continue
        base_dir.mkdir(parents=True, exist_ok=True)
        for subdir in _PROJECT_DATA_SUBDIRS:
            (base_dir / subdir).mkdir(parents=True, exist_ok=True)
        record.storage_path = str(base_dir.relative_to(self.storage_dir))
        self._write_project_metadata(record, base_dir=base_dir)
        self._rewrite_project_storage(record, base_dir)
        return base_dir

    def _rewrite_project_storage(self, record: ProjectRecord, base_dir: Path) -> None:
        uploads_dir = base_dir / "uploads"
        meta_dir = uploads_dir / "meta"
        if not meta_dir.exists():
            return

        datasets = []
        for meta_file in sorted(meta_dir.glob("*.json")):
            try:
                with meta_file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue

            meta_changed = False
            if data.get("project_slug") != record.identifier:
                data["project_slug"] = record.identifier
                meta_changed = True
            if data.get("project_id") != record.identifier:
                data["project_id"] = record.identifier
                meta_changed = True

            for key in ("source_file", "pkl_file", "jsonl_file"):
                value = data.get(key)
                if isinstance(value, str):
                    rewritten = _rewrite_relative_project_path(value, record.identifier)
                    if rewritten != value:
                        data[key] = rewritten
                        meta_changed = True

            if meta_changed:
                try:
                    with meta_file.open("w", encoding="utf-8") as fh:
                        json.dump(data, fh, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            dataset_entry = {
                "id": data.get("id"),
                "project": record.name,
                "project_id": record.identifier,
                "project_slug": record.identifier,
                "display_name": data.get("display_name"),
                "stored_at": data.get("stored_at"),
                "rows": data.get("rows"),
                "column_count": data.get("column_count"),
                "columns": data.get("columns", []),
                "column_mapping": data.get("column_mapping", {}),
                "topic_label": data.get("topic_label", ""),
                "file_size": data.get("file_size"),
                "source_file": data.get("source_file"),
                "pkl_file": data.get("pkl_file"),
                "jsonl_file": data.get("jsonl_file"),
            }
            datasets.append(dataset_entry)

        if not datasets:
            return

        datasets.sort(key=lambda item: item.get("stored_at", ""), reverse=True)
        manifest_payload = {
            "project": record.name,
            "project_id": record.identifier,
            "datasets": datasets,
        }
        manifest_path = uploads_dir / "manifest.json"
        try:
            with manifest_path.open("w", encoding="utf-8") as fh:
                json.dump(manifest_payload, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _ensure_all_projects_have_storage(self) -> None:
        updated = False
        for name, record in list(self._projects.items()):
            previous_identifier = record.identifier
            previous_storage = record.storage_path
            self._ensure_project_directories(record)
            if record.identifier != previous_identifier or record.storage_path != previous_storage:
                updated = True
            self._projects[name] = record
        if updated:
            self._save_to_disk()
        else:
            self._reindex()

    def _save_to_disk(self) -> None:
        self._reindex()
        data = {name: record.to_dict() for name, record in self._projects.items()}
        with self._pickle_path.open("wb") as fh:
            pickle.dump(data, fh)
        with self._json_path.open("w", encoding="utf-8") as fh:
            json.dump(list(data.values()), fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_projects(self) -> List[Dict[str, Any]]:
        ordered = sorted(
            self._projects.values(),
            key=lambda record: record.updated_at,
            reverse=True,
        )
        return [record.to_dict() for record in ordered]

    def get_project_record(self, reference: str) -> Optional[ProjectRecord]:
        key = str(reference or "").strip()
        if not key:
            return None
        project = self._projects.get(key)
        if project:
            return project
        project = self._projects_by_id.get(key)
        if project:
            return project
        for candidate in self._projects.values():
            if candidate.identifier == key:
                return candidate
        return None

    def get_project(self, reference: str) -> Optional[Dict[str, Any]]:
        project = self.get_project_record(reference)
        return project.to_dict() if project else None

    def ensure_project_storage(self, reference: str, *, create_if_missing: bool = False) -> ProjectRecord:
        project = self.get_project_record(reference)
        if not project:
            if not create_if_missing:
                raise LookupError(f"Project '{reference}' was not found")
            project = ProjectRecord(name=str(reference))
            self._projects[project.name] = project
        previous_identifier = project.identifier
        previous_storage = project.storage_path
        self._ensure_project_directories(project)
        self._projects[project.name] = project
        if project.identifier != previous_identifier or project.storage_path != previous_storage:
            self._save_to_disk()
        return project

    def resolve_identifier(self, reference: str) -> Optional[str]:
        project = self.get_project_record(reference)
        if not project:
            return None
        previous_identifier = project.identifier
        previous_storage = project.storage_path
        self._ensure_project_directories(project)
        self._projects[project.name] = project
        if project.identifier != previous_identifier or project.storage_path != previous_storage:
            self._save_to_disk()
        return project.identifier or None

    def create_or_update_project(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        project = self.get_project_record(name)
        if not project:
            project = ProjectRecord(name=name)
            self._projects[name] = project
        if description is not None:
            project.description = description
        if metadata:
            project.metadata.update(_serialise_mapping(metadata))
        project.touch()
        self._ensure_project_directories(project)
        self._projects[project.name] = project
        self._save_to_disk()
        return project.to_dict()

    def log_operation(
        self,
        name: str,
        operation: str,
        params: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ) -> Dict[str, Any]:
        params = _serialise_mapping(params or {})
        project = self.get_project_record(name)
        if not project:
            project = ProjectRecord(name=name)
            self._projects[name] = project
        record = OperationRecord(operation=operation, params=params, success=success)
        project.add_operation(record)
        self._ensure_project_directories(project)
        self._projects[project.name] = project
        self._save_to_disk()
        return record.to_dict()

    def delete_project(self, name: str) -> bool:
        """Delete a project from storage.

        Returns ``True`` if a project with the given name existed and was removed.
        ``False`` is returned when the project could not be found.
        """

        project = self.get_project_record(name)
        if not project:
            return False

        self._projects.pop(project.name, None)
        if project.identifier:
            self._projects_by_id.pop(project.identifier, None)
        self._save_to_disk()
        storage_dir = self._project_base_dir(project.identifier) if project.identifier else None
        if storage_dir and storage_dir.exists():
            try:
                shutil.rmtree(storage_dir)
            except Exception:
                pass
        return True


# A lightweight global accessor that avoids repeated disk reads when imported
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager
