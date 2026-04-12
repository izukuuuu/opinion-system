from __future__ import annotations

import atexit
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Sequence
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from server_support import get_active_database_connection, load_databases_config, load_llm_config
from ..utils.setting.paths import get_data_root
from ..utils.setting.settings import settings


ENV_DEVELOPMENT = "development"
ENV_PRODUCTION = "production"
BACKEND_SQLITE = "sqlite"
BACKEND_POSTGRES = "postgres"


@dataclass(frozen=True)
class ReportRuntimeProfile:
    environment: str
    persistence_enabled: bool
    source_mode: str
    connection_id: str
    connection_name: str
    connection_engine: str
    schema_name: str
    resolved_database: str
    resolved_host: str
    resolved_url_redacted: str
    checkpointer_backend: str
    checkpoint_locator: str
    checkpoint_path: str
    langsmith_enabled: bool
    langsmith_project: str


_SHARED_CHECKPOINTERS: Dict[str, tuple[Any, Any, ReportRuntimeProfile]] = {}
SOURCE_REUSE_ACTIVE = "reuse_active"


def _read_setting(path: str, default: Any = None) -> Any:
    try:
        settings.reload()
    except Exception:
        pass
    return settings.get(path, default)


def _read_llm_runtime_config() -> Dict[str, Any]:
    config = load_llm_config()
    langchain = config.get("langchain") if isinstance(config.get("langchain"), dict) else {}
    report = langchain.get("report") if isinstance(langchain.get("report"), dict) else {}
    runtime = report.get("runtime") if isinstance(report.get("runtime"), dict) else {}
    return runtime


def _env_text(name: str) -> str:
    return str(os.getenv(name) or "").strip()


def _read_text(path: str, env_name: str, default: str = "") -> str:
    env_value = _env_text(env_name)
    if env_value:
        return env_value
    return str(_read_setting(path, default) or default).strip()


def _read_bool(path: str, env_name: str, default: bool = False) -> bool:
    env_value = _env_text(env_name).lower()
    if env_value:
        return env_value in {"1", "true", "yes", "on"}
    value = _read_setting(path, default)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _environment() -> str:
    raw = (
        _env_text("OPINION_REPORT_RUNTIME_ENV")
        or str((_read_llm_runtime_config().get("environment") or "")).strip()
        or _env_text("APP_ENV")
        or _env_text("FLASK_ENV")
    ).lower()
    return ENV_PRODUCTION if raw in {"prod", "production"} else ENV_DEVELOPMENT


def _checkpointer_backend() -> str:
    persistence = _runtime_persistence_config()
    configured = (
        _env_text("OPINION_REPORT_CHECKPOINTER_BACKEND")
        or str(persistence.get("backend") or "").strip()
    ).lower()
    if configured in {BACKEND_SQLITE, BACKEND_POSTGRES}:
        return configured
    if _persistence_enabled():
        return BACKEND_POSTGRES
    return BACKEND_POSTGRES if _environment() == ENV_PRODUCTION else BACKEND_SQLITE


def _runtime_persistence_config() -> Dict[str, Any]:
    runtime = _read_llm_runtime_config()
    persistence = runtime.get("persistence") if isinstance(runtime.get("persistence"), dict) else {}
    return persistence


def _persistence_enabled() -> bool:
    persistence = _runtime_persistence_config()
    value = persistence.get("enabled", None)
    if value is None:
        return _checkpointer_backend() == BACKEND_POSTGRES
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _source_mode() -> str:
    persistence = _runtime_persistence_config()
    configured = str(persistence.get("source_mode") or persistence.get("source") or "").strip().lower()
    return SOURCE_REUSE_ACTIVE if configured in {"", SOURCE_REUSE_ACTIVE, "reuse_active_database_connection"} else configured


def _schema_name() -> str:
    persistence = _runtime_persistence_config()
    schema_name = str(persistence.get("schema_name") or "report_runtime").strip()
    return schema_name or "report_runtime"


def _sqlite_locator(purpose: str, *, locator_hint: str = "") -> str:
    hinted = str(locator_hint or "").strip()
    if hinted:
        return hinted
    configured = _read_text("llm.langchain.report.runtime.persistence.sqlite_path", "OPINION_REPORT_SQLITE_CHECKPOINTER_PATH", "")
    if configured:
        return configured
    base_dir = get_data_root() / "_report" / "checkpoints"
    base_dir.mkdir(parents=True, exist_ok=True)
    return str(base_dir / f"{purpose}.sqlite")


