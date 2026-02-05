"""
数据查询功能
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..utils.io.db import DatabaseManager
from ..utils.setting.settings import settings
from ..utils.logging.logging import (
    log_error,
    log_module_start,
    log_success,
    setup_logger,
)


def _summarise_tables(tables: List[Dict[str, Any]]) -> Dict[str, Any]:
    """生成表级别统计信息"""

    total_rows = 0
    counted_tables = 0
    for table in tables:
        record_count = table.get("record_count")
        if isinstance(record_count, (int, float)):
            total_rows += int(record_count)
            counted_tables += 1

    return {
        "table_count": len(tables),
        "counted_table_count": counted_tables,
        "total_rows": total_rows,
    }


PREVIEW_ROW_LIMIT = 20


def _serialise_preview(df: pd.DataFrame, max_rows: int = PREVIEW_ROW_LIMIT) -> Dict[str, Any]:
    """将数据预览转换为可序列化结构"""

    preview_df = df.head(max_rows)
    columns = preview_df.columns.tolist()
    rows: List[Dict[str, Any]] = []

    for record in preview_df.to_dict(orient="records"):
        normalised: Dict[str, Any] = {}
        for key, value in record.items():
            if isinstance(value, (datetime, date)):
                normalised[key] = value.isoformat()
            elif isinstance(value, Decimal):
                normalised[key] = float(value)
            elif isinstance(value, (bytes, bytearray)):
                normalised[key] = value.decode("utf-8", errors="replace")
            elif pd.isna(value):
                normalised[key] = None
            elif hasattr(value, "item"):
                try:
                    normalised[key] = value.item()
                except Exception:
                    normalised[key] = str(value)
            else:
                normalised[key] = value
        rows.append(normalised)

    return {"columns": columns, "rows": rows}


MAX_TABLE_WORKERS = 6


def _fetch_table_info(
    db_manager: DatabaseManager,
    db_name: str,
    table_name: str,
    logger: Any,
    approx_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch the row count and sample for a single table."""

    table_info: Dict[str, Any] = {"name": table_name}
    
    # Use dialect to determine quoting
    try:
        engine = db_manager.connect()
        dialect_name = engine.dialect.name
    except Exception:
        dialect_name = "unknown"

    def get_query_target(db: str, table: str) -> str:
        if dialect_name == "postgresql":
            # In Postgres, we must be connected to the DB, so we query the table directly (public schema assumed)
            # We explicitly quote the table name
            return f'"{table}"'
        elif dialect_name == "mysql":
            # In MySQL, we stay on one connection and query db.table
            return f"`{db}`.`{table}`"
        return table

    # 优先使用 information_schema.TABLES 提供的近似行数，避免对每张表执行 COUNT(*)
    # checking for None and pd.isna (if pandas is available, but safe check is simpler)
    # If the provided approx_rows effectively implies "we don't know" (None), do a real count.
    
    use_approx = False
    if approx_rows is not None:
        try:
            # Check for NaN if it came from pandas
            import math
            if isinstance(approx_rows, float) and math.isnan(approx_rows):
                raise ValueError("NaN")
            
            # Postgres returns -1 if statistics are missing
            if int(approx_rows) < 0:
                raise ValueError("Negative approx rows (missing stats)")

            table_info["record_count"] = int(approx_rows)
            use_approx = True
        except Exception:
            # Failed to use approx_rows (e.g. it was None, NaN, or invalid), proceed to query
            pass

    if not use_approx:
        try:
            target = get_query_target(db_name, table_name)
            count_query = f"SELECT COUNT(*) as record_count FROM {target}"
            count_result = db_manager.execute_query(count_query)
            record_count = count_result["record_count"].iloc[0]
            table_info["record_count"] = int(record_count)
            log_success(logger, f"表 {db_name}.{table_name} 包含 {record_count} 条记录", "Query")
        except Exception as e:
            table_info["error"] = str(e)
            log_error(logger, f"查询表 {db_name}.{table_name} 信息失败: {e}", "Query")
            return table_info

    try:
        target = get_query_target(db_name, table_name)
        preview_query = f"SELECT * FROM {target} LIMIT {PREVIEW_ROW_LIMIT}"
        preview_result = db_manager.execute_query(preview_query)
        table_info["preview"] = _serialise_preview(preview_result)
    except Exception as preview_error:
        table_info["preview_error"] = str(preview_error)
        log_error(
            logger,
            f"查询表 {db_name}.{table_name} 预览数据失败: {preview_error}",
            "Query",
        )

    return table_info


