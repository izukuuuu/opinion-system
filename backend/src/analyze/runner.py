"""
分析运行器模块
"""
import asyncio
import json
from datetime import datetime, timezone
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from ..utils.setting.paths import bucket
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error, log_save_success, log_skip
from ..utils.setting.settings import settings
from ..utils.io.excel import read_jsonl
from ..utils.ai import call_langchain_chat, get_qwen_client
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

ANALYZE_FILE_MAP = {
    "volume": "volume.json",
    "attitude": "attitude.json",
    "trends": "trends.json",
    "geography": "geography.json",
    "publishers": "publishers.json",
    "keywords": "keywords.json",
    "classification": "classification.json",
}

DEFAULT_ANALYZE_FILENAME = "result.json"
SUMMARY_FILENAME = "summary.txt"
AI_SUMMARY_FILENAME = "ai_summary.json"
MAX_SNAPSHOT_ROWS = 5
MAIN_FINDING_CONTEXT_LIMIT = 7
MAIN_FINDING_TEXT_LIMIT = 420

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


def _compose_analyze_folder(date: str, end_date: Optional[str]) -> str:
    date_text = str(date or "").strip()
    end_text = str(end_date or "").strip()
    if not date_text:
        return ""
    if end_text:
        return f"{date_text}_{end_text}"
    return date_text


def _split_analyze_folder(folder: str) -> Tuple[str, str]:
    folder_text = str(folder or "").strip()
    if not folder_text:
        return "", ""
    if "_" in folder_text:
        start, end = folder_text.split("_", 1)
        start_text = str(start or "").strip()
        end_text = str(end or "").strip() or start_text
        return start_text, end_text
    return folder_text, folder_text


def _resolve_analyze_filename(func_name: str) -> str:
    return ANALYZE_FILE_MAP.get(str(func_name or "").strip(), DEFAULT_ANALYZE_FILENAME)


def _load_json_result_file(file_path: Path) -> Any:
    with open(file_path, 'r', encoding='utf-8') as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            fh.seek(0)
            return fh.read()


def _generate_ai_summary(func_name: str, target: str, snapshot: str, logger) -> str:
    if not snapshot.strip():
        return ""
    label = FUNCTION_LABELS.get(func_name, func_name)

    # 根据模块类型添加数据定义说明
    data_hints = ""
    if func_name == 'geography':
        data_hints = "\n数据定义：统计结果中的"-"表示未标注地域信息的数据条目，不属于具体地域分布。"
    elif func_name == 'publishers':
        data_hints = "\n数据定义：统计结果中的"-"表示无发布者信息的数据条目，通常不纳入发布者主体分析。"

    prompt = (
        "你是一名资深舆情分析师。基于以下统计快照，以不超过80字的中文总结核心洞察，不要输出列表或多段。"
        f"\n模块：{label}"
        f"\n范围：{target}"
        f"{data_hints}"
        f"\n统计数据：\n{snapshot}"
        "\n请直接输出精炼结论。"
    )
    try:
        langchain_text = _safe_async_call(
            call_langchain_chat(
                [
                    {"role": "system", "content": "你是一名资深舆情分析师。"},
                    {"role": "user", "content": prompt},
                ],
                task="analyze_summary",
                max_tokens=400,
            )
        )
        if isinstance(langchain_text, str) and langchain_text.strip():
            return langchain_text.strip()
    except Exception as exc:  # pragma: no cover - 外部依赖
        log_error(logger, f"LangChain 摘要生成失败：{exc}", "Analysis")

    client = _get_ai_client(logger)
    if not client:
        return ""
    try:
        response = _safe_async_call(client.call(prompt, model="qwen-plus", max_tokens=400))
    except Exception as exc:  # pragma: no cover - 外部依赖
        log_error(logger, f"AI摘要生成失败：{exc}", "Analysis")
        return ""
    if not response:
        return ""
    text = response.get('text') or ''
    return text.strip()


