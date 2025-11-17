"""
分析运行器模块
"""
import asyncio
import json
from datetime import datetime, timezone
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional
from ..utils.setting.paths import bucket
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error, log_save_success, log_skip
from ..utils.setting.settings import settings
from ..utils.io.excel import read_jsonl
from ..utils.ai import get_qwen_client
from .functions.volume import analyze_volume_overall, analyze_volume_by_channel
from .functions.attitude import analyze_attitude_overall, analyze_attitude_by_channel
from .functions.trends import analyze_trends_overall, analyze_trends_by_channel
from .functions.geography import analyze_geography_overall, analyze_geography_by_channel
from .functions.publishers import analyze_publishers_overall, analyze_publishers_by_channel
from .functions.keywords import analyze_keywords_overall, analyze_keywords_by_channel
from .functions.classification import analyze_classification_overall, analyze_classification_by_channel


FUNCTION_LABELS = {
    'volume': '声量概览',
    'attitude': '情感分析',
    'trends': '趋势洞察',
    'keywords': '关键词分析',
    'geography': '地域分析',
    'publishers': '发布者分析',
    'classification': '话题分类',
}

SUMMARY_FILENAME = "summary.txt"
AI_SUMMARY_FILENAME = "ai_summary.json"
MAX_SNAPSHOT_ROWS = 5

_AI_CLIENT: Optional[Any] = None
_AI_CLIENT_ERROR = False


def _get_ai_client(logger) -> Optional[Any]:
    global _AI_CLIENT, _AI_CLIENT_ERROR
    if _AI_CLIENT_ERROR:
        return None
    if _AI_CLIENT is not None:
        return _AI_CLIENT
    try:
        _AI_CLIENT = get_qwen_client()
        return _AI_CLIENT
    except Exception as exc:  # pragma: no cover - 外部依赖
        _AI_CLIENT_ERROR = True
        log_error(logger, f"AI摘要模块不可用：{exc}", "Analysis")
        return None


