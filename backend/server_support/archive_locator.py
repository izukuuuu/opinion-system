"""
统一存档定位器

合并 analyze/topic/report 三个模块中各自实现的"找目录、列历史、取结果"逻辑为
统一的 ArchiveLocator，输出标准 ArchiveRecord。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .paths import DATA_PROJECTS_ROOT
from .topic_context import TopicContext

_MIGRATED_POINTER_FILENAME = "MIGRATED_TO.json"


# ── File signature map per layer ───────────────────────────────────────────
# If a layer has an entry here the directory must contain **at least one** of
# the listed files to count as a valid archive.  ``None`` means "any sub-
# directory is valid" (used for ``reports``).

LAYER_SIGNATURES: Dict[str, Optional[Sequence[str]]] = {
    "analyze": (
        "volume.json",
        "attitude.json",
        "trends.json",
        "geography.json",
        "publishers.json",
        "keywords.json",
        "classification.json",
    ),
    "topic": (
        "1主题统计结果.json",
        "2主题关键词.json",
        "3文档2D坐标.json",
        "4大模型再聚类结果.json",
        "5大模型主题关键词.json",
    ),
    "reports": None,
    "media_tags": (
        "summary.json",
        "candidates.json",
    ),
}


@dataclass
class ArchiveRecord:
    """Normalised archive metadata record returned by ``ArchiveLocator``."""

    id: str
    topic: str
    topic_identifier: str
    start: str
    end: str
    folder: str
    updated_at: str
    available_files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "topic": self.topic,
            "topic_identifier": self.topic_identifier,
            "start": self.start,
            "end": self.end,
            "folder": self.folder,
            "updated_at": self.updated_at,
        }
        if self.available_files:
            result["available_files"] = list(self.available_files)
        return result


# ── Folder-name helpers ────────────────────────────────────────────────────

def split_folder_range(folder: str) -> Tuple[str, str]:
    """Parse ``start_end`` or ``start`` style folder names into (start, end)."""
    token = str(folder or "").strip()
    if not token:
        return "", ""
    if "_" in token:
        start, end = token.split("_", 1)
        start = start.strip()
        end = end.strip() or start
    else:
        start = token
        end = token
    return start, end


def compose_folder_name(start: str, end: Optional[str] = None) -> str:
    """Build a folder name from start/end date strings."""
    start_text = str(start or "").strip()
    end_text = str(end or "").strip()
    if not start_text:
        return ""
    if end_text and end_text != start_text:
        return f"{start_text}_{end_text}"
    return start_text


# ── ArchiveLocator ─────────────────────────────────────────────────────────

class ArchiveLocator:
    """Unified archive scanner for all analysis layers.

    Replaces the per-module implementations:
    * ``analyze.api._collect_analyze_history``
    * ``topic.api._build_topic_identifier_candidates`` +
      ``topic.api._collect_bertopic_history_records``
    * ``report.api._collect_report_history``
    """

    def __init__(
        self,
        ctx: TopicContext,
        *,
        projects_root: Optional[Path] = None,
    ) -> None:
        self._ctx = ctx
        self._projects_root = projects_root or DATA_PROJECTS_ROOT

    # ── Candidate expansion ────────────────────────────────────────────

    def _expand_candidates(self) -> List[str]:
        """Return de-duplicated directory name candidates.

        Merges the logic previously in:
        * ``_collect_analyze_history`` (aliases + normalise)
        * ``_build_topic_identifier_candidates`` (aliases + resolve +
          normalise + suffix match on projects root)
        * ``_collect_report_history`` (aliases + normalise)
        """
        # ctx.aliases already contains identifier, raw values, resolved ids,
        # and normalised forms (built by resolve_context).
        candidates = list(self._ctx.aliases)

        # Prefer project-scoped storage keys when available (reports migration).
        project_id = str(getattr(self._ctx, "project_identifier", "") or "").strip()
        topic_id = str(self._ctx.identifier or "").strip()
        if project_id and topic_id:
            scoped = f"{project_id}-{topic_id}".strip("-")
            if scoped and scoped not in candidates:
                candidates.insert(0, scoped)

        # Suffix match: scan projects root for dirs ending with any alias.
        seed_labels = [
            v for v in (self._ctx.aliases or [self._ctx.identifier])
            if v
        ]
        if self._projects_root.exists():
            for label in seed_labels:
                suffix = f"-{label}"
                for entry in self._projects_root.iterdir():
                    if not entry.is_dir():
                        continue
                    name = entry.name
                    if name == label or name.endswith(suffix):
                        if name not in candidates:
                            candidates.append(name)

        return candidates

    # ── History listing ────────────────────────────────────────────────

    def list_history(
        self,
        layer: str,
        *,
        display_topic: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Scan the filesystem for archive entries in *layer* and return a
        list of ``ArchiveRecord`` dicts sorted newest-first.

        Parameters
        ----------
        layer:
            One of ``"analyze"``, ``"topic"``, ``"reports"``, etc.
        display_topic:
            Override for the ``topic`` field in each record.  Falls back
            to ``ctx.display_name``.
        """

        topic_display = display_topic or self._ctx.display_name or self._ctx.identifier
        signatures = LAYER_SIGNATURES.get(layer)
        candidates = self._expand_candidates()

        seen_dirs: set[str] = set()
        seen_ids: set[str] = set()
        records: List[Dict[str, Any]] = []

        for candidate in candidates:
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned in seen_dirs:
                continue
            seen_dirs.add(cleaned)

            layer_dir = self._projects_root / cleaned / layer
            if not layer_dir.exists() or not layer_dir.is_dir():
                continue

            for entry in layer_dir.iterdir():
                if not entry.is_dir() or entry.name.startswith("."):
                    continue

                start, end = split_folder_range(entry.name)
                if not start:
                    continue

                # Signature check
                available_keys: List[str] = []
                if signatures is not None:
                    for sig_file in signatures:
                        if (entry / sig_file).exists():
                            available_keys.append(
                                Path(sig_file).stem  # e.g. "volume"
                            )
                    if not available_keys:
                        # For analyze, also accept sub-dirs (function dirs)
                        if layer == "analyze":
                            has_subdirs = any(
                                child.is_dir() for child in entry.iterdir()
                            )
                            if not has_subdirs:
                                continue
                        else:
                            continue

                # Compute latest mtime
                effective_entry = entry
                redirected = False
                if layer == "reports":
                    pointer = entry / _MIGRATED_POINTER_FILENAME
                    if pointer.exists():
                        try:
                            import json as _json  # local import to keep module light

                            payload = _json.loads(pointer.read_text(encoding="utf-8"))
                        except Exception:
                            payload = {}
                        target_dir = str((payload or {}).get("target_dir") or "").strip()
                        if target_dir:
                            target_path = Path(target_dir)
                            if target_path.exists() and target_path.is_dir():
                                effective_entry = target_path
                                redirected = True

                try:
                    latest_mtime = effective_entry.stat().st_mtime
                except OSError:
                    latest_mtime = 0.0

                if signatures is not None:
                    for sig_file in signatures:
                        sig_path = effective_entry / sig_file
                        if sig_path.exists():
                            try:
                                latest_mtime = max(latest_mtime, sig_path.stat().st_mtime)
                            except OSError:
                                pass
                elif redirected and layer == "reports":
                    # Reports layer doesn't have signatures; include a light file listing
                    # so history callers can tell something exists at the target.
                    try:
                        available_keys = sorted([p.name for p in effective_entry.iterdir() if p.is_file() and not p.name.startswith(".")])[:60]
                    except Exception:
                        available_keys = []

                record_id = f"{cleaned}:{entry.name}"
                if record_id in seen_ids:
                    continue
                seen_ids.add(record_id)

                record = ArchiveRecord(
                    id=record_id,
                    topic=topic_display,
                    topic_identifier=cleaned,
                    start=start,
                    end=end,
                    folder=entry.name,
                    updated_at=self._format_timestamp(latest_mtime, layer),
                    available_files=available_keys if available_keys else [],
                )
                records.append({
                    **record.to_dict(),
                    "_updated_ts": latest_mtime,
                })

        # Sort newest first
        records.sort(key=lambda r: r.get("_updated_ts", 0), reverse=True)

        # Strip internal sort key and format
        for r in records:
            r.pop("_updated_ts", None)

        return records

    # ── Result directory resolution ────────────────────────────────────

    def resolve_result_dir(
        self,
        layer: str,
        start: str,
        end: Optional[str] = None,
    ) -> Optional[Path]:
        """Locate the result directory for a given layer and date range.

        Tries multiple folder-name patterns and multiple candidate
        identifiers.  Returns the first match or ``None``.
        """
        start_text = str(start or "").strip()
        end_text = str(end or "").strip()
        if not start_text:
            return None

        # Build folder candidates in priority order
        folder_candidates: List[str] = []
        composed = compose_folder_name(start_text, end_text or None)
        if composed:
            folder_candidates.append(composed)
        if end_text:
            alt = f"{start_text}_{end_text}"
            if alt not in folder_candidates:
                folder_candidates.append(alt)
        if start_text not in folder_candidates:
            folder_candidates.append(start_text)
        same_day = f"{start_text}_{start_text}"
        if same_day not in folder_candidates:
            folder_candidates.append(same_day)

        # Search across all candidate identifiers
        candidates = self._expand_candidates()
        for candidate in candidates:
            cleaned = str(candidate or "").strip()
            if not cleaned:
                continue
            for folder in folder_candidates:
                target = self._projects_root / cleaned / layer / folder
                if target.exists() and target.is_dir():
                    return target

        return None

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _format_timestamp(mtime: float, layer: str) -> str:
        """Format a modification timestamp.

        ``analyze`` and ``reports`` use local-time strings (matching the
        original implementation); ``topic`` (BERTopic) returns the raw
        float so the frontend can format it.
        """
        if layer == "topic":
            # BERTopic history originally returned raw floats
            return mtime
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))


__all__ = [
    "ArchiveLocator",
    "ArchiveRecord",
    "LAYER_SIGNATURES",
    "compose_folder_name",
    "split_folder_range",
]
