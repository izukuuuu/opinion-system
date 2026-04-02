"""Deterministic keyword-based noise cleaning for preclean/postclean flows."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from sqlalchemy import inspect, text

from ..topic.prompt_config import load_topic_bertopic_prompt_config
from ..utils.io.db import db_manager
from ..utils.io.excel import read_jsonl, write_jsonl
from ..utils.logging.logging import (
    log_error,
    log_module_start,
    log_skip,
    log_success,
    setup_logger,
)
from ..utils.setting.paths import ensure_bucket, get_relative_path, bucket

PRECLEAN_SUMMARY_FILENAME = "_summary.json"
PRECLEAN_REPORT_FILENAME = "_preclean_report.json"
POSTCLEAN_REPORT_DIR = "postclean"
_PROGRESS_CACHE_DIR = Path(__file__).resolve().parent / "cache"
_WHITESPACE_RE = re.compile(r"\s+")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_RECENT_LIMIT = 40
_SAMPLE_LIMIT = 20


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str, fallback: str) -> str:
    text_value = _SAFE_NAME_RE.sub("-", str(value or "").strip()).strip("-")
    return text_value or fallback


def _normalise_match_text(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub("", str(value)).strip().lower()


def _normalise_terms(raw_terms: Any) -> List[str]:
    if isinstance(raw_terms, list):
        source_values = raw_terms
    else:
        source_values = [raw_terms]

    result: List[str] = []
    seen = set()
    for raw in source_values:
        value = _normalise_match_text(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def load_shared_noise_terms(topic: str) -> Dict[str, Any]:
    """Load shared blacklist terms from the BERTopic topic prompt config."""

    payload = load_topic_bertopic_prompt_config(topic)
    terms = _normalise_terms(payload.get("project_stopwords", []))
    return {
        "terms": terms,
        "path": str(payload.get("path") or ""),
        "topic": str(payload.get("topic") or topic).strip() or topic,
    }


def _build_match_source(row: pd.Series) -> str:
    parts = [
        row.get("title", ""),
        row.get("contents", ""),
        row.get("hit_words", ""),
    ]
    return _normalise_match_text(" ".join(str(part or "") for part in parts))


def _match_terms(source_text: str, terms: Sequence[str]) -> List[str]:
    matched: List[str] = []
    for term in terms:
        if term and term in source_text:
            matched.append(term)
    return matched


def _preview_text(row: pd.Series) -> str:
    for key in ("contents", "title", "hit_words"):
        value = str(row.get(key) or "").strip()
        if value:
            return value[:120].rstrip() + ("…" if len(value) > 120 else "")
    return ""


def _remove_existing_filter_outputs(filter_dir: Path) -> None:
    if not filter_dir.exists():
        return
    for pattern in ("*.jsonl", PRECLEAN_SUMMARY_FILENAME, PRECLEAN_REPORT_FILENAME):
        for path in filter_dir.glob(pattern):
            try:
                path.unlink()
            except OSError:
                continue


def _clear_progress_cache(topic: str, date: str) -> None:
    prefix = f"{topic}_{date}_"
    if not _PROGRESS_CACHE_DIR.exists():
        return
    for path in _PROGRESS_CACHE_DIR.glob(f"{prefix}*_progress.json"):
        try:
            path.unlink()
        except OSError:
            continue


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def run_keyword_preclean(topic: str, date: str, logger=None) -> Dict[str, Any]:
    """Execute deterministic clean->filter keyword filtering."""

    if logger is None:
        logger = setup_logger(topic, date)

    log_module_start(logger, "FilterPreclean")

    terms_payload = load_shared_noise_terms(topic)
    terms = list(terms_payload.get("terms") or [])
    clean_dir = bucket("clean", topic, date)
    files = sorted(clean_dir.glob("*.jsonl")) if clean_dir.exists() else []
    if not files:
        message = f"未找到可用的 Clean 产物: {clean_dir}"
        log_error(logger, message, "FilterPreclean")
        return {"status": "error", "message": message}

    filter_dir = ensure_bucket("filter", topic, date)
    _remove_existing_filter_outputs(filter_dir)
    _clear_progress_cache(topic, date)

    total_rows = 0
    kept_rows = 0
    discarded_rows = 0
    channel_reports: List[Dict[str, Any]] = []
    failed_channels: List[str] = []
    recent_records: List[Dict[str, Any]] = []
    relevant_samples: List[Dict[str, Any]] = []
    irrelevant_samples: List[Dict[str, Any]] = []
    term_hits: Counter[str] = Counter()

    for file_path in files:
        channel = file_path.stem
        if channel == "all":
            continue
        try:
            df = read_jsonl(file_path)
        except Exception as exc:
            detail = f"读取 {file_path.name} 失败: {exc}"
            log_error(logger, detail, "FilterPreclean")
            failed_channels.append(channel)
            channel_reports.append(
                {"channel": channel, "status": "error", "message": detail, "total_rows": 0}
            )
            continue

        if df.empty:
            log_skip(logger, f"{channel} 无数据，跳过", "FilterPreclean")
            channel_reports.append(
                {
                    "channel": channel,
                    "status": "skipped",
                    "message": "空文件",
                    "total_rows": 0,
                    "kept_rows": 0,
                    "discarded_rows": 0,
                }
            )
            continue

        match_results: List[List[str]] = []
        keep_mask: List[bool] = []
        for row_idx, (_, row) in enumerate(df.iterrows()):
            source_text = _build_match_source(row)
            matched_terms = _match_terms(source_text, terms)
            is_kept = len(matched_terms) == 0
            match_results.append(matched_terms)
            keep_mask.append(is_kept)

            title = str(row.get("title") or "").strip()
            preview = _preview_text(row)
            record = {
                "channel": channel,
                "index": row_idx,
                "status": "kept" if is_kept else "discarded",
                "title": title[:80].rstrip() + ("…" if len(title) > 80 else ""),
                "preview": preview,
                "classification": str(row.get("classification") or "").strip(),
                "matched_terms": matched_terms[:10],
                "updated_at": _utc_now(),
            }
            recent_records.append(record)
            if is_kept and len(relevant_samples) < _SAMPLE_LIMIT:
                relevant_samples.append(
                    {
                        "channel": channel,
                        "index": row_idx,
                        "title": record["title"],
                        "preview": preview,
                    }
                )
            if (not is_kept) and len(irrelevant_samples) < _SAMPLE_LIMIT:
                irrelevant_samples.append(
                    {
                        "channel": channel,
                        "index": row_idx,
                        "title": record["title"],
                        "preview": preview,
                    }
                )
                term_hits.update(matched_terms)

        kept_df = df.loc[keep_mask].copy()
        output_path = filter_dir / file_path.name
        write_jsonl(kept_df, output_path)

        channel_total = len(df)
        channel_kept = len(kept_df)
        channel_discarded = channel_total - channel_kept
        total_rows += channel_total
        kept_rows += channel_kept
        discarded_rows += channel_discarded
        channel_reports.append(
            {
                "channel": channel,
                "status": "ok",
                "source_file": file_path.name,
                "output_file": output_path.name,
                "total_rows": channel_total,
                "kept_rows": channel_kept,
                "discarded_rows": channel_discarded,
            }
        )
        log_success(
            logger,
            f"{channel} 预清洗完成 | 原始:{channel_total}, 保留:{channel_kept}, 丢弃:{channel_discarded}",
            "FilterPreclean",
        )

    recent_records.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    has_failed_channels = len(failed_channels) > 0
    summary_payload = {
        "topic": topic,
        "date": date,
        "total_rows": total_rows,
        "kept_rows": kept_rows,
        "discarded_rows": discarded_rows,
        "relevant_samples": relevant_samples[:_SAMPLE_LIMIT],
        "irrelevant_samples": irrelevant_samples[:_SAMPLE_LIMIT],
        "recent_records": recent_records[:_RECENT_LIMIT],
        "token_usage": 0,
        "completed": not has_failed_channels,
        "source": "keyword-preclean",
        "failed_channels": failed_channels,
        "updated_at": _utc_now(),
    }
    summary_path = filter_dir / PRECLEAN_SUMMARY_FILENAME
    _write_json(summary_path, summary_payload)

    report_payload = {
        "topic": topic,
        "date": date,
        "generated_at": _utc_now(),
        "source": "keyword-preclean",
        "terms_count": len(terms),
        "terms_path": terms_payload.get("path") or "",
        "term_hits": dict(term_hits.most_common()),
        "failed_channels": failed_channels,
        "channels": channel_reports,
        "total_rows": total_rows,
        "kept_rows": kept_rows,
        "discarded_rows": discarded_rows,
    }
    report_path = filter_dir / PRECLEAN_REPORT_FILENAME
    _write_json(report_path, report_payload)

    result = {
        "status": "ok",
        "topic": topic,
        "date": date,
        "source": "keyword-preclean",
        "terms_count": len(terms),
        "kept_rows": kept_rows,
        "discarded_rows": discarded_rows,
        "total_rows": total_rows,
        "report_path": get_relative_path(report_path),
        "output_dir": get_relative_path(filter_dir),
        "failed_channels": failed_channels,
        "channels": channel_reports,
    }
    if has_failed_channels:
        result["status"] = "error"
        result["message"] = f"预清洗未完整完成，失败渠道: {', '.join(failed_channels)}"
    return result


def _quote_identifier(dialect_name: str, name: str) -> str:
    if dialect_name == "mysql":
        return f"`{name.replace('`', '``')}`"
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def _normalised_column_expr(dialect_name: str, column_name: str) -> str:
    quoted = _quote_identifier(dialect_name, column_name)
    return (
        f"LOWER(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE({quoted}, ''), ' ', ''), "
        f"CHAR(10), ''), CHAR(13), ''), CHAR(9), ''))"
        if dialect_name == "mysql"
        else f"LOWER(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE({quoted}, ''), ' ', ''), "
        f"CHR(10), ''), CHR(13), ''), CHR(9), ''))"
    )


def _combined_text_expr(dialect_name: str, columns: Sequence[str]) -> str:
    expressions = [_normalised_column_expr(dialect_name, column) for column in columns]
    if dialect_name == "mysql":
        return f"CONCAT({', '.join(expressions)})"
    return "(" + " || ".join(expressions) + ")"


def _escape_like_term(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_match_condition(dialect_name: str, columns: Sequence[str], terms: Sequence[str]) -> tuple[str, Dict[str, Any]]:
    combined_expr = _combined_text_expr(dialect_name, columns)
    params: Dict[str, Any] = {}
    clauses: List[str] = []
    for idx, term in enumerate(terms):
        param_name = f"term_{idx}"
        params[param_name] = f"%{_escape_like_term(term)}%"
        clauses.append(f"{combined_expr} LIKE :{param_name} ESCAPE '\\\\'")
    return " OR ".join(clauses) if clauses else "1=0", params


def run_database_postclean(
    topic: str,
    database: str,
    *,
    tables: Optional[Sequence[str]] = None,
    logger=None,
) -> Dict[str, Any]:
    """Hard-delete rows in a database whose business fields hit shared blacklist terms."""

    target_database = str(database or "").strip()
    if not target_database:
        return {"status": "error", "message": "Missing required field(s): database"}

    if logger is None:
        logger = setup_logger(topic, "postclean")
    log_module_start(logger, "DatabasePostclean")

    terms_payload = load_shared_noise_terms(topic)
    terms = list(terms_payload.get("terms") or [])

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

            requested_tables = [
                str(item or "").strip()
                for item in (tables or [])
                if str(item or "").strip()
            ]
            if requested_tables:
                table_names = [table_name for table_name in available_tables if table_name in requested_tables]
                missing_tables = sorted(set(requested_tables) - set(table_names))
                if not table_names:
                    return {
                        "status": "error",
                        "message": "指定的数据表不存在",
                        "missing_tables": missing_tables,
                    }
            else:
                table_names = available_tables
                missing_tables = []

            report_tables: List[Dict[str, Any]] = []
            total_deleted_rows = 0

            for table_name in table_names:
                column_names = {
                    str(column.get("name") or "").strip()
                    for column in inspector.get_columns(table_name)
                }
                matched_columns = [
                    column_name
                    for column_name in ("title", "contents", "hit_words")
                    if column_name in column_names
                ]
                if not matched_columns:
                    report_tables.append(
                        {
                            "table": table_name,
                            "status": "skipped",
                            "reason": "缺少 title / contents / hit_words 列",
                            "deleted_rows": 0,
                        }
                    )
                    continue

                if not terms:
                    report_tables.append(
                        {
                            "table": table_name,
                            "status": "ok",
                            "deleted_rows": 0,
                            "matched_columns": matched_columns,
                        }
                    )
                    continue

                quoted_table = _quote_identifier(dialect_name, table_name)
                where_clause, params = _build_match_condition(dialect_name, matched_columns, terms)
                count_sql = text(f"SELECT COUNT(*) AS matched_rows FROM {quoted_table} WHERE {where_clause}")
                matched_rows = int(conn.execute(count_sql, params).scalar() or 0)
                deleted_rows = 0
                if matched_rows > 0:
                    delete_sql = text(f"DELETE FROM {quoted_table} WHERE {where_clause}")
                    delete_result = conn.execute(delete_sql, params)
                    deleted_rows = int(delete_result.rowcount or matched_rows)
                    total_deleted_rows += deleted_rows

                report_tables.append(
                    {
                        "table": table_name,
                        "status": "ok",
                        "matched_columns": matched_columns,
                        "matched_rows": matched_rows,
                        "deleted_rows": deleted_rows,
                    }
                )
                log_success(
                    logger,
                    f"{target_database}.{table_name} 后清洗完成 | 命中:{matched_rows}, 删除:{deleted_rows}",
                    "DatabasePostclean",
                )

    except Exception as exc:
        detail = f"数据库后清洗失败: {exc}"
        log_error(logger, detail, "DatabasePostclean")
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
        "missing_tables": missing_tables,
        "deleted_rows": total_deleted_rows,
        "tables": report_tables,
    }
    _write_json(report_path, report_payload)

    return {
        "status": "ok",
        "topic": topic,
        "database": target_database,
        "terms_count": len(terms),
        "deleted_rows": total_deleted_rows,
        "tables": report_tables,
        "missing_tables": missing_tables,
        "report_path": get_relative_path(report_path),
    }


__all__ = [
    "load_shared_noise_terms",
    "run_database_postclean",
    "run_keyword_preclean",
]
