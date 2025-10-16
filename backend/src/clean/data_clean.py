"""
数据清洗功能
"""
import re
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dateutil import parser
import pytz
from ..utils.setting.paths import bucket, ensure_bucket
from ..utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from ..utils.setting.settings import settings
from ..utils.io.excel import read_jsonl, write_jsonl


def parse_datetime(time_str: str, formats: List[str] = None) -> Optional[datetime]:
    """
    解析时间字符串
    
    Args:
        time_str (str): 时间字符串
        formats (List[str], optional): 时间格式列表
    
    Returns:
        Optional[datetime]: 解析后的时间对象
    """
    if pd.isna(time_str) or not time_str:
        return None
    
    if formats:
        for fmt in formats:
            try:
                return datetime.strptime(str(time_str), fmt)
            except ValueError:
                continue
    
    # 使用dateutil自动解析
    try:
        parsed = parser.parse(str(time_str))
        # 设置时区为上海
        tz = pytz.timezone('Asia/Shanghai')
        if parsed.tzinfo is None:
            parsed = tz.localize(parsed)
        return parsed
    except Exception:
        return None


def clean_text_whitespace(text: str) -> str:
    """
    仅规范空白与空行，不移除任何标点符号
    
    Args:
        text (str): 原始文本
    
    Returns:
        str: 仅做空白处理后的文本
    """
    if pd.isna(text) or not text:
        return ""
    text = str(text)
    # 将各种空白序列折叠为单个空格，并去首尾空白
    return re.sub(r'\s+', ' ', text).strip()


def normalize_region(region: str, fillna: str = "未知") -> str:
    """
    标准化地域信息（省级化）
    
    Args:
        region (str): 原始地域
        fillna (str, optional): 空值填充，默认"未知"
    
    Returns:
        str: 标准化后的地域
    """
    if pd.isna(region) or not region:
        return fillna
    
    region = str(region).strip()
    
    # 省级映射
    province_map = {
        '北京': '北京市', '天津': '天津市', '上海': '上海市', '重庆': '重庆市',
        '河北': '河北省', '山西': '山西省', '辽宁': '辽宁省', '吉林': '吉林省',
        '黑龙江': '黑龙江省', '江苏': '江苏省', '浙江': '浙江省', '安徽': '安徽省',
        '福建': '福建省', '江西': '江西省', '山东': '山东省', '河南': '河南省',
        '湖北': '湖北省', '湖南': '湖南省', '广东': '广东省', '海南': '海南省',
        '四川': '四川省', '贵州': '贵州省', '云南': '云南省', '陕西': '陕西省',
        '甘肃': '甘肃省', '青海': '青海省', '台湾': '台湾省', '内蒙古': '内蒙古自治区',
        '广西': '广西壮族自治区', '西藏': '西藏自治区', '宁夏': '宁夏回族自治区',
        '新疆': '新疆维吾尔自治区', '香港': '香港特别行政区', '澳门': '澳门特别行政区'
    }
    
    # 查找匹配的省份
    for short, full in province_map.items():
        if short in region or full in region:
            return full
    
    # 如果没有匹配到省份，返回原值或默认值
    return region if region else fillna


