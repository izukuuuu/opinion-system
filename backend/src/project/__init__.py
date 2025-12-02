"""Project management entry points."""

from .manager import ProjectManager, get_project_manager

__all__ = [
    "ProjectManager",
    "get_project_manager",
    "get_dataset_date_summary",
    "get_dataset_preview",
    "list_project_datasets",
    "normalise_project_name",
    "store_uploaded_dataset",
    "update_dataset_column_mapping",
    "get_dataset_metadata",
    "find_dataset_by_id",
]

_STORAGE_EXPORTS = {
    "find_dataset_by_id",
    "get_dataset_metadata",
    "get_dataset_date_summary",
    "get_dataset_preview",
    "list_project_datasets",
    "normalise_project_name",
    "store_uploaded_dataset",
    "update_dataset_column_mapping",
}


def __getattr__(name):
    if name in _STORAGE_EXPORTS:
        from . import storage

        return getattr(storage, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _STORAGE_EXPORTS)
