"""
AI相关性筛选功能
"""
import json
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from ..utils.setting.paths import bucket, ensure_bucket
from ..utils.logging.logging import (
    setup_logger,
    log_success,
    log_error,
    log_skip,
    log_module_start,
)
from ..utils.setting.settings import settings
from ..utils.io.excel import write_jsonl, read_jsonl
from ..utils.ai import QwenClient, OpenAIClient
from ..utils.ai.token import count_tokens


def _load_progress(topic: str, date: str, channel: str) -> Dict[str, Any]:
    """
    加载进度记录

    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        channel (str): 渠道名称

    Returns:
        Dict[str, Any]: 进度记录
    """
    progress_file = Path(__file__).parent / f"{topic}_{date}_{channel}_progress.json"
    if progress_file.exists():
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_indices": [], "failed_indices": [], "total_count": 0, "results": []}


def _save_progress(topic: str, date: str, channel: str, progress: Dict[str, Any]) -> None:
    """
    保存进度记录

    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        channel (str): 渠道名称
        progress (Dict[str, Any]): 进度记录
    """
    try:
        progress_file = Path(__file__).parent / f"{topic}_{date}_{channel}_progress.json"
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except Exception as exc:  # pragma: no cover - 记录失败不影响流程
        print(f"保存进度记录失败: {exc}")


def _save_partial_results(topic: str, date: str, channel: str, results_df: pd.DataFrame) -> None:
    """
    保存部分结果到JSONL文件

    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        channel (str): 渠道名称
        results_df (pd.DataFrame): 结果数据框
    """
    if results_df.empty:
        return

    try:
        dst = ensure_bucket("filter", topic, date)
        output_file = dst / f"{channel}.jsonl"

        if output_file.exists():
            try:
                existing_df = read_jsonl(output_file)
            except Exception:
                existing_df = pd.DataFrame()
            combined_df = pd.concat([existing_df, results_df], ignore_index=True)
            if "contents" in combined_df.columns:
                combined_df = combined_df.drop_duplicates(subset=["contents"], keep="last")
            write_jsonl(combined_df, output_file)
        else:
            write_jsonl(results_df, output_file)
    except Exception as exc:  # pragma: no cover - 写入失败不应中断整体流程
        print(f"保存部分结果失败: {exc}")


def _clear_progress(topic: str, date: str, channel: str) -> None:
    """
    清理进度记录文件

    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        channel (str): 渠道名称
    """
    try:
        progress_file = Path(__file__).parent / f"{topic}_{date}_{channel}_progress.json"
        if progress_file.exists():
            progress_file.unlink()
    except Exception:
        pass


def _truncate(text: str, max_tokens: int, min_keep: int) -> str:
    """
    截断文本到指定长度
    
    Args:
        text (str): 待截断文本
        max_tokens (int): 最大token数
        min_keep (int): 最小保留长度
    
    Returns:
        str: 截断后的文本
    """
    if not isinstance(text, str):
        return ""
    if len(text) <= max_tokens:
        return text
    # 优先按句号裁切
    parts = text.split('。')
    buf = []
    total = 0
    for p in parts:
        seg = (p + '。') if p else ''
        if total + len(seg) <= max_tokens:
            buf.append(seg)
            total += len(seg)
        else:
            break
    cut = ''.join(buf)
    if len(cut) >= min_keep:
        return cut
    return text[:max_tokens]


def _parse_response(raw: str) -> Dict[str, Any]:
    """
    解析API响应
    
    Args:
        raw (str): 原始响应文本
    
    Returns:
        Dict[str, Any]: 解析后的响应数据
    """
    try:
        s = raw.strip()
        # 去掉常见围栏
        if s.startswith('```'):
            s = s.split('```', 1)[-1]
            s = s.strip()
        # 直接JSON或提取JSON片段
        if s.startswith('{') and s.endswith('}'):
            return json.loads(s)
        i = s.find('{'); j = s.rfind('}')
        if i != -1 and j != -1 and j > i:
            return json.loads(s[i:j+1])
    except Exception:
        pass
    return {"相关": False, "分类": "未知", "理由": "解析失败"}


