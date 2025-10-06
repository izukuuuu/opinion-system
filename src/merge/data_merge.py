"""
TRS数据合并功能
"""
import pandas as pd
from pathlib import Path
from ..utils.setting.paths import bucket, ensure_bucket
from ..utils.setting.settings import settings
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error, log_skip
from ..utils.io.excel import read_excel, write_excel


def merge_trs_data(topic: str, date: str, logger=None) -> bool:
    """
    合并TRS Excel文件
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
        
    # 1. 定位文件
    raw_dir = bucket("raw", topic, date)
    if not raw_dir.exists():
        log_error(logger, f"原始数据目录不存在: {raw_dir}", "Merge")
        return False
    
    # 2. 获取渠道配置
    channels_config = settings.get_channel_config()
    keep_channels = channels_config.get('keep', [])
    field_aliases = channels_config.get('field_aliases', {})
    
    if not keep_channels:
        log_error(logger, "未找到渠道配置", "Merge")
        return False
    
    # 3. 创建输出目录
    merge_dir = ensure_bucket("merge", topic, date)
    
    # 4. 收集所有Excel文件
    excel_files = list(raw_dir.glob("*.xlsx"))
    if not excel_files:
        log_error(logger, "未找到Excel文件", "Merge")
        return False
        
    # 5. 按渠道分组处理
    channel_data = {}
    success_count = 0
    
    for file_path in excel_files:
        try:
            # 读取Excel文件的所有sheet
            excel_data = pd.read_excel(file_path, sheet_name=None)
            
            for sheet_name, df in excel_data.items():
                if df.empty:
                    continue
                
                # 检查是否是目标渠道
                if sheet_name in keep_channels:
                    if sheet_name not in channel_data:
                        channel_data[sheet_name] = []
                    
                    # 应用字段别名
                    df = df.rename(columns=field_aliases)
                    channel_data[sheet_name].append(df)
        
        except Exception as e:
            log_error(logger, f"处理文件失败: {file_path.name} - {e}", "Merge")
            continue
    
    # 6. 合并并保存数据
    for channel, data_list in channel_data.items():
        if not data_list:
            continue
        
        try:
            # 合并同一渠道的所有数据
            merged_df = pd.concat(data_list, ignore_index=True)
            
            # 去重
            before_count = len(merged_df)
            merged_df = merged_df.drop_duplicates()
            after_count = len(merged_df)
            
            if before_count != after_count:
                log_success(logger, f"渠道 {channel} 去重: {before_count} -> {after_count}", "Merge")
            
            # 保存到merge目录
            output_file = merge_dir / f"{channel}.xlsx"
            write_excel(merged_df, output_file)
            
            success_count += 1
            log_success(logger, f"成功保存: {channel} -- 共{len(merged_df)}条", "Merge")
            
        except Exception as e:
            log_error(logger, f"合并渠道 {channel} 失败: {e}", "Merge")
            continue
    
    if success_count > 0:
        return True
    else:
        log_error(logger, "合并失败: 没有成功处理任何渠道", "Merge")
        return False


def run_merge(topic: str, date: str, logger=None):
    """
    运行TRS数据合并
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger(topic, date)
    
    log_module_start(logger, "Merge")

    try:
        result = merge_trs_data(topic, date, logger)
        if result:
            return True
        else:
            log_error(logger, "模块执行失败", "Merge")
            return False
    except Exception as e:
        log_error(logger, f"模块执行失败: {e}", "Merge")
        return False
