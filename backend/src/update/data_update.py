"""
数据更新功能
"""
from __future__ import annotations

import json
import pandas as pd
import re
from typing import Any, Dict, List, Optional

from ..utils.setting.paths import bucket, ensure_bucket
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error, log_skip
from ..utils.io.excel import read_jsonl, write_jsonl, sanitize_dataframe, get_standard_table_schema
from ..utils.io.db import db_manager
from sqlalchemy import DateTime, MetaData, String, Table, Text, Column, inspect, inspect, text
from sqlalchemy.exc import IntegrityError as SAIntegrityError

try:  # Optional dependency; PyMySQL is used by default
    from pymysql.err import IntegrityError as PyMysqlIntegrityError
except Exception:  # pragma: no cover - fallback when driver missing
    PyMysqlIntegrityError = None


STANDARD_SCHEMA = get_standard_table_schema()
STANDARD_COLUMNS = list(STANDARD_SCHEMA.keys())
DIRECT_INGEST_CLASSIFICATION = "未筛选"


def _date_variants(date: str) -> List[str]:
    """
    生成日期目录的兼容候选：
    - 原始值
    - 8位 YYYYMMDD
    - 连字符 YYYY-MM-DD
    """
    raw = str(date or "").strip()
    variants: List[str] = []

    def _append(value: str) -> None:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in variants:
            variants.append(cleaned)

    _append(raw)
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 8:
        _append(digits)
        _append(f"{digits[:4]}-{digits[4:6]}-{digits[6:]}")
    return variants


def _resolve_layer_jsonl_files(layer: str, topic: str, date: str) -> tuple[str, Any, List[Any]]:
    """
    在同义日期目录里查找首个可用 JSONL 文件集合。
    """
    first_existing_date = ""
    first_existing_dir = None
    for candidate_date in _date_variants(date):
        layer_dir = bucket(layer, topic, candidate_date)
        if layer_dir.exists() and first_existing_dir is None:
            first_existing_dir = layer_dir
            first_existing_date = candidate_date
        files = sorted(layer_dir.glob("*.jsonl"))
        if files:
            return candidate_date, layer_dir, files

    if first_existing_dir is not None:
        return first_existing_date, first_existing_dir, []

    fallback_dir = bucket(layer, topic, str(date or "").strip())
    return str(date or "").strip(), fallback_dir, []


def _normalise_upload_dataframe(
    df: pd.DataFrame,
    *,
    classification_default: str = "未知",
) -> pd.DataFrame:
    """
    将任意输入数据规整到标准入库字段，避免因额外列导致写库失败。

    Args:
        df: 原始数据
        classification_default: 缺失分类时的默认值

    Returns:
        pd.DataFrame: 仅包含标准字段的数据
    """
    source_has_classification = "classification" in df.columns
    normalised = sanitize_dataframe(df.copy())

    defaults: Dict[str, Any] = {
        "id": "",
        "title": "未知",
        "contents": "未知",
        "platform": "未知",
        "author": "未知",
        "published_at": pd.NaT,
        "url": "未知",
        "region": "未知",
        "hit_words": "未知",
        "polarity": "未知",
        "classification": classification_default or "未知",
    }
    for col in STANDARD_COLUMNS:
        if col not in normalised.columns:
            normalised[col] = defaults[col]

    normalised["id"] = normalised["id"].fillna("").astype(str).str.strip()
    normalised = normalised[normalised["id"] != ""]
    if normalised.empty:
        return normalised[STANDARD_COLUMNS]

    normalised["published_at"] = pd.to_datetime(normalised["published_at"], errors="coerce")
    classification_fill = classification_default or "未知"
    if not source_has_classification:
        normalised["classification"] = classification_fill
    else:
        normalised["classification"] = (
            normalised["classification"].fillna(classification_fill).astype(str).str.strip()
        )
        normalised.loc[
            normalised["classification"].isin(["", "nan", "None", "null"]),
            "classification",
        ] = classification_fill

    return normalised[STANDARD_COLUMNS]


