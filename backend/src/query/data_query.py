"""
数据查询功能
"""
import pandas as pd
from ..utils.io.db import DatabaseManager
from ..utils.setting.settings import settings
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error


def query_database_info(logger=None) -> bool:
    """
    查询数据库信息
    
    Args:
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    
    try:
        # 获取数据库配置
        db_config = settings.get('databases', {})
        db_url = db_config.get('db_url')
        
        if not db_url:
            log_error(logger, "未找到数据库连接配置", "Query")
            return False
        
        # 创建数据库管理器
        db_manager = DatabaseManager(db_url)
        
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
            return False
        
        log_success(logger, f"发现 {len(databases_df)} 个数据库: {', '.join(databases_df['database_name'].tolist())}", "Query")
        
        # 遍历每个数据库
        for _, db_row in databases_df.iterrows():
            db_name = db_row['database_name']
            
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
                continue
            
            table_names = tables_df['table_name'].tolist()
            log_success(logger, f"数据库 {db_name} 包含 {len(table_names)} 个表: {', '.join(table_names)}", "Query")
            
            # 遍历每个表
            for table_name in table_names:
                try:
                    # 获取表记录数
                    count_query = f"SELECT COUNT(*) as record_count FROM `{db_name}`.`{table_name}`"
                    count_result = db_manager.execute_query(count_query)
                    record_count = count_result['record_count'].iloc[0]
                    
                    log_success(logger, f"表 {db_name}.{table_name} 包含 {record_count} 条记录", "Query")
                        
                except Exception as e:
                    log_error(logger, f"查询表 {db_name}.{table_name} 信息失败: {e}", "Query")
                    continue
        
        db_manager.close()
        return True
        
    except Exception as e:
        log_error(logger, f"查询数据库信息失败: {e}", "Query")
        return False


def run_query(logger=None) -> bool:
    """
    运行数据查询
    
    Args:
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger("Query", "info")
    
    log_module_start(logger, "Query")

    try:
        result = query_database_info(logger)
        if result:
            return True
        else:
            log_error(logger, "模块执行失败", "Query")
            return False
    except Exception as e:
        log_error(logger, f"模块执行失败: {e}", "Query")
        return False