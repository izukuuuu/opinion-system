"""
声量解读功能
"""
import asyncio
from typing import Dict, Any, Optional
from .base import ExplainBase


async def explain_volume_overall(topic: str, date: str, logger=None, end_date: str = None) -> Optional[Dict[str, Any]]:
    """
    解读总体声量分析结果
    
    Args:
        topic (str): 专题名称
        date (str): 日期
        logger: 日志记录器
        end_date (str, optional): 结束日期
        
    Returns:
        Optional[Dict[str, Any]]: 解读结果
    """
    explainer = ExplainBase(topic, logger)
    
    # 加载分析数据
    data = explainer.load_analysis_data("volume", "总体", date, end_date)
    if not data:
        return None
    
    # 生成解读
    explanation = await explainer.generate_explanation("volume", data, "总体")
    if explanation:
        # 保存结果
        explainer.save_explanation("volume", "总体", explanation, date, end_date)
        return explanation
    
    return None


async def explain_volume_by_channel(topic: str, channel_name: str, date: str, logger=None, end_date: str = None) -> Optional[Dict[str, Any]]:
    """
    解读渠道声量分析结果
    
    Args:
        topic (str): 专题名称
        channel_name (str): 渠道名称
        date (str): 日期
        logger: 日志记录器
        end_date (str, optional): 结束日期
        
    Returns:
        Optional[Dict[str, Any]]: 解读结果
    """
    explainer = ExplainBase(topic, logger)
    
    # 加载分析数据
    data = explainer.load_analysis_data("volume", "渠道", date, end_date)
    if not data:
        return None
    
    # 过滤特定渠道数据
    channel_data = {"data": [item for item in data.get("data", []) if item.get("name") == channel_name]}
    if not channel_data["data"]:
        return None
    
    # 生成解读
    explanation = await explainer.generate_explanation("volume", channel_data, "渠道", channel_name)
    if explanation:
        # 保存结果
        explainer.save_explanation("volume", "渠道", explanation, date, end_date, channel_name)
        return explanation
    
    return None