def _write_direct_ingest_summary(
    topic: str,
    date: str,
    filter_dir,
    *,
    total_rows: int,
) -> None:
    """
    写入直入模式生成的筛选汇总文件，兼容前端状态读取。
    """
    summary_path = filter_dir / "_summary.json"
    summary_payload = {
        "topic": topic,
        "date": date,
        "total_rows": total_rows,
        "kept_rows": total_rows,
        "discarded_rows": 0,
        "completed": True,
        "source": "clean-direct-ingest",
        "token_usage": 0,
        "relevant_samples": [],
        "irrelevant_samples": [],
    }
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary_payload, fh, ensure_ascii=False, indent=2)


def _prepare_intermediate_from_clean(topic: str, date: str, logger=None) -> Dict[str, Any]:
    """
    当 filter 层不存在产物时，从 clean 层生成可入库的中间 JSONL。
    """
    resolved_clean_date, clean_dir, clean_files = _resolve_layer_jsonl_files("clean", topic, date)
    filter_dir = ensure_bucket("filter", topic, date)
    result: Dict[str, Any] = {
        "status": "error",
        "topic": topic,
        "date": date,
        "resolved_clean_date": resolved_clean_date,
        "source_dir": str(clean_dir),
        "target_dir": str(filter_dir),
        "generated": [],
        "skipped": [],
        "failed": [],
        "rows": 0,
    }

    if not clean_files:
        result["message"] = (
            f"未找到可用的 Clean 产物，无法生成中间数据。"
            f"（已尝试日期: {', '.join(_date_variants(date)) or '空'}）"
        )
        return result

    total_rows = 0
    for file_path in clean_files:
        channel = file_path.stem
        try:
            source_df = read_jsonl(file_path)
            if source_df is None or len(source_df) == 0:
                result["skipped"].append(
                    {"channel": channel, "file": file_path.name, "reason": "清洗文件无数据"}
                )
                log_skip(logger, f"{file_path.name} 无数据，跳过中间数据生成", "Upload")
                continue

            prepared_df = _normalise_upload_dataframe(
                source_df,
                classification_default=DIRECT_INGEST_CLASSIFICATION,
            )
            if prepared_df.empty:
                result["skipped"].append(
                    {"channel": channel, "file": file_path.name, "reason": "无有效ID，无法入库"}
                )
                log_skip(logger, f"{file_path.name} 缺少有效ID，跳过中间数据生成", "Upload")
                continue

            output_file = filter_dir / file_path.name
            write_jsonl(prepared_df, output_file)
            total_rows += len(prepared_df)
            result["generated"].append(
                {"channel": channel, "file": output_file.name, "rows": len(prepared_df)}
            )
            log_success(logger, f"已生成中间数据: {output_file.name} ({len(prepared_df)} 条)", "Upload")
        except Exception as exc:
            detail = str(exc)
            result["failed"].append(
                {"channel": channel, "file": file_path.name, "reason": "生成失败", "detail": detail}
            )
            log_error(logger, f"生成中间数据失败: {file_path.name} - {detail}", "Upload")

    result["rows"] = total_rows
    if result["generated"]:
        _write_direct_ingest_summary(topic, date, filter_dir, total_rows=total_rows)
        result["status"] = "ok"
        result["message"] = f"已从 Clean 层生成 {len(result['generated'])} 个中间文件。"
        return result

    result["message"] = "未能从 Clean 层生成可入库中间文件。"
    return result


