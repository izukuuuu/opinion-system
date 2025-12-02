"""
数据更新功能
"""
from __future__ import annotations

import pandas as pd
import re
from typing import Any, Dict, List, Optional

from ..utils.setting.paths import bucket
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error, log_skip
from ..utils.io.excel import read_jsonl, sanitize_dataframe, get_standard_table_schema
from ..utils.io.db import db_manager
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError as SAIntegrityError

try:  # Optional dependency; PyMySQL is used by default
    from pymysql.err import IntegrityError as PyMysqlIntegrityError
except Exception:  # pragma: no cover - fallback when driver missing
    PyMysqlIntegrityError = None


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


def upload_filtered_excels(topic: str, date: str, logger=None, dataset_name: Optional[str] = None) -> Dict[str, Any]:
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
    filter_dir = bucket("filter", topic, date)
    jsonl_files = list(filter_dir.glob("*.jsonl"))

    target_database = (dataset_name or topic).strip()
    if not target_database:
        target_database = topic
    response: Dict[str, Any] = {
        "filter_dir": str(filter_dir),
        "topic": topic,
        "date": date,
        "uploaded": [],
        "skipped": [],
        "failed": [],
        "database": target_database,
    }

    if not jsonl_files:
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

                if not table_exists(conn, table_name, topic):
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
                    df = sanitize_dataframe(df)

                    # 去重（基于id字段）
                    if "id" in df.columns:
                        before_count = len(df)
                        df = df.drop_duplicates(subset=["id"])
                        after_count = len(df)
                        if before_count != after_count:
                            log_success(logger, f"{file_path.name} 去重: {before_count} -> {after_count}", "Upload")

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


def run_update(topic: str, date: str, logger=None, dataset_name: Optional[str] = None) -> Dict[str, Any]:
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
        result = upload_filtered_excels(topic, date, logger, dataset_name=dataset_name)
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
