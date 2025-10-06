"""
发布机构分析函数
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
import pandas as pd
from ...utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from ...utils.setting.paths import bucket
from ...utils.io.excel import read_csv

def _analyze_publishers(df: pd.DataFrame, channel_name: str, logger=None) -> Dict[str, Any]:
    """
    发布机构分析核心函数
    
    Args:
        df (pd.DataFrame): 数据框
        channel_name (str): 渠道名称
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 发布机构分析结果
    """
    if logger is None:
        logger = setup_logger("Analyze", "default")
    
    try:
        if 'author' not in df.columns:
            log_error(logger, "数据缺少 author 列", "Analyze")
            return {"data": []}

        # 计算发布机构统计（过滤 "未知"）
        _clean = df['author'].dropna().astype(str).map(lambda x: x.strip())
        _clean = _clean[_clean != "未知"]
        publisher_counts = _clean.value_counts().to_dict()
        top_publishers = list(publisher_counts.items())[:20]
        
        # 转换为要求的格式
        data = [{"name": pub, "value": count} for pub, count in top_publishers]
        result = {"data": data}
        
        log_success(logger, f"publishers | {channel_name} 分析完成", "Analyze")
        return result
        
    except Exception as e:
        log_error(logger, f"发布机构分析失败: {e}", "Analyze")
        return {"data": []}

def analyze_publishers_overall(df: pd.DataFrame, logger=None) -> Dict[str, Any]:
    """
    分析总体发布机构
    
    Args:
        df (pd.DataFrame): 数据框
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 发布机构分析结果
    """
    return _analyze_publishers(df, "总体", logger)

def analyze_publishers_by_channel(df: pd.DataFrame, channel_name: str, logger=None) -> Dict[str, Any]:
    """
    分析渠道发布机构
    
    Args:
        df (pd.DataFrame): 数据框
        channel_name (str): 渠道名称
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 发布机构分析结果
    """
    return _analyze_publishers(df, channel_name, logger)


