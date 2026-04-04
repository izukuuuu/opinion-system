"""Database-side cleanup helpers for postclean, publisher inspection, and dedup."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from sqlalchemy import bindparam, inspect, text

from ..topic.prompt_config import load_topic_bertopic_prompt_config
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
_POSTCLEAN_SAMPLE_LIMIT = 3


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

            _emit(
                "phase.started",
                f"数据库去重已启动，准备扫描 {total_tables} 张表。",
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
                if "id" not in column_names or "contents" not in column_names:
                    missing_cols = [
                        column_name
                        for column_name in ("id", "contents")
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
                contents_expr = _normalised_column_expr(dialect_name, "contents")
                order_expr = _build_asc_order_expr(dialect_name, column_names)
                select_duplicates_sql = text(
                    f"SELECT ranked.id FROM ("
                    f"SELECT {_quote_identifier(dialect_name, 'id')} AS id, "
                    f"ROW_NUMBER() OVER (PARTITION BY {contents_expr} ORDER BY {order_expr}) AS rn "
                    f"FROM {quoted_table} "
                    f"WHERE TRIM(COALESCE({_quote_identifier(dialect_name, 'contents')}, '')) <> ''"
                    f") AS ranked WHERE ranked.rn > 1"
                )
                duplicate_ids = [row.get("id") for row in conn.execute(select_duplicates_sql).mappings()]
                deleted_rows = _delete_ids(conn, dialect_name, table_name, duplicate_ids)
                total_deleted_rows += deleted_rows
                report_tables.append(
                    {
                        "table": table_name,
                        "status": "ok",
                        "duplicate_rows": len(duplicate_ids),
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
                    f"{table_name} 去重完成，删除 {deleted_rows} 条重复记录。",
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
        "deleted_rows": total_deleted_rows,
        "missing_tables": missing_tables,
        "tables": report_tables,
        "report_path": get_relative_path(report_path),
    }


__all__ = [
    "list_postclean_publishers",
    "load_shared_publisher_blacklist",
    "run_database_deduplicate",
    "run_database_postclean",
]
