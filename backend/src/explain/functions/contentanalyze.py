"""
内容分析解读功能
"""
import asyncio
from typing import Dict, Any, Optional
from .base import ExplainBase


async def explain_contentanalyze_by_channel(topic: str, channel_name: str, date: str, logger=None, end_date: str = None) -> Optional[Dict[str, Any]]:
    """
    解读渠道内容分析结果
    
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
    
    # 加载内容分析数据（特殊处理）
    data = explainer.load_contentanalyze_data(date, end_date)
    if not data:
        return None
    
    # 生成解读
    explanation = await explainer.generate_explanation("contentanalyze", data, "渠道", channel_name)
    if explanation:
        # 保存结果
        explainer.save_explanation("contentanalyze", "渠道", explanation, date, end_date, channel_name)
        return explanation
    
    return None
