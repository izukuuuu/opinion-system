"""
数据提取功能
"""
import pandas as pd
from ..utils.setting.paths import bucket, ensure_bucket
from ..utils.setting.settings import settings
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error, log_skip
from ..utils.io.excel import write_jsonl, read_jsonl
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url


def fetch_range(topic: str, start_date: str, end_date: str, output_date: str, logger=None) -> bool:
    """
    从数据库提取指定时间范围的数据
    
    Args:
        topic (str): 专题名称（作为数据库名）
        start_date (str): 开始日期
        end_date (str): 结束日期
        output_date (str): 输出日期（用于分桶）
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    
    # 1. 获取渠道配置
    channels_config = settings.get_channel_config()
    channels = channels_config.get('keep', [])
    
    # 2. 创建输出目录
    folder_name = f"{start_date}_{end_date}"
    fetch_dir = ensure_bucket("fetch", topic, folder_name)
    
    # 3. 获取数据库连接
    db_config = settings.get('databases', {})
    db_url = db_config.get('db_url')
    if not db_url:
        log_error(logger, "未找到数据库连接配置", "Fetch")
        return False
    
    base_url = make_url(db_url)
    db_url_with_db = base_url.set(database=topic)
    engine = create_engine(db_url_with_db)
    
    all_data = []
    channel_files = {}
    
    try:
        with engine.connect() as conn:
            # 4. 提取各渠道数据
            for channel in channels:
                try:
                    if not table_exists(conn, channel, topic):
                        log_skip(logger, f"表 {topic}.{channel} 不存在，跳过", "Fetch")
                        continue
                    
                    # 查询数据
                    query = """
                    SELECT * FROM {table_name}
                    WHERE DATE(published_at) BETWEEN :start_date AND :end_date
                    ORDER BY published_at DESC
                    """.format(table_name=channel)
                    
                    result = conn.execute(text(query), {
                        'start_date': start_date,
                        'end_date': end_date
                    })
                    
                    df = pd.DataFrame(result.fetchall(), columns=result.keys())
                    
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
                    return True
                else:
                    log_error(logger, "没有提取到任何数据", "Fetch")
                    return False
            else:
                log_error(logger, "没有提取到任何数据", "Fetch")
                return False
                
    finally:
        engine.dispose()


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


def run_fetch(topic: str, start: str, end: str, logger=None) -> bool:
    """
    运行数据提取
    
    Args:
        topic (str): 专题名称
        start (str): 开始日期
        end (str): 结束日期
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger(topic, start)
    
    log_module_start(logger, "Fetch")
    
    try:
        result = fetch_range(topic, start, end, start, logger)
        if result:
            return True
        else:
            log_error(logger, "模块执行失败", "Fetch")
            return False
    except Exception as e:
        log_error(logger, f"模块执行失败: {e}", "Fetch")
        return False