def _is_explicit_sqlite_locator(locator_hint: str) -> bool:
    hinted = str(locator_hint or "").strip().lower()
    if not hinted:
        return False
    return hinted.endswith(".sqlite") or hinted.endswith(".db")

def _build_postgres_runtime_connection(*, purpose: str, locator_hint: str = "") -> tuple[str, str, Dict[str, str]]:
    if _source_mode() != SOURCE_REUSE_ACTIVE:
        raise RuntimeError("Report runtime persistence only supports reusing the active database connection.")
    databases_config = load_databases_config()
    active = get_active_database_connection(databases_config)
    if not active:
        raise RuntimeError("Report runtime persistence requires an active database connection.")
    engine = str(active.get("engine") or "").strip().lower()
    if engine != "postgresql":
        raise RuntimeError("Report runtime persistence requires the active database connection to be PostgreSQL.")
    raw_url = str(active.get("url") or "").strip()
    if not raw_url:
        raise RuntimeError("The active PostgreSQL connection is missing its URL.")
    parsed = make_url(raw_url)
    database_name = str(parsed.database or "").strip()
    host = str(parsed.host or "").strip()
    schema_name = _schema_name()
    options_value = f"-csearch_path={schema_name}"
    query = dict(parsed.query) if isinstance(parsed.query, dict) else {}
    query["application_name"] = "opinion-system-report-runtime"
    query["options"] = options_value
    runtime_url = parsed.set(drivername="postgresql", query=query)
    locator = str(locator_hint or f"postgres://{active.get('id') or 'active'}/{database_name or 'postgres'}?schema={schema_name}&purpose={purpose}").strip()
    redacted = runtime_url.render_as_string(hide_password=True)
    dsn = runtime_url.render_as_string(hide_password=False)
    summary = {
        "connection_id": str(active.get("id") or "").strip(),
        "connection_name": str(active.get("name") or "").strip(),
        "connection_engine": engine,
        "schema_name": schema_name,
        "resolved_database": database_name,
        "resolved_host": host,
        "resolved_url_redacted": redacted,
        "checkpoint_locator": locator,
        "dsn": dsn,
    }
    return dsn, locator, summary


def _ensure_postgres_schema(dsn: str, schema_name: str) -> None:
    engine = create_engine(dsn, pool_pre_ping=True, connect_args={"connect_timeout": 10, "application_name": "opinion-system-report-runtime"})
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name.replace(chr(34), "")}"'))
    finally:
        engine.dispose()


def _langsmith_project() -> str:
    return (
        _env_text("OPINION_REPORT_LANGSMITH_PROJECT")
        or str((((_read_llm_runtime_config().get("observability") if isinstance(_read_llm_runtime_config().get("observability"), dict) else {}).get("langsmith") or {}).get("project") or "")).strip()
        or "opinion-system-report"
    )


def _langsmith_endpoint() -> str:
    observability = _read_llm_runtime_config().get("observability") if isinstance(_read_llm_runtime_config().get("observability"), dict) else {}
    langsmith = observability.get("langsmith") if isinstance(observability.get("langsmith"), dict) else {}
    return (
        _env_text("LANGSMITH_ENDPOINT")
        or _env_text("OPINION_REPORT_LANGSMITH_ENDPOINT")
        or str(langsmith.get("endpoint") or "").strip()
    )


def _langsmith_api_key() -> str:
    runtime = _read_llm_runtime_config()
    observability = runtime.get("observability") if isinstance(runtime.get("observability"), dict) else {}
    langsmith = observability.get("langsmith") if isinstance(observability.get("langsmith"), dict) else {}
    llm_config = load_llm_config()
    credentials = llm_config.get("credentials") if isinstance(llm_config.get("credentials"), dict) else {}
    credential_api_key = str(credentials.get("langsmith_api_key") or "").strip()
    return (
        _env_text("LANGSMITH_API_KEY")
        or _env_text("OPINION_REPORT_LANGSMITH_API_KEY")
        or credential_api_key
        or str(langsmith.get("api_key") or "").strip()
    )