def _collect_main_finding_context(entries: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    contexts: List[Dict[str, str]] = []
    for key in sorted(entries.keys()):
        entry = entries[key]
        if entry.get('target') not in (None, '', '总体'):
            continue
        label = entry.get('function_label') or entry.get('function') or '未命名'
        text = (entry.get('ai_summary') or entry.get('text_snapshot') or '').strip()
        if not text:
            continue
        contexts.append({
            "label": label,
            "text": text[:MAIN_FINDING_TEXT_LIMIT]
        })
    return contexts[:MAIN_FINDING_CONTEXT_LIMIT]


def _generate_main_finding_text(topic: str, start: str, end: Optional[str], contexts: List[Dict[str, str]], logger) -> str:
    if not contexts:
        return ""
    time_range = f"{start}→{end or start}"
    topics_text = []
    for item in contexts:
        label = item.get('label') or '模块'
        text = (item.get('text') or '').strip()
        if not text:
            continue
        topics_text.append(f"【{label}】{text}")
    prompt_parts = [
        "你是一名资深舆情分析师，请基于不同分析模块的摘要，提炼一个整体主要发现。",
        "输出要求：",
        "1）用 2-3 句话完成，不要使用序号或项目符号；",
        "2）要融合情绪、声量、趋势、话题与渠道等关键信号，避免逐条罗列模块；",
        "3）语气客观精炼，控制在 120 字以内。",
        f"分析时间段：{time_range}，专题：{topic or '当前专题'}。",
        "以下是各模块的AI解读或数据快照：",
        "\n\n".join(topics_text),
        "\n请直接输出主要发现的两到三句话。"
    ]
    prompt = "\n".join(prompt_parts)
    try:
        langchain_text = _safe_async_call(
            call_langchain_chat(
                [
                    {"role": "system", "content": "你是一名资深舆情分析师。"},
                    {"role": "user", "content": prompt},
                ],
                task="analyze_summary",
                max_tokens=400,
            )
        )
        if isinstance(langchain_text, str) and langchain_text.strip():
            return langchain_text.strip()
    except Exception as exc:  # pragma: no cover - 外部依赖
        log_error(logger, f"LangChain 总体发现生成失败：{exc}", "Analysis")

    client = _get_ai_client(logger)
    if not client:
        return ""
    try:
        response = _safe_async_call(client.call(prompt, model="qwen-plus", max_tokens=400))
    except Exception as exc:  # pragma: no cover - 外部依赖
        log_error(logger, f"AI总体发现生成失败：{exc}", "Analysis")
        return ""
    text = response.get('text') if response else ''
    return (text or '').strip()


def _fallback_main_finding(contexts: List[Dict[str, str]]) -> str:
    if not contexts:
        return ""
    snippets: List[str] = []
    for ctx in contexts[:3]:
        text = (ctx.get('text') or '').strip()
        if not text:
            continue
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), '')
        if first_line:
            snippets.append(first_line)
    if not snippets:
        return ""
    merged = "；".join(snippets)
    return merged[:200]


def _build_main_finding(ai_entries: Dict[str, Dict[str, Any]], previous: Optional[Dict[str, Any]], topic: str, start: str, end: Optional[str], logger) -> Optional[Dict[str, Any]]:
    contexts = _collect_main_finding_context(ai_entries)
    if not contexts:
        return previous
    ai_text = _generate_main_finding_text(topic, start, end, contexts, logger)
    summary_text = ai_text or _fallback_main_finding(contexts)
    if not summary_text:
        return previous
    candidate = {
        "summary": summary_text,
        "source_functions": [ctx['label'] for ctx in contexts],
        "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
    }
    if previous and (previous.get('summary') or '').strip() == candidate['summary'].strip():
        return previous
    return candidate


def _load_existing_ai_summary(path: Path) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not path.exists():
        return {}, None
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            payload = json.load(fh)
        entries = {}
        for item in payload.get('summaries', []):
            key = f"{item.get('function')}::{item.get('target', '总体')}"
            entries[key] = item
        main_finding = payload.get('main_finding') if isinstance(payload.get('main_finding'), dict) else None
        return entries, main_finding
    except Exception:
        return {}, None


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


