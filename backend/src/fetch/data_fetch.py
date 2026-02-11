"""
数据提取功能
"""
import logging
import re
from datetime import date, datetime
from typing import List, Optional, Tuple, Dict, Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from ..utils.setting.paths import ensure_bucket
from ..utils.setting.settings import settings
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error, log_skip
from ..utils.io.excel import write_jsonl, read_jsonl
from ..utils.io.db import DatabaseManager


def fetch_range(
    topic: str,
    start_date: str,
    end_date: str,
    output_date: str,
    logger=None,
    db_topic: Optional[str] = None,
) -> Optional[int]:
    """
    从数据库提取指定时间范围的数据
    
    Args:
        topic (str): 专题名称（作为数据库名）
        start_date (str): 开始日期
        end_date (str): 结束日期
        output_date (str): 输出日期（用于分桶）
        logger: 日志记录器
    
    Returns:
        Optional[int]: 成功返回提取条数，失败返回 None
    """
    
    # 1. 获取渠道配置
    channels_config = settings.get_channel_config()
    channels = channels_config.get('keep', [])
    
    # 2. 创建输出目录
    folder_name = f"{start_date}_{end_date}"
    fetch_dir = ensure_bucket("fetch", topic, folder_name)
    
    db_name = _normalise_db_topic(db_topic or topic)

    # 3. 获取数据库连接（统一走 DatabaseManager，兼容 active MySQL/PostgreSQL）
    engine = _create_topic_engine(db_name, logger=logger)
    if engine is None:
        return None
    
    all_data = []
    channel_files = {}
    
    try:
        # 4. 提取各渠道数据（每个渠道独立连接，降低长连接断开影响）
        for channel in channels:
            try:
                df = _fetch_channel_dataframe(engine, db_name, channel, start_date, end_date, logger=logger)
                if df is None:
                    log_skip(logger, f"表 {db_name}.{channel} 不存在，跳过", "Fetch")
                    continue

                if len(df) > 0:
                    # 确保classification字段存在
                    if 'classification' not in df.columns:
                        df['classification'] = '未知'
                    else:
                        df['classification'] = df['classification'].fillna('未知')

                    # 保存渠道数据
                    channel_file = fetch_dir / f"{channel}.jsonl"
                    write_jsonl(df, channel_file)
                    channel_files[channel] = channel_file
                    all_data.append(df)

                    log_success(logger, f"成功提取: {channel} -- 共{len(df)}条", "Fetch")
                else:
                    log_skip(logger, f"渠道 {channel} 无数据", "Fetch")
            except Exception as e:
                log_error(logger, f"提取渠道 {channel} 失败: {e}", "Fetch")
                continue

        # 5. 合并渠道数据
        merge_config = channels_config.get('merge_for_analysis', {})
        files_to_remove = set()

        for merge_name, source_channels in merge_config.items():
            try:
                merge_data = []
                for source_channel in source_channels:
                    if source_channel in channel_files and channel_files[source_channel].exists():
                        df = read_jsonl(channel_files[source_channel])
                        if len(df) > 0:
                            merge_data.append(df)
                            files_to_remove.add(source_channel)

                if merge_data:
                    merged_df = pd.concat(merge_data, ignore_index=True)
                    merged_file = fetch_dir / f"{merge_name}.jsonl"
                    write_jsonl(merged_df, merged_file)
                    all_data.append(merged_df)
                    log_success(logger, f"合并完成: {merge_name} -- {len(merged_df)}条)", "Fetch")

            except Exception as e:
                log_error(logger, f"合并 {merge_name} 失败: {e}", "Fetch")
                continue

        # 6. 删除已合并的原始文件
        for channel in files_to_remove:
            if channel in channel_files and channel_files[channel].exists():
                try:
                    channel_files[channel].unlink()
                except Exception as e:
                    log_error(logger, f"删除文件 {channel}.jsonl 失败: {e}", "Fetch")

        # 7. 保存总体数据
        if all_data:
            # 重新收集未合并的数据
            final_data = []
            for channel in channels:
                if channel not in files_to_remove and channel in channel_files and channel_files[channel].exists():
                    df = read_jsonl(channel_files[channel])
                    if len(df) > 0:
                        final_data.append(df)

            # 添加合并后的数据
            for merge_name in merge_config.keys():
                merged_file = fetch_dir / f"{merge_name}.jsonl"
                if merged_file.exists():
                    df = read_jsonl(merged_file)
                    if len(df) > 0:
                        final_data.append(df)

            if final_data:
                all_df = pd.concat(final_data, ignore_index=True)
                all_file = fetch_dir / "总体.jsonl"
                write_jsonl(all_df, all_file)
                return len(all_df)
            else:
                log_error(logger, "没有提取到任何数据", "Fetch")
                return None
        else:
            log_error(logger, "没有提取到任何数据", "Fetch")
            return None

    finally:
        engine.dispose()