def _langsmith_enabled() -> bool:
    observability = _read_llm_runtime_config().get("observability") if isinstance(_read_llm_runtime_config().get("observability"), dict) else {}
    langsmith = observability.get("langsmith") if isinstance(observability.get("langsmith"), dict) else {}
    env_value = _env_text("OPINION_REPORT_LANGSMITH_ENABLED").lower()
    if env_value:
        explicit = env_value in {"1", "true", "yes", "on"}
    else:
        explicit = bool(langsmith.get("enabled", False))
    if explicit:
        return True
    tracing_value = _env_text("LANGCHAIN_TRACING_V2").lower()
    return tracing_value in {"1", "true", "yes", "on"}


def _configure_langsmith(project: str) -> None:
    if not _langsmith_enabled():
        return
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", project)
    endpoint = _langsmith_endpoint()
    api_key = _langsmith_api_key()
    if endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", endpoint)
    if api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", api_key)


def _require_production_backend() -> None:
    backend = _checkpointer_backend()
    if _environment() == ENV_PRODUCTION and backend != BACKEND_POSTGRES:
        raise RuntimeError("Report runtime production mode requires PostgresSaver; sqlite and memory are not allowed.")


def resolve_runtime_profile(*, purpose: str, locator_hint: str = "") -> ReportRuntimeProfile:
    if _is_explicit_sqlite_locator(locator_hint):
        sqlite_path = _sqlite_locator(purpose, locator_hint=locator_hint)
        project = _langsmith_project()
        _configure_langsmith(project)
        return ReportRuntimeProfile(
            environment=_environment(),
            persistence_enabled=False,
            source_mode="sqlite_explicit_override",
            connection_id="",
            connection_name="",
            connection_engine="",
            schema_name="",
            resolved_database="",
            resolved_host="",
            resolved_url_redacted="",
            checkpointer_backend=BACKEND_SQLITE,
            checkpoint_locator=sqlite_path,
            checkpoint_path=sqlite_path,
            langsmith_enabled=_langsmith_enabled(),
            langsmith_project=project,
        )
    _require_production_backend()
    backend = _checkpointer_backend()
    project = _langsmith_project()
    _configure_langsmith(project)
    if backend == BACKEND_POSTGRES:
        dsn, locator, summary = _build_postgres_runtime_connection(purpose=purpose, locator_hint=locator_hint)
        return ReportRuntimeProfile(
            environment=_environment(),
            persistence_enabled=_persistence_enabled(),
            source_mode=_source_mode(),
            connection_id=summary["connection_id"],
            connection_name=summary["connection_name"],
            connection_engine=summary["connection_engine"],
            schema_name=summary["schema_name"],
            resolved_database=summary["resolved_database"],
            resolved_host=summary["resolved_host"],
            resolved_url_redacted=summary["resolved_url_redacted"],
            checkpointer_backend=BACKEND_POSTGRES,
            checkpoint_locator=locator,
            checkpoint_path="",
            langsmith_enabled=_langsmith_enabled(),
            langsmith_project=project,
        )
    sqlite_path = _sqlite_locator(purpose, locator_hint=locator_hint)
    return ReportRuntimeProfile(
        environment=_environment(),
        persistence_enabled=False,
        source_mode="sqlite_development",
        connection_id="",
        connection_name="",
        connection_engine="",
        schema_name="",
        resolved_database="",
        resolved_host="",
        resolved_url_redacted="",
        checkpointer_backend=BACKEND_SQLITE,
        checkpoint_locator=sqlite_path,
        checkpoint_path=sqlite_path,
        langsmith_enabled=_langsmith_enabled(),
        langsmith_project=project,
    )


