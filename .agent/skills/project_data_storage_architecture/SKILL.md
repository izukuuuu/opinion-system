---
name: Project Data Storage Architecture Analysis
description: In-depth analysis of the backend data storage architecture, covering the unified TopicContext/ArchiveLocator pattern, data fetching, querying, local/cloud interaction, and storage structure.
---

# Project Data Storage Architecture

## Core Design Philosophy: Cloud as Intermediate Layer

Data flows: **Cloud (SQL) → Local Cache → Local Analysis → Results**.

1. **Upload**: Cleaned `.jsonl` → cloud database via `backend/src/update/data_update.py`.
2. **Fetch**: SQL query by date range → local JSONL cache at `projects/{id}/fetch/{range}/`.
3. **Analyze**: Reads from local `fetch/` → Pandas calculations → JSON results → `analyze/` directory.

---

## Unified Topic Identity Model

**All "topic" identification is handled by a single model: `TopicContext`.**

### File: `backend/server_support/topic_context.py`

```python
@dataclass
class TopicContext:
    identifier: str        # Canonical local dir name (e.g. "20260304-091855-2025控烟舆情")
    display_name: str      # User-facing label
    db_topic: str          # Remote database name (e.g. "2025控烟舆情")
    log_project: str       # Name for operation logs
    aliases: List[str]     # All candidate strings for cross-identity matching
    dataset_meta: Dict     # Raw dataset metadata
```

**Factory function:** `resolve_context(payload, project_manager) → TopicContext`

This replaces the old scattered logic that was duplicated in `analyze/api.py`, `topic/api.py`, and `report/api.py`. The legacy `pipeline.py:resolve_topic_identifier()` is now a thin wrapper around `resolve_context()`.

### Candidate expansion order

1. Dataset metadata fields: `project_id`, `project_slug`, `project`, `topic_label`
2. Project manager resolution: `project_manager.resolve_identifier(project_name)`
3. `normalise_project_name(project_name)`
4. Raw `project_name`, `topic`, `topic_label` from the payload
5. Normalised forms (via `_normalise_topic()` from `paths.py`)
6. First candidate matching an existing directory wins as `identifier`

---

## Unified Archive Locator

**All "find directory / list history / get results" logic is handled by `ArchiveLocator`.**

### File: `backend/server_support/archive_locator.py`

```python
LAYER_SIGNATURES = {
    "analyze": ("volume.json", "attitude.json", "trends.json", ...),
    "topic":   ("1主题统计结果.json", "2主题关键词.json", ...),
    "reports": None,   # any subdirectory is valid
}

class ArchiveLocator:
    def __init__(self, ctx: TopicContext): ...
    def list_history(self, layer: str) -> list[dict]: ...
    def resolve_result_dir(self, layer, start, end) -> Path | None: ...
```

### How API routes use it

All three API blueprints follow the same pattern:

```python
# History endpoint
ctx = resolve_context(payload, PROJECT_MANAGER)
locator = ArchiveLocator(ctx)
records = locator.list_history("analyze")  # or "topic" / "reports"

# Results endpoint
ctx = resolve_context(payload, PROJECT_MANAGER)
locator = ArchiveLocator(ctx)
result_dir = locator.resolve_result_dir("analyze", start, end)
```

### `list_history(layer)` behaviour

1. Expands candidates from `ctx.aliases` + suffix-matching on `projects/` root
2. For each candidate dir, scans `{candidate}/{layer}/` for subdirectories
3. Parses folder names as `"start_end"` date ranges
4. **Signature check**: if `LAYER_SIGNATURES[layer]` is defined, at least one file must exist
5. Computes `updated_at` from file mtimes
6. Returns `ArchiveRecord` dicts sorted newest-first

### `resolve_result_dir(layer, start, end)` behaviour

1. Builds folder name candidates: `"start_end"`, `"start"`, `"start_start"`
2. Tries each candidate dir across all expanded identifiers
3. Returns the first existing directory or `None`

---

## Frontend Unified Adapter

### File: `frontend/src/composables/useArchiveHistory.js`

Shared normalizer consumed by all three page composables:

| Export | Purpose |
|---|---|
| `splitFolderRange(folder)` | Parse `"start_end"` folder names |
| `normaliseRecord(record, defaults, options)` | Normalise one record to standard shape |
| `normaliseArchiveRecords(records, defaults, options)` | Batch normalise + filter + limit |
| `normalizeArchiveResponse(response, layer, topicHint)` | Extract records from varying API response envelopes |
| `fetchAndNormaliseHistory(apiPath, layer, topicHint)` | Convenience: fetch + normalise |

### Standard normalised record shape

```javascript
{
  id: "identifier:folder",
  topic: "display name",
  topic_identifier: "local dir name",
  start: "2025-01-01",
  end: "2025-01-31",
  folder: "2025-01-01_2025-01-31",
  updated_at: "2025-02-01 12:00:00",
  // Optional:
  display_topic: "...",       // bertopic only
  available_files: ["..."]    // bertopic only
}
```

### Consumer composables

- `useBasicAnalysis.js` → delegates to `normaliseArchiveRecords` + `normalizeArchiveResponse`
- `useTopicBertopicView.js` → delegates to `normaliseArchiveRecords`
- `useReportGeneration.js` → delegates to `normaliseRecord` + `splitFolderRange`

---

## Project Storage Structure

All data lives under `backend/data/projects/{project_id}/`:

| Directory | Purpose | Managed by |
|---|---|---|
| `fetch/` | Local cache of cloud data (.jsonl) | `data_fetch.py` |
| `analyze/` | Analysis results (volume.json, etc.) + AI summaries | `analyze/runner.py`, `ArchiveLocator` |
| `topic/` | BERTopic results (主题统计, 关键词, 坐标, etc.) | `topic/bertopic/`, `ArchiveLocator` |
| `reports/` | Generated report payloads | `report/structured_service.py`, `ArchiveLocator` |
| `filter/` | Cleaning artifacts, input for Upload | filtering pipeline |
| `uploads/` | Upload records, metadata, manifest.json | `project/storage.py` |

### Management Core

- **ProjectManager** (`backend/src/project/manager.py`): creates directories, resolves identifiers, logs operations
- **Metadata**: `projects.json` / `projects.pkl` — project list, statuses, audit trail
- **TopicContext** (`server_support/topic_context.py`): canonical identity across all modules
- **ArchiveLocator** (`server_support/archive_locator.py`): canonical archive scanning across all layers