def _is_high(parsed: Dict[str, Any]) -> bool:
    """
    判断是否为高度相关
    
    Args:
        parsed (Dict[str, Any]): 解析后的响应数据
    
    Returns:
        bool: 是否为高度相关
    """
    if not isinstance(parsed, dict):
        return False
    if isinstance(parsed.get('相关'), bool):
        return bool(parsed['相关'])
    for k in ['相关性', 'relevance', 'level', 'score', '类别']:
        v = parsed.get(k)
        if isinstance(v, str):
            t = v.strip().lower()
            if ('高' in t) or ('高度相关' in t) or (t in ['high', 'highly relevant', 'relevant']):
                return True
    return False


def _get_classification(parsed: Dict[str, Any]) -> str:
    """
    提取分类信息
    
    Args:
        parsed (Dict[str, Any]): 解析后的响应数据
    
    Returns:
        str: 分类结果
    """
    if not isinstance(parsed, dict):
        return "未知"
    
    # 优先从"分类"字段获取
    classification = parsed.get('分类', '')
    if isinstance(classification, str) and classification.strip():
        return classification.strip()
    
    # 尝试其他可能的字段名
    for key in ['类别', 'category', 'type', 'class']:
        value = parsed.get(key, '')
        if isinstance(value, str) and value.strip():
            return value.strip()
    
    return "未知"


