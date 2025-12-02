"""
分类分析模块 - 对classification字段进行统计分析
"""
import pandas as pd
from typing import Dict, Any, List
from ...utils.logging.logging import log_success, log_error, log_skip


def analyze_classification_overall(df: pd.DataFrame, logger) -> Dict[str, Any]:
    """
    分析总体分类统计
    
    Args:
        df (pd.DataFrame): 总体数据
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 分类统计结果
    """
    try:
        if df.empty:
            log_skip(logger, "总体数据为空，跳过分类分析", "Analyze")
            return {}
        
        # 检查classification字段是否存在
        if 'classification' not in df.columns:
            log_error(logger, "数据中缺少classification字段", "Analyze")
            return {}
        
        # 清理分类数据
        df_classification = df['classification'].fillna('未知').astype(str).str.strip()
        df_classification = df_classification.replace(['', 'nan', 'None', 'null'], '未知')
        
        # 统计分类分布
        classification_counts = df_classification.value_counts()
        total_count = len(df_classification)
        
        # 计算百分比
        classification_percentages = (classification_counts / total_count * 100).round(2)
        
        # 构建结果 - 按照指定格式
        data_list = []
        for classification, count in classification_counts.items():
            data_list.append({
                "name": classification,
                "value": int(count)
            })
        
        result = {
            "data": data_list
        }
        
        log_success(logger, "classification | 总体 分析完成", "Analyze")
        return result
        
    except Exception as e:
        log_error(logger, f"总体分类分析失败: {e}", "Analyze")
        return {}


def analyze_classification_by_channel(df: pd.DataFrame, channel_name: str, logger) -> Dict[str, Any]:
    """
    分析渠道分类统计
    
    Args:
        df (pd.DataFrame): 渠道数据
        channel_name (str): 渠道名称
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 渠道分类统计结果
    """
    try:
        if df.empty:
            log_skip(logger, f"渠道 {channel_name} 数据为空，跳过分类分析", "Analyze")
            return {}
        
        # 检查classification字段是否存在
        if 'classification' not in df.columns:
            log_error(logger, f"渠道 {channel_name} 数据中缺少classification字段", "Analyze")
            return {}
        
        # 清理分类数据
        df_classification = df['classification'].fillna('未知').astype(str).str.strip()
        df_classification = df_classification.replace(['', 'nan', 'None', 'null'], '未知')
        
        # 统计分类分布
        classification_counts = df_classification.value_counts()
        total_count = len(df_classification)
        
        # 计算百分比
        classification_percentages = (classification_counts / total_count * 100).round(2)
        
        # 构建结果 - 按照指定格式
        data_list = []
        for classification, count in classification_counts.items():
            data_list.append({
                "name": classification,
                "value": int(count)
            })
        
        result = {
            "data": data_list
        }
        
        log_success(logger, f"classification | {channel_name} 分析完成", "Analyze")
        return result
        
    except Exception as e:
        log_error(logger, f"渠道分类分析失败: {e}", "Analyze")
        return {}
