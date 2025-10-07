"""Project management utilities for OpinionSystem."""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    "OperationRecord",
    "ProjectRecord",
    "ProjectManager",
]


def _now() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


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
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": _serialise_mapping(self.metadata),
            "operations": [record.to_dict() for record in self.operations],
            "dates": _ensure_sorted_unique(self.dates),
            "status": self.status,
            "last_operation": self.operations[-1].to_dict() if self.operations else None,
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

    def _coerce_project(self, payload: Any) -> ProjectRecord:
        if isinstance(payload, ProjectRecord):
            return payload
        if isinstance(payload, dict):
            return ProjectRecord.from_dict(payload)
        raise TypeError(f"Unsupported project payload: {type(payload)!r}")

    def _save_to_disk(self) -> None:
        data = {name: record.to_dict() for name, record in self._projects.items()}
        with self._pickle_path.open("wb") as fh:
            pickle.dump(data, fh)
        with self._json_path.open("w", encoding="utf-8") as fh:
            json.dump(list(data.values()), fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_projects(self) -> List[Dict[str, Any]]:
        return [
            self._projects[name].to_dict()
            for name in sorted(
                self._projects.keys(),
                key=lambda item: self._projects[item].updated_at,
                reverse=True,
            )
        ]

    def get_project(self, name: str) -> Optional[Dict[str, Any]]:
        project = self._projects.get(name)
        return project.to_dict() if project else None

    def create_or_update_project(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        project = self._projects.get(name)
        if not project:
            project = ProjectRecord(name=name)
            self._projects[name] = project
        if description is not None:
            project.description = description
        if metadata:
            project.metadata.update(_serialise_mapping(metadata))
        project.touch()
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
        project = self._projects.get(name)
        if not project:
            project = ProjectRecord(name=name)
            self._projects[name] = project
        record = OperationRecord(operation=operation, params=params, success=success)
        project.add_operation(record)
        self._projects[name] = project
        self._save_to_disk()
        return record.to_dict()

    def delete_project(self, name: str) -> bool:
        """Delete a project from storage.

        Returns ``True`` if a project with the given name existed and was removed.
        ``False`` is returned when the project could not be found.
        """

        if name not in self._projects:
            return False

        self._projects.pop(name, None)
        self._save_to_disk()
        return True


# A lightweight global accessor that avoids repeated disk reads when imported
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager
