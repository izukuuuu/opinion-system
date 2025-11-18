"""Shared helper utilities for :mod:`backend.server` routes."""

from .archives import (  # type: ignore
    collect_layer_archives,
    collect_project_archives,
    resolve_stage_processing_date,
)
from .backups import (  # type: ignore
    build_settings_backup,
    restore_settings_backup,
)
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
from .filter_jobs import (
    is_filter_job_running,
    mark_filter_job_finished,
    mark_filter_job_running,
)
from .filter_progress import collect_filter_status
from .filter_templates import (
    load_filter_template_config,
    persist_filter_template_config,
)
from .content_analysis_prompts import (
    content_prompt_path,
    load_content_prompt_config,
    persist_content_prompt_config,
)
from .paths import (
    BACKEND_DIR,
    CONFIG_PATH,
    DATA_PROJECTS_ROOT,
    CONFIGS_DIR,
    CONTENT_PROMPT_DIR,
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
    # Archive helpers
    "collect_layer_archives",
    "collect_project_archives",
    "resolve_stage_processing_date",
    # Backup helpers
    "build_settings_backup",
    "restore_settings_backup",
    # Configuration helpers
    "filter_ai_overview",
    "load_config",
    "load_databases_config",
    "load_llm_config",
    "persist_databases_config",
    "persist_llm_config",
    "reload_settings",
    # Content analysis prompt helpers
    "content_prompt_path",
    "load_content_prompt_config",
    "persist_content_prompt_config",
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
    "is_filter_job_running",
    "load_filter_template_config",
    "mark_filter_job_finished",
    "mark_filter_job_running",
    "persist_filter_template_config",
    # Paths
    "BACKEND_DIR",
    "CONFIG_PATH",
    "DATA_PROJECTS_ROOT",
    "CONFIGS_DIR",
    "CONTENT_PROMPT_DIR",
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
