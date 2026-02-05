#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
舆论流体动力学指标计算与热度预测模块
整合 ind_test.py 的所有功能

功能概述：
- 计算舆论场五维状态面板：流速(I)、粘度(C)、密度(D)、温度(T)、压力(S)
- 计算综合指标：涡度(Ω)、压强梯度(G)、雷诺数(Re)、热度(H)
- 基于舆论流体力学模型进行热度预测

数据要求：
- 文档位于 data/fetch 目录，包含 θ、published_at、author 等列
- 支持 CSV 文件（推荐，由 raw_data_cleaner 生成）和 Excel 文件
"""
import re
from pathlib import Path
from typing import Optional

# 导入系统的路径和日志工具
from ..utils.setting.paths import get_project_root, bucket, ensure_bucket
from ..utils.logging.logging import (
    setup_logger, log_success, log_error, log_module_start, log_save_success
)
import math
import os
import json
import random
import re
import asyncio
import argparse
import contextlib
import io
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

try:
    import networkx as nx  # 可选：用于 PageRank
except Exception:
    nx = None  # type: ignore

PROJECT_ROOT = get_project_root()

# 缺失值处理与 TRS API 相关能力已关闭，仅保留指标计算
mv_handler = None
TRS_API_AVAILABLE = False

# 路径变量已移除，由 run_fluid_analysis 函数传入

# 配置变量已移除，由 run_fluid_analysis 函数传入

# 平台权重映射
PLATFORM_WEIGHTS: Dict[str, float] = {
    "微信": 1.25,
    "微博": 1.25,
    "新闻app": 1,
    "新闻网站": 1,
    "视频": 0.75,
    "自媒体号": 0.6,
    "论坛": 0.8,
    "电子报": 1.2,
}
PLATFORM_KEYS = list(PLATFORM_WEIGHTS.keys())

TIME_CANDIDATES = ["IR_URLTIME", "published_at", "时间", "timestamp", "time", "date", "datetime"]

# 数据列名映射（从raw数据到标准格式）
COLUMN_MAPPING = {
    "SY_ABSTRACT": "contents",  # 内容摘要作为主要分析文本
    "IR_CHANNEL": "author",
    "IR_SITENAME": "platform",
    "IR_URLNAME": "title",
    "IR_URLTITLE": "title",  # 备用标题列
    "SY_KEYWORDS": "hit_words",  # 关键词
    "SY_MEDIA_AREA": "media_area",  # 地区信息
    "SY_MEDIA_RANK": "media_rank",  # 媒体等级（核心/一级/二级）
    "IR_COUNT1": "点赞量",
    "likecount": "点赞量",  # 兼容likecount列名
    "IR_COUNT2": "阅读量",
    "IR_COUNT3": "评论量",
    "IR_COUNT4": "转发量",
    "IR_URLTIME": "published_at",  # 时间列映射
}
EDGE_SOURCE_CANDIDATES = [
    "source_author", "src_author", "author", "user", "from_user",
]
EDGE_TARGET_CANDIDATES = [
    "target_author", "dst_author", "retweet_from", "reply_to", "in_reply_to",
    "引用作者", "被转发作者", "to_user",
]


def iter_data_files(root: Path) -> Iterable[Path]:
    """遍历目录中的所有数据文件（CSV和Excel）"""
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            # 支持CSV和Excel文件
            if (name.lower().endswith((".xlsx", ".xls", ".csv")) and 
                not name.startswith("~$")):
                yield Path(dirpath) / name


def iter_excel_files(root: Path) -> Iterable[Path]:
    """向后兼容：遍历所有数据文件"""
    return iter_data_files(root)


def detect_platform_from_name(filename: str) -> str:
    for key in PLATFORM_KEYS:
        if key in filename:
            return key
    return "未知平台"


def read_concat_sheets(path: Path) -> pd.DataFrame:
    """读取数据文件（支持CSV和Excel）"""
    frames: List[pd.DataFrame] = []
    
    # 根据文件扩展名选择读取方式
    if path.suffix.lower() == '.csv':
        # 尝试多种编码（优先使用中文常用编码：GBK系列）
        # 注意：如果文件有乱码，可能需要手动指定正确的编码
        encodings = ['gbk', 'gb18030', 'gb2312', 'utf-8-sig', 'utf-8', 'big5', 'latin-1', 'cp1252']
        df = None
        last_error = None
        
        for encoding in encodings:
            try:
                df = pd.read_csv(path, encoding=encoding)
                if df is not None and not df.empty:
                    print(f"    [成功] 使用编码 {encoding} 读取 {path.name}")
                    
                    # 验证并尝试修复关键列的乱码
                    if 'SY_MEDIA_RANK' in df.columns or 'media_rank' in df.columns:
                        rank_col = 'SY_MEDIA_RANK' if 'SY_MEDIA_RANK' in df.columns else 'media_rank'
                        sample_values = df[rank_col].dropna().astype(str).head(20)
                        # 检查是否包含预期的值（核心、一级、二级）
                        has_valid_values = any(val.strip() in ['核心', '一级', '二级'] for val in sample_values)
                        
                        if not has_valid_values and len(sample_values) > 0:
                            print(f"    [检测到乱码] {rank_col}列的值可能不是预期的格式，前5个值: {sample_values.head(5).tolist()}")
                            # 尝试修复：如果当前编码不对，尝试其他编码重新读取
                            if encoding in ['utf-8-sig', 'utf-8']:
                                # 如果用的是UTF-8但值不对，尝试用GBK重新读取
                                try:
                                    df_gbk = pd.read_csv(path, encoding='gbk')
                                    if df_gbk is not None and not df_gbk.empty:
                                        rank_col_gbk = 'SY_MEDIA_RANK' if 'SY_MEDIA_RANK' in df_gbk.columns else 'media_rank'
                                        if rank_col_gbk in df_gbk.columns:
                                            sample_gbk = df_gbk[rank_col_gbk].dropna().astype(str).head(20)
                                            has_valid_gbk = any(val.strip() in ['核心', '一级', '二级'] for val in sample_gbk)
                                            if has_valid_gbk:
                                                print(f"    [修复] 使用GBK编码重新读取，修复了乱码")
                                                df = df_gbk
                                                frames.append(df)
                                                break
                                except:
                                    pass
                            elif encoding in ['gbk', 'gb18030', 'gb2312']:
                                # 如果用的是GBK但值不对，尝试用UTF-8重新读取
                                try:
                                    df_utf8 = pd.read_csv(path, encoding='utf-8-sig')
                                    if df_utf8 is not None and not df_utf8.empty:
                                        rank_col_utf8 = 'SY_MEDIA_RANK' if 'SY_MEDIA_RANK' in df_utf8.columns else 'media_rank'
                                        if rank_col_utf8 in df_utf8.columns:
                                            sample_utf8 = df_utf8[rank_col_utf8].dropna().astype(str).head(20)
                                            has_valid_utf8 = any(val.strip() in ['核心', '一级', '二级'] for val in sample_utf8)
                                            if has_valid_utf8:
                                                print(f"    [修复] 使用UTF-8编码重新读取，修复了乱码")
                                                df = df_utf8
                                                frames.append(df)
                                                break
                                except:
                                    pass
                    
                    if df is not None and not df.empty:
                        frames.append(df)
                        break
            except UnicodeDecodeError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue
        
        # 如果所有编码都失败，尝试使用errors='replace'或'ignore'
        if df is None or df.empty:
            for encoding in ['gbk', 'gb18030', 'utf-8-sig']:
                try:
                    df = pd.read_csv(path, encoding=encoding, errors='replace')  # 替换无法解码的字符
                    if df is not None and not df.empty:
                        print(f"    [警告] 使用编码 {encoding} 读取 {path.name}（使用errors='replace'处理无法解码的字符）")
                        frames.append(df)
                        break
                except Exception:
                    continue
        
        if df is None or df.empty:
            print(f"  [错误] 读取CSV文件失败 {path.name}: 尝试了所有编码都失败")
            if last_error:
                print(f"    最后错误: {last_error}")
            return pd.DataFrame()  # 返回空DataFrame而不是None
    else:
        # 读取Excel文件
        try:
            with pd.ExcelFile(path) as xls:
                for sheet in xls.sheet_names or ["Sheet1"]:
                    try:
                        df = xls.parse(sheet)
                        # 只添加非空的DataFrame
                        if df is not None and not df.empty:
                            frames.append(df)
                    except Exception:
                        continue
        except Exception as e:
            print(f"  [警告] 读取Excel文件失败 {path.name}: {e}")
    
    if not frames:
        return pd.DataFrame()
    
    # 如果只有一个DataFrame，直接使用
    if len(frames) == 1:
        result = frames[0]
    else:
        # 合并多个sheet
        all_cols = set()
        for df in frames:
            all_cols.update(df.columns)
        aligned = [df.reindex(columns=sorted(all_cols)) for df in frames]
        result = pd.concat(aligned, ignore_index=True)
    
    # 过滤掉完全为空的行
    if not result.empty:
        result = result.dropna(how='all')

    # 应用列名映射（将raw数据格式转换为标准格式）
    if not result.empty and COLUMN_MAPPING:
        for old_col, new_col in COLUMN_MAPPING.items():
            if old_col in result.columns and new_col not in result.columns:
                result.rename(columns={old_col: new_col}, inplace=True)

    return result
    
        
def generate_random_data(num_posts: int = 100, hours: int = 24) -> List[pd.DataFrame]:
    """生成随机数据用于测试"""
    print(f"生成随机数据: {num_posts} 条帖子，时间跨度 {hours} 小时")
    
    np.random.seed(42)
    random.seed(42)
    
    platforms = ["微信", "微博", "新闻app", "新闻网站", "视频", "自媒体号", "论坛"]
    
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    frames = []
    
    for platform in platforms:
        platform_posts = max(1, int(num_posts * np.random.uniform(0.1, 0.3)))
        
        data = {
            'id': [f"{platform}_{i:04d}" for i in range(platform_posts)],
            'title': [f"随机标题_{i}" for i in range(platform_posts)],
            'contents': [f"这是第{i}条随机内容" for i in range(platform_posts)],
            'platform': [platform] * platform_posts,
            'author': [f"用户_{random.randint(1, 50)}" for _ in range(platform_posts)],
            'published_at': [
                start_time + timedelta(
                    seconds=random.randint(0, int(hours * 3600))
                ) for _ in range(platform_posts)
            ],
            'url': [f"https://example.com/{platform}/{i}" for i in range(platform_posts)],
            'region': [random.choice(["北京", "上海", "广州", "深圳", "其他"]) for _ in range(platform_posts)],
            'hit_words': [random.choice(["控烟", "吸烟", "健康", "政策"]) for _ in range(platform_posts)],
            'polarity': [random.choice([-1, 0, 1]) for _ in range(platform_posts)],
            'θ': [np.random.normal(0, 0.5) for _ in range(platform_posts)],
            '点赞量': [random.randint(0, 1000) for _ in range(platform_posts)],
            '阅读量': [random.randint(10, 10000) for _ in range(platform_posts)],
            '评论量': [random.randint(0, 500) for _ in range(platform_posts)],
            '收藏量': [random.randint(0, 200) for _ in range(platform_posts)],
            '转发量': [random.randint(0, 300) for _ in range(platform_posts)]
        }
        
        df = pd.DataFrame(data)
        frames.append(df)
    
    print(f"生成了 {len(frames)} 个平台的数据，总记录数: {sum(len(df) for df in frames)}")
    return frames


def load_theta_from_json() -> Dict:
    """从合并的θ值JSON文件加载数据"""
    theta_file = PROJECT_ROOT / "fluid" / "theta_values.json"
    
    if not theta_file.exists():
        print(f"[警告] 未找到θ值文件: {theta_file}")
        return {}
    
    try:
        with open(theta_file, 'r', encoding='utf-8') as f:
            theta_data = json.load(f)
        print(f"[OK] 从θ值文件加载数据: {theta_file.name}")
        print(f"  - 时间窗口数: {theta_data['metadata']['total_windows']}")
        print(f"  - 总记录数: {theta_data['metadata']['total_records']}")
        
        # 兼容新格式：theta_values → windows，计算theta_mean
        if 'theta_values' in theta_data and 'windows' not in theta_data:
            print(f"  [转换] 检测到新格式theta_values，转换为windows格式")
            windows = {}
            for window_key, theta_list in theta_data['theta_values'].items():
                # 计算该窗口的θ均值
                if theta_list:
                    theta_mean = sum(item['theta'] for item in theta_list) / len(theta_list)
                else:
                    theta_mean = 0.0
                windows[window_key] = {
                    'theta_mean': theta_mean,
                    'theta_list': theta_list  # 保留原始列表供详细分析使用
                }
            theta_data['windows'] = windows
            print(f"  [OK] 已转换 {len(windows)} 个时间窗口")
        
        return theta_data
    except Exception as e:
        print(f"[警告] 读取θ值文件失败: {e}")
        import traceback
        traceback.print_exc()
        return {}


def read_all_docs(root: Path, target_file: Optional[str] = None) -> Tuple[List[Path], List[pd.DataFrame]]:
    """读取所有文档，处理空值并直接从polarity列生成θ值"""
    paths: List[Path] = []
    frames: List[pd.DataFrame] = []
    
    print(f"[OK] 使用polarity列直接生成θ值（无需theta_values.json文件）")
    
    if root.exists():
        # 先扫描所有文件，显示统计信息
        all_files = list(iter_data_files(root))
        
        # 如果指定了target_file，只处理该文件
        if target_file is not None:
            target_path = root / target_file
            if target_path.exists():
                all_files = [target_path]
                print(f"\n[指定文件] 只分析: {target_file}")
            else:
                print(f"\n[错误] 指定的文件不存在: {target_file}")
                print(f"  查找路径: {target_path}")
                raise FileNotFoundError(f"未找到指定文件: {target_file}")
        
        if all_files:
            csv_files = [f for f in all_files if f.suffix.lower() == '.csv']
            excel_files = [f for f in all_files if f.suffix.lower() in ['.xlsx', '.xls']]
            print(f"\n[OK] 在 {root} 中找到数据文件:")
            print(f"  - CSV 文件: {len(csv_files)} 个")
            print(f"  - Excel 文件: {len(excel_files)} 个")
            print(f"  - 总计: {len(all_files)} 个文件")
        else:
            print(f"\n[警告] 在 {root} 中未找到任何数据文件（CSV或Excel）")
        
        # 使用过滤后的文件列表
        for f in all_files:
            paths.append(f)
            print(f"\n[调试] 正在处理文件: {f.name} ({f.suffix})")
            df = read_concat_sheets(f)
            # 只保留非空DataFrame
            if df is not None and not df.empty:
                print(f"  - DataFrame行数: {len(df)}")
                print(f"  - DataFrame列: {list(df.columns)[:5]}...")
                
                # 在添加到frames之前，检查关键列
                print(f"  [最终检查] 准备添加 {f.name} 到frames...")
                if 'θ' in df.columns:
                    theta_count = df['θ'].notna().sum()
                    theta_unique = df['θ'].nunique()
                    print(f"    θ列: 非空={theta_count}/{len(df)}, 去重={theta_unique}, 范围=[{df['θ'].min():.2f}, {df['θ'].max():.2f}]")
                else:
                    print(f"    [错误] 缺少θ列！")
                
                if 'author' in df.columns:
                    author_unique = df['author'].nunique()
                    print(f"    author列: 去重={author_unique}/{len(df)}, 前3个={df['author'].unique()[:3].tolist()}")
                else:
                    print(f"    [错误] 缺少author列！")
                    
                frames.append(df)
    
    if not frames:
        raise ValueError(f"数据目录 {root} 中没有找到有效数据，请检查数据文件")
    total_posts = sum(len(df) for df in frames)

    if not frames:
        print("警告: 没有找到任何数据文件")
        return paths, frames

    # 统一列名（将原始列名映射为标准列名）
    for df in frames:
        for old_col, new_col in COLUMN_MAPPING.items():
            if old_col in df.columns and new_col not in df.columns:
                if df[old_col].notna().any():  # 只有当该列有非空值时才重命名
                    df.rename(columns={old_col: new_col}, inplace=True)
    
    # 应用缺失值处理（禁用默认值填充）
    if mv_handler is not None:
        print("[OK] 应用缺失值处理...")
        for i, df in enumerate(frames):
            print(f"  [处理前] 文件{i+1}: θ列存在={('θ' in df.columns)}, author去重={df['author'].nunique() if 'author' in df.columns else 0}")
            try:
                frames[i] = mv_handler.fill_missing_values(df, logger=None)
                print(f"  [处理后] 文件{i+1}: θ列存在={('θ' in frames[i].columns)}, author去重={frames[i]['author'].nunique() if 'author' in frames[i].columns else 0}")
            except Exception as e:
                print(f"  [警告] 缺失值处理失败（文件{i+1}）: {e}")
        print(f"  [OK] 缺失值处理完成")
    else:
        print("[警告] 缺失值处理器未初始化，跳过缺失值处理")

    # 直接从polarity列生成θ值（主要方案）
    print(f"\n[生成θ值] 从polarity列直接生成θ值...")
    polarity_found = any("polarity" in df.columns for df in frames)
    emotional_found = any("SY_EMOTIONAL_DIGIT" in df.columns for df in frames)
    
    if polarity_found:
        print(f"  [OK] 检测到polarity列，将用于生成θ值")
    elif emotional_found:
        print(f"  [OK] 检测到SY_EMOTIONAL_DIGIT列，将用于生成θ值")
    else:
        print(f"  [警告] 未找到polarity或SY_EMOTIONAL_DIGIT列，将使用随机θ值")

    # 确保所有frames都有θ列
    for df in frames:
        if "θ" not in df.columns:
            # 方案1: 从polarity生成θ（主要方案）
            if "polarity" in df.columns:
                # 处理文本格式的polarity（如"正面"、"负面"、"中性"）
                polarity_str = df["polarity"].astype(str).str.strip()
                
                # 文本情感值映射
                emotion_map = {
                    '正面': 1.0,
                    '负面': -1.0,
                    '中性': 0.0,
                    '积极': 1.0,
                    '消极': -1.0,
                    'positive': 1.0,
                    'negative': -1.0,
                    'neutral': 0.0,
                }
                
                # 先尝试文本映射
                polarity_numeric = polarity_str.map(emotion_map)
                
                # 如果映射后仍有NaN，尝试直接转换为数值
                if polarity_numeric.isna().any():
                    polarity_numeric = polarity_numeric.fillna(
                        pd.to_numeric(df["polarity"], errors="coerce")
                    )
                
                # 填充剩余的NaN为0
                polarity_values = polarity_numeric.fillna(0)
                
                # 归一化到[-1, 1]范围（如果polarity已经是[-1, 1]范围，则直接使用；如果是[0, 1]或[1, -1]，需要调整）
                # 假设polarity可能是：-1/0/1 或 1/0/-1 或 0/1/-1，统一映射到[-1, 1]
                # 如果值在[-1, 1]范围内，直接使用；否则可能需要除以最大值
                max_abs = polarity_values.abs().max()
                if max_abs > 1.0 and max_abs > 0:
                    polarity_values = polarity_values / max_abs
                
                # 生成θ值：直接使用polarity值（已在[-1, 1]范围），添加小的随机噪声
                df["θ"] = polarity_values + np.random.normal(0, 0.05, len(df))
                text_mapped = polarity_str.isin(emotion_map.keys()).sum()
                print(f"  [OK] 从polarity列生成θ值: 文本映射={text_mapped}/{len(df)}, 数值范围=[{df['θ'].min():.3f}, {df['θ'].max():.3f}]")
            # 方案2: 从SY_EMOTIONAL_DIGIT生成θ
            elif "SY_EMOTIONAL_DIGIT" in df.columns:
                emotional_values = pd.to_numeric(df["SY_EMOTIONAL_DIGIT"], errors="coerce").fillna(50)
                df["θ"] = (emotional_values - 50.0) / 50.0 + np.random.normal(0, 0.05, len(df))
                print(f"  [OK] 从SY_EMOTIONAL_DIGIT列生成θ值: 范围=[{df['θ'].min():.3f}, {df['θ'].max():.3f}]")
            # 方案3: 使用随机值
            else:
                df["θ"] = np.random.normal(0, 0.3, len(df))
                print(f"  [警告] 无情感列，使用随机θ值")
    
    # 填充缺失列（为所有DataFrame添加必需的列）
    for i, df in enumerate(frames):
        # 为文本列设置默认值
        if 'author' not in df.columns:
            df['author'] = '未知用户'
        if 'platform' not in df.columns:
            # 尝试从文件名推断
            if i < len(paths):
                inferred_platform = detect_platform_from_name(paths[i].name)
                df['platform'] = inferred_platform
            else:
                df['platform'] = '未知平台'
        
        # 为数值列设置默认值
        for col in ['点赞量', '阅读量', '评论量', '转发量']:
            if col not in df.columns:
                df[col] = 0
        
        # 如果可选，使用缺失值处理器填充其他缺失值
        if mv_handler is not None:
            mv_handler.fill_missing_values(df, logger=None)
    
    # 验证所有frames都有θ列
    has_theta = all("θ" in df.columns for df in frames)
    if not has_theta:
        raise ValueError("未能为所有数据生成θ列，请检查数据文件")

    print(f"成功读取 {len(paths)} 个文件，共 {total_posts} 条记录")
    return paths, frames


def filter_recent_3hours_data(frames: List[pd.DataFrame]) -> List[pd.DataFrame]:
    """过滤最近24小时的数据（基于数据中的最新时间）"""
    filtered_frames = []
    all_times = []
    
    for df in frames:
        if df is None or df.empty:
            continue
        
        time_col = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        if time_col is None:
            continue
        
        try:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            valid_times = df[time_col].dropna()
            if not valid_times.empty:
                all_times.extend(valid_times.tolist())
        except Exception:
            continue
    
    if not all_times:
        print("警告: 没有找到有效的时间数据，使用全部数据")
        return frames
    
    latest_time = max(all_times)
    three_hours_ago = latest_time - timedelta(hours=24)  # 修改为24小时
    
    print(f"数据时间范围: {three_hours_ago} 到 {latest_time}")
    
    for df in frames:
        if df is None or df.empty:
            continue
        
        time_col = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        if time_col is None:
            continue
        
        try:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            mask = df[time_col] >= three_hours_ago
            filtered_df = df[mask].copy()
            
            if not filtered_df.empty:
                filtered_frames.append(filtered_df)
                
        except Exception as e:
            print(f"过滤数据时出错: {e}")
            continue
    
    if not filtered_frames:
        print("警告: 过滤后没有数据，使用全部数据")
        return frames
    
    print(f"过滤后数据量: {sum(len(df) for df in filtered_frames)} 条记录")
    return filtered_frames


def build_doc_posts_3hours(root: Path) -> List[Tuple[str, int]]:
    """构建最近24小时内的文档帖子数"""
    result = []
    
    all_times = []
    for f in iter_excel_files(root):
        df = read_concat_sheets(f)
        if df is None or df.empty:
            continue
        
        time_col = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        if time_col is not None:
            try:
                df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
                valid_times = df[time_col].dropna()
                if not valid_times.empty:
                    all_times.extend(valid_times.tolist())
            except Exception:
                continue
    
    if not all_times:
        return result
    
    latest_time = max(all_times)
    three_hours_ago = latest_time - timedelta(hours=24)  # 修改为24小时
    
    for f in iter_excel_files(root):
        platform = detect_platform_from_name(f.name)
        df = read_concat_sheets(f)
        if df is None or df.empty:
            continue
        
        time_col = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        if time_col is not None:
            try:
                df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
                mask = df[time_col] >= three_hours_ago
                df = df[mask]
            except Exception:
                continue
        
        posts = int(len(df))
        if posts > 0:
            result.append((platform, posts))
    
    return result


# ——————————— I （全局信息扩散速度/流速） ———————————

def compute_global_I(frames: List[pd.DataFrame]) -> Tuple[int, float, float]:
    """返回 (全部帖子数, I值 帖子/小时, 时间跨度 小时)。"""
    times: List[pd.Series] = []
    total_posts = 0
    for df in frames:
        if df is None or df.empty:
            continue
        total_posts += len(df)
        tcol = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        if tcol is None:
            continue
        ts = pd.to_datetime(df[tcol], errors="coerce").dropna()
        if not ts.empty:
            times.append(ts)
    if total_posts == 0 or not times:
        return 0, float("nan"), float("nan")
    all_ts = pd.concat(times)
    if all_ts.empty:
        return total_posts, float("nan"), float("nan")
    t_min = all_ts.min()
    t_max = all_ts.max()
    # 计算实际的时间跨度（小时）
    delta_seconds = (t_max - t_min).total_seconds()
    
    # 如果时间跨度太小（所有帖子时间戳几乎相同），使用窗口大小（3小时）作为默认值
    if delta_seconds < 60:  # 小于1分钟
        delta_hours = 3.0  # 使用标准时间窗口大小
    else:
        delta_hours = delta_seconds / 3600.0
    
    I_val = float(total_posts / delta_hours)
    return int(total_posts), I_val, float(delta_hours)


# ——————————— Ω （全局情感波动/涡度） ———————————

def compute_global_Omega(frames: List[pd.DataFrame]) -> Tuple[int, float, float, float]:
    """计算舆论场的情感方差（Ω²）与标准差（Ω）"""
    thetas: List[float] = []
    
    for df in frames:
        if df is None or df.empty:
            continue
        if "θ" not in df.columns:
            continue
        s = pd.to_numeric(df["θ"], errors="coerce").dropna()
        if s.empty:
            continue
        thetas.extend(s.astype(float).tolist())

    N = len(thetas)
    if N == 0:
        return 0, float("nan"), float("nan"), float("nan")

    theta_bar = sum(thetas) / N
    Omega2 = sum((t - theta_bar) ** 2 for t in thetas) / N
    Omega = math.sqrt(Omega2)
    return N, Omega2, Omega, theta_bar
   # 返回：(有效 θ 样本数量, 情感方差, 情感标准差, 平均情感值)

# ——————————— G （全局关键用户差异/压强梯度，PageRank优先） ———————————

def identify_graph_edges(df: pd.DataFrame) -> Optional[List[Tuple[str, str]]]:
    cols = set(c.lower() for c in df.columns)
    name_map = {c.lower(): c for c in df.columns}
    src_col = next((name_map[c] for c in (c.lower() for c in EDGE_SOURCE_CANDIDATES) if c in cols), None)
    tgt_col = next((name_map[c] for c in (c.lower() for c in EDGE_TARGET_CANDIDATES) if c in cols), None)
    if src_col is None or tgt_col is None:
        return None
    s = df[[src_col, tgt_col]].dropna()
    if s.empty:
        return None
    edges: List[Tuple[str, str]] = []
    for a, b in s.itertuples(index=False):
        sa = str(a).strip()
        sb = str(b).strip()
        if sa and sb and sa != sb:
            edges.append((sa, sb))
    return edges or None


def pagerank_key_users(frames: List[pd.DataFrame]) -> Optional[set]:
    if nx is None:
        return None
    edges_all: List[Tuple[str, str]] = []
    for df in frames:
        if df is None or df.empty:
            continue
        edges = identify_graph_edges(df)
        if edges:
            edges_all.extend(edges)
    if not edges_all:
        return None
    try:
        Gd = nx.DiGraph()
        Gd.add_edges_from(edges_all)
        pr = nx.pagerank(Gd, alpha=0.85, max_iter=100)
        if not pr:
            return None
        scores = pd.Series(pr).sort_values(ascending=False)
        k = max(1, int(math.ceil(len(scores) * 0.05)))
        return set(scores.index[:k])
    except Exception:
        return None


def compute_global_G(frames: List[pd.DataFrame]) -> float:
    """
    计算压强梯度G（关键用户与其他用户的态度差异）
    强制使用备用方案：使用点赞量识别关键用户（不再使用媒体等级）
    - 点赞量 >= 80分位数 = 关键用户
    - 点赞量 < 80分位数 = 其他用户
    """
    thetas_key: List[float] = []
    thetas_other: List[float] = []
    
    # 强制使用备用方案（点赞量）
    used_fallback = False
    # 用于控制日志输出，避免每个窗口都输出
    if not hasattr(compute_global_G, '_first_window_logged'):
        compute_global_G._first_window_logged = False
        compute_global_G._method_logged = False
        compute_global_G._calc_logged = False
    
    for df in frames:
        if df is None or df.empty:
            continue
            
        if "θ" not in df.columns:
            print(f"警告: 数据框中没有找到 'θ' 列，跳过G计算")
            continue
            
        theta = pd.to_numeric(df["θ"], errors="coerce")
        
        # 强制使用备用方案：使用点赞量识别关键用户
        # 支持多种列名：点赞量、likecount、IR_COUNT1
        likes_col = None
        for col_name in ["点赞量", "likecount", "IR_COUNT1"]:
            if col_name in df.columns:
                likes_col = col_name
                break
        
        if likes_col:
            vals = pd.to_numeric(df[likes_col], errors="coerce")
            q80 = vals.quantile(0.80)
            mask = vals >= q80
            
            # 统计分组情况
            key_count = mask.sum()
            other_count = (~mask).sum()
            total_count = len(df)
            
            # 减少G值计算的详细输出，只在第一个窗口或异常情况输出
            if not hasattr(compute_global_G, '_first_window_logged'):
                print(f"    [G值计算] 使用列'{likes_col}', 点赞量80分位数={q80:.2f}, 关键用户={key_count}, 其他用户={other_count}")
                compute_global_G._first_window_logged = True
            
            thetas_key.extend(theta[mask].dropna().tolist())
            thetas_other.extend(theta[~mask].dropna().tolist())
            used_fallback = True
        else:
            print(f"警告: 没有找到点赞量列（已检查: 点赞量、likecount、IR_COUNT1），跳过此DataFrame")
            print(f"    可用列: {list(df.columns)[:10]}")
            continue
    
    # 只在第一次或异常情况输出识别方式
    if used_fallback and not hasattr(compute_global_G, '_method_logged'):
        print(f"⚠ [G值计算] 强制使用点赞量80分位数作为备用方案（已禁用媒体等级识别）")
        compute_global_G._method_logged = True
    
    # 只在数据不足时输出警告
    if len(thetas_key) == 0 or len(thetas_other) == 0:
        print(f"[警告] G值计算数据不足: 关键用户θ样本数={len(thetas_key)}, 其他用户θ样本数={len(thetas_other)}")
    
    # 数据不足时返回None，由调用者决定如何处理
    if not thetas_key or not thetas_other:
        print(f"[警告] 数据分组不足（关键用户={len(thetas_key)}, 其他用户={len(thetas_other)}），返回None")
        return None
    
    key_mean = float(np.mean(thetas_key))
    other_mean = float(np.mean(thetas_other))
    G_val = abs(key_mean - other_mean)
    
    # 只在第一个窗口或G值异常时输出详细计算信息
    if not hasattr(compute_global_G, '_calc_logged') or G_val > 0.5:
        print(f"  [G值] 关键用户θ均值={key_mean:.4f}, 其他用户θ均值={other_mean:.4f}, G={G_val:.4f}")
        compute_global_G._calc_logged = True
    
    return G_val


# ——————————— C （全局平台粘性/粘度） ———————————

def build_doc_posts(root: Path) -> List[Tuple[str, int]]:
    """返回 [(platform, s_i)]，其中 s_i 为单个文档的帖子数。"""
    result: List[Tuple[str, int]] = []
    for f in iter_excel_files(root):
        platform = detect_platform_from_name(f.name)
        df = read_concat_sheets(f)
        posts = int(len(df))
        result.append((platform, posts))
    return result


def compute_global_C_doc(posts_by_doc: List[Tuple[str, int]]) -> Tuple[int, float]:
    """C = Σ_doc w_i*(s_i/S)^2；S 为所有文档帖子总数，s_i 为单文档帖子数。返回 (S, C)。"""
    if not posts_by_doc:
        return 0, float("nan")
    S = int(sum(p for _, p in posts_by_doc))
    if S == 0:
        return 0, float("nan")
    total = 0.0
    for platform, s_i in posts_by_doc:
        w_i = PLATFORM_WEIGHTS.get(platform, 1.0)
        total += w_i * (float(s_i) / float(S)) ** 2
    return S, float(total)


# ——————————— D （全局参与用户密度） ———————————

def compute_global_D(frames: List[pd.DataFrame]) -> Tuple[int, int, float]:
    authors_all: List[str] = []
    for df in frames:
        if df is None or df.empty or "author" not in df.columns:
            continue
        authors_all.extend(df["author"].dropna().astype(str).tolist())
    total = len(authors_all)
    if total == 0:
        return 0, 0, float("nan")
    unique = len(set(authors_all))
    return unique, total, float(unique) / float(total)


# ——————————— T（温度/整体情感倾向） ———————————

def compute_global_T(mean_theta: float) -> float:
    """
    计算舆论温度T（整体情感倾向）
    基于θ的均值，归一化到[0, 1]区间
    θ实际范围通常在[-1, 1]，映射到[0, 1]
    """
    # 检查θ是否超出合理范围，如果超出则按实际情况处理
    if abs(mean_theta) > 3:  # 可能是[-3, 3]范围（随机生成的情况）
        normalized = (mean_theta + 3) / 6.0  # 映射到[0, 1]
    else:  # 标准情况 [-1, 1]
        normalized = (mean_theta + 1) / 2.0  # 映射到[0, 1]
    
    normalized = max(0.0, min(1.0, normalized))  # 确保在[0, 1]范围内
    return normalized


# ——————————— S（外部压力/敏感度） ———————————

def compute_global_S(Omega: float, G: float, C: float) -> float:
    """
    计算外部压力S（社会敏感性与外部干预强度）
    修复：综合极化、影响力和平台因素，不仅依赖Omega
    
    S = 极化压力 + 影响力压力 + 平台集中压力
    """
    # 1. 极化压力（Omega越大，观点对立越强，外部干预压力越大）
    polarization_pressure = 2.0 * Omega if not np.isnan(Omega) else 0.0
    
    # 2. 影响力压力（G越大，意见领袖影响力强，外部关注压力大）
    influence_pressure = 1.5 * G if G is not None and not np.isnan(G) else 0.0
    
    # 3. 平台集中压力（C越大，信息越集中，外部干预影响越大）
    platform_pressure = 1.0 * C if not np.isnan(C) else 0.0
    
    # 综合压力（多维度加权求和）
    total_pressure = polarization_pressure + influence_pressure + platform_pressure
    
    return total_pressure


# ——————————— Re（雷诺数） ———————————

def compute_reynolds_number(I: float, unique_authors: int, C: float, D: float) -> float:
    """
    计算舆论雷诺数 Re_opinion（基于舆论流体力学模型）
    公式: Re_opinion = (ρ_info * v_diff * L_net) / μ_resis
    """
    rho_info = max(I / 100.0, 1e-6)
    v_diff = max(I, 1e-6)
    L_net = math.sqrt(unique_authors) if unique_authors > 0 else 1.0
    mu_resis = 0.6 * (1 - C) + 0.4 * (1 - D)
    
    if mu_resis > 0:
        reynolds = (rho_info * v_diff * L_net) / mu_resis
    else:
        reynolds = float('inf')
    
    return reynolds


def get_flow_state(reynolds: float) -> str:
    """根据雷诺数判断流态"""
    if reynolds < 2000.0:
        return "层流"
    elif reynolds <= 4000.0:
        return "过渡"
    else:
        return "湍流"


# ——————————— H（热度） ———————————

def compute_heat(
    I: float, Omega: float, G: float, C: float, D: float,
    h: int,
    alpha: float = 1.0, beta: float = 1.0, eta: float = 1.0,
    delta: float = 1.0, epsilon: float = 0.1, gamma: float = 1.0
) -> float:
    """
    计算舆论热度H（基于舆论流体力学模型）
    """
    I_val = max(I, 1e-6)
    Omega_val = Omega if Omega is not None and not np.isnan(Omega) else 0.0
    G_val = G if G is not None and not np.isnan(G) else 0.0
    C_val = C if C is not None and not np.isnan(C) else 0.0
    D_val = D if D is not None and not np.isnan(D) else 0.0
    
    # 计算热度变化率
    info_diffusion_term = alpha * math.log(I_val)
    attitude_vorticity_term = beta * (Omega_val ** 2)
    influence_term = eta * G_val
    user_density_term = delta * math.sqrt(D_val + epsilon) / math.exp(1 - C_val)
    time_period_term = gamma * math.sin(2 * math.pi * h / 24)
    
    dH_dt = info_diffusion_term + attitude_vorticity_term + influence_term + user_density_term + time_period_term
    
    return dH_dt


# 按论文严格公式计算热度变化率：
# dH/dt = α⋅ln(dI/dt) + β⋅Ω^2 + (η⋅G + ζ⋅E⋅e^(−t/τ)) + δ⋅√(D+ε)/e^(1−C) + γ⋅sin(2πh/24)
def compute_heat_rate_theoretical(
    dI_dt: float,
    Omega: float,
    G: float,
    C: float,
    D: float,
    E: float,
    h: int,
    t_hours: float,
    alpha: float = 2.0,      # 信息生成效率系数（增大以体现信息流速的重要性）
    beta: float = 3.0,       # 极化效应强度系数（增大以体现极化的影响）
    eta: float = 2.5,        # 社会压力响应系数（增大以体现影响力梯度的作用）
    zeta: float = 1.5,       # 事件影响衰减系数
    delta: float = 1.0,      # 平台耗散系数（会乘以负号）
    epsilon: float = 0.01,   # 密度修正参数（避免D=0时出现问题）
    gamma: float = 0.5,      # 周期波动幅度系数（降低周期项的影响）
    tau: float = 24.0,       # 事件影响力衰减时间常数（小时）
) -> float:
    """
    根据舆论流体力学理论计算热度变化率 dH/dt
    
    公式（舆论流体理论.txt第126行）：
    dH/dt = α·ln(dI/dt) + β·Ω² + (η·G + ζ·E·e^(-t/τ)) - δ·√(D+ε)/e^(1-C) + γ·sin(2πh/24)
    
    注意：耗散项前有负号（理论第119行）
    """
    # 处理NaN值和None值
    Omega_val = Omega if Omega is not None and not np.isnan(Omega) else 0.0
    G_val = G if G is not None and not np.isnan(G) else 0.0
    C_val = max(0.0, min(1.0, C if C is not None and not np.isnan(C) else 0.5))  # 限制在[0,1]
    D_val = max(0.0, min(1.0, D if D is not None and not np.isnan(D) else 0.5))  # 限制在[0,1]
    E_val = E if E is not None and not np.isnan(E) else 0.0
    t_val = max(t_hours, 0.0)

    # 1. 信息生成项：α·ln(dI/dt)
    # 关键修复：处理dI/dt <= 0的情况
    if dI_dt > 0:
        # 正常情况：信息量增长
        info_term = alpha * math.log(dI_dt + 1.0)  # 加1避免ln(很小的数)导致大负值
    else:
        # 信息量下降或不变：使用负的对数衰减
        # 当dI/dt < 0时，表示信息量在减少，热度应该下降
        info_term = alpha * math.log(abs(dI_dt) + 1.0) * (-0.5)  # 负增长时热度降低
    
    # 2. 观点对流项（极化效应）：β·Ω²
    vorticity_term = beta * (Omega_val ** 2)
    
    # 3. 舆论场压力项：η·G + ζ·E·e^(-t/τ)
    # 内部压力（影响力梯度）+ 外部事件影响（随时间衰减）
    internal_pressure = eta * G_val
    external_event_impact = zeta * abs(E_val) * math.exp(-t_val / max(tau, 1e-9))
    pressure_term = internal_pressure + external_event_impact
    
    # 4. 平台耗散项（传播阻力）：-δ·√(D+ε)/e^(1-C)
    # 注意：根据理论第119行，这一项前面有负号
    # 用户密度越高、平台越分散，耗散越大
    numerator = math.sqrt(D_val + epsilon)
    denominator = math.exp(1 - C_val)  # C越大（越集中），分母越小，耗散越大
    dissipation_term = -delta * numerator / max(denominator, 1e-9)  # 负号表示耗散
    
    # 5. 周期调节项（昼夜节律）：γ·sin(2πh/24)
    period_term = gamma * math.sin(2 * math.pi * (h % 24) / 24)

    # 总热度变化率
    dH_dt = info_term + vorticity_term + pressure_term + dissipation_term + period_term
    
    return dH_dt


# ——————————— 预测热度 ———————————

def predict_future_metrics(current_result: Dict, hours_ahead: int = 1, tau: float = 24.0) -> Dict:
    """
    预测未来指标
    
    Args:
        current_result: 当前窗口的结果字典
        hours_ahead: 预测未来多少小时
        tau: 事件影响力衰减时间常数
        
    Returns:
        Dict: 预测的指标字典
    """
    I_raw = current_result.get("流速(I)_原始", current_result.get("I_raw", 1.0))
    Omega = current_result.get("涡度(Ω)", 0.0)
    G = current_result.get("压强梯度(G)", 0.0)
    C = current_result.get("粘度(C)", 0.0)
    D = current_result.get("密度(D)", 0.0)
    h = current_result.get("h", datetime.now().hour)
    
    # 预测未来指标（基础：小幅季节性）
    predicted_I = I_raw * (1 + 0.05 * math.sin(2 * math.pi * hours_ahead / 24))
    predicted_Omega = Omega
    predicted_G = G
    predicted_C = C
    predicted_D = D
    predicted_h = (h + hours_ahead) % 24
    
    return {
        "I": predicted_I,
        "Omega": predicted_Omega,
        "G": predicted_G,
        "C": predicted_C,
        "D": predicted_D,
        "h": predicted_h,
    }

def calculate_predicted_heat(predicted_metrics: Dict, dI_dt: float, E: float = 0.0, t_hours: float = 0.0,
                             alpha: float = 1.5, beta: float = 2.0, eta: float = 1.8, 
                             zeta: float = 1.2, delta: float = 0.8, epsilon: float = 0.01, 
                             gamma: float = 0.3, tau: float = 24.0) -> float:
    """
    根据舆论流体理论计算预测热度（与真实热度计算不同）
    
    理论公式（第179-180行）：
    H_pred = α·ln(dI/dt)+ β·Ω² + η·G + δ·e^(1-C)/√(D+ε) + ζ·E·e^(-t/τ) + γ·sin(2πh/24)
    
    注意：预测公式耗散项为正，且分子分母与真实计算相反，这使预测更平滑
    
    Args:
        predicted_metrics: 预测的指标字典
        dI_dt: 信息量变化率
        E: 事件影响力
        t_hours: 距离事件发生的小时数
        其他参数: 模型系数
        
    Returns:
        float: 预测的热度变化率 H_pred
    """
    I = max(predicted_metrics.get("I", 1e-6), 1e-6)
    Omega = predicted_metrics.get("Omega", 0.0) if not np.isnan(predicted_metrics.get("Omega", 0.0)) else 0.0
    G = predicted_metrics.get("G", 0.0) if not np.isnan(predicted_metrics.get("G", 0.0)) else 0.0
    C = max(0.0, min(1.0, predicted_metrics.get("C", 0.5)))  # 限制在[0,1]
    D = max(0.0, min(1.0, predicted_metrics.get("D", 0.5)))  # 限制在[0,1]
    h = predicted_metrics.get("h", 0) % 24
    
    # 1. 信息生成项：α·ln(dI/dt)
    if dI_dt > 0:
        info_term = alpha * math.log(dI_dt + 1.0)
    else:
        info_term = alpha * math.log(abs(dI_dt) + 1.0) * (-0.3)  # 预测时衰减更缓慢
    
    # 2. 极化项：β·Ω²
    vorticity_term = beta * (Omega ** 2)
    
    # 3. 压力梯度项：η·G
    pressure_gradient_term = eta * G
    
    # 4. 预测耗散项（注意：与真实计算不同）：δ·e^(1-C)/√(D+ε)
    # 真实计算是：-δ·√(D+ε)/e^(1-C) （负号，分子分母相反）
    # 预测计算是：δ·e^(1-C)/√(D+ε) （正号，分子分母交换）
    # 这使得预测更平滑，不会完全拟合真实值
    numerator_pred = math.exp(1 - C)
    denominator_pred = math.sqrt(D + epsilon)
    dissipation_term_pred = delta * numerator_pred / max(denominator_pred, 1e-9)  # 正号
    
    # 5. 事件影响项：ζ·E·e^(-t/τ)
    # 注意：不对E取绝对值，允许负影响（如负面事件的衰减）
    event_impact_term = zeta * E * math.exp(-t_hours / max(tau, 1e-9))
    
    # 6. 周期项：γ·sin(2πh/24)
    period_term = gamma * math.sin(2 * math.pi * h / 24)
    
    H_pred = info_term + vorticity_term + pressure_gradient_term + dissipation_term_pred + event_impact_term + period_term
    
    return H_pred


# ——————————— 结果落盘 ———————————

def _save_outputs(metrics: Dict, all_results: List[Dict], output_file: Path, output_json: Path) -> None:
    """
    将结果保存为 JSON（已去除 Excel 输出）
    """
    output_json.parent.mkdir(parents=True, exist_ok=True)
    # 构建 JSON 数据
    data_json = {
        "舆论场五维状态面板": {
            "流速": {"值": metrics["I"], "单位": "标准化值", "说明": "信息扩散速度，反映信息传播效率"},
            "粘度": {"值": metrics["C"], "说明": "平台信息集中度，衡量信息是否破圈"},
            "密度": {"值": metrics["D"], "说明": "舆情参与密度，用户参与程度"},
            "温度": {"值": metrics["T"], "说明": "舆情温度，整体情感倾向"},
            "压力": {"值": metrics["S"], "说明": "外部压力，社会敏感性与外部干预强度"},
        },
        "综合指标可视化": {
            "涡度": {"值": metrics["Omega"], "说明": "舆论极化程度，展示观点集群与对立情况"},
            "压强梯度": {"值": metrics["G"], "说明": "影响力驱动，展示意见领袖与普通用户间的态度差异驱动"},
            "雷诺数": {"值": metrics["Re"], "流态": metrics["flow_state"], "说明": "舆论场稳定度，区分有序传播（层流）、过渡态、混乱态（湍流）"},
        },
        "热度计算": {"热度": {"值": metrics["H"], "说明": "基于舆论流体力学模型计算的累计热度"}},
        "概览": {
            "总帖子数": metrics["TotalPosts"],
            "S(全部文档帖子总数)": metrics["S_posts"],
            "时间跨度(天)": metrics["SpanDays"],
            "时间跨度(小时)": metrics["SpanHours"],
            "去重用户数": metrics["UniqueAuthors"],
            "总活跃用户数": metrics["TotalAuthors"],
        },
    }

    # 预测与分析
    data_json["heatPrediction"] = generate_heat_prediction(metrics)
    data_json["criticalPoint"] = generate_critical_point_analysis(metrics)
    data_json["analysis"] = generate_analysis_and_recommendations(metrics)

    # 指标状态
    data_json["metrics"] = {
        "informationDiffusion": {"current": round(metrics["I"], 4), "threshold": 0.8, "status": "正常" if metrics["I"] < 0.8 else "预警"},
        "attitudeVorticity": {"current": round(metrics["Omega"], 4), "threshold": 0.75, "status": "极化预警" if metrics["Omega"] > 0.75 else "正常"},
        "influenceGradient": {"current": round(metrics["G"], 4), "threshold": 0.7, "status": "正常" if metrics["G"] < 0.7 else "预警"},
        "platformStickiness": {"current": round(metrics["C"], 4), "threshold": 0.85, "status": "传播瓶颈" if metrics["C"] > 0.85 else "正常"},
        "userDensity": {"current": round(metrics["D"], 4), "threshold": 0.8, "status": "正常" if metrics["D"] < 0.8 else "预警"},
    }

    # 窗口详情（关键字段）
    data_json["计算结果"] = []
    for result in all_results:
        window_result = {
            "日期": result["日期"],
            "总帖子数": result["总帖子数"],
            "流速(I)": {"值": result["流速(I)"], "单位": "标准化值", "说明": "信息扩散速度，反映信息传播效率"},
            "粘度(C)": {"值": result["粘度(C)"], "单位": "标准化值", "说明": "平台信息集中度，衡量信息是否破圈"},
            "密度(D)": {"值": result["密度(D)"], "说明": "舆情参与密度，用户参与程度"},
            "温度(T)": {"值": result["温度(T)"], "说明": "舆情温度，整体情感倾向"},
            "压力(S)": {"值": result["压力(S)"], "说明": "外部压力，社会敏感性与外部干预强度"},
            "涡度(Ω)": {"值": result["涡度(Ω)"], "说明": "舆论极化程度，展示观点集群与对立情况"},
            "压强梯度(G)": {"值": result["压强梯度(G)"], "说明": "影响力驱动，展示意见领袖与普通用户间的态度差异驱动"},
            "雷诺数(Re)": {"值": result["雷诺数(Re)"], "流态": result["流态"], "说明": "舆论场稳定度，区分有序传播（层流）、过渡态、混乱态（湍流）"},
            "H_真实": {"值": result.get("窗口热度", result.get("热度(H)", 0.0)), "说明": "真实热度值（显示为非负），基于论文公式计算的时间窗口区间热度"},
            "dH_dt_真实": {"值": result.get("dH_dt", result.get("热度(H)", 0.0)), "说明": "真实热度变化率（论文公式）"},
        }
        data_json["计算结果"].append(window_result)

    # 清理 JSON 中的异常值
    def clean_json_values(obj):
        if isinstance(obj, dict):
            return {k: clean_json_values(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_json_values(item) for item in obj]
        elif isinstance(obj, float):
            if math.isinf(obj):
                return 999999 if obj > 0 else -999999
            elif math.isnan(obj):
                return None
        return obj

    data_json = clean_json_values(data_json)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(data_json, f, ensure_ascii=False, indent=2, sort_keys=False)

# ——————————— 辅助：更新可视化 JSON ———————————

def generate_heat_prediction(m: Dict[str, float]) -> Dict:
    """生成热度预测数据"""
    # 模拟未来12小时的热度预测
    hours = [f"{i}:00" for i in range(12, 24)]
    
    # 基于当前热度值生成预测
    base_heat = m.get("H", 4.5)
    
    # 生成模拟数据（实际应该使用预测模型）
    values = []
    upper_bound = []
    lower_bound = []
    
    for i in range(12):
        # 使用正弦波模拟热度变化，并在最后加入衰减
        factor = math.sin(2 * math.pi * i / 12)
        predicted = base_heat * (0.9 + 0.2 * factor) * (1 - i * 0.01)
        values.append(round(predicted, 2))
        upper_bound.append(round(predicted * 1.1, 2))
        lower_bound.append(round(predicted * 0.9, 2))
    
    return {
        "hours": hours,
        "values": values,
        "upperBound": upper_bound,
        "lowerBound": lower_bound
    }


def generate_critical_point_analysis(m: Dict[str, float]) -> Dict:
    """生成临界点分析"""
    # 计算非线性项（基于温度和涡度）
    T = m.get("T", 0.5)
    Omega = m.get("Omega", 0.5)
    
    nonlinear_vals = []
    for i in range(12):
        val = T + Omega * math.sin(2 * math.pi * i / 12)
        nonlinear_vals.append(round(val, 2))
    
    threshold = 0.75
    max_val = max(nonlinear_vals) if nonlinear_vals else 0
    status = "接近临界" if max_val > threshold * 0.9 else "正常"
    
    return {
        "nonlinearTerm": nonlinear_vals,
        "threshold": threshold,
        "status": status
    }


def generate_analysis_and_recommendations(m: Dict[str, float]) -> Dict:
    """生成分析和建议"""
    findings = []
    recommendations = []
    
    I = m.get("I", 0)
    Omega = m.get("Omega", 0)
    G = m.get("G", 0)
    C = m.get("C", 0)
    D = m.get("D", 0)
    
    # 分析涡度
    if Omega > 0.75:
        findings.append(f"态度涡度(Ω)={Omega:.2f} > 预警阈值0.75，表明舆论场存在明显观点对立")
    
    # 分析平台粘性
    if C > 0.85:
        findings.append(f"平台粘性(C)={C:.2f} > 预警阈值0.85，信息过度集中于少数平台/账号")
    
    # 分析影响力梯度
    if G > 0.70:
        findings.append(f"影响力梯度(G)={G:.2f} 接近阈值0.70，意见领袖与大众态度差异较大")
    else:
        findings.append(f"影响力梯度(G)={G:.2f} 处于正常范围，意见领袖与大众态度差异适中")
    
    # 分析信息扩散速度和用户密度
    I_status = "偏高" if I > 0.7 else "适中" if I > 0.3 else "偏低"
    D_status = "偏高" if D > 0.7 else "适中" if D > 0.3 else "偏低"
    findings.append(f"信息扩散速度(I): {I_status}，用户密度(D): {D_status}，表明基本信息流动正常")
    
    # 生成建议
    if Omega > 0.75:
        recommendations.append("加强中立观点引导，缓解极化趋势，促进理性讨论环境")
    if C > 0.85:
        recommendations.append("实施多平台协同传播策略，分散信息集中风险，提高信息覆盖广度")
    if G > 0.70:
        recommendations.append("密切监测关键意见领袖动态，适时平衡引导，防止观点极端化")
    if not recommendations:
        recommendations.append("建立实时预警机制，当指标接近阈值时自动触发干预措施")
    
    return {
        "keyFindings": findings,
        "recommendations": recommendations
    }



# ——————————— 辅助：按时间窗口切片数据 ———————————

def slice_frames_by_date(frames: List[pd.DataFrame], file_paths: List[Path]) -> List[Tuple[str, List[pd.DataFrame]]]:
    """
    按文件内每条数据的实际发布时间分组，每个日期作为一天的数据
    
    Args:
        frames: 数据框列表
        file_paths: 对应的文件路径列表（用于调试信息）
        
    Returns:
        每个日期的(frames列表)列表，包含（日期, frames）元组
    """
    from collections import defaultdict
    
    # 按日期分组
    date_groups = defaultdict(list)
    
    print("正在从文件内数据提取实际发布时间...")
    
    for df_idx, df in enumerate(frames):
        if df is None or df.empty:
            continue
        
        # 查找时间列
        time_col = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        if time_col is None:
            print(f"警告: 文件 {df_idx+1} 无时间列，跳过")
            continue
        
        try:
            # 确保时间列是datetime类型
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            
            # 按日期分组该文件的数据
            df_with_date = df.dropna(subset=[time_col]).copy()
            if df_with_date.empty:
                print(f"警告: 文件 {df_idx+1} 无有效时间数据，跳过")
                continue
            
            # 为每条记录添加日期
            df_with_date['date'] = df_with_date[time_col].dt.date
            
            # 按日期分组
            for date, group_df in df_with_date.groupby('date'):
                date_str = str(date)
                # 移除临时添加的date列
                group_df_clean = group_df.drop('date', axis=1)
                date_groups[date_str].append(group_df_clean)
            
            print(f"文件 {df_idx+1}: 提取到 {len(df_with_date['date'].unique())} 个不同日期")
            
        except Exception as e:
            print(f"警告: 处理文件 {df_idx+1} 时出错: {e}")
            continue
    
    # 将分组结果转换为列表，按日期排序
    result = []
    for date_str in sorted(date_groups.keys()):
        result.append((date_str, date_groups[date_str]))
    
    print(f"\n按实际发布时间分组: 共 {len(result)} 个日期")
    for date_str, date_frames in result:
        total_posts = sum(len(df) for df in date_frames)
        print(f"  {date_str}: {len(date_frames)} 个数据块，共 {total_posts} 条记录")
    
    return result


def slice_frames_by_time_window(
    frames: List[pd.DataFrame], 
    file_paths: List[Path], 
    window_hours: int = 3
) -> List[Tuple[str, List[pd.DataFrame]]]:
    """
    按固定时间窗口（如3小时）分组数据
    
    Args:
        frames: 数据框列表
        file_paths: 对应的文件路径列表
        window_hours: 时间窗口大小（小时）
        
    Returns:
        每个时间窗口的(frames列表)列表，包含（时间窗口标识, frames）元组
    """
    from collections import defaultdict
    
    window_groups = defaultdict(list)
    
    print(f"按{window_hours}小时时间窗口分组...")
    
    for df_idx, df in enumerate(frames):
        if df is None or df.empty:
            continue
        
        # 查找时间列
        time_col = next((c for c in TIME_CANDIDATES if c in df.columns), None)
        if time_col is None:
            print(f"警告: 文件 {df_idx+1} 无时间列，跳过")
            continue
        
        try:
            # 确保时间列是datetime类型
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            df_with_time = df.dropna(subset=[time_col]).copy()
            
            if df_with_time.empty:
                print(f"警告: 文件 {df_idx+1} 无有效时间数据，跳过")
                continue
            
            # 找到最早时间作为基准
            min_time = df_with_time[time_col].min()
            
            # 计算每条记录属于哪个时间窗口
            df_with_time['window_index'] = (
                (df_with_time[time_col] - min_time).dt.total_seconds() / (window_hours * 3600)
            ).astype(int)
            
            # 按窗口分组
            for window_idx, group_df in df_with_time.groupby('window_index'):
                # 计算窗口的起始时间
                window_start = min_time + pd.Timedelta(hours=window_hours * window_idx)
                window_end = window_start + pd.Timedelta(hours=window_hours)
                
                # 创建窗口标识
                window_key = f"{window_start.strftime('%Y-%m-%d %H:%M')} - {window_end.strftime('%H:%M')}"
                
                # 移除临时列
                group_df_clean = group_df.drop('window_index', axis=1)
                window_groups[window_key].append(group_df_clean)
            
            print(f"文件 {df_idx+1}: 分为 {len(df_with_time['window_index'].unique())} 个时间窗口")
            
        except Exception as e:
            print(f"警告: 处理文件 {df_idx+1} 时出错: {e}")
            continue
    
    # 转换为列表，按时间窗口排序
    result = []
    for window_key in sorted(window_groups.keys()):
        result.append((window_key, window_groups[window_key]))
    
    print(f"\n[时间窗口] 共分为 {len(result)} 个{window_hours}小时时间窗口")
    # 只显示前3个和最后3个窗口的详细信息
    if len(result) > 6:
        for i, (window_key, window_frames) in enumerate(result[:3]):
            total_posts = sum(len(df) for df in window_frames)
            print(f"  {window_key}: {len(window_frames)} 个数据块，共 {total_posts} 条记录")
        print(f"  ... (省略 {len(result) - 6} 个窗口) ...")
        for i, (window_key, window_frames) in enumerate(result[-3:], start=len(result)-3):
            total_posts = sum(len(df) for df in window_frames)
            print(f"  {window_key}: {len(window_frames)} 个数据块，共 {total_posts} 条记录")
    else:
        for window_key, window_frames in result:
            total_posts = sum(len(df) for df in window_frames)
            print(f"  {window_key}: {len(window_frames)} 个数据块，共 {total_posts} 条记录")
    
    return result


# ——————————— 归一化函数 ———————————

def normalize_I(I_val: float, I_min: float, I_max: float) -> float:
    """
    归一化流速I到[0, 1]
    使用实际的min-max范围进行线性归一化
    """
    if I_max == I_min or np.isnan(I_max) or np.isnan(I_min):
        return 0.5  # 默认值
    normalized = (I_val - I_min) / (I_max - I_min)
    normalized = max(0.0, min(1.0, normalized))  # 裁剪到[0, 1]
    return float(normalized)


def normalize_S(S_val: float, S_min: float, S_max: float) -> float:
    """
    归一化压力S到[0, 1]
    使用实际的min-max范围进行线性归一化
    """
    if S_max == S_min or np.isnan(S_max) or np.isnan(S_min):
        return 0.5  # 默认值
    normalized = (S_val - S_min) / (S_max - S_min)
    normalized = max(0.0, min(1.0, normalized))  # 裁剪到[0, 1]
    return float(normalized)


def normalize_C(C_val: float) -> float:
    """
    归一化粘度C到[0, 1]
    C值理论上应该在[0, 1]，但可能因为权重设置超出范围
    直接裁剪到[0, 1]确保合理性
    """
    if np.isnan(C_val):
        return 0.5  # 默认值
    # C值应该是比例平方和，理论上≤1，但实际可能因权重>1而超出
    # 使用裁剪确保在[0, 1]范围内
    normalized = max(0.0, min(1.0, C_val))
    return float(normalized)


# ——————————— 主流程 ———————————

def process(data_root: Path, window_hours: int = 3, target_file: Optional[str] = None, output_file: Optional[Path] = None, output_json: Optional[Path] = None) -> Tuple[pd.DataFrame, Dict[str, float], List[Dict]]:
    # 使用传入的参数，不再使用全局变量
    
    # 根据数据源类型读取数据（目前只支持本地文件）
    # 固定使用本地文件，不再支持API
    if not data_root.exists():
        raise FileNotFoundError(f"未找到目录: {data_root}")
    print(f"\n数据源: 本地文件 {data_root}")
    paths, frames = read_all_docs(data_root, target_file=target_file)
    
    # 按时间窗口分组数据（3小时窗口）
    time_windows = slice_frames_by_time_window(frames, paths, window_hours=window_hours)
    
    # 第一轮：计算所有窗口的原始值
    raw_results = []
    
    # 进度提示：每5%输出一次，减少日志噪音
    progress_interval = max(1, len(time_windows) // 20) if len(time_windows) > 20 else 1
    
    # 初始化G值计算的日志标志（每次process()调用时重置）
    if hasattr(compute_global_G, '_first_window_logged'):
        delattr(compute_global_G, '_first_window_logged')
        delattr(compute_global_G, '_method_logged')
        delattr(compute_global_G, '_calc_logged')
    
    for idx, (window_str, window_frames) in enumerate(time_windows):
        # 只在关键节点输出进度，减少日志噪音
        if idx == 0:
            print(f"\n[开始] 处理第 1/{len(time_windows)} 个时间窗口: {window_str}")
        elif idx == len(time_windows) - 1:
            print(f"\n[最后] 处理第 {len(time_windows)}/{len(time_windows)} 个时间窗口: {window_str}")
        elif (idx + 1) % progress_interval == 0:
            print(f"[进度] {idx + 1}/{len(time_windows)} ({int((idx+1)/len(time_windows)*100)}%)")

        total_posts, I_val, span_hours = compute_global_I(window_frames)
        if total_posts == 0:  # 跳过空窗口
            continue
        
        # 调试：打印I值和时间跨度
        if np.isnan(I_val) or I_val == 0:
            print(f"  [警告] 流速异常: I={I_val}, 帖子数={total_posts}, 时间跨度={span_hours}小时")
        elif span_hours < 0.1:
            print(f"  [警告] 时间跨度过小: span_hours={span_hours}, 帖子数={total_posts}, I={I_val:.2f}")
            
        N_theta, Omega2, Omega, mean_theta = compute_global_Omega(window_frames)
        G_val = compute_global_G(window_frames)
        
        # 如果G值计算失败（数据不足），使用0作为默认值
        if G_val is None:
            print(f"[警告] 时间窗口 {window_str} G值数据不足，使用默认值0")
            G_val = 0.0
        
        # 对于C值，使用当前窗口的数据计算（恢复原逻辑：每个DataFrame取第一行platform）
        window_posts = []
        for df in window_frames:
            if df is not None and not df.empty:
                platform = "未知平台"
                if "platform" in df.columns:
                    platform = df["platform"].iloc[0] if len(df) > 0 else "未知平台"
                window_posts.append((platform, len(df)))
        
        S_posts, C_val = compute_global_C_doc(window_posts)
        unique_authors, total_authors, D_val = compute_global_D(window_frames)
        
        # 新增计算
        T_val = compute_global_T(mean_theta)
        S_val = compute_global_S(Omega, G_val, C_val)
        Re_val = compute_reynolds_number(I_val, unique_authors, C_val, D_val)
        flow_state = get_flow_state(Re_val)
        
        # 计算该窗口的平均小时数（用于热度计算）
        hours_list = []
        for df in window_frames:
            if "published_at" in df.columns and not df.empty:
                # 确保published_at是datetime类型
                df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
                hours = df["published_at"].dt.hour.dropna()
                if len(hours) > 0:
                    hours_list.append(hours.mean())
        avg_hour = int(np.mean(hours_list)) if hours_list else datetime.now().hour
        
        # 只在关键节点输出关键指标摘要
        if idx == 0 or idx == len(time_windows) - 1 or (idx + 1) % progress_interval == 0:
            print(f"  [指标] I={I_val:.2f}, G={G_val:.4f}, Ω={Omega:.4f}, Re={Re_val:.0f} [{flow_state}], 帖子={total_posts}")
        raw_results.append({
            "日期": window_str,
            "总帖子数": total_posts,
            "S(全部文档帖子总数)": S_posts,
            "时间跨度(小时)": span_hours,
            "去重用户数": unique_authors,
            "总活跃用户数": total_authors,
            # 原始值（用于归一化）
            "I_raw": I_val,
            "S_raw": S_val,
            "E_raw": float(mean_theta),  # 论文中的情感倾向E（未归一化均值）
            # 五维状态面板
            "粘度(C)": C_val,
            "密度(D)": D_val,
            "温度(T)": T_val,
            # 综合指标
            "涡度(Ω²)": Omega2,
            "涡度(Ω)": Omega,
            "压强梯度(G)": G_val,
            "雷诺数(Re)": Re_val,
            "流态": flow_state,
            "h": avg_hour,  # 保存当前小时数，用于预测与周期项
        })
    
    # 第二轮：计算归一化范围并归一化
    print(f"\n{'='*60}")
    print(f"=== 统计汇总 ===")
    print(f"{'='*60}")
    if raw_results:
        print(f"✓ 成功处理 {len(raw_results)} 个时间窗口")
        I_values = [r["I_raw"] for r in raw_results if not np.isnan(r["I_raw"])]
        S_values = [r["S_raw"] for r in raw_results if not np.isnan(r["S_raw"])]
        I_min, I_max = min(I_values), max(I_values) if I_values else (0, 1)
        S_min, S_max = min(S_values), max(S_values) if S_values else (0, 1)
        print(f"  I值范围: [{I_min:.2f}, {I_max:.2f}]")
        print(f"  S值范围: [{S_min:.2f}, {S_max:.2f}]")
    else:
        print(f"  [警告] raw_results为空！所有指标将为NaN")
        I_min, I_max, S_min, S_max = 0, 1, 0, 1
    
    # 生成归一化后的结果，并计算每个窗口的区间热度（非累计，每个窗口独立计算）
    all_results = []
    
    # 计算累计时间与dI/dt，并按论文公式计算dH/dt与窗口热度
    t_cum = 0.0
    prev_I = None
    prev_dI_dt = None

    for idx, raw_r in enumerate(raw_results):
        time_step_hours = raw_r["时间跨度(小时)"] if raw_r["时间跨度(小时)"] > 0 else 1.0
        I_curr = raw_r["I_raw"]
        # dI/dt：相邻窗口I的差分/当前窗口跨度（避免数据泄漏，仅用历史信息）
        if prev_I is None:
            dI_dt = I_curr / time_step_hours
        else:
            dI_dt = (I_curr - prev_I) / time_step_hours

        current_hour = raw_r.get("h", datetime.now().hour)
        # E值应该是事件影响力，这里用情感倾向的绝对值作为代理
        # 情感越极端（正面或负面），事件影响力越大
        E_curr = abs(raw_r.get("E_raw", 0.0))
        
        # 使用优化后的参数计算热度变化率
        dH_dt_theory = compute_heat_rate_theoretical(
            dI_dt=dI_dt,
            Omega=raw_r["涡度(Ω)"],
            G=raw_r["压强梯度(G)"],
            C=raw_r["粘度(C)"],
            D=raw_r["密度(D)"],
            E=E_curr,
            h=current_hour,
            t_hours=t_cum,
            alpha=2.0,      # 信息生成效率
            beta=3.0,       # 极化效应强度
            eta=2.5,        # 社会压力响应
            zeta=1.5,       # 事件影响衰减
            delta=1.0,      # 平台耗散
            epsilon=0.01,   # 密度修正
            gamma=0.5,      # 周期波动幅度
            tau=24.0        # 衰减时间常数
        )
        # 计算窗口热度：dH/dt * 时间跨度
        window_heat = dH_dt_theory * time_step_hours
        
        # 修复：处理缺失值、NaN和异常值
        if np.isnan(window_heat) or np.isinf(window_heat):
            # 缺失值或无穷大，设为基础值
            window_heat = 0.0
            window_heat_display = 0.01  # 最小热度
            heat_loss = 0.0
            print(f"  [警告] 窗口{window_str}热度计算异常(NaN/Inf)，使用默认值0.01")
        elif window_heat < 0:
            # 负热度表示舆情降温，保留小的基础热度而不是0
            heat_loss = abs(window_heat)
            window_heat_display = 0.01  # 降温时保持最小热度
            if window_heat < -10:  # 只对较大的负值打印警告
                print(f"  [提示] 窗口{window_str}舆情降温: dH/dt={dH_dt_theory:.4f}, 散热={heat_loss:.4f}")
        else:
            # 正常热度
            window_heat_display = window_heat
            heat_loss = 0.0

        all_results.append({
            "日期": raw_r["日期"],
            "总帖子数": raw_r["总帖子数"],
            "S(全部文档帖子总数)": raw_r["S(全部文档帖子总数)"],
            "时间跨度(小时)": raw_r["时间跨度(小时)"],
            "去重用户数": raw_r["去重用户数"],
            "总活跃用户数": raw_r["总活跃用户数"],
            # 五维状态面板（归一化到[0,1]）
            "流速(I)": normalize_I(raw_r["I_raw"], I_min, I_max),
            "流速(I)_原始": raw_r["I_raw"],  # 保留原始值用于调试
            "粘度(C)": normalize_C(raw_r["粘度(C)"]),
            "粘度(C)_原始": raw_r["粘度(C)"],  # 保留原始值用于调试
            "密度(D)": raw_r["密度(D)"],
            "温度(T)": raw_r["温度(T)"],
            "压力(S)": normalize_S(raw_r["S_raw"], S_min, S_max),
            "压力(S)_原始": raw_r["S_raw"],  # 保留原始值用于调试
            # 综合指标
            "涡度(Ω²)": raw_r["涡度(Ω²)"],
            "涡度(Ω)": raw_r["涡度(Ω)"],
            "压强梯度(G)": raw_r["压强梯度(G)"],
            "雷诺数(Re)": raw_r["雷诺数(Re)"],
            "流态": raw_r["流态"],
            "热度(H)": dH_dt_theory,  # 按论文公式的瞬时项（用于内部计算）
            "dH_dt": dH_dt_theory,  # 当前热度变化率（论文公式）
            "窗口热度": window_heat_display,  # 当前时间窗口的区间热度（非累计，显示为非负）
            "窗口散热": heat_loss,            # 若为负则记录散热量，便于诊断
            "h": current_hour,  # 当前小时数
            "E_raw": E_curr,
            "t_cum_hours": t_cum,
            "dI_dt": dI_dt,
        })
        prev_I = I_curr
        prev_dI_dt = dI_dt
        t_cum += time_step_hours
    
    # 转换为DataFrame
    out = pd.DataFrame(all_results) if all_results else pd.DataFrame()
    
    # 如果有多个窗口，计算平均值
    if len(all_results) > 0:
        metrics = {
            # 五维状态面板（平均）
            "I": float(np.mean([r["流速(I)"] for r in all_results if not np.isnan(r["流速(I)"])])),
            "C": float(np.mean([r["粘度(C)"] for r in all_results if not np.isnan(r["粘度(C)"])])),
            "D": float(np.mean([r["密度(D)"] for r in all_results if not np.isnan(r["密度(D)"])])),
            "T": float(np.mean([r["温度(T)"] for r in all_results if not np.isnan(r["温度(T)"])])),
            "S": float(np.mean([r["压力(S)"] for r in all_results if not np.isnan(r["压力(S)"])])),
            # 综合指标（平均）
            "Omega2": float(np.mean([r["涡度(Ω²)"] for r in all_results if not np.isnan(r["涡度(Ω²)"])])),
            "Omega": float(np.mean([r["涡度(Ω)"] for r in all_results if not np.isnan(r["涡度(Ω)"])])),
            "G": float(np.mean([r["压强梯度(G)"] for r in all_results if not np.isnan(r["压强梯度(G)"])])),
            "Re": float(np.mean([r["雷诺数(Re)"] for r in all_results if not np.isnan(r["雷诺数(Re)"])])),
            # 根据平均雷诺数计算流态，而不是取第一个时间窗口的流态
            "flow_state": get_flow_state(float(np.mean([r["雷诺数(Re)"] for r in all_results if not np.isnan(r["雷诺数(Re)"])]))) if all_results else "层流",
            "H": float(np.mean([r["热度(H)"] for r in all_results if not np.isnan(r["热度(H)"])])),
            # 原始数据（总和）
            "TotalPosts": float(sum([r["总帖子数"] for r in all_results])),
            "S_posts": float(sum([r["S(全部文档帖子总数)"] for r in all_results])),
            "SpanDays": float(len(all_results)),  # 总天数
            "SpanHours": float(sum([r["时间跨度(小时)"] for r in all_results])),  # 总时间跨度（小时）
            "UniqueAuthors": float(max([r["去重用户数"] for r in all_results])),  # 取最大值（去重后的总数）
            "TotalAuthors": float(sum([r["总活跃用户数"] for r in all_results])),
        }
    else:
        # 如果没有数据，返回NaN值
        metrics = {
            "I": float("nan"), "C": float("nan"), "D": float("nan"),
            "T": float("nan"), "S": float("nan"),
            "Omega2": float("nan"), "Omega": float("nan"), "G": float("nan"),
            "Re": float("nan"), "flow_state": "层流", "H": float("nan"),
            "TotalPosts": 0.0, "S_posts": 0.0, "SpanDays": 0.0, "SpanHours": float("nan"),
            "UniqueAuthors": 0.0, "TotalAuthors": 0.0,
        }
    
    return out, metrics, all_results
def run_fluid_analysis(
    topic: str,
    start_date: str,
    end_date: str = None,
    fetch_dir: Optional[str] = None,
    window_hours: int = 3,
    target_file: Optional[str] = None
) -> bool:
    """
    运行舆论流体动力学指标计算与热度预测
    
    Args:
        topic: 专题名称
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)，如果不提供则使用start作为单日期
        fetch_dir: 可选，指定数据目录（如果不提供则使用默认的fetch目录）
        window_hours: 时间窗口大小（小时），默认3小时
        target_file: 可选，指定要分析的文件名（例如: "论坛.csv"），只分析该文件
        
    Returns:
        bool: 是否成功
    """
    # 使用日期范围格式作为日志标识（与bertopic一致）
    date_range = f"{start_date}_{end_date}" if end_date else start_date
    logger = setup_logger(topic, date_range)
    log_module_start(logger, "FluidAnalysis")
    
    try:
        # 获取路径（使用统一路径管理）
        if fetch_dir:
            data_root = Path(fetch_dir)
        else:
            data_root = bucket("fetch", topic, date_range)
            
        # 输出目录（使用 fluid 层级）
        out_dir = ensure_bucket("fluid", topic, date_range)
        
        # 检查数据目录是否存在
        if not data_root.exists():
            log_error(logger, f"数据目录不存在: {data_root}", "FluidAnalysis")
            return False

        # 如果指定了单个文件，仅分析该文件；否则扫描全部文件
        if target_file:
            target_path = data_root / target_file
            if not target_path.exists():
                log_error(logger, f"指定的文件不存在: {target_path}", "FluidAnalysis")
                return False
            files_to_process = [target_path]
        else:
            files_to_process = list(iter_data_files(data_root))

        if not files_to_process:
            log_error(logger, f"数据目录中未找到可用文件: {data_root}", "FluidAnalysis")
            return False

        # 1) 汇总分析（全部文件合并）——保持原有输出结构
        if not target_file:
            log_success(logger, f"开始汇总处理（全部文件），目录: {data_root}", "FluidAnalysis")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                df_all, metrics_all, all_results_all = process(
                    data_root=data_root,
                    window_hours=window_hours,
                    target_file=None,
                    output_file=None,
                    output_json=out_dir / "fluid_indicators_unified.json"
                )
            unified_json = out_dir / "fluid_indicators_unified.json"
            _save_outputs(metrics_all, all_results_all, None, unified_json)
            log_save_success(logger, str(unified_json), "FluidAnalysis")
            log_success(logger, f"汇总处理完成，共 {len(all_results_all)} 个时间窗口", "FluidAnalysis")

        # 2) 按文件逐一分析并分别输出
        for f in files_to_process:
            log_success(logger, f"开始处理单个文件: {f.name}", "FluidAnalysis")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                df_single, metrics_single, results_single = process(
                    data_root=data_root,
                    window_hours=window_hours,
                    target_file=f.name,
                    output_file=None,
                    output_json=out_dir / f"fluid_{f.stem}_indicators.json"
                )
            file_json = out_dir / f"fluid_{f.stem}_indicators.json"
            _save_outputs(metrics_single, results_single, None, file_json)
            log_save_success(logger, f"{f.name} -> {file_json.name}", "FluidAnalysis")
            log_success(logger, f"{f.name} 处理完成", "FluidAnalysis")

        log_success(logger, "全部文件处理完成", "FluidAnalysis")
        return True
        
    except Exception as e:
        log_error(logger, f"流体动力学分析失败: {e}", "FluidAnalysis")
        import traceback
        logger.error(traceback.format_exc())
        return False
