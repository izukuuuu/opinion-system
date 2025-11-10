"""
关键词分析函数
"""
import pandas as pd
import re
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Any, Tuple
from ...utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from ...utils.setting.paths import bucket
from ...utils.io.excel import read_excel, read_csv
from .echarts_common import build_bar_option

# 导入jieba分词
try:
    import jieba
    import jieba.posseg as pseg
    JIEBA_AVAILABLE = True
    # 静默设置jieba日志级别
    jieba.setLogLevel(60)  # 设置为ERROR级别，减少输出
except ImportError:
    JIEBA_AVAILABLE = False

def load_stopwords() -> set:
    """
    从配置文件加载停用词库
    
    Returns:
        set: 停用词集合
    """
    try:
        # 获取项目根目录
        project_root = Path(__file__).resolve().parents[4]
        stopwords_file = project_root / "configs" / "stopwords.txt"
        
        # 如果第一个路径不存在，尝试其他可能的路径
        if not stopwords_file.exists():
            # 尝试从当前工作目录查找
            cwd = Path.cwd()
            stopwords_file = cwd / "configs" / "stopwords.txt"
            
        if not stopwords_file.exists():
            # 尝试从环境变量或配置文件获取
            import os
            config_dir = os.getenv('OPINION_CONFIG_DIR', 'configs')
            stopwords_file = Path(config_dir) / "stopwords.txt"
        
        if not stopwords_file.exists():
            # 停用词文件不存在，返回空集合
            return set()
        
        with open(stopwords_file, 'r', encoding='utf-8') as f:
            stopwords = {line.strip() for line in f if line.strip()}
        
        return stopwords
    except Exception as e:
        # 加载停用词失败，返回空集合
        return set()

def extract_keywords(text: str, stopwords: set, min_length: int = 2) -> List[str]:
    """
    提取关键词
    
    Args:
        text (str): 文本内容
        stopwords (set): 停用词集合
        min_length (int, optional): 最小词长度，默认2
    
    Returns:
        List[str]: 关键词列表
    """
    if not text or pd.isna(text):
        return []
    
    # 清理文本
    text = str(text).strip()
    if not text:
        return []
    
    if JIEBA_AVAILABLE:
        # 使用jieba进行智能分词
        words = []
        for word, flag in pseg.cut(text):
            # 只保留有意义的词性：n(名词)、v(动词)、a(形容词)、nr(人名)、ns(地名)、nt(机构名)
            if flag.startswith(('n', 'v', 'a', 'nr', 'ns', 'nt')) and len(word) >= min_length:
                # 过滤停用词
                if word not in stopwords:
                    words.append(word)
        
        return words
    else:
        # 降级到简单分词
        # 去除标点符号、数字和特殊字符，保留中文和英文
        text = re.sub(r'[^\u4e00-\u9fff\w\s]', ' ', text)
        
        # 按空格分割
        words = text.split()
        
        # 过滤短词和停用词
        keywords = [word for word in words if len(word) >= min_length and word not in stopwords]
        
        return keywords

def _analyze_keywords(df: pd.DataFrame, topic: str, channel_name: str, logger=None) -> Dict[str, Any]:
    """
    关键词分析核心函数
    
    Args:
        df (pd.DataFrame): 数据框
        topic (str): 话题名称
        channel_name (str): 渠道名称
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 关键词分析结果
    """
    if logger is None:
        logger = setup_logger("Analyze", "default")
    
    try:
        # 合并所有文本内容 - 支持多种列名
        content_columns = []
        for col in df.columns:
            if any(keyword in col.lower() for keyword in ['content', 'contents', '内容', '正文', '摘要', 'ocr', 'segment']):
                content_columns.append(col)
        
        if not content_columns:
            # 如果没有找到内容列，使用所有可能包含文本的列
            text_columns = ['title', 'summary', 'content', 'contents', '正文', '摘要']
            content_columns = [col for col in text_columns if col in df.columns]
        
        if not content_columns:
            log_error(logger, "未找到任何可用的内容列", "Analyze")
            return {"data": []}
        
        all_text = ' '.join(df[content_columns].fillna('').astype(str).values.flatten())
        
        if not all_text.strip():
            log_error(logger, "文本内容为空", "Analyze")
            return {"data": []}
        
        # 加载停用词
        stopwords = load_stopwords()
        
        # 提取关键词
        keywords = extract_keywords(all_text, stopwords)
        
        if not keywords:
            log_error(logger, "未提取到关键词", "Analyze")
            return {"data": []}
        
        # 统计词频
        keyword_counts = Counter(keywords)
        
        # 获取top关键词，转换为要求的格式
        top_keywords = keyword_counts.most_common(20)
        data = [{"name": word, "value": count} for word, count in top_keywords]
        
        result = {"data": data}
        if data:
            result["echarts"] = build_bar_option(
                title=f"关键词 TOP20 · {channel_name}",
                data=data,
                orientation="horizontal",
                category_label="关键词",
                value_label="词频",
            )
        
        log_success(logger, f"keywords | {channel_name} 分析完成", "Analyze")
        return result
        
    except Exception as e:
        log_error(logger, f"关键词分析失败: {e}", "Analyze")
        return {"data": []}

def analyze_keywords_overall(df: pd.DataFrame, topic: str, logger=None) -> Dict[str, Any]:
    """
    分析总体关键词
    
    Args:
        df (pd.DataFrame): 数据框
        topic (str): 话题名称
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 关键词分析结果
    """
    return _analyze_keywords(df, topic, "总体", logger)

def analyze_keywords_by_channel(df: pd.DataFrame, topic: str, channel_name: str, logger=None) -> Dict[str, Any]:
    """
    分析渠道关键词
    
    Args:
        df (pd.DataFrame): 数据框
        topic (str): 话题名称
        channel_name (str): 渠道名称
        logger: 日志记录器
    
    Returns:
        Dict[str, Any]: 关键词分析结果
    """
    return _analyze_keywords(df, topic, channel_name, logger)
