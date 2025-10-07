"""
数据查询功能
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

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


def query_database_info(logger=None) -> Optional[Dict[str, Any]]:
    """
    查询数据库信息

    Args:
        logger: 日志记录器

    Returns:
        Optional[Dict[str, Any]]: 查询结果摘要
    """

    db_manager: Optional[DatabaseManager] = None

    try:
        # 获取数据库配置
        db_config = settings.get('databases', {})
        db_url = db_config.get('db_url')

        if not db_url:
            log_error(logger, "未找到数据库连接配置", "Query")
            raise RuntimeError("未找到数据库连接配置")

        overview: Dict[str, Any] = {
            "queried_at": datetime.utcnow().isoformat() + "Z",
            "connection": {},
            "databases": [],
            "summary": {},
        }

        # 创建数据库管理器
        db_manager = DatabaseManager(db_url)

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

        # 获取所有数据库（屏蔽系统库）
        databases_query = """
        SELECT SCHEMA_NAME as database_name
        FROM information_schema.SCHEMATA
        WHERE SCHEMA_NAME NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys', 'test', 'phpmyadmin')
        ORDER BY SCHEMA_NAME
        """

        databases_df = db_manager.execute_query(databases_query)

        if databases_df.empty:
            log_error(logger, "未找到任何数据库", "Query")
            raise RuntimeError("未找到任何业务数据库")

        log_success(
            logger,
            f"发现 {len(databases_df)} 个数据库: {', '.join(databases_df['database_name'].tolist())}",
            "Query",
        )

        total_tables = 0
        total_rows = 0

        # 遍历每个数据库
        for _, db_row in databases_df.iterrows():
            db_name = db_row['database_name']
            database_overview: Dict[str, Any] = {
                "name": db_name,
                "tables": [],
            }

            # 获取数据库中的表
            tables_query = """
            SELECT TABLE_NAME as table_name
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :db_name
            ORDER BY TABLE_NAME
            """

            tables_df = db_manager.execute_query(tables_query, {"db_name": db_name})

            if tables_df.empty:
                log_success(logger, f"数据库 {db_name} 无表", "Query")
                database_overview.update(_summarise_tables([]))
                overview["databases"].append(database_overview)
                continue

            table_names = tables_df['table_name'].tolist()
            log_success(
                logger,
                f"数据库 {db_name} 包含 {len(table_names)} 个表: {', '.join(table_names)}",
                "Query",
            )

            # 遍历每个表
            for table_name in table_names:
                table_info: Dict[str, Any] = {"name": table_name}
                try:
                    # 获取表记录数
                    count_query = f"SELECT COUNT(*) as record_count FROM `{db_name}`.`{table_name}`"
                    count_result = db_manager.execute_query(count_query)
                    record_count = count_result['record_count'].iloc[0]
                    table_info["record_count"] = int(record_count)
                    log_success(logger, f"表 {db_name}.{table_name} 包含 {record_count} 条记录", "Query")
                except Exception as e:
                    table_info["error"] = str(e)
                    log_error(logger, f"查询表 {db_name}.{table_name} 信息失败: {e}", "Query")
                database_overview["tables"].append(table_info)

            stats = _summarise_tables(database_overview["tables"])
            database_overview.update(stats)
            total_tables += stats["table_count"]
            total_rows += stats["total_rows"]
            overview["databases"].append(database_overview)

        overview["summary"] = {
            "database_count": len(overview["databases"]),
            "table_count": total_tables,
            "row_count": total_rows,
        }

        log_success(logger, "数据库元信息查询完成", "Query")
        return overview

    except Exception as e:
        log_error(logger, f"查询数据库信息失败: {e}", "Query")
        raise RuntimeError(f"查询数据库信息失败: {e}") from e
    finally:
        if db_manager is not None:
            try:
                db_manager.close()
            except Exception:
                pass


def run_query(logger=None) -> Dict[str, Any]:
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

    result = query_database_info(logger)
    if result is None:
        log_error(logger, "模块执行失败", "Query")
        raise RuntimeError("数据库查询未返回数据")
    return result
