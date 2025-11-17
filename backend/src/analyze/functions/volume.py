"""
声量分析函数
"""
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any
from ...utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from ...utils.setting.paths import bucket
from ...utils.io.excel import read_jsonl
from .echarts_common import build_bar_option


def analyze_volume_overall(df: pd.DataFrame, topic: str, date: str, logger=None, end_date: str = None) -> Dict[str, Any]:
    """
    分析总体声量 - 统计各渠道JSONL文件的样本数量对比
    
    Args:
        df (pd.DataFrame): 数据框（总体数据）
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 声量分析结果
    """
    if logger is None:
        logger = setup_logger("Analyze", "default")
    
    try:
        # 从fetch目录读取各渠道JSONL文件进行统计
        # 如果提供了结束日期，使用日期范围格式，否则使用单个日期
        if end_date:
            folder_name = f"{date}_{end_date}"
        else:
            folder_name = date
        fetch_dir = bucket("fetch", topic, folder_name)
        if not fetch_dir.exists():
            log_error(logger, f"fetch目录不存在: {fetch_dir}", "Analyze")
            return {"data": []}
        
        # 获取所有JSONL文件（排除 总体.jsonl）
        jsonl_files = [f for f in fetch_dir.glob('*.jsonl') if f.name != '总体.jsonl']
        if not jsonl_files:
            log_error(logger, f"fetch目录中没有找到渠道JSONL文件: {fetch_dir}", "Analyze")
            return {"data": []}
        
        # 统计每个渠道JSONL文件的行数
        channel_counts = {}
        for jsonl_path in jsonl_files:
            try:
                df_channel = read_jsonl(jsonl_path)
                channel_name = jsonl_path.stem
                record_count = len(df_channel)
                channel_counts[channel_name] = record_count
            except Exception as e:
                log_error(logger, f"读取 {jsonl_path.name} 失败: {e}", "Analyze")
                continue
        
        if not channel_counts:
            log_error(logger, "没有成功读取任何渠道JSONL文件", "Analyze")
            return {"data": []}
        
        # 转换为要求的格式
        data = [{"name": k, "value": v} for k, v in channel_counts.items()]
        result = {"data": data}
        if data:
            result["echarts"] = build_bar_option(
                title=f"声量对比 · 总体",
                data=data,
                sort_desc=True,
                category_label="渠道",
                value_label="声量",
            )
        
        log_success(logger, f"volume | 总体 分析完成", "Analyze")
        return result
        
    except Exception as e:
        log_error(logger, f"声量分析失败: {e}", "Analyze")
        return {"data": []}

def analyze_volume_by_channel(df: pd.DataFrame, channel_name: str, topic: str, date: str, logger=None, end_date: str = None) -> Dict[str, Any]:
    """
    分析渠道声量 - 统计单个渠道JSONL文件的样本数量
    
    Args:
        df (pd.DataFrame): 数据框（渠道数据）
        channel_name (str): 渠道名称
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 声量分析结果
    """
    if logger is None:
        logger = setup_logger("Analyze", "default")
    
    try:
        # 从fetch目录读取对应渠道的JSONL文件
        # 如果提供了结束日期，使用日期范围格式，否则使用单个日期
        if end_date:
            folder_name = f"{date}_{end_date}"
        else:
            folder_name = date
        fetch_dir = bucket("fetch", topic, folder_name)
        jsonl_file = fetch_dir / f"{channel_name}.jsonl"
        
        if not jsonl_file.exists():
            log_error(logger, f"渠道JSONL文件不存在: {jsonl_file}", "Analyze")
            return {"data": []}
        
        # 读取并统计记录数量
        df_channel = read_jsonl(jsonl_file)
        record_count = len(df_channel)
        
        # 转换为要求的格式
        data = [{"name": channel_name, "value": record_count}]
        result = {"data": data}
        if data:
            result["echarts"] = build_bar_option(
                title=f"声量对比 · {channel_name}",
                data=data,
                sort_desc=True,
                category_label="渠道",
                value_label="声量",
            )
        
        log_success(logger, f"volume | {channel_name} 分析完成", "Analyze")
        return result
        
    except Exception as e:
        log_error(logger, f"声量分析失败: {e}", "Analyze")
        return {"data": []}