def run_clean(topic: str, date: str, logger=None) -> bool:
    """
    运行清洗流水线（直接读取 merge/<topic>/<date> 下各渠道 JSONL）
    
    清洗流程线：
    - 遍历 data/merge/<topic>/<date> 下每个渠道的 JSONL
    - 每表重编号：id = yyyymmdd + 序号（从1开始），整型
    - 按 channels.yaml.field_alias 将列名映射
    - 针对 content 去重，再基于 contents 再去重
    - 将 title、summary、ocr、content 合并为 contents（存在则拼接）
    - 保留列：id、contents、author、published_at、url、region、hit_words、polarity
    - 清洗 contents 文本；region 省级化；published_at 解析为 MySQL 格式
    - 保存到 data/clean/<topic>/<date>/<channel>.jsonl
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger(topic, date)

    log_module_start(logger, "Clean")

    merge_dir = bucket("merge", topic, date)
    clean_dir = ensure_bucket("clean", topic, date)

    channel_config = settings.get_channel_config()
    field_alias = channel_config.get('field_alias', {})
    region_config = channel_config.get('region', {})

    jsonl_files = sorted(merge_dir.glob("*.jsonl"))
    if not jsonl_files:
        log_error(logger, f"未在 {merge_dir} 找到任何渠道 JSONL 文件")
        return False

    date_digits = date.replace('-', '')
    total_rows = 0
    success_files = 0

    for file_path in jsonl_files:
        channel_name = file_path.stem
        try:
            df = read_jsonl(file_path)
            original_count = len(df)
        except Exception as e:
            log_error(logger, f"读取 {file_path.name} 失败：{e}", "Clean")
            continue

        if df.empty:
            log_error(logger, f"{file_path.name} 无数据，跳过", "Clean")
            continue

        # 列名映射
        rename_map: Dict[str, str] = {}
        for std_field, aliases in field_alias.items():
            for alias in aliases:
                if alias in df.columns:
                    rename_map[alias] = std_field
                    break
        if rename_map:
            df = df.rename(columns=rename_map)
        else:
            log_error(logger, "无列名映射", "Clean")

        # 内容去重（基于 content）
        if 'content' in df.columns:
            df = df.drop_duplicates(subset=['content'], keep='first')
        else:
            log_error(logger, "无content列，跳过内容去重", "Clean")

        # 合并文本 -> contents（仅空白清理，不去除标点；缺失填"未知"；带标签前缀）
        for col in ['title', 'summary', 'ocr', 'content']:
            if col in df.columns:
                df[col] = df[col].fillna("未知").astype(str)
        pieces = [df[col] for col in ['title', 'summary', 'ocr', 'content'] if col in df.columns]
        if pieces:
            def _merge_with_labels(row):
                """
                合并文本字段，添加标签前缀
                
                Args:
                    row (pd.Series): 数据行
                
                Returns:
                    str: 合并后的文本内容
                """
                parts = []
                if 'title' in row and str(row['title']).strip() != '未知':
                    parts.append(f"title: {clean_text_whitespace(row['title'])}")
                if 'summary' in row and str(row['summary']).strip() != '未知':
                    parts.append(f"summary: {clean_text_whitespace(row['summary'])}")
                if 'ocr' in row and str(row['ocr']).strip() != '未知':
                    parts.append(f"ocr: {clean_text_whitespace(row['ocr'])}")
                if 'content' in row and str(row['content']).strip() != '未知':
                    parts.append(f"content: {clean_text_whitespace(row['content'])}")
                return ' '.join(parts).strip() if parts else '未知'
            df['contents'] = df.apply(_merge_with_labels, axis=1)
        else:
            df['contents'] = "未知"

        # 仅规范空白（不去标点）
        df['contents'] = df['contents'].apply(clean_text_whitespace)

        # region 省级化
        fillna_region = region_config.get('fillna', '未知')
        if 'region' in df.columns:
            df['region'] = df['region'].apply(lambda x: normalize_region(x, fillna_region))
        else:
            df['region'] = fillna_region

        # 时间解析与格式化
        time_formats = ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d"]
        if 'published_at' in df.columns:
            df['published_at'] = df['published_at'].apply(lambda x: parse_datetime(x, time_formats))
            df['published_at'] = df['published_at'].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) and x is not None else None
            )
        else:
            df['published_at'] = None
            log_error(logger, "无published_at列，时间设为NULL", "Clean")

        # 发布平台（platform）：微博/微信固定；其他渠道优先用重命名后的标准列，其次按别名从原始列取
        if channel_name in ['微博', '微信']:
            df['platform'] = channel_name
        else:
            if 'platform' in df.columns:
                df['platform'] = df['platform'].astype(str).replace('', '未知').fillna('未知')
            else:
                platform_aliases = field_alias.get('platform', [])
                platform_col = next((a for a in platform_aliases if a in df.columns), None)
                if platform_col is not None:
                    df['platform'] = df[platform_col].astype(str).replace('', '未知').fillna('未知')
                else:
                    df['platform'] = '未知'
                    log_error(logger, "无platform信息，设为'未知'", "Clean")

        # 微博的 title 用 content 替代
        if channel_name == '微博' and 'content' in df.columns:
            df['title'] = df['content']

        # 补全并保留列（保留 title；缺失统一填充"未知"）
        keep_cols = ['id', 'title', 'contents', 'platform', 'author', 'published_at', 'url', 'region', 'hit_words', 'polarity']
        missing_cols = []
        for col in ['title', 'author', 'url', 'hit_words', 'polarity']:
            if col not in df.columns:
                df[col] = "未知"
                missing_cols.append(col)
            else:
                # 将空字符串/NaN 填充为 "未知"
                df[col] = df[col].replace('', '未知').fillna('未知')

        # 重编号（每表独立）
        df = df.reset_index(drop=True)
        df['id'] = df.index.map(lambda i: int(f"{date_digits}{i+1}"))

        # 基于 contents 再次去重
        df = df.drop_duplicates(subset=['contents'], keep='first')
        final_count = len(df)
        log_success(logger, f"清洗完成: {channel_name} {original_count} -> {final_count} 条", "Clean")

        df_out = df[[c for c in keep_cols]]

        out_file = clean_dir / f"{channel_name}.jsonl"
        try:
            write_jsonl(df_out, out_file)
            total_rows += len(df_out)
            success_files += 1
        except Exception as e:
            log_error(logger, f"保存 {out_file.name} 失败：{e}", "Clean")
            continue

    return success_files > 0
