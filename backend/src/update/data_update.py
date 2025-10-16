"""
数据更新功能
"""
import pandas as pd
from pathlib import Path
from ..utils.setting.paths import bucket, ensure_bucket
from ..utils.setting.settings import settings
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error, log_skip
from ..utils.io.excel import read_jsonl, sanitize_dataframe, get_standard_table_schema
from ..utils.io.db import db_manager
from sqlalchemy import text


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


def upload_filtered_excels(topic: str, date: str, logger=None) -> bool:
    """
    上传筛选后的JSONL文件到数据库
    使用锁死的标准表结构，按最大容量设计
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    
    # 1. 定位文件
    filter_dir = bucket("filter", topic, date)
    jsonl_files = list(filter_dir.glob("*.jsonl"))
    
    if not jsonl_files:
        log_error(logger, "未找到JSONL文件", "Upload")
        return False
    
    # 2. 确保数据库存在
    if not db_manager.ensure_database(topic):
        log_error(logger, f"创建数据库 {topic} 失败", "Upload")
        return False
    
    # 3. 获取数据库引擎
    engine = db_manager.get_engine_for_database(topic)
    success_count = 0
    
    with engine.begin() as conn:
        # 4. 创建表（如果不存在）
        for file_path in jsonl_files:
            table_name = file_path.stem
            
            if not table_exists(conn, table_name, topic):
                if not create_table_with_standard_schema(conn, table_name, topic, logger):
                    continue
        
        # 5. 上传数据
        for file_path in jsonl_files:
            table_name = file_path.stem
            
            try:
                # 读取JSONL文件
                df = read_jsonl(file_path)
                if df is None or len(df) == 0:
                    log_skip(logger, f"{file_path.name} 无数据，跳过", "Upload")
                    continue
                
                # 清理数据
                df = sanitize_dataframe(df)
                
                # 去重（基于id字段）
                if 'id' in df.columns:
                    before_count = len(df)
                    df = df.drop_duplicates(subset=['id'])
                    after_count = len(df)
                    if before_count != after_count:
                        log_success(logger, f"{file_path.name} 去重: {before_count} -> {after_count}", "Upload")
                
                # 上传数据
                df.to_sql(
                    table_name, 
                    con=engine, 
                    if_exists='append', 
                    index=False, 
                    method='multi', 
                    chunksize=1000
                )
                
                success_count += 1
                log_success(logger, f"成功上传: {table_name} -- 共{len(df)}条", "Upload")
                
            except Exception as e:
                log_error(logger, f"上传失败: {topic}.{table_name} - {e}", "Upload")
                continue
    
    engine.dispose()
    return success_count > 0


def run_update(topic: str, date: str, logger=None) -> bool:
    """
    运行数据更新
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger(topic, date)
    
    log_module_start(logger, "Update")

    try:
        # 上传筛选后的Excel文件
        result = upload_filtered_excels(topic, date, logger)

        if result:
            return True
        else:
            log_error(logger, "模块执行失败", "Update")
            return False
    except Exception as e:
        log_error(logger, f"模块执行失败: {e}", "Update")
        return False
