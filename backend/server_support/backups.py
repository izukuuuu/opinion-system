"""Utilities for exporting and importing runtime backups.

The backup payload should include git-ignored runtime assets:
- ``backend/.env``
- ``backend/configs/``
- ``backend/data/``
- ``frontend/.env.local``
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Dict, Iterable, List, Tuple

from .paths import BACKEND_DIR, CONFIGS_DIR, PROJECT_ROOT

__all__ = [
    "build_settings_backup",
    "restore_settings_backup",
]

_BACKUP_ITEMS = [
    ("backend/.env", BACKEND_DIR / ".env", "file"),
    ("backend/configs", CONFIGS_DIR, "dir"),
    ("backend/data", BACKEND_DIR / "data", "dir"),
    ("frontend/.env.local", PROJECT_ROOT / "frontend" / ".env.local", "file"),
]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_backup_files(label: str, path: Path) -> Iterable[Tuple[str, Path]]:
    if path.is_file():
        yield label, path
        return

    if not path.is_dir():
        return

    for child in path.rglob("*"):
        if child.is_file():
            relative = child.relative_to(path)
            arcname = str(Path(label) / relative)
            yield arcname, child


def build_settings_backup() -> Tuple[io.BytesIO, str, Dict[str, object]]:
    """Bundle runtime assets into an in-memory zip archive."""

    manifest: Dict[str, object] = {
        "version": 1,
        "generated_at": _utc_timestamp(),
        "included_roots": [],
        "missing_roots": [],
        "file_count": 0,
    }

    buffer = io.BytesIO()
    included_roots: List[str] = []
    missing_roots: List[str] = []

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for label, path, _kind in _BACKUP_ITEMS:
            if not path.exists():
                missing_roots.append(label)
                continue

            included_roots.append(label)
            for arcname, source in _iter_backup_files(label, path):
                archive.write(source, arcname)
                manifest["file_count"] = int(manifest["file_count"]) + 1

        manifest["included_roots"] = included_roots
        manifest["missing_roots"] = missing_roots
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    buffer.seek(0)
    filename = f"opinion-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return buffer, filename, manifest


def _match_restore_target(arcname: str):
    normalised = arcname.lstrip("/").replace("\\", "/")
    if not normalised or normalised.endswith("/"):
        return None

    path_obj = Path(normalised)
    for label, destination, kind in _BACKUP_ITEMS:
        label_path = Path(label)
        if kind == "file":
            if normalised == label_path.as_posix():
                base_dir = destination.parent
                return destination, base_dir
            continue

        try:
            relative = path_obj.relative_to(label_path)
        except ValueError:
            continue

        if any(part == ".." for part in relative.parts):
            continue

        target_path = destination / relative
        base_dir = destination
        return target_path, base_dir

    return None


def restore_settings_backup(upload: BinaryIO) -> Dict[str, object]:
    """Restore runtime assets from an uploaded zip archive."""

    try:
        upload.seek(0)
    except Exception:
        pass

    if not zipfile.is_zipfile(upload):
        raise ValueError("上传的文件不是有效的 ZIP 存档")

    try:
        upload.seek(0)
    except Exception:
        pass

    restored: List[str] = []
    skipped: List[str] = []

    with zipfile.ZipFile(upload) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = _match_restore_target(member.filename)
            if not target:
                skipped.append(member.filename)
                continue

            target_path, base_dir = target
            try:
                resolved_base = base_dir.resolve()
                resolved_target = target_path.resolve()
                resolved_target.relative_to(resolved_base)
            except Exception:
                skipped.append(member.filename)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, target_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            restored.append(member.filename)

    return {
        "restored": restored,
        "skipped": skipped,
        "allowed_roots": [label for label, _, _ in _BACKUP_ITEMS],
    }