def _process_database_metadata(
    db_name: str,
    base_engine_url: Any,
    dialect_name: str,
    include_counts: bool,
    logger: Any
) -> Dict[str, Any]:
    """Process a single database to retrieve its tables and stats."""
    
    database_overview: Dict[str, Any] = {
        "name": db_name,
        "tables": [],
    }
    
    # Decide which manager to use
    scope_manager = None
    
    try:
        if dialect_name == 'postgresql':
            # Use sqlalchemy to build new URL with replaced database
            from sqlalchemy.engine.url import make_url
            
            base_url = make_url(base_engine_url)
            # Create a temporary manager for this specific database
            target_url = base_url.set(database=db_name)
            # IMPORTANT: render_as_string(hide_password=False) ensure password is not masked as ***
            scope_manager = DatabaseManager(target_url.render_as_string(hide_password=False))
        else:
            # Re-use existing manager concept (conceptually) but we need a fresh one 
            # if we want thread safety or just use a new one for consistency.
            scope_manager = DatabaseManager(base_engine_url)

        # 获取数据库中的表及 approximate 行数
        if dialect_name == 'postgresql':
            tables_query = """
            SELECT
                t.tablename as table_name,
                c.reltuples::bigint as table_rows
            FROM pg_tables t
            JOIN pg_class c ON t.tablename = c.relname
            WHERE t.schemaname = 'public'
                AND c.relkind = 'r'
            ORDER BY t.tablename
            """
        else:
            tables_query = """
            SELECT
                TABLE_NAME as table_name,
                TABLE_ROWS as table_rows
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :db_name
            ORDER BY TABLE_NAME
            """

        try:
            tables_df = scope_manager.execute_query(tables_query, {"db_name": db_name})
        except Exception as conn_err:
            log_error(logger, f"无法连接或查询数据库 {db_name}: {conn_err}", "Query")
            return database_overview

        if tables_df.empty:
            log_success(logger, f"数据库 {db_name} 无表", "Query")
            database_overview.update(_summarise_tables([]))
            return database_overview

        table_names = tables_df['table_name'].tolist()
        approx_rows_map = {}
        if 'table_rows' in tables_df.columns:
            approx_rows_map = {
                row['table_name']: row['table_rows']
                for _, row in tables_df.iterrows()
            }
        
        log_success(
            logger,
            f"数据库 {db_name} 包含 {len(table_names)} 个表",
            "Query",
        )

        # 轻量模式
        if not include_counts:
            database_overview["tables"] = [{"name": name} for name in table_names]
            stats = {
                "table_count": len(table_names),
                "counted_table_count": 0,
                "total_rows": 0,
            }
            database_overview.update(stats)
            return database_overview

        table_workers = min(MAX_TABLE_WORKERS, len(table_names)) or 1
        
        # We are already in a thread, so avoiding nested large thread pools is good,
        # but fetching table info is IO bound.
        # Let's verify sequentially if table count is small, or small pool.
        
        futures: Dict[Any, Tuple[int, str]] = {}
        with ThreadPoolExecutor(max_workers=table_workers) as executor:
            for index, table_name in enumerate(table_names):
                approx_rows = approx_rows_map.get(table_name)
                future = executor.submit(_fetch_table_info, scope_manager, db_name, table_name, logger, approx_rows)
                futures[future] = (index, table_name)

            table_results: List[Tuple[int, Dict[str, Any]]] = []
            for future in as_completed(futures):
                index, table_name = futures[future]
                try:
                    table_info = future.result()
                except Exception as exc:
                    log_error(
                        logger,
                        f"查询表 {db_name}.{table_name} 过程中发生异常: {exc}",
                        "Query",
                    )
                    table_info = {"name": table_name, "error": str(exc)}
                table_results.append((index, table_info))

        table_results.sort(key=lambda pair: pair[0])
        database_overview["tables"] = [info for _, info in table_results]

        stats = _summarise_tables(database_overview["tables"])
        database_overview.update(stats)
        return database_overview
        
    finally:
        if scope_manager:
            try:
                scope_manager.close()
            except Exception:
                pass


