"""
趋势分析函数
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
import pandas as pd
from ...utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from ...utils.setting.paths import bucket
from ...utils.io.excel import read_csv

def _analyze_trends(df: pd.DataFrame, channel_name: str, logger=None) -> Dict[str, Any]:
    """
    趋势分析核心函数
    
    Args:
        df (pd.DataFrame): 数据框
        channel_name (str): 渠道名称
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 趋势分析结果
    """
    if logger is None:
        logger = setup_logger("Analyze", "default")
    
    try:
        # 检查数据是否为空
        if df.empty:
            log_error(logger, "数据框为空，无法进行趋势分析", "Analyze")
            return {"data": []}
        
        # 检查必要的列是否存在
        if 'published_at' not in df.columns:
            log_error(logger, "缺少必要的列: published_at", "Analyze")
            return {"data": []}
        
        # 确保时间字段是datetime类型
        df = df.copy()  # 创建副本避免警告
        df['published_at'] = pd.to_datetime(df['published_at'], errors='coerce')
        df = df.dropna(subset=['published_at'])
        
        if df.empty:
            log_error(logger, "时间字段处理后数据为空，无法进行趋势分析", "Analyze")
            return {"data": []}
        
        # 按日期统计趋势
        df['date'] = df['published_at'].dt.date
        daily_counts = df['date'].value_counts().sort_index()
        
        # 转换为要求的格式
        data = [{"name": str(k), "value": int(v)} for k, v in daily_counts.items()]
        result = {"data": data}
        
        log_success(logger, f"trends | {channel_name} 分析完成", "Analyze")
        return result
        
    except Exception as e:
        log_error(logger, f"趋势分析失败: {e}", "Analyze")
        return {"data": []}

def analyze_trends_overall(df: pd.DataFrame, logger=None) -> Dict[str, Any]:
    """
    分析总体趋势
    
    Args:
        df (pd.DataFrame): 数据框
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 趋势分析结果
    """
    return _analyze_trends(df, "总体", logger)

def analyze_trends_by_channel(df: pd.DataFrame, channel_name: str, logger=None) -> Dict[str, Any]:
    """
    分析渠道趋势
    
    Args:
        df (pd.DataFrame): 数据框
        channel_name (str): 渠道名称
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 趋势分析结果
    """
    return _analyze_trends(df, channel_name, logger)