def _rebuild_from_fetch(
    topic: str,
    date: str,
    logger=None,
    dataset_name: Optional[str] = None,
    *,
    fetch_date: str = "",
) -> Dict[str, Any]:
    """
    从 fetch 层直接重建数据库，不经过 clean/filter 流程。

    Args:
        topic (str): 专题名称
        date (str): 日期字符串（用于filter层目录）
        logger: 日志记录器
        dataset_name: 数据库名称
        fetch_date: fetch层日期目录（如 "2025-01-15_2025-12-31"）

    Returns:
        Dict[str, Any]: 执行结果与详细信息
    """
    from ..utils.setting.paths import bucket as get_bucket

    target_database = (dataset_name or topic).strip()
    if not target_database:
        target_database = topic

    result: Dict[str, Any] = {
        "status": "error",
        "topic": topic,
        "date": date,
        "fetch_date": fetch_date,
        "database": target_database,
        "uploaded": [],
        "skipped": [],
        "failed": [],
    }

    # 定位 fetch 层数据
    if fetch_date:
        fetch_dir = get_bucket("fetch", topic, fetch_date)
    else:
        # 自动查找最新的 fetch 日期
        fetch_base = get_bucket("fetch", topic, "").parent
        fetch_dates = []
        if fetch_base.exists():
            for item in fetch_base.iterdir():
                if item.is_dir():
                    fetch_dates.append(item.name)
        fetch_dates.sort(reverse=True)
        if not fetch_dates:
            result["message"] = "未找到 fetch 层数据，请先执行数据抓取。"
            log_error(logger, result["message"], "Rebuild")
            return result
        fetch_date = fetch_dates[0]
        fetch_dir = get_bucket("fetch", topic, fetch_date)
        result["fetch_date"] = fetch_date

    if not fetch_dir.exists():
        result["message"] = f"fetch 层目录不存在: {fetch_dir}"
        log_error(logger, result["message"], "Rebuild")
        return result

    jsonl_files = sorted(fetch_dir.glob("*.jsonl"))
    # 跳过合并文件（如 总体.jsonl），避免重复导入
    MERGED_FILE_NAMES = {"总体", "all", "merged", "combined"}
    jsonl_files = [f for f in jsonl_files if f.stem not in MERGED_FILE_NAMES]
    if not jsonl_files:
        result["message"] = f"未在 fetch 层找到有效的渠道 JSONL 文件: {fetch_dir}"
        log_error(logger, result["message"], "Rebuild")
        return result

    log_success(logger, f"从 fetch 层({fetch_date})找到 {len(jsonl_files)} 个数据文件", "Rebuild")

    # 确保数据库存在
    if not db_manager.ensure_database(target_database):
        result["message"] = f"创建或连接数据库 {target_database} 失败。"
        log_error(logger, result["message"], "Rebuild")
        return result

    # 获取数据库引擎
    engine = None
    try:
        engine = db_manager.get_engine_for_database(target_database)
    except Exception as exc:
        result["message"] = f"无法连接数据库 {target_database}: {exc}"
        log_error(logger, result["message"], "Rebuild")
        return result

    # 上传数据
    success_tables: List[Dict[str, Any]] = []
    try:
        with engine.begin() as conn:
            # 创建表（如果不存在），已存在则 TRUNCATE 清空（重建 = 全量覆盖）
            for file_path in jsonl_files:
                table_name = file_path.stem
                if not table_exists(conn, table_name, target_database):
                    if not create_table_with_standard_schema(conn, table_name, topic, logger):
                        result["failed"].append(
                            {"channel": table_name, "file": file_path.name, "reason": "建表失败"}
                        )
                        continue
                else:
                    try:
                        conn.execute(text(f"TRUNCATE TABLE `{table_name}`"))
                        log_success(logger, f"已清空表 {table_name}（重建模式）", "Rebuild")
                    except Exception as trunc_exc:
                        log_error(logger, f"清空表 {table_name} 失败: {trunc_exc}", "Rebuild")

            # 上传数据
            total_rows = 0
            for file_path in jsonl_files:
                table_name = file_path.stem
                try:
                    df = read_jsonl(file_path)
                    if df is None or len(df) == 0:
                        log_skip(logger, f"{file_path.name} 无数据，跳过", "Rebuild")
                        result["skipped"].append({"channel": table_name, "reason": "文件无数据"})
                        continue

                    # 标准化数据
                    df = _normalise_upload_dataframe(df)
                    if df.empty:
                        result["skipped"].append({"channel": table_name, "reason": "无有效入库数据"})
                        continue

                    # 去重（基于id字段，先去文件内重复）
                    if "id" in df.columns:
                        before_count = len(df)
                        df = df.drop_duplicates(subset=["id"])
                        after_count = len(df)
                        if before_count != after_count:
                            log_success(logger, f"{file_path.name} 文件内去重: {before_count} -> {after_count}", "Rebuild")

                    # 写入数据库（表已 TRUNCATE，直接 append 无主键冲突）
                    df.to_sql(
                        table_name,
                        con=engine,
                        if_exists="append",
                        index=False,
                        method="multi",
                        chunksize=1000,
                    )

                    total_rows += len(df)
                    result["uploaded"].append(
                        {"channel": table_name, "file": file_path.name, "rows": len(df)}
                    )
                    log_success(
                        logger,
                        f"已上传 {table_name}: {len(df)} 条",
                        "Rebuild",
                    )
                except Exception as exc:
                    summary = _summarise_upload_exception(table_name, exc)
                    result["failed"].append(
                        {
                            "channel": table_name,
                            "file": file_path.name,
                            "reason": summary["reason"],
                            "detail": summary["detail"],
                        }
                    )
                    log_error(
                        logger,
                        f"上传 {table_name} 失败: {summary['detail']}",
                        "Rebuild",
                    )

        result["status"] = "ok"
        result["message"] = f"从 fetch 层({fetch_date})重建完成，共上传 {len(result['uploaded'])} 个表，{total_rows} 条记录。"
        log_success(logger, result["message"], "Rebuild")
        return result

    except Exception as exc:
        result["message"] = f"数据库操作异常: {exc}"
        log_error(logger, result["message"], "Rebuild")
        return result


