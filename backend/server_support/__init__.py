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
from .rag_config import (
    load_rag_config,
    persist_rag_config,
    mask_api_keys,
    validate_rag_config,
    get_default_rag_config,
)
from .rag import (
    ensure_rag_ready,
    get_rag_build_status,
    ensure_routerrag_db,
    ensure_tagrag_db,
    list_project_routerrag_topics,
    list_project_tagrag_topics,
    start_rag_build,
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
from .postclean_jobs import (
    create_postclean_job,
    get_postclean_job,
    heartbeat_postclean_job,
    update_postclean_job,
)
from .deduplicate_jobs import (
    create_deduplicate_job,
    get_deduplicate_job,
    heartbeat_deduplicate_job,
    update_deduplicate_job,
)
from .fetch_refresh_jobs import (
    create_fetch_refresh_job,
    get_fetch_refresh_job,
    heartbeat_fetch_refresh_job,
    load_fetch_refresh_worker_status,
    list_fetch_refresh_jobs,
    update_fetch_refresh_job,
    update_fetch_refresh_worker,
)
from .rebuild_fetch_jobs import (
    create_rebuild_fetch_job,
    get_rebuild_fetch_job,
    heartbeat_rebuild_fetch_job,
    list_rebuild_fetch_jobs,
    update_rebuild_fetch_job,
)
from .publisher_detection import (
    build_status_payload as build_publisher_detection_status_payload,
    create_or_reuse_task as create_publisher_detection_task,
)
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
from .topic_context import (
    TopicContext,
    context_to_tuple,
    resolve_context,
)
from .archive_locator import (
    ArchiveLocator,
    ArchiveRecord,
    LAYER_SIGNATURES,
    compose_folder_name,
    split_folder_range,
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
    # RAG configuration helpers
    "load_rag_config",
    "persist_rag_config",
    "mask_api_keys",
    "validate_rag_config",
    "get_default_rag_config",
    # RAG storage helpers
    "ensure_routerrag_db",
    "ensure_tagrag_db",
    "ensure_rag_ready",
    "get_rag_build_status",
    "list_project_routerrag_topics",
    "list_project_tagrag_topics",
    "start_rag_build",
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
    "create_postclean_job",
    "create_deduplicate_job",
    "create_fetch_refresh_job",
    "create_publisher_detection_task",
    "create_rebuild_fetch_job",
    "get_deduplicate_job",
    "get_fetch_refresh_job",
    "get_postclean_job",
    "get_rebuild_fetch_job",
    "heartbeat_deduplicate_job",
    "heartbeat_fetch_refresh_job",
    "heartbeat_postclean_job",
    "heartbeat_rebuild_fetch_job",
    "is_filter_job_running",
    "list_fetch_refresh_jobs",
    "list_rebuild_fetch_jobs",
    "load_fetch_refresh_worker_status",
    "load_filter_template_config",
    "mark_filter_job_finished",
    "mark_filter_job_running",
    "update_deduplicate_job",
    "update_fetch_refresh_job",
    "update_fetch_refresh_worker",
    "update_postclean_job",
    "update_rebuild_fetch_job",
    "build_publisher_detection_status_payload",
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
    # Topic context
    "TopicContext",
    "context_to_tuple",
    "resolve_context",
    # Archive locator
    "ArchiveLocator",
    "ArchiveRecord",
    "LAYER_SIGNATURES",
    "compose_folder_name",
    "split_folder_range",
    # Response helpers
    "error",
    "evaluate_success",
    "require_fields",
    "serialise_result",
    "success",
]