def query_database_info(logger=None, include_counts: bool = True) -> Optional[Dict[str, Any]]:
    """
    查询数据库信息

    Args:
        logger: 日志记录器

    Returns:
        Optional[Dict[str, Any]]: 查询结果摘要
    """
    db_manager: Optional[DatabaseManager] = None

    try:
        # 创建数据库管理器 (让 DatabaseManager 自动解析 active 连接)
        db_manager = DatabaseManager()
        
        if not db_manager.db_url:
            log_error(logger, "未找到数据库连接配置 (active or db_url)", "Query")
            return None

        overview: Dict[str, Any] = {
            "queried_at": datetime.utcnow().isoformat() + "Z",
            "connection": {},
            "databases": [],
            "summary": {},
        }

        try:
            from sqlalchemy.engine.url import make_url

            parsed_url = make_url(db_manager.db_url)
            overview["connection"] = {
                "driver": parsed_url.drivername,
                "host": parsed_url.host,
                "port": parsed_url.port,
                "database": parsed_url.database,
                "username": parsed_url.username,
                "has_password": bool(parsed_url.password),
            }
        except Exception:
            overview["connection"] = {"driver": "unknown"}

        try:
            # 获取所有数据库（屏蔽系统库）
            engine = db_manager.connect()
            # Force a connection check because create_engine is lazy
            with engine.connect() as check_conn:
                pass
        except Exception as e:
            # If default connection fails (e.g. database deleted), try fallback to 'postgres'
            log_error(logger, f"Primary database connection failed ({e}). Attempting fallback to 'postgres'...", "Query")
            try:
                from sqlalchemy import create_engine
                from sqlalchemy.engine.url import make_url
                base_url = make_url(db_manager.db_url)
                # Try 'postgres' first (common for PostgreSQL)
                fallback_url = base_url.set(database='postgres')
                db_manager.engine = create_engine(fallback_url)
                engine = db_manager.engine
                
                # Verify fallback also works
                with engine.connect() as check_conn:
                    pass
                    
                # Update db_url to valid one so subsequent calls work
                db_manager.db_url = fallback_url.render_as_string(hide_password=False)
            except Exception as fallback_err:
                 log_error(logger, f"Fallback connection also failed: {fallback_err}", "Query")
                 # Re-raise the original or fallback error? 
                 # If fallback fails, we can't do anything.
                 raise fallback_err from e 

        dialect_name = engine.dialect.name
        
        if dialect_name == 'postgresql':
            databases_query = """
            SELECT datname as database_name
            FROM pg_database
            WHERE datistemplate = false
              AND datname NOT IN ('postgres')
            ORDER BY datname
            """
        else:
            databases_query = """
            SELECT SCHEMA_NAME as database_name
            FROM information_schema.SCHEMATA
            WHERE SCHEMA_NAME NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys', 'test', 'phpmyadmin')
            ORDER BY SCHEMA_NAME
            """

        databases_df = db_manager.execute_query(databases_query)

        if databases_df.empty:
            log_error(logger, "未找到任何数据库", "Query")
            return None

        db_names = databases_df['database_name'].tolist()
        log_success(
            logger,
            f"发现 {len(db_names)} 个数据库: {', '.join(db_names)}",
            "Query",
        )
        
        base_url_str = db_manager.db_url
        
        # Parallel Execution for databases
        max_db_workers = min(8, len(db_names))
        
        futures_db = []
        with ThreadPoolExecutor(max_workers=max_db_workers) as executor:
            for db_name in db_names:
                futures_db.append(
                    executor.submit(
                        _process_database_metadata,
                        db_name,
                        base_url_str,
                        dialect_name,
                        include_counts,
                        logger
                    )
                )
                
            for future in as_completed(futures_db):
                try:
                    db_result = future.result()
                    if db_result:
                        overview["databases"].append(db_result)
                except Exception as e:
                    log_error(logger, f"处理数据库元数据失败: {e}", "Query")

        overview["databases"].sort(key=lambda x: x["name"])

        # Calculate totals
        total_tables = sum(db.get("table_count", 0) for db in overview["databases"])
        total_rows = sum(db.get("total_rows", 0) for db in overview["databases"])

        overview["summary"] = {
            "database_count": len(overview["databases"]),
            "table_count": total_tables,
            "row_count": total_rows,
        }

        log_success(logger, "数据库元信息查询完成", "Query")
        return overview

    except Exception as e:
        log_error(logger, f"查询数据库信息失败: {e}", "Query")
        return None
    finally:
        # Close the main manager
        if db_manager is not None:
             try:
                 db_manager.close()
             except Exception:
                 pass


def run_query(logger=None, include_counts: bool = True) -> Dict[str, Any]:
    """
    运行数据查询

    Args:
        logger: 日志记录器

    Returns:
        Dict[str, Any]: 查询结果摘要
    """
    if logger is None:
        logger = setup_logger("Query", "info")

    log_module_start(logger, "Query")

    try:
        result = query_database_info(logger, include_counts=include_counts)
        if result is not None:
            return result

        log_error(logger, "模块执行失败", "Query")
        return {"status": "error"}
    except Exception as e:
        log_error(logger, f"模块执行失败: {e}", "Query")
        return {"status": "error", "message": str(e)}
