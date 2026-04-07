"""Database-side cleanup helpers for postclean, publisher inspection, and dedup."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd
from sqlalchemy import bindparam, inspect, text

from ..topic.prompt_config import load_topic_bertopic_prompt_config
from ..utils.io.excel import read_jsonl, write_jsonl
from ..utils.io.db import db_manager
from ..utils.logging.logging import (
    log_error,
    log_module_start,
    log_success,
    setup_logger,
)
from ..utils.setting.paths import ensure_bucket, get_relative_path
from .keyword_cleaning import (
    POSTCLEAN_REPORT_DIR,
    _normalise_match_text,
    _normalise_terms,
    _safe_name,
    _utc_now,
    _write_json,
    load_shared_noise_terms,
)

DEDUP_REPORT_DIR = "deduplicate"
_UNKNOWN_AUTHORS = {
    "",
    "未知",
    "-",
    "unknown",
    "未知发布者",
    "none",
    "null",
    "n/a",
}
_NORMALISED_UNKNOWN_AUTHORS = {_normalise_match_text(item) for item in _UNKNOWN_AUTHORS}
_UNKNOWN_URLS = {
    "",
    "未知",
    "-",
    "unknown",
    "none",
    "null",
    "n/a",
}
_NORMALISED_UNKNOWN_URLS = {_normalise_match_text(item) for item in _UNKNOWN_URLS}
_POSTCLEAN_SAMPLE_LIMIT = 3
_SNAPSHOT_CHUNK_SIZE = 5000


def load_shared_publisher_blacklist(topic: str) -> Dict[str, Any]:
    payload = load_topic_bertopic_prompt_config(topic)
    raw_values = payload.get("publisher_blacklist", [])
    values = _normalise_terms(raw_values)
    return {
        "authors": values,
        "path": str(payload.get("path") or ""),
        "topic": str(payload.get("topic") or topic).strip() or topic,
    }


def _quote_identifier(dialect_name: str, name: str) -> str:
    if _is_mysql_dialect(dialect_name):
        return f"`{name.replace('`', '``')}`"
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def _normalise_dialect_name(dialect_name: str) -> str:
    return str(dialect_name or "").strip().lower()


def _is_mysql_dialect(dialect_name: str) -> bool:
    return _normalise_dialect_name(dialect_name).startswith("mysql")


def _is_postgresql_dialect(dialect_name: str) -> bool:
    return _normalise_dialect_name(dialect_name).startswith("postgres")


def _linebreak_char_fn(dialect_name: str) -> str:
    return "CHAR" if _is_mysql_dialect(dialect_name) else "CHR"


def _concat_text_expressions(dialect_name: str, expressions: Sequence[str]) -> str:
    if _is_mysql_dialect(dialect_name):
        return f"CONCAT({', '.join(expressions)})"
    return "(" + " || ".join(expressions) + ")"


def _like_escape_clause(dialect_name: str) -> str:
    if _is_postgresql_dialect(dialect_name):
        return r" ESCAPE '\'"
    if _is_mysql_dialect(dialect_name):
        return r" ESCAPE '\\'"
    return ""


def _normalised_column_expr(dialect_name: str, column_name: str) -> str:
    quoted = _quote_identifier(dialect_name, column_name)
    char_fn = _linebreak_char_fn(dialect_name)
    return (
        f"LOWER(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE({quoted}, ''), ' ', ''), "
        f"{char_fn}(10), ''), {char_fn}(13), ''), {char_fn}(9), ''))"
    )


def _combined_text_expr(dialect_name: str, columns: Sequence[str]) -> str:
    expressions = [_normalised_column_expr(dialect_name, column) for column in columns]
    return _concat_text_expressions(dialect_name, expressions)


def _normalised_datetime_expr(dialect_name: str, column_name: str) -> str:
    quoted = _quote_identifier(dialect_name, column_name)
    if _is_mysql_dialect(dialect_name):
        return f"COALESCE(DATE_FORMAT({quoted}, '%Y-%m-%d %H:%i:%s'), '')"
    return f"COALESCE(TO_CHAR({quoted}, 'YYYY-MM-DD HH24:MI:SS'), '')"


def _sql_literal(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _is_meaningful_normalised_expr(expr: str, placeholders: Sequence[str]) -> str:
    if not placeholders:
        return f"({expr}) <> ''"
    placeholder_sql = ", ".join(_sql_literal(item) for item in placeholders)
    return f"(({expr}) <> '' AND ({expr}) NOT IN ({placeholder_sql}))"


def _deduplicate_temp_table_name(table_name: str) -> str:
    digest = hashlib.sha1(str(table_name or "").encode("utf-8")).hexdigest()[:12]
    return f"__dedup_tmp_{digest}"


def _snapshot_root(topic: str) -> Path:
    return ensure_bucket("results", topic, "deduplicate_snapshots")


def _snapshot_directory(topic: str, snapshot_id: str) -> Path:
    path = _snapshot_root(topic) / str(snapshot_id or "").strip()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_manifest_path(topic: str, snapshot_id: str) -> Path:
    return _snapshot_root(topic) / str(snapshot_id or "").strip() / "manifest.json"


def _load_snapshot_manifest(path: Path) -> Optional[Dict[str, Any]]:
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_database_deduplicate_snapshots(
    topic: str,
    database: str,
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    root = _snapshot_root(topic)
    database_name = str(database or "").strip()
    snapshots: List[Dict[str, Any]] = []
    if not root.exists():
        return snapshots
    for manifest_path in root.glob("*/manifest.json"):
        payload = _load_snapshot_manifest(manifest_path)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("database") or "").strip() != database_name:
            continue
        snapshots.append(payload)
    snapshots.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return snapshots[: max(1, int(limit or 10))]


def _get_snapshot_manifest(topic: str, database: str, snapshot_id: str) -> Optional[Dict[str, Any]]:
    target_id = str(snapshot_id or "").strip()
    if not target_id:
        return None
    path = _snapshot_manifest_path(topic, target_id)
    payload = _load_snapshot_manifest(path)
    if not isinstance(payload, dict):
        return None
    if str(payload.get("database") or "").strip() != str(database or "").strip():
        return None
    return payload


def _write_snapshot_manifest(path: Path, payload: Dict[str, Any]) -> None:
    _write_json(path, payload)


def _create_database_snapshot(
    conn,
    *,
    topic: str,
    database: str,
    dialect_name: str,
    table_names: Sequence[str],
    inspector,
) -> Dict[str, Any]:
    snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_dir = _snapshot_directory(topic, snapshot_id)
    tables_payload: List[Dict[str, Any]] = []
    total_rows = 0

    for table_name in table_names:
        ordered_columns = [str(column.get("name") or "").strip() for column in inspector.get_columns(table_name)]
        quoted_columns = [_quote_identifier(dialect_name, column_name) for column_name in ordered_columns]
        selected_columns_sql = ", ".join(quoted_columns) if quoted_columns else "*"
        quoted_table = _quote_identifier(dialect_name, table_name)
        sql = text(f"SELECT {selected_columns_sql} FROM {quoted_table}")
        output_path = snapshot_dir / f"{table_name}.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        row_count = 0
        chunk_index = 0
        for chunk in pd.read_sql_query(sql, conn, chunksize=_SNAPSHOT_CHUNK_SIZE):
            write_jsonl(chunk, output_path, mode="w" if chunk_index == 0 else "a")
            row_count += len(chunk)
            chunk_index += 1
        if chunk_index == 0:
            write_jsonl(pd.DataFrame(columns=ordered_columns), output_path, mode="w")

        total_rows += row_count
        tables_payload.append(
            {
                "table": table_name,
                "row_count": row_count,
                "columns": ordered_columns,
                "file": output_path.name,
                "path": get_relative_path(output_path),
            }
        )

    manifest = {
        "snapshot_id": snapshot_id,
        "topic": topic,
        "database": str(database or "").strip(),
        "created_at": _utc_now(),
        "tables": tables_payload,
        "table_count": len(tables_payload),
        "total_rows": total_rows,
        "path": get_relative_path(snapshot_dir),
    }
    _write_snapshot_manifest(snapshot_dir / "manifest.json", manifest)
    return manifest


def restore_database_snapshot(
    topic: str,
    database: str,
    *,
    snapshot_id: Optional[str] = None,
    tables: Optional[Sequence[str]] = None,
    logger=None,
    progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    target_database = str(database or "").strip()
    if not target_database:
        return {"status": "error", "message": "Missing required field(s): database"}

    snapshots = list_database_deduplicate_snapshots(topic, target_database, limit=20)
    manifest = None
    if snapshot_id:
        manifest = _get_snapshot_manifest(topic, target_database, snapshot_id)
    elif snapshots:
        manifest = snapshots[0]
    if not isinstance(manifest, dict):
        return {"status": "error", "message": "未找到可恢复的数据库快照"}

    if logger is None:
        logger = setup_logger(topic, "deduplicate-restore")
    log_module_start(logger, "DatabaseDeduplicateRestore")

    def _emit(event: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if progress_callback:
            try:
                progress_callback(event, message, payload or {})
            except Exception:
                pass

    snapshot_tables = manifest.get("tables") if isinstance(manifest.get("tables"), list) else []
    requested_tables = {
        str(item or "").strip()
        for item in (tables or [])
        if str(item or "").strip()
    }
    target_tables = [
        item for item in snapshot_tables
        if isinstance(item, dict) and str(item.get("table") or "").strip()
        and (not requested_tables or str(item.get("table") or "").strip() in requested_tables)
    ]
    missing_tables = sorted(requested_tables - {str(item.get("table") or "").strip() for item in target_tables})
    if not target_tables:
        return {
            "status": "error",
            "message": "指定快照中没有可恢复的数据表",
            "missing_tables": missing_tables,
            "snapshot": manifest,
        }

    engine = None
    try:
        engine = db_manager.get_engine_for_database(target_database)
        from ..update.data_update import create_table_with_standard_schema  # Local import to avoid module cycle.

        with engine.begin() as conn:
            dialect_name = conn.dialect.name
            inspector = inspect(conn)
            total_tables = len(target_tables)
            completed_tables = 0
            restored_rows = 0
            report_tables: List[Dict[str, Any]] = []

            _emit(
                "phase.started",
                f"数据库恢复已启动，准备恢复 {total_tables} 张表。",
                {"total_tables": total_tables, "completed_tables": 0, "deleted_rows": 0, "percentage": 0},
            )

            for item in target_tables:
                table_name = str(item.get("table") or "").strip()
                file_name = str(item.get("file") or "").strip()
                snapshot_file = _snapshot_directory(topic, str(manifest.get("snapshot_id") or "")) / file_name
                _emit(
                    "table.started",
                    f"开始恢复数据表 {table_name}。",
                    {
                        "table": table_name,
                        "total_tables": total_tables,
                        "completed_tables": completed_tables,
                        "deleted_rows": restored_rows,
                    },
                )

                if not inspector.has_table(table_name):
                    if not create_table_with_standard_schema(conn, table_name, topic, logger):
                        raise RuntimeError(f"{table_name} 建表失败，无法恢复快照")
                    inspector = inspect(conn)

                columns = [str(column.get("name") or "").strip() for column in inspector.get_columns(table_name)]
                if not snapshot_file.exists():
                    raise RuntimeError(f"{table_name} 快照文件缺失: {snapshot_file}")

                stored_row_count = int(item.get("row_count") or 0)
                stored_columns = item.get("columns") if isinstance(item.get("columns"), list) else columns
                if stored_row_count > 0:
                    df = read_jsonl(snapshot_file)
                else:
                    df = pd.DataFrame(columns=stored_columns)
                if columns:
                    for column_name in columns:
                        if column_name not in df.columns:
                            df[column_name] = None
                    df = df[columns]

                quoted_table = _quote_identifier(dialect_name, table_name)
                conn.execute(text(f"DELETE FROM {quoted_table}"))
                if not df.empty:
                    df.to_sql(
                        table_name,
                        con=conn,
                        if_exists="append",
                        index=False,
                        method="multi",
                        chunksize=1000,
                    )

                table_rows = len(df)
                restored_rows += table_rows
                completed_tables += 1
                report_tables.append(
                    {
                        "table": table_name,
                        "status": "ok",
                        "restored_rows": table_rows,
                        "snapshot_file": get_relative_path(snapshot_file),
                    }
                )
                _emit(
                    "table.completed",
                    f"{table_name} 恢复完成，写回 {table_rows} 条记录。",
                    {
                        "table": table_name,
                        "total_tables": total_tables,
                        "completed_tables": completed_tables,
                        "deleted_rows": restored_rows,
                        "percentage": round(completed_tables / max(1, total_tables) * 100),
                    },
                )

    except Exception as exc:
        detail = f"数据库恢复失败: {exc}"
        log_error(logger, detail, "DatabaseDeduplicateRestore")
        _emit("task.failed", detail, {})
        return {"status": "error", "message": detail, "snapshot": manifest}
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass

    result = {
        "status": "ok",
        "topic": topic,
        "database": target_database,
        "snapshot": manifest,
        "restored_rows": restored_rows,
        "missing_tables": missing_tables,
        "tables": report_tables,
    }
    _emit(
        "task.completed",
        f"数据库恢复完成，共写回 {restored_rows} 条记录。",
        {
            "total_tables": len(target_tables),
            "completed_tables": len(target_tables),
            "deleted_rows": restored_rows,
            "percentage": 100,
        },
    )
    return result


def _build_deduplicate_key_expr(
    dialect_name: str,
    column_names: Sequence[str],
) -> tuple[Optional[str], str]:
    normalised_columns = set(column_names)
    url_expr = _normalised_column_expr(dialect_name, "url") if "url" in normalised_columns else None
    contents_expr = _normalised_column_expr(dialect_name, "contents") if "contents" in normalised_columns else None
    author_expr = _normalised_column_expr(dialect_name, "author") if "author" in normalised_columns else None
    platform_expr = (
        _normalised_column_expr(dialect_name, "platform")
        if "platform" in normalised_columns
        else _sql_literal("")
    )
    published_expr = (
        _normalised_datetime_expr(dialect_name, "published_at")
        if "published_at" in normalised_columns
        else _sql_literal("")
    )

    branches: List[str] = []
    strategies: List[str] = []

    if url_expr is not None:
        url_condition = _is_meaningful_normalised_expr(url_expr, sorted(_NORMALISED_UNKNOWN_URLS))
        url_key = _concat_text_expressions(dialect_name, [_sql_literal("url:"), url_expr])
        branches.append(f"WHEN {url_condition} THEN {url_key}")
        strategies.append("链接")

    if contents_expr is not None and author_expr is not None and "published_at" in normalised_columns:
        contents_condition = _is_meaningful_normalised_expr(contents_expr, [])
        author_condition = _is_meaningful_normalised_expr(author_expr, sorted(_NORMALISED_UNKNOWN_AUTHORS))
        published_condition = f"({published_expr}) <> ''"
        composite_condition = f"{contents_condition} AND {author_condition} AND {published_condition}"
        composite_key = _concat_text_expressions(
            dialect_name,
            [
                _sql_literal("meta:"),
                contents_expr,
                _sql_literal("|"),
                author_expr,
                _sql_literal("|"),
                published_expr,
                _sql_literal("|"),
                platform_expr,
            ],
        )
        branches.append(f"WHEN {composite_condition} THEN {composite_key}")
        strategies.append("正文+作者+发布时间+平台")

    if not branches:
        return None, ""

    return "CASE " + " ".join(branches) + " ELSE NULL END", " 或 ".join(strategies)


def _escape_like_term(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_match_condition(
    dialect_name: str,
    columns: Sequence[str],
    terms: Sequence[str],
) -> tuple[str, Dict[str, Any]]:
    combined_expr = _combined_text_expr(dialect_name, columns)
    escape_clause = _like_escape_clause(dialect_name)
    params: Dict[str, Any] = {}
    clauses: List[str] = []
    for idx, term in enumerate(terms):
        param_name = f"term_{idx}"
        params[param_name] = f"%{_escape_like_term(term)}%"
        clauses.append(f"{combined_expr} LIKE :{param_name}{escape_clause}")
    return " OR ".join(clauses) if clauses else "1=0", params


def _build_author_match_condition(
    dialect_name: str,
    column_name: str,
    authors: Sequence[str],
) -> tuple[str, Dict[str, Any]]:
    expr = _normalised_column_expr(dialect_name, column_name)
    params: Dict[str, Any] = {}
    clauses: List[str] = []
    for idx, author in enumerate(authors):
        param_name = f"author_{idx}"
        params[param_name] = _normalise_match_text(author)
        clauses.append(f"{expr} = :{param_name}")
    return " OR ".join(clauses) if clauses else "1=0", params


def _coerce_tables(
    available_tables: Sequence[str],
    requested_tables: Optional[Sequence[str]],
) -> tuple[List[str], List[str]]:
    requested = [
        str(item or "").strip()
        for item in (requested_tables or [])
        if str(item or "").strip()
    ]
    if requested:
        matched = [table_name for table_name in available_tables if table_name in requested]
        missing = sorted(set(requested) - set(matched))
        return matched, missing
    return list(available_tables), []


def _clean_author_display(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalise_author_key(value: Any) -> str:
    return _normalise_match_text(_clean_author_display(value))


def _is_unknown_author(value: Any) -> bool:
    display = _clean_author_display(value)
    normalised = _normalise_author_key(display)
    return not normalised or normalised in _NORMALISED_UNKNOWN_AUTHORS


def _serialise_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return value


def _preview_excerpt(*values: Any) -> str:
    for raw in values:
        text_value = str(raw or "").strip()
        if text_value:
            return text_value[:120].rstrip() + ("…" if len(text_value) > 120 else "")
    return ""


def _build_desc_order_expr(dialect_name: str, column_names: Sequence[str]) -> str:
    order_parts: List[str] = []
    if "published_at" in column_names:
        quoted_published_at = _quote_identifier(dialect_name, "published_at")
        order_parts.append(f"CASE WHEN {quoted_published_at} IS NULL THEN 1 ELSE 0 END")
        order_parts.append(f"{quoted_published_at} DESC")
    if "id" in column_names:
        order_parts.append(f"{_quote_identifier(dialect_name, 'id')} DESC")
    return ", ".join(order_parts) if order_parts else "1"


def _build_asc_order_expr(dialect_name: str, column_names: Sequence[str]) -> str:
    order_parts: List[str] = []
    if "published_at" in column_names:
        quoted_published_at = _quote_identifier(dialect_name, "published_at")
        order_parts.append(f"CASE WHEN {quoted_published_at} IS NULL THEN 1 ELSE 0 END")
        order_parts.append(f"{quoted_published_at} ASC")
    if "id" in column_names:
        order_parts.append(f"{_quote_identifier(dialect_name, 'id')} ASC")
    return ", ".join(order_parts) if order_parts else "1"


def _delete_ids(conn, dialect_name: str, table_name: str, ids: Sequence[Any]) -> int:
    if not ids:
        return 0
    quoted_table = _quote_identifier(dialect_name, table_name)
    delete_stmt = text(
        f"DELETE FROM {quoted_table} WHERE {_quote_identifier(dialect_name, 'id')} IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    deleted = 0
    batch_size = 1000
    for index in range(0, len(ids), batch_size):
        batch = list(ids[index:index + batch_size])
        if not batch:
            continue
        result = conn.execute(delete_stmt, {"ids": batch})
        deleted += int(result.rowcount or len(batch))
    return deleted


def list_postclean_publishers(
    topic: str,
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
    limit: int = 50,
    sample_limit: int = _POSTCLEAN_SAMPLE_LIMIT,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    target_database = str(database or "").strip()
    if not target_database:
        return {"status": "error", "message": "Missing required field(s): database"}

    engine = None
    missing_tables: List[str] = []
    scanned_tables: List[str] = []
    skipped_tables: List[Dict[str, Any]] = []
    ranked: List[Dict[str, Any]] = []
    def _emit(
        *,
        phase: str,
        message: str,
        total_tables: int = 0,
        completed_tables: int = 0,
        current_table: str = "",
    ) -> None:
        if progress_callback is None:
            return
        total = max(int(total_tables or 0), 0)
        completed = max(0, min(int(completed_tables or 0), total)) if total > 0 else 0
        if total > 0:
            percentage = max(0, min(100, int(round((completed / total) * 90))))
        else:
            percentage = 0
        progress_callback(
            {
                "phase": phase,
                "message": message,
                "total_tables": total,
                "completed_tables": completed,
                "current_table": str(current_table or "").strip(),
                "percentage": percentage,
                "scanned_tables": list(scanned_tables),
                "skipped_tables": [dict(item) for item in skipped_tables],
                "missing_tables": list(missing_tables),
            }
        )

    try:
        engine = db_manager.get_engine_for_database(target_database)
        with engine.begin() as conn:
            dialect_name = conn.dialect.name
            inspector = inspect(conn)
            available_tables = sorted(inspector.get_table_names())
            if not available_tables:
                return {
                    "status": "error",
                    "message": f"数据库 {target_database} 中没有可处理的数据表",
                }

            table_names, missing_tables = _coerce_tables(available_tables, tables)
            if not table_names:
                return {
                    "status": "error",
                    "message": "指定的数据表不存在",
                    "missing_tables": missing_tables,
                }

            blacklisted = set(load_shared_publisher_blacklist(topic).get("authors") or [])
            aggregate: Dict[str, Dict[str, Any]] = {}
            table_columns: Dict[str, set[str]] = {}
            total_tables = len(table_names)

            _emit(
                phase="prepare",
                message=f"已锁定 {total_tables} 张表，开始统计发布者分布。",
                total_tables=total_tables,
                completed_tables=0,
            )

            for index, table_name in enumerate(table_names, start=1):
                _emit(
                    phase="analyze",
                    message=f"正在统计 {table_name} 的发布者分布。",
                    total_tables=total_tables,
                    completed_tables=index - 1,
                    current_table=table_name,
                )
                columns = {
                    str(column.get("name") or "").strip()
                    for column in inspector.get_columns(table_name)
                }
                table_columns[table_name] = columns
                if "author" not in columns:
                    skipped_tables.append({"table": table_name, "reason": "缺少 author 列"})
                    _emit(
                        phase="analyze",
                        message=f"{table_name} 缺少 author 列，已跳过。",
                        total_tables=total_tables,
                        completed_tables=index,
                        current_table=table_name,
                    )
                    continue
                scanned_tables.append(table_name)
                quoted_table = _quote_identifier(dialect_name, table_name)
                count_sql = text(
                    f"SELECT author, COUNT(*) AS row_count "
                    f"FROM {quoted_table} "
                    "WHERE author IS NOT NULL AND TRIM(COALESCE(author, '')) <> '' "
                    "GROUP BY author"
                )
                for row in conn.execute(count_sql).mappings():
                    display = _clean_author_display(row.get("author"))
                    normalised = _normalise_author_key(display)
                    if _is_unknown_author(display):
                        continue
                    entry = aggregate.get(normalised)
                    if entry is None:
                        entry = {
                            "author": display,
                            "normalised": normalised,
                            "count": 0,
                            "samples": [],
                        }
                        aggregate[normalised] = entry
                    entry["count"] += int(row.get("row_count") or 0)
                _emit(
                    phase="analyze",
                    message=f"{table_name} 统计完成。",
                    total_tables=total_tables,
                    completed_tables=index,
                    current_table=table_name,
                )

            ranked = sorted(
                aggregate.values(),
                key=lambda item: (-int(item.get("count") or 0), str(item.get("author") or "")),
            )[: max(1, int(limit or 50))]

            _emit(
                phase="sample",
                message=f"已完成表扫描，正在整理 Top{max(1, int(limit or 50))} 发布者样本。",
                total_tables=total_tables,
                completed_tables=total_tables,
                current_table="",
            )

            for item in ranked:
                normalised = str(item.get("normalised") or "")
                samples: List[Dict[str, Any]] = []
                for table_name in scanned_tables:
                    if len(samples) >= sample_limit:
                        break
                    columns = table_columns.get(table_name) or set()
                    selected_columns = [
                        column_name
                        for column_name in ("title", "contents", "hit_words", "published_at", "url", "id")
                        if column_name in columns
                    ]
                    if not selected_columns:
                        continue
                    quoted_table = _quote_identifier(dialect_name, table_name)
                    author_expr = _normalised_column_expr(dialect_name, "author")
                    order_expr = _build_desc_order_expr(dialect_name, columns)
                    sample_sql = text(
                        f"SELECT {', '.join(_quote_identifier(dialect_name, column) for column in selected_columns)} "
                        f"FROM {quoted_table} "
                        f"WHERE {author_expr} = :author_norm "
                        f"ORDER BY {order_expr} "
                        "LIMIT :sample_limit"
                    )
                    remaining = max(sample_limit - len(samples), 1)
                    for row in conn.execute(
                        sample_sql,
                        {"author_norm": normalised, "sample_limit": remaining},
                    ).mappings():
                        title = str(row.get("title") or "").strip()
                        samples.append(
                            {
                                "table": table_name,
                                "title": title[:100].rstrip() + ("…" if len(title) > 100 else "") if title else "",
                                "preview": _preview_excerpt(
                                    row.get("contents"),
                                    row.get("title"),
                                    row.get("hit_words"),
                                ),
                                "published_at": _serialise_scalar(row.get("published_at")),
                                "url": str(row.get("url") or "").strip(),
                            }
                        )
                        if len(samples) >= sample_limit:
                            break
                item["samples"] = samples
                item["blacklisted"] = normalised in blacklisted
                item.pop("normalised", None)

    except Exception as exc:
        return {"status": "error", "message": f"异常发布者识别失败: {exc}"}
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass

    return {
        "status": "ok",
        "topic": topic,
        "database": target_database,
        "publishers": ranked,
        "scanned_tables": scanned_tables,
        "skipped_tables": skipped_tables,
        "missing_tables": missing_tables,
        "generated_at": _utc_now(),
    }


def run_database_postclean(
    topic: str,
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
    logger=None,
    progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    target_database = str(database or "").strip()
    if not target_database:
        return {"status": "error", "message": "Missing required field(s): database"}

    if logger is None:
        logger = setup_logger(topic, "postclean")
    log_module_start(logger, "DatabasePostclean")

    def _emit(event: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if progress_callback:
            try:
                progress_callback(event, message, payload or {})
            except Exception:
                pass

    terms_payload = load_shared_noise_terms(topic)
    terms = list(terms_payload.get("terms") or [])
    publisher_payload = load_shared_publisher_blacklist(topic)
    blacklisted_authors = list(publisher_payload.get("authors") or [])

    engine = None
    try:
        engine = db_manager.get_engine_for_database(target_database)
        with engine.begin() as conn:
            dialect_name = conn.dialect.name
            inspector = inspect(conn)
            available_tables = sorted(inspector.get_table_names())
            if not available_tables:
                return {
                    "status": "error",
                    "message": f"数据库 {target_database} 中没有可处理的数据表",
                }

            table_names, missing_tables = _coerce_tables(available_tables, tables)
            if not table_names:
                return {
                    "status": "error",
                    "message": "指定的数据表不存在",
                    "missing_tables": missing_tables,
                }

            report_tables: List[Dict[str, Any]] = []
            total_deleted_rows = 0
            total_tables = len(table_names)
            completed_tables = 0
            aggregate_breakdown = {
                "keyword_only": 0,
                "author_only": 0,
                "both": 0,
            }

            _emit(
                "phase.started",
                f"后清洗 worker 已启动，准备扫描 {total_tables} 张表。",
                {
                    "total_tables": total_tables,
                    "completed_tables": completed_tables,
                    "deleted_rows": total_deleted_rows,
                },
            )

            for table_name in table_names:
                _emit(
                    "table.started",
                    f"开始检查数据表 {table_name}。",
                    {
                        "table": table_name,
                        "total_tables": total_tables,
                        "completed_tables": completed_tables,
                        "deleted_rows": total_deleted_rows,
                    },
                )
                column_names = {
                    str(column.get("name") or "").strip()
                    for column in inspector.get_columns(table_name)
                }
                if "id" not in column_names:
                    report_tables.append(
                        {
                            "table": table_name,
                            "status": "skipped",
                            "reason": "缺少 id 列",
                            "deleted_rows": 0,
                        }
                    )
                    completed_tables += 1
                    _emit(
                        "table.skipped",
                        f"{table_name} 跳过：缺少 id 列。",
                        {
                            "table": table_name,
                            "total_tables": total_tables,
                            "completed_tables": completed_tables,
                            "deleted_rows": total_deleted_rows,
                            "percentage": round(completed_tables / max(1, total_tables) * 100),
                        },
                    )
                    continue

                matched_columns = [
                    column_name
                    for column_name in ("title", "contents", "hit_words")
                    if column_name in column_names
                ]
                has_keyword_match = bool(terms and matched_columns)
                has_author_match = bool(blacklisted_authors and "author" in column_names)

                if not has_keyword_match and not has_author_match:
                    report_tables.append(
                        {
                            "table": table_name,
                            "status": "ok",
                            "reason": "当前未配置排除词/发布者黑名单或目标表缺少匹配列",
                            "deleted_rows": 0,
                            "matched_columns": matched_columns,
                        }
                    )
                    completed_tables += 1
                    _emit(
                        "table.completed",
                        f"{table_name} 检查完成，未命中可执行的清洗规则。",
                        {
                            "table": table_name,
                            "total_tables": total_tables,
                            "completed_tables": completed_tables,
                            "deleted_rows": total_deleted_rows,
                            "percentage": round(completed_tables / max(1, total_tables) * 100),
                        },
                    )
                    continue

                keyword_condition = ""
                keyword_params: Dict[str, Any] = {}
                if has_keyword_match:
                    keyword_condition, keyword_params = _build_match_condition(dialect_name, matched_columns, terms)

                author_condition = ""
                author_params: Dict[str, Any] = {}
                if has_author_match:
                    author_condition, author_params = _build_author_match_condition(
                        dialect_name,
                        "author",
                        blacklisted_authors,
                    )

                where_clauses = [clause for clause in (keyword_condition, author_condition) if clause]
                combined_condition = " OR ".join(f"({clause})" for clause in where_clauses if clause) or "1=0"
                keyword_flag = f"CASE WHEN ({keyword_condition}) THEN 1 ELSE 0 END" if keyword_condition else "0"
                author_flag = f"CASE WHEN ({author_condition}) THEN 1 ELSE 0 END" if author_condition else "0"
                quoted_table = _quote_identifier(dialect_name, table_name)
                select_sql = text(
                    f"SELECT {_quote_identifier(dialect_name, 'id')} AS id, "
                    f"{keyword_flag} AS keyword_hit, "
                    f"{author_flag} AS author_hit "
                    f"FROM {quoted_table} "
                    f"WHERE {combined_condition}"
                )
                matched_rows = list(conn.execute(select_sql, {**keyword_params, **author_params}).mappings())
                ids_to_delete = [row.get("id") for row in matched_rows if row.get("id") is not None]
                keyword_only = 0
                author_only = 0
                both = 0
                for row in matched_rows:
                    keyword_hit = bool(int(row.get("keyword_hit") or 0))
                    author_hit = bool(int(row.get("author_hit") or 0))
                    if keyword_hit and author_hit:
                        both += 1
                    elif keyword_hit:
                        keyword_only += 1
                    elif author_hit:
                        author_only += 1
                deleted_rows = _delete_ids(conn, dialect_name, table_name, ids_to_delete)
                total_deleted_rows += deleted_rows
                aggregate_breakdown["keyword_only"] += keyword_only
                aggregate_breakdown["author_only"] += author_only
                aggregate_breakdown["both"] += both
                report_tables.append(
                    {
                        "table": table_name,
                        "status": "ok",
                        "matched_columns": matched_columns,
                        "matched_rows": len(matched_rows),
                        "deleted_rows": deleted_rows,
                        "reason_breakdown": {
                            "keyword_only": keyword_only,
                            "author_only": author_only,
                            "both": both,
                        },
                    }
                )
                completed_tables += 1
                log_success(
                    logger,
                    f"{target_database}.{table_name} 后清洗完成 | 命中:{len(matched_rows)}, 删除:{deleted_rows}",
                    "DatabasePostclean",
                )
                _emit(
                    "table.completed",
                    f"{table_name} 检查完成，命中 {len(matched_rows)} 条，删除 {deleted_rows} 条。",
                    {
                        "table": table_name,
                        "matched_rows": len(matched_rows),
                        "deleted_rows": total_deleted_rows,
                        "table_deleted_rows": deleted_rows,
                        "total_tables": total_tables,
                        "completed_tables": completed_tables,
                        "percentage": round(completed_tables / max(1, total_tables) * 100),
                    },
                )

    except Exception as exc:
        detail = f"数据库后清洗失败: {exc}"
        log_error(logger, detail, "DatabasePostclean")
        _emit("task.failed", detail, {})
        return {"status": "error", "message": detail}
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass

    report_dir = ensure_bucket("results", topic, POSTCLEAN_REPORT_DIR)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"{_safe_name(target_database, 'database')}_{timestamp}.json"
    report_payload = {
        "topic": topic,
        "database": target_database,
        "generated_at": _utc_now(),
        "source": "database-postclean",
        "terms_count": len(terms),
        "terms_path": terms_payload.get("path") or "",
        "publisher_blacklist_count": len(blacklisted_authors),
        "publisher_blacklist_path": publisher_payload.get("path") or "",
        "deleted_rows": total_deleted_rows,
        "missing_tables": missing_tables,
        "reason_breakdown": aggregate_breakdown,
        "tables": report_tables,
    }
    _write_json(report_path, report_payload)

    _emit(
        "task.completed",
        f"后清洗完成，共删除 {total_deleted_rows} 条记录。",
        {
            "deleted_rows": total_deleted_rows,
            "total_tables": len(report_tables),
            "completed_tables": len(report_tables),
            "percentage": 100,
            "report_path": get_relative_path(report_path),
        },
    )

    return {
        "status": "ok",
        "topic": topic,
        "database": target_database,
        "terms_count": len(terms),
        "publisher_blacklist_count": len(blacklisted_authors),
        "deleted_rows": total_deleted_rows,
        "missing_tables": missing_tables,
        "reason_breakdown": aggregate_breakdown,
        "tables": report_tables,
        "report_path": get_relative_path(report_path),
    }


def run_database_deduplicate(
    topic: str,
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
    logger=None,
    progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    target_database = str(database or "").strip()
    if not target_database:
        return {"status": "error", "message": "Missing required field(s): database"}

    if logger is None:
        logger = setup_logger(topic, "deduplicate")
    log_module_start(logger, "DatabaseDeduplicate")

    def _emit(event: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if progress_callback:
            try:
                progress_callback(event, message, payload or {})
            except Exception:
                pass

    engine = None
    try:
        engine = db_manager.get_engine_for_database(target_database)
        with engine.begin() as conn:
            dialect_name = conn.dialect.name
            inspector = inspect(conn)
            available_tables = sorted(inspector.get_table_names())
            if not available_tables:
                return {
                    "status": "error",
                    "message": f"数据库 {target_database} 中没有可处理的数据表",
                }

            table_names, missing_tables = _coerce_tables(available_tables, tables)
            if not table_names:
                return {
                    "status": "error",
                    "message": "指定的数据表不存在",
                    "missing_tables": missing_tables,
                }

            report_tables: List[Dict[str, Any]] = []
            total_deleted_rows = 0
            total_tables = len(table_names)
            completed_tables = 0
            snapshot_manifest = _create_database_snapshot(
                conn,
                topic=topic,
                database=target_database,
                dialect_name=dialect_name,
                table_names=table_names,
                inspector=inspector,
            )

            _emit(
                "phase.started",
                f"数据库快照已创建，准备扫描 {total_tables} 张表。",
                {
                    "total_tables": total_tables,
                    "completed_tables": completed_tables,
                    "deleted_rows": total_deleted_rows,
                },
            )

            for table_name in table_names:
                _emit(
                    "table.started",
                    f"开始检查数据表 {table_name}。",
                    {
                        "table": table_name,
                        "total_tables": total_tables,
                        "completed_tables": completed_tables,
                        "deleted_rows": total_deleted_rows,
                    },
                )
                column_names = {
                    str(column.get("name") or "").strip()
                    for column in inspector.get_columns(table_name)
                }
                required_columns = [column_name for column_name in ("contents", "url") if column_name in column_names]
                if not required_columns:
                    missing_cols = [
                        column_name
                        for column_name in ("contents", "url")
                        if column_name not in column_names
                    ]
                    report_tables.append(
                        {
                            "table": table_name,
                            "status": "skipped",
                            "reason": f"缺少 {' / '.join(missing_cols)} 列",
                            "deleted_rows": 0,
                        }
                    )
                    completed_tables += 1
                    _emit(
                        "table.skipped",
                        f"{table_name} 跳过：缺少 {' / '.join(missing_cols)} 列。",
                        {
                            "table": table_name,
                            "total_tables": total_tables,
                            "completed_tables": completed_tables,
                            "deleted_rows": total_deleted_rows,
                            "percentage": round(completed_tables / max(1, total_tables) * 100),
                        },
                    )
                    continue

                quoted_table = _quote_identifier(dialect_name, table_name)
                ordered_columns = [str(column.get("name") or "").strip() for column in inspector.get_columns(table_name)]
                quoted_columns = [_quote_identifier(dialect_name, column_name) for column_name in ordered_columns]
                selected_columns_sql = ", ".join(quoted_columns)
                dedupe_key_expr, strategy_label = _build_deduplicate_key_expr(dialect_name, ordered_columns)
                if not dedupe_key_expr:
                    report_tables.append(
                        {
                            "table": table_name,
                            "status": "skipped",
                            "reason": "缺少稳定判重字段，已跳过以避免误删",
                            "deleted_rows": 0,
                        }
                    )
                    completed_tables += 1
                    _emit(
                        "table.skipped",
                        f"{table_name} 跳过：缺少稳定判重字段，未执行删除。",
                        {
                            "table": table_name,
                            "total_tables": total_tables,
                            "completed_tables": completed_tables,
                            "deleted_rows": total_deleted_rows,
                            "percentage": round(completed_tables / max(1, total_tables) * 100),
                        },
                    )
                    continue

                order_expr = _build_asc_order_expr(dialect_name, column_names)
                ranked_cte_sql = (
                    f"WITH ranked AS ("
                    f"SELECT base.*, "
                    f"CASE WHEN base.dedupe_key IS NULL THEN 1 "
                    f"ELSE ROW_NUMBER() OVER (PARTITION BY base.dedupe_key ORDER BY {order_expr}) END AS rn "
                    f"FROM ("
                    f"SELECT {selected_columns_sql}, {dedupe_key_expr} AS dedupe_key "
                    f"FROM {quoted_table}"
                    f") AS base"
                    f") "
                )
                table_stats_sql = text(
                    ranked_cte_sql +
                    "SELECT "
                    "COUNT(*) AS total_rows, "
                    "SUM(CASE WHEN dedupe_key IS NOT NULL THEN 1 ELSE 0 END) AS keyed_rows, "
                    "SUM(CASE WHEN dedupe_key IS NULL THEN 1 ELSE 0 END) AS unsafe_rows, "
                    "SUM(CASE WHEN dedupe_key IS NOT NULL AND rn > 1 THEN 1 ELSE 0 END) AS duplicate_rows, "
                    "SUM(CASE WHEN dedupe_key IS NULL OR rn = 1 THEN 1 ELSE 0 END) AS kept_rows "
                    "FROM ranked"
                )
                table_stats = conn.execute(table_stats_sql).mappings().first() or {}
                total_rows = int(table_stats.get("total_rows") or 0)
                keyed_rows = int(table_stats.get("keyed_rows") or 0)
                unsafe_rows = int(table_stats.get("unsafe_rows") or 0)
                duplicate_rows = int(table_stats.get("duplicate_rows") or 0)
                kept_rows = int(table_stats.get("kept_rows") or 0)

                if total_rows > 0 and kept_rows <= 0:
                    raise RuntimeError(f"{table_name} 判重结果异常：未保留任何记录，已中止")

                deleted_rows = 0
                if duplicate_rows > 0:
                    temp_table_name = _deduplicate_temp_table_name(table_name)
                    quoted_temp_table = _quote_identifier(dialect_name, temp_table_name)
                    conn.execute(text(f"DROP TABLE IF EXISTS {quoted_temp_table}"))
                    create_temp_sql = text(
                        f"CREATE TEMPORARY TABLE {quoted_temp_table} AS " +
                        ranked_cte_sql +
                        f"SELECT {selected_columns_sql} FROM ranked WHERE dedupe_key IS NULL OR rn = 1"
                    )
                    conn.execute(create_temp_sql)
                    survivor_count = int(
                        (conn.execute(text(f"SELECT COUNT(*) AS row_count FROM {quoted_temp_table}")).mappings().first() or {}).get("row_count") or 0
                    )
                    if total_rows > 0 and survivor_count <= 0:
                        raise RuntimeError(f"{table_name} 临时保留集为空，已中止")
                    if survivor_count > total_rows:
                        raise RuntimeError(f"{table_name} 临时保留集异常放大，已中止")

                    conn.execute(text(f"DELETE FROM {quoted_table}"))
                    conn.execute(
                        text(
                            f"INSERT INTO {quoted_table} ({selected_columns_sql}) "
                            f"SELECT {selected_columns_sql} FROM {quoted_temp_table}"
                        )
                    )
                    conn.execute(text(f"DROP TABLE IF EXISTS {quoted_temp_table}"))
                    deleted_rows = total_rows - survivor_count

                total_deleted_rows += deleted_rows
                report_tables.append(
                    {
                        "table": table_name,
                        "status": "ok",
                        "strategy": strategy_label,
                        "total_rows": total_rows,
                        "keyed_rows": keyed_rows,
                        "unsafe_rows_kept": unsafe_rows,
                        "duplicate_rows": duplicate_rows,
                        "kept_rows": kept_rows,
                        "deleted_rows": deleted_rows,
                    }
                )
                completed_tables += 1
                log_success(
                    logger,
                    f"{target_database}.{table_name} 数据库去重完成 | 删除:{deleted_rows}",
                    "DatabaseDeduplicate",
                )
                _emit(
                    "table.completed",
                    f"{table_name} 去重完成，删除 {deleted_rows} 条明确重复记录，保留 {total_rows - deleted_rows} 条。",
                    {
                        "table": table_name,
                        "deleted_rows": total_deleted_rows,
                        "table_deleted_rows": deleted_rows,
                        "total_tables": total_tables,
                        "completed_tables": completed_tables,
                        "percentage": round(completed_tables / max(1, total_tables) * 100),
                    },
                )

    except Exception as exc:
        detail = f"数据库去重失败: {exc}"
        log_error(logger, detail, "DatabaseDeduplicate")
        _emit("task.failed", detail, {})
        return {"status": "error", "message": detail}
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass

    report_dir = ensure_bucket("results", topic, DEDUP_REPORT_DIR)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"{_safe_name(target_database, 'database')}_{timestamp}.json"
    report_payload = {
        "topic": topic,
        "database": target_database,
        "generated_at": _utc_now(),
        "source": "database-deduplicate",
        "snapshot": snapshot_manifest,
        "deleted_rows": total_deleted_rows,
        "missing_tables": missing_tables,
        "tables": report_tables,
    }
    _write_json(report_path, report_payload)

    _emit(
        "task.completed",
        f"数据库去重完成，共删除 {total_deleted_rows} 条重复记录。",
        {
            "deleted_rows": total_deleted_rows,
            "total_tables": len(report_tables),
            "completed_tables": len(report_tables),
            "percentage": 100,
            "report_path": get_relative_path(report_path),
        },
    )

    return {
        "status": "ok",
        "topic": topic,
        "database": target_database,
        "snapshot": snapshot_manifest,
        "deleted_rows": total_deleted_rows,
        "missing_tables": missing_tables,
        "tables": report_tables,
        "report_path": get_relative_path(report_path),
    }


__all__ = [
    "list_database_deduplicate_snapshots",
    "list_postclean_publishers",
    "load_shared_publisher_blacklist",
    "restore_database_snapshot",
    "run_database_deduplicate",
    "run_database_postclean",
]