async def run_filter_async(topic: str, date: str, logger=None) -> bool:
    """
    运行相关性筛选

    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器

    Returns:
        bool: 是否成功
    """
    if logger is None:
        logger = setup_logger(topic, date)

    log_module_start(logger, "Filter")

    # 读取配置
    llm_cfg = settings.get("llm", {}).get("filter_llm", {})
    provider = (llm_cfg.get("provider") or "qwen").lower()
    if provider == "openai":
        model = llm_cfg.get("model", "gpt-3.5-turbo")
    else:
        provider = "qwen"
        model = llm_cfg.get("model", "qwen-plus")
    qps = int(llm_cfg.get("qps", 200))
    max_tokens = int(llm_cfg.get("truncation", 200))
    batch_size = int(llm_cfg.get("batch_size", 32))

    log_success(
        logger,
        f"使用模型: {model} (provider={provider}), QPS: {qps}, 截断长度: {max_tokens}, 批次大小: {batch_size}",
        "Filter",
    )

    # 读取提示词模板
    prompt_config_path = Path(f"configs/prompt/filter/{topic}.yaml")
    if not prompt_config_path.exists():
        log_error(logger, f"未找到提示词配置文件: {prompt_config_path}", "Filter")
        return False

    try:
        import yaml
        with open(prompt_config_path, 'r', encoding='utf-8') as f:
            prompt_cfg = yaml.safe_load(f)
        template = prompt_cfg.get('template', '').strip()
        if not template:
            log_error(logger, "提示词模板为空", "Filter")
            return False
    except Exception as e:
        log_error(logger, f"读取提示词配置失败: {e}", "Filter")
        return False

    clean_dir = bucket("clean", topic, date)
    files = sorted(clean_dir.glob("*.jsonl"))
    if not files:
        log_error(logger, f"未找到清洗数据: {clean_dir}", "Filter")
        return False

    # 初始化客户端
    if provider == "openai":
        client = OpenAIClient()
    else:
        client = QwenClient()
    total_tasks = 0
    successful_tasks = 0
    total_tokens = 0

    # QPS控制
    last_request_time = time.time()

    async def call_with_qps(
        prompt: str,
        idx: int,
        channel: str,
        max_retries: int = 3,
    ) -> Tuple[int, Optional[str], int, bool]:
        """
        带QPS控制和重试机制的API调用

        Args:
            prompt (str): 提示词
            idx (int): 任务索引
            channel (str): 渠道名称
            max_retries (int): 最大重试次数

        Returns:
            Tuple[int, Optional[str], int, bool]: (索引, 响应内容, token消耗, 是否成功)
        """
        nonlocal last_request_time

        for attempt in range(max_retries + 1):
            try:
                # QPS控制 - 更保守的延迟
                current_time = time.time()
                time_diff = current_time - last_request_time
                min_interval = 1.0 / qps
                
                # 添加额外的安全间隔，避免API过载
                if time_diff < min_interval * 1.2:  # 增加20%的安全间隔
                    await asyncio.sleep(min_interval * 1.2 - time_diff)
                
                last_request_time = time.time()

                # 调用模型客户端执行推理
                result = await client.call(prompt, model, max_tokens)

                if result and result.get("text"):
                    text_response = result["text"]
                    usage_info = result.get("usage", {})

                    # 解析响应并判断相关性
                    parsed = _parse_response(text_response)
                    is_relevant = _is_high(parsed)
                    classification = _get_classification(parsed)

                    # 获取实际token消耗
                    total_token_usage = usage_info.get("total_tokens", 0)
                    if total_token_usage == 0:
                        # 如果API没有返回token信息，则使用token计算器
                        input_tokens = count_tokens(prompt, model, provider)
                        output_tokens = count_tokens(text_response, model, provider)
                        total_token_usage = input_tokens + output_tokens

                    # 显示判断结果而不是原始响应
                    result_text = "相关" if is_relevant else "不相关"
                    if attempt > 0:
                        log_success(
                            logger,
                            f"[{channel}] 任务{idx} 成功 (重试{attempt}次) | 结果: {result_text} | 分类: {classification} | Token: {total_token_usage}",
                            "Filter",
                        )
                    else:
                        log_success(
                            logger,
                            f"[{channel}] 任务{idx} 成功 | 结果: {result_text} | 分类: {classification} | Token: {total_token_usage}",
                            "Filter",
                        )

                    return idx, text_response, total_token_usage, True
                else:
                    if attempt < max_retries:
                        # 重试前等待更长时间
                        wait_time = (attempt + 1) * 2  # 递增等待时间
                        log_error(
                            logger,
                            f"[{channel}] 任务{idx} 失败，{wait_time}秒后重试 (第{attempt + 1}次)",
                            "Filter",
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        log_error(logger, f"[{channel}] 任务{idx} 失败 | 无响应 (已重试{max_retries}次)", "Filter")
                        return idx, None, 0, False

            except Exception as e:
                if attempt < max_retries:
                    wait_time = (attempt + 1) * 2
                    log_error(
                        logger,
                        f"[{channel}] 任务{idx} 异常，{wait_time}秒后重试 (第{attempt + 1}次) | {str(e)}",
                        "Filter",
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    log_error(logger, f"[{channel}] 任务{idx} 异常 | {str(e)} (已重试{max_retries}次)", "Filter")
                    return idx, None, 0, False

        return idx, None, 0, False

    # 处理每个渠道
    for fp in files:
        channel = fp.stem
        if channel == "all":
            continue

        log_success(logger, f"开始处理渠道: {channel}", "Filter")
        try:
            df = read_jsonl(fp)
            if df.empty:
                log_skip(logger, f"{channel} 空数据，跳过", "Filter")
                continue

            # 加载进度记录
            progress = _load_progress(topic, date, channel)
            completed_indices = set(progress.get("completed_indices", []))
            failed_indices = set(progress.get("failed_indices", []))

            # 构建 prompts 并过滤已完成的任务
            texts: List[str] = []
            pending_indices: List[int] = []

            for idx, (_, r) in enumerate(df.iterrows()):
                if idx in completed_indices:
                    continue

                c = r.get("contents", "")
                if isinstance(c, str) and c.strip():
                    texts.append(_truncate(c, max_tokens, 50))  # min_keep设为50
                    pending_indices.append(idx)
                else:
                    completed_indices.add(idx)
                    failed_indices.discard(idx)

            if not texts:
                progress["completed_indices"] = list(completed_indices)
                progress["failed_indices"] = list(failed_indices)
                progress["total_count"] = len(df)
                _save_progress(topic, date, channel, progress)

                if completed_indices:
                    log_success(logger, f"{channel} 所有任务已完成，跳过", "Filter")
                else:
                    log_skip(logger, f"{channel} 无有效文段，跳过", "Filter")
                continue

            prompts = [template.replace("{text}", t) for t in texts]

            if completed_indices or failed_indices:
                log_success(
                    logger,
                    f"{channel} 断点续传 | 已完成:{len(completed_indices)}, 失败:{len(failed_indices)}, 待处理:{len(texts)}",
                    "Filter",
                )

            actual_batch_size = batch_size
            channel_tokens = 0

            try:
                for i in range(0, len(prompts), actual_batch_size):
                    batch_prompts = prompts[i : i + actual_batch_size]
                    batch_indices = pending_indices[i : i + actual_batch_size]

                    batch_tasks = [
                        asyncio.create_task(call_with_qps(prompt, batch_indices[j], channel))
                        for j, prompt in enumerate(batch_prompts)
                    ]

                    current_batch_results = await asyncio.gather(*batch_tasks)

                    batch_tokens = 0
                    batch_responses: List[Optional[str]] = []
                    for (idx, response, tokens, success), original_idx in zip(
                        current_batch_results, batch_indices
                    ):
                        total_tasks += 1
                        batch_tokens += tokens
                        channel_tokens += tokens
                        batch_responses.append(response)

                        if response and success:
                            successful_tasks += 1
                            total_tokens += tokens
                            completed_indices.add(idx)
                            failed_indices.discard(idx)
                        else:
                            failed_indices.add(original_idx)

                    parsed_batch = [_parse_response(r or "") for r in batch_responses]
                    mask_batch = [_is_high(p) for p in parsed_batch]
                    classifications_batch = [_get_classification(p) for p in parsed_batch]

                    batch_df = df.iloc[batch_indices].copy()
                    batch_df["rel_raw"] = parsed_batch
                    batch_df["rel_score"] = mask_batch
                    batch_df["classification"] = classifications_batch

                    relevant_batch = batch_df[batch_df["rel_score"] == True]  # noqa: E712
                    if not relevant_batch.empty:
                        original_cols = [
                            c for c in df.columns if c not in ["rel_raw", "rel_score", "classification"]
                        ]
                        if all(col in relevant_batch.columns for col in original_cols):
                            to_save = relevant_batch[original_cols + ["classification"]]
                        else:
                            to_save = relevant_batch.drop(columns=["rel_raw", "rel_score"], errors="ignore")
                        _save_partial_results(topic, date, channel, to_save)

                    progress["completed_indices"] = list(completed_indices)
                    progress["failed_indices"] = list(failed_indices)
                    progress["total_count"] = len(df)
                    _save_progress(topic, date, channel, progress)

                    log_success(
                        logger,
                        f"{channel} 批次完成 | 进度:{len(completed_indices)}/{len(df)}, Token:{batch_tokens}",
                        "Filter",
                    )

            except KeyboardInterrupt:
                log_error(logger, f"{channel} 用户中断，保存当前进度", "Filter")
                progress["completed_indices"] = list(completed_indices)
                progress["failed_indices"] = list(failed_indices)
                progress["total_count"] = len(df)
                _save_progress(topic, date, channel, progress)
                raise
            except Exception as exc:
                log_error(logger, f"{channel} 处理异常，保存当前进度: {exc}", "Filter")
                progress["completed_indices"] = list(completed_indices)
                progress["failed_indices"] = list(failed_indices)
                progress["total_count"] = len(df)
                _save_progress(topic, date, channel, progress)
                continue

            total_completed = len(completed_indices)
            total_failed = len(failed_indices)

            if total_completed == len(df):
                log_success(
                    logger,
                    f"{channel} 完全完成 | 原始:{len(df)}, Token消耗:{channel_tokens}",
                    "Filter",
                )
            else:
                log_success(
                    logger,
                    f"{channel} 部分完成 | 原始:{len(df)}, 已完成:{total_completed}, 失败:{total_failed}, Token消耗:{channel_tokens}",
                    "Filter",
                )

        except Exception as e:
            log_error(logger, f"{channel} 处理失败: {e}", "Filter")
            continue

    # 最终汇总与进度清理
    all_channels_fully_completed = True
    for fp in files:
        channel = fp.stem
        if channel == "all":
            continue
        progress = _load_progress(topic, date, channel)
        completed_indices = set(progress.get("completed_indices", []))
        total_count = progress.get("total_count", 0)
        if total_count > 0 and len(completed_indices) < total_count:
            all_channels_fully_completed = False
            break

    if all_channels_fully_completed:
        log_success(logger, "所有渠道完全完成，清理进度记录文件", "Filter")
        for fp in files:
            channel = fp.stem
            if channel != "all":
                _clear_progress(topic, date, channel)
        log_success(
            logger,
            f"筛选完全完成汇总 | 总任务:{total_tasks}, 成功:{successful_tasks}, 总Token:{total_tokens}",
            "Filter",
        )
    else:
        log_success(
            logger,
            f"筛选部分完成汇总 | 总任务:{total_tasks}, 成功:{successful_tasks}, 总Token:{total_tokens}",
            "Filter",
        )
        log_success(logger, "部分渠道未完成，进度记录已保存，可重新运行继续处理", "Filter")

    return successful_tasks > 0


def run_filter(topic: str, date: str, logger=None) -> bool:
    """
    同步运行相关性筛选
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        logger: 日志记录器
    
    Returns:
        bool: 是否成功
    """
    return asyncio.run(run_filter_async(topic, date, logger))
