"""
态度分析函数
"""
import asyncio
import pandas as pd
from typing import Dict, List, Any, Optional, Callable
from ...utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from ...utils.ai import call_langchain_chat

# AI 情感分类配置
SENTIMENT_MAX_RETRIES = 3  # 最大重试次数
SENTIMENT_RETRY_DELAY = 1.0  # 重试间隔（秒）
SENTIMENT_TEXT_MAX_LENGTH = 500  # 文本截断长度


def _normalize_attitude_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    将数据框中的情感列标准化为 attitude 字段，兼容多种列名与取值

    Args:
        df (pd.DataFrame): 数据框

    Returns:
        pd.DataFrame: 标准化后的数据框
    """
    if 'attitude' in df.columns:
        return df
    df = df.copy()
    # 候选列名（按常见命名）
    candidate_cols = [
        'polarity', 'sentiment', '情感', '情绪', '情感倾向', 'att', 'label'
    ]
    col = next((c for c in candidate_cols if c in df.columns), None)
    if col is None:
        df['attitude'] = 'unknown'
        return df
    s = df[col]
    # 标准化值
    def to_att(v):
        """
        将情感值标准化为英文标签

        Args:
            v: 原始情感值

        Returns:
            str: 标准化的情感标签
        """
        if v is None:
            return 'unknown'
        try:
            # 数字映射
            f = float(v)
            if f > 0:
                return 'positive'
            if f < 0:
                return 'negative'
            return 'neutral'
        except Exception:
            pass
        x = str(v).strip().lower()
        mapping = {
            '正面': 'positive', '积极': 'positive', 'positive': 'positive', 'pos': 'positive', 'p': 'positive',
            '负面': 'negative', '消极': 'negative', 'negative': 'negative', 'neg': 'negative', 'n': 'negative',
            '中性': 'neutral', 'neutral': 'neutral', '客观': 'neutral', 'neu': 'neutral'
        }
        return mapping.get(x, 'unknown')
    df['attitude'] = s.map(to_att)
    return df


def _truncate_text(text: str, max_length: int = SENTIMENT_TEXT_MAX_LENGTH) -> str:
    """截断文本，保留核心内容"""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def _build_single_sentiment_prompt(text: str) -> List[Dict[str, str]]:
    """构建单条文本的情感分类提示词"""
    truncated = _truncate_text(text)
    if not truncated:
        return []

    system_prompt = """你是一个专业的情感分析助手。请根据文本内容判断其情感倾向。

情感分类标准：
- positive（正面）：表达赞赏、支持、满意、喜悦、期待等积极情绪
- negative（负面）：表达批评、反对、不满、愤怒、担忧等消极情绪
- neutral（中性）：客观陈述事实，无明显情感倾向，或情感模糊难以判断

请只输出一个标签：positive、negative 或 neutral，不要输出其他内容。"""

    user_prompt = f"请判断以下文本的情感倾向：\n\n{truncated}"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _parse_single_sentiment_response(response: str) -> str:
    """解析单条情感分类结果"""
    if not response:
        return 'neutral'

    label = response.strip().lower()

    # 标准化标签
    if label in ['positive', 'pos', 'p', '正面', '积极']:
        return 'positive'
    elif label in ['negative', 'neg', 'n', '负面', '消极']:
        return 'negative'
    elif label in ['neutral', 'neu', '中性', '客观']:
        return 'neutral'

    # 尝试从文本中提取标签
    for keyword in ['positive', '正面', '积极']:
        if keyword in label:
            return 'positive'
    for keyword in ['negative', '负面', '消极']:
        if keyword in label:
            return 'negative'
    for keyword in ['neutral', '中性', '客观']:
        if keyword in label:
            return 'neutral'

    return 'neutral'


async def _classify_single_with_retry(
    text: str,
    logger,
    max_retries: int = SENTIMENT_MAX_RETRIES,
    retry_delay: float = SENTIMENT_RETRY_DELAY,
) -> str:
    """带重试机制的单条情感分类"""
    messages = _build_single_sentiment_prompt(text)
    if not messages:
        return 'neutral'

    for attempt in range(max_retries):
        try:
            response = await call_langchain_chat(
                messages,
                task="analyze",
                max_tokens=50,
                timeout=30,
                max_retries=1,
            )

            if response:
                return _parse_single_sentiment_response(response)

        except Exception as e:
            if logger and attempt < max_retries - 1:
                log_error(
                    logger,
                    f"情感分类请求失败: {e}，准备重试 (attempt {attempt + 1}/{max_retries})",
                    "Attitude"
                )
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue

    # 重试全部失败时，fallback 为 neutral
    if logger:
        log_error(logger, f"单条情感分类失败，已重试 {max_retries} 次，fallback 为 neutral", "Attitude")
    return 'neutral'


def _run_async_classify(coro):
    """运行异步协程"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    else:
        # 已有运行中的循环，使用 create_task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=1800)  # 30 分钟超时，支持大量数据分类


