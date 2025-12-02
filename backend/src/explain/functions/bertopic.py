"""
主题分析（BERTopic）解读功能
"""
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from .base import ExplainBase
from ...utils.setting.paths import bucket, get_project_root
from ...utils.logging.logging import log_success, log_error


async def explain_bertopic_overall(topic: str, date: str, logger=None, end_date: str = None) -> Optional[Dict[str, Any]]:
    """
    解读总体主题分析结果
    
    Args:
        topic (str): 专题名称
        date (str): 日期
        logger: 日志记录器
        end_date (str, optional): 结束日期
        
    Returns:
        Optional[Dict[str, Any]]: 解读结果
    """
    explainer = ExplainBase(topic, logger)
    
    # 加载主题分析数据
    data = explainer.load_bertopic_data(date, end_date)
    if not data:
        return None
    
    # 生成解读
    explanation = await explainer.generate_explanation("bertopic", data, "总体")
    if explanation:
        # 保存结果
        explainer.save_explanation("bertopic", "总体", explanation, date, end_date)
        return explanation
    
    return None

