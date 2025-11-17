"""
地域分析函数
"""
import pandas as pd
from typing import Dict, List, Any
from ...utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from .echarts_common import build_bar_option

def _detect_region_col(df: pd.DataFrame) -> str:
    """
    检测地域列名
    
    Args:
        df (pd.DataFrame): 数据框
    
    Returns:
        str: 地域列名，如果未找到则返回None
    """
    candidate_cols = ['region', '地区', '省份', 'province', 'Province', 'location_province']
    return next((c for c in candidate_cols if c in df.columns), None)

def _count_regions(df: pd.DataFrame) -> Dict[str, int]:
    """
    统计地域分布
    
    Args:
        df (pd.DataFrame): 数据框
    
    Returns:
        Dict[str, int]: 地域统计结果
    """
    # 兼容多种列名
    region_col = _detect_region_col(df)
    if region_col is None:
        return {}
    series = df[region_col].fillna('未知')
    # 去除空白
    series = series.astype(str).str.strip()
    counts = series.value_counts().to_dict()
    return counts


def analyze_geography_overall(df: pd.DataFrame, logger=None) -> Dict[str, Any]:
    """
    分析总体地域分布
    
    Args:
        df (pd.DataFrame): 数据框
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 地域分析结果
    """
    if logger is None:
        logger = setup_logger("default", "default")
        
    try:
        # 统计地域分布
        region_counts = _count_regions(df)
        sorted_counts = sorted(region_counts.items(), key=lambda item: item[1], reverse=True)

        # 转换为JSON格式
        region_data = [{"name": k, "value": v} for k, v in sorted_counts]

        result = {
            "data": region_data
        }
        if region_data:
            result["echarts"] = build_bar_option(
                title="地域分布 · 总体",
                data=region_data,
                orientation="horizontal",
                category_label="地域",
                value_label="声量",
            )

        log_success(logger, "geography | 总体 分析完成", "Analyze")
        return result

    except Exception as e:
        log_error(logger, f"geography | 总体 分析失败: {e}", "Analyze")
        return {}

def analyze_geography_by_channel(df: pd.DataFrame, channel_name: str, logger=None) -> Dict[str, Any]:
    """
    分析单渠道地域分布，返回与总体类似的结构

    Args:
        df (pd.DataFrame): 数据框
        channel_name (str): 渠道名称
        logger: 日志记录器

    Returns:
        Dict[str, Any]: 渠道地域分析结果
    """
    if logger is None:
        logger = setup_logger("default", "default")

    try:
        # 统计地域分布
        region_counts = _count_regions(df)
        sorted_counts = sorted(region_counts.items(), key=lambda item: item[1], reverse=True)

        # 转换为JSON格式
        region_data = [{"name": k, "value": v} for k, v in sorted_counts]

        result = {
            "data": region_data
        }
        if region_data:
            result["echarts"] = build_bar_option(
                title=f"地域分布 · {channel_name}",
                data=region_data,
                orientation="horizontal",
                category_label="地域",
                value_label="声量",
            )

        log_success(logger, f"geography | {channel_name} 分析完成", "Analyze")
        return result
    except Exception as e:
        log_error(logger, f"geography | {channel_name} 分析失败: {e}", "Analyze")
        return {}