def create_table_with_standard_schema(conn, table_name: str, topic: str, logger) -> bool:
    """
    使用标准结构创建表
    
    Args:
        conn: 数据库连接
        table_name (str): 表名
        topic (str): 专题名称
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    try:
        schema = get_standard_table_schema()
        column_defs = [f"`{col}` {mysql_type}" for col, mysql_type in schema.items()]
        
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            {', '.join(column_defs)}
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        
        conn.execute(text(create_sql))
        log_success(logger, f"已创建表 {topic}.{table_name}（标准结构）", "Upload")
        return True
        
    except Exception as e:
        log_error(logger, f"创建表 {topic}.{table_name} 失败: {e}", "Upload")
        return False


def table_exists(conn, table_name: str, topic: str) -> bool:
    """
    检查表是否存在
    
    Args:
        conn: 数据库连接
        table_name (str): 表名
        topic (str): 专题名称
    
    Returns:
        bool: 表是否存在
    """
    try:
        query = """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = :schema AND table_name = :table
        """
        result = conn.execute(text(query), {"schema": topic, "table": table_name})
        return (result.scalar() or 0) > 0
    except Exception:
        return False


def dedup_database_tables(
    database: str,
    table_names: Optional[List[str]] = None,
    logger=None,
) -> Dict[str, Any]:
    """
    对数据库中已存在的表按 id 字段去重。
    策略：读出全表 → drop_duplicates(id, keep='first') → TRUNCATE → 重写。

    Args:
        database: 数据库名称
        table_names: 要处理的表名列表；为 None 时处理该库全部表
        logger: 日志记录器

    Returns:
        Dict 包含每张表的处理结果
    """
    result: Dict[str, Any] = {
        "database": database,
        "cleaned": [],
        "skipped": [],
        "failed": [],
    }

    if not db_manager.ensure_database(database):
        result["status"] = "error"
        result["message"] = f"无法连接数据库 {database}"
        log_error(logger, result["message"], "Dedup")
        return result

    try:
        engine = db_manager.get_engine_for_database(database)
    except Exception as exc:
        result["status"] = "error"
        result["message"] = f"获取引擎失败: {exc}"
        log_error(logger, result["message"], "Dedup")
        return result

    try:
        with engine.connect() as probe_conn:
            inspector = inspect(probe_conn)
            all_tables = inspector.get_table_names()

        targets = [t for t in (table_names or all_tables) if t in all_tables]
        if not targets:
            result["status"] = "ok"
            result["message"] = "没有找到需要处理的表"
            return result

        for table_name in targets:
            try:
                df = pd.read_sql(f"SELECT * FROM `{table_name}`", con=engine)
                if df.empty or "id" not in df.columns:
                    result["skipped"].append({"table": table_name, "reason": "无数据或缺少id列"})
                    log_skip(logger, f"{table_name} 无数据或缺少id列，跳过", "Dedup")
                    continue

                before = len(df)
                df_dedup = df.drop_duplicates(subset=["id"], keep="first")
                after = len(df_dedup)
                removed = before - after

                if removed == 0:
                    result["skipped"].append({"table": table_name, "reason": "无重复行", "rows": before})
                    log_skip(logger, f"{table_name} 无重复行（{before} 条），跳过", "Dedup")
                    continue

                # 重写：TRUNCATE + 批量插入去重后数据
                with engine.begin() as conn:
                    conn.execute(text(f"TRUNCATE TABLE `{table_name}`"))
                    df_dedup.to_sql(
                        table_name,
                        con=conn,
                        if_exists="append",
                        index=False,
                        method="multi",
                        chunksize=1000,
                    )

                result["cleaned"].append({"table": table_name, "before": before, "after": after, "removed": removed})
                log_success(logger, f"{table_name} 去重完成: {before} → {after}（移除 {removed} 条）", "Dedup")

            except Exception as exc:
                result["failed"].append({"table": table_name, "detail": str(exc)})
                log_error(logger, f"{table_name} 去重失败: {exc}", "Dedup")

    finally:
        engine.dispose()

    result["status"] = "ok"
    result["message"] = (
        f"完成：{len(result['cleaned'])} 张表去重，"
        f"{len(result['skipped'])} 张跳过，"
        f"{len(result['failed'])} 张失败"
    )
    log_success(logger, result["message"], "Dedup")
    return result


def _summarise_upload_exception(channel: str, exc: Exception) -> Dict[str, str]:
    """Return user-friendly reason + technical details for upload failures."""

    detail = str(exc)
    reason = detail

    is_integrity = isinstance(exc, SAIntegrityError) or (
        PyMysqlIntegrityError is not None and isinstance(getattr(exc, "orig", exc), PyMysqlIntegrityError)
    )

    if is_integrity and "Duplicate entry" in detail:
        match = re.search(r"Duplicate entry '([^']+)' for key '([^']+)'", detail)
        if match:
            duplicate_id, key_name = match.groups()
            reason = f"{channel} 表已存在相同主键（示例 ID {duplicate_id}，索引 {key_name}）"
        else:
            reason = f"{channel} 表已存在重复主键记录"
    elif is_integrity:
        reason = f"{channel} 表触发唯一性约束，请检查字段设置"
    else:
        reason = f"{channel} 表写入失败，请查看服务器日志"

    return {"reason": reason, "detail": detail}


def upload_filtered_excels(
    topic: str,
    date: str,
    logger=None,
    dataset_name: Optional[str] = None,
    *,
    prepare_intermediate_from_clean: bool = False,
    rebuild_from_fetch: bool = False,
    fetch_date: str = "",
) -> Dict[str, Any]:
    """
    上传筛选后的JSONL文件到数据库
    使用锁死的标准表结构，按最大容量设计

    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器

    Returns:
        Dict[str, Any]: 执行结果与详细信息
    """

    # 1. 定位文件
    resolved_filter_date, filter_dir, jsonl_files = _resolve_layer_jsonl_files("filter", topic, date)

    target_database = (dataset_name or topic).strip()
    if not target_database:
        target_database = topic
    response: Dict[str, Any] = {
        "filter_dir": str(filter_dir),
        "topic": topic,
        "date": date,
        "resolved_filter_date": resolved_filter_date,
        "uploaded": [],
        "skipped": [],
        "failed": [],
        "database": target_database,
        "source_layer": "filter",
        "prepare_intermediate_from_clean": bool(prepare_intermediate_from_clean),
        "rebuild_from_fetch": bool(rebuild_from_fetch),
    }

    # 从 fetch 层重建：直接从 fetch 读取并入库
    if rebuild_from_fetch:
        rebuild_result = _rebuild_from_fetch(
            topic, date, logger, dataset_name=target_database, fetch_date=fetch_date
        )
        response["rebuild"] = rebuild_result
        if rebuild_result.get("status") != "ok":
            message = str(rebuild_result.get("message") or "从fetch层重建数据失败")
            log_error(logger, message, "Upload")
            return {
                **response,
                "status": "error",
                "message": message,
            }
        # 重建成功，直接返回结果（不需要再处理 filter 层文件）
        response["source_layer"] = "fetch-direct"
        response["uploaded"] = rebuild_result.get("uploaded", [])
        response["skipped"] = rebuild_result.get("skipped", [])
        response["failed"] = rebuild_result.get("failed", [])
        return {
            **response,
            "status": "ok",
            "message": rebuild_result.get("message", "从fetch层重建完成"),
        }

    if prepare_intermediate_from_clean and not rebuild_from_fetch:
        intermediate = _prepare_intermediate_from_clean(topic, date, logger)
        response["intermediate"] = intermediate
        if intermediate.get("status") == "ok":
            generated_files = intermediate.get("generated")
            resolved_files: List[Any] = []
            if isinstance(generated_files, list):
                for item in generated_files:
                    if not isinstance(item, dict):
                        continue
                    file_name = item.get("file")
                    if not isinstance(file_name, str) or not file_name.strip():
                        continue
                    candidate = filter_dir / file_name.strip()
                    if candidate.exists():
                        resolved_files.append(candidate)
            jsonl_files = sorted(resolved_files)
            response["source_layer"] = "clean->filter"
        else:
            message = str(intermediate.get("message") or "生成中间数据失败")
            log_error(logger, message, "Upload")
            return {
                **response,
                "status": "error",
                "message": message,
            }

    if not jsonl_files:
        if prepare_intermediate_from_clean:
            message = "中间数据已生成流程未产出可入库文件，请检查 clean 层数据。"
        else:
            message = "未找到筛选产物，请先完成 Filter 步骤或检查目录。"
        log_error(logger, message, "Upload")
        return {
            **response,
            "status": "error",
            "message": message,
        }

    # 2. 确保数据库存在
    if not db_manager.ensure_database(target_database):
        message = f"创建或连接数据库 {target_database} 失败，请检查数据库配置。"
        log_error(logger, message, "Upload")
        return {
            **response,
            "status": "error",
            "message": message,
        }

    # 3. 获取数据库引擎
    engine = None
    try:
        engine = db_manager.get_engine_for_database(target_database)
    except Exception as exc:
        message = f"无法连接数据库 {target_database}: {exc}"
        log_error(logger, message, "Upload")
        return {
            **response,
            "status": "error",
            "message": message,
        }

    success_tables: List[Dict[str, Any]] = []
    try:
        with engine.begin() as conn:
            # 4. 创建表（如果不存在）
            for file_path in jsonl_files:
                table_name = file_path.stem

                if not table_exists(conn, table_name, target_database):
                    if not create_table_with_standard_schema(conn, table_name, topic, logger):
                        response["failed"].append(
                            {"channel": table_name, "file": file_path.name, "reason": "建表失败"}
                        )
                        continue

            # 5. 上传数据
            for file_path in jsonl_files:
                table_name = file_path.stem

                try:
                    # 读取JSONL文件
                    df = read_jsonl(file_path)
                    if df is None or len(df) == 0:
                        log_skip(logger, f"{file_path.name} 无数据，跳过", "Upload")
                        response["skipped"].append(
                            {"channel": table_name, "file": file_path.name, "reason": "文件无数据"}
                        )
                        continue

                    # 清理数据
                    df = _normalise_upload_dataframe(df)
                    if df.empty:
                        log_skip(logger, f"{file_path.name} 无有效入库数据，跳过", "Upload")
                        response["skipped"].append(
                            {"channel": table_name, "file": file_path.name, "reason": "无有效入库数据"}
                        )
                        continue

                    # 去重（基于id字段）
                    if "id" in df.columns:
                        before_count = len(df)
                        df = df.drop_duplicates(subset=["id"])
                        after_count = len(df)
                        if before_count != after_count:
                            log_success(logger, f"{file_path.name} 文件内去重: {before_count} -> {after_count}", "Upload")

                        # 过滤数据库中已存在的ID，避免主键冲突
                        try:
                            existing_ids_df = pd.read_sql(
                                text(f"SELECT id FROM `{table_name}`"), con=engine
                            )
                            existing_ids = set(existing_ids_df["id"].astype(str).tolist())
                            if existing_ids:
                                before_db = len(df)
                                df = df[~df["id"].isin(existing_ids)]
                                after_db = len(df)
                                if before_db != after_db:
                                    log_success(
                                        logger,
                                        f"{table_name} 过滤已存在记录: {before_db - after_db} 条，剩余 {after_db} 条待入库",
                                        "Upload",
                                    )
                        except Exception as db_exc:
                            log_skip(logger, f"查询已存在ID失败，跳过DB去重: {db_exc}", "Upload")

                        if df.empty:
                            log_skip(logger, f"{table_name} 全部记录已存在于数据库，跳过写入", "Upload")
                            response["skipped"].append(
                                {"channel": table_name, "file": file_path.name, "reason": "全部记录已存在"}
                            )
                            continue

                    # 上传数据
                    df.to_sql(
                        table_name,
                        con=engine,
                        if_exists="append",
                        index=False,
                        method="multi",
                        chunksize=1000,
                    )

                    success_tables.append({"channel": table_name, "rows": len(df)})
                    log_success(logger, f"成功上传: {table_name} -- 共{len(df)}条", "Upload")

                except Exception as exc:
                    summary = _summarise_upload_exception(table_name, exc)
                    log_error(logger, f"上传失败: {topic}.{table_name} - {summary['detail']}", "Upload")
                    response["failed"].append(
                        {
                            "channel": table_name,
                            "file": file_path.name,
                            "reason": summary["reason"],
                            "detail": summary["detail"],
                        }
                    )
                    continue
    finally:
        if engine is not None:
            engine.dispose()

    response["uploaded"] = success_tables
    if success_tables:
        return {
            **response,
            "status": "ok",
            "message": f"{len(success_tables)} 个渠道写入成功",
        }

    fallback_message = "未成功写入任何渠道，请查看失败原因或服务器日志。"
    if response["failed"]:
        last_failure = response["failed"][-1]
        fallback_message = last_failure.get("reason") or fallback_message
    elif response["skipped"]:
        fallback_message = "筛选文件均为空或被跳过。"

    return {
        **response,
        "status": "error",
        "message": fallback_message,
    }


def run_update(
    topic: str,
    date: str,
    logger=None,
    dataset_name: Optional[str] = None,
    *,
    prepare_intermediate_from_clean: bool = False,
    rebuild_from_fetch: bool = False,
    fetch_date: str = "",
) -> Dict[str, Any]:
    """
    运行数据更新

    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器

    Returns:
        Dict[str, Any]: 执行状态与详情
    """
    if logger is None:
        logger = setup_logger(topic, date)

    log_module_start(logger, "Update")

    try:
        result = upload_filtered_excels(
            topic,
            date,
            logger,
            dataset_name=dataset_name,
            prepare_intermediate_from_clean=prepare_intermediate_from_clean,
            rebuild_from_fetch=rebuild_from_fetch,
            fetch_date=fetch_date,
        )
        if isinstance(result, dict):
            if result.get("status") != "error":
                return result
            message = result.get("message") or "上传阶段失败"
            log_error(logger, message, "Update")
            return result

        # 兼容旧实现返回布尔值
        if result:
            return {"status": "ok", "message": "上传完成"}
        log_error(logger, "模块执行失败", "Update")
        return {"status": "error", "message": "模块执行失败"}
    except Exception as exc:
        message = f"模块执行失败: {exc}"
        log_error(logger, message, "Update")
        return {
            "status": "error",
            "message": message,
            "topic": topic,
            "date": date,
        }