def _save_ai_summary_file(path: Path, topic: str, start: str, end: Optional[str], entries: Dict[str, Dict[str, Any]], main_finding: Optional[Dict[str, Any]] = None):
    if not entries and not main_finding:
        return
    payload = {
        "topic": topic,
        "range": {"start": start, "end": end or start},
        "generated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "summaries": [entries[key] for key in sorted(entries.keys())],
    }
    if main_finding and (main_finding.get('summary') or '').strip():
        payload["main_finding"] = {
            "summary": (main_finding.get('summary') or '').strip(),
            "source_functions": main_finding.get('source_functions') or [],
            "updated_at": main_finding.get('updated_at') or datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
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


def _supplement_ai_summary_from_analyze(
    topic: str,
    date: str,
    logger=None,
    only_function: str = None,
    end_date: str = None,
) -> bool:
    folder_name = _compose_analyze_folder(date, end_date)
    return rebuild_ai_summary_from_analyze_folder(
        topic,
        folder_name,
        logger=logger,
        only_function=only_function,
    )


def rebuild_ai_summary_from_analyze_folder(
    topic: str,
    folder_name: str,
    logger=None,
    only_function: str = None,
) -> bool:
    if logger is None:
        log_date, _ = _split_analyze_folder(folder_name)
        logger = setup_logger(topic, log_date or str(folder_name or "").strip() or "analyze")

    folder_name = str(folder_name or "").strip()
    if not folder_name:
        return False
    analyze_root = bucket("analyze", topic, folder_name)
    if not analyze_root.exists() or not analyze_root.is_dir():
        return False

    function_dirs = [child for child in analyze_root.iterdir() if child.is_dir()]
    if only_function:
        alias = only_function.strip().lower()
        function_dirs = [child for child in function_dirs if child.name.strip().lower() == alias]
        if not function_dirs:
            return False

    ai_summary_file = analyze_root / AI_SUMMARY_FILENAME
    ai_summary_entries, previous_main_finding = _load_existing_ai_summary(ai_summary_file)
    ai_state = {"dirty": False}
    processed_count = 0

    for func_dir in sorted(function_dirs, key=lambda path: path.name):
        func_name = func_dir.name
        for target_dir in sorted([child for child in func_dir.iterdir() if child.is_dir()], key=lambda path: path.name):
            output_file = target_dir / _resolve_analyze_filename(func_name)
            if not output_file.exists():
                json_candidates = sorted(target_dir.glob("*.json"))
                if json_candidates:
                    output_file = json_candidates[0]
                else:
                    continue
            try:
                result = _load_json_result_file(output_file)
            except Exception as exc:
                log_error(logger, f"读取分析产物失败: {output_file} ({exc})", "Analysis")
                continue
            _post_process_result(func_name, target_dir.name, target_dir, result, ai_summary_entries, ai_state, logger)
            processed_count += 1

    if processed_count == 0:
        return False

    start_date, end_date = _split_analyze_folder(folder_name)
    start_for_save = start_date or folder_name
    end_for_save = end_date or start_for_save

    main_finding = _build_main_finding(
        ai_summary_entries,
        previous_main_finding,
        topic,
        start_for_save,
        end_for_save,
        logger,
    )
    if main_finding and main_finding is not previous_main_finding:
        ai_state['dirty'] = True

    if ai_state.get('dirty'):
        _save_ai_summary_file(
            ai_summary_file,
            topic,
            start_for_save,
            end_for_save,
            ai_summary_entries,
            main_finding,
        )
        log_save_success(logger, str(ai_summary_file), "Analysis")
    else:
        log_skip(logger, "AI摘要无变化，跳过写入", "Analysis")

    return True


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
    folder_name = _compose_analyze_folder(date, end_date)
    if not folder_name:
        log_error(logger, "无效日期参数，无法定位分析目录", "Analysis")
        return False

    fetch_dir = bucket("fetch", topic, folder_name)
    if not fetch_dir.exists():
        log_skip(logger, f"未找到 fetch 目录，尝试基于已有 analyze 结果补充AI摘要: {fetch_dir}", "Analysis")
        if _supplement_ai_summary_from_analyze(topic, date, logger, only_function=only_function, end_date=end_date):
            log_success(logger, "已基于历史 analyze 结果补充AI摘要", "Analyze")
            return True
        log_error(logger, f"未找到数据目录: {fetch_dir}", "Analysis")
        return False
    overall_file = fetch_dir / "总体.jsonl"
    if not overall_file.exists():
        log_skip(logger, f"未找到总体数据文件，尝试基于已有 analyze 结果补充AI摘要: {overall_file}", "Analysis")
        if _supplement_ai_summary_from_analyze(topic, date, logger, only_function=only_function, end_date=end_date):
            log_success(logger, "已基于历史 analyze 结果补充AI摘要", "Analyze")
            return True
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
    analyze_root = bucket("analyze", topic, folder_name)
    analyze_root.mkdir(parents=True, exist_ok=True)

    ai_summary_file = analyze_root / AI_SUMMARY_FILENAME
    ai_summary_entries, previous_main_finding = _load_existing_ai_summary(ai_summary_file)
    ai_state = {"dirty": False}
    main_finding = previous_main_finding
    
    success_count = 0
    
    # 若仅运行单功能，先做一次过滤（支持别名与大小写不敏感）
    if only_function:
        alias = only_function.strip()
        alias_norm = alias.lower()
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
                filename = _resolve_analyze_filename(func_name)
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
                    filename = _resolve_analyze_filename(func_name)
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
    
    main_finding = _build_main_finding(ai_summary_entries, previous_main_finding, topic, date, end_date, logger)
    if main_finding and main_finding is not previous_main_finding:
        ai_state['dirty'] = True

    should_save = bool(ai_state.get('dirty'))
    if not should_save and main_finding and main_finding is not previous_main_finding:
        should_save = True

    if should_save:
        _save_ai_summary_file(ai_summary_file, topic, date, end_date, ai_summary_entries, main_finding)

    # 输出最终统计信息
    log_success(logger, "模块执行完成", "Analyze")
    
    # 返回是否成功（至少有一个函数成功）
    return success_count > 0


def run_Analyze_with_progress(
    topic: str,
    date: str,
    logger=None,
    only_function: str = None,
    end_date: str = None,
    progress_callback=None,
    max_workers: int = 4,
) -> bool:
    """
    运行分析任务（支持进度回调和多线程）。

    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
        only_function (str, optional): 仅运行指定分析函数
        end_date (str, optional): 结束日期
        progress_callback: 进度回调函数，签名: callback(payload: Dict[str, Any]) -> None
            payload 包含: phase, percentage, message, total_functions, completed_functions,
                          current_function, current_target
        max_workers: 多线程处理的最大线程数，默认4

    Returns:
        bool: 是否成功
    """
    import concurrent.futures
    from datetime import datetime, timezone

    def _emit_progress(
        phase: str,
        percentage: int,
        message: str,
        *,
        total_functions: int = 0,
        completed_functions: int = 0,
        current_function: str = "",
        current_target: str = "",
        sentiment_phase: str = "",
        sentiment_total: int = 0,
        sentiment_processed: int = 0,
        sentiment_classified: int = 0,
        sentiment_remaining: int = 0,
    ) -> None:
        if progress_callback:
            try:
                progress_callback({
                    "phase": phase,
                    "percentage": percentage,
                    "message": message,
                    "total_functions": total_functions,
                    "completed_functions": completed_functions,
                    "current_function": current_function,
                    "current_target": current_target,
                    "sentiment_phase": sentiment_phase,
                    "sentiment_total": sentiment_total,
                    "sentiment_processed": sentiment_processed,
                    "sentiment_classified": sentiment_classified,
                    "sentiment_remaining": sentiment_remaining,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                pass

    if logger is None:
        logger = setup_logger(topic, date)

    log_module_start(logger, "Analyze")

    _emit_progress("prepare", 5, "正在加载分析配置。")

    # 获取分析配置
    analysis_config = settings.get_analysis_config()
    functions = analysis_config.get('functions', [])

    if not functions:
        log_error(logger, "未配置分析函数", "Analysis")
        _emit_progress("error", 0, "未配置分析函数")
        return False

    # 读取数据
    folder_name = _compose_analyze_folder(date, end_date)
    if not folder_name:
        log_error(logger, "无效日期参数，无法定位分析目录", "Analysis")
        _emit_progress("error", 0, "无效日期参数")
        return False

    fetch_dir = bucket("fetch", topic, folder_name)
    if not fetch_dir.exists():
        log_skip(logger, f"未找到 fetch 目录，尝试基于已有 analyze 结果补充AI摘要: {fetch_dir}", "Analysis")
        if _supplement_ai_summary_from_analyze(topic, date, logger, only_function=only_function, end_date=end_date):
            log_success(logger, "已基于历史 analyze 结果补充AI摘要", "Analyze")
            _emit_progress("completed", 100, "已基于历史 analyze 结果补充AI摘要")
            return True
        log_error(logger, f"未找到数据目录: {fetch_dir}", "Analysis")
        _emit_progress("error", 0, f"未找到数据目录: {fetch_dir}")
        return False

    overall_file = fetch_dir / "总体.jsonl"
    if not overall_file.exists():
        log_skip(logger, f"未找到总体数据文件，尝试基于已有 analyze 结果补充AI摘要: {overall_file}", "Analysis")
        if _supplement_ai_summary_from_analyze(topic, date, logger, only_function=only_function, end_date=end_date):
            log_success(logger, "已基于历史 analyze 结果补充AI摘要", "Analyze")
            _emit_progress("completed", 100, "已基于历史 analyze 结果补充AI摘要")
            return True
        log_error(logger, f"未找到总体数据文件: {overall_file}", "Analysis")
        _emit_progress("error", 0, f"未找到总体数据文件: {overall_file}")
        return False

    try:
        df_overall = read_jsonl(overall_file)
    except Exception as e:
        log_error(logger, f"读取总体数据失败: {e}", "Analysis")
        _emit_progress("error", 0, f"读取总体数据失败: {e}")
        return False

    # 收集渠道文件
    channel_files: Dict[str, Path] = {}
    for jsonl_path in fetch_dir.glob("*.jsonl"):
        if jsonl_path.name == "总体.jsonl":
            continue
        channel_name = jsonl_path.stem
        channel_files[channel_name] = jsonl_path

    # 创建输出目录
    analyze_root = bucket("analyze", topic, folder_name)
    analyze_root.mkdir(parents=True, exist_ok=True)

    ai_summary_file = analyze_root / AI_SUMMARY_FILENAME
    ai_summary_entries, previous_main_finding = _load_existing_ai_summary(ai_summary_file)
    ai_state = {"dirty": False}
    main_finding = previous_main_finding

    _emit_progress("prepare", 10, f"已加载配置，共 {len(functions)} 个分析项待处理。")

    # 若仅运行单功能，先做一次过滤
    if only_function:
        alias = only_function.strip()
        alias_norm = alias.lower()
        functions = [f for f in functions if (f.get('name', '').strip().lower() == alias_norm)]
        if not functions:
            log_error(logger, f"--func 未匹配到任何分析项：{only_function}", "Analysis")
            _emit_progress("error", 0, f"未匹配到分析项: {only_function}")
            return False

    total_functions = len(functions)
    completed_functions = 0
    success_count = 0

    # 运行分析函数
    for func_config in functions:
        func_name = func_config.get('name')
        target = func_config.get('target')

        # 执行前的进度：显示当前正在处理哪个任务
        pending_percentage = 10 + int((completed_functions / max(total_functions, 1)) * 85)
        _emit_progress(
            "analyze", pending_percentage,
            f"正在运行 {FUNCTION_LABELS.get(func_name, func_name)} ({target})",
            total_functions=total_functions,
            completed_functions=completed_functions,
            current_function=func_name,
            current_target=target,
        )

        try:
            # 情感分析子任务进度回调
            def _attitude_progress_cb(payload: Dict[str, Any]) -> None:
                sub_pct = int(payload.get("percentage") or 0)
                sub_msg = str(payload.get("message") or "").strip()
                # 情感分析详细进度
                sent_phase = str(payload.get("phase") or "").strip()
                sent_total = int(payload.get("total_unknown") or payload.get("sentiment_total") or 0)
                sent_processed = int(payload.get("processed_unknown") or payload.get("sentiment_processed") or 0)
                sent_classified = int(payload.get("classified") or payload.get("sentiment_classified") or 0)
                sent_remaining = int(payload.get("remaining") or payload.get("sentiment_remaining") or 0)
                # 将子任务进度映射到整体进度区间
                sub_base = pending_percentage
                sub_range = int(85 / max(total_functions, 1))
                overall_pct = sub_base + int((sub_pct / 100) * sub_range)
                _emit_progress(
                    "analyze", overall_pct,
                    f"{FUNCTION_LABELS.get(func_name, func_name)} ({target}) - {sub_msg}",
                    total_functions=total_functions,
                    completed_functions=completed_functions,
                    current_function=func_name,
                    current_target=target,
                    sentiment_phase=sent_phase,
                    sentiment_total=sent_total,
                    sentiment_processed=sent_processed,
                    sentiment_classified=sent_classified,
                    sentiment_remaining=sent_remaining,
                )

            if target == '总体':
                # 运行总体
                result = None
                if func_name == 'volume':
                    result = analyze_volume_overall(df_overall, topic, date, logger, end_date)
                elif func_name == 'attitude':
                    result = analyze_attitude_overall(df_overall, logger, progress_callback=_attitude_progress_cb)
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
                filename = _resolve_analyze_filename(func_name)
                output_file = func_dir / filename
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result or {}, f, ensure_ascii=False, indent=2, default=str)

                _post_process_result(func_name, '总体', func_dir, result, ai_summary_entries, ai_state, logger)
                success_count += 1
                completed_functions += 1

            elif target == '渠道':
                # 逐渠道运行（使用线程池并行处理）
                any_success = False
                channel_items = list(channel_files.items())

                def _process_channel(channel_item):
                    channel_name, jsonl_path = channel_item
                    try:
                        df_channel = read_jsonl(jsonl_path)
                    except Exception as e:
                        log_error(logger, f"读取渠道 {channel_name} 数据失败: {e}", "Analysis")
                        return None

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

                    return (channel_name, result)

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(_process_channel, item): item for item in channel_items}
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            result = future.result(timeout=60)
                            if result is None:
                                continue
                            channel_name, channel_result = result
                            func_dir = analyze_root / func_name / channel_name
                            func_dir.mkdir(parents=True, exist_ok=True)
                            filename = _resolve_analyze_filename(func_name)
                            output_file = func_dir / filename
                            with open(output_file, 'w', encoding='utf-8') as f:
                                json.dump(channel_result or {}, f, ensure_ascii=False, indent=2, default=str)
                            _post_process_result(func_name, channel_name, func_dir, channel_result, ai_summary_entries, ai_state, logger)
                            any_success = True
                        except Exception as exc:
                            log_error(logger, f"处理渠道失败: {exc}", "Analysis")

                if any_success:
                    success_count += 1
                    completed_functions += 1

        except Exception as e:
            log_error(logger, f"{func_name}_{target}: {e}", "Analysis")
            completed_functions += 1
            continue

    main_finding = _build_main_finding(ai_summary_entries, previous_main_finding, topic, date, end_date, logger)
    if main_finding and main_finding is not previous_main_finding:
        ai_state['dirty'] = True

    should_save = bool(ai_state.get('dirty'))
    if not should_save and main_finding and main_finding is not previous_main_finding:
        should_save = True

    if should_save:
        _save_ai_summary_file(ai_summary_file, topic, date, end_date, ai_summary_entries, main_finding)

    _emit_progress(
        "completed", 100,
        f"分析完成，共成功处理 {success_count} 个分析项。",
        total_functions=total_functions,
        completed_functions=total_functions,
    )

    log_success(logger, "模块执行完成", "Analyze")
    return success_count > 0
    