_PROJECT_ID_PATTERN = re.compile(r"^(\d{8})-(\d{6})-(.+)$")


def _normalise_db_topic(topic: str) -> str:
    """
    将项目标识形式的专题名（例如 20251202-071626-控烟）还原为数据库名部分。

    如果不符合时间戳前缀模式，则返回原始字符串的去空白版本。
    """
    text = str(topic or "").strip()
    match = _PROJECT_ID_PATTERN.match(text)
    if match:
        return match.group(3).strip() or text
    return text


def _format_date(value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _quote_identifier(conn, identifier: str) -> str:
    """使用底层方言的规则对对象名加引号，避免特殊字符导致 SQL 报错。"""
    try:
        preparer = getattr(conn.dialect, "identifier_preparer", None)
        if preparer:
            return preparer.quote(identifier)
    except Exception:
        pass
    safe = identifier.replace('"', '""').replace("`", "``")
    return f'"{safe}"'


def _create_topic_engine(db_topic: str, logger=None):
    """创建并返回指定专题数据库的引擎（兼容 active MySQL/PostgreSQL）。"""
    try:
        db_manager = DatabaseManager()
        return db_manager.get_engine_for_database(db_topic)
    except Exception as exc:
        log_error(logger, f"创建数据库引擎失败({db_topic}): {exc}", "Fetch")
        return None


def _build_fetch_query(conn, table_name: str):
    quoted_table = _quote_identifier(conn, table_name)
    date_expr = "CAST(published_at AS DATE)" if conn.dialect.name == 'postgresql' else "DATE(published_at)"
    query = f"""
    SELECT * FROM {quoted_table}
    WHERE {date_expr} BETWEEN :start_date AND :end_date
    ORDER BY published_at DESC
    """
    return text(query)


def _is_disconnect_error(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    markers = [
        "lost connection",
        "server has gone away",
        "(2013",
        "(2006",
        "connection reset",
    ]
    return any(marker in message for marker in markers)


def _fetch_channel_dataframe(engine, db_name: str, channel: str, start_date: str, end_date: str, logger=None):
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                if not table_exists(conn, channel, db_name):
                    return None
                query = _build_fetch_query(conn, channel)
                result = conn.execute(query, {"start_date": start_date, "end_date": end_date})
                return pd.DataFrame(result.fetchall(), columns=result.keys())
        except OperationalError as exc:
            if attempt < max_attempts and _is_disconnect_error(exc):
                log_skip(logger, f"渠道 {channel} 连接中断，正在重试({attempt}/{max_attempts})", "Fetch")
                continue
            raise
    return None


def _query_table_date_range(conn, table_name: str, topic: str, logger=None) -> Tuple[Optional[date], Optional[date]]:
    if not table_exists(conn, table_name, topic):
        log_skip(logger, f"表 {topic}.{table_name} 不存在", "Fetch")
        return None, None

    quoted_table = _quote_identifier(conn, table_name)
    
    # Dialect-specific date function
    if conn.dialect.name == 'postgresql':
        date_expr = "CAST(published_at AS DATE)"
    else:
        date_expr = "DATE(published_at)"
        
    query = f"""
    SELECT
        MIN({date_expr}) AS start_date,
        MAX({date_expr}) AS end_date
    FROM {quoted_table}
    """
    try:
        result = conn.execute(text(query)).mappings().first()
    except Exception as exc:
        log_error(logger, f"查询表 {table_name} 日期区间失败: {exc}", "Fetch")
        return None, None

    if not result:
        return None, None
    return result.get("start_date"), result.get("end_date")


def _list_topic_tables(conn, topic: str, logger=None) -> List[str]:
    """
    获取专题数据库中包含 published_at 字段的所有表。
    """
    if conn.dialect.name == 'postgresql':
        # PostgreSQL: Check public schema in the current database (already connected)
        query = """
        SELECT DISTINCT TABLE_NAME AS table_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name = 'published_at'
        ORDER BY TABLE_NAME
        """
        params = {}
    else:
        # MySQL: table_schema is the database name
        query = """
        SELECT DISTINCT TABLE_NAME AS table_name
        FROM information_schema.columns
        WHERE table_schema = :schema AND column_name = 'published_at'
        ORDER BY TABLE_NAME
        """
        params = {"schema": topic}

    try:
        result = conn.execute(text(query), params).mappings()
        tables = [row.get("table_name") for row in result if row and row.get("table_name")]
        if not tables:
            log_skip(logger, f"专题 {topic} 未找到包含 published_at 字段的表", "Fetch")
        return tables
    except Exception as e:
        log_error(logger, f"查询专题 {topic} 表结构失败: {e}", "Fetch")
        return []


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
        if conn.dialect.name == 'postgresql':
            query = """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = :table
            """
            params = {"table": table_name}
        else:
            query = """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :table
            """
            params = {"schema": topic, "table": table_name}
            
        result = conn.execute(text(query), params)
        return (result.scalar() or 0) > 0
    except Exception:
        return False


def get_available_date_range(topic: str, table_name: str, logger=None):
    """
    查询指定专题下表的可用日期区间（最早/最晚发布时间）

    Args:
        topic (str): 专题名称（数据库名）
        table_name (str): 表名
        logger: 日志记录器

    Returns:
        tuple[str | None, str | None]: (最早日期, 最晚日期)。若表不存在或无数据则返回 (None, None)
    """
    if logger is None:
        logger = logging.getLogger("fetch-availability")
    db_topic = _normalise_db_topic(topic)
    engine = _create_topic_engine(db_topic, logger=logger)
    if engine is None:
        return None, None

    try:
        with engine.connect() as conn:
            if not table_exists(conn, table_name, db_topic):
                log_skip(logger, f"表 {db_topic}.{table_name} 不存在", "Fetch")
                return None, None

            start_date, end_date = _query_table_date_range(conn, table_name, db_topic, logger)
            return _format_date(start_date), _format_date(end_date)
    except OperationalError as e:
        log_error(logger, f"查询表 {table_name} 日期区间失败: {e}", "Fetch")
        return None, None
    except Exception as e:
        log_error(logger, f"查询表 {table_name} 日期区间失败: {e}", "Fetch")
        return None, None
    finally:
        engine.dispose()


def get_topic_available_date_range(topic: str, logger=None):
    """
    汇总专题下所有渠道表的可用日期范围

    Args:
        topic (str): 专题名称（数据库名）
        logger: 日志记录器

    Returns:
        dict: {
            "start": Optional[str],
            "end": Optional[str],
            "channels": Dict[str, Dict[str, Optional[str]]]
        }
    """
    if logger is None:
        logger = logging.getLogger("fetch-availability")
    db_topic = _normalise_db_topic(topic)
    engine = _create_topic_engine(db_topic, logger=logger)
    if engine is None:
        return {"start": None, "end": None, "channels": {}}

    table_ranges = {}
    min_date: Optional[date] = None
    max_date: Optional[date] = None

    try:
        with engine.connect() as conn:
            tables = _list_topic_tables(conn, db_topic, logger)
            if not tables:
                log_skip(logger, f"专题 {db_topic} 无可用表，返回默认空区间", "Fetch")
            for table_name in tables:
                start_value, end_value = _query_table_date_range(conn, table_name, db_topic, logger)
                table_ranges[table_name] = {
                    "start": _format_date(start_value),
                    "end": _format_date(end_value)
                }
                if start_value:
                    if min_date is None or start_value < min_date:
                        min_date = start_value
                if end_value:
                    if max_date is None or end_value > max_date:
                        max_date = end_value
    except OperationalError as e:
        log_error(logger, f"汇总专题 {db_topic} 日期区间失败: {e}", "Fetch")
    except Exception as e:
        log_error(logger, f"汇总专题 {db_topic} 日期区间失败: {e}", "Fetch")
    finally:
        engine.dispose()

    return {
        "start": _format_date(min_date),
        "end": _format_date(max_date),
        "tables": table_ranges,
        "channels": table_ranges,  # 向后兼容旧字段
    }


def run_fetch(topic: str, start: str, end: str, logger=None, db_topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    运行数据提取
    
    Args:
        topic (str): 专题名称
        start (str): 开始日期
        end (str): 结束日期
        logger: 日志记录器
        db_topic (Optional[str]): 远程数据库名称（可选），不传则使用 topic
    
    Returns:
        Optional[Dict[str, Any]]: 成功返回包含计数的结果字典，失败返回 None
    """
    if logger is None:
        logger = setup_logger(topic, start)
    
    log_module_start(logger, "Fetch")
    
    try:
        count = fetch_range(topic, start, end, start, logger, db_topic=db_topic)
        if count is not None:
            return {"count": count}
        else:
            log_error(logger, "模块执行失败", "Fetch")
            return None
    except Exception as e:
        log_error(logger, f"模块执行失败: {e}", "Fetch")
        return None
