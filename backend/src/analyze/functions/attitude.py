"""
态度分析函数
"""
import pandas as pd
from typing import Dict, List, Any
from ...utils.logging.logging import setup_logger, log_success, log_error, log_module_start

def _normalize_attitude_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    将数据框中的情感列标准化为 attitude 字段，兼容多种列名与取值
    
    Args:
        df (pd.DataFrame): 数据框
    
    Returns:
        pd.DataFrame: 标准化后的数据框
    """
    if 'attitude' in df.columns:
        return df
    df = df.copy()
    # 候选列名（按常见命名）
    candidate_cols = [
        'polarity', 'sentiment', '情感', '情绪', '情感倾向', 'att', 'label'
    ]
    col = next((c for c in candidate_cols if c in df.columns), None)
    if col is None:
        df['attitude'] = 'unknown'
        return df
    s = df[col]
    # 标准化值
    def to_att(v):
        """
        将情感值标准化为英文标签
        
        Args:
            v: 原始情感值
        
        Returns:
            str: 标准化的情感标签
        """
        if v is None:
            return 'unknown'
        try:
            # 数字映射
            f = float(v)
            if f > 0:
                return 'positive'
            if f < 0:
                return 'negative'
            return 'neutral'
        except Exception:
            pass
        x = str(v).strip().lower()
        mapping = {
            '正面': 'positive', '积极': 'positive', 'positive': 'positive', 'pos': 'positive', 'p': 'positive',
            '负面': 'negative', '消极': 'negative', 'negative': 'negative', 'neg': 'negative', 'n': 'negative',
            '中性': 'neutral', 'neutral': 'neutral', '客观': 'neutral', 'neu': 'neutral'
        }
        return mapping.get(x, 'unknown')
    df['attitude'] = s.map(to_att)
    return df

def analyze_attitude_overall(df: pd.DataFrame, logger=None) -> Dict[str, Any]:
    """
    分析总体态度分布

    Args:
        df (pd.DataFrame): 数据框
        logger: 日志记录器

    Returns:
        Dict[str, Any]: 态度分析结果
    """
    if logger is None:
        logger = setup_logger("attitude", "analysis")


    try:
        # 标准化态度字段
        df = _normalize_attitude_column(df)

        # 统计态度分布
        attitude_counts = df['attitude'].value_counts().to_dict()

        # 转换为数据格式
        attitude_data = [{"name": k, "value": v} for k, v in attitude_counts.items()]

        result = {
            "data": attitude_data
        }

        log_success(logger, "attitude | 总体 分析完成", "Analyze")
        return result

    except Exception as e:
        log_error(logger, f"总体态度分析失败: {e}", "Analyze")
        # 返回空的data数组
        return {
            "data": []
        }

def analyze_attitude_by_channel(df: pd.DataFrame, channel_name: str, logger=None) -> Dict[str, Any]:
    """
    按渠道分析态度分布

    Args:
        df (pd.DataFrame): 数据框
        channel_name (str): 渠道名称
        logger: 日志记录器

    Returns:
        Dict[str, Any]: 态度分析结果
    """
    if logger is None:
        logger = setup_logger("attitude", "channel")


    try:
        df = _normalize_attitude_column(df)
        attitude_counts = df['attitude'].value_counts().to_dict()
        attitude_data = [{"name": k, "value": v} for k, v in attitude_counts.items()]

        result = {
            "data": attitude_data
        }

        log_success(logger, f"attitude | {channel_name} 分析完成", "Analyze")
        return result

    except Exception as e:
        log_error(logger, f"渠道态度分析失败: {e}", "Analyze")
        return {
            "data": []
        }


