"""
态度分析函数
"""
import asyncio
import pandas as pd
from typing import Dict, List, Any, Optional, Callable
from ...utils.logging.logging import setup_logger, log_success, log_error, log_module_start
from ...utils.ai import call_langchain_chat

# AI 情感分类配置
SENTIMENT_BATCH_SIZE = 15  # 每批处理的条目数
SENTIMENT_MAX_RETRIES = 3  # 最大重试次数
SENTIMENT_RETRY_DELAY = 2.0  # 重试间隔（秒）
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


def _build_sentiment_prompt(texts: List[str]) -> List[Dict[str, str]]:
    """构建情感分类提示词"""
    numbered_texts = []
    for i, text in enumerate(texts, 1):
        truncated = _truncate_text(text)
        if truncated:
            numbered_texts.append(f"[{i}] {truncated}")

    if not numbered_texts:
        return []

    text_block = "\n".join(numbered_texts)

    system_prompt = """你是一个专业的情感分析助手。请根据文本内容判断其情感倾向。

情感分类标准：
- positive（正面）：表达赞赏、支持、满意、喜悦、期待等积极情绪
- negative（负面）：表达批评、反对、不满、愤怒、担忧等消极情绪
- neutral（中性）：客观陈述事实，无明显情感倾向，或情感模糊难以判断

请严格按照要求输出，每条文本输出一个标签，格式为：序号:标签
例如：1:positive 2:negative 3:neutral

只输出标签，不要解释原因。"""

    user_prompt = f"""请对以下文本进行情感分类，每条输出一个标签（positive/negative/neutral）：

{text_block}

请按序号输出分类结果，格式为：序号:标签（如 1:positive）"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _parse_sentiment_response(response: str) -> Dict[int, str]:
    """解析 AI 返回的情感分类结果"""
    if not response:
        return {}

    result = {}
    lines = response.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 尝试匹配格式：序号:标签 或 序号 标号 标签
        # 支持多种分隔符：冒号、空格、逗号
        parts = None
        for sep in [':', '：', ' ', ',', '，', '\t']:
            if sep in line:
                parts = line.split(sep, 1)
                break

        if not parts or len(parts) < 2:
            continue

        try:
            idx = int(parts[0].strip().replace('[', '').replace(']', ''))
            label = parts[1].strip().lower()

            # 标准化标签
            if label in ['positive', 'pos', 'p', '正面', '积极']:
                result[idx] = 'positive'
            elif label in ['negative', 'neg', 'n', '负面', '消极']:
                result[idx] = 'negative'
            elif label in ['neutral', 'neu', '中性', '客观']:
                result[idx] = 'neutral'
        except Exception:
            continue

    return result


async def _classify_batch_with_retry(
    texts: List[str],
    logger,
    max_retries: int = SENTIMENT_MAX_RETRIES,
    retry_delay: float = SENTIMENT_RETRY_DELAY,
) -> Dict[int, str]:
    """带重试机制的分批情感分类"""
    if not texts:
        return {}

    messages = _build_sentiment_prompt(texts)
    if not messages:
        return {}

    for attempt in range(max_retries):
        try:
            response = await call_langchain_chat(
                messages,
                task="analyze",
                max_tokens=300,
                timeout=60,
                max_retries=1,  # 单次请求由 LangChain 内部处理
            )

            if response:
                parsed = _parse_sentiment_response(response)
                if parsed:
                    # 验证解析结果覆盖率
                    coverage = len(parsed) / len(texts)
                    if coverage >= 0.7:  # 70% 以上有效则接受
                        if coverage < 1.0 and logger:
                            log_error(
                                logger,
                                f"情感分类部分有效 ({len(parsed)}/{len(texts)})，已接受",
                                "Attitude"
                            )
                        return parsed
                    elif attempt < max_retries - 1:
                        if logger:
                            log_error(
                                logger,
                                f"情感分类覆盖率不足 ({coverage:.1%})，准备重试 (attempt {attempt + 1}/{max_retries})",
                                "Attitude"
                            )
                        await asyncio.sleep(retry_delay)
                        continue

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

    if logger:
        log_error(logger, f"情感分类失败，已重试 {max_retries} 次", "Attitude")
    return {}


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
            return future.result(timeout=120)


def _classify_unknown_sentiments(
    df: pd.DataFrame,
    logger=None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> pd.DataFrame:
    """
    对 unknown 情感的数据进行 AI 分类

    Args:
        df: 已标准化 attitude 列的数据框
        logger: 日志记录器
        progress_callback: 进度回调函数

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
        return df

    total_texts = len(texts_to_classify)
    processed = 0

    # 分批处理
    batch_size = SENTIMENT_BATCH_SIZE

    for batch_start in range(0, total_texts, batch_size):
        batch_end = min(batch_start + batch_size, total_texts)
        batch_items = texts_to_classify[batch_start:batch_end]
        batch_texts = [item[1] for item in batch_items]
        batch_indices = [item[0] for item in batch_items]

        # 调用 AI 分类
        parsed = _run_async_classify(
            _classify_batch_with_retry(batch_texts, logger)
        )

        # 更新结果并统计本批次分类数
        classified_in_batch = 0
        for i, idx in enumerate(batch_indices, 1):
            if i in parsed:
                df.loc[idx, 'attitude'] = parsed[i]
                classified_in_batch += 1

        processed += len(batch_items)

        # 进度回调：更新分类结果
        if progress_callback:
            try:
                progress_callback({
                    "phase": "sentiment_classify",
                    "percentage": int(10 + (processed / max(total_texts, 1)) * 80),
                    "message": f"正在 AI 情感分类 ({processed}/{total_texts})",
                    "total_unknown": total_texts,
                    "processed_unknown": processed,
                    "sentiment_phase": "classify",
                    "sentiment_total": total_texts,
                    "sentiment_processed": processed,
                    "sentiment_classified": classified_in_batch,
                    "sentiment_remaining": total_texts - processed,
                })
            except Exception:
                pass

        if logger:
            log_success(
                logger,
                f"AI 情感分类批次完成 ({processed}/{total_texts})",
                "Attitude"
            )

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
            f"AI 情感分类结束 | 成功分类 {classified_count} 条，剩余 {final_unknown} 条仍为 unknown",
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