def _safe_async_call(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _extract_rows(result: Any) -> List[Dict[str, Any]]:
    if isinstance(result, dict):
        data = result.get('data')
        if isinstance(data, list):
            return data
    if isinstance(result, list):
        return result
    return []


def _format_row_pair(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return str(row)
    name = row.get('name') or row.get('label') or row.get('key') or '未命名'
    value = row.get('value')
    if value is None:
        for key in ('count', 'total', 'ratio', 'percent'):
            value = row.get(key)
            if value is not None:
                break
    return f"{name}: {value if value is not None else '-'}"


def _build_text_snapshot(
    func_name: str,
    target: str,
    result: Any,
    max_rows: Optional[int] = MAX_SNAPSHOT_ROWS,
    ellipsis: bool = True,
) -> str:
    label = FUNCTION_LABELS.get(func_name, func_name)
    rows = _extract_rows(result)
    lines = [f"{label}（{target}）分析概览", f"记录数：{len(rows)}"]
    if rows:
        lines.append("关键条目：")
        selected_rows = rows if max_rows is None else rows[:max_rows]
        for row in selected_rows:
            lines.append(f"- {_format_row_pair(row)}")
        if ellipsis and max_rows is not None and len(rows) > max_rows:
            lines.append(f"……其余 {len(rows) - max_rows} 条已省略")
    else:
        lines.append("暂无有效数据")
    return "\n".join(lines)


def _write_text_snapshot(target_dir: Path, snapshot: str):
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with open(target_dir / SUMMARY_FILENAME, 'w', encoding='utf-8') as fh:
            fh.write(snapshot)
    except Exception:
        # 文本快照写入失败不影响主流程
        pass


def _generate_ai_summary(func_name: str, target: str, snapshot: str, logger) -> str:
    client = _get_ai_client(logger)
    if not client or not snapshot.strip():
        return ""
    label = FUNCTION_LABELS.get(func_name, func_name)
    prompt = (
        "你是一名资深舆情分析师。基于以下统计快照，以不超过80字的中文总结核心洞察，不要输出列表或多段。"
        f"\n模块：{label}"
        f"\n范围：{target}"
        f"\n统计数据：\n{snapshot}"
        "\n请直接输出精炼结论。"
    )
    try:
        response = _safe_async_call(client.call(prompt, model="qwen-plus", max_tokens=400))
    except Exception as exc:  # pragma: no cover - 外部依赖
        log_error(logger, f"AI摘要生成失败：{exc}", "Analysis")
        return ""
    if not response:
        return ""
    text = response.get('text') or ''
    return text.strip()


def _load_existing_ai_summary(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            payload = json.load(fh)
        entries = {}
        for item in payload.get('summaries', []):
            key = f"{item.get('function')}::{item.get('target', '总体')}"
            entries[key] = item
        return entries
    except Exception:
        return {}


def _update_ai_summary_entry(entries: Dict[str, Dict[str, Any]], func_name: str, target: str, snapshot: str, ai_text: str) -> bool:
    key = f"{func_name}::{target}"
    label = FUNCTION_LABELS.get(func_name, func_name)
    new_entry = {
        "function": func_name,
        "function_label": label,
        "target": target,
        "text_snapshot": snapshot,
        "ai_summary": ai_text,
        "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
    }
    previous = entries.get(key)
    if previous == new_entry:
        return False
    entries[key] = new_entry
    return True


def _save_ai_summary_file(path: Path, topic: str, start: str, end: Optional[str], entries: Dict[str, Dict[str, Any]]):
    if not entries:
        return
    payload = {
        "topic": topic,
        "range": {"start": start, "end": end or start},
        "generated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "summaries": [entries[key] for key in sorted(entries.keys())],
    }
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _post_process_result(func_name: str, target: str, target_dir: Path, result: Any, ai_entries: Dict[str, Dict[str, Any]], ai_state: Dict[str, bool], logger):
    snapshot = _build_text_snapshot(func_name, target, result or {})
    _write_text_snapshot(target_dir, snapshot)
    if target != '总体':
        return
    full_snapshot = _build_text_snapshot(func_name, target, result or {}, max_rows=None, ellipsis=False)
    ai_text = _generate_ai_summary(func_name, target, full_snapshot, logger)
    if _update_ai_summary_entry(ai_entries, func_name, target, snapshot, ai_text):
        ai_state['dirty'] = True

def run_Analyze(topic: str, date: str, logger=None, only_function: str = None, end_date: str = None) -> bool:
    """
    运行分析任务
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
        only_function (str, optional): 仅运行指定分析函数
    
    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger(topic, date)
    
    log_module_start(logger, "Analyze")
        
    # 获取分析配置
    analysis_config = settings.get_analysis_config()
    functions = analysis_config.get('functions', [])
    
    if not functions:
        log_error(logger, "未配置分析函数", "Analysis")
        return False
    
    # 读取数据：总体.jsonl 与各渠道 *.jsonl（排除 总体.jsonl）
    # 如果提供了结束日期，使用日期范围格式，否则使用单个日期
    if end_date:
        folder_name = f"{date}_{end_date}"
    else:
        folder_name = date
    fetch_dir = bucket("fetch", topic, folder_name)
    if not fetch_dir.exists():
        log_error(logger, f"未找到数据目录: {fetch_dir}", "Analysis")
        return False
    overall_file = fetch_dir / "总体.jsonl"
    if not overall_file.exists():
        log_error(logger, f"未找到总体数据文件: {overall_file}", "Analysis")
        return False
    try:
        df_overall = read_jsonl(overall_file)
    except Exception as e:
        log_error(logger, f"读取总体数据失败: {e}", "Analysis")
        return False
    # 收集渠道文件
    channel_files: Dict[str, Path] = {}
    for jsonl_path in fetch_dir.glob("*.jsonl"):
        if jsonl_path.name == "总体.jsonl":
            continue
        channel_name = jsonl_path.stem
        channel_files[channel_name] = jsonl_path
    
    # 创建输出目录（按功能/渠道分层）
    # 使用与fetch模块相同的日期范围格式
    if end_date:
        folder_name = f"{date}_{end_date}"
    else:
        folder_name = date
    analyze_root = bucket("analyze", topic, folder_name)
    analyze_root.mkdir(parents=True, exist_ok=True)

    ai_summary_file = analyze_root / AI_SUMMARY_FILENAME
    ai_summary_entries = _load_existing_ai_summary(ai_summary_file)
    ai_state = {"dirty": False}
    
    success_count = 0
    
    # 若仅运行单功能，先做一次过滤（支持别名与大小写不敏感）
    if only_function:
        alias = only_function.strip()
        alias_norm = alias.lower()
        before = len(functions)
        functions = [f for f in functions if (f.get('name','').strip().lower() == alias_norm)]
        if not functions:
            log_error(logger, f"--func 未匹配到任何分析项：{only_function}", "Analysis")
            return False
            
    # 运行分析函数
    for func_config in functions:
        func_name = func_config.get('name')
        target = func_config.get('target')
        # 这里不再逐项跳过，已在上方统一过滤
        try:
            # 根据函数名和目标调用对应的分析函数，并按功能/渠道落盘
            if target == '总体':
                # 运行总体
                result = None
                if func_name == 'volume':
                    result = analyze_volume_overall(df_overall, topic, date, logger, end_date)
                elif func_name == 'attitude':
                    result = analyze_attitude_overall(df_overall, logger)
                elif func_name == 'trends':
                    result = analyze_trends_overall(df_overall, logger)
                elif func_name == 'keywords':
                    result = analyze_keywords_overall(df_overall, topic, logger)
                elif func_name == 'geography':
                    result = analyze_geography_overall(df_overall, logger)
                elif func_name == 'publishers':
                    result = analyze_publishers_overall(df_overall, logger)
                elif func_name == 'classification':
                    result = analyze_classification_overall(df_overall, logger)

                # 保存总体
                func_dir = analyze_root / func_name / '总体'
                func_dir.mkdir(parents=True, exist_ok=True)
                # attitude函数保存为attitude.json，geography函数保存为geography.json，keywords函数保存为keywords.json，publishers函数保存为publishers.json，trends函数保存为trends.json，volume函数保存为volume.json，classification函数保存为classification.json，其他函数保存为result.json
                if func_name == 'attitude':
                    filename = 'attitude.json'
                elif func_name == 'geography':
                    filename = 'geography.json'
                elif func_name == 'keywords':
                    filename = 'keywords.json'
                elif func_name == 'publishers':
                    filename = 'publishers.json'
                elif func_name == 'trends':
                    filename = 'trends.json'
                elif func_name == 'volume':
                    filename = 'volume.json'
                elif func_name == 'classification':
                    filename = 'classification.json'
                else:
                    filename = 'result.json'
                output_file = func_dir / filename
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result or {}, f, ensure_ascii=False, indent=2, default=str)

                _post_process_result(func_name, '总体', func_dir, result, ai_summary_entries, ai_state, logger)

                success_count += 1

            elif target == '渠道':
                # 逐渠道运行
                any_success = False
                for channel_name, jsonl_path in channel_files.items():
                    try:
                        df_channel = read_jsonl(jsonl_path)
                    except Exception as e:
                        log_error(logger, f"读取渠道 {channel_name} 数据失败: {e}", "Analysis")
                        continue

                    result = None
                    if func_name == 'volume':
                        result = analyze_volume_by_channel(df_channel, channel_name, topic, date, logger, end_date)
                    elif func_name == 'trends':
                        result = analyze_trends_by_channel(df_channel, channel_name, logger)
                    elif func_name == 'publishers':
                        result = analyze_publishers_by_channel(df_channel, channel_name, logger)
                    elif func_name == 'keywords':
                        result = analyze_keywords_by_channel(df_channel, topic, channel_name, logger)
                    elif func_name == 'attitude':
                        result = analyze_attitude_by_channel(df_channel, channel_name, logger)
                    elif func_name == 'geography':
                        result = analyze_geography_by_channel(df_channel, channel_name, logger)
                    elif func_name == 'classification':
                        result = analyze_classification_by_channel(df_channel, channel_name, logger)

                    func_dir = analyze_root / func_name / channel_name
                    func_dir.mkdir(parents=True, exist_ok=True)
                    # attitude函数保存为attitude.json，geography函数保存为geography.json，keywords函数保存为keywords.json，publishers函数保存为publishers.json，trends函数保存为trends.json，volume函数保存为volume.json，classification函数保存为classification.json，其他函数保存为result.json
                    if func_name == 'attitude':
                        filename = 'attitude.json'
                    elif func_name == 'geography':
                        filename = 'geography.json'
                    elif func_name == 'keywords':
                        filename = 'keywords.json'
                    elif func_name == 'publishers':
                        filename = 'publishers.json'
                    elif func_name == 'trends':
                        filename = 'trends.json'
                    elif func_name == 'volume':
                        filename = 'volume.json'
                    elif func_name == 'classification':
                        filename = 'classification.json'
                    else:
                        filename = 'result.json'
                    output_file = func_dir / filename
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(result or {}, f, ensure_ascii=False, indent=2, default=str)

                    _post_process_result(func_name, channel_name, func_dir, result, ai_summary_entries, ai_state, logger)

                    any_success = True

                if any_success:
                    success_count += 1

        except Exception as e:
            log_error(logger, f"{func_name}_{target}: {e}", "Analysis")
            continue
    
    if ai_state.get('dirty'):
        _save_ai_summary_file(ai_summary_file, topic, date, end_date, ai_summary_entries)

    # 输出最终统计信息
    log_success(logger, "模块执行完成", "Analyze")
    
    # 返回是否成功（至少有一个函数成功）
    return success_count > 0
    