def _classify_unknown_sentiments(
    df: pd.DataFrame,
    logger=None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    max_concurrent: int = 15,
) -> pd.DataFrame:
    """
    对 unknown 情感的数据进行 AI 分类（逐条并发处理）

    Args:
        df: 已标准化 attitude 列的数据框
        logger: 日志记录器
        progress_callback: 进度回调函数
        max_concurrent: 最大并发请求数，控制 QPS

    Returns:
        pd.DataFrame: 更新后的数据框
    """
    if 'attitude' not in df.columns:
        return df

    # 找出 unknown 的记录
    unknown_mask = df['attitude'] == 'unknown'
    unknown_count = unknown_mask.sum()

    if unknown_count == 0:
        return df

    df = df.copy()

    # 获取文本内容列
    text_col = None
    for col in ['contents', 'content', 'text', '正文', '内容', 'title']:
        if col in df.columns:
            text_col = col
            break

    if text_col is None:
        if logger:
            log_error(logger, "未找到文本内容列，无法进行 AI 情感分类", "Attitude")
        # 无文本列时全部 fallback 为 neutral
        df.loc[unknown_mask, 'attitude'] = 'neutral'
        return df

    if logger:
        log_module_start(logger, f"AI 情感分类 | 共 {unknown_count} 条待处理", "Attitude")

    # 提取 unknown 记录的文本
    unknown_indices = df[unknown_mask].index.tolist()
    texts_to_classify = []

    for idx in unknown_indices:
        text = str(df.loc[idx, text_col] or "").strip()
        if text and text != "未知" and text != "nan":
            texts_to_classify.append((idx, text))

    if not texts_to_classify:
        if logger:
            log_success(logger, "所有 unknown 记录无有效文本内容，跳过 AI 分类", "Attitude")
        # 无有效文本时全部 fallback 为 neutral
        df.loc[unknown_mask, 'attitude'] = 'neutral'
        return df

    total_texts = len(texts_to_classify)
    processed = 0
    classified_count = 0
    last_progress_update = [0]  # 使用列表以便在嵌套函数中修改

    async def _classify_all():
        """并发分类所有文本"""
        nonlocal processed, classified_count
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _classify_one(idx: int, text: str):
            nonlocal processed, classified_count
            async with semaphore:
                result = await _classify_single_with_retry(text, logger)
                processed += 1
                if result != 'neutral':
                    classified_count += 1
                # 进度回调 - 节流：每处理 5% 或至少每 20 条更新一次
                if progress_callback:
                    update_interval = max(20, total_texts // 20)  # 5% 或至少 20 条
                    should_update = (
                        processed >= last_progress_update[0] + update_interval or
                        processed == total_texts  # 最后一条必须更新
                    )
                    if should_update:
                        last_progress_update[0] = processed
                        try:
                            progress_callback({
                                "phase": "sentiment_classify",
                                "percentage": int(10 + (processed / max(total_texts, 1)) * 80),
                                "message": f"正在 AI 情感分类 ({processed}/{total_texts})",
                                "sentiment_phase": "classify",
                                "sentiment_total": total_texts,
                                "sentiment_processed": processed,
                                "sentiment_classified": classified_count,
                                "sentiment_remaining": total_texts - processed,
                            })
                        except Exception:
                            pass
                return (idx, result)

        tasks = [_classify_one(idx, text) for idx, text in texts_to_classify]
        return await asyncio.gather(*tasks)

    # 运行并发分类
    results = _run_async_classify(_classify_all())

    # 更新结果到 DataFrame
    for idx, label in results:
        df.loc[idx, 'attitude'] = label

    # 最终进度
    if progress_callback:
        try:
            final_unknown = (df['attitude'] == 'unknown').sum()
            classified_count = unknown_count - final_unknown
            progress_callback({
                "phase": "sentiment_classify_done",
                "percentage": 95,
                "message": f"AI 情感分类完成，成功分类 {classified_count} 条",
                "sentiment_phase": "done",
                "sentiment_total": total_texts,
                "sentiment_processed": total_texts,
                "sentiment_classified": classified_count,
                "sentiment_remaining": final_unknown,
            })
        except Exception:
            pass

    # 统计分类结果
    final_unknown = (df['attitude'] == 'unknown').sum()
    classified_count = unknown_count - final_unknown

    if logger:
        log_success(
            logger,
            f"AI 情感分类结束 | 成功分类 {classified_count} 条，剩余 {final_unknown} 条为 neutral",
            "Attitude"
        )

    return df


def analyze_attitude_overall(
    df: pd.DataFrame,
    logger=None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    分析总体态度分布

    Args:
        df (pd.DataFrame): 数据框
        logger: 日志记录器
        progress_callback: 进度回调函数

    Returns:
        Dict[str, Any]: 态度分析结果
    """
    if logger is None:
        logger = setup_logger("attitude", "analysis")

    try:
        # 进度回调：开始
        if progress_callback:
            try:
                progress_callback({
                    "phase": "attitude_start",
                    "percentage": 5,
                    "message": "开始情感分析...",
                    "sentiment_phase": "prepare",
                    "sentiment_total": 0,
                    "sentiment_processed": 0,
                    "sentiment_classified": 0,
                    "sentiment_remaining": 0,
                })
            except Exception:
                pass

        # 标准化态度字段
        df = _normalize_attitude_column(df)

        # 统计 unknown 数量
        unknown_count = (df['attitude'] == 'unknown').sum()

        # 进度回调：标准化完成
        if progress_callback:
            try:
                progress_callback({
                    "phase": "attitude_normalized",
                    "percentage": 10,
                    "message": f"情感字段标准化完成，发现 {unknown_count} 条 unknown 数据",
                    "sentiment_phase": "normalize",
                    "sentiment_total": unknown_count,
                    "sentiment_processed": 0,
                    "sentiment_classified": 0,
                    "sentiment_remaining": unknown_count,
                })
            except Exception:
                pass

        # 对 unknown 进行 AI 分类
        df = _classify_unknown_sentiments(df, logger, progress_callback)

        # 统计态度分布
        attitude_counts = df['attitude'].value_counts().to_dict()

        # 转换为数据格式
        attitude_data = [{"name": k, "value": v} for k, v in attitude_counts.items()]

        result = {
            "data": attitude_data
        }

        # 进度回调：完成
        final_unknown = (df['attitude'] == 'unknown').sum()
        classified = unknown_count - final_unknown
        if progress_callback:
            try:
                progress_callback({
                    "phase": "attitude_done",
                    "percentage": 100,
                    "message": "情感分析完成",
                    "sentiment_phase": "done",
                    "sentiment_total": unknown_count,
                    "sentiment_processed": unknown_count,
                    "sentiment_classified": classified,
                    "sentiment_remaining": final_unknown,
                })
            except Exception:
                pass

        log_success(logger, "attitude | 总体 分析完成", "Analyze")
        return result

    except Exception as e:
        log_error(logger, f"总体态度分析失败: {e}", "Analyze")
        # 返回空的data数组
        return {
            "data": []
        }


def analyze_attitude_by_channel(
    df: pd.DataFrame,
    channel_name: str,
    logger=None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    按渠道分析态度分布

    Args:
        df (pd.DataFrame): 数据框
        channel_name (str): 渠道名称
        logger: 日志记录器
        progress_callback: 进度回调函数

    Returns:
        Dict[str, Any]: 态度分析结果
    """
    if logger is None:
        logger = setup_logger("attitude", "channel")

    try:
        df = _normalize_attitude_column(df)
        df = _classify_unknown_sentiments(df, logger, progress_callback)
        attitude_counts = df['attitude'].value_counts().to_dict()
        attitude_data = [{"name": k, "value": v} for k, v in attitude_counts.items()]

        result = {
            "data": attitude_data
        }

        log_success(logger, f"attitude | {channel_name} 分析完成", "Analyze")
        return result

    except Exception as e:
        log_error(logger, f"渠道态度分析失败: {e}", "Analyze")
        return {
            "data": []
        }
