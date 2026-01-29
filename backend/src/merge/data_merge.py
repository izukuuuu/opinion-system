"""
TRS数据合并功能
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from ..utils.setting.paths import bucket, ensure_bucket
from ..utils.setting.settings import settings
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error
from ..utils.io.excel import write_jsonl


def _normalise_keep_channels(channels: List[str]) -> Dict[str, str]:
    """Build a case-insensitive lookup for configured渠道."""
    lookup: Dict[str, str] = {}
    for channel in channels:
        if not isinstance(channel, str):
            continue
        cleaned = channel.strip()
        if not cleaned:
            continue
        lookup[cleaned.lower()] = cleaned
    return lookup


def _resolve_channel_name(raw: str, keep_lookup: Dict[str, str]) -> Optional[str]:
    """Normalise a raw channel value against the keep list (case-insensitive)."""
    name = str(raw or "").strip()
    if not name:
        return None
    key = name.lower()
    if keep_lookup and key not in keep_lookup:
        return None
    return keep_lookup.get(key, name)


def _infer_channel_from_filename(file_path: Path, keep_lookup: Dict[str, str]) -> Optional[str]:
    """Infer channel from file name tokens (split by '_' then '-')."""
    for token in reversed(file_path.stem.split("_")):
        channel = _resolve_channel_name(token, keep_lookup)
        if channel:
            return channel
    for token in reversed(file_path.stem.split("-")):
        channel = _resolve_channel_name(token, keep_lookup)
        if channel:
            return channel
    return _resolve_channel_name(file_path.stem, keep_lookup)


def _split_dataframe_by_channel(
    df: pd.DataFrame,
    file_path: Path,
    keep_lookup: Dict[str, str],
    logger=None,
) -> List[Tuple[str, pd.DataFrame]]:
    """Split a flat table into channel-tagged frames using column hints or filename."""
    channel_frames: List[Tuple[str, pd.DataFrame]] = []
    if df is None or df.empty:
        return channel_frames

    channel_columns = ["channel", "渠道", "发布平台", "platform"]
    channel_col = next((col for col in channel_columns if col in df.columns), None)

    if channel_col:
        grouped = df.groupby(df[channel_col].astype(str).str.strip())
        for raw_channel, group_df in grouped:
            channel_name = _resolve_channel_name(raw_channel, keep_lookup)
            if not channel_name:
                log_error(logger, f"{file_path.name} 渠道 {raw_channel} 不在 keep 列表中，已跳过", "Merge")
                continue
            channel_frames.append((channel_name, group_df))
    else:
        channel_name = _infer_channel_from_filename(file_path, keep_lookup)
        if not channel_name:
            log_error(logger, f"{file_path.name} 缺少渠道信息，已跳过", "Merge")
            return channel_frames
        channel_frames.append((channel_name, df))

    return channel_frames


def _build_field_alias_map(config: Dict[str, Any]) -> Dict[str, str]:
    """
    解析字段别名配置，兼容 field_alias 与 field_aliases 两种写法.

    返回 {源列名: 标准列名} 形式，便于 DataFrame.rename 使用。
    """
    raw_aliases = config.get("field_aliases") or config.get("field_alias") or {}
    alias_map: Dict[str, str] = {}
    if not isinstance(raw_aliases, dict):
        return alias_map

    for canonical, aliases in raw_aliases.items():
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias.strip():
                    alias_map[alias] = canonical
        elif isinstance(aliases, str):
            if canonical:
                alias_map[canonical] = aliases
    return alias_map


def _iter_channel_frames(
    file_path: Path,
    keep_lookup: Dict[str, str],
    field_alias_map: Dict[str, str],
    logger=None,
):
    """Yield (channel, DataFrame) pairs from an Excel/CSV/JSONL file."""
    suffix = file_path.suffix.lower()

    try:
        if suffix in (".xlsx", ".xls"):
            excel_data = pd.read_excel(file_path, sheet_name=None)
            for sheet_name, df in excel_data.items():
                if df.empty:
                    continue
                channel_name = _resolve_channel_name(sheet_name, keep_lookup)
                if not channel_name:
                    continue
                if field_alias_map:
                    df = df.rename(columns=field_alias_map)
                yield channel_name, df
        elif suffix == ".csv":
            df = pd.read_csv(file_path, encoding="utf-8-sig")
            for channel_name, channel_df in _split_dataframe_by_channel(df, file_path, keep_lookup, logger):
                if field_alias_map:
                    channel_df = channel_df.rename(columns=field_alias_map)
                yield channel_name, channel_df
        elif suffix == ".jsonl":
            df = pd.read_json(file_path, lines=True)
            for channel_name, channel_df in _split_dataframe_by_channel(df, file_path, keep_lookup, logger):
                if field_alias_map:
                    channel_df = channel_df.rename(columns=field_alias_map)
                yield channel_name, channel_df
        else:
            log_error(logger, f"不支持的文件类型: {file_path.suffix}", "Merge")
    except Exception as e:
        log_error(logger, f"处理文件失败: {file_path.name} - {e}", "Merge")


def merge_trs_data(topic: str, date: str, logger=None) -> bool:
    """
    合并TRS原始表（支持Excel/CSV/JSONL）并输出JSONL
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """

    # 1. 定位文件
    raw_dir = bucket("raw", topic, date)
    if not raw_dir.exists():
        log_error(logger, f"原始数据目录不存在: {raw_dir}", "Merge")
        return False

    # 2. 获取渠道配置
    channels_config = settings.get_channel_config()
    keep_config = channels_config.get("keep", [])
    keep_channels = keep_config if isinstance(keep_config, list) else []
    if not keep_channels:
        log_error(logger, "未找到渠道配置", "Merge")
        return False

    keep_lookup = _normalise_keep_channels(keep_channels)
    field_alias_map = _build_field_alias_map(channels_config)

    # 3. 创建输出目录
    merge_dir = ensure_bucket("merge", topic, date)

    # 4. 收集所有支持的原始文件（大小写不敏感）
    supported_suffixes = {".xlsx", ".xls", ".csv", ".jsonl"}
    source_files = sorted(
        path
        for path in raw_dir.iterdir()
        if path.is_file() and path.suffix.lower() in supported_suffixes
    )
    if not source_files:
        available_files = sorted(path.name for path in raw_dir.iterdir() if path.is_file())
        hint = "目录为空"
        if available_files:
            preview = ", ".join(available_files[:10])
            hint = f"当前目录文件: {preview}"
        log_error(logger, f"未找到可用的 Excel/CSV/JSONL 文件（{hint}）", "Merge")
        return False

    # 5. 按渠道分组处理
    channel_data: Dict[str, List[pd.DataFrame]] = {}
    success_count = 0

    for file_path in source_files:
        for channel_name, df in _iter_channel_frames(file_path, keep_lookup, field_alias_map, logger):
            if channel_name not in channel_data:
                channel_data[channel_name] = []
            channel_data[channel_name].append(df)

    if not channel_data:
        log_error(logger, "未收集到任何渠道数据，可能渠道名称未在 keep 配置中", "Merge")
        return False

    # 6. 合并并保存数据
    for channel, data_list in channel_data.items():
        if not data_list:
            continue

        try:
            # 合并同一渠道的所有数据
            merged_df = pd.concat(data_list, ignore_index=True)

            # 去重
            before_count = len(merged_df)
            merged_df = merged_df.drop_duplicates()
            after_count = len(merged_df)

            if before_count != after_count:
                log_success(logger, f"渠道 {channel} 去重: {before_count} -> {after_count}", "Merge")

            # 保存为 JSONL 格式
            output_file = merge_dir / f"{channel}.jsonl"
            write_jsonl(merged_df, output_file)

            success_count += 1
            log_success(logger, f"成功保存: {channel} -- 共{len(merged_df)}条", "Merge")

        except Exception as e:
            log_error(logger, f"合并渠道 {channel} 失败: {e}", "Merge")
            continue

    if success_count > 0:
        return True
    log_error(logger, "合并失败: 没有成功处理任何渠道", "Merge")
    return False


def run_merge(topic: str, date: str, logger=None):
    """
    运行TRS数据合并
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger(topic, date)
    
    log_module_start(logger, "Merge")

    try:
        result = merge_trs_data(topic, date, logger)
        if result:
            return True
        else:
            log_error(logger, "模块执行失败", "Merge")
            return False
    except Exception as e:
        log_error(logger, f"模块执行失败: {e}", "Merge")
        return False