@contextmanager
def open_report_checkpointer(*, purpose: str, locator_hint: str = "") -> Iterator[tuple[Any, ReportRuntimeProfile]]:
    profile = resolve_runtime_profile(purpose=purpose, locator_hint=locator_hint)
    if profile.checkpointer_backend == BACKEND_SQLITE:
        from langgraph.checkpoint.sqlite import SqliteSaver

        Path(profile.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(profile.checkpoint_path) as checkpointer:
            yield checkpointer, profile
        return

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except Exception as exc:
        raise RuntimeError(
            "Report runtime requires langgraph-checkpoint-postgres for production persistence."
        ) from exc
    dsn, _, summary = _build_postgres_runtime_connection(purpose=purpose, locator_hint=locator_hint)
    _ensure_postgres_schema(dsn, summary["schema_name"])
    with PostgresSaver.from_conn_string(dsn) as checkpointer:
        setup = getattr(checkpointer, "setup", None)
        if callable(setup):
            setup()
        yield checkpointer, profile


def get_shared_report_checkpointer(*, purpose: str, locator_hint: str = "") -> tuple[Any, ReportRuntimeProfile]:
    profile = resolve_runtime_profile(purpose=purpose, locator_hint=locator_hint)
    cache_key = f"{profile.checkpointer_backend}:{profile.checkpoint_locator}:{purpose}"
    cached = _SHARED_CHECKPOINTERS.get(cache_key)
    if cached is not None:
        return cached[1], cached[2]
    if profile.checkpointer_backend == BACKEND_SQLITE:
        from langgraph.checkpoint.sqlite import SqliteSaver

        Path(profile.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        manager = SqliteSaver.from_conn_string(profile.checkpoint_path)
    else:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except Exception as exc:
            raise RuntimeError(
                "Report runtime requires langgraph-checkpoint-postgres for production persistence."
            ) from exc
        dsn, _, summary = _build_postgres_runtime_connection(purpose=purpose, locator_hint=locator_hint)
        _ensure_postgres_schema(dsn, summary["schema_name"])
        manager = PostgresSaver.from_conn_string(dsn)
    checkpointer = manager.__enter__()
    setup = getattr(checkpointer, "setup", None)
    if callable(setup):
        setup()
    _SHARED_CHECKPOINTERS[cache_key] = (manager, checkpointer, profile)
    atexit.register(_close_shared_report_checkpointer, cache_key)
    return checkpointer, profile


def _close_shared_report_checkpointer(cache_key: str) -> None:
    cached = _SHARED_CHECKPOINTERS.pop(cache_key, None)
    if cached is None:
        return
    manager = cached[0]
    try:
        manager.__exit__(None, None, None)
    except Exception:
        return


def build_report_runnable_config(
    *,
    thread_id: str,
    purpose: str,
    task_id: str = "",
    tags: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    locator_hint: str = "",
) -> Dict[str, Any]:
    profile = resolve_runtime_profile(purpose=purpose, locator_hint=locator_hint)
    tag_list = [str(item).strip() for item in (tags or ()) if str(item or "").strip()]
    tag_list.extend(
        [
            "report-runtime",
            f"report-purpose:{purpose}",
            f"checkpoint:{profile.checkpointer_backend}",
        ]
    )
    merged_metadata = {
        "report_runtime": {
            "purpose": purpose,
            "task_id": str(task_id or "").strip(),
            "thread_id": str(thread_id or "").strip(),
            "persistence_enabled": profile.persistence_enabled,
            "source_mode": profile.source_mode,
            "connection_id": profile.connection_id,
            "schema_name": profile.schema_name,
            "resolved_database": profile.resolved_database,
            "checkpoint_backend": profile.checkpointer_backend,
            "checkpoint_locator": profile.checkpoint_locator,
            "environment": profile.environment,
            "langsmith_enabled": profile.langsmith_enabled,
            "langsmith_project": profile.langsmith_project,
        }
    }
    if isinstance(metadata, Mapping):
        merged_metadata.update(dict(metadata))
    return {
        "configurable": {"thread_id": str(thread_id or "").strip()},
        "tags": list(dict.fromkeys(tag_list)),
        "metadata": merged_metadata,
    }


def build_runtime_diagnostics(*, purpose: str, thread_id: str, task_id: str = "", locator_hint: str = "") -> Dict[str, Any]:
    profile = resolve_runtime_profile(purpose=purpose, locator_hint=locator_hint)
    return {
        "runtime_mode": purpose,
        "thread_id": str(thread_id or "").strip(),
        "task_id": str(task_id or "").strip(),
        "persistence_enabled": profile.persistence_enabled,
        "source_mode": profile.source_mode,
        "connection_id": profile.connection_id,
        "schema_name": profile.schema_name,
        "resolved_database": profile.resolved_database,
        "checkpoint_backend": profile.checkpointer_backend,
        "checkpoint_locator": profile.checkpoint_locator,
        "checkpoint_path": profile.checkpoint_path,
        "environment": profile.environment,
        "langsmith_enabled": profile.langsmith_enabled,
        "langsmith_project": profile.langsmith_project,
    }


__all__ = [
    "BACKEND_POSTGRES",
    "BACKEND_SQLITE",
    "ENV_DEVELOPMENT",
    "ENV_PRODUCTION",
    "ReportRuntimeProfile",
    "build_report_runnable_config",
    "build_runtime_diagnostics",
    "get_shared_report_checkpointer",
    "open_report_checkpointer",
    "resolve_runtime_profile",
]
