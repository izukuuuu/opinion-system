"""Shared helper utilities for :mod:`backend.server` routes."""

from .configuration import (
    filter_ai_overview,
    load_config,
    load_databases_config,
    load_llm_config,
    persist_databases_config,
    persist_llm_config,
    reload_settings,
)
from .dataset_files import (
    ensure_raw_dataset_availability,
    iter_unique_strings,
    parse_column_mapping_from_form,
    parse_column_mapping_payload,
    resolve_dataset_payload,
    resolve_dataset_source_path,
    update_dataset_source_references,
)
from .filter_progress import collect_filter_status
from .filter_templates import (
    load_filter_template_config,
    persist_filter_template_config,
)
from .paths import (
    BACKEND_DIR,
    CONFIG_PATH,
    DATA_PROJECTS_ROOT,
    FILTER_PROMPT_DIR,
    FILTER_PROGRESS_DIR,
    FILTER_SUMMARY_FILENAME,
    PROJECT_ROOT,
    SRC_DIR,
)
from .pipeline import (
    normalise_topic_label,
    prepare_pipeline_args,
    resolve_topic_identifier,
)
from .responses import (
    error,
    evaluate_success,
    require_fields,
    serialise_result,
    success,
)

__all__ = [
    # Configuration helpers
    "filter_ai_overview",
    "load_config",
    "load_databases_config",
    "load_llm_config",
    "persist_databases_config",
    "persist_llm_config",
    "reload_settings",
    # Dataset helpers
    "ensure_raw_dataset_availability",
    "iter_unique_strings",
    "parse_column_mapping_from_form",
    "parse_column_mapping_payload",
    "resolve_dataset_payload",
    "resolve_dataset_source_path",
    "update_dataset_source_references",
    # Filter helpers
    "collect_filter_status",
    "load_filter_template_config",
    "persist_filter_template_config",
    # Paths
    "BACKEND_DIR",
    "CONFIG_PATH",
    "DATA_PROJECTS_ROOT",
    "FILTER_PROMPT_DIR",
    "FILTER_PROGRESS_DIR",
    "FILTER_SUMMARY_FILENAME",
    "PROJECT_ROOT",
    "SRC_DIR",
    # Pipeline helpers
    "normalise_topic_label",
    "prepare_pipeline_args",
    "resolve_topic_identifier",
    # Response helpers
    "error",
    "evaluate_success",
    "require_fields",
    "serialise_result",
    "success",
]